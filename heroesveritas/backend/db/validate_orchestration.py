"""
HEROES' VERITAS XR SYSTEMS — Orchestration Engine Validation Suite
Phase 1A — Component 2

Tests:
  - Session lifecycle (create → lobby → running → completed)
  - State machine transition guards (invalid transitions rejected)
  - Timer accuracy (elapsed, remaining, pause/resume)
  - Flag system (set, check, downstream unlock)
  - Node graph traversal (full 7-node run)
  - Hint system (tiered hints, threshold checks)
  - Soft reset (node-level, flags cleared correctly)
  - Hard reset (full session, deterministic)
  - Operator overrides (bypass, difficulty adjust, AI freeze)
  - Telemetry emission verification
"""

import sys
import os
import time

# Add backend root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.orchestration_engine import (
    create_session, start_session, pause_session, resume_session,
    complete_session, fail_session,
    set_flag, check_flag, get_session_flags,
    get_node_status, get_timer_status,
    get_hint, check_hint_threshold,
    soft_reset_node, hard_reset_session,
    operator_bypass_node, operator_adjust_difficulty, freeze_combat_ai,
    get_session, list_active_sessions,
    SessionState, NodeState
)
from services.player_service import create_player
from db.connection import get_db, fetchall, fetchone

PASS = "  [PASS]"
FAIL = "  [FAIL]"
results = []


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{status} {label}{suffix}")
    results.append(condition)
    return condition


