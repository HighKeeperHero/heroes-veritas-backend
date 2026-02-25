"""
HEROES' VERITAS XR SYSTEMS — WebSocket Server
Phase 1A — Component 5

Architecture:
  - Pure Python stdlib WebSocket server (no external deps)
  - Runs alongside the REST API (different port: 8001)
  - All UE5.5 clients connect here for real-time state sync
  - Operator dashboard also connects for live push (no polling needed)

Message Protocol:
  All messages are JSON. Every message has:
    { "type": "<MESSAGE_TYPE>", "payload": {...} }

Client → Server (UE5.5 sends):
  authenticate      { session_id, player_id, client_type }
  node_action       { session_id, node_id, action_type, data }
  puzzle_progress   { session_id, node_id, step, value }
  puzzle_solved     { session_id, node_id }
  combat_wave_clear { session_id, node_id, wave_number }
  combat_complete   { session_id, node_id }
  player_health     { session_id, player_id, health, energy }
  request_hint      { session_id, node_id, player_id }
  heartbeat         { session_id, player_id }

Server → Client (backend pushes):
  authenticated     { client_id, session_id, player_id }
  session_state     { session } — full session snapshot
  state_changed     { session_id, old_state, new_state }
  node_entered      { session_id, node_id, node_type, display_name }
  node_completed    { session_id, node_id }
  flag_set          { session_id, flag_id, set_by }
  hint_delivered    { session_id, node_id, tier, type, message }
  timer_sync        { session_id, elapsed_secs, time_remaining_secs }
  player_update     { session_id, player_id, health, energy }
  session_complete  { session_id, summary }
  error             { code, message }
  pong              { ts }
"""

import json
import uuid
import socket
import struct
import hashlib
import base64
import threading
import time
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from db.connection import get_db, fetchone, fetchall
from services.orchestration import (
    get_session, start_session, pause_session, resume_session,
    set_flag, enter_node, request_hint,
    operator_bypass_node, hard_reset_session,
)
from services.economy import generate_session_summary

WS_PORT = 8001
HEARTBEAT_INTERVAL = 15   # seconds — send timer_sync to all clients
HEARTBEAT_TIMEOUT  = 45   # seconds — disconnect silent clients

# ─────────────────────────────────────────────────────────────────────────────
# Connection Registry
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionRegistry:
    """
    Thread-safe registry of all active WebSocket connections.
    Indexed by: client_id, session_id, player_id
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._clients = {}   # client_id → ClientConn

    def register(self, conn):
        with self._lock:
            self._clients[conn.client_id] = conn

    def unregister(self, client_id):
        with self._lock:
            self._clients.pop(client_id, None)

    def get(self, client_id):
        with self._lock:
            return self._clients.get(client_id)

    def get_by_session(self, session_id):
        with self._lock:
            return [c for c in self._clients.values()
                    if c.session_id == session_id]

    def get_all(self):
        with self._lock:
            return list(self._clients.values())

    def count(self):
        with self._lock:
            return len(self._clients)

    def stats(self):
        with self._lock:
            sessions = {}
            for c in self._clients.values():
                if c.session_id:
                    sessions.setdefault(c.session_id, []).append(c.player_id)
            return {
                "total_connections": len(self._clients),
                "sessions": sessions,
            }


REGISTRY = ConnectionRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Handshake & Frame Codec
# ─────────────────────────────────────────────────────────────────────────────

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def do_handshake(sock):
    """Perform HTTP→WebSocket upgrade handshake. Returns True on success."""
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                return False
            data += chunk

        request = data.decode("utf-8", errors="replace")
        key = None
        for line in request.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
                break

        if not key:
            return False

        accept = base64.b64encode(
            hashlib.sha1((key + WS_MAGIC).encode()).digest()
        ).decode()

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        sock.sendall(response.encode())
        return True
    except Exception:
        return False


def decode_frame(sock):
    """
    Decode a single WebSocket frame from socket.
    Returns (opcode, payload_bytes) or raises on disconnect/error.
    """
    header = _recv_exact(sock, 2)
    if not header or len(header) < 2:
        raise ConnectionError("Connection closed")

    fin    = (header[0] & 0x80) != 0
    opcode = header[0] & 0x0F
    masked = (header[1] & 0x80) != 0
    plen   = header[1] & 0x7F

    if plen == 126:
        plen = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif plen == 127:
        plen = struct.unpack(">Q", _recv_exact(sock, 8))[0]

    mask_key = _recv_exact(sock, 4) if masked else None
    payload  = _recv_exact(sock, plen)

    if masked and mask_key:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    return opcode, payload


def encode_frame(data: bytes, opcode: int = 0x01) -> bytes:
    """Encode data as a WebSocket frame (server-side, unmasked)."""
    length = len(data)
    if length <= 125:
        header = bytes([0x80 | opcode, length])
    elif length <= 65535:
        header = bytes([0x80 | opcode, 126]) + struct.pack(">H", length)
    else:
        header = bytes([0x80 | opcode, 127]) + struct.pack(">Q", length)
    return header + data


def _recv_exact(sock, n):
    """Receive exactly n bytes from socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed during recv")
        buf += chunk
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# Client Connection
# ─────────────────────────────────────────────────────────────────────────────

