# TFT Coach

A personal Teamfight Tactics coaching assistant. It ingests my TFT match history from the Riot API, compares it with high-elo games, and answers questions using retrieval over patch notes. Stats are computed in code; the LLM only explains them.

> Status: Milestone 0 (setup) complete. See [`PLAN.md`](PLAN.md) for the roadmap and [`docs/decisions.md`](docs/decisions.md) for design decisions.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then set RIOT_API_KEY
uv run pytest
```

Get an API key at [developer.riotgames.com](https://developer.riotgames.com). Development keys expire every 24 hours; a registered Personal API Key does not.

## Milestone 0: Riot API client

`tftcoach.riot.RiotClient` wraps the three endpoints the project starts from: Riot ID → PUUID, PUUID → recent TFT match IDs, and match ID → match details. It uses regional routing (configurable via `RIOT_REGION`), sends the key in the `X-Riot-Token` header, and retries HTTP 429 responses after the `Retry-After` delay.

```bash
uv run python -m tftcoach.riot --riot-id "Name#TAG"
```

This prints the 20 most recent match IDs and saves the newest match to `tests/fixtures/` for use in offline tests. Unit tests mock HTTP with `httpx.MockTransport`, so the suite never calls the live API.
