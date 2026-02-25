"""
HEROES' VERITAS XR SYSTEMS — Session Orchestration Engine
Phase 1A — Component 2

Responsibilities:
  - Session lifecycle state machine (Idle → Lobby → Running → ... → Completed)
  - Node graph traversal and flag-based transitions
  - Timer management (start, pause, resume, elapsed)
  - Flag emission system (SetFlag, CheckFlag, GetFlags)
  - Hint system (tiered, time-based + manual trigger)
  - Fail/success state handling
  - Deterministic reset (soft + hard)
  - Telemetry event emission at every state change

This logic is server-authoritative. The UE5.5 client is a consumer,
never a source of truth for session state.
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from db.connection import get_db, fetchone, fetchall


# ── Constants ─────────────────────────────────────────────────────────────────

SESSION_STATES = [
    "idle", "lobby", "running", "paused",
    "node_transition", "completed", "failed",
    "resetting", "error"
]

NODE_STATES = [
    "locked", "available", "in_progress",
    "completed", "failed", "skipped"
]

# Valid state transitions — no implicit jumps allowed
VALID_TRANSITIONS = {
    "idle":            ["lobby"],
    "lobby":           ["running", "idle"],
    "running":         ["paused", "node_transition", "completed", "failed", "error"],
    "paused":          ["running", "failed", "resetting"],
    "node_transition": ["running", "completed", "failed"],
    "completed":       ["resetting"],
    "failed":          ["resetting"],
    "resetting":       ["idle"],
    "error":           ["resetting", "idle"],
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> datetime:
    return datetime.now(timezone.utc)


def get_config(conn, key: str, default=None):
    row = fetchone(conn, "SELECT config_value FROM config_store WHERE config_key=?", (key,))
    if row is None:
        return default
    val = row["config_value"]
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# ── Telemetry ─────────────────────────────────────────────────────────────────

def emit_event(conn, event_type: str, session_id: str = None,
               player_id: str = None, node_id: str = None, context: dict = None):
    """Write a telemetry event. Called at every meaningful state change."""
    versions = {
        "gameplay_version": get_config(conn, "version.gameplay", "unknown"),
        "config_version":   get_config(conn, "version.config",   "unknown"),
    }
    conn.execute("""
        INSERT INTO telemetry_events
            (event_id, session_id, player_id, node_id, event_type,
             context_json, gameplay_version, config_version, ts)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), session_id, player_id, node_id, event_type,
        json.dumps(context or {}),
        versions["gameplay_version"], versions["config_version"],
        now_iso()
    ))


# ── Session Creation ──────────────────────────────────────────────────────────

