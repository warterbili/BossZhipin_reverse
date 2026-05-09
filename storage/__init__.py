"""存储后端 —— 通过 STORAGE_REGISTRY 插件式扩展。

内置:
  jsonl  (默认, 无依赖)
  sqlite (无依赖, 标准库)
  csv    (无依赖, 用 utf-8-sig 让 Excel 正确显示中文)
  excel  (需要 openpyxl)
  mysql  (需要 pymysql)

写自己的:
  在 storage/ 下放个 .py，用 @register("name") 装饰类，重启即可。
"""
from ._base import Storage, STORAGE_REGISTRY, register
# 触发注册（按依赖大小排序）
from . import jsonl_storage  # noqa: F401
from . import sqlite_storage  # noqa: F401
from . import csv_storage  # noqa: F401
# 可选依赖：导入失败不阻断启动
try:
    from . import excel_storage  # noqa: F401
except Exception:
    pass
try:
    from . import mysql_storage  # noqa: F401
except Exception:
    pass


def get_storage(name: str = "jsonl", **kwargs) -> Storage:
    cls = STORAGE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown storage: {name}. available: {list(STORAGE_REGISTRY)}")
    return cls(**kwargs)


def list_backends() -> list[str]:
    return list(STORAGE_REGISTRY.keys())


__all__ = ["Storage", "get_storage", "list_backends", "register"]
