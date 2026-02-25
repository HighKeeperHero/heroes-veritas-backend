"""
HEROES' VERITAS XR SYSTEMS — Session Orchestration Engine
Phase 1A — Component 2

Responsibilities:
  - Session lifecycle state machine (Idle → Lobby → Running → ... → Completed)
  - Node graph traversal and entry/exit condition validation
  - Timer management (start, pause, resume, remaining)
  - Unified flag system (SetFlag, CheckFlag, EmitOutputs)
  - Hint system (tiered, time-threshold + manual request)
  - Puzzle ↔ Combat interop via shared flag primitives
  - Telemetry event emission on every state transition
  - Deterministic reset (soft node reset + full hard reset)
  - Operator override hooks (bypass, force-advance, hint inject)
"""

import json
import uuid
import datetime
from typing import Optional

from db.connection import get_db, fetchone, fetchall


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

class SessionState:
    IDLE            = "idle"
    LOBBY           = "lobby"
    RUNNING         = "running"
    PAUSED          = "paused"
    NODE_TRANSITION = "node_transition"
    COMPLETED       = "completed"
    FAILED          = "failed"
    RESETTING       = "resetting"
    ERROR           = "error"

VALID_TRANSITIONS = {
    SessionState.IDLE:            [SessionState.LOBBY, SessionState.RESETTING],
    SessionState.LOBBY:           [SessionState.RUNNING, SessionState.IDLE, SessionState.RESETTING],
    SessionState.RUNNING:         [SessionState.PAUSED, SessionState.NODE_TRANSITION,
                                   SessionState.COMPLETED, SessionState.FAILED,
                                   SessionState.RESETTING, SessionState.ERROR],
    SessionState.PAUSED:          [SessionState.RUNNING, SessionState.RESETTING, SessionState.ERROR],
    SessionState.NODE_TRANSITION: [SessionState.RUNNING, SessionState.COMPLETED,
                                   SessionState.FAILED, SessionState.ERROR],
    SessionState.COMPLETED:       [SessionState.IDLE, SessionState.RESETTING],
    SessionState.FAILED:          [SessionState.IDLE, SessionState.RESETTING],
    SessionState.RESETTING:       [SessionState.IDLE],
    SessionState.ERROR:           [SessionState.RESETTING, SessionState.IDLE],
}

class NodeState:
    LOCKED      = "locked"
    AVAILABLE   = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    SKIPPED     = "skipped"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _new_id() -> str:
    return str(uuid.uuid4())

def _get_config(conn, key: str, default=None):
    row = fetchone(conn, "SELECT config_value FROM config_store WHERE config_key=?", (key,))
    if row:
        val = row["config_value"]
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return default

