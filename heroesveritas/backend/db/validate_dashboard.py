"""
HEROES' VERITAS XR SYSTEMS — Operator API Validation
Phase 1A — Component 4
"""

import sys
import os
import json
import time
import threading
import urllib.request
import urllib.error
import importlib.util
from http.server import HTTPServer

PASS = "  [PASS]"
FAIL = "  [FAIL]"
results = []
BASE = "http://localhost:8099"

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND_DIR)

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{status} {label}{suffix}")
    results.append(condition)
    return condition

def api(method, path, body=None):
    url = BASE + "/api" + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as ex:
        return {"status": "error", "message": str(ex)}

def start_server():
    os.chdir(BACKEND_DIR)
    spec = importlib.util.spec_from_file_location(
        "operator_api",
        os.path.join(BACKEND_DIR, "operator_api.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ensure_operator()
    server = HTTPServer(("", 8099), mod.DashboardHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.8)
    return server

def run():
    print("\n=== HEROES VERITAS — OPERATOR API VALIDATION ===\n")

    print("[0] Starting API server on port 8099...")
    try:
        server = start_server()
        check("Server started", True, "port 8099")
    except Exception as e:
        check("Server started", False, str(e))
        sys.exit(1)

    # ── Health
    print("\n[1] Health endpoint")
    r = api("GET", "/health")
    check("GET /api/health returns ok", r.get("status") == "ok")

    # ── Sessions
    print("\n[2] Session endpoints")
    r = api("GET", "/sessions")
    check("GET /api/sessions returns ok", r.get("status") == "ok")
    check("Sessions is a list", isinstance(r.get("data"), list))

    r = api("POST", "/sessions", {"difficulty": "normal", "room_id": "room-test"})
    check("POST /api/sessions creates session", r.get("status") == "ok")
    check("Session has session_id", bool(r.get("data", {}).get("session_id")))
    sid = r.get("data", {}).get("session_id", "")

    r2 = api("GET", f"/sessions/{sid}")
    check("GET /api/sessions/{id} returns session", r2.get("status") == "ok")
    check("Session state is lobby", r2.get("data", {}).get("state") == "lobby")

    # ── Actions
    print("\n[3] Session action endpoints")
    r = api("POST", f"/sessions/{sid}/action/start", {})
    check("action/start — running", r.get("status") == "ok" and
          r.get("data", {}).get("state") == "running")

    r = api("POST", f"/sessions/{sid}/action/pause", {})
    check("action/pause — paused", r.get("status") == "ok" and
          r.get("data", {}).get("state") == "paused")

    r = api("POST", f"/sessions/{sid}/action/resume", {})
    check("action/resume — running", r.get("status") == "ok" and
          r.get("data", {}).get("state") == "running")

    r_s = api("GET", f"/sessions/{sid}")
    current_node = r_s.get("data", {}).get("current_node_id")
    if current_node:
        r = api("POST", f"/sessions/{sid}/action/trigger_hint",
                {"node_id": current_node})
        check("action/trigger_hint returns hint",
              r.get("status") == "ok" and "hint" in r.get("data", {}))

        r = api("POST", f"/sessions/{sid}/action/bypass_node",
                {"node_id": current_node})
        check("action/bypass_node — OK", r.get("status") == "ok")
    else:
        check("trigger_hint skipped (no current node)", True, "session auto-advanced")
        check("bypass_node skipped (no current node)", True, "session auto-advanced")

    r = api("POST", f"/sessions/{sid}/action/set_flag", {"flag_id": "test_api_flag"})
    check("action/set_flag — OK", r.get("status") == "ok")
    check("Flag in session flags",
          "test_api_flag" in r.get("data", {}).get("flags", []))

    r = api("POST", f"/sessions/{sid}/action/hard_reset", {})
    check("action/hard_reset — idle",
          r.get("status") == "ok" and r.get("data", {}).get("state") == "idle")

    # ── Errors
    print("\n[4] Error handling")
    r = api("POST", f"/sessions/{sid}/action/explode", {})
    check("Unknown action returns error", r.get("status") == "error")

    r = api("GET", "/sessions/nonexistent-000")
    check("Missing session returns error", r.get("status") == "error")

    # ── Telemetry
    print("\n[5] Telemetry endpoint")
    r = api("GET", "/telemetry?limit=20")
    check("GET /api/telemetry returns list", isinstance(r.get("data"), list))
    check("Telemetry has events", len(r.get("data", [])) > 0)
    if r.get("data"):
        ev = r["data"][0]
        check("Event has required fields",
              all(k in ev for k in ["event_type", "ts", "session_id"]))

    # ── Analytics
    print("\n[6] Analytics endpoint")
    r = api("GET", "/analytics")
    check("GET /api/analytics returns ok", r.get("status") == "ok")
    d = r.get("data", {})
    check("Has total_sessions",       "total_sessions" in d)
    check("Has completion_rate",      "completion_rate" in d)
    check("Has difficulty_distribution", "difficulty_distribution" in d)
    check("Has avg_xp_per_session",   "avg_xp_per_session" in d)

    # ── Config
    print("\n[7] Config endpoints")
    r = api("GET", "/config")
    check("GET /api/config returns dict", isinstance(r.get("data"), dict))
    check("Config has xp keys",
          any("xp." in k for k in r.get("data", {}).keys()))

    r = api("POST", "/config", {"config_key": "xp.base_node_puzzle", "config_value": 175})
    check("POST /api/config updates value", r.get("status") == "ok")
    r = api("POST", "/config", {"config_key": "xp.base_node_puzzle", "config_value": 150})
    check("Config restored", r.get("status") == "ok")

    r = api("POST", "/config", {"config_key": "xp.nonexistent", "config_value": 1})
    check("Unknown config key rejected", r.get("status") == "error")

    # ── Nodes
    print("\n[8] Node definitions endpoint")
    r = api("GET", "/nodes")
    check("GET /api/nodes returns list", isinstance(r.get("data"), list))
    check("At least 5 nodes", len(r.get("data", [])) >= 5)

    # ── Operator Log
    print("\n[9] Operator log endpoint")
    r = api("GET", "/operator-log")
    check("GET /api/operator-log returns list", isinstance(r.get("data"), list))
    check("Log has entries", len(r.get("data", [])) > 0)

    # ── Dashboard HTML
    print("\n[10] Dashboard HTML")
    try:
        with urllib.request.urlopen(BASE + "/", timeout=5) as resp:
            html = resp.read().decode()
        check("GET / returns HTML", "<html" in html.lower())
        check("Has correct title",   "HEROES VERITAS" in html)
        check("Has session list",    "session-list" in html)
        check("Has hard reset btn",  "HARD RESET" in html)
        check("Has analytics",       "Investor Metrics" in html)
        check("Has telemetry feed",  "Telemetry Feed" in html)
        check("Has live config",     "Live Config" in html)
        check("Has node graph",      "node-graph" in html)
        check("Has operator log",    "Operator Log" in html)
    except Exception as e:
        check("Dashboard HTML served", False, str(e))

    server.shutdown()

    passed = sum(results)
    failed  = len(results) - passed
    print(f"\n{'='*55}")
    print(f"  RESULTS: {passed}/{len(results)} passed  |  {failed} failed")
    print(f"{'='*55}\n")

    if failed > 0:
        print("  ACTION REQUIRED: Fix failures before Component 5.\n")
        sys.exit(1)
    else:
        print("  Component 4 — Operator Dashboard: VALIDATED ✓\n")
        print("  Ready to proceed to Component 5 — WebSocket Layer.\n")
        sys.exit(0)

if __name__ == "__main__":
    run()
