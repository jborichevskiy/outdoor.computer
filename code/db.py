"""SQLite helpers. All readers and writers go through here so the schema-init
path stays in one place.

Design: a single connection per process (SQLite handles concurrent readers fine;
WAL mode lets pollers and the web app write without blocking each other).
"""

import sqlite3
import time
from pathlib import Path

from config import DB_PATH

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect() -> sqlite3.Connection:
    """Open or create the DB, initialize schema, enable WAL."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def insert_sample(
    conn: sqlite3.Connection,
    source: str,
    metric: str,
    value_num: float | None = None,
    value_text: str | None = None,
    ts: int | None = None,
) -> None:
    """Add a row to `samples`. Either value_num or value_text (or both) should be set."""
    conn.execute(
        "INSERT INTO samples(ts, source, metric, value_num, value_text) VALUES (?, ?, ?, ?, ?)",
        (ts or int(time.time()), source, metric, value_num, value_text),
    )


def log_event(conn: sqlite3.Connection, kind: str, details: str = "") -> None:
    """Add a row to `events` — for status transitions, poller errors, startups."""
    conn.execute(
        "INSERT INTO events(ts, kind, details) VALUES (?, ?, ?)",
        (int(time.time()), kind, details),
    )


def latest_sample(
    conn: sqlite3.Connection, source: str, metric: str
) -> tuple[int, float | None, str | None] | None:
    """Most recent sample for a (source, metric). Returns (ts, value_num, value_text) or None."""
    row = conn.execute(
        "SELECT ts, value_num, value_text FROM samples "
        "WHERE source=? AND metric=? ORDER BY ts DESC LIMIT 1",
        (source, metric),
    ).fetchone()
    return row  # type: ignore[return-value]


def series(
    conn: sqlite3.Connection, source: str, metric: str, since_seconds: int
) -> list[tuple[int, float | None]]:
    """All (ts, value_num) rows for a metric in the last `since_seconds` seconds."""
    cutoff = int(time.time()) - since_seconds
    return list(
        conn.execute(
            "SELECT ts, value_num FROM samples WHERE source=? AND metric=? AND ts > ? "
            "ORDER BY ts",
            (source, metric, cutoff),
        )
    )
