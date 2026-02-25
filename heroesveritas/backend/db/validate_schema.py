"""
HEROES' VERITAS XR SYSTEMS — DB Validation Suite
Phase 1A — Component 1: Database & Schema
Tests: schema integrity, FK constraints, config completeness, node graph
"""

import sqlite3
import json
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "heroes_veritas.db")

PASS = "  [PASS]"
FAIL = "  [FAIL]"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{status} {label}{suffix}")
    return condition


def run_validation():
    print("\n=== HEROES VERITAS — DB VALIDATION ===\n")
    conn = get_db()
    results = []

    # ── Table Existence ───────────────────────────────────────────────────────
    print("[1] Table existence checks")
    required_tables = [
        "players", "player_profiles", "player_titles", "player_loot",
        "player_achievements", "sessions", "session_players", "session_flags",
        "node_definitions", "session_node_states", "level_definitions",
        "loot_items", "loot_tables", "achievements", "telemetry_events",
        "operator_actions", "config_store"
    ]
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for t in required_tables:
        results.append(check(f"Table: {t}", t in existing))

    # ── Row Count Minimums ────────────────────────────────────────────────────
    print("\n[2] Minimum row count checks")
    minimums = {
        "node_definitions": 5,
        "level_definitions": 10,
        "loot_items": 10,
        "loot_tables": 10,
        "achievements": 5,
        "config_store": 10,
    }
    for table, minimum in minimums.items():
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        results.append(check(
            f"{table} has >= {minimum} rows",
            count >= minimum,
            f"found {count}"
        ))

    # ── Node Graph Integrity ──────────────────────────────────────────────────
    print("\n[3] Node graph integrity checks")
    nodes = conn.execute(
        "SELECT node_id, node_type, sequence_order, entry_conditions_json, exit_conditions_json "
        "FROM node_definitions ORDER BY sequence_order"
    ).fetchall()

    results.append(check("Node count >= 5", len(nodes) >= 5, f"found {len(nodes)}"))

    node_types_present = {n["node_type"] for n in nodes}
    for required_type in ["puzzle", "combat", "narrative", "reward"]:
        results.append(check(
            f"Node type present: {required_type}",
            required_type in node_types_present
        ))

    # Validate all exit flags are used as entry conditions somewhere
    all_exit_flags = set()
    all_entry_flags = set()
    for n in nodes:
        exits = json.loads(n["exit_conditions_json"] or "[]")
        entries = json.loads(n["entry_conditions_json"] or "[]")
        all_exit_flags.update(exits)
        all_entry_flags.update(entries)

    # Every entry flag should be an exit of a prior node (except first node)
    orphaned = all_entry_flags - all_exit_flags
    results.append(check(
        "No orphaned entry conditions",
        len(orphaned) == 0,
        f"orphaned: {orphaned}" if orphaned else "graph connected"
    ))

    # ── Level Curve Integrity ─────────────────────────────────────────────────
    print("\n[4] Level curve integrity checks")
    levels = conn.execute(
        "SELECT level, xp_required FROM level_definitions ORDER BY level"
    ).fetchall()

    results.append(check("Level 1 starts at 0 XP", levels[0]["xp_required"] == 0))

    is_ascending = all(
        levels[i]["xp_required"] < levels[i+1]["xp_required"]
        for i in range(len(levels) - 1)
    )
    results.append(check("Level XP curve is ascending", is_ascending))

    # ── Loot Table Integrity ──────────────────────────────────────────────────
    print("\n[5] Loot table integrity checks")
    guaranteed = conn.execute(
        "SELECT COUNT(*) FROM loot_tables WHERE is_guaranteed=1"
    ).fetchone()[0]
    results.append(check("At least 1 guaranteed loot entry", guaranteed >= 1))

    # All item_ids in loot_tables reference real loot_items
    orphan_loot = conn.execute("""
        SELECT lt.item_id FROM loot_tables lt
        LEFT JOIN loot_items li ON lt.item_id = li.item_id
        WHERE li.item_id IS NULL
    """).fetchall()
    results.append(check(
        "No orphaned loot_table item references",
        len(orphan_loot) == 0,
        f"orphaned: {[r[0] for r in orphan_loot]}" if orphan_loot else "all valid"
    ))

    rarity_counts = {}
    for row in conn.execute("SELECT rarity, COUNT(*) as c FROM loot_items GROUP BY rarity"):
        rarity_counts[row["rarity"]] = row["c"]
    for rarity in ["common", "rare", "epic"]:
        results.append(check(
            f"Loot rarity present: {rarity}",
            rarity_counts.get(rarity, 0) > 0
        ))

    # ── Config Completeness ───────────────────────────────────────────────────
    print("\n[6] Config store checks")
    required_configs = [
        "xp.base_node_puzzle",
        "xp.base_node_combat",
        "xp.difficulty_multiplier",
        "session.duration_secs",
        "session.max_players",
        "session.reset_sla_secs",
        "hints.auto_trigger_secs",
        "version.gameplay",
        "version.content",
        "version.config",
        "version.economy",
        "economy.xp_event_multiplier",
    ]
    existing_configs = {
        r["config_key"] for r in conn.execute("SELECT config_key FROM config_store")
    }
    for key in required_configs:
        results.append(check(f"Config key: {key}", key in existing_configs))

    # ── Achievement Integrity ─────────────────────────────────────────────────
    print("\n[7] Achievement checks")
    achievements = conn.execute("SELECT * FROM achievements").fetchall()
    results.append(check("At least 5 achievements", len(achievements) >= 5, f"found {len(achievements)}"))

    for a in achievements:
        if a["reward_item_id"]:
            item_exists = conn.execute(
                "SELECT 1 FROM loot_items WHERE item_id=?", (a["reward_item_id"],)
            ).fetchone()
            results.append(check(
                f"Achievement reward item valid: {a['achievement_key']}",
                item_exists is not None
            ))

    # ── FK Pragma Check ───────────────────────────────────────────────────────
    print("\n[8] Foreign key integrity")
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    results.append(check(
        "No FK violations in seed data",
        len(fk_violations) == 0,
        f"{len(fk_violations)} violations found" if fk_violations else "clean"
    ))

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)
    total = len(results)

    print(f"\n{'='*45}")
    print(f"  RESULTS: {passed}/{total} passed  |  {failed} failed")
    print(f"{'='*45}\n")

    conn.close()

    if failed > 0:
        print("  ACTION REQUIRED: Fix failures before proceeding to Component 2.\n")
        sys.exit(1)
    else:
        print("  Component 1 — Database & Schema: VALIDATED ✓\n")
        print("  Ready to proceed to Component 2 — Session Orchestration Engine.\n")
        sys.exit(0)


if __name__ == "__main__":
    run_validation()
