# TFT Coach

A personal Teamfight Tactics coaching assistant. It ingests my TFT match history from the Riot API, compares it with high-elo games, and answers questions using retrieval over patch notes. Stats are computed in code; the LLM only explains them.

> Status: Milestone 1 (match data pipeline) complete. See [`PLAN.md`](PLAN.md) for the roadmap and [`docs/decisions.md`](docs/decisions.md) for design decisions.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then set RIOT_API_KEY
createdb tftcoach && createdb tftcoach_test   # local Postgres
uv run python -m tftcoach.db init             # tables + patch dates
uv run python -m tftcoach.db load-static      # display names from Community Dragon
uv run pytest
```

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

Comp                             Games Avg place  Top 4
Executioner Zyra                     3      5.00    33%  (small sample)
Juggernaut Zyra                      2      3.50    50%  (small sample)
Vanguard Aphelios                    2      4.00    50%  (small sample)
...
```

**Ingestion** stores each untouched API response in `raw_matches` (JSONB) and parses it into `matches`, `participants`, `traits`, and `units` in one transaction per match. Before fetching, it skips every match ID already stored, so a re-run makes zero match-detail calls (150 matches: 153 calls the first run, 2 the second, both just the match-ID list). A sliding-window rate limiter keeps requests under the development-key limits (20/s, 100/2 min), with 429 retries as a backstop; 150 matches take about 2 minutes.

**Patches.** Riot's `game_version` no longer contains the patch number, so each match's patch is the latest entry in `src/tftcoach/db/patches.csv` that started on or before the match's Pacific-time date.

**Comps** are labeled "<main trait> <carry>", computed at query time:
- *carry*: the unit whose items contain the most offensive components (B.F. Sword, Recurve Bow, Rod, Tear), so an itemized tank isn't mistaken for the carry.
- *main trait*: the active, non-unique trait with the most units.

**Stats** (`--patch latest | previous | all | 18.3`) default to ranked games only. Comps with fewer than 10 games are marked as a small sample.

**What's not available:** augments (removed from the match API in Set 13) and anything round-by-round. See `docs/decisions.md`.
