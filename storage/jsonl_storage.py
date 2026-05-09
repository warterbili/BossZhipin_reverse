"""JSONL 行存储 —— 默认后端。每个 table 一个文件，每行一条 JSON。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ._base import Storage, register


@register("jsonl")
class JsonlStorage(Storage):
    def __init__(self, root: str | Path = "./data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, table: str) -> Path:
        return self.root / f"{table}.jsonl"

    def write(self, table: str, record: dict[str, Any]) -> None:
        record = {"_ts": int(time.time() * 1000), **record}
        with self._path(table).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self, table: str, limit: int = 100, **filters) -> list[dict[str, Any]]:
        p = self._path(table)
        if not p.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if filters and not all(rec.get(k) == v for k, v in filters.items()):
                continue
            items.append(rec)
        return items[-limit:]