def _emit_telemetry(conn, session_id: str, player_id: Optional[str],
                    node_id: Optional[str], event_type: str, context: dict):
    versions = {
        "gameplay_version": _get_config(conn, "version.gameplay", "1.0.0"),
        "config_version":   _get_config(conn, "version.config",   "1.0.0"),
    }
    conn.execute("""
        INSERT INTO telemetry_events
            (event_id, session_id, player_id, node_id, event_type,
             context_json, gameplay_version, config_version, ts)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        _new_id(), session_id, player_id, node_id, event_type,
        json.dumps(context),
        versions["gameplay_version"], versions["config_version"],
        _now_iso()
    ))

def _log_operator_action(conn, operator_id: str, session_id: str,
                          action_type: str, payload: dict, confirmed: bool = True):
    conn.execute("""
        INSERT INTO operator_actions
            (action_id, operator_id, session_id, action_type, payload_json, confirmed, ts)
        VALUES (?,?,?,?,?,?,?)
    """, (
        _new_id(), operator_id, session_id, action_type,
        json.dumps(payload), 1 if confirmed else 0, _now_iso()
    ))


# ─────────────────────────────────────────────────────────────────────────────
# SESSION CREATION
# ─────────────────────────────────────────────────────────────────────────────

def create_session(player_ids: list, difficulty: str = "normal",
                   room_id: str = None, operator_id: str = None) -> dict:
    """
    Create a new session in LOBBY state and bind players.
    Returns the full session record.
    """
    if difficulty not in ("easy", "normal", "hard"):
        raise ValueError(f"Invalid difficulty: {difficulty}")

    conn = get_db()
    session_id = _new_id()
    party_id   = _new_id()
    duration   = int(_get_config(conn, "session.duration_secs", 3600))
    max_p      = int(_get_config(conn, "session.max_players", 6))
    min_p      = int(_get_config(conn, "session.min_players", 2))

    if len(player_ids) < min_p:
        raise ValueError(f"Minimum {min_p} players required, got {len(player_ids)}")
    if len(player_ids) > max_p:
        raise ValueError(f"Maximum {max_p} players allowed, got {len(player_ids)}")

    # Verify all players exist
    for pid in player_ids:
        if not fetchone(conn, "SELECT 1 FROM players WHERE player_id=?", (pid,)):
            raise ValueError(f"Player not found: {pid}")

    versions = {
        "gameplay_version": _get_config(conn, "version.gameplay", "1.0.0"),
        "content_version":  _get_config(conn, "version.content",  "1.0.0"),
        "config_version":   _get_config(conn, "version.config",   "1.0.0"),
        "economy_version":  _get_config(conn, "version.economy",  "1.0.0"),
    }

    conn.execute("""
        INSERT INTO sessions
            (session_id, party_session_id, state, difficulty,
             total_duration_secs, room_id, operator_id,
             gameplay_version, content_version, config_version, economy_version,
             created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        session_id, party_id, SessionState.LOBBY, difficulty,
        duration, room_id, operator_id,
        versions["gameplay_version"], versions["content_version"],
        versions["config_version"], versions["economy_version"],
        _now_iso(), _now_iso()
    ))

    for pid in player_ids:
        conn.execute("""
            INSERT INTO session_players (session_id, player_id, joined_at)
            VALUES (?,?,?)
        """, (session_id, pid, _now_iso()))

    # Initialize node states
    nodes = fetchall(conn, """
        SELECT node_id, sequence_order, entry_conditions_json
        FROM node_definitions WHERE is_active=1 ORDER BY sequence_order
    """)
    for node in nodes:
        entry_conds = json.loads(node["entry_conditions_json"] or "[]")
        initial_state = NodeState.AVAILABLE if not entry_conds else NodeState.LOCKED
        conn.execute("""
            INSERT INTO session_node_states
                (session_id, node_id, state)
            VALUES (?,?,?)
        """, (session_id, node["node_id"], initial_state))

    _emit_telemetry(conn, session_id, None, None, "session_created", {
        "player_count": len(player_ids),
        "difficulty": difficulty,
        "room_id": room_id
    })

    conn.commit()
    session = get_session(session_id)
    conn.close()
    return session


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────

def _transition_session(conn, session_id: str, new_state: str, context: dict = None):
    """
    Validated state transition. Raises if transition is invalid.
    All transitions are logged to telemetry.
    """
    session = fetchone(conn, "SELECT state FROM sessions WHERE session_id=?", (session_id,))
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    current = session["state"]
    allowed = VALID_TRANSITIONS.get(current, [])
    if new_state not in allowed:
        raise ValueError(
            f"Invalid transition: {current} → {new_state}. "
            f"Allowed: {allowed}"
        )

    conn.execute("""
        UPDATE sessions SET state=?, updated_at=? WHERE session_id=?
    """, (new_state, _now_iso(), session_id))

    _emit_telemetry(conn, session_id, None, None, "session_state_changed", {
        "from": current, "to": new_state, **(context or {})
    })


def start_session(session_id: str, operator_id: str = None) -> dict:
    """
    Transition LOBBY → RUNNING.
    Starts the timer and enters the first available node.
    """
    conn = get_db()
    _transition_session(conn, session_id, SessionState.RUNNING)

    conn.execute("""
        UPDATE sessions SET timer_started_at=?, updated_at=? WHERE session_id=?
    """, (_now_iso(), _now_iso(), session_id))

    if operator_id:
        _log_operator_action(conn, operator_id, session_id, "start_session", {})

    conn.commit()

    # Enter first node
    result = _enter_next_available_node(session_id)
    conn.close()
    return result


