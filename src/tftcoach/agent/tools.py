"""Tools the agent can call. Each returns JSON text; the LLM sees nothing else.

Tool output only ever contains the tracked player's own aggregated stats and public patch
notes, never other players' names or PUUIDs, because free/contributor LLM tiers may use
prompts for training.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import psycopg

from tftcoach.analysis.comps import display_name, summarize_comps
from tftcoach.analysis.queries import (
    CURRENT_SET,
    LATEST_PATCH,
    NoDataError,
    load_boards,
    load_display_names,
    load_item_components,
    resolve_patch,
    resolve_set,
)
from tftcoach.rag.embed import Embedder
from tftcoach.rag.search import search_notes

# Words models use for "the patch we're on" in tool arguments.
LATEST_ALIASES = {"current", "this", "now", "today", "newest", "last"}
# Below this many games, per-comp numbers are noise (CLAUDE.md: say there isn't enough data).
MIN_GAMES_FOR_CONCLUSIONS = 10
MAX_COMPS = 8
SEARCH_RESULTS = 5


@dataclass
class ToolContext:
    conn: psycopg.Connection
    puuid: str
    embedder: Embedder
    # Chunk keys returned by search_patch_notes during this turn, to validate citations.
    retrieved_chunks: set[str] = field(default_factory=set)


def get_my_stats(ctx: ToolContext, patch: str = LATEST_PATCH) -> dict[str, Any]:
    set_number = resolve_set(ctx.conn, ctx.puuid, CURRENT_SET)
    if patch.strip().lower() in LATEST_ALIASES:
        patch = LATEST_PATCH
    resolved = resolve_patch(ctx.conn, ctx.puuid, patch)
    boards = load_boards(ctx.conn, ctx.puuid, resolved, set_number=set_number)
    if not boards:
        return {"patch": resolved or "all", "ranked_games": 0, "comps": []}

    names = load_display_names(ctx.conn)
    stats = summarize_comps(boards, load_item_components(ctx.conn))
    placements = [b.placement for b in boards]

    def name(api_name: str | None) -> str | None:
        return display_name(api_name, names) if api_name else None

    return {
        "set": set_number,
        "patch": resolved or f"all patches of set {set_number}",
        "ranked_games": len(boards),
        "overall": {
            "avg_placement": round(sum(placements) / len(placements), 2),
            "top4_rate_pct": round(100 * sum(p <= 4 for p in placements) / len(placements), 1),
            "wins": sum(p == 1 for p in placements),
        },
        "min_games_for_conclusions": MIN_GAMES_FOR_CONCLUSIONS,
        "comps": [
            {
                "carry": name(s.comp.carry),
                "usual_tank": name(s.usual_tank),
                "usual_trait": name(s.usual_trait),
                "games": s.games,
                "avg_placement": round(s.avg_placement, 2),
                "top4_rate_pct": round(100 * s.top4_rate, 1),
                "enough_data": s.games >= MIN_GAMES_FOR_CONCLUSIONS,
            }
            for s in stats[:MAX_COMPS]
        ],
    }


def search_patch_notes(ctx: ToolContext, query: str, patch: str | None = None) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must name what to look for, e.g. a trait, unit, or item")
    results = search_notes(ctx.conn, ctx.embedder, query, patch or None, k=SEARCH_RESULTS)
    if not results:
        return {"results": [], "note": f"No patch-note changes found for {query!r}."}
    out = []
    for r in results:
        if r.chunk_key in ctx.retrieved_chunks:
            # Already in the conversation; don't spend tokens sending it again.
            out.append({"id": r.chunk_key, "note": "already shown above"})
            continue
        ctx.retrieved_chunks.add(r.chunk_key)
        out.append(
            {
                "id": r.chunk_key,
                "patch": r.patch,
                "section": r.section,
                "entity": r.entity,
                "mid_patch_update": r.midpatch,
                "text": r.content,
            }
        )
    return {"results": out}


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_my_stats",
            "description": (
                "The player's ranked results in the current set, grouped by comp (carry unit), "
                "with games played, average placement, top-4 rate, and whether there are "
                "enough games to draw conclusions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": (
                            '"all" = every patch of the current set (largest sample; use for '
                            '"this set" or how the player does with a unit overall), "latest" '
                            '= the current patch only, "previous", or a patch like "18.3".'
                        ),
                    }
                },
                "required": ["patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_patch_notes",
            "description": (
                "Search official patch notes for changes to traits, units, items, augments, "
                "or systems. Without a patch, newer patches are preferred. Each result has "
                "an id to cite like [18.4-20]."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for."},
                    "patch": {
                        "type": "string",
                        "description": 'Optional patch to restrict to, e.g. "18.4".',
                    },
                },
                "required": ["query"],
            },
        },
    },
]

_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_my_stats": get_my_stats,
    "search_patch_notes": search_patch_notes,
}


def run_tool(ctx: ToolContext, name: str, arguments: str) -> str:
    """Execute a tool call and return its JSON result; errors go back to the model as data."""
    tool = _TOOLS.get(name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool {name!r}"})
    try:
        args = json.loads(arguments or "{}")
        return json.dumps(tool(ctx, **args), ensure_ascii=False)
    except NoDataError as exc:
        return json.dumps({"error": str(exc)})
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"Bad arguments for {name}: {exc}"})
