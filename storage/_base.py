"""Storage adapter abstract base.

任何"我抓到的数据要往哪存"都通过这里。默认提供 JSONL/SQLite/CSV 三种实现，
用户可以写自己的（HBase/Postgres/Kafka...）注册到 STORAGE_REGISTRY。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable


class Storage(ABC):
    """所有存储后端必须实现的接口。"""

    @abstractmethod
    def write(self, table: str, record: dict[str, Any]) -> None:
        """写一条记录。table 类似数据库表名，比如 'jobs' / 'greetings'。"""
        ...

    def write_batch(self, table: str, records: Iterable[dict[str, Any]]) -> int:
        """批量写。默认实现 = 多次调 write。"""
        n = 0
        for r in records:
            self.write(table, r)
            n += 1
        return n

    @abstractmethod
    def read(self, table: str, limit: int = 100, **filters) -> list[dict[str, Any]]:
        """读最近 N 条。"""
        ...

    def close(self) -> None:
        """关闭底层连接（默认空实现）。"""


# 全局注册表，core/server.py 启动时根据 config 选一个
STORAGE_REGISTRY: dict[str, type[Storage]] = {}


def register(name: str):
    """装饰器，注册一个 storage 实现。"""
    def deco(cls: type[Storage]) -> type[Storage]:
        STORAGE_REGISTRY[name] = cls
        return cls
    return deco