def pause_session(session_id: str, operator_id: str = None) -> dict:
    """Transition RUNNING → PAUSED. Accumulates paused time for timer accuracy."""
    conn = get_db()
    session = fetchone(conn, "SELECT * FROM sessions WHERE session_id=?", (session_id,))

    elapsed = _calc_elapsed_secs(session)
    conn.execute("""
        UPDATE sessions SET
            state=?,
            timer_paused_secs=?,
            updated_at=?
        WHERE session_id=?
    """, (SessionState.PAUSED, elapsed, _now_iso(), session_id))

    _emit_telemetry(conn, session_id, None, None, "session_state_changed", {
        "from": SessionState.RUNNING, "to": SessionState.PAUSED,
        "elapsed_secs": elapsed
    })
    if operator_id:
        _log_operator_action(conn, operator_id, session_id, "pause_session",
                             {"elapsed_secs": elapsed})

    conn.commit()
    conn.close()
    return get_session(session_id)


def resume_session(session_id: str, operator_id: str = None) -> dict:
    """Transition PAUSED → RUNNING. Resets timer_started_at to now so elapsed is correct."""
    conn = get_db()

    conn.execute("""
        UPDATE sessions SET
            state=?,
            timer_started_at=?,
            updated_at=?
        WHERE session_id=?
    """, (SessionState.RUNNING, _now_iso(), _now_iso(), session_id))

    _emit_telemetry(conn, session_id, None, None, "session_state_changed", {
        "from": SessionState.PAUSED, "to": SessionState.RUNNING
    })
    if operator_id:
        _log_operator_action(conn, operator_id, session_id, "resume_session", {})

    conn.commit()
    conn.close()
    return get_session(session_id)


def complete_session(session_id: str) -> dict:
    """Transition RUNNING/NODE_TRANSITION → COMPLETED."""
    conn = get_db()
    _transition_session(conn, session_id, SessionState.COMPLETED, {"reason": "all_nodes_complete"})
    conn.execute("""
        UPDATE sessions SET completed_at=?, updated_at=? WHERE session_id=?
    """, (_now_iso(), _now_iso(), session_id))
    conn.commit()
    conn.close()
    return get_session(session_id)


def fail_session(session_id: str, reason: str = "unknown") -> dict:
    """Transition RUNNING → FAILED."""
    conn = get_db()
    _transition_session(conn, session_id, SessionState.FAILED, {"reason": reason})
    conn.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (_now_iso(), session_id))
    conn.commit()
    conn.close()
    return get_session(session_id)


# ─────────────────────────────────────────────────────────────────────────────
# TIMER
# ─────────────────────────────────────────────────────────────────────────────

def _calc_elapsed_secs(session: dict) -> int:
    """
    Compute total elapsed seconds accounting for pause accumulation.
    When paused: elapsed = timer_paused_secs (frozen at pause moment).
    When running: elapsed = timer_paused_secs + (now - timer_started_at).
    """
    if session["state"] == SessionState.PAUSED:
        return session.get("timer_paused_secs", 0)

    started = session.get("timer_started_at")
    if not started:
        return 0

    # Strip trailing Z for fromisoformat compatibility
    started_dt = datetime.datetime.fromisoformat(started.rstrip("Z"))
    now_dt = datetime.datetime.utcnow()
    live_elapsed = int((now_dt - started_dt).total_seconds())
    return session.get("timer_paused_secs", 0) + live_elapsed


def get_timer_status(session_id: str) -> dict:
    """Returns elapsed, remaining, and percent complete."""
    conn = get_db()
    session = fetchone(conn, "SELECT * FROM sessions WHERE session_id=?", (session_id,))
    conn.close()
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    duration = session["total_duration_secs"]
    elapsed  = _calc_elapsed_secs(session)
    remaining = max(0, duration - elapsed)
    pct = round((elapsed / duration) * 100, 1) if duration > 0 else 0

    expired = elapsed >= duration and session["state"] == SessionState.RUNNING

    return {
        "session_id":   session_id,
        "state":        session["state"],
        "duration_secs":  duration,
        "elapsed_secs":   elapsed,
        "remaining_secs": remaining,
        "percent_complete": pct,
        "expired": expired
    }


