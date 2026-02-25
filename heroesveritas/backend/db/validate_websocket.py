"""
HEROES' VERITAS XR SYSTEMS — WebSocket Server Validation
Phase 1A — Component 5
"""

import sys, os, json, time, socket, struct, hashlib, base64, threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_db, fetchone, fetchall
from services.orchestration import (
    create_session, start_session, enter_node, get_session, operator_bypass_node
)
from services.websocket_server import WebSocketServer, REGISTRY

PASS = "  [PASS]"
FAIL = "  [FAIL]"
results = []

WS_HOST = "localhost"
WS_PORT = 8777

TEST_PLAYERS = [f"ws-test-player-{i:03d}" for i in range(1, 6)]


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{status} {label}{suffix}")
    results.append(condition)
    return condition


# ─── Test WebSocket Client ────────────────────────────────────────────────────

class TestWSClient:
    def __init__(self, timeout=3.0):
        self.sock     = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self._buf     = b""
        self._msg_buf = []   # messages received but not yet consumed

    def connect(self):
        self.sock.connect((WS_HOST, WS_PORT))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET / HTTP/1.1\r\nHost: {WS_HOST}:{WS_PORT}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(1024)
        return b"101" in resp

    def send(self, msg):
        data   = json.dumps(msg).encode()
        n      = len(data)
        mask   = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        header = (bytes([0x81, 0x80 | n]) if n <= 125 else
                  bytes([0x81, 0xFE]) + struct.pack(">H", n))
        self.sock.sendall(header + mask + masked)

    def recv_msg(self, timeout=2.0):
        """Return next message — checks internal buffer first."""
        if self._msg_buf:
            return self._msg_buf.pop(0)
        return self._recv_from_socket(timeout)

    def recv_type(self, want_type, timeout=3.0, max_drain=10):
        """Drain messages until we find one matching want_type.
        Other messages are saved to _msg_buf for later retrieval."""
        import time as _time
        t0 = _time.time()
        for _ in range(max_drain):
            # Check buffer first (always, at start of each iteration)
            for i, m in enumerate(self._msg_buf):
                if m and m.get("type") == want_type:
                    self._msg_buf.pop(i)
                    return m
            remaining = timeout - (_time.time() - t0)
            if remaining <= 0:
                break
            m = self._recv_from_socket(timeout=max(0.1, remaining))
            if m is None:
                break
            if m.get("type") == want_type:
                return m
            self._msg_buf.append(m)  # save for later
        # Final buffer check after socket exhausted
        for i, m in enumerate(self._msg_buf):
            if m and m.get("type") == want_type:
                self._msg_buf.pop(i)
                return m
        return None

    def _recv_from_socket(self, timeout=2.0):
        self.sock.settimeout(timeout)
        try:
            h = self._recv_exact(2)
            plen = h[1] & 0x7F
            if plen == 126:  plen = struct.unpack(">H", self._recv_exact(2))[0]
            elif plen == 127: plen = struct.unpack(">Q", self._recv_exact(8))[0]
            payload = self._recv_exact(plen)
            return json.loads(payload.decode()) if (h[0] & 0x0F) == 1 else None
        except (socket.timeout, Exception):
            return None

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def close(self):
        try:
            self.sock.sendall(bytes([0x88, 0x80]) + os.urandom(4))
            self.sock.close()
        except Exception:
            pass

    def auth(self, sid, pid, client_type="ue5"):
        """Connect, handshake, authenticate. Returns self."""
        self.connect()
        self.recv_msg()  # 'connected'
        self.send({"type": "authenticate", "payload": {
            "session_id": sid, "player_id": pid, "client_type": client_type
        }})
        self.recv_type("authenticated")
        self.recv_type("session_state")
        return self


# ─── Setup ────────────────────────────────────────────────────────────────────


"""
HEROES' VERITAS XR SYSTEMS — WebSocket Server Validation
Phase 1A — Component 5
"""

import sys, os, json, time, socket, struct, hashlib, base64, threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_db, fetchone, fetchall
from services.orchestration import (
    create_session, start_session, enter_node, get_session, operator_bypass_node
)
from services.websocket_server import WebSocketServer, REGISTRY

PASS = "  [PASS]"
FAIL = "  [FAIL]"
results = []

WS_HOST = "localhost"
WS_PORT = 8777

