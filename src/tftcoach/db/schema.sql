-- TFT Coach schema. Idempotent: safe to run on every `db init`.

-- Untouched API responses. A match ID here is never fetched again, and every
-- table below can be rebuilt from these payloads without touching the API.
CREATE TABLE IF NOT EXISTS raw_matches (
    match_id   TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Riot ID -> PUUID cache, so re-running ingestion skips the account lookup.
CREATE TABLE IF NOT EXISTS players (
    puuid     TEXT PRIMARY KEY,
    game_name TEXT NOT NULL,
    tag_line  TEXT NOT NULL,
    UNIQUE (game_name, tag_line)
);

-- Patch release dates, seeded from patches.csv. Riot's game_version field no
-- longer carries the patch number, so a match's patch is looked up by date.
CREATE TABLE IF NOT EXISTS patches (
    patch      TEXT PRIMARY KEY,
    set_number INTEGER NOT NULL,
    start_date DATE NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS matches (
    match_id      TEXT PRIMARY KEY REFERENCES raw_matches (match_id),
    game_datetime TIMESTAMPTZ NOT NULL,
    game_length   REAL NOT NULL,
    queue_id      INTEGER NOT NULL,
    set_number    INTEGER NOT NULL,
    patch         TEXT REFERENCES patches (patch)
);
CREATE INDEX IF NOT EXISTS matches_patch_idx ON matches (patch);

-- All 8 players per match, not just the tracked user: contested-comp and
-- high-elo baseline analysis need the other boards.
CREATE TABLE IF NOT EXISTS participants (
    match_id           TEXT NOT NULL REFERENCES matches (match_id) ON DELETE CASCADE,
    puuid              TEXT NOT NULL,
    placement          INTEGER NOT NULL CHECK (placement BETWEEN 1 AND 8),
    level              INTEGER NOT NULL,
    gold_left          INTEGER NOT NULL,
    last_round         INTEGER NOT NULL,
    time_eliminated    REAL NOT NULL,
    players_eliminated INTEGER NOT NULL,
    damage_to_players  INTEGER NOT NULL,
    game_name          TEXT,
    tag_line           TEXT,
    PRIMARY KEY (match_id, puuid)
);
CREATE INDEX IF NOT EXISTS participants_puuid_idx ON participants (puuid);

CREATE TABLE IF NOT EXISTS traits (
    match_id     TEXT NOT NULL,
    puuid        TEXT NOT NULL,
    trait_id     TEXT NOT NULL,
    num_units    INTEGER NOT NULL,
    style        INTEGER NOT NULL,
    tier_current INTEGER NOT NULL,
    tier_total   INTEGER NOT NULL,
    PRIMARY KEY (match_id, puuid, trait_id),
    FOREIGN KEY (match_id, puuid) REFERENCES participants (match_id, puuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS units (
    id           BIGSERIAL PRIMARY KEY,
    match_id     TEXT NOT NULL,
    puuid        TEXT NOT NULL,
    character_id TEXT NOT NULL,
    star_level   INTEGER NOT NULL,
    rarity       INTEGER NOT NULL,
    items        TEXT[] NOT NULL DEFAULT '{}',
    FOREIGN KEY (match_id, puuid) REFERENCES participants (match_id, puuid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS units_participant_idx ON units (match_id, puuid);

-- Internal API names (DA_18_Diana) -> display names (Diana), from Community Dragon.
CREATE TABLE IF NOT EXISTS static_names (
    api_name     TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('unit', 'trait', 'item')),
    display_name TEXT NOT NULL,
    set_number   INTEGER
);
-- For items: the two components it is built from, used to tell carries from tanks.
ALTER TABLE static_names ADD COLUMN IF NOT EXISTS components TEXT[];

-- Patch-note retrieval (Milestone 2) -----------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;

-- Embeddings keyed by content hash, so re-chunking or re-indexing only embeds text
-- that actually changed.
CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT NOT NULL,
    model        TEXT NOT NULL,
    embedding    vector(768) NOT NULL,
    PRIMARY KEY (content_hash, model)
);

-- One row per chunk. Rebuilt per patch on every index run; chunk_key ("18.4-12") is
-- what the agent cites. 768-dim vectors with exact search: a few hundred rows don't
-- need an ANN index.
CREATE TABLE IF NOT EXISTS patch_chunks (
    chunk_key    TEXT PRIMARY KEY,
    patch        TEXT NOT NULL REFERENCES patches (patch),
    section      TEXT NOT NULL,
    entity       TEXT,
    midpatch     TEXT,  -- mid-patch update heading (e.g. "OCTOBER 7TH"), NULL for main notes
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding    vector(768) NOT NULL
);
CREATE INDEX IF NOT EXISTS patch_chunks_patch_idx ON patch_chunks (patch);