# ─────────────────────────────────────────────────────────────────────────────
# FLAG SYSTEM — Unified Output Primitives
# ─────────────────────────────────────────────────────────────────────────────

def set_flag(session_id: str, flag_id: str, set_by: str = None) -> dict:
    """
    SetFlag(flag_id) — unified output primitive for puzzles and combat.
    After setting, evaluates node exit conditions and unlocks downstream nodes.
    """
    conn = get_db()
    existing = fetchone(conn,
        "SELECT 1 FROM session_flags WHERE session_id=? AND flag_id=?",
        (session_id, flag_id)
    )
    if not existing:
        conn.execute("""
            INSERT INTO session_flags (session_id, flag_id, set_by, set_at)
            VALUES (?,?,?,?)
        """, (session_id, flag_id, set_by, _now_iso()))

        _emit_telemetry(conn, session_id, None, set_by, "flag_set", {
            "flag_id": flag_id, "set_by": set_by
        })
        conn.commit()

    # Re-evaluate node unlock states
    _evaluate_node_unlocks(conn, session_id)

    # Check if current node's exit conditions are met
    session = fetchone(conn, "SELECT current_node_id FROM sessions WHERE session_id=?", (session_id,))
    advanced = False
    if session and session["current_node_id"]:
        advanced = _check_node_exit(conn, session_id, session["current_node_id"])

    conn.commit()
    conn.close()

    return {
        "flag_id": flag_id,
        "session_id": session_id,
        "node_advanced": advanced
    }


def check_flag(session_id: str, flag_id: str) -> bool:
    """Returns True if flag is set for this session."""
    conn = get_db()
    row = fetchone(conn,
        "SELECT 1 FROM session_flags WHERE session_id=? AND flag_id=?",
        (session_id, flag_id)
    )
    conn.close()
    return row is not None


def get_session_flags(session_id: str) -> list:
    """Returns all flags set for a session."""
    conn = get_db()
    flags = fetchall(conn,
        "SELECT flag_id, set_by, set_at FROM session_flags WHERE session_id=? ORDER BY set_at",
        (session_id,)
    )
    conn.close()
    return flags


# ─────────────────────────────────────────────────────────────────────────────
# NODE GRAPH ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate_node_unlocks(conn, session_id: str):
    """
    Re-evaluate all LOCKED nodes — unlock any whose entry conditions are now met.
    Called after every flag set.
    """
    active_flags = {
        r["flag_id"] for r in fetchall(conn,
            "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,)
        )
    }
    locked_nodes = fetchall(conn, """
        SELECT sns.node_id, nd.entry_conditions_json
        FROM session_node_states sns
        JOIN node_definitions nd ON sns.node_id = nd.node_id
        WHERE sns.session_id=? AND sns.state=?
    """, (session_id, NodeState.LOCKED))

    for node in locked_nodes:
        entry_conds = json.loads(node["entry_conditions_json"] or "[]")
        if all(f in active_flags for f in entry_conds):
            conn.execute("""
                UPDATE session_node_states SET state=?
                WHERE session_id=? AND node_id=?
            """, (NodeState.AVAILABLE, session_id, node["node_id"]))
            _emit_telemetry(conn, session_id, None, node["node_id"], "node_unlocked", {
                "entry_conditions_met": entry_conds
            })


