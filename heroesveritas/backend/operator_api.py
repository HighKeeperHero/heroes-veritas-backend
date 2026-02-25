"""
HEROES' VERITAS XR SYSTEMS — Operator API Server
Phase 1A — Component 4

Serves:
  - Static dashboard HTML at GET /
  - REST API endpoints consumed by the dashboard
  - All operator control actions from the requirements doc

Run:  python3 operator_api.py
      Then open http://localhost:8000 in your browser
"""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add backend root to path — works whether run as script or module
_backend_root = os.path.dirname(os.path.abspath(__file__))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from db.connection import get_db, fetchall, fetchone
from services.orchestration import (
    create_session, get_session, start_session,
    pause_session, resume_session,
    set_flag, get_flags,
    enter_node, soft_reset_node, hard_reset_session,
    operator_bypass_node, operator_force_fail,
    request_hint,
)
from services.economy import (
    generate_session_summary, get_player_profile,
    get_all_config, update_config,
)

PORT = 8000
OPERATOR_ID = "operator-dashboard-01"

# ── Seed a demo operator player if needed ─────────────────────────────────────
def ensure_operator():
    conn = get_db()
    conn.execute("""
        INSERT OR IGNORE INTO players (player_id, account_type, display_name)
        VALUES (?, 'operator', 'Dashboard Operator')
    """, (OPERATOR_ID,))
    conn.commit()
    conn.close()


# ── Response helpers ──────────────────────────────────────────────────────────
def ok(data):
    return 200, {"status": "ok", "data": data}

def err(msg, code=400):
    return code, {"status": "error", "message": str(msg)}


# ── Route handlers ────────────────────────────────────────────────────────────

def handle_get_sessions(params):
    """GET /api/sessions — list all active/recent sessions"""
    conn = get_db()
    sessions = fetchall(conn, """
        SELECT s.session_id, s.state, s.difficulty, s.room_id,
               s.current_node_id, s.timer_started_at, s.timer_paused_secs,
               s.total_duration_secs, s.created_at, s.completed_at,
               s.gameplay_version, s.config_version,
               COUNT(sp.player_id) as player_count
        FROM sessions s
        LEFT JOIN session_players sp ON s.session_id = sp.session_id
        GROUP BY s.session_id
        ORDER BY s.created_at DESC
        LIMIT 50
    """)
    conn.close()

    # Attach elapsed/remaining to each
    import time
    from datetime import datetime, timezone
    for s in sessions:
        if s["timer_started_at"] and s["state"] == "running":
            started = datetime.fromisoformat(s["timer_started_at"])
            elapsed = int((datetime.now(timezone.utc) - started).total_seconds())
            elapsed -= s.get("timer_paused_secs", 0)
            s["elapsed_secs"] = max(0, elapsed)
            s["time_remaining_secs"] = max(0, s["total_duration_secs"] - elapsed)
        else:
            s["elapsed_secs"] = 0
            s["time_remaining_secs"] = s["total_duration_secs"]
    return ok(sessions)


def handle_get_session(session_id):
    """GET /api/sessions/{id}"""
    s = get_session(session_id)
    if not s:
        return err(f"Session not found: {session_id}", 404)
    return ok(s)


def handle_create_session(body):
    """POST /api/sessions"""
    player_ids = body.get("player_ids", [])
    difficulty  = body.get("difficulty", "normal")
    room_id     = body.get("room_id", "room-01")

    if not player_ids:
        # Auto-generate demo players for the dashboard
        player_ids = [f"demo-player-{i:03d}" for i in range(1, 5)]
        conn = get_db()
        for pid in player_ids:
            conn.execute("""
                INSERT OR IGNORE INTO players (player_id, account_type, display_name)
                VALUES (?, 'guest', ?)
            """, (pid, f"Player {pid[-3:]}"))
        conn.commit()
        conn.close()

    session = create_session(player_ids, difficulty=difficulty,
                              room_id=room_id, operator_id=OPERATOR_ID)
    return ok(session)


