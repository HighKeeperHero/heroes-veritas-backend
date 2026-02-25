"""
HEROES' VERITAS XR SYSTEMS — DB Connection Manager
Shared across all backend services.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "heroes_veritas.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def fetchone(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def fetchall(conn, sql, params=()):
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