def _check_node_exit(conn, session_id: str, node_id: str) -> bool:
    """
    Check if the current node's exit conditions are satisfied.
    If yes, mark node COMPLETED and advance to next.
    Returns True if node was advanced.
    """
    node_def = fetchone(conn,
        "SELECT exit_conditions_json FROM node_definitions WHERE node_id=?", (node_id,)
    )
    if not node_def:
        return False

    exit_conds = json.loads(node_def["exit_conditions_json"] or "[]")
    if not exit_conds:
        return False

    active_flags = {
        r["flag_id"] for r in fetchall(conn,
            "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,)
        )
    }

    if all(f in active_flags for f in exit_conds):
        # Mark node completed
        conn.execute("""
            UPDATE session_node_states
            SET state=?, completed_at=?
            WHERE session_id=? AND node_id=?
        """, (NodeState.COMPLETED, _now_iso(), session_id, node_id))

        _emit_telemetry(conn, session_id, None, node_id, "node_completed", {
            "exit_conditions_met": exit_conds
        })
        return True
    return False


def _enter_next_available_node(session_id: str) -> dict:
    """
    Find and enter the next AVAILABLE node in sequence order.
    Sets current_node_id on session, marks node IN_PROGRESS.
    If no nodes remain, complete the session.
    """
    conn = get_db()

    available = fetchall(conn, """
        SELECT sns.node_id, nd.sequence_order, nd.node_type, nd.display_name
        FROM session_node_states sns
        JOIN node_definitions nd ON sns.node_id = nd.node_id
        WHERE sns.session_id=? AND sns.state=?
        ORDER BY nd.sequence_order ASC
        LIMIT 1
    """, (session_id, NodeState.AVAILABLE))

    if not available:
        # No nodes left — session complete
        conn.close()
        return complete_session(session_id)

    node = available[0]
    node_id = node["node_id"]

    conn.execute("""
        UPDATE sessions SET current_node_id=?, node_index=node_index+1,
        state=?, updated_at=? WHERE session_id=?
    """, (node_id, SessionState.RUNNING, _now_iso(), session_id))

    conn.execute("""
        UPDATE session_node_states
        SET state=?, attempts=attempts+1, entered_at=?
        WHERE session_id=? AND node_id=?
    """, (NodeState.IN_PROGRESS, _now_iso(), session_id, node_id))

    _emit_telemetry(conn, session_id, None, node_id, "node_entered", {
        "node_type": node["node_type"],
        "display_name": node["display_name"],
        "sequence_order": node["sequence_order"]
    })

    conn.commit()
    conn.close()
    return get_session(session_id)


def get_node_status(session_id: str) -> list:
    """Returns full node graph status for a session — used by operator dashboard."""
    conn = get_db()
    nodes = fetchall(conn, """
        SELECT
            nd.node_id, nd.display_name, nd.node_type, nd.sequence_order,
            sns.state, sns.attempts, sns.hints_used,
            sns.entered_at, sns.completed_at, sns.time_spent_secs
        FROM session_node_states sns
        JOIN node_definitions nd ON sns.node_id = nd.node_id
        WHERE sns.session_id=?
        ORDER BY nd.sequence_order
    """, (session_id,))
    conn.close()
    return nodes


