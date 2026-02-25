-- ============================================================
-- HEROES' VERITAS XR SYSTEMS — DATABASE SCHEMA
-- Phase 1A — Component 1: Database & Schema
-- ============================================================
-- Run order: schema.sql → seed.py → validate_schema.py
-- Compatible: SQLite 3.x (swap to PostgreSQL for Phase 2 scale)
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- IDENTITY LAYER
-- ============================================================

CREATE TABLE IF NOT EXISTS players (
    player_id       TEXT PRIMARY KEY,           -- UUID
    account_type    TEXT NOT NULL DEFAULT 'guest'
                        CHECK(account_type IN ('guest','registered','admin','operator')),
    display_name    TEXT,
    email           TEXT UNIQUE,
    password_hash   TEXT,                       -- bcrypt in production
    device_id       TEXT,                       -- device-linked auth fallback
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- PROGRESSION LAYER
-- ============================================================

CREATE TABLE IF NOT EXISTS player_profiles (
    player_id           TEXT PRIMARY KEY REFERENCES players(player_id) ON DELETE CASCADE,
    total_xp            INTEGER NOT NULL DEFAULT 0,
    current_level       INTEGER NOT NULL DEFAULT 1,
    sessions_completed  INTEGER NOT NULL DEFAULT 0,
    best_completion_time_secs INTEGER,          -- NULL until first completion
    highest_difficulty  TEXT DEFAULT 'normal'
                            CHECK(highest_difficulty IN ('easy','normal','hard')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS player_titles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    title_key   TEXT NOT NULL,                  -- e.g. 'rune_bearer'
    unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_id, title_key)
);

CREATE TABLE IF NOT EXISTS player_loot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,                  -- references loot_items.item_id
    quantity    INTEGER NOT NULL DEFAULT 1,
    earned_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_id, item_id)
);

CREATE TABLE IF NOT EXISTS player_achievements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    achievement_key TEXT NOT NULL,
    unlocked_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_id, achievement_key)
);

-- ============================================================
-- SESSION LAYER
-- ============================================================

CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,       -- UUID
    party_session_id    TEXT,                   -- group identifier
    state               TEXT NOT NULL DEFAULT 'idle'
                            CHECK(state IN (
                                'idle','lobby','running','paused',
                                'node_transition','completed','failed',
                                'resetting','error'
                            )),
    difficulty          TEXT NOT NULL DEFAULT 'normal'
                            CHECK(difficulty IN ('easy','normal','hard')),
    current_node_id     TEXT,
    node_index          INTEGER NOT NULL DEFAULT 0,
    timer_started_at    TEXT,                   -- ISO timestamp when timer began
    timer_paused_secs   INTEGER NOT NULL DEFAULT 0, -- accumulated pause time
    total_duration_secs INTEGER NOT NULL DEFAULT 3600, -- 60 min default
    gameplay_version    TEXT,
    content_version     TEXT,
    config_version      TEXT,
    economy_version     TEXT,
    operator_id         TEXT REFERENCES players(player_id),
    room_id             TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at        TEXT,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    player_id   TEXT NOT NULL REFERENCES players(player_id),
    joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
    health      INTEGER NOT NULL DEFAULT 100,
    energy      INTEGER NOT NULL DEFAULT 100,
    is_active   INTEGER NOT NULL DEFAULT 1,     -- 0 = disconnected
    UNIQUE(session_id, player_id)
);

-- Flags emitted by puzzles and combat — the unified reward primitive
CREATE TABLE IF NOT EXISTS session_flags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    flag_id     TEXT NOT NULL,                  -- e.g. 'puzzle_1_solved'
    set_by      TEXT,                           -- node_id or 'operator'
    set_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id, flag_id)
);

-- ============================================================
-- NODE LAYER — Gameplay Graph
-- ============================================================

CREATE TABLE IF NOT EXISTS node_definitions (
    node_id         TEXT PRIMARY KEY,           -- e.g. 'node_puzzle_runes_01'
    node_type       TEXT NOT NULL
                        CHECK(node_type IN (
                            'puzzle','combat','narrative','reward','transition'
                        )),
    display_name    TEXT NOT NULL,
    description     TEXT,
    sequence_order  INTEGER NOT NULL DEFAULT 0,
    config_json     TEXT NOT NULL DEFAULT '{}', -- difficulty params, enemy counts, etc.
    entry_conditions_json TEXT DEFAULT '[]',    -- flags required to enter
    exit_conditions_json  TEXT DEFAULT '[]',    -- flags required to exit
    is_active       INTEGER NOT NULL DEFAULT 1,
    content_version TEXT
);