def handle_session_action(session_id, action, body):
    """POST /api/sessions/{id}/action"""
    try:
        if action == "start":
            s = start_session(session_id, OPERATOR_ID)
        elif action == "pause":
            s = pause_session(session_id, OPERATOR_ID)
        elif action == "resume":
            s = resume_session(session_id, OPERATOR_ID)
        elif action == "hard_reset":
            s = hard_reset_session(session_id, OPERATOR_ID)
        elif action == "force_fail":
            s = operator_force_fail(session_id, OPERATOR_ID, "operator_dashboard")
        elif action == "bypass_node":
            node_id = body.get("node_id")
            if not node_id:
                return err("node_id required for bypass_node")
            s = operator_bypass_node(session_id, node_id, OPERATOR_ID)
        elif action == "soft_reset_node":
            node_id = body.get("node_id")
            if not node_id:
                return err("node_id required for soft_reset_node")
            s = soft_reset_node(session_id, node_id, OPERATOR_ID)
        elif action == "trigger_hint":
            node_id = body.get("node_id")
            if not node_id:
                return err("node_id required for trigger_hint")
            hint = request_hint(session_id, node_id, forced=True)
            return ok({"hint": hint, "session": get_session(session_id)})
        elif action == "set_flag":
            flag_id = body.get("flag_id")
            if not flag_id:
                return err("flag_id required")
            set_flag(session_id, flag_id, f"operator:{OPERATOR_ID}")
            s = get_session(session_id)
        elif action == "complete":
            conn = get_db()
            conn.execute("""
                UPDATE sessions SET state='completed', completed_at=datetime('now')
                WHERE session_id=?
            """, (session_id,))
            conn.commit()
            conn.close()
            summary = generate_session_summary(session_id)
            return ok({"summary": summary})
        else:
            return err(f"Unknown action: {action}")
        return ok(s)
    except ValueError as e:
        return err(str(e))


def handle_get_telemetry(params):
    """GET /api/telemetry — recent events"""
    conn = get_db()
    limit = int(params.get("limit", ["50"])[0])
    session_id = params.get("session_id", [None])[0]

    if session_id:
        events = fetchall(conn, """
            SELECT * FROM telemetry_events
            WHERE session_id=?
            ORDER BY ts DESC LIMIT ?
        """, (session_id, limit))
    else:
        events = fetchall(conn, """
            SELECT * FROM telemetry_events
            ORDER BY ts DESC LIMIT ?
        """, (limit,))
    conn.close()
    return ok(events)


def handle_get_analytics(params):
    """GET /api/analytics — investor KPI metrics"""
    conn = get_db()

    total_sessions = conn.execute(
        "SELECT COUNT(*) FROM sessions").fetchone()[0]
    completed = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE state='completed'").fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE state='failed'").fetchone()[0]

    completion_rate = round((completed / total_sessions * 100), 1) if total_sessions else 0

    avg_time = conn.execute("""
        SELECT AVG(
            CAST((julianday(completed_at) - julianday(created_at)) * 86400 AS INTEGER)
        )
        FROM sessions WHERE state='completed' AND completed_at IS NOT NULL
    """).fetchone()[0]

    # XP per session
    xp_events = fetchall(conn, """
        SELECT context_json FROM telemetry_events
        WHERE event_type='xp_granted'
    """)
    total_xp = 0
    for e in xp_events:
        try:
            ctx = json.loads(e["context_json"] or "{}")
            total_xp += int(ctx.get("xp_earned", 0))
        except Exception:
            pass

    avg_xp = round(total_xp / completed, 1) if completed else 0

    # Difficulty distribution
    diff_rows = fetchall(conn, """
        SELECT difficulty, COUNT(*) as count
        FROM sessions GROUP BY difficulty
    """)
    diff_dist = {r["difficulty"]: r["count"] for r in diff_rows}

    # Drop-off node (most common current_node when session failed)
    dropoff = fetchall(conn, """
        SELECT current_node_id, COUNT(*) as count
        FROM sessions WHERE state='failed' AND current_node_id IS NOT NULL
        GROUP BY current_node_id ORDER BY count DESC LIMIT 1
    """)

    # Recent event type counts
    event_counts = fetchall(conn, """
        SELECT event_type, COUNT(*) as count
        FROM telemetry_events
        GROUP BY event_type ORDER BY count DESC LIMIT 10
    """)

    conn.close()
    return ok({
        "total_sessions":    total_sessions,
        "completed":         completed,
        "failed":            failed,
        "completion_rate":   completion_rate,
        "avg_completion_secs": int(avg_time) if avg_time else 0,
        "avg_xp_per_session": avg_xp,
        "difficulty_distribution": diff_dist,
        "top_dropoff_node":  dropoff[0]["current_node_id"] if dropoff else None,
        "event_type_counts": event_counts,
    })


