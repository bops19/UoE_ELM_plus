"""SQLite connection helpers shared across app/handlers."""

import os
import sqlite3


def open_sqlite_db(db_file: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
