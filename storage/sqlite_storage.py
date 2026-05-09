"""SQLite storage —— 落表查询用得上时切到这个。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ._base import Storage, register


@register("sqlite")
class SqliteStorage(Storage):
    def __init__(self, path: str | Path = "./data.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS records "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            " table_name TEXT NOT NULL, ts INTEGER NOT NULL, "
            " data TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_table_ts "
            "ON records(table_name, ts DESC)"
        )

    def write(self, table: str, record: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO records(table_name, ts, data) VALUES (?, ?, ?)",
            (table, int(time.time() * 1000), json.dumps(record, ensure_ascii=False)),
        )
        self._conn.commit()

    def read(self, table: str, limit: int = 100, **filters) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT ts, data FROM records WHERE table_name = ? "
            "ORDER BY ts DESC LIMIT ?", (table, limit),
        )
        out: list[dict[str, Any]] = []
        for ts, raw in cur:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if filters and not all(rec.get(k) == v for k, v in filters.items()):
                continue
            out.append({"_ts": ts, **rec})
        return out

    def close(self) -> None:
        self._conn.close()
