"""
HEROES' VERITAS — Combined startup
Railway assigns one PORT. REST API uses it.
WebSocket server uses a fixed internal port (8001) — accessible to UE5.5
clients that connect directly, and will be wired via Railway's TCP service
when needed. For POC team testing, only the REST API + dashboard are needed.
"""

import os
import sys
import threading

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Seed database on first start
def ensure_seeded():
    try:
        from db.connection import get_db
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM node_definitions").fetchone()[0]
        conn.close()
        if count == 0:
            raise Exception("empty")
    except Exception:
        try:
            import db.seed as seed
            seed.run_seed()
            print("  Database seeded OK")
        except Exception as e:
            print(f"  Seed warning: {e}")

ensure_seeded()

# WebSocket on fixed port 8001 (internal, not Railway's public PORT)
WS_PORT = 8001

def start_ws():
    try:
        from services.websocket_server import WebSocketServer
        print(f"  WebSocket server starting on ws://0.0.0.0:{WS_PORT}")
        WebSocketServer(host="0.0.0.0", port=WS_PORT).start().serve_forever()
    except Exception as e:
        print(f"  WebSocket server error: {e}")

ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# REST API on Railway's PORT (main thread)
from operator_api import _run_server
_run_server()
