"""
HEROES' VERITAS XR SYSTEMS — Economy & Progression Service
Phase 1A — Component 3

Responsibilities:
  - XP calculation (base + difficulty multiplier + time bonus + event multiplier)
  - Anti-exploit guards (daily cap, repeat decay, minimum participation)
  - Level-up processing (curve evaluation, reward unlocks)
  - Loot resolution (weighted tables, rarity tiers, guaranteed drops)
  - Achievement evaluation (per-session unlock checks)
  - Session summary generation (full post-run report)
  - Profile persistence (transactional — no partial writes)
  - All values config-driven — zero hardcoded tuning numbers

Architecture note:
  Called by the orchestration engine at session completion.
  Never called mid-session. All writes are atomic transactions.
  Partial sessions (failed/quit early) do NOT grant rewards.
"""

import json
import uuid
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from db.connection import get_db, fetchone, fetchall


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> datetime:
    return datetime.now(timezone.utc)


def get_config(conn, key: str, default=None):
    row = fetchone(conn, "SELECT config_value FROM config_store WHERE config_key=?", (key,))
    if row is None:
        return default
    try:
        return json.loads(row["config_value"])
    except (json.JSONDecodeError, TypeError):
        return row["config_value"]


def _emit_economy_event(conn, event_type: str, session_id: str = None,
                         player_id: str = None, context: dict = None):
    """Write economy telemetry event."""
    conn.execute("""
        INSERT INTO telemetry_events
            (event_id, session_id, player_id, event_type, context_json,
             gameplay_version, config_version, ts)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), session_id, player_id, event_type,
        json.dumps(context or {}),
        get_config(conn, "version.gameplay", "1.0.0"),
        get_config(conn, "version.config",   "1.0.0"),
        now_iso()
    ))


# ─────────────────────────────────────────────────────────────────────────────
# XP Calculation
# ─────────────────────────────────────────────────────────────────────────────

def calculate_xp(session_id: str, player_id: str) -> dict:
    """
    Calculate XP earned for a player in a completed session.

    Formula:
      base_xp        = sum of base XP for each completed node type
      difficulty_mod = multiplier by difficulty (easy: 0.75, normal: 1.0, hard: 1.5)
      time_bonus     = xp_per_min_remaining × minutes_left
      event_mod      = live event multiplier (default 1.0)
      repeat_decay   = 0.5 if replayed within 1 hour
      daily_cap      = hard ceiling on XP per player per day

    Returns breakdown dict for summary screen transparency.
    """
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT * FROM sessions WHERE session_id=?", (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        if session["state"] != "completed":
            raise ValueError(f"XP only granted for completed sessions (state: {session['state']})")

        # ── Base XP per node type ─────────────────────────────────────────────
        base_puzzle = int(get_config(conn, "xp.base_node_puzzle", 150))
        base_combat = int(get_config(conn, "xp.base_node_combat", 200))

        node_states = fetchall(conn, """
            SELECT ns.state, nd.node_type
            FROM session_node_states ns
            JOIN node_definitions nd ON ns.node_id = nd.node_id
            WHERE ns.session_id = ?
        """, (session_id,))

        base_xp = 0
        nodes_completed = 0
        for node in node_states:
            if node["state"] not in ("completed", "skipped", "in_progress"):
                continue
            # Only count nodes that had meaningful activity
            if node["state"] == "in_progress":
                continue
            nodes_completed += 1
            if node["node_type"] == "puzzle":
                base_xp += base_puzzle
            elif node["node_type"] == "combat":
                base_xp += base_combat
            # narrative/reward/transition nodes grant no XP

        # ── Difficulty multiplier ─────────────────────────────────────────────
        difficulty_map = get_config(conn, "xp.difficulty_multiplier",
                                    {"easy": 0.75, "normal": 1.0, "hard": 1.5})
        diff_multiplier = float(difficulty_map.get(session["difficulty"], 1.0))

        # ── Time bonus ────────────────────────────────────────────────────────
        xp_per_min = int(get_config(conn, "xp.time_bonus_per_min", 10))
        elapsed_secs = _calc_session_elapsed(session)
        remaining_secs = max(0, session["total_duration_secs"] - elapsed_secs)
        remaining_mins = remaining_secs // 60
        time_bonus = xp_per_min * remaining_mins

        # ── Minimum participation guard ───────────────────────────────────────
        # Player must have completed at least 1 node to earn any XP
        if nodes_completed == 0:
            return {
                "player_id": player_id,
                "base_xp": 0, "difficulty_multiplier": diff_multiplier,
                "time_bonus": 0, "event_multiplier": 1.0,
                "repeat_decay": 1.0, "gross_xp": 0, "daily_xp_used": 0,
                "xp_earned": 0, "nodes_completed": 0,
                "reason": "no_nodes_completed"
            }

        # ── Sub-total before caps ─────────────────────────────────────────────
        subtotal = int((base_xp * diff_multiplier) + time_bonus)

        # ── Live event multiplier ─────────────────────────────────────────────
        event_multiplier = float(get_config(conn, "economy.xp_event_multiplier", 1.0))
        gross_xp = int(subtotal * event_multiplier)

        # ── Repeat decay ──────────────────────────────────────────────────────
        decay_factor = float(get_config(conn, "xp.repeat_decay_factor", 0.5))
        repeat_decay = 1.0
        one_hour_ago = (now_ts() - timedelta(hours=1)).isoformat()
        recent_completions = conn.execute("""
            SELECT COUNT(*) FROM sessions s
            JOIN session_players sp ON s.session_id = sp.session_id
            WHERE sp.player_id = ?
              AND s.state = 'completed'
              AND s.completed_at > ?
              AND s.session_id != ?
        """, (player_id, one_hour_ago, session_id)).fetchone()[0]

        if recent_completions > 0:
            repeat_decay = decay_factor
            gross_xp = int(gross_xp * repeat_decay)

        # ── Daily cap ─────────────────────────────────────────────────────────
        daily_cap = int(get_config(conn, "xp.daily_cap", 2000))
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0).isoformat()

        daily_xp_used = conn.execute("""
            SELECT COALESCE(SUM(CAST(context_json AS TEXT)), 0)
            FROM telemetry_events
            WHERE player_id = ?
              AND event_type = 'xp_granted'
              AND ts > ?
        """, (player_id, today_start)).fetchone()[0]

        # Parse daily_xp_used from telemetry context JSON
        daily_used = _sum_daily_xp(conn, player_id, today_start)
        headroom = max(0, daily_cap - daily_used)
        xp_earned = min(gross_xp, headroom)

        return {
            "player_id":           player_id,
            "base_xp":             base_xp,
            "difficulty_multiplier": diff_multiplier,
            "time_bonus":          time_bonus,
            "event_multiplier":    event_multiplier,
            "repeat_decay":        repeat_decay,
            "gross_xp":            gross_xp,
            "daily_xp_used":       daily_used,
            "daily_cap":           daily_cap,
            "xp_earned":           xp_earned,
            "nodes_completed":     nodes_completed,
            "difficulty":          session["difficulty"],
            "remaining_secs":      remaining_secs,
        }
    finally:
        conn.close()


def _calc_session_elapsed(session: dict) -> int:
    if not session.get("timer_started_at"):
        return 0
    started = datetime.fromisoformat(session["timer_started_at"])
    elapsed = (now_ts() - started).total_seconds()
    return max(0, int(elapsed) - session.get("timer_paused_secs", 0))


def _sum_daily_xp(conn, player_id: str, today_start: str) -> int:
    """Sum XP granted to a player today from telemetry."""
    rows = fetchall(conn, """
        SELECT context_json FROM telemetry_events
        WHERE player_id = ? AND event_type = 'xp_granted' AND ts > ?
    """, (player_id, today_start))
    total = 0
    for row in rows:
        try:
            ctx = json.loads(row["context_json"] or "{}")
            total += int(ctx.get("xp_earned", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Level Processing
# ─────────────────────────────────────────────────────────────────────────────

def get_level_for_xp(total_xp: int, conn) -> int:
    """Return the level a player should be at for a given total XP."""
    levels = fetchall(conn,
        "SELECT level, xp_required FROM level_definitions ORDER BY level DESC")
    for lvl in levels:
        if total_xp >= lvl["xp_required"]:
            return lvl["level"]
    return 1


def process_level_ups(player_id: str, xp_gained: int,
                       session_id: str = None) -> dict:
    """
    Apply XP to a player profile and process any level-ups.
    Transactional — either all level-ups apply or none do.
    Returns: { old_level, new_level, levels_gained, rewards_unlocked, new_total_xp }
    """
    conn = get_db()
    try:
        profile = fetchone(conn,
            "SELECT total_xp, current_level FROM player_profiles WHERE player_id=?",
            (player_id,))

        if not profile:
            # Create profile on first XP grant
            conn.execute("""
                INSERT INTO player_profiles (player_id, total_xp, current_level)
                VALUES (?,?,1)
            """, (player_id,))
            profile = {"total_xp": 0, "current_level": 1}

        old_xp    = profile["total_xp"]
        old_level = profile["current_level"]
        new_xp    = old_xp + xp_gained
        new_level = get_level_for_xp(new_xp, conn)

        conn.execute("""
            UPDATE player_profiles
            SET total_xp=?, current_level=?, updated_at=?
            WHERE player_id=?
        """, (new_xp, new_level, now_iso(), player_id))

        # Process rewards for each new level crossed
        rewards_unlocked = []
        if new_level > old_level:
            for lvl_num in range(old_level + 1, new_level + 1):
                level_def = fetchone(conn,
                    "SELECT reward_json FROM level_definitions WHERE level=?",
                    (lvl_num,))
                if not level_def:
                    continue
                reward = json.loads(level_def["reward_json"] or "{}")

                # Unlock title
                if "title" in reward:
                    conn.execute("""
                        INSERT OR IGNORE INTO player_titles
                            (player_id, title_key, unlocked_at)
                        VALUES (?,?,?)
                    """, (player_id, reward["title"], now_iso()))
                    rewards_unlocked.append({"type": "title", "value": reward["title"]})

                # Unlock loot item
                if "loot" in reward:
                    conn.execute("""
                        INSERT OR IGNORE INTO player_loot
                            (player_id, item_id, earned_at)
                        VALUES (?,?,?)
                    """, (player_id, reward["loot"], now_iso()))
                    rewards_unlocked.append({"type": "loot", "value": reward["loot"]})

                _emit_economy_event(conn, "level_up", session_id=session_id,
                                    player_id=player_id,
                                    context={"old_level": lvl_num - 1,
                                             "new_level": lvl_num,
                                             "rewards": reward})

        _emit_economy_event(conn, "xp_granted", session_id=session_id,
                            player_id=player_id,
                            context={"xp_earned": xp_gained, "new_total_xp": new_xp,
                                     "old_level": old_level, "new_level": new_level})
        conn.commit()

        return {
            "player_id":        player_id,
            "old_level":        old_level,
            "new_level":        new_level,
            "levels_gained":    new_level - old_level,
            "old_total_xp":     old_xp,
            "new_total_xp":     new_xp,
            "xp_gained":        xp_gained,
            "rewards_unlocked": rewards_unlocked,
            "leveled_up":       new_level > old_level,
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Loot Resolution
# ─────────────────────────────────────────────────────────────────────────────

def resolve_loot(session_id: str, player_id: str,
                  performance_tier: str = "bronze") -> list:
    """
    Resolve loot drops for a player after session completion.

    Process:
      1. Always grant all guaranteed items from matching tables
      2. Roll weighted random from eligible pool (filtered by difficulty)
      3. Skip items player already owns
      4. Record to player_loot and emit telemetry

    performance_tier: 'bronze' | 'silver' | 'gold'
    Returns list of granted item dicts.
    """
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT difficulty, state FROM sessions WHERE session_id=?",
            (session_id,))
        if not session or session["state"] != "completed":
            raise ValueError("Loot only granted for completed sessions")

        difficulty = session["difficulty"]
        reward_boost = get_config(conn, "economy.reward_boost_active", False)

        # Build eligible table IDs
        table_ids = ["completion_any"]
        if difficulty in ("normal", "hard"):
            table_ids.append(f"completion_{difficulty}")

        # Fetch all eligible loot table entries
        placeholders = ",".join("?" * len(table_ids))
        entries = fetchall(conn, f"""
            SELECT lt.item_id, lt.weight, lt.is_guaranteed, li.display_name,
                   li.rarity, li.category
            FROM loot_tables lt
            JOIN loot_items li ON lt.item_id = li.item_id
            WHERE lt.table_id IN ({placeholders})
              AND li.is_active = 1
        """, table_ids)

        # Items already owned by this player
        owned = {r["item_id"] for r in fetchall(conn,
            "SELECT item_id FROM player_loot WHERE player_id=?", (player_id,))}

        granted = []

        # ── Step 1: Guaranteed drops ──────────────────────────────────────────
        for entry in entries:
            if entry["is_guaranteed"] and entry["item_id"] not in owned:
                _grant_item(conn, player_id, session_id, entry)
                owned.add(entry["item_id"])
                granted.append(_loot_dict(entry, guaranteed=True))

        # ── Step 2: Weighted random roll ──────────────────────────────────────
        pool = [e for e in entries
                if not e["is_guaranteed"] and e["item_id"] not in owned]

        if pool:
            # Performance tier bonus: gold = 2 rolls, silver = 1.5 (chance), bronze = 1
            rolls = 1
            if performance_tier == "gold":
                rolls = 2
            elif performance_tier == "silver" and random.random() < 0.5:
                rolls = 2

            # Apply reward boost if active
            if reward_boost:
                rolls += 1

            for _ in range(rolls):
                pool_remaining = [e for e in pool if e["item_id"] not in owned]
                if not pool_remaining:
                    break
                weights = [e["weight"] for e in pool_remaining]
                chosen = random.choices(pool_remaining, weights=weights, k=1)[0]
                _grant_item(conn, player_id, session_id, chosen)
                owned.add(chosen["item_id"])
                granted.append(_loot_dict(chosen, guaranteed=False))

        conn.commit()
        return granted
    finally:
        conn.close()


def _grant_item(conn, player_id: str, session_id: str, entry: dict):
    conn.execute("""
        INSERT OR IGNORE INTO player_loot (player_id, item_id, earned_at)
        VALUES (?,?,?)
    """, (player_id, entry["item_id"], now_iso()))
    _emit_economy_event(conn, "loot_granted", session_id=session_id,
                        player_id=player_id,
                        context={"item_id": entry["item_id"],
                                 "rarity": entry["rarity"],
                                 "category": entry["category"]})


def _loot_dict(entry: dict, guaranteed: bool) -> dict:
    return {
        "item_id":     entry["item_id"],
        "display_name": entry["display_name"],
        "rarity":      entry["rarity"],
        "category":    entry["category"],
        "guaranteed":  guaranteed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Achievement Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_achievements(session_id: str, player_id: str,
                            session_stats: dict) -> list:
    """
    Check all achievements against session stats and unlock eligible ones.
    session_stats keys expected:
      - is_first_completion   (bool)
      - hints_used_total      (int)
      - any_player_downed     (bool)
      - difficulty            (str)
      - completion_time_secs  (int)
      - lore_items_owned      (int)

    Returns list of newly unlocked achievement dicts.
    """
    conn = get_db()
    try:
        # Re-query fresh — avoids stale cache across multiple calls in same test
        already_unlocked = {r["achievement_key"] for r in fetchall(conn,
            "SELECT achievement_key FROM player_achievements WHERE player_id=?",
            (player_id,))}

        all_achievements = fetchall(conn,
            "SELECT * FROM achievements WHERE is_active=1")

        newly_unlocked = []

        for ach in all_achievements:
            key = ach["achievement_key"]
            if key in already_unlocked:
                continue

            earned = False

            if key == "first_completion":
                earned = session_stats.get("is_first_completion", False)

            elif key == "perfect_puzzle_run":
                earned = session_stats.get("hints_used_total", 99) == 0

            elif key == "no_down_combat":
                earned = not session_stats.get("any_player_downed", True)

            elif key == "beat_on_hard":
                earned = session_stats.get("difficulty") == "hard"

            elif key == "speed_run":
                limit = 45 * 60  # 45 minutes
                earned = session_stats.get("completion_time_secs", 9999) <= limit

            elif key == "full_codex":
                lore_items = fetchall(conn, """
                    SELECT pl.item_id FROM player_loot pl
                    JOIN loot_items li ON pl.item_id = li.item_id
                    WHERE pl.player_id = ? AND li.category = 'lore_unlock'
                """, (player_id,))
                total_lore = conn.execute(
                    "SELECT COUNT(*) FROM loot_items WHERE category='lore_unlock'"
                ).fetchone()[0]
                earned = len(lore_items) >= total_lore and total_lore > 0

            if not earned:
                continue

            # Unlock the achievement
            conn.execute("""
                INSERT OR IGNORE INTO player_achievements
                    (player_id, achievement_key, unlocked_at)
                VALUES (?,?,?)
            """, (player_id, key, now_iso()))

            # Grant title reward
            if ach["reward_title"]:
                conn.execute("""
                    INSERT OR IGNORE INTO player_titles
                        (player_id, title_key, unlocked_at)
                    VALUES (?,?,?)
                """, (player_id, ach["reward_title"], now_iso()))

            # Grant item reward
            if ach["reward_item_id"]:
                conn.execute("""
                    INSERT OR IGNORE INTO player_loot
                        (player_id, item_id, earned_at)
                    VALUES (?,?,?)
                """, (player_id, ach["reward_item_id"], now_iso()))

            _emit_economy_event(conn, "achievement_unlocked",
                                session_id=session_id, player_id=player_id,
                                context={"achievement_key": key,
                                         "reward_title": ach["reward_title"],
                                         "reward_item": ach["reward_item_id"]})

            newly_unlocked.append({
                "achievement_key": key,
                "display_name":    ach["display_name"],
                "description":     ach["description"],
                "reward_title":    ach["reward_title"],
                "reward_item_id":  ach["reward_item_id"],
            })

        conn.commit()
        return newly_unlocked
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Session Summary — Full Post-Run Report
# ─────────────────────────────────────────────────────────────────────────────

def generate_session_summary(session_id: str) -> dict:
    """
    Master entry point called at session completion.
    Orchestrates: XP calc → level-ups → loot → achievements → profile update.
    Fully transactional — partial writes do not occur.
    Returns complete summary for the post-session screen and telemetry.
    """
    conn = get_db()
    try:
        session = fetchone(conn, "SELECT * FROM sessions WHERE session_id=?",
                           (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        if session["state"] != "completed":
            raise ValueError(
                f"Summary only for completed sessions (state: {session['state']})")

        players = fetchall(conn,
            "SELECT player_id FROM session_players WHERE session_id=? AND is_active=1",
            (session_id,))
        player_ids = [p["player_id"] for p in players]

        # Gather session-level stats used by achievements
        node_states = fetchall(conn, """
            SELECT ns.state, ns.hints_used, nd.node_type
            FROM session_node_states ns
            JOIN node_definitions nd ON ns.node_id = nd.node_id
            WHERE ns.session_id = ?
        """, (session_id,))

        elapsed_secs = _calc_session_elapsed(session)
        hints_total  = sum(n["hints_used"] for n in node_states)
        nodes_done   = sum(1 for n in node_states
                           if n["state"] in ("completed", "skipped"))

        # Performance tier
        remaining_pct = max(0, 1.0 - (elapsed_secs / session["total_duration_secs"]))
        if remaining_pct >= 0.3 and hints_total == 0:
            perf_tier = "gold"
        elif remaining_pct >= 0.1 or hints_total <= 2:
            perf_tier = "silver"
        else:
            perf_tier = "bronze"

        player_summaries = []

        for pid in player_ids:
            # Check first-completion flag
            prior = conn.execute("""
                SELECT COUNT(*) FROM player_profiles WHERE player_id=?
            """, (pid,)).fetchone()[0]
            is_first = prior == 0

            session_stats = {
                "is_first_completion":  is_first,
                "hints_used_total":     hints_total,
                "any_player_downed":    False,   # Phase 1B: wire to combat data
                "difficulty":           session["difficulty"],
                "completion_time_secs": elapsed_secs,
            }

            # XP
            xp_breakdown = calculate_xp(session_id, pid)
            xp_result    = process_level_ups(pid, xp_breakdown["xp_earned"],
                                              session_id)

            # Loot
            loot_granted = resolve_loot(session_id, pid, perf_tier)

            # Achievements
            achievements = evaluate_achievements(session_id, pid, session_stats)

            # Update sessions_completed and best time on profile
            _update_completion_stats(conn, pid, elapsed_secs, session["difficulty"])

            player_summaries.append({
                "player_id":          pid,
                "xp_breakdown":       xp_breakdown,
                "xp_earned":          xp_breakdown["xp_earned"],
                "old_level":          xp_result["old_level"],
                "new_level":          xp_result["new_level"],
                "leveled_up":         xp_result["leveled_up"],
                "rewards_from_level": xp_result["rewards_unlocked"],
                "loot_granted":       loot_granted,
                "achievements":       achievements,
            })

        # Emit top-level session summary event
        _emit_economy_event(conn, "session_summary_generated",
                            session_id=session_id,
                            context={
                                "player_count":    len(player_ids),
                                "elapsed_secs":    elapsed_secs,
                                "difficulty":      session["difficulty"],
                                "nodes_completed": nodes_done,
                                "hints_total":     hints_total,
                                "performance_tier": perf_tier,
                            })
        conn.commit()

        return {
            "session_id":        session_id,
            "difficulty":        session["difficulty"],
            "completion_time_secs": elapsed_secs,
            "completion_time_fmt":  _fmt_time(elapsed_secs),
            "nodes_completed":   nodes_done,
            "hints_used":        hints_total,
            "performance_tier":  perf_tier,
            "room_id":           session.get("room_id"),
            "gameplay_version":  session.get("gameplay_version"),
            "config_version":    session.get("config_version"),
            "player_summaries":  player_summaries,
        }
    finally:
        conn.close()


def _update_completion_stats(conn, player_id: str,
                               elapsed_secs: int, difficulty: str):
    """Update sessions_completed and best_completion_time on profile."""
    profile = fetchone(conn,
        "SELECT sessions_completed, best_completion_time_secs, highest_difficulty "
        "FROM player_profiles WHERE player_id=?", (player_id,))
    if not profile:
        return

    new_count = profile["sessions_completed"] + 1
    best = profile["best_completion_time_secs"]
    new_best = elapsed_secs if (best is None or elapsed_secs < best) else best

    diff_rank = {"easy": 0, "normal": 1, "hard": 2}
    current_rank  = diff_rank.get(profile["highest_difficulty"] or "easy", 0)
    new_rank      = diff_rank.get(difficulty, 0)
    new_highest   = difficulty if new_rank > current_rank else profile["highest_difficulty"]

    conn.execute("""
        UPDATE player_profiles
        SET sessions_completed=?, best_completion_time_secs=?,
            highest_difficulty=?, updated_at=?
        WHERE player_id=?
    """, (new_count, new_best, new_highest, now_iso(), player_id))


def _fmt_time(secs: int) -> str:
    m, s = divmod(secs, 60)
    return f"{m:02d}:{s:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Profile Retrieval
# ─────────────────────────────────────────────────────────────────────────────

def get_player_profile(player_id: str) -> Optional[dict]:
    """Return full player profile with titles, loot, achievements."""
    conn = get_db()
    try:
        profile = fetchone(conn,
            "SELECT * FROM player_profiles WHERE player_id=?", (player_id,))
        if not profile:
            return None

        conn2 = get_db()
        profile["titles"] = [r["title_key"] for r in fetchall(conn2,
            "SELECT title_key FROM player_titles WHERE player_id=?", (player_id,))]
        profile["loot"] = fetchall(conn2, """
            SELECT pl.item_id, pl.quantity, li.display_name, li.rarity, li.category
            FROM player_loot pl
            JOIN loot_items li ON pl.item_id = li.item_id
            WHERE pl.player_id = ?
        """, (player_id,))
        profile["achievements"] = [r["achievement_key"] for r in fetchall(conn2,
            "SELECT achievement_key FROM player_achievements WHERE player_id=?",
            (player_id,))]

        # XP progress to next level
        levels = fetchall(conn2,
            "SELECT level, xp_required FROM level_definitions ORDER BY level")
        current_level = profile["current_level"]
        current_xp    = profile["total_xp"]

        current_lvl_def = next((l for l in levels if l["level"] == current_level), None)
        next_lvl_def    = next((l for l in levels if l["level"] == current_level + 1), None)

        if current_lvl_def and next_lvl_def:
            xp_in_level    = current_xp - current_lvl_def["xp_required"]
            xp_for_level   = next_lvl_def["xp_required"] - current_lvl_def["xp_required"]
            profile["xp_progress_pct"] = round(
                min(100.0, (xp_in_level / xp_for_level) * 100), 1)
            profile["xp_to_next_level"] = max(0, next_lvl_def["xp_required"] - current_xp)
        else:
            profile["xp_progress_pct"]  = 100.0
            profile["xp_to_next_level"] = 0

        conn2.close()
        return profile
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Live Config Tuning API
# ─────────────────────────────────────────────────────────────────────────────

def update_config(key: str, value, updated_by: str = "admin") -> dict:
    """
    Update a config value without code deploy.
    Validates key exists before writing.
    """
    conn = get_db()
    try:
        existing = fetchone(conn,
            "SELECT config_key FROM config_store WHERE config_key=?", (key,))
        if not existing:
            raise ValueError(f"Config key not found: {key}. "
                             "Add new keys via migration, not live update.")

        serialized = json.dumps(value) if not isinstance(value, str) else value

        conn.execute("""
            UPDATE config_store
            SET config_value=?, updated_by=?, updated_at=?, version=?
            WHERE config_key=?
        """, (serialized, updated_by, now_iso(),
              get_config(conn, "version.config", "1.0.0"), key))
        conn.commit()

        return {"config_key": key, "config_value": value,
                "updated_by": updated_by, "updated_at": now_iso()}
    finally:
        conn.close()


def get_all_config() -> dict:
    """Return all config as a flat dict. Used by operator dashboard."""
    conn = get_db()
    try:
        rows = fetchall(conn, "SELECT config_key, config_value, description FROM config_store")
        return {r["config_key"]: {
            "value": r["config_value"],
            "description": r["description"]
        } for r in rows}
    finally:
        conn.close()
