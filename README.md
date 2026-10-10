# TFT Coach

A personal Teamfight Tactics coaching assistant. It ingests my TFT match history from the Riot API, compares it with high-elo games, and answers questions using retrieval over patch notes. Stats are computed in code; the LLM only explains them.

> Status: Milestone 2 (patch-notes RAG + chat agent) complete. See [`PLAN.md`](PLAN.md) for the roadmap and [`docs/decisions.md`](docs/decisions.md) for design decisions.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then set RIOT_API_KEY
createdb tftcoach && createdb tftcoach_test   # local Postgres
uv run python -m tftcoach.db init             # tables + patch dates
uv run python -m tftcoach.db load-static      # display names from Community Dragon
uv run python -m tftcoach.rag index           # chunk + embed patch_notes/ into pgvector
uv run pytest
```

The LLM settings in `.env` point at any OpenAI-compatible endpoint. The default is Google's Gemini free tier (key from [AI Studio](https://aistudio.google.com), no card needed): `gemini-3.1-flash-lite` for chat and `gemini-embedding-2` for embeddings.

Get an API key at [developer.riotgames.com](https://developer.riotgames.com). Development keys expire every 24 hours; a registered Personal API Key does not.

## Milestone 0: Riot API client

`tftcoach.riot.RiotClient` wraps the three endpoints the project starts from: Riot ID → PUUID, PUUID → recent TFT match IDs, and match ID → match details. It uses regional routing (configurable via `RIOT_REGION`), sends the key in the `X-Riot-Token` header, and retries HTTP 429 responses after the `Retry-After` delay.

```bash
uv run python -m tftcoach.riot --riot-id "Name#TAG"
```

This prints the 20 most recent match IDs and saves the newest match to `tests/fixtures/` for use in offline tests. Unit tests mock HTTP with `httpx.MockTransport`, so the suite never calls the live API.

## Milestone 1: match data pipeline

```bash
uv run python -m tftcoach.ingest --riot-id "Name#TAG" --count 150
uv run python -m tftcoach.analysis top-comps --riot-id "Name#TAG" --patch previous
```

```
Top 5 comps for monk#monke, patch 18.3 (ranked, 33 games)

Carry                    Usual tank       Usual trait      Games Avg place  Top 4
Zyra                     Malphite         Executioner          6      5.00    33%  (small sample)
Draven                   Maokai           Elderwood            5      5.60    20%  (small sample)
Ashe                     Maokai           Juggernaut           4      3.75    75%  (small sample)
...
```

**Ingestion** stores each untouched API response in `raw_matches` (JSONB) and parses it into `matches`, `participants`, `traits`, and `units` in one transaction per match. Before fetching, it skips every match ID already stored, so a re-run makes zero match-detail calls (150 matches: 153 calls the first run, 2 the second, both just the match-ID list). A sliding-window rate limiter keeps requests under the development-key limits (20/s, 100/2 min), with 429 retries as a backstop; 150 matches take about 2 minutes.

**Patches.** Riot's `game_version` no longer contains the patch number, so each match's patch is the latest entry in `src/tftcoach/db/patches.csv` that started on or before the match's Pacific-time date.

**Comps** are grouped by carry, with the most common tank and main trait shown alongside. `--by-trait` splits them into "<main trait> <carry>" instead. Both are computed at query time:
- *carry*: the unit whose items contain the most offensive components (B.F. Sword, Recurve Bow, Rod, Tear), so an itemized tank isn't mistaken for the carry.
- *tank*: the other unit whose items contain the most defensive components (Chain Vest, Negatron Cloak, Giant's Belt).
- *main trait*: the active, non-unique trait with the most units.

Grouping by carry is the default because the tank and main trait vary between games on the same board: on real data, 33 games in one patch split into 26 trait+carry or 25 carry+tank groups, but only 17 carries.

**Stats** default to ranked games in your current set. `--patch latest | previous | all | 18.3` picks patches within that set; `--set 17` or `--set all` looks at other sets, since units and traits don't carry over between sets. Comps with fewer than 10 games are marked as a small sample.

**What's not available:** augments (removed from the match API in Set 13) and anything round-by-round. See `docs/decisions.md`.

## Milestone 2: patch-notes RAG and the chat agent

```bash
uv run streamlit run src/tftcoach/ui/app.py        # chat UI at http://localhost:8501
uv run python -m tftcoach.agent "What should I watch out for this patch?" --show-tools
```

Example (real output, abridged):

> You have played 11 games with Draven as your carry, averaging a 4.82 placement with a 36.4% top-4 rate. [...] Draven now refunds 50% Mana if his axes hit 0 enemies [18.4-46]. His bleed damage was increased from 140/210 AD to 150/225 AD [18.4-46].
>
> *Tool calls: get_my_stats, search_patch_notes. Grounding: all 11 numbers found in tool output.*

**Patch notes** (`patch_notes/*.md`) are downloaded from the official site with `python -m tftcoach.rag fetch 18.5` and converted to Markdown that keeps the page's headings and nested change lists.

**Chunking** follows that structure rather than a fixed size: each changed trait, unit, or item becomes one chunk together with the designer's explanation of why it changed, so "was Juggernaut nerfed?" retrieves exactly the Juggernaut change. Flat lists (bug fixes, most mid-patch updates) stay grouped. Every chunk is tagged with its patch, section, and mid-patch update date. Cosmetics and performance sections are skipped. Four patches produce 188 chunks.

**Retrieval** embeds chunks (768 dimensions) into pgvector, with an embedding cache keyed by content hash so re-indexing only embeds changed text. A query's score is cosine similarity plus a bonus when the chunk literally contains a query word (embeddings are weak at exact unit names), and weak matches are dropped, so searching for a unit that didn't change returns nothing instead of noise. Without a patch filter, older patches get a small penalty and only the newest chunk per entity is kept, so a superseded value can't be presented as current.

**The agent** is a hand-written tool-calling loop (no framework) over two tools:
- `get_my_stats(patch)`: the player's ranked comps for the current set with games, average placement, top-4 rate, and an `enough_data` flag (10+ games). It never includes other players' names or IDs.
- `search_patch_notes(query, patch)`: chunks with citable ids like `[18.4-46]`.

The loop runs up to 6 rounds; the last round withholds tools so the model must answer with what it has. Chunks already sent in the same turn aren't re-sent, which keeps the context small.

**Guardrails:**
- *Grounding check:* every number in the answer must match a number in the tool output at the answer's precision (4.82 supports "4.8"; 0.364 supports "36%"). Unmatched numbers are shown as a warning under the answer.
- *Citation check:* cited chunk ids must have been retrieved in that turn.
- *Small samples:* comps under 10 games are flagged, and the prompt requires "not enough data" instead of a judgment.

The chat UI shows each answer's cited sources and tool calls in expanders.
