"""
HEROES' VERITAS XR SYSTEMS — Seed Data
Phase 1A — Component 1: Database & Schema
Populates: nodes, levels, loot items, loot tables, achievements, config
"""

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "heroes_veritas.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn):
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    print("  [OK] Schema initialized")


# ── Node Definitions ──────────────────────────────────────────────────────────

NODE_DEFINITIONS = [
    {
        "node_id": "node_intro_narrative_01",
        "node_type": "narrative",
        "display_name": "The Awakening",
        "description": "Opening narrative — players receive their objective.",
        "sequence_order": 0,
        "config_json": json.dumps({"duration_secs": 120, "skippable": False}),
        "entry_conditions_json": json.dumps([]),
        "exit_conditions_json": json.dumps(["narrative_01_complete"]),
        "content_version": "1.0.0"
    },
    {
        "node_id": "node_puzzle_runes_01",
        "node_type": "puzzle",
        "display_name": "The Rune Sequence",
        "description": "Sequence/Pattern puzzle — restore the rune order.",
        "sequence_order": 1,
        "config_json": json.dumps({
            "puzzle_type": "sequence_pattern",
            "steps_required": 5,
            "hint_thresholds_secs": [180, 360, 540],
            "time_limit_secs": 600,
            "difficulty_overrides": {
                "easy":   {"steps_required": 3, "hint_thresholds_secs": [120, 240, 360]},
                "hard":   {"steps_required": 7, "hint_thresholds_secs": [240, 480, 720]}
            }
        }),
        "entry_conditions_json": json.dumps(["narrative_01_complete"]),
        "exit_conditions_json": json.dumps(["rune_puzzle_solved"]),
        "content_version": "1.0.0"
    },
    {
        "node_id": "node_combat_wave_01",
        "node_type": "combat",
        "display_name": "The First Trial",
        "description": "Wave arena — 3 waves, melee and ranged enemies.",
        "sequence_order": 2,
        "config_json": json.dumps({
            "combat_format": "wave_arena",
            "wave_count": 3,
            "enemy_archetypes": ["melee_chaser", "ranged_support"],
            "difficulty_overrides": {
                "easy": {"wave_count": 2, "enemy_count_per_wave": 2},
                "hard": {"wave_count": 4, "enemy_count_per_wave": 5}
            }
        }),
        "entry_conditions_json": json.dumps(["rune_puzzle_solved"]),
        "exit_conditions_json": json.dumps(["combat_01_cleared"]),
        "content_version": "1.0.0"
    },
    {
        "node_id": "node_puzzle_spatial_01",
        "node_type": "puzzle",
        "display_name": "The Altar Alignment",
        "description": "Spatial/Placement puzzle — align the beacon shards.",
        "sequence_order": 3,
        "config_json": json.dumps({
            "puzzle_type": "spatial_placement",
            "placements_required": 4,
            "hint_thresholds_secs": [180, 360, 540],
            "time_limit_secs": 720,
            "difficulty_overrides": {
                "easy": {"placements_required": 2},
                "hard": {"placements_required": 6}
            }
        }),
        "entry_conditions_json": json.dumps(["combat_01_cleared"]),
        "exit_conditions_json": json.dumps(["spatial_puzzle_solved"]),
        "content_version": "1.0.0"
    },
    {
        "node_id": "node_puzzle_search_01",
        "node_type": "puzzle",
        "display_name": "The Codex Cipher",
        "description": "Search/Interpret puzzle — decode the lore fragments.",
        "sequence_order": 4,
        "config_json": json.dumps({
            "puzzle_type": "search_interpret",
            "clues_required": 3,
            "hint_thresholds_secs": [180, 360, 540],
            "time_limit_secs": 600
        }),
        "entry_conditions_json": json.dumps(["spatial_puzzle_solved"]),
        "exit_conditions_json": json.dumps(["codex_puzzle_solved"]),
        "content_version": "1.0.0"
    },
    {
        "node_id": "node_combat_boss_01",
        "node_type": "combat",
        "display_name": "Keeper of the Emberlight",
        "description": "Boss encounter — scripted single fight, deterministic termination.",
        "sequence_order": 5,
        "config_json": json.dumps({
            "combat_format": "encounter_room",
            "encounter_count": 1,
            "is_boss": True,
            "termination_sequence": "deterministic",
            "difficulty_overrides": {
                "easy": {"boss_health_multiplier": 0.75},
                "hard": {"boss_health_multiplier": 1.5}
            }
        }),
        "entry_conditions_json": json.dumps(["codex_puzzle_solved"]),
        "exit_conditions_json": json.dumps(["boss_defeated"]),
        "content_version": "1.0.0"
    },
    {
        "node_id": "node_reward_finale_01",
        "node_type": "reward",
        "display_name": "Victory — The Emberlight Falls",
        "description": "Session complete — XP and loot granted, summary triggered.",
        "sequence_order": 6,
        "config_json": json.dumps({
            "triggers_session_complete": True,
            "summary_screen": True
        }),
        "entry_conditions_json": json.dumps(["boss_defeated"]),
        "exit_conditions_json": json.dumps(["session_complete"]),
        "content_version": "1.0.0"
    }
]