def handle_get_config(params):
    return ok(get_all_config())


def handle_update_config(body):
    key   = body.get("config_key")
    value = body.get("config_value")
    if not key or value is None:
        return err("config_key and config_value required")
    try:
        result = update_config(key, value, updated_by=OPERATOR_ID)
        return ok(result)
    except ValueError as e:
        return err(str(e))


def handle_get_nodes(params):
    conn = get_db()
    nodes = fetchall(conn, """
        SELECT node_id, node_type, display_name, sequence_order,
               entry_conditions_json, exit_conditions_json
        FROM node_definitions WHERE is_active=1
        ORDER BY sequence_order
    """)
    conn.close()
    return ok(nodes)


def handle_get_operator_log(params):
    conn = get_db()
    limit = int(params.get("limit", ["30"])[0])
    log = fetchall(conn, """
        SELECT * FROM operator_actions
        ORDER BY ts DESC LIMIT ?
    """, (limit,))
    conn.close()
    return ok(log)


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default access log noise

    def _send(self, code, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
            if os.path.exists(dashboard_path):
                with open(dashboard_path, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            else:
                self._send(*err("dashboard.html not found", 404))
            return

        if path == "/api/sessions":
            self._send(*handle_get_sessions(params))
        elif path.startswith("/api/sessions/") and path.endswith("/telemetry"):
            sid = path.split("/")[3]
            self._send(*handle_get_telemetry({"session_id": [sid], "limit": ["50"]}))
        elif path.startswith("/api/sessions/"):
            sid = path.split("/")[3]
            self._send(*handle_get_session(sid))
        elif path == "/api/telemetry":
            self._send(*handle_get_telemetry(params))
        elif path == "/api/analytics":
            self._send(*handle_get_analytics(params))
        elif path == "/api/config":
            self._send(*handle_get_config(params))
        elif path == "/api/nodes":
            self._send(*handle_get_nodes(params))
        elif path == "/api/operator-log":
            self._send(*handle_get_operator_log(params))
        elif path == "/api/health":
            self._send(*ok({"status": "healthy", "version": "1.0.0"}))
        else:
            self._send(*err("Not found", 404))

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        body   = self._read_body()

        if path == "/api/sessions":
            self._send(*handle_create_session(body))
        elif path.startswith("/api/sessions/") and "/action/" in path:
            parts  = path.split("/")
            sid    = parts[3]
            action = parts[5]
            self._send(*handle_session_action(sid, action, body))
        elif path == "/api/config":
            self._send(*handle_update_config(body))
        else:
            self._send(*err("Not found", 404))


# ── Entry Point ───────────────────────────────────────────────────────────────

def _run_server():
    ensure_operator()
    port = int(os.environ.get("PORT", PORT))
    print(f"\n  HEROES VERITAS — Operator API Server")
    print(f"  Running at http://0.0.0.0:{port}")
    print(f"  Dashboard: http://0.0.0.0:{port}/")
    print(f"  API base:  http://0.0.0.0:{port}/api/\n")
    print(f"  Press Ctrl+C to stop.\n")
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")

if __name__ == "__main__":
    _run_server()