CREATE TABLE IF NOT EXISTS session_node_states (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL REFERENCES node_definitions(node_id),
    state           TEXT NOT NULL DEFAULT 'locked'
                        CHECK(state IN ('locked','available','in_progress','completed','failed','skipped')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    hints_used      INTEGER NOT NULL DEFAULT 0,
    entered_at      TEXT,
    completed_at    TEXT,
    time_spent_secs INTEGER NOT NULL DEFAULT 0,
    UNIQUE(session_id, node_id)
);

-- ============================================================
-- ECONOMY LAYER — Config Driven
-- ============================================================

CREATE TABLE IF NOT EXISTS level_definitions (
    level           INTEGER PRIMARY KEY,
    xp_required     INTEGER NOT NULL,           -- XP to reach this level
    reward_json     TEXT NOT NULL DEFAULT '{}' -- items/titles unlocked at this level
);

CREATE TABLE IF NOT EXISTS loot_items (
    item_id         TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    category        TEXT NOT NULL
                        CHECK(category IN (
                            'title','avatar_skin','companion_skin',
                            'weapon_skin','emblem','lore_unlock'
                        )),
    rarity          TEXT NOT NULL DEFAULT 'common'
                        CHECK(rarity IN ('common','rare','epic')),
    description     TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    content_version TEXT
);

CREATE TABLE IF NOT EXISTS loot_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id        TEXT NOT NULL,              -- e.g. 'completion_normal'
    item_id         TEXT NOT NULL REFERENCES loot_items(item_id),
    weight          INTEGER NOT NULL DEFAULT 100, -- relative probability
    difficulty      TEXT DEFAULT NULL,          -- NULL = all difficulties
    is_guaranteed   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(table_id, item_id)
);

CREATE TABLE IF NOT EXISTS achievements (
    achievement_key TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    description     TEXT,
    reward_title    TEXT,                       -- title_key unlocked
    reward_item_id  TEXT REFERENCES loot_items(item_id),
    is_active       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- TELEMETRY LAYER
-- ============================================================

CREATE TABLE IF NOT EXISTS telemetry_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL UNIQUE,       -- UUID
    session_id      TEXT REFERENCES sessions(session_id),
    player_id       TEXT REFERENCES players(player_id),
    node_id         TEXT,
    event_type      TEXT NOT NULL,              -- e.g. 'node_entered', 'hint_used'
    context_json    TEXT DEFAULT '{}',
    gameplay_version TEXT,
    config_version  TEXT,
    ts              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- OPERATOR LAYER
-- ============================================================

CREATE TABLE IF NOT EXISTS operator_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id   TEXT NOT NULL UNIQUE,           -- UUID
    operator_id TEXT REFERENCES players(player_id),
    session_id  TEXT REFERENCES sessions(session_id),
    action_type TEXT NOT NULL,                  -- e.g. 'force_reset', 'trigger_hint'
    payload_json TEXT DEFAULT '{}',
    confirmed   INTEGER NOT NULL DEFAULT 0,
    ts          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- CONFIG LAYER — Live-tunable without code deploy
-- ============================================================

CREATE TABLE IF NOT EXISTS config_store (
    config_key      TEXT PRIMARY KEY,
    config_value    TEXT NOT NULL,              -- JSON or scalar as text
    description     TEXT,
    version         TEXT,
    updated_by      TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- INDEXES — Performance
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_sessions_state       ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_room        ON sessions(room_id);
CREATE INDEX IF NOT EXISTS idx_session_players_sid  ON session_players(session_id);
CREATE INDEX IF NOT EXISTS idx_session_flags_sid    ON session_flags(session_id);
CREATE INDEX IF NOT EXISTS idx_node_states_sid      ON session_node_states(session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_session    ON telemetry_events(session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_type       ON telemetry_events(event_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts         ON telemetry_events(ts);
CREATE INDEX IF NOT EXISTS idx_operator_actions_sid ON operator_actions(session_id);