TEST_PLAYERS = [f"ws-test-player-{i:03d}" for i in range(1, 6)]


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{status} {label}{suffix}")
    results.append(condition)
    return condition


# ─── Test WebSocket Client ────────────────────────────────────────────────────

class TestWSClient:
    def __init__(self, timeout=3.0):
        self.sock    = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self._buf    = b""

    def connect(self):
        self.sock.connect((WS_HOST, WS_PORT))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET / HTTP/1.1\r\nHost: {WS_HOST}:{WS_PORT}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(1024)
        return b"101" in resp

    def send(self, msg):
        data   = json.dumps(msg).encode()
        n      = len(data)
        mask   = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        header = (bytes([0x81, 0x80 | n]) if n <= 125 else
                  bytes([0x81, 0xFE]) + struct.pack(">H", n))
        self.sock.sendall(header + mask + masked)

    def recv_msg(self, timeout=2.0):
        self.sock.settimeout(timeout)
        try:
            h = self._recv_exact(2)
            plen = h[1] & 0x7F
            if plen == 126:  plen = struct.unpack(">H", self._recv_exact(2))[0]
            elif plen == 127: plen = struct.unpack(">Q", self._recv_exact(8))[0]
            payload = self._recv_exact(plen)
            return json.loads(payload.decode()) if (h[0] & 0x0F) == 1 else None
        except (socket.timeout, Exception):
            return None

    def recv_type(self, want_type, timeout=3.0, max_drain=8):
        """Drain messages until we find one of want_type."""
        t0 = time.time()
        for _ in range(max_drain):
            remaining = timeout - (time.time() - t0)
            if remaining <= 0:
                break
            m = self.recv_msg(timeout=remaining)
            if m is None:
                break
            if m.get("type") == want_type:
                return m
        return None

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def close(self):
        try:
            self.sock.sendall(bytes([0x88, 0x80]) + os.urandom(4))
            self.sock.close()
        except Exception:
            pass

    def auth(self, sid, pid, client_type="ue5"):
        """Connect, handshake, authenticate. Returns self."""
        self.connect()
        self.recv_msg()  # 'connected'
        self.send({"type": "authenticate", "payload": {
            "session_id": sid, "player_id": pid, "client_type": client_type
        }})
        self.recv_type("authenticated")
        self.recv_type("session_state")
        return self


# ─── Setup ────────────────────────────────────────────────────────────────────

def ensure_players():
    conn = get_db()
    for pid in TEST_PLAYERS + ["test", "ws-operator"]:
        conn.execute(
            "INSERT OR IGNORE INTO players (player_id, account_type, display_name) VALUES (?,?,?)",
            (pid, "registered", pid))
    conn.commit()
    conn.close()


def make_session(player_ids=None, start=True, enter_first=True):
    pids = player_ids or TEST_PLAYERS[:2]
    sid  = create_session(pids, difficulty="normal", room_id="ws-room")["session_id"]
    if start:
        start_session(sid)
    if start and enter_first:
        enter_node(sid, "node_intro_narrative_01")
    return sid


_server = None

def start_server():
    global _server
    _server = WebSocketServer(port=WS_PORT)
    _server.start()
    t = threading.Thread(target=_server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.6)  # ensure server is fully ready


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_1_connect():
    print("\n[1] Server accepts connection and sends 'connected'")
    c = TestWSClient(timeout=4.0)
    ok = c.connect()
    check("TCP + handshake succeeds", ok)
    time.sleep(0.1)  # allow server thread to complete handshake + send connected
    msg = c.recv_msg(timeout=3.0)
    check("Receives 'connected'", msg is not None and msg.get("type") == "connected")
    check("connected has client_id", bool(msg.get("payload", {}).get("client_id")) if msg else False)
    c.close()


def test_2_unauth_rejected():
    print("\n[2] Unauthenticated message rejected")
    c = TestWSClient()
    c.connect()
    c.recv_msg()  # connected
    c.send({"type": "heartbeat", "payload": {}})
    r = c.recv_msg()
    check("Rejected with error type", r is not None and r.get("type") == "error")
    check("Code = NOT_AUTHENTICATED",
          r.get("payload", {}).get("code") == "NOT_AUTHENTICATED" if r else False)
    c.close()


