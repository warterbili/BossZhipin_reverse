"""CSV 存储 —— Excel 友好（UTF-8 BOM）。每个 table 一个 .csv。"""
from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from ._base import Storage, register


@register("csv")
class CsvStorage(Storage):
    def __init__(self, root: str | Path = "./data/csv"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # 缓存每个 table 已有的 columns，写新行时按列对齐
        self._fieldnames: dict[str, list[str]] = {}

    def _path(self, table: str) -> Path:
        return self.root / f"{table}.csv"

    def _get_fieldnames(self, table: str, sample: dict[str, Any]) -> list[str]:
        """优先用文件已有 header，否则用 sample 的 keys。"""
        if table in self._fieldnames:
            # 增量加新 key
            for k in sample:
                if k not in self._fieldnames[table]:
                    self._fieldnames[table].append(k)
            return self._fieldnames[table]
        p = self._path(table)
        if p.exists() and p.stat().st_size > 0:
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                hdr = next(reader, None) or []
        else:
            hdr = ["_ts"] + [k for k in sample.keys() if k != "_ts"]
        self._fieldnames[table] = hdr
        return hdr

    def _flatten(self, val: Any) -> str:
        """复杂值转字符串（dict/list 用 JSON）。"""
        import json
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        if val is None:
            return ""
        return str(val)

    def write(self, table: str, record: dict[str, Any]) -> None:
        record = {"_ts": int(time.time() * 1000), **record}
        p = self._path(table)
        is_new = not p.exists() or p.stat().st_size == 0

        fieldnames = self._get_fieldnames(table, record)
        # 如果这条记录有新 key，扩展 header（CSV 不支持就地扩展，需要重写头）
        new_keys = [k for k in record if k not in fieldnames]
        if new_keys:
            fieldnames.extend(new_keys)
            self._fieldnames[table] = fieldnames
            # 重写 header（追加旧记录到新表）
            if not is_new:
                old = list(self.read(table, limit=10**9))
                with p.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=fieldnames)
                    w.writeheader()
                    for r in old:
                        w.writerow({k: self._flatten(r.get(k)) for k in fieldnames})
                is_new = False

        with p.open("a", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if is_new:
                w.writeheader()
            w.writerow({k: self._flatten(record.get(k)) for k in fieldnames})

    def read(self, table: str, limit: int = 100, **filters) -> list[dict[str, Any]]:
        p = self._path(table)
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows: list[dict[str, Any]] = []
            for r in reader:
                if filters and not all(str(r.get(k, "")) == str(v) for k, v in filters.items()):
                    continue
                rows.append(r)
        return rows[-limit:]