class ClientConn:
    """Represents one connected WebSocket client (UE5.5 headset or dashboard)."""

    def __init__(self, sock, addr):
        self.sock        = sock
        self.addr        = addr
        self.client_id   = str(uuid.uuid4())
        self.session_id  = None
        self.player_id   = None
        self.client_type = "unknown"   # 'ue5', 'operator', 'dashboard'
        self.authenticated = False
        self.last_seen   = time.time()
        self._send_lock  = threading.Lock()

    def send(self, msg: dict):
        """Thread-safe JSON message send."""
        try:
            data = json.dumps(msg, default=str).encode("utf-8")
            frame = encode_frame(data)
            with self._send_lock:
                self.sock.sendall(frame)
            return True
        except Exception:
            return False

    def close(self):
        try:
            # Send close frame
            frame = encode_frame(b"", opcode=0x08)
            with self._send_lock:
                self.sock.sendall(frame)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Broadcast Utilities
# ─────────────────────────────────────────────────────────────────────────────

def broadcast_to_session(session_id: str, msg: dict, exclude_client: str = None):
    """Send message to all clients connected to a session."""
    for conn in REGISTRY.get_by_session(session_id):
        if conn.client_id != exclude_client:
            conn.send(msg)


def broadcast_session_state(session_id: str):
    """Push full session snapshot to all session clients."""
    session = get_session(session_id)
    if not session:
        return
    broadcast_to_session(session_id, {
        "type":    "session_state",
        "payload": {"session": session}
    })


# ─────────────────────────────────────────────────────────────────────────────
# Message Handlers
# ─────────────────────────────────────────────────────────────────────────────

def handle_authenticate(conn: ClientConn, payload: dict) -> dict:
    """
    Authenticate a client connection to a session.
    Must be the first message sent after WebSocket connect.
    """
    session_id  = payload.get("session_id")
    player_id   = payload.get("player_id")
    client_type = payload.get("client_type", "ue5")

    if not session_id or not player_id:
        return error_msg("AUTH_MISSING", "session_id and player_id required")

    session = get_session(session_id)
    if not session:
        return error_msg("SESSION_NOT_FOUND", f"Session {session_id} not found")

    conn.session_id   = session_id
    conn.player_id    = player_id
    conn.client_type  = client_type
    conn.authenticated = True

    _log_ws_event("client_authenticated", session_id, player_id,
                  {"client_type": client_type, "client_id": conn.client_id})

    # Push full current state immediately on auth
    conn.send({
        "type": "authenticated",
        "payload": {
            "client_id":   conn.client_id,
            "session_id":  session_id,
            "player_id":   player_id,
            "client_type": client_type,
        }
    })
    conn.send({
        "type":    "session_state",
        "payload": {"session": session}
    })

    return None   # response already sent directly


def handle_node_action(conn: ClientConn, payload: dict) -> dict:
    """Generic node interaction from UE5.5 (button press, item placement, etc.)"""
    session_id  = payload.get("session_id")
    node_id     = payload.get("node_id")
    action_type = payload.get("action_type")
    data        = payload.get("data", {})

    if not all([session_id, node_id, action_type]):
        return error_msg("MISSING_FIELDS", "session_id, node_id, action_type required")

    _log_ws_event("node_action", session_id, conn.player_id,
                  {"node_id": node_id, "action_type": action_type, "data": data})

    broadcast_to_session(session_id, {
        "type": "node_action_received",
        "payload": {
            "session_id":  session_id,
            "node_id":     node_id,
            "player_id":   conn.player_id,
            "action_type": action_type,
            "data":        data,
        }
    }, exclude_client=conn.client_id)

    return ok_msg("node_action_ack", {
        "session_id":  session_id,
        "node_id":     node_id,
        "action_type": action_type,
    })