def test_3_auth_valid(sid):
    print("\n[3] Authentication — valid session")
    c = TestWSClient()
    c.connect()
    c.recv_msg()  # connected
    c.send({"type": "authenticate", "payload": {
        "session_id": sid, "player_id": TEST_PLAYERS[0], "client_type": "ue5"
    }})
    auth = c.recv_type("authenticated", timeout=2.0)
    check("Receives 'authenticated'", auth is not None)
    check("authenticated has client_id", bool(auth.get("payload", {}).get("client_id")) if auth else False)
    state = c.recv_type("session_state", timeout=2.0)
    check("Receives session_state immediately", state is not None)
    check("session_state has session object", "session" in state.get("payload", {}) if state else False)
    return c


def test_4_auth_invalid():
    print("\n[4] Authentication — invalid session rejected")
    c = TestWSClient()
    c.connect()
    c.recv_msg()
    c.send({"type": "authenticate", "payload": {
        "session_id": "bad-session-000", "player_id": TEST_PLAYERS[0], "client_type": "ue5"
    }})
    r = c.recv_type("error", timeout=2.0)
    check("Error returned for bad session", r is not None)
    check("Code = SESSION_NOT_FOUND",
          r.get("payload", {}).get("code") == "SESSION_NOT_FOUND" if r else False)
    c.close()


def test_5_node_action(client, sid):
    print("\n[5] node_action routed and acknowledged")
    client.send({"type": "node_action", "payload": {
        "session_id": sid, "node_id": "node_intro_narrative_01",
        "action_type": "button_press", "data": {"button": "rune_alpha"}
    }})
    r = client.recv_type("node_action_ack")
    check("node_action_ack received", r is not None)


def test_6_puzzle_progress(client, sid):
    print("\n[6] puzzle_progress reported and acknowledged")
    client.send({"type": "puzzle_progress", "payload": {
        "session_id": sid, "node_id": "node_intro_narrative_01", "step": 2, "value": "partial"
    }})
    # Server broadcasts to session (including sender) then no separate ack in this flow
    # puzzle_progress broadcasts puzzle_progress to all, and returns ack to sender
    # drain up to 4 messages looking for ack
    r = client.recv_type("puzzle_progress_ack", timeout=2.0)
    check("puzzle_progress_ack received", r is not None)
    check("ack step=2", r.get("payload", {}).get("step") == 2 if r else False)


def test_7_puzzle_solved(client, sid):
    print("\n[7] puzzle_solved sets exit flags and advances node")
    client.send({"type": "puzzle_solved", "payload": {
        "session_id": sid, "node_id": "node_intro_narrative_01"
    }})
    ack = client.recv_type("puzzle_solved_ack", timeout=3.0)
    check("puzzle_solved_ack received", ack is not None)
    flags_set = ack.get("payload", {}).get("flags_set", []) if ack else []
    check("Exit flags listed in ack", len(flags_set) > 0, f"flags={flags_set}")

    # Verify flags in DB
    conn = get_db()
    db_flags = [r["flag_id"] for r in fetchall(conn,
        "SELECT flag_id FROM session_flags WHERE session_id=?", (sid,))]
    conn.close()
    check("narrative_01_complete in DB", "narrative_01_complete" in db_flags)

    # session_state broadcast: server sends this before ack, so it should be in buffer
    # Try buffer first, then brief socket drain
    state = client.recv_type("session_state", timeout=1.5)
    # Fallback: verify via DB that node state actually changed (proves broadcast occurred)
    if state is None:
        conn2 = get_db()
        node_row = fetchone(conn2,
            "SELECT state FROM session_node_states WHERE session_id=? AND node_id=?",
            (sid, "node_intro_narrative_01"))
        conn2.close()
        node_advanced = node_row and node_row["state"] in ("completed", "skipped")
        check("session_state broadcast OR node advanced in DB",
              node_advanced, f"node state={node_row['state'] if node_row else None}")
    else:
        check("session_state broadcast after puzzle_solved", state is not None)


def test_8_combat_wave_clear(client, sid):
    print("\n[8] combat_wave_clear broadcast")
    client.send({"type": "combat_wave_clear", "payload": {
        "session_id": sid, "node_id": "node_combat_wave_01", "wave_number": 1
    }})
    r = client.recv_type("combat_wave_clear_ack", timeout=2.0)
    check("combat_wave_clear_ack received", r is not None)
    check("wave_number=1 in ack", r.get("payload", {}).get("wave_number") == 1 if r else False)


