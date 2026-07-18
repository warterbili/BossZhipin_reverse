"""数据处理管道 —— 所有数据流的统一事件钩子。

用法（写在 pipelines/ 下任意 .py 文件）:

    from pipelines import on

    @on("record", table="boss_jobs")
    def filter_low_salary(record):
        if parse_salary(record.get("salaryDesc")) < 20:
            return None  # 返回 None 表示丢弃这条
        return record

    @on("record")  # 不限 table, 所有 record 事件都过这里
    def add_timestamp(record):
        import time
        record["_processed_at"] = time.time()
        return record

    @on("capture")
    def webhook_capture(record):
        # 比如: 推到自己的日志系统
        import requests
        requests.post("http://my-server/log", json=record, timeout=2)
        return record

    @on("greet:after")
    def notify_slack(result):
        if result.get("ok"):
            requests.post("https://hooks.slack.com/...", json={"text": result})
        return result

当前实际触发的事件:
  record            存储前，用 table="boss_jobs" 等过滤
  capture           mitm 抓到一条新请求
  <operation>:after 业务操作完成，如 greet:after / search:after
"""
from __future__ import annotations

import importlib
import pkgutil
import threading
import traceback
from typing import Any, Callable

# 注册表: event -> [(filter_kwargs, fn)]
_HOOKS: dict[str, list[tuple[dict, Callable]]] = {}
_LOAD_LOCK = threading.Lock()
_LOADED = False


def on(event: str, **match_filter):
    """装饰器: 注册一个事件处理器。

    Args:
        event: 事件名 (record / capture / greet:after ...)
        match_filter: 可选的 kwargs 过滤，比如 table="boss_jobs"
    """
    def deco(fn):
        _HOOKS.setdefault(event, []).append((match_filter, fn))
        return fn
    return deco


def emit(event: str, **kwargs) -> Any:
    """触发事件，依次跑所有匹配的处理器。

    Args:
        event: 事件名（也会跑 'event:*' 的兜底处理器）
        **kwargs: 会传给处理器；其中如果有 'record' 或 'data' key，
                  且某 hook 返回值不为 None 时，新值替换原值（管道传递）

    返回最终的 kwargs (dict)。
    """
    for ev in (event, event.split(":", 1)[0] + ":*", "*"):
        for match_filter, fn in _HOOKS.get(ev, []):
            # 检查 filter 匹配
            if not all(kwargs.get(k) == v for k, v in match_filter.items()):
                continue
            try:
                # hook 函数签名: 单参数 (record/result) 或 关键字
                # 我们传 kwargs 主体（record / data 等）
                main = kwargs.get("record") or kwargs.get("data") or kwargs.get("result") or kwargs
                ret = fn(main)
                # None: 丢弃 / dict: 替换
                if ret is None and ("record" in kwargs or "data" in kwargs):
                    return None
                if isinstance(ret, dict):
                    if "record" in kwargs:
                        kwargs["record"] = ret
                    elif "data" in kwargs:
                        kwargs["data"] = ret
                    elif "result" in kwargs:
                        kwargs["result"] = ret
            except Exception:
                # 单个 hook 出错不影响其它
                traceback.print_exc()
    return kwargs


def load_all() -> None:
    """扫描 pipelines/ 下所有 .py 文件，触发它们的 @on 装饰器。"""
    global _LOADED
    with _LOAD_LOCK:
        if _LOADED:
            return
        _LOADED = True

    pkg = importlib.import_module("pipelines")
    for _f, name, is_pkg in pkgutil.iter_modules(pkg.__path__):
        if name.startswith("_"):
            continue
        try:
            importlib.import_module(f"pipelines.{name}")
        except Exception as e:
            print(f"[pipeline] load fail {name}: {e}")
            traceback.print_exc()


def list_hooks() -> list[dict]:
    """看当前注册了哪些 hook，给 UI 用。"""
    out = []
    for event, items in _HOOKS.items():
        for filt, fn in items:
            out.append({
                "event": event,
                "filter": filt,
                "func": getattr(fn, "__name__", str(fn)),
                "module": getattr(fn, "__module__", "?"),
                "doc": (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "",
            })
    return out


__all__ = ["on", "emit", "load_all", "list_hooks"]