def handle_puzzle_progress(conn: ClientConn, payload: dict) -> dict:
    """UE5.5 reports incremental puzzle progress (step N completed)."""
    session_id = payload.get("session_id")
    node_id    = payload.get("node_id")
    step       = payload.get("step")
    value      = payload.get("value")

    if not all([session_id, node_id, step is not None]):
        return error_msg("MISSING_FIELDS", "session_id, node_id, step required")

    _log_ws_event("puzzle_progress", session_id, conn.player_id,
                  {"node_id": node_id, "step": step, "value": value})

    # Broadcast progress to all clients in session (show on operator dashboard)
    broadcast_to_session(session_id, {
        "type": "puzzle_progress",
        "payload": {
            "session_id": session_id,
            "node_id":    node_id,
            "player_id":  conn.player_id,
            "step":       step,
            "value":      value,
        }
    })

    return ok_msg("puzzle_progress_ack", {"step": step})


def handle_puzzle_solved(conn: ClientConn, payload: dict) -> dict:
    """
    UE5.5 reports puzzle solved. Backend sets exit flags → auto-advances node.
    """
    session_id = payload.get("session_id")
    node_id    = payload.get("node_id")

    if not session_id or not node_id:
        return error_msg("MISSING_FIELDS", "session_id and node_id required")

    # Look up what flags this node's exit produces
    conn_db = get_db()
    node_def = fetchone(conn_db,
        "SELECT exit_conditions_json, display_name FROM node_definitions WHERE node_id=?",
        (node_id,))
    conn_db.close()

    if not node_def:
        return error_msg("NODE_NOT_FOUND", f"Node {node_id} not found")

    exit_flags = json.loads(node_def["exit_conditions_json"] or "[]")

    # Set all exit flags — orchestration engine auto-advances
    for flag in exit_flags:
        set_flag(session_id, flag, f"ue5:{conn.player_id}")

    _log_ws_event("puzzle_solved", session_id, conn.player_id,
                  {"node_id": node_id, "flags_set": exit_flags})

    # Push updated state to all clients
    broadcast_session_state(session_id)

    return ok_msg("puzzle_solved_ack", {
        "session_id": session_id,
        "node_id":    node_id,
        "flags_set":  exit_flags,
    })


def handle_combat_wave_clear(conn: ClientConn, payload: dict) -> dict:
    """UE5.5 reports a combat wave has been cleared."""
    session_id  = payload.get("session_id")
    node_id     = payload.get("node_id")
    wave_number = payload.get("wave_number", 1)

    if not session_id or not node_id:
        return error_msg("MISSING_FIELDS", "session_id and node_id required")

    _log_ws_event("combat_wave_clear", session_id, conn.player_id,
                  {"node_id": node_id, "wave_number": wave_number})

    broadcast_to_session(session_id, {
        "type": "combat_wave_cleared",
        "payload": {
            "session_id":  session_id,
            "node_id":     node_id,
            "wave_number": wave_number,
        }
    })

    return ok_msg("combat_wave_clear_ack", {"wave_number": wave_number})


def handle_combat_complete(conn: ClientConn, payload: dict) -> dict:
    """UE5.5 reports combat node fully completed. Sets exit flags."""
    session_id = payload.get("session_id")
    node_id    = payload.get("node_id")

    if not session_id or not node_id:
        return error_msg("MISSING_FIELDS", "session_id and node_id required")

    conn_db = get_db()
    node_def = fetchone(conn_db,
        "SELECT exit_conditions_json FROM node_definitions WHERE node_id=?",
        (node_id,))
    conn_db.close()

    if not node_def:
        return error_msg("NODE_NOT_FOUND", f"Node {node_id} not found")

    exit_flags = json.loads(node_def["exit_conditions_json"] or "[]")
    for flag in exit_flags:
        set_flag(session_id, flag, f"ue5:{conn.player_id}")

    _log_ws_event("combat_complete", session_id, conn.player_id,
                  {"node_id": node_id, "flags_set": exit_flags})

    broadcast_session_state(session_id)

    return ok_msg("combat_complete_ack", {
        "session_id": session_id,
        "node_id":    node_id,
        "flags_set":  exit_flags,
    })