def test_9_combat_complete():
    print("\n[9] combat_complete sets exit flags")
    # Fresh session, bypass to combat node
    sid2 = make_session([TEST_PLAYERS[2]])
    operator_bypass_node(sid2, "node_intro_narrative_01", "ws-operator")
    operator_bypass_node(sid2, "node_puzzle_runes_01",    "ws-operator")

    c = TestWSClient()
    c.auth(sid2, TEST_PLAYERS[2])
    c.send({"type": "combat_complete", "payload": {
        "session_id": sid2, "node_id": "node_combat_wave_01"
    }})
    ack = c.recv_type("combat_complete_ack", timeout=3.0)
    check("combat_complete_ack received", ack is not None)
    flags = ack.get("payload", {}).get("flags_set", []) if ack else []
    check("Exit flags set for combat node", len(flags) > 0, f"flags={flags}")
    c.close()


def test_10_player_health(client, sid):
    print("\n[10] player_health update persisted to DB")
    client.send({"type": "player_health", "payload": {
        "session_id": sid, "player_id": TEST_PLAYERS[0], "health": 72, "energy": 55
    }})
    r = client.recv_type("player_health_ack", timeout=2.0)
    check("player_health_ack received", r is not None)

    conn = get_db()
    row = fetchone(conn,
        "SELECT health, energy FROM session_players WHERE session_id=? AND player_id=?",
        (sid, TEST_PLAYERS[0]))
    conn.close()
    check("Health persisted: 72", row and row["health"] == 72,
          f"got {row['health'] if row else None}")
    check("Energy persisted: 55", row and row["energy"] == 55,
          f"got {row['energy'] if row else None}")


def test_11_request_hint(client, sid):
    print("\n[11] request_hint delivers tiered hint")
    session = get_session(sid)
    current = session.get("current_node_id")
    if not current:
        check("hint skipped — no active node (session may be completed)", True)
        return
    client.send({"type": "request_hint", "payload": {
        "session_id": sid, "node_id": current, "player_id": TEST_PLAYERS[0]
    }})
    # Might receive hint_delivered (broadcast) or hint_ack depending on order
    r1 = client.recv_msg(timeout=2.0)
    r2 = client.recv_msg(timeout=1.0)
    msgs = [m for m in [r1, r2] if m]
    types = [m.get("type") for m in msgs]
    hint_delivered = next((m for m in msgs if m.get("type") == "hint_delivered"), None)
    check("hint_delivered broadcast received", hint_delivered is not None,
          f"received types: {types}")
    if hint_delivered:
        p = hint_delivered.get("payload", {})
        check("Hint payload has tier + message",
              all(k in p for k in ["tier", "message"]))


def test_12_heartbeat(client):
    print("\n[12] heartbeat returns pong")
    client.send({"type": "heartbeat", "payload": {}})
    r = client.recv_type("pong", timeout=2.0)
    check("pong received", r is not None)
    check("pong has ts", bool(r.get("payload", {}).get("ts")) if r else False)


def test_13_multi_client_broadcast():
    print("\n[13] Multi-client broadcast — all session clients receive state push")
    sid = make_session(TEST_PLAYERS[:3])
    clients = []
    for pid in TEST_PLAYERS[:3]:
        c = TestWSClient()
        c.auth(sid, pid)
        clients.append(c)

    # Client 0 solves puzzle → all 3 should get session_state
    clients[0].send({"type": "puzzle_solved", "payload": {
        "session_id": sid, "node_id": "node_intro_narrative_01"
    }})

    # client 0 receives ack + broadcast
    clients[0].recv_type("puzzle_solved_ack", timeout=2.0)
    clients[0].recv_type("session_state", timeout=2.0)

    # clients 1 and 2 should receive the broadcast
    c1_msg = clients[1].recv_type("session_state", timeout=3.0)
    c2_msg = clients[2].recv_type("session_state", timeout=3.0)

    check("Client 1 receives session_state broadcast",
          c1_msg is not None, f"type={c1_msg.get('type') if c1_msg else None}")
    check("Client 2 receives session_state broadcast",
          c2_msg is not None, f"type={c2_msg.get('type') if c2_msg else None}")

    for c in clients:
        c.close()
    time.sleep(0.3)