def create_session(player_ids: list, difficulty: str = "normal",
                   room_id: str = None, operator_id: str = None) -> dict:
    """
    Create a new session in 'lobby' state and bind players.
    Returns the session dict.
    """
    conn = get_db()
    try:
        # Validate inputs
        if difficulty not in ("easy", "normal", "hard"):
            raise ValueError(f"Invalid difficulty: {difficulty}")
        if not player_ids:
            raise ValueError("At least one player_id required")

        max_players = int(get_config(conn, "session.max_players", 6))
        if len(player_ids) > max_players:
            raise ValueError(f"Exceeds max players ({max_players})")

        session_id = str(uuid.uuid4())
        party_id   = str(uuid.uuid4())
        duration   = int(get_config(conn, "session.duration_secs", 3600))

        versions = {
            "gameplay_version": get_config(conn, "version.gameplay", "1.0.0"),
            "content_version":  get_config(conn, "version.content",  "1.0.0"),
            "config_version":   get_config(conn, "version.config",   "1.0.0"),
            "economy_version":  get_config(conn, "version.economy",  "1.0.0"),
        }

        conn.execute("""
            INSERT INTO sessions
                (session_id, party_session_id, state, difficulty,
                 total_duration_secs, room_id, operator_id,
                 gameplay_version, content_version, config_version, economy_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id, party_id, "lobby", difficulty,
            duration, room_id, operator_id,
            versions["gameplay_version"], versions["content_version"],
            versions["config_version"],   versions["economy_version"],
        ))

        # Bind players
        for pid in player_ids:
            conn.execute("""
                INSERT OR IGNORE INTO session_players (session_id, player_id)
                VALUES (?,?)
            """, (session_id, pid))

        # Initialise all node states as 'locked'
        nodes = fetchall(conn,
            "SELECT node_id, sequence_order FROM node_definitions "
            "WHERE is_active=1 ORDER BY sequence_order"
        )
        for node in nodes:
            conn.execute("""
                INSERT INTO session_node_states (session_id, node_id, state)
                VALUES (?,?,?)
            """, (session_id, node["node_id"], "locked"))

        # First node is immediately 'available'
        if nodes:
            conn.execute("""
                UPDATE session_node_states SET state='available'
                WHERE session_id=? AND node_id=?
            """, (session_id, nodes[0]["node_id"]))

        emit_event(conn, "session_created", session_id=session_id,
                   context={"difficulty": difficulty, "player_count": len(player_ids),
                             "room_id": room_id})
        conn.commit()

        return get_session(session_id)
    finally:
        conn.close()


# ── Session Retrieval ─────────────────────────────────────────────────────────

def get_session(session_id: str) -> Optional[dict]:
    """Return full session state including players, current node, and flags."""
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT * FROM sessions WHERE session_id=?", (session_id,))
        if not session:
            return None

        session["players"] = fetchall(conn,
            "SELECT player_id, health, energy, is_active FROM session_players "
            "WHERE session_id=?", (session_id,))

        session["flags"] = [r["flag_id"] for r in fetchall(conn,
            "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,))]

        session["node_states"] = fetchall(conn,
            "SELECT ns.node_id, ns.state, ns.attempts, ns.hints_used, "
            "       ns.entered_at, ns.completed_at, ns.time_spent_secs, "
            "       nd.node_type, nd.display_name, nd.sequence_order "
            "FROM session_node_states ns "
            "JOIN node_definitions nd ON ns.node_id=nd.node_id "
            "WHERE ns.session_id=? ORDER BY nd.sequence_order", (session_id,))

        session["elapsed_secs"] = _calc_elapsed(session)
        session["time_remaining_secs"] = max(
            0, session["total_duration_secs"] - session["elapsed_secs"]
        )

        return session
    finally:
        conn.close()


def _calc_elapsed(session: dict) -> int:
    """Calculate elapsed session time accounting for pauses."""
    if not session.get("timer_started_at"):
        return 0
    started = datetime.fromisoformat(session["timer_started_at"])
    elapsed = (now_ts() - started).total_seconds()
    return max(0, int(elapsed) - session.get("timer_paused_secs", 0))


# ── State Transitions ─────────────────────────────────────────────────────────

def transition_session(session_id: str, new_state: str,
                        operator_id: str = None, reason: str = None) -> dict:
    """
    Move session to new_state. Validates against VALID_TRANSITIONS.
    Raises ValueError on invalid transition.
    """
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT state FROM sessions WHERE session_id=?", (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        current = session["state"]
        if new_state not in VALID_TRANSITIONS.get(current, []):
            raise ValueError(
                f"Invalid transition: {current} → {new_state}. "
                f"Allowed: {VALID_TRANSITIONS.get(current, [])}"
            )

        updates = {"state": new_state, "updated_at": now_iso()}

        # Timer management on transitions
        if new_state == "running" and current == "lobby":
            updates["timer_started_at"] = now_iso()
        elif new_state == "paused" and current == "running":
            updates["_pause_started"] = now_iso()   # tracked externally
        elif new_state in ("completed", "failed"):
            updates["completed_at"] = now_iso()

        conn.execute("""
            UPDATE sessions SET state=?, updated_at=?
            WHERE session_id=?
        """, (new_state, updates["updated_at"], session_id))

        if new_state == "running" and current == "lobby":
            conn.execute("""
                UPDATE sessions SET timer_started_at=?
                WHERE session_id=?
            """, (updates["timer_started_at"], session_id))

        if new_state in ("completed", "failed"):
            conn.execute("""
                UPDATE sessions SET completed_at=?
                WHERE session_id=?
            """, (updates["completed_at"], session_id))

        emit_event(conn, "session_state_changed", session_id=session_id,
                   context={"from": current, "to": new_state,
                             "operator_id": operator_id, "reason": reason})
        conn.commit()
        return get_session(session_id)
    finally:
        conn.close()


# ── Session Start / Pause / Resume ───────────────────────────────────────────

def start_session(session_id: str, operator_id: str = None) -> dict:
    return transition_session(session_id, "running", operator_id, "operator_start")


def pause_session(session_id: str, operator_id: str = None) -> dict:
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT state, timer_started_at, timer_paused_secs FROM sessions "
            "WHERE session_id=?", (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        if session["state"] != "running":
            raise ValueError(f"Can only pause a running session (current: {session['state']})")

        # Record pause start timestamp in context for resume calculation
        conn.execute("""
            UPDATE sessions SET state='paused', updated_at=?
            WHERE session_id=?
        """, (now_iso(), session_id))

        emit_event(conn, "session_paused", session_id=session_id,
                   context={"operator_id": operator_id, "paused_at": now_iso()})
        conn.commit()
    finally:
        conn.close()
    return get_session(session_id)


def resume_session(session_id: str, operator_id: str = None) -> dict:
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT state, updated_at, timer_paused_secs FROM sessions "
            "WHERE session_id=?", (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        if session["state"] != "paused":
            raise ValueError(f"Can only resume a paused session (current: {session['state']})")

        # Add time spent paused to the paused accumulator
        paused_at = datetime.fromisoformat(session["updated_at"])
        pause_duration = int((now_ts() - paused_at).total_seconds())
        new_paused_total = session["timer_paused_secs"] + pause_duration

        conn.execute("""
            UPDATE sessions SET state='running', timer_paused_secs=?, updated_at=?
            WHERE session_id=?
        """, (new_paused_total, now_iso(), session_id))

        emit_event(conn, "session_resumed", session_id=session_id,
                   context={"operator_id": operator_id,
                             "pause_duration_secs": pause_duration})
        conn.commit()
    finally:
        conn.close()
    return get_session(session_id)


# ── Flag System ───────────────────────────────────────────────────────────────

def set_flag(session_id: str, flag_id: str, set_by: str = "system") -> bool:
    """
    Emit a flag for a session. Idempotent — setting the same flag twice is safe.
    After setting, check if current node's exit conditions are now met.
    Returns True if flag was newly set, False if already existed.
    """
    conn = get_db()
    try:
        existing = fetchone(conn,
            "SELECT 1 FROM session_flags WHERE session_id=? AND flag_id=?",
            (session_id, flag_id))
        if existing:
            return False

        conn.execute("""
            INSERT INTO session_flags (session_id, flag_id, set_by)
            VALUES (?,?,?)
        """, (session_id, flag_id, set_by))

        emit_event(conn, "flag_set", session_id=session_id,
                   context={"flag_id": flag_id, "set_by": set_by})
        conn.commit()

        # Check if this flag unlocks a node transition
        _check_node_transitions(session_id)
        return True
    finally:
        conn.close()


def get_flags(session_id: str) -> list:
    conn = get_db()
    try:
        return [r["flag_id"] for r in fetchall(conn,
            "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,))]
    finally:
        conn.close()


def check_flag(session_id: str, flag_id: str) -> bool:
    conn = get_db()
    try:
        return bool(fetchone(conn,
            "SELECT 1 FROM session_flags WHERE session_id=? AND flag_id=?",
            (session_id, flag_id)))
    finally:
        conn.close()


# ── Node Transitions ──────────────────────────────────────────────────────────

def _check_node_transitions(session_id: str):
    """
    Called after every flag set. Evaluates whether exit conditions of the
    current in-progress node are met, and if so advances to the next node.
    Internal function — not called directly by UE5.5 client.
    """
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT state, current_node_id FROM sessions WHERE session_id=?",
            (session_id,))
        if not session or session["state"] not in ("running", "node_transition"):
            return

        current_node_id = session["current_node_id"]
        if not current_node_id:
            return

        node_def = fetchone(conn,
            "SELECT * FROM node_definitions WHERE node_id=?", (current_node_id,))
        if not node_def:
            return

        exit_conditions = json.loads(node_def["exit_conditions_json"] or "[]")
        if not exit_conditions:
            return

        current_flags = set(r["flag_id"] for r in fetchall(conn,
            "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,)))

        if all(flag in current_flags for flag in exit_conditions):
            # Mark current node complete
            conn.execute("""
                UPDATE session_node_states
                SET state='completed', completed_at=?
                WHERE session_id=? AND node_id=?
            """, (now_iso(), session_id, current_node_id))

            emit_event(conn, "node_completed", session_id=session_id,
                       node_id=current_node_id,
                       context={"exit_flags": exit_conditions})
            conn.commit()

            # Advance to next available node
            advance_to_next_node(session_id)
    finally:
        conn.close()


def enter_node(session_id: str, node_id: str) -> dict:
    """
    Move session into a specific node. Validates entry conditions.
    Sets session.current_node_id and node state to in_progress.
    """
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT state FROM sessions WHERE session_id=?", (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        node_def = fetchone(conn,
            "SELECT * FROM node_definitions WHERE node_id=?", (node_id,))
        if not node_def:
            raise ValueError(f"Node not found: {node_id}")

        # Validate entry conditions
        entry_conditions = json.loads(node_def["entry_conditions_json"] or "[]")
        if entry_conditions:
            current_flags = set(r["flag_id"] for r in fetchall(conn,
                "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,)))
            missing = [f for f in entry_conditions if f not in current_flags]
            if missing:
                raise ValueError(
                    f"Entry conditions not met for {node_id}. Missing flags: {missing}"
                )

        conn.execute("""
            UPDATE sessions SET current_node_id=?, state='running', updated_at=?
            WHERE session_id=?
        """, (node_id, now_iso(), session_id))

        conn.execute("""
            UPDATE session_node_states
            SET state='in_progress', entered_at=?,
                attempts = attempts + 1
            WHERE session_id=? AND node_id=?
        """, (now_iso(), session_id, node_id))

        emit_event(conn, "node_entered", session_id=session_id, node_id=node_id,
                   context={"node_type": node_def["node_type"],
                             "display_name": node_def["display_name"]})
        conn.commit()
        return get_session(session_id)
    finally:
        conn.close()


def advance_to_next_node(session_id: str) -> dict:
    """
    Find and enter the next available node after current one completes.
    If no next node exists, the session is complete.
    """
    conn = get_db()
    try:
        session = fetchone(conn,
            "SELECT current_node_id FROM sessions WHERE session_id=?", (session_id,))
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        current_node_id = session["current_node_id"]

        # Get all nodes ordered by sequence
        all_nodes = fetchall(conn,
            "SELECT nd.node_id, nd.sequence_order, nd.entry_conditions_json, "
            "       ns.state as node_state "
            "FROM node_definitions nd "
            "JOIN session_node_states ns ON nd.node_id=ns.node_id AND ns.session_id=? "
            "WHERE nd.is_active=1 ORDER BY nd.sequence_order",
            (session_id,))

        current_order = next(
            (n["sequence_order"] for n in all_nodes if n["node_id"] == current_node_id),
            -1
        )

        current_flags = set(r["flag_id"] for r in fetchall(conn,
            "SELECT flag_id FROM session_flags WHERE session_id=?", (session_id,)))

        # Find next node whose entry conditions are met
        next_node = None
        for node in all_nodes:
            if node["sequence_order"] <= current_order:
                continue
            entry_conditions = json.loads(node["entry_conditions_json"] or "[]")
            if all(f in current_flags for f in entry_conditions):
                next_node = node
                break

        conn.commit()

        if not next_node:
            # No more nodes — session complete
            return _complete_session(session_id)

        # Unlock the next node then enter it
        conn3 = get_db()
        try:
            conn3.execute("""
                UPDATE session_node_states SET state='available'
                WHERE session_id=? AND node_id=?
            """, (session_id, next_node["node_id"]))
            conn3.commit()
        finally:
            conn3.close()

        return enter_node(session_id, next_node["node_id"])
    finally:
        conn.close()


def _complete_session(session_id: str) -> dict:
    """Mark session as completed and emit final telemetry."""
    conn = get_db()
    try:
        session = fetchone(conn, "SELECT * FROM sessions WHERE session_id=?", (session_id,))
        elapsed = _calc_elapsed(session)
        conn.execute("""
            UPDATE sessions SET state='completed', completed_at=?, updated_at=?
            WHERE session_id=?
        """, (now_iso(), now_iso(), session_id))

        emit_event(conn, "session_completed", session_id=session_id,
                   context={"elapsed_secs": elapsed,
                             "difficulty": session["difficulty"]})
        conn.commit()
    finally:
        conn.close()
    return get_session(session_id)


# ── Hint System ───────────────────────────────────────────────────────────────

def request_hint(session_id: str, node_id: str,
                 player_id: str = None, forced: bool = False) -> dict:
    """
    Issue the next available hint tier for a node.
    Tiered: hint 1 (nudge) → hint 2 (directional) → hint 3 (near-solution).
    Returns hint content and tier.
    """
    conn = get_db()
    try:
        node_state = fetchone(conn,
            "SELECT hints_used FROM session_node_states "
            "WHERE session_id=? AND node_id=?", (session_id, node_id))
        if not node_state:
            raise ValueError(f"Node state not found: {node_id} in {session_id}")

        node_def = fetchone(conn,
            "SELECT config_json, display_name FROM node_definitions WHERE node_id=?",
            (node_id,))
        config = json.loads(node_def["config_json"] or "{}")
        hints_used = node_state["hints_used"]

        hint_tiers = [
            {"tier": 1, "type": "nudge",       "message": f"Look more carefully at the {node_def['display_name']}. Something in the environment holds the key."},
            {"tier": 2, "type": "directional",  "message": f"Focus on the interactive elements directly. The sequence matters — try a different order."},
            {"tier": 3, "type": "near_solution","message": f"The solution is within reach. Check each element systematically from left to right."},
        ]

        next_tier = min(hints_used, 2)  # cap at tier 3 (index 2)
        hint = hint_tiers[next_tier]

        # Increment hints used
        conn.execute("""
            UPDATE session_node_states SET hints_used = hints_used + 1
            WHERE session_id=? AND node_id=?
        """, (session_id, node_id))

        emit_event(conn, "hint_used", session_id=session_id, node_id=node_id,
                   player_id=player_id,
                   context={"tier": hint["tier"], "forced": forced})
        conn.commit()
        return hint
    finally:
        conn.close()


def check_auto_hints(session_id: str, node_id: str) -> Optional[dict]:
    """
    Check if time-based auto-hint should fire.
    Called periodically by the orchestration loop.
    Returns a hint dict if one should be shown, None otherwise.
    """
    conn = get_db()
    try:
        node_state = fetchone(conn,
            "SELECT hints_used, entered_at FROM session_node_states "
            "WHERE session_id=? AND node_id=?", (session_id, node_id))
        if not node_state or not node_state["entered_at"]:
            return None

        entered = datetime.fromisoformat(node_state["entered_at"])
        time_in_node = int((now_ts() - entered).total_seconds())
        hints_used = node_state["hints_used"]

        thresholds = get_config(conn, "hints.auto_trigger_secs", [180, 360, 540])

        # Fire if we've crossed a threshold we haven't hinted yet
        for i, threshold in enumerate(thresholds):
            if time_in_node >= threshold and hints_used <= i:
                return request_hint(session_id, node_id, forced=True)

        return None
    finally:
        conn.close()


# ── Reset System ──────────────────────────────────────────────────────────────

def soft_reset_node(session_id: str, node_id: str,
                    operator_id: str = None) -> dict:
    """
    Soft reset: return node to checkpoint state (attempts preserved).
    Clears node-specific flags without touching other session state.
    """
    conn = get_db()
    try:
        node_def = fetchone(conn,
            "SELECT exit_conditions_json FROM node_definitions WHERE node_id=?",
            (node_id,))
        if not node_def:
            raise ValueError(f"Node not found: {node_id}")

        # Remove only this node's exit flags
        exit_flags = json.loads(node_def["exit_conditions_json"] or "[]")
        for flag in exit_flags:
            conn.execute("""
                DELETE FROM session_flags
                WHERE session_id=? AND flag_id=?
            """, (session_id, flag))

        conn.execute("""
            UPDATE session_node_states
            SET state='in_progress', completed_at=NULL
            WHERE session_id=? AND node_id=?
        """, (session_id, node_id))

        _log_operator_action(conn, operator_id, session_id, "soft_reset_node",
                             {"node_id": node_id})
        emit_event(conn, "node_soft_reset", session_id=session_id, node_id=node_id,
                   context={"operator_id": operator_id})
        conn.commit()
        return get_session(session_id)
    finally:
        conn.close()


def hard_reset_session(session_id: str, operator_id: str = None) -> dict:
    """
    Hard reset: full session wipe back to initial state.
    Deterministic — clears all flags, resets all nodes, restores timer.
    Must complete within session.reset_sla_secs.
    Previous session data is preserved in telemetry.
    """
    conn = get_db()
    try:
        conn.execute("""
            UPDATE sessions
            SET state='lobby', current_node_id=NULL,
                timer_started_at=NULL, timer_paused_secs=0,
                completed_at=NULL, updated_at=?
            WHERE session_id=?
        """, (now_iso(), session_id))

        # Clear all flags
        conn.execute("DELETE FROM session_flags WHERE session_id=?", (session_id,))

        # Reset all node states to locked
        conn.execute("""
            UPDATE session_node_states
            SET state='locked', attempts=0, hints_used=0,
                entered_at=NULL, completed_at=NULL, time_spent_secs=0
            WHERE session_id=?
        """, (session_id,))

        # First node back to available
        first_node = fetchone(conn,
            "SELECT nd.node_id FROM node_definitions nd "
            "JOIN session_node_states ns ON nd.node_id=ns.node_id "
            "WHERE ns.session_id=? AND nd.is_active=1 "
            "ORDER BY nd.sequence_order LIMIT 1", (session_id,))
        if first_node:
            conn.execute("""
                UPDATE session_node_states SET state='available'
                WHERE session_id=? AND node_id=?
            """, (session_id, first_node["node_id"]))

        # Transition to lobby — immediately ready to start a new run
        conn.execute("""
            UPDATE sessions SET state='lobby', updated_at=?
            WHERE session_id=?
        """, (now_iso(), session_id))

        _log_operator_action(conn, operator_id, session_id, "hard_reset_session", {})
        emit_event(conn, "session_hard_reset", session_id=session_id,
                   context={"operator_id": operator_id})
        conn.commit()
        return get_session(session_id)
    finally:
        conn.close()


# ── Operator Actions ──────────────────────────────────────────────────────────

def _log_operator_action(conn, operator_id: str, session_id: str,
                          action_type: str, payload: dict):
    conn.execute("""
        INSERT INTO operator_actions
            (action_id, operator_id, session_id, action_type, payload_json, confirmed)
        VALUES (?,?,?,?,?,1)
    """, (str(uuid.uuid4()), operator_id, session_id,
          action_type, json.dumps(payload)))


def operator_bypass_node(session_id: str, node_id: str,
                          operator_id: str = None) -> dict:
    """
    Force-complete a node without solving it.
    Sets current_node_id to this node first so advance_to_next_node
    can find the correct sequence position, then advances.
    """
    conn = get_db()
    try:
        node_def = fetchone(conn,
            "SELECT exit_conditions_json FROM node_definitions WHERE node_id=?",
            (node_id,))
        if not node_def:
            raise ValueError(f"Node not found: {node_id}")

        # Force-unlock this node in case it is still locked
        conn.execute("""
            UPDATE session_node_states SET state='available'
            WHERE session_id=? AND node_id=?
        """, (session_id, node_id))

        # Set current_node_id so advance_to_next_node knows our position
        conn.execute("""
            UPDATE sessions SET current_node_id=?, state='running', updated_at=?
            WHERE session_id=?
        """, (node_id, now_iso(), session_id))

        # Mark node skipped with timestamps
        conn.execute("""
            UPDATE session_node_states
            SET state='skipped', completed_at=?, entered_at=COALESCE(entered_at, ?)
            WHERE session_id=? AND node_id=?
        """, (now_iso(), now_iso(), session_id, node_id))

        # Inject all exit flags
        exit_flags = json.loads(node_def["exit_conditions_json"] or "[]")
        for flag in exit_flags:
            conn.execute("""
                INSERT OR IGNORE INTO session_flags (session_id, flag_id, set_by)
                VALUES (?,?,?)
            """, (session_id, flag, f"operator:{operator_id}"))

        _log_operator_action(conn, operator_id, session_id, "bypass_node",
                             {"node_id": node_id, "flags_set": exit_flags})
        emit_event(conn, "node_bypassed", session_id=session_id, node_id=node_id,
                   context={"operator_id": operator_id})
        conn.commit()
    finally:
        conn.close()

    # Advance to next node (or complete session if this was the last node)
    return advance_to_next_node(session_id)


def operator_force_fail(session_id: str, operator_id: str = None,
                         reason: str = None) -> dict:
    """Force a session into failed state."""
    return transition_session(session_id, "failed", operator_id, reason or "operator_force_fail")
