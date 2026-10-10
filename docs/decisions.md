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

## 2026-10-09: Group comps by carry by default

**Decision:** Comps are grouped by carry alone, showing the most common main trait as a detail; `--by-trait` gives the "<main trait> <carry>" split.
**Why:** On real data, trait+carry split 33 games in one patch into 26 comps, so nothing reached the 10-game threshold. The trait often changes between games on the same board (Zyra appeared as both "Executioner Zyra" and "Juggernaut Zyra"), which says more about the label than the strategy. Grouping by carry gave 17 groups on the same patch, with the largest at 6 games. That's still small, which is why the high-elo baseline in Milestone 4 matters.

## 2026-10-09: Tank shown as a detail, not part of the comp key

**Decision:** Each comp row shows its usual tank (the non-carry unit with the most defensive item components), but comps stay grouped by carry only.
**Why:** Grouping by carry + tank split 33 games on one patch into 25 groups, nearly as many as trait + carry (26), because the same carry is played with different tanks (Draven with Maokai or Amumu). Showing the most common tank keeps that information without shrinking the sample sizes.

## 2026-10-09: Gemini free tier for the LLM and embeddings, behind an OpenAI-compatible interface

**Decision:** Use a Gemini Flash model for chat/tool calling (see the next entry for which) and `gemini-embedding-2` for embeddings, both through Gemini's OpenAI-compatible endpoint. Provider, key, and model names come from `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, and `EMBEDDING_MODEL`.
**Why:** The free tier needs no card and covers both tool calling and embeddings, so one key serves the whole LLM layer. Meta's Muse Spark (Contributor tier) was the first choice but requires billing setup. Because both providers speak the OpenAI Chat Completions format, switching is a `.env` change, not a code change. The model is pinned rather than `-latest` so eval results stay reproducible.
**Trade-off:** On free/Contributor tiers the provider may use prompts for training. Tools therefore send only the user's aggregated stats and public patch notes, never other players' names or PUUIDs.

## 2026-10-09: Default chat model is gemini-3.1-flash-lite

**Decision:** Default `LLM_MODEL` to `gemini-3.1-flash-lite` instead of `gemini-3.8-flash`.
**Why:** The free tier allows only 20 requests per day for `gemini-3.8-flash`, and one coaching question takes 3-6 requests, so the quota ran out during development. Its responses also took 10-250 s per round. On the same question, Flash-Lite answered in about 6 s total, called the right tools (stats, then one search per carry), cited the right chunks, and every number passed the grounding check. Quotas are per model, so the bigger model is a one-line `.env` change for comparison in Milestone 5.
**Also:** The HTTP client now gives up immediately when the server's requested retry delay exceeds 60 s (a daily quota said "retry in 85045s"), instead of retrying for minutes.

## 2026-10-09: Entity-level chunks instead of whole sections

**Decision:** Each changed trait/unit/item (a top-level bullet with its nested changes) is its own chunk, with the designer's "Name: why" paragraph attached. Flat lists stay grouped and are split only when long.
**Why:** A section like Traits covers about 10 traits. Retrieving the whole section for "was Juggernaut nerfed?" fills the context with unrelated changes and invites the model to mix values between traits. Entity chunks make each citation point at exactly one change. Milestone 5 compares this against section and fixed-size chunking.

## 2026-10-09: Hybrid scoring with a cutoff

**Decision:** Score = cosine similarity + 0.10 if the chunk contains a query word; drop results under 0.65.
**Why:** Bare unit names embed poorly. "Maokai" (not in the 18.4 notes) matched unrelated chunks at 0.63 while the real Juggernaut chunk scored 0.67. The lexical bonus lifts exact-name matches, and the cutoff means a search for an unchanged unit returns nothing. The empty result tells the model "no changes" ("There were no patch note changes for Morgana") instead of handing it irrelevant text to misread. The constants are hand-tuned on spot checks and are a Milestone 5 experiment.

## 2026-10-09: Newest-wins re-ranking

**Decision:** Without a patch filter, scores lose 0.03 per patch of age, and if an entity appears in several patches only its newest chunk is kept.
**Why:** If a value changed in 18.2 and again in 18.4, returning both invites the model to quote the stale one. Asking about a specific patch filters instead, so history is still reachable.

## 2026-10-09: Grounding check by number matching

**Decision:** Extract every number from the answer and require a number in the tool output (or question/system prompt) that rounds to it at the answer's precision; also accept fraction-to-percent. Star levels, "top 4", and lobby size are always allowed. Citation ids are ignored.
**Why:** It's the CLAUDE.md rule made testable, and cheap enough to run on every answer. Answers aren't blocked, because false positives are possible; the UI shows a warning instead, and Milestone 5 measures how often it fires. The prompt also forbids computing differences ("quote old ⇒ new values"), because derived numbers can't be verified this way.

## 2026-10-09: Agent loop details

**Decision:** Hand-written loop, max 6 rounds, last round sent without tools; chunks already shown in a turn are replaced with "already shown above"; assistant messages are appended back unchanged.
**Why:** The first live run made 15 tool calls, grew the context to tens of thousands of tokens (one round took 175 s), and hit the round limit without answering. Withholding tools on the final round guarantees an answer, and not resending chunks keeps context small. Gemini attaches signatures to tool calls that must be sent back verbatim, so replies aren't rebuilt.

## 2026-10-09: Default stats scope is the whole set

**Decision:** The tool description and system prompt tell the model to use patch "all" (every patch of the current set) for "how am I doing" questions unless a patch is named.
**Why:** Asked about Draven "this set", the model first fetched only the latest patch (1 game, "not enough data") although the set had 11 games. Per-patch samples are usually under the 10-game threshold.