# ─────────────────────────────────────────────────────────────────────────────
# HINT SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def get_hint(session_id: str, node_id: str, requested_by: str = "player") -> dict:
    """
    Tiered hint system. Returns next hint tier for the current node.
    Hint tiers: 1 (nudge) → 2 (directional) → 3 (near-solution).
    Increments hint counter and logs telemetry.
    """
    conn = get_db()
    node_state = fetchone(conn, """
        SELECT hints_used FROM session_node_states
        WHERE session_id=? AND node_id=?
    """, (session_id, node_id))

    if not node_state:
        conn.close()
        raise ValueError(f"Node {node_id} not found in session {session_id}")

    hints_used = node_state["hints_used"]
    next_tier  = hints_used + 1

    node_def = fetchone(conn,
        "SELECT config_json, display_name FROM node_definitions WHERE node_id=?", (node_id,)
    )
    config = json.loads(node_def["config_json"] or "{}")

    HINT_MESSAGES = {
        "sequence_pattern": {
            1: "Look carefully at the order the symbols were revealed to you.",
            2: "The sequence follows the direction of the light source. Start from the brightest.",
            3: "Begin with the top-left rune, then follow clockwise: top-right, bottom-right, bottom-left, center."
        },
        "spatial_placement": {
            1: "Each shard has a unique shape that matches a socket on the altar.",
            2: "Align the shard markings with the grooves. Rotation matters.",
            3: "Place the triangular shard first (north socket), then circular (east), then crescent (south), then star (west)."
        },
        "search_interpret": {
            1: "The clues are hidden in the environment — look for things that seem out of place.",
            2: "The three symbols you need appear on different surfaces in the room. Check the walls and floor.",
            3: "The cipher key is the Veritas sigil. Match each fragment to the sigil's segments in order."
        },
        "wave_arena": {
            1: "Focus on one enemy type at a time. The ranged enemies are most dangerous.",
            2: "Use the environment as cover. Break line of sight with ranged enemies.",
            3: "Melee enemies have a 1-second wind-up before attacking. Use that window to counterattack."
        },
        "encounter_room": {
            1: "Watch for the boss's tells — it always telegraphs its strongest attack.",
            2: "The boss has a vulnerability window after each phase transition.",
            3: "During the third phase, attack the glowing core on the boss's back during its charge animation."
        },
    }

    puzzle_type = config.get("puzzle_type") or config.get("combat_format", "sequence_pattern")
    hints_for_type = HINT_MESSAGES.get(puzzle_type, {})

    if next_tier > 3:
        hint_text = "Maximum hints reached. Your operator can assist if you are still stuck."
        tier = 3
    else:
        hint_text = hints_for_type.get(next_tier, f"Hint tier {next_tier}: Keep exploring the current node carefully.")
        tier = next_tier

        # Only increment if we have a new tier to give
        conn.execute("""
            UPDATE session_node_states SET hints_used=hints_used+1
            WHERE session_id=? AND node_id=?
        """, (session_id, node_id))

    _emit_telemetry(conn, session_id, None, node_id, "hint_used", {
        "tier": tier, "requested_by": requested_by,
        "puzzle_type": puzzle_type
    })

    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "node_id": node_id,
        "hint_tier": tier,
        "hint_text": hint_text,
        "hints_used_total": hints_used + (1 if next_tier <= 3 else 0),
        "max_hints": 3
    }


def check_hint_threshold(session_id: str, node_id: str) -> dict:
    """
    Called periodically to check if auto-hint should trigger.
    Compares time spent on current node against config thresholds.
    Returns recommended hint tier or None.
    """
    conn = get_db()
    node_state = fetchone(conn, """
        SELECT hints_used, entered_at FROM session_node_states
        WHERE session_id=? AND node_id=? AND state=?
    """, (session_id, node_id, NodeState.IN_PROGRESS))

    thresholds = _get_config(conn, "hints.auto_trigger_secs", [180, 360, 540])
    conn.close()

    if not node_state or not node_state["entered_at"]:
        return {"should_hint": False, "recommended_tier": None}

    entered_dt = datetime.datetime.fromisoformat(node_state["entered_at"].rstrip("Z"))
    time_on_node = int((datetime.datetime.utcnow() - entered_dt).total_seconds())
    hints_used = node_state["hints_used"]

    recommended_tier = None
    for i, threshold in enumerate(thresholds):
        tier = i + 1
        if time_on_node >= threshold and hints_used < tier:
            recommended_tier = tier

    return {
        "should_hint": recommended_tier is not None,
        "recommended_tier": recommended_tier,
        "time_on_node_secs": time_on_node,
        "hints_used": hints_used
    }


# ─────────────────────────────────────────────────────────────────────────────
# RESET SYSTEM — Deterministic
# ─────────────────────────────────────────────────────────────────────────────