# ── Level Curve ───────────────────────────────────────────────────────────────

LEVEL_DEFINITIONS = [
    {"level": 1,  "xp_required": 0,    "reward_json": json.dumps({"title": "initiate"})},
    {"level": 2,  "xp_required": 100,  "reward_json": json.dumps({"title": "rune_bearer", "loot": "emblem_trial_01"})},
    {"level": 3,  "xp_required": 300,  "reward_json": json.dumps({"loot": "avatar_tint_ember"})},
    {"level": 4,  "xp_required": 600,  "reward_json": json.dumps({"title": "keeper_of_embers", "loot": "weapon_skin_ember_01"})},
    {"level": 5,  "xp_required": 1000, "reward_json": json.dumps({"loot": "companion_skin_fox_ember"})},
    {"level": 6,  "xp_required": 1500, "reward_json": json.dumps({"title": "slayer_of_the_first_trial", "loot": "lore_codex_01"})},
    {"level": 7,  "xp_required": 2100, "reward_json": json.dumps({"loot": "avatar_skin_veritas_01"})},
    {"level": 8,  "xp_required": 2800, "reward_json": json.dumps({"title": "guardian_of_veritas", "loot": "emblem_guardian"})},
    {"level": 9,  "xp_required": 3600, "reward_json": json.dumps({"loot": "weapon_skin_void_01"})},
    {"level": 10, "xp_required": 4500, "reward_json": json.dumps({"title": "master_of_the_emberlight", "loot": "companion_skin_fox_void"})},
]

# ── Loot Items ────────────────────────────────────────────────────────────────

LOOT_ITEMS = [
    {"item_id": "emblem_trial_01",        "display_name": "Mark of the First Trial",   "category": "emblem",        "rarity": "common", "description": "Awarded to those who endured the First Trial."},
    {"item_id": "emblem_guardian",        "display_name": "Guardian's Seal",           "category": "emblem",        "rarity": "rare",   "description": "A mark of protection and resolve."},
    {"item_id": "avatar_tint_ember",      "display_name": "Ember Tint",                "category": "avatar_skin",   "rarity": "common", "description": "A warm ember glow for your avatar."},
    {"item_id": "avatar_skin_veritas_01", "display_name": "Veritas Shroud",            "category": "avatar_skin",   "rarity": "rare",   "description": "The full Veritas ceremonial armor."},
    {"item_id": "weapon_skin_ember_01",   "display_name": "Emberlight Blade",          "category": "weapon_skin",   "rarity": "rare",   "description": "A weapon forged in the Emberlight."},
    {"item_id": "weapon_skin_void_01",    "display_name": "Void Cleaver",              "category": "weapon_skin",   "rarity": "epic",   "description": "Carved from the silence between worlds."},
    {"item_id": "companion_skin_fox_ember","display_name": "Fate Fox — Ember",         "category": "companion_skin","rarity": "rare",   "description": "The Fate Fox, warmed by ember light."},
    {"item_id": "companion_skin_fox_void", "display_name": "Fate Fox — Void",          "category": "companion_skin","rarity": "epic",   "description": "The Fate Fox, cloaked in void energy."},
    {"item_id": "lore_codex_01",          "display_name": "Codex Entry: The Awakening","category": "lore_unlock",   "rarity": "common", "description": "Unlocks the first lore chapter."},
    {"item_id": "lore_codex_02",          "display_name": "Codex Entry: The Keeper",  "category": "lore_unlock",   "rarity": "rare",   "description": "Unlocks the story of the Keeper."},
]

