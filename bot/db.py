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
    return conn


def init_db() -> None:
    conn = get_connection()
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
    conn.commit()
    conn.close()