def soft_reset_node(session_id: str, node_id: str, operator_id: str = None) -> dict:
    """
    Soft reset: returns current node to IN_PROGRESS from its checkpoint.
    Clears only the flags emitted by this node. Increments attempt counter.
    """
    conn = get_db()

    # Identify which flags this node emits (its exit conditions)
    node_def = fetchone(conn,
        "SELECT exit_conditions_json FROM node_definitions WHERE node_id=?", (node_id,)
    )
    if not node_def:
        raise ValueError(f"Node not found: {node_id}")

    exit_flags = json.loads(node_def["exit_conditions_json"] or "[]")

    # Remove only this node's output flags
    for flag in exit_flags:
        conn.execute("""
            DELETE FROM session_flags WHERE session_id=? AND flag_id=?
        """, (session_id, flag))

    # Reset node state
    conn.execute("""
        UPDATE session_node_states
        SET state=?, completed_at=NULL, attempts=attempts+1, hints_used=0, entered_at=?
        WHERE session_id=? AND node_id=?
    """, (NodeState.IN_PROGRESS, _now_iso(), session_id, node_id))

    _emit_telemetry(conn, session_id, None, node_id, "node_soft_reset", {
        "flags_cleared": exit_flags,
        "operator_id": operator_id
    })
    if operator_id:
        _log_operator_action(conn, operator_id, session_id, "soft_reset_node",
                             {"node_id": node_id, "flags_cleared": exit_flags})

    conn.commit()
    conn.close()
    return get_session(session_id)


def hard_reset_session(session_id: str, operator_id: str = None) -> dict:
    """
    Hard reset: returns session to initial IDLE state.
    Clears all flags, resets all node states, resets timer.
    Preserves session record and player profile data.
    Deterministic — guaranteed to complete cleanly.
    """
    conn = get_db()

    # Transition to RESETTING state
    conn.execute("""
        UPDATE sessions SET state=?, updated_at=? WHERE session_id=?
    """, (SessionState.RESETTING, _now_iso(), session_id))

    # Clear all session flags
    conn.execute("DELETE FROM session_flags WHERE session_id=?", (session_id,))

    # Reset all node states to initial
    nodes = fetchall(conn, """
        SELECT nd.node_id, nd.entry_conditions_json
        FROM session_node_states sns
        JOIN node_definitions nd ON sns.node_id = nd.node_id
        WHERE sns.session_id=?
    """, (session_id,))

    for node in nodes:
        entry_conds = json.loads(node["entry_conditions_json"] or "[]")
        initial_state = NodeState.AVAILABLE if not entry_conds else NodeState.LOCKED
        conn.execute("""
            UPDATE session_node_states
            SET state=?, attempts=0, hints_used=0,
                entered_at=NULL, completed_at=NULL, time_spent_secs=0
            WHERE session_id=? AND node_id=?
        """, (initial_state, session_id, node["node_id"]))

    # Reset session timer and state
    conn.execute("""
        UPDATE sessions SET
            state=?,
            current_node_id=NULL,
            node_index=0,
            timer_started_at=NULL,
            timer_paused_secs=0,
            completed_at=NULL,
            updated_at=?
        WHERE session_id=?
    """, (SessionState.IDLE, _now_iso(), session_id))

    # Reset player health/energy
    conn.execute("""
        UPDATE session_players SET health=100, energy=100
        WHERE session_id=?
    """, (session_id,))

    _emit_telemetry(conn, session_id, None, None, "session_hard_reset", {
        "operator_id": operator_id,
        "nodes_reset": len(nodes),
        "flags_cleared": True
    })
    if operator_id:
        _log_operator_action(conn, operator_id, session_id, "hard_reset_session",
                             {"nodes_reset": len(nodes)})

    conn.commit()
    conn.close()
    return get_session(session_id)


# ─────────────────────────────────────────────────────────────────────────────
# OPERATOR OVERRIDES
# ─────────────────────────────────────────────────────────────────────────────