# ── Loot Tables ───────────────────────────────────────────────────────────────

LOOT_TABLES = [
    # Completion rewards (all difficulties)
    {"table_id": "completion_any",      "item_id": "emblem_trial_01",        "weight": 100, "difficulty": None, "is_guaranteed": 1},
    {"table_id": "completion_any",      "item_id": "lore_codex_01",          "weight": 80,  "difficulty": None, "is_guaranteed": 0},
    {"table_id": "completion_any",      "item_id": "avatar_tint_ember",      "weight": 60,  "difficulty": None, "is_guaranteed": 0},
    # Normal+ rewards
    {"table_id": "completion_normal",   "item_id": "weapon_skin_ember_01",   "weight": 40,  "difficulty": "normal", "is_guaranteed": 0},
    {"table_id": "completion_normal",   "item_id": "companion_skin_fox_ember","weight": 30, "difficulty": "normal", "is_guaranteed": 0},
    {"table_id": "completion_normal",   "item_id": "lore_codex_02",          "weight": 25,  "difficulty": "normal", "is_guaranteed": 0},
    # Hard-only rewards
    {"table_id": "completion_hard",     "item_id": "avatar_skin_veritas_01", "weight": 50,  "difficulty": "hard", "is_guaranteed": 0},
    {"table_id": "completion_hard",     "item_id": "weapon_skin_void_01",    "weight": 30,  "difficulty": "hard", "is_guaranteed": 0},
    {"table_id": "completion_hard",     "item_id": "companion_skin_fox_void","weight": 20,  "difficulty": "hard", "is_guaranteed": 0},
    {"table_id": "completion_hard",     "item_id": "emblem_guardian",        "weight": 15,  "difficulty": "hard", "is_guaranteed": 0},
]

# ── Achievements ──────────────────────────────────────────────────────────────

ACHIEVEMENTS = [
    {"achievement_key": "first_completion",    "display_name": "The First Step",          "description": "Complete your first session.",                       "reward_title": "initiate",                "reward_item_id": "emblem_trial_01"},
    {"achievement_key": "perfect_puzzle_run",  "display_name": "Mind Unbroken",           "description": "Complete all puzzles with no hints used.",           "reward_title": "rune_bearer",             "reward_item_id": None},
    {"achievement_key": "no_down_combat",      "display_name": "Undefeated",              "description": "Complete all combat without any player going down.", "reward_title": "slayer_of_the_first_trial","reward_item_id": "emblem_guardian"},
    {"achievement_key": "beat_on_hard",        "display_name": "Keeper of the Emberlight","description": "Complete the session on Hard difficulty.",            "reward_title": "keeper_of_embers",        "reward_item_id": "avatar_skin_veritas_01"},
    {"achievement_key": "speed_run",           "display_name": "Faster Than Fate",        "description": "Complete the session in under 45 minutes.",          "reward_title": "guardian_of_veritas",     "reward_item_id": None},
    {"achievement_key": "full_codex",          "display_name": "Seeker of Truth",         "description": "Unlock all lore codex entries.",                     "reward_title": "master_of_the_emberlight","reward_item_id": "lore_codex_02"},
]

# ── Config Store ──────────────────────────────────────────────────────────────

