"""Saves and queries command history (shown on the History page in Phase 9).

Respects privacy.save_history: when it's false, nothing is written.
Note the "?" placeholders in the SQL: values are passed separately, never pasted into
the SQL text. That prevents "SQL injection" - a spoken phrase can't change the query.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from services.database_service import Database


@dataclass
class HistoryEntry:
    id: int
    created_at: str
    input_text: str
    input_mode: str
    source: str
    intents: list
    reply: str
    status: str


class HistoryService:
    def __init__(self, db: Database, enabled: bool = True):
        self.db = db
        self.enabled = enabled

    def add(self, input_text: str, input_mode: str, source: str, intents: list[dict], reply: str, status: str) -> None:
        if not self.enabled:
            return
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO command_history (created_at, input_text, input_mode, source, intents, reply, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), input_text, input_mode, source,
                 json.dumps(intents), reply, status),
            )

    def recent(self, limit: int = 50, search: str | None = None) -> list[HistoryEntry]:
        sql = "SELECT * FROM command_history"
        args: list = []
        if search:
            sql += " WHERE input_text LIKE ? OR reply LIKE ?"
            args += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.db.transaction() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [HistoryEntry(**{**dict(r), "intents": json.loads(r["intents"])}) for r in rows]

    def clear(self) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM command_history")