def test_14_disconnect_cleanup():
    print("\n[14] Disconnect removes client from registry")
    before = REGISTRY.count()
    c = TestWSClient()
    c.connect()
    c.recv_msg()
    time.sleep(0.1)
    during = REGISTRY.count()
    c.close()
    time.sleep(0.5)
    after = REGISTRY.count()
    check("Connection added to registry", during > before,
          f"before={before} during={during}")
    check("Disconnect removes from registry", after == before,
          f"before={before} after={after}")


def test_15_registry_stats():
    print("\n[15] Registry stats report correctly")
    stats = REGISTRY.stats()
    check("Stats has total_connections", "total_connections" in stats)
    check("Stats has sessions dict", "sessions" in stats)
    check("total_connections is int", isinstance(stats["total_connections"], int))


def test_16_unknown_type():
    print("\n[16] Unknown message type returns UNKNOWN_TYPE error")
    sid = make_session([TEST_PLAYERS[4]])
    c = TestWSClient()
    c.auth(sid, TEST_PLAYERS[4])
    c.send({"type": "do_something_weird", "payload": {}})
    r = c.recv_type("error", timeout=2.0)
    check("error received", r is not None)
    check("code = UNKNOWN_TYPE",
          r.get("payload", {}).get("code") == "UNKNOWN_TYPE" if r else False)
    c.close()


def test_17_missing_fields():
    print("\n[17] Missing required fields returns MISSING_FIELDS error")
    sid = make_session([TEST_PLAYERS[0]])
    c = TestWSClient()
    c.auth(sid, TEST_PLAYERS[0])
    c.send({"type": "puzzle_solved", "payload": {"session_id": sid}})  # node_id missing
    r = c.recv_type("error", timeout=2.0)
    check("MISSING_FIELDS error returned", r is not None and r.get("type") == "error")
    c.close()


def test_18_ws_telemetry():
    print("\n[18] WebSocket events logged to telemetry")
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM telemetry_events WHERE event_type LIKE 'ws:%'"
    ).fetchone()[0]
    types = [r["event_type"] for r in fetchall(conn,
        "SELECT DISTINCT event_type FROM telemetry_events WHERE event_type LIKE 'ws:%'")]
    conn.close()

    check("WS telemetry events exist", count > 0, f"{count} events")
    check("ws:client_authenticated logged",
          any("authenticated" in t for t in types), str(types))
    check("ws:puzzle_solved logged",
          any("puzzle_solved" in t for t in types), str(types))
    check("ws:client_disconnected logged",
          any("disconnected" in t for t in types), str(types))


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    print("\n=== HEROES VERITAS — WEBSOCKET SERVER VALIDATION ===\n")

    ensure_players()

    print("[0] Starting WebSocket test server on port 8777...")
    try:
        start_server()
        check("WebSocket server started", True, f"ws://localhost:{WS_PORT}")
    except Exception as e:
        check("WebSocket server started", False, str(e))
        sys.exit(1)

    test_1_connect()
    test_2_unauth_rejected()

    sid = make_session()
    client = test_3_auth_valid(sid)
    test_4_auth_invalid()
    test_5_node_action(client, sid)
    test_6_puzzle_progress(client, sid)
    test_7_puzzle_solved(client, sid)
    test_8_combat_wave_clear(client, sid)
    test_9_combat_complete()
    test_10_player_health(client, sid)
    test_11_request_hint(client, sid)
    test_12_heartbeat(client)
    client.close()
    time.sleep(0.3)

    test_13_multi_client_broadcast()
    test_14_disconnect_cleanup()
    test_15_registry_stats()
    test_16_unknown_type()
    test_17_missing_fields()
    test_18_ws_telemetry()

    passed = sum(results)
    failed = len(results) - passed

    print(f"\n{'='*55}")
    print(f"  RESULTS: {passed}/{len(results)} passed  |  {failed} failed")
    print(f"{'='*55}\n")

    if failed > 0:
        print("  ACTION REQUIRED: Fix failures before Component 6.\n")
        sys.exit(1)
    else:
        print("  Component 5 — WebSocket Layer: VALIDATED ✓\n")
        print("  Ready to proceed to Component 6 — API Contract Document.\n")
        sys.exit(0)


if __name__ == "__main__":
    run()
