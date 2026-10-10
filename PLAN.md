# TFT Coach: build plan

Work through these in order. Each milestone ends with something working and demoable. Stop for review after each one.

## Milestone 0: setup

- [x] Repo scaffold: `src/tftcoach/` package, `tests/`, `pyproject.toml`, `.gitignore` (include `.env`), `.env.example`, README stub, `docs/decisions.md`
- [x] Riot API client: Riot ID → PUUID → last 20 TFT match IDs → one match's details
- [x] Save one raw match JSON to `tests/fixtures/` for tests

**Done when:** `python -m tftcoach.riot --riot-id "Name#TAG"` prints 20 match IDs and saves one match JSON. API key is read from `.env` only.

## Milestone 1: match data pipeline

- [x] Ingestion command that fetches the last 100+ matches, skips ones already stored, and handles 429 with backoff
- [x] Database schema: `matches` (incl. patch), `participants`, `traits`, `units` (with star level and items)
- [x] Patch lookup from match date (the API's `game_version` no longer contains the patch number)
- [x] ID-to-display-name mapping from static TFT data
- [x] Stats functions: games per comp, average placement, top-4 rate, all filterable by patch
- [x] Tests for parsing and stats using fixtures

**Done when:** a CLI command prints "your top 5 comps last patch" with game count, average placement, and top-4 rate. Re-running ingestion makes zero duplicate API calls.

## Milestone 2: patch-notes RAG + first end-to-end version

- [x] Store patch notes for the last 3–4 patches as text files tagged by patch number (I'll provide or point to sources)
- [x] Chunk by section (trait / unit / augment / system), embed, store with patch metadata
- [x] Retrieval that filters or boosts by patch so newest wins
- [x] Tool-calling agent with `get_my_stats(patch)` and `search_patch_notes(query, patch)`
- [x] Streamlit chat UI

**Done when:** asking "what should I watch out for this patch?" returns an answer grounded in my match stats and cited patch-note chunks.

## Milestone 3: structured patch changes + proactive alerts

- [ ] LLM extraction of patch changes into JSON (entity, entity type, stat, old value, new value, direction), validated with pydantic, stored in Postgres
- [ ] Join changes with my most-played traits and units from the previous patch
- [ ] "Patch briefing" generator: which of my comps were buffed or nerfed, and by how much

**Done when:** running the briefing for a new patch produces messages like "You played 6 Juggernauts a lot last patch, and it was nerfed: [specific changes]."

## Milestone 4: "why isn't this working" analysis

- [ ] Ingest high-elo matches (Challenger/Grandmaster ladder → recent matches) as a baseline, within rate limits
- [ ] For a comp: compare me vs. baseline on carry items, star levels, level at elimination, round eliminated, gold left, damage dealt, and how contested the comp was in the lobby
- [ ] Compare my own top-4 vs. bottom-4 games on the same comp
- [ ] Sample-size guard: fewer than ~10 games → "not enough data yet"
- [ ] Add `compare_comp(comp, patch)` tool to the agent
- [ ] Tests for comparison functions

**Done when:** "why do I keep going 6th on this comp?" returns specific, data-backed patterns, each traceable to computed numbers.

## Milestone 5: evaluation + quality

- [ ] Eval set of 100–150 questions in `evals/` with expected answers, covering:
  - Patch facts (was X changed in patch Y?)
  - Numeric changes (old/new values)
  - Personal stats (compare against computed values)
  - Retrieval recall@k (right patch, right entity)
  - Grounding (every number in the answer appears in tool output)
  - Coaching quality (LLM-as-judge with a rubric; I'll spot-check)
- [ ] Eval runner that outputs a results table
- [ ] Experiments: section vs. fixed-size chunking; vector vs. hybrid search; with/without reranker; patch filter on/off
- [ ] Caching for API calls and embeddings; record latency and cost per question

**Done when:** README has a results table with accuracy, latency, and cost for each experiment, and the best config is the default.

## Milestone 6: ship it

- [ ] FastAPI backend + React/Next.js frontend (or keep Streamlit if time is short; ask me)
- [ ] Deploy (Render, Fly.io, or Railway) with managed Postgres + pgvector
- [ ] Scheduled job to pull new matches and new patch notes
- [ ] README polish: demo GIF placeholder, architecture diagram, setup steps, eval results, what didn't work

**Done when:** a public URL works end to end and the README is complete.

## Stretch (only after Milestone 6)

- Pivot suggestions based on what's winning at high elo
- Discord bot for patch briefings
- Multi-user support (needs the right Riot key approval)
- Screenshot analysis for positioning
- Post-game notes from the user
- Trend charts over time
