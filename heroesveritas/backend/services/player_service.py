"""
HEROES' VERITAS XR SYSTEMS — Player Service
Minimal account creation for Phase 1A.
"""

import uuid
import datetime
from db.connection import get_db, fetchone


def _now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"


def create_player(display_name: str, account_type: str = "registered",
                  email: str = None) -> dict:
    conn = get_db()
    player_id = str(uuid.uuid4())

    conn.execute("""
        INSERT INTO players (player_id, account_type, display_name, email, created_at, updated_at)
        VALUES (?,?,?,?,?,?)
    """, (player_id, account_type, display_name, email, _now_iso(), _now_iso()))

    conn.execute("""
        INSERT INTO player_profiles (player_id, total_xp, current_level, updated_at)
        VALUES (?,0,1,?)
    """, (player_id, _now_iso()))

    conn.commit()
    player = fetchone(conn, "SELECT * FROM players WHERE player_id=?", (player_id,))
    conn.close()
    return dict(player)


def get_player(player_id: str) -> dict:
    conn = get_db()
    player = fetchone(conn, "SELECT * FROM players WHERE player_id=?", (player_id,))
    conn.close()
    if not player:
        raise ValueError(f"Player not found: {player_id}")
    return player