def handle_player_health(conn: ClientConn, payload: dict) -> dict:
    """UE5.5 reports player health/energy update (combat damage, healing)."""
    session_id = payload.get("session_id")
    player_id  = payload.get("player_id", conn.player_id)
    health     = payload.get("health")
    energy     = payload.get("energy")

    if not session_id or health is None:
        return error_msg("MISSING_FIELDS", "session_id and health required")

    conn_db = get_db()
    updates = []
    params  = []
    if health is not None:
        updates.append("health=?"); params.append(int(health))
    if energy is not None:
        updates.append("energy=?"); params.append(int(energy))

    if updates:
        params.extend([session_id, player_id])
        conn_db.execute(
            f"UPDATE session_players SET {', '.join(updates)} "
            f"WHERE session_id=? AND player_id=?",
            params
        )
        conn_db.commit()
    conn_db.close()

    _log_ws_event("player_health_update", session_id, player_id,
                  {"health": health, "energy": energy})

    broadcast_to_session(session_id, {
        "type": "player_update",
        "payload": {
            "session_id": session_id,
            "player_id":  player_id,
            "health":     health,
            "energy":     energy,
        }
    })

    return ok_msg("player_health_ack", {"health": health, "energy": energy})


def handle_request_hint(conn: ClientConn, payload: dict) -> dict:
    """UE5.5 player manually requests a hint."""
    session_id = payload.get("session_id")
    node_id    = payload.get("node_id")
    player_id  = payload.get("player_id", conn.player_id)

    if not session_id or not node_id:
        return error_msg("MISSING_FIELDS", "session_id and node_id required")

    try:
        hint = request_hint(session_id, node_id, player_id=player_id)
    except Exception as e:
        return error_msg("HINT_ERROR", str(e))

    _log_ws_event("hint_requested", session_id, player_id,
                  {"node_id": node_id, "tier": hint["tier"]})

    # Broadcast hint to all clients in session
    broadcast_to_session(session_id, {
        "type": "hint_delivered",
        "payload": {
            "session_id": session_id,
            "node_id":    node_id,
            "tier":       hint["tier"],
            "type":       hint["type"],
            "message":    hint["message"],
        }
    })

    return ok_msg("hint_ack", {"tier": hint["tier"]})


def handle_heartbeat(conn: ClientConn, payload: dict) -> dict:
    """Client keepalive. Returns pong with server timestamp."""
    conn.last_seen = time.time()
    return {
        "type":    "pong",
        "payload": {"ts": datetime.now(timezone.utc).isoformat()}
    }


# ─────────────────────────────────────────────────────────────────────────────
# Message Router
# ─────────────────────────────────────────────────────────────────────────────

HANDLERS = {
    "authenticate":       handle_authenticate,
    "node_action":        handle_node_action,
    "puzzle_progress":    handle_puzzle_progress,
    "puzzle_solved":      handle_puzzle_solved,
    "combat_wave_clear":  handle_combat_wave_clear,
    "combat_complete":    handle_combat_complete,
    "player_health":      handle_player_health,
    "request_hint":       handle_request_hint,
    "heartbeat":          handle_heartbeat,
}