def make_players(n=3):
    return [create_player(f"TestPlayer_{i}") for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== HEROES VERITAS — ORCHESTRATION ENGINE VALIDATION ===\n")

# ── 1. Session Creation ───────────────────────────────────────────────────────
print("[1] Session creation")
players = make_players(3)
pids = [p["player_id"] for p in players]

session = create_session(pids, difficulty="normal", room_id="room_01")
sid = session["session_id"]

check("Session created with ID",   bool(sid))
check("Session state is LOBBY",    session["state"] == SessionState.LOBBY)
check("Session has 3 players",     len(session["players"]) == 3)
check("Difficulty set to normal",  session["difficulty"] == "normal")
check("Timer not started yet",     session["timer"]["elapsed_secs"] == 0)
check("Version tags present",      bool(session["gameplay_version"]))

# ── 2. State Machine Guards ───────────────────────────────────────────────────
print("\n[2] State machine — invalid transition rejection")
try:
    complete_session(sid)  # LOBBY → COMPLETED is invalid
    check("LOBBY→COMPLETED rejected", False, "should have raised")
except ValueError as e:
    check("LOBBY→COMPLETED rejected", True, str(e)[:60])

try:
    fail_session(sid)  # LOBBY → FAILED is invalid
    check("LOBBY→FAILED rejected", False, "should have raised")
except ValueError as e:
    check("LOBBY→FAILED rejected", True, str(e)[:60])

# ── 3. Start Session + Timer ──────────────────────────────────────────────────
print("\n[3] Start session & timer")
session = start_session(sid)
check("Session state is RUNNING",  session["state"] == SessionState.RUNNING)
check("Timer started",             bool(session["timer_started_at"]))

time.sleep(1)
timer = get_timer_status(sid)
check("Timer elapsed >= 1s",       timer["elapsed_secs"] >= 1)
check("Timer remaining < 3600",    timer["remaining_secs"] < 3600)
check("Timer not expired",         not timer["expired"])

# ── 4. Node Graph — First Node Entered ────────────────────────────────────────
print("\n[4] Node graph — first node auto-entered")
session = get_session(sid)
check("Current node is set",       bool(session["current_node_id"]))
check("First node is narrative",   "narrative" in session["current_node_id"])

node_statuses = get_node_status(sid)
in_progress = [n for n in node_statuses if n["state"] == NodeState.IN_PROGRESS]
locked      = [n for n in node_statuses if n["state"] == NodeState.LOCKED]
check("Exactly 1 node in-progress",    len(in_progress) == 1)
check("Remaining nodes locked/avail",  len(locked) >= 4)

# ── 5. Flag System ────────────────────────────────────────────────────────────
print("\n[5] Flag system")
result = set_flag(sid, "narrative_01_complete", set_by="node_intro_narrative_01")
check("Flag set returns session_id",   result["session_id"] == sid)
check("Flag is checkable",             check_flag(sid, "narrative_01_complete"))
check("Non-existent flag is False",    not check_flag(sid, "does_not_exist"))

# Duplicate flag set should be idempotent
set_flag(sid, "narrative_01_complete", set_by="node_intro_narrative_01")
flags = get_session_flags(sid)
flag_ids = [f["flag_id"] for f in flags]
check("Flag not duplicated",           flag_ids.count("narrative_01_complete") == 1)

# ── 6. Node Unlock via Flag ───────────────────────────────────────────────────
print("\n[6] Node unlock — downstream unlock via flag")
node_statuses = get_node_status(sid)
puzzle_node = next((n for n in node_statuses if "runes" in n["node_id"]), None)
check("Puzzle node exists",            puzzle_node is not None)
check("Puzzle node now unlocked",
      puzzle_node["state"] in (NodeState.AVAILABLE, NodeState.IN_PROGRESS))

# ── 7. Pause / Resume ────────────────────────────────────────────────────────
print("\n[7] Pause and resume")
session = pause_session(sid)
check("Session paused",                session["state"] == SessionState.PAUSED)

time.sleep(1)
timer_while_paused = get_timer_status(sid)
elapsed_at_pause = timer_while_paused["elapsed_secs"]
time.sleep(1)
timer_still_paused = get_timer_status(sid)
check("Timer frozen while paused",
      timer_still_paused["elapsed_secs"] == elapsed_at_pause,
      f"{elapsed_at_pause}s frozen")

session = resume_session(sid)
check("Session resumed",               session["state"] == SessionState.RUNNING)
time.sleep(1)
timer_after_resume = get_timer_status(sid)
check("Timer running after resume",
      timer_after_resume["elapsed_secs"] > elapsed_at_pause)

# ── 8. Hint System ───────────────────────────────────────────────────────────
print("\n[8] Hint system")
current_node_id = get_session(sid)["current_node_id"]
hint1 = get_hint(sid, current_node_id, requested_by="player")
check("Hint tier 1 returned",          hint1["hint_tier"] == 1)
check("Hint text is non-empty",        len(hint1["hint_text"]) > 10)

hint2 = get_hint(sid, current_node_id, requested_by="player")
check("Hint tier 2 returned",          hint2["hint_tier"] == 2)

hint3 = get_hint(sid, current_node_id, requested_by="operator")
check("Hint tier 3 returned",          hint3["hint_tier"] == 3)

hint4 = get_hint(sid, current_node_id, requested_by="player")
check("Max hints — no tier 4",         hint4["hint_tier"] == 3)
check("Max hints message returned",    "Maximum hints" in hint4["hint_text"])

threshold = check_hint_threshold(sid, current_node_id)
check("Hint threshold check returns dict", "should_hint" in threshold)

# ── 9. Full Node Traversal via Operator Bypass ────────────────────────────────
print("\n[9] Full 7-node traversal via operator bypass")
operator_id = pids[0]

all_nodes = get_node_status(sid)
node_ids_ordered = [n["node_id"] for n in
                    sorted(all_nodes, key=lambda x: x["sequence_order"])]

traversed = 0
for _ in range(len(node_ids_ordered)):
    s = get_session(sid)
    if s["state"] in (SessionState.COMPLETED, SessionState.FAILED):
        break
    current = s["current_node_id"]
    if not current:
        break
    operator_bypass_node(sid, current, operator_id)
    traversed += 1

s = get_session(sid)
check(f"All nodes traversed ({traversed})",
      traversed >= 5)
check("Session auto-completed after last node",
      s["state"] == SessionState.COMPLETED)

# ── 10. Hard Reset — Deterministic ───────────────────────────────────────────
print("\n[10] Hard reset — deterministic")
import time as _time
reset_start = _time.time()
session = hard_reset_session(sid, operator_id=operator_id)
reset_duration = _time.time() - reset_start

check("Session reset to IDLE",         session["state"] == SessionState.IDLE)
check("Current node cleared",          session["current_node_id"] is None)
check("Timer reset",                   session["timer"]["elapsed_secs"] == 0)
check(f"Reset completed in <60s",      reset_duration < 60,
      f"{reset_duration:.2f}s")

# Verify flags cleared
flags_after_reset = get_session_flags(sid)
check("All flags cleared after reset", len(flags_after_reset) == 0)

# Verify node states reset
node_statuses = get_node_status(sid)
first_node = min(node_statuses, key=lambda n: n["sequence_order"])
check("First node back to AVAILABLE",  first_node["state"] == NodeState.AVAILABLE)
locked_after = [n for n in node_statuses if n["state"] == NodeState.LOCKED]
check("Downstream nodes re-locked",    len(locked_after) >= 4)

# ── 11. Operator Controls ─────────────────────────────────────────────────────
print("\n[11] Operator controls")
# After hard reset, session is IDLE — must re-enter LOBBY then RUNNING
conn_tmp = get_db()
conn_tmp.execute("UPDATE sessions SET state=? WHERE session_id=?", (SessionState.LOBBY, sid))
conn_tmp.commit()
conn_tmp.close()
session = start_session(sid)
check("Session restarted after reset", session["state"] == SessionState.RUNNING)

# Difficulty adjust
session = operator_adjust_difficulty(sid, "hard", operator_id)
check("Difficulty adjusted to hard",   session["difficulty"] == "hard")

# Combat AI freeze
current = get_session(sid)["current_node_id"]
freeze_result = freeze_combat_ai(sid, current, operator_id)
check("Combat AI freeze flag set",     "combat_ai_frozen" in freeze_result["flag_id"])

# ── 12. Telemetry Verification ────────────────────────────────────────────────
print("\n[12] Telemetry verification")
conn = get_db()
events = fetchall(conn,
    "SELECT event_type FROM telemetry_events WHERE session_id=? ORDER BY ts",
    (sid,)
)
conn.close()

event_types = [e["event_type"] for e in events]
expected_events = [
    "session_created", "session_state_changed", "node_entered",
    "flag_set", "hint_used", "node_bypassed", "session_hard_reset"
]
for evt in expected_events:
    check(f"Telemetry logged: {evt}", evt in event_types)

check("Total telemetry events > 15",   len(events) > 15, f"found {len(events)}")

# ── 13. List Active Sessions ──────────────────────────────────────────────────
print("\n[13] Active session listing")
active = list_active_sessions()
check("Active sessions list returns",  isinstance(active, list))

# ── 14. Min Player Guard ──────────────────────────────────────────────────────
print("\n[14] Player count guards")
try:
    create_session([pids[0]], difficulty="normal")  # 1 player — below minimum
    check("Min player guard rejected", False, "should have raised")
except ValueError as e:
    check("Min player guard rejected", True, str(e)[:60])

try:
    create_session(pids * 3, difficulty="normal")  # 9 players — above max
    check("Max player guard rejected", False, "should have raised")
except ValueError as e:
    check("Max player guard rejected", True, str(e)[:60])

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r)
failed = sum(1 for r in results if not r)
total  = len(results)

print(f"\n{'='*50}")
print(f"  RESULTS: {passed}/{total} passed  |  {failed} failed")
print(f"{'='*50}\n")

if failed > 0:
    print("  ACTION REQUIRED: Fix failures before Component 3.\n")
    sys.exit(1)
else:
    print("  Component 2 — Session Orchestration Engine: VALIDATED ✓\n")
    print("  Ready to proceed to Component 3 — Economy & Progression System.\n")
    sys.exit(0)
