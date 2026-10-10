"""The tool-calling loop, written by hand.

1. Send the conversation and tool specs to the model.
2. If it asks for tools, run them, append the results, and go back to 1.
3. Otherwise its message is the answer; check its numbers and citations.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field

from tftcoach.agent.grounding import GroundingReport, check_grounding
from tftcoach.agent.llm import ChatModel, Message
from tftcoach.agent.tools import MIN_GAMES_FOR_CONCLUSIONS, TOOL_SPECS, ToolContext, run_tool

log = logging.getLogger(__name__)

MAX_ROUNDS = 6
FINAL_ROUND_PROMPT = (
    "You have used all your tool calls. Answer now using only the tool results above; "
    "if they aren't enough, say what is missing."
)
CITATION = re.compile(r"\[(\d+\.\d+-\d+)\]")

SYSTEM_PROMPT = """\
You are a Teamfight Tactics coach for one player. Today the current set is {set_number} \
and the current patch is {current_patch}. Patch notes are available for: {note_patches}.

Rules:
- Answer only from tool results. Call get_my_stats for anything about the player's games \
and search_patch_notes for anything about balance changes. Never use outside knowledge \
of TFT numbers.
- Every number you write must appear in a tool result. Quote values as given \
(e.g. "20/33/45% ⇒ 20/30/42%"); do not compute differences or new percentages.
- For how the player is doing (with a unit, comp, or overall), use get_my_stats with \
patch "all" unless they ask about a specific patch: per-patch samples are usually too small.
- For questions about what matters to the player, first get their stats, then search the \
patch notes for their carries, tanks, and traits by name (one search per name).
- Cite patch notes with their id in square brackets, e.g. [18.4-20], right after the claim.
- If a comp has enough_data=false (fewer than {min_games} games), say there isn't enough \
data to draw conclusions about it instead of judging it.
- Describe "why" as patterns and correlations in the data, not certainties.
- Be concise and practical: a short answer, then the supporting points.
"""


@dataclass
class ToolCallRecord:
    name: str
    arguments: str
    result: str


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    grounding: GroundingReport = field(default_factory=lambda: GroundingReport(0, []))
    citations: list[str] = field(default_factory=list)
    unknown_citations: list[str] = field(default_factory=list)

    def cited_sources(self) -> dict[str, str]:
        """Text of each cited patch-note chunk, in citation order, for display."""
        texts: dict[str, str] = {}
        for record in self.tool_calls:
            if record.name != "search_patch_notes":
                continue
            for item in json.loads(record.result).get("results", []):
                if "text" in item:
                    texts[item["id"]] = item["text"]
        return {key: texts[key] for key in self.citations if key in texts}


def system_prompt(set_number: int, current_patch: str, note_patches: list[str]) -> str:
    return SYSTEM_PROMPT.format(
        set_number=set_number,
        current_patch=current_patch,
        note_patches=", ".join(note_patches) or "none",
        min_games=MIN_GAMES_FOR_CONCLUSIONS,
    )


def run_agent(
    question: str,
    ctx: ToolContext,
    model: ChatModel,
    system: str,
    history: list[Message] | None = None,
) -> AgentResult:
    messages: list[Message] = [{"role": "system", "content": system}, *(history or [])]
    messages.append({"role": "user", "content": question})
    records: list[ToolCallRecord] = []
    ctx.retrieved_chunks.clear()

    answer = None
    for round_number in range(1, MAX_ROUNDS + 1):
        final_round = round_number == MAX_ROUNDS
        if final_round:
            # Withhold tools on the last round so the model must answer with what it has.
            messages.append({"role": "user", "content": FINAL_ROUND_PROMPT})
        started = time.monotonic()
        reply = model.complete(messages, [] if final_round else TOOL_SPECS)
        log.info("round %d: model replied in %.1fs", round_number, time.monotonic() - started)
        # Append the reply unchanged: some providers (Gemini) attach signatures to tool
        # calls that must be sent back verbatim on the next request.
        messages.append(reply)
        tool_calls = reply.get("tool_calls") or []
        if not tool_calls or final_round:
            answer = reply.get("content") or ""
            break
        for call in tool_calls:
            fn = call["function"]
            log.info("  tool %s(%s)", fn["name"], fn.get("arguments"))
            result = run_tool(ctx, fn["name"], fn.get("arguments") or "{}")
            records.append(ToolCallRecord(fn["name"], fn.get("arguments") or "{}", result))
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    if answer is None:
        answer = "I couldn't finish answering within the tool-call limit. Try a narrower question."

    citations = list(dict.fromkeys(CITATION.findall(answer)))
    return AgentResult(
        answer=answer,
        tool_calls=records,
        grounding=check_grounding(answer, [system, question] + [r.result for r in records]),
        citations=citations,
        unknown_citations=[c for c in citations if c not in ctx.retrieved_chunks],
    )


def tool_result_preview(record: ToolCallRecord, limit: int = 400) -> str:
    text = json.dumps(json.loads(record.result), indent=1, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " ..."
