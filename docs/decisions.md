# Design decisions

One short entry per notable decision: what, why, and what I'd revisit.

## 2026-10-09: uv and a `src/` layout

**Decision:** Manage the project with `uv` (venv, lockfile, runner) and put code under `src/tftcoach/`.
**Why:** One tool replaces pip + venv + pip-tools, and the lockfile makes installs reproducible. The `src/` layout forces tests to import the installed package rather than whatever is in the working directory, which catches packaging mistakes early.

## 2026-10-09: API key as `SecretStr`, loaded only from env

**Decision:** `pydantic-settings` reads `RIOT_API_KEY` from the environment / `.env` into a `SecretStr`.
**Why:** `SecretStr` renders as `**********` in reprs, logs, and tracebacks, so "never print the key" is enforced by the type rather than by discipline. `RiotAPIError` messages include only the request path, never headers, for the same reason.

## 2026-10-09: Injectable transport and sleep in `RiotClient`

**Decision:** The client accepts an optional `httpx` transport and `sleep` function.
**Why:** Tests swap in `httpx.MockTransport` and a recording `sleep`, so the 429 backoff is tested deterministically, with no network and no real waiting, without a mocking library.

## 2026-10-09: Retry 429s from the start

**Decision:** Basic 429 retry (up to 3 times, honoring `Retry-After`) lives in the client from Milestone 0, ahead of the full caching work in Milestone 1.
**Why:** Development keys allow 100 requests per 2 minutes, so even ad hoc runs can hit the limit. Putting it at the lowest layer means every caller gets it.

## 2026-10-09: No augment data

**Decision:** Drop augments from the schema and analysis. Derive each match's patch from its date.
**Why:** Riot removed augments from match history starting with Set 13 to curb augment stat sites. Set 18 match payloads confirm the field is absent. Third-party sites appear to collect augments through client-side apps, which conflicts with this project's between-games-only rule, and manual logging wasn't worth the friction. `game_version` is also blank (`"?.?.?.?"`), so the patch is looked up from `game_datetime` against patch release dates. Augment changes still reach the coach through patch notes (Milestones 2–3).

## 2026-10-09: Postgres from Milestone 1, plain SQL with psycopg

**Decision:** Use Postgres (with pgvector available) now instead of SQLite, and write SQL directly with `psycopg` and a `schema.sql` file instead of using an ORM.
**Why:** Postgres was already installed, and starting there avoids a migration when pgvector arrives in Milestone 2. The stats are aggregates over joins, which read clearly as SQL. The schema is idempotent (`IF NOT EXISTS`), which is enough until there's real migration pressure.

## 2026-10-09: Keep raw API responses

**Decision:** Every match payload is stored unchanged in `raw_matches` (JSONB) next to the parsed tables.
**Why:** It makes "never refetch a match" a primary-key lookup, and the parsed tables can be rebuilt after a schema or parser change without spending rate limit.

## 2026-10-09: Client-side rate limiter

**Decision:** A sliding-window limiter (20 per 1 s, 100 per 120 s) runs before every request; 429 retry remains as a fallback.
**Why:** Avoiding 429s is cheaper than recovering from them, since Riot can penalize keys that keep exceeding limits. A real 150-match ingest finished in 2 min 11 s with no 429s.

## 2026-10-09: Comp = main trait + carry, carry chosen by offensive components

**Decision:** A comp is labeled "<main trait> <carry>" at query time. The carry is the unit whose items contain the most offensive components; the main trait is the active non-unique trait with the most units.
**Why:** The API has no comp label. The first version picked the unit with the most items, but tanks often hold three items too, so boards came out as "Vanguard Taric" instead of the Aphelios carry. Scoring by item recipe (from Community Dragon) fixed that. Computing the label at query time means the definition can change without re-ingesting.
**Revisit:** On real data, 33 games in one patch split into 26 comps, so nearly every comp is below the 10-game threshold.

## 2026-10-09: Pure analysis functions, SQL only for loading

**Decision:** SQL loads a player's boards; comp labeling and aggregation are plain Python functions over dataclasses.
**Why:** The logic that matters (who is the carry, how stats are computed) is unit-tested with hand-built boards and no database. A small set of integration tests covers the SQL against a real `tftcoach_test` database.
