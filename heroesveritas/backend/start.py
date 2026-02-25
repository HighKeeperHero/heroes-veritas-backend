"""
HEROES' VERITAS — Railway entry point
Runs REST API only. WebSocket server is a separate service.
"""
import os
import sys

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

# Start REST API — reads PORT from environment (Railway sets this to 8080)
from operator_api import _run_server
_run_server()