def operator_bypass_node(session_id: str, node_id: str, operator_id: str) -> dict:
    """
    Operator bypass: force-complete a stuck node by injecting its exit flags.
    Logged as operator action. Used when puzzle is technically stuck.
    """
    conn = get_db()

    node_def = fetchone(conn,
        "SELECT exit_conditions_json, display_name FROM node_definitions WHERE node_id=?",
        (node_id,)
    )
    if not node_def:
        conn.close()
        raise ValueError(f"Node not found: {node_id}")

    exit_flags = json.loads(node_def["exit_conditions_json"] or "[]")

    # Inject all exit flags
    for flag in exit_flags:
        conn.execute("""
            INSERT OR IGNORE INTO session_flags (session_id, flag_id, set_by, set_at)
            VALUES (?,?,?,?)
        """, (session_id, flag, f"operator:{operator_id}", _now_iso()))

    _emit_telemetry(conn, session_id, None, node_id, "node_bypassed", {
        "operator_id": operator_id,
        "flags_injected": exit_flags
    })
    _log_operator_action(conn, operator_id, session_id, "bypass_node", {
        "node_id": node_id,
        "flags_injected": exit_flags
    })

    conn.commit()
    _evaluate_node_unlocks(conn, session_id)
    _check_node_exit(conn, session_id, node_id)
    conn.commit()
    conn.close()

    return _enter_next_available_node(session_id)


def operator_adjust_difficulty(session_id: str, difficulty: str, operator_id: str) -> dict:
    """Live difficulty adjustment within session bounds."""
    if difficulty not in ("easy", "normal", "hard"):
        raise ValueError(f"Invalid difficulty: {difficulty}")
    conn = get_db()
    conn.execute("""
        UPDATE sessions SET difficulty=?, updated_at=? WHERE session_id=?
    """, (difficulty, _now_iso(), session_id))
    _log_operator_action(conn, operator_id, session_id, "adjust_difficulty",
                         {"new_difficulty": difficulty})
    conn.commit()
    conn.close()
    return get_session(session_id)


def freeze_combat_ai(session_id: str, node_id: str, operator_id: str) -> dict:
    """Operator safety control: freeze combat AI for a node."""
    conn = get_db()
    _log_operator_action(conn, operator_id, session_id, "freeze_combat_ai",
                         {"node_id": node_id})
    _emit_telemetry(conn, session_id, None, node_id, "combat_ai_frozen",
                    {"operator_id": operator_id})
    conn.commit()
    conn.close()
    # In UE5.5: this flag is polled by the combat system to halt AI tick
    return set_flag(session_id, f"combat_ai_frozen:{node_id}", f"operator:{operator_id}")


# ─────────────────────────────────────────────────────────────────────────────
# SESSION READ
# ─────────────────────────────────────────────────────────────────────────────

def get_session(session_id: str) -> dict:
    """Full session record including timer status and player list."""
    conn = get_db()
    session = fetchone(conn, "SELECT * FROM sessions WHERE session_id=?", (session_id,))
    if not session:
        conn.close()
        raise ValueError(f"Session not found: {session_id}")

    players = fetchall(conn, """
        SELECT sp.player_id, p.display_name, sp.health, sp.energy, sp.is_active
        FROM session_players sp
        JOIN players p ON sp.player_id = p.player_id
        WHERE sp.session_id=?
    """, (session_id,))

    session["players"] = players

    # Add live timer
    elapsed  = _calc_elapsed_secs(session)
    duration = session["total_duration_secs"]
    session["timer"] = {
        "elapsed_secs":   elapsed,
        "remaining_secs": max(0, duration - elapsed),
        "total_secs":     duration,
        "expired": elapsed >= duration and session["state"] == SessionState.RUNNING
    }

    conn.close()
    return session


def list_active_sessions() -> list:
    """Returns all non-idle, non-completed sessions — for operator dashboard."""
    conn = get_db()
    sessions = fetchall(conn, """
        SELECT s.session_id, s.state, s.difficulty, s.room_id,
               s.current_node_id, s.node_index,
               s.timer_started_at, s.timer_paused_secs, s.total_duration_secs,
               COUNT(sp.player_id) as player_count
        FROM sessions s
        LEFT JOIN session_players sp ON s.session_id = sp.session_id AND sp.is_active=1
        WHERE s.state NOT IN ('idle','completed','failed','resetting')
        GROUP BY s.session_id
        ORDER BY s.created_at DESC
    """)

    for s in sessions:
        elapsed = _calc_elapsed_secs(s)
        s["timer"] = {
            "elapsed_secs": elapsed,
            "remaining_secs": max(0, s["total_duration_secs"] - elapsed)
        }

    conn.close()
    return sessions
