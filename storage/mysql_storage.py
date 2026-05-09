"""MySQL 存储 —— 需要 pymysql，可选依赖。

  pip install pymysql

每个 table 自动建表。所有非主键字段塞 JSON 列方便扩展。
"""
from __future__ import annotations

import json
import time
from typing import Any

from ._base import Storage, register


@register("mysql")
class MysqlStorage(Storage):
    def __init__(self, host: str = "127.0.0.1", port: int = 3306,
                 user: str = "root", password: str = "",
                 database: str = "mitm_rpc",
                 charset: str = "utf8mb4"):
        try:
            import pymysql
        except ImportError:
            raise RuntimeError(
                "MysqlStorage 需要 pymysql，安装: pip install pymysql"
            )
        self._pymysql = pymysql
        self._cfg = dict(host=host, port=port, user=user,
                         password=password, database=database,
                         charset=charset, autocommit=True)
        # 建库 + 检查连接
        self._ensure_db()
        self._tables_created: set[str] = set()

    def _ensure_db(self) -> None:
        cfg = dict(self._cfg)
        db = cfg.pop("database")
        with self._pymysql.connect(**cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` "
                            f"CHARACTER SET {cfg['charset']}")

    def _conn(self):
        return self._pymysql.connect(**self._cfg)

    def _ensure_table(self, table: str) -> None:
        if table in self._tables_created:
            return
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS `{table}` ("
                "`id` BIGINT AUTO_INCREMENT PRIMARY KEY, "
                "`ts` BIGINT NOT NULL, "
                "`data` JSON NOT NULL, "
                "INDEX `idx_ts` (`ts` DESC)"
                f") CHARACTER SET {self._cfg['charset']}"
            )
        self._tables_created.add(table)

    def write(self, table: str, record: dict[str, Any]) -> None:
        self._ensure_table(table)
        ts = record.pop("_ts", int(time.time() * 1000))
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO `{table}` (`ts`, `data`) VALUES (%s, %s)",
                (ts, json.dumps(record, ensure_ascii=False)),
            )

    def read(self, table: str, limit: int = 100, **filters) -> list[dict[str, Any]]:
        self._ensure_table(table)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT ts, data FROM `{table}` ORDER BY ts DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        out: list[dict[str, Any]] = []
        for ts, raw in rows:
            try:
                rec = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, json.JSONDecodeError):
                rec = {}
            if filters and not all(rec.get(k) == v for k, v in filters.items()):
                continue
            out.append({"_ts": ts, **rec})
        return out
