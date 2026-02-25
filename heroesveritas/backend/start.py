"""
HEROES' VERITAS — Combined startup
Runs REST API and WebSocket server in a single process.
REST API runs in main thread, WebSocket server runs in background thread.
Railway only needs one service, one PORT, one container, one shared SQLite DB.

WebSocket is exposed on PORT+1 (Railway sets PORT for the main web service).
For the POC, both servers share the same process and the same DB connection pool.
"""

import os
import sys
import threading

# Ensure backend root is on path
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from db.connection import get_db

# Seed the database on first start
def ensure_seeded():
    try:
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM node_definitions").fetchone()[0]
        conn.close()
        if count == 0:
            print("  Seeding database...")
            import db.seed as seed
            seed.run_seed()
    except Exception:
        print("  Running seed script...")
        try:
            import db.seed as seed
            seed.run_seed()
        except Exception as e:
            print(f"  Seed warning: {e}")

ensure_seeded()

# Start WebSocket server in background thread
ws_port = int(os.environ.get("PORT", 8000)) + 1

def start_ws():
    from services.websocket_server import WebSocketServer
    print(f"  WebSocket server starting on port {ws_port}")
    WebSocketServer(host="0.0.0.0", port=ws_port).start().serve_forever()

ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# Start REST API in main thread
from operator_api import _run_server
_run_server()
