import json
from typing import Any

import psycopg
import pytest

from tests.fakes import FakeEmbedder, ScriptedModel, answer, tool_call
from tests.test_db import store
from tftcoach.agent.loop import MAX_ROUNDS, run_agent, system_prompt
from tftcoach.agent.tools import ToolContext, run_tool
from tftcoach.rag.chunk import chunk_notes
from tftcoach.rag.index import index_chunks

NOTES = """## LARGE CHANGES
### TRAITS
- Juggernaut
  - Durability: 20/33/45% ⇒ 20/30/42%
"""


def setup(db: psycopg.Connection, match_payload: dict[str, Any]) -> ToolContext:
    store(db, match_payload)
    embedder = FakeEmbedder()
    index_chunks(db, "18.4", chunk_notes(NOTES, "18.4"), embedder)
    me = next(p for p in match_payload["info"]["participants"] if p["riotIdGameName"] == "monk")
    return ToolContext(conn=db, puuid=me["puuid"], embedder=embedder)


SYSTEM = system_prompt(18, "18.4", ["18.4"])

pytestmark = pytest.mark.usefixtures("fake_search_cutoff")


def test_runs_tools_then_answers(db: psycopg.Connection, match_payload) -> None:
    ctx = setup(db, match_payload)
    model = ScriptedModel(
        [
            tool_call("get_my_stats", {"patch": "current"}),
            tool_call("search_patch_notes", {"query": "Juggernaut"}, call_id="call-2"),
            answer("You placed 2 in your only game. Juggernaut: 20/33/45% ⇒ 20/30/42% [18.4-1]."),
        ]
    )

    result = run_agent("What changed?", ctx, model, SYSTEM)

    assert [c.name for c in result.tool_calls] == ["get_my_stats", "search_patch_notes"]
    stats = json.loads(result.tool_calls[0].result)
    assert stats["patch"] == "18.4" and stats["ranked_games"] == 1
    assert stats["comps"][0]["enough_data"] is False
    # The tool result was sent back to the model with the matching call id.
    tool_msg = model.received[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call-1"
    assert result.citations == ["18.4-1"] and result.unknown_citations == []
    assert result.grounding.ok
    assert "20/33/45% ⇒ 20/30/42%" in result.cited_sources()["18.4-1"]


def test_stats_never_include_other_players(db: psycopg.Connection, match_payload) -> None:
    ctx = setup(db, match_payload)
    text = run_tool(ctx, "get_my_stats", '{"patch": "latest"}')
    assert "puuid" not in text and "Player1" not in text


def test_flags_invented_numbers_and_unretrieved_citations(db: psycopg.Connection, match_payload):
    ctx = setup(db, match_payload)
    model = ScriptedModel([answer("Juggernaut lost 13% durability [18.4-99].")])

    result = run_agent("Was Juggernaut nerfed?", ctx, model, SYSTEM)

    assert result.grounding.unsupported == ["13"]
    assert result.unknown_citations == ["18.4-99"]


def test_tool_errors_are_returned_to_the_model(db: psycopg.Connection, match_payload) -> None:
    ctx = setup(db, match_payload)
    assert "error" in json.loads(run_tool(ctx, "delete_everything", "{}"))
    assert "error" in json.loads(run_tool(ctx, "get_my_stats", '{"bogus": 1}'))
    assert "error" in json.loads(run_tool(ctx, "search_patch_notes", '{"query": " "}'))


def test_last_round_forces_an_answer_without_tools(db: psycopg.Connection, match_payload):
    ctx = setup(db, match_payload)
    replies = [tool_call("get_my_stats", {"patch": "latest"})] * (MAX_ROUNDS - 1)
    model = ScriptedModel([*replies, answer("Here is what I found.")])
    tools_offered: list[int] = []
    original = model.complete
    model.complete = lambda messages, tools: (
        tools_offered.append(len(tools)),
        original(messages, tools),
    )[1]

    result = run_agent("Keep digging", ctx, model, SYSTEM)

    assert result.answer == "Here is what I found."
    assert len(result.tool_calls) == MAX_ROUNDS - 1
    assert tools_offered[-1] == 0 and all(n > 0 for n in tools_offered[:-1])


def test_repeated_chunks_are_not_resent(db: psycopg.Connection, match_payload) -> None:
    ctx = setup(db, match_payload)
    first = json.loads(run_tool(ctx, "search_patch_notes", '{"query": "Juggernaut durability"}'))
    second = json.loads(run_tool(ctx, "search_patch_notes", '{"query": "Juggernaut durability"}'))
    assert "text" in first["results"][0]
    assert second["results"][0] == {"id": first["results"][0]["id"], "note": "already shown above"}


def test_search_for_absent_name_returns_nothing(db: psycopg.Connection, match_payload) -> None:
    ctx = setup(db, match_payload)
    out = json.loads(run_tool(ctx, "search_patch_notes", '{"query": "Gnar"}'))
    assert out["results"] == [] and "No patch-note changes" in out["note"]
