import sqlite3

from bot.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite database.

    row_factory = sqlite3.Row lets us read columns by name (row["title"])
    instead of by numeric position (row[3]) -- more readable and robust to
    column-order changes.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON") # enforices FKs + on delete cascade 
    return conn

def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY, 
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title       TEXT NOT NULL,
            company     TEXT,
            description TEXT,
            url         TEXT,
            location    TEXT,
            fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
            status TEXT NOT NULL DEFAULT('new') CHECK(status IN ('new','scored','notified','skipped','seen')),
            UNIQUE(source, external_id)     
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tele_chat_id TEXT NOT NULL UNIQUE,
            keywords TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            sent_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, job_id)
        )
        """
    )
    conn.commit()
    conn.close()

def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?",(key,)).fetchone()
    return row["value"] if row else None

def set_meta(conn, key, value):
    conn.execute(
        """
        INSERT INTO meta(key,value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key,value)
    )