CONFIG_STORE = [
    # XP Tuning
    {"config_key": "xp.base_node_puzzle",       "config_value": "150",        "description": "Base XP for completing a puzzle node"},
    {"config_key": "xp.base_node_combat",       "config_value": "200",        "description": "Base XP for completing a combat node"},
    {"config_key": "xp.time_bonus_per_min",     "config_value": "10",         "description": "XP per minute remaining at session end"},
    {"config_key": "xp.difficulty_multiplier",  "config_value": '{"easy":0.75,"normal":1.0,"hard":1.5}', "description": "XP multiplier by difficulty"},
    {"config_key": "xp.daily_cap",              "config_value": "2000",       "description": "Max XP earnable per player per day"},
    {"config_key": "xp.repeat_decay_factor",    "config_value": "0.5",        "description": "XP multiplier on repeat plays within 1 hour"},
    # Session Tuning
    {"config_key": "session.duration_secs",     "config_value": "3600",       "description": "Default session length in seconds"},
    {"config_key": "session.max_players",       "config_value": "6",          "description": "Maximum players per session"},
    {"config_key": "session.min_players",       "config_value": "2",          "description": "Minimum players to start session"},
    {"config_key": "session.reset_sla_secs",    "config_value": "60",         "description": "Max seconds for a full session reset"},
    # Hint Tuning
    {"config_key": "hints.auto_trigger_secs",   "config_value": '[180,360,540]',"description": "Seconds stuck before auto-hint tiers"},
    {"config_key": "hints.player_request_enabled","config_value": "true",     "description": "Allow players to request hints manually"},
    # Economy Events (Phase 1B/2 hooks)
    {"config_key": "economy.xp_event_multiplier","config_value": "1.0",       "description": "Live event XP multiplier (1.0 = normal)"},
    {"config_key": "economy.reward_boost_active","config_value": "false",     "description": "Whether a reward boost event is active"},
    # Versions
    {"config_key": "version.gameplay",          "config_value": "1.0.0",      "description": "Current gameplay build version"},
    {"config_key": "version.content",           "config_value": "1.0.0",      "description": "Current content version"},
    {"config_key": "version.config",            "config_value": "1.0.0",      "description": "Current config version"},
    {"config_key": "version.economy",           "config_value": "1.0.0",      "description": "Current economy version"},
]


# ── Seeder ────────────────────────────────────────────────────────────────────

def seed_table(conn, table, rows, pk_field, label):
    inserted = 0
    skipped = 0
    for row in rows:
        try:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(["?" for _ in row])
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
                list(row.values())
            )
            inserted += conn.execute(
                f"SELECT changes()"
            ).fetchone()[0]
        except Exception as e:
            print(f"  [WARN] {label} row skipped: {e}")
            skipped += 1
    print(f"  [OK] {label}: {inserted} inserted, {skipped} skipped")


def run_seed():
    print("\n=== HEROES VERITAS — DB SEED ===\n")
    conn = get_db()

    print("[1/3] Initializing schema...")
    init_schema(conn)

    print("\n[2/3] Seeding reference data...")
    seed_table(conn, "node_definitions", NODE_DEFINITIONS, "node_id", "Nodes")
    seed_table(conn, "level_definitions", LEVEL_DEFINITIONS, "level", "Levels")
    seed_table(conn, "loot_items", LOOT_ITEMS, "item_id", "Loot Items")
    seed_table(conn, "loot_tables", LOOT_TABLES, "id", "Loot Tables")
    seed_table(conn, "achievements", ACHIEVEMENTS, "achievement_key", "Achievements")
    seed_table(conn, "config_store", CONFIG_STORE, "config_key", "Config")

    conn.commit()

    print("\n[3/3] Verifying counts...")
    tables = [
        "node_definitions", "level_definitions", "loot_items",
        "loot_tables", "achievements", "config_store"
    ]
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:30s} → {count} rows")

    conn.close()
    print("\n=== SEED COMPLETE ===\n")


if __name__ == "__main__":
    run_seed()
