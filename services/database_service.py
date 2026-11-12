"""SQLite connection management.

SQLite is a full SQL database stored in ONE file, built into Python (import sqlite3).
No server to install - perfect for a desktop app.

Threads: the assistant writes history from its worker thread while the UI may read it.
One connection is shared (check_same_thread=False) and every use is wrapped in a lock,
so only one thread talks to the database at a time.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from utils.constants import DATABASE_DIR

SCHEMA_FILE = DATABASE_DIR / "schema.sql"


class Database:
    def __init__(self, path: Path | str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # rows behave like dicts: row["input_text"]
        self._lock = threading.Lock()
        with self.transaction() as conn:
            conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

    @contextmanager
    def transaction(self):
        """`with db.transaction() as conn:` - commits on success, rolls back on error."""
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()
