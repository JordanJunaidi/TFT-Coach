# TFT Coach

A personal Teamfight Tactics coaching assistant. It ingests the user's TFT match history from the Riot API, compares it with high-elo games, and answers questions using retrieval over patch notes. The LLM explains; it never invents numbers.

This is a portfolio project for new grad SWE recruiting. Code quality, tests, a clear README, and real evaluation numbers matter as much as features.

## How to work in this repo

- Work through `PLAN.md` one milestone at a time, in order. Do not start the next milestone until the current one meets its acceptance criteria.
- At the end of each milestone: run the tests, update the README section for that milestone, tick the boxes in `PLAN.md`, and stop for my review.
- Before writing code for a milestone, briefly propose the approach (files, schema, key functions) and wait for my OK if anything is ambiguous.
- I'm using this project to learn. When you make a non-obvious design choice, explain it in one or two sentences in your reply.
- Prefer small, focused commits with clear messages.

## Architecture

Two pipelines feed one agent:

1. **Match data (structured):** Riot API → ingestion job → Postgres. Stats are computed in code/SQL, never by the LLM.
2. **Patch notes (unstructured):** patch notes text → chunk + embed → vector store (pgvector). The LLM also extracts structured changes (entity, stat, old value, new value, buff/nerf) as JSON, validated and stored in Postgres.
3. **Agent:** an LLM with tool calling. Tools: `get_my_stats(patch)`, `compare_comp(comp, patch)`, `search_patch_notes(query, patch)`. It answers only from tool output.
4. **UI:** Streamlit first; FastAPI + React/Next.js later.

## Stack

- Python 3.11+, `uv` or `pip` + venv
- Postgres with pgvector (SQLite + Chroma acceptable for milestones 1–2 only)
- `httpx` for HTTP, `pydantic` for schemas and validating LLM JSON output
- `pytest` for tests
- LLM: any provider with tool calling; key and model names come from env vars
- Write the RAG and tool-calling loop by hand first. Do not add LangChain/LangGraph unless I ask.

## Riot API notes

- Auth: API key in the `X-Riot-Token` header. Key lives in `.env` as `RIOT_API_KEY`. Never commit it, never print it, never hard-code it.
- Riot ID → PUUID: `GET https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}`
- Match IDs: `GET https://americas.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids` (params: `start`, `count`, `startTime`, `endTime`)
- Match details: `GET https://americas.api.riotgames.com/tft/match/v1/matches/{matchId}`
- Match endpoints use regional routing (AMERICAS for NA). Keep the region configurable.
- Development keys have tight rate limits. Always: cache raw responses, never refetch a stored match, back off and retry on HTTP 429 (respect `Retry-After`).
- Trait/unit IDs are internal and change every set. Map them to display names from static data; never hard-code names.
- Keep all analysis between games. No real-time, in-game advice features.

## Rules for the LLM layer

- Every number in an answer must come from tool output. Add a check that flags numbers in answers not present in tool results.
- When sample size is small (fewer than ~10 games for a comp), say there isn't enough data instead of drawing conclusions.
- Frame "why" analysis as patterns and correlations, not certainties.
- Newer patches outrank older ones in retrieval; always tag chunks with patch number.

## Conventions

- `src/` package layout: `src/tftcoach/{riot, ingest, db, analysis, rag, agent, ui}`
- Secrets via env vars only; provide `.env.example` with placeholder values.
- Type hints everywhere; tests for analysis functions and parsers use saved fixture JSON in `tests/fixtures/`, not live API calls.
- Keep a `docs/decisions.md` log: one short entry per notable design decision (I'll use these in interviews).
