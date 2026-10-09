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