def route_message(conn: ClientConn, raw: str):
    """Parse and dispatch incoming message. Returns response dict or None."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return error_msg("PARSE_ERROR", "Invalid JSON")

    msg_type = msg.get("type")
    payload  = msg.get("payload", {})

    if not msg_type:
        return error_msg("NO_TYPE", "Message must have a 'type' field")

    # Gate: require authentication before any other message
    if msg_type != "authenticate" and not conn.authenticated:
        return error_msg("NOT_AUTHENTICATED",
                         "Send 'authenticate' message first")

    handler = HANDLERS.get(msg_type)
    if not handler:
        return error_msg("UNKNOWN_TYPE", f"Unknown message type: {msg_type}")

    try:
        return handler(conn, payload)
    except Exception as e:
        _log_ws_event("handler_error", conn.session_id, conn.player_id,
                      {"type": msg_type, "error": str(e)})
        return error_msg("HANDLER_ERROR", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Client Thread
# ─────────────────────────────────────────────────────────────────────────────

def handle_client(sock, addr):
    """
    Per-client thread. Handles the full lifecycle of one WebSocket connection.
    """
    if not do_handshake(sock):
        sock.close()
        return

    conn = ClientConn(sock, addr)
    REGISTRY.register(conn)

    # Send welcome
    conn.send({
        "type": "connected",
        "payload": {
            "client_id": conn.client_id,
            "server":    "Heroes Veritas WS v1.0",
            "ts":        datetime.now(timezone.utc).isoformat(),
        }
    })

    try:
        while True:
            opcode, payload_bytes = decode_frame(sock)

            # Ping → Pong
            if opcode == 0x09:
                sock.sendall(encode_frame(payload_bytes, opcode=0x0A))
                continue

            # Close frame
            if opcode == 0x08:
                break

            # Text frame
            if opcode == 0x01:
                conn.last_seen = time.time()
                raw      = payload_bytes.decode("utf-8", errors="replace")
                response = route_message(conn, raw)
                if response:
                    conn.send(response)

    except (ConnectionError, OSError):
        pass
    finally:
        REGISTRY.unregister(conn.client_id)
        _log_ws_event("client_disconnected", conn.session_id, conn.player_id,
                      {"client_id": conn.client_id, "client_type": conn.client_type})
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Timer Sync & Heartbeat Loop
# ─────────────────────────────────────────────────────────────────────────────

def timer_sync_loop():
    """
    Background thread. Every HEARTBEAT_INTERVAL seconds:
      - Push timer_sync to all clients in running sessions
      - Disconnect clients that haven't sent in HEARTBEAT_TIMEOUT seconds
    """
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        now = time.time()

        # Disconnect stale clients
        stale = [c for c in REGISTRY.get_all()
                 if (now - c.last_seen) > HEARTBEAT_TIMEOUT]
        for conn in stale:
            _log_ws_event("client_timeout", conn.session_id, conn.player_id, {})
            REGISTRY.unregister(conn.client_id)
            conn.close()

        # Push timer sync to running sessions
        seen_sessions = set()
        for conn in REGISTRY.get_all():
            if conn.session_id and conn.session_id not in seen_sessions:
                seen_sessions.add(conn.session_id)
                session = get_session(conn.session_id)
                if session and session.get("state") == "running":
                    broadcast_to_session(conn.session_id, {
                        "type": "timer_sync",
                        "payload": {
                            "session_id":         conn.session_id,
                            "elapsed_secs":       session.get("elapsed_secs", 0),
                            "time_remaining_secs": session.get("time_remaining_secs", 0),
                        }
                    })


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Server
# ─────────────────────────────────────────────────────────────────────────────

class WebSocketServer:

    def __init__(self, host="", port=WS_PORT):
        self.host  = host
        self.port  = port
        self._sock = None
        self._running = False

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(50)
        self._running = True

        # Start timer sync thread
        t = threading.Thread(target=timer_sync_loop, daemon=True)
        t.start()

        print(f"  WebSocket server listening on ws://localhost:{self.port}")
        return self

    def accept_one(self, timeout=0.5):
        """Accept one connection (non-blocking with timeout). Returns True if accepted."""
        self._sock.settimeout(timeout)
        try:
            sock, addr = self._sock.accept()
            sock.settimeout(None)
            t = threading.Thread(target=handle_client, args=(sock, addr), daemon=True)
            t.start()
            return True
        except socket.timeout:
            return False
        except Exception:
            return False

    def serve_forever(self):
        try:
            while self._running:
                self.accept_one(timeout=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    @property
    def running(self):
        return self._running


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def ok_msg(msg_type: str, data: dict) -> dict:
    return {"type": msg_type, "payload": data}


def error_msg(code: str, message: str) -> dict:
    return {"type": "error", "payload": {"code": code, "message": message}}


def _log_ws_event(event_type: str, session_id, player_id, context: dict):
    try:
        conn_db = get_db()
        conn_db.execute("""
            INSERT INTO telemetry_events
                (event_id, session_id, player_id, event_type, context_json,
                 gameplay_version, config_version, ts)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            str(uuid.uuid4()), session_id, player_id,
            f"ws:{event_type}",
            json.dumps(context),
            "1.0.0", "1.0.0",
            datetime.now(timezone.utc).isoformat()
        ))
        conn_db.commit()
        conn_db.close()
    except Exception:
        pass   # never crash the WS thread on a logging failure


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", WS_PORT))
    print("\n  HEROES VERITAS — WebSocket Server")
    print(f"  ws://0.0.0.0:{port}\n")
    print("  Press Ctrl+C to stop.\n")
    WebSocketServer(host="0.0.0.0", port=port).start().serve_forever()
