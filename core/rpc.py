"""Browser ↔ Python RPC 协议层。

任务流：
   Python.BrowserSession.fetch(...)
       ↓ post /rpc/req
   FastAPI 把任务塞进 _queue
       ↓ browser fetch /rpc/poll
   浏览器执行 op → post /rpc/result/{id}
       ↓
   /rpc/req 的 Future 被 set_result，Python 拿到响应
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


class RpcBus:
    """单实例：管理 task 队列 + 等待中的 Future。可以多浏览器 tab 接，一起消费。"""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.pending: dict[str, asyncio.Future] = {}
        # 统计
        self.stats = {"req": 0, "ok": 0, "err": 0, "timeout": 0}

    async def send(self, op: str, timeout: float = 25.0, **payload) -> dict:
        """Python 侧调用：发任务并等浏览器返回。"""
        task_id = uuid.uuid4().hex[:12]
        body = {"id": task_id, "op": op, **payload}
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self.pending[task_id] = fut
        await self.queue.put(body)
        self.stats["req"] += 1
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            if isinstance(result, dict) and result.get("ok") is False:
                self.stats["err"] += 1
            else:
                self.stats["ok"] += 1
            return result
        except asyncio.TimeoutError:
            self.pending.pop(task_id, None)
            self.stats["timeout"] += 1
            raise HTTPException(status_code=504, detail="browser RPC timeout")
        except asyncio.CancelledError:
            self.pending.pop(task_id, None)
            raise

    async def poll(self, wait: float = 5.0) -> dict | None:
        """浏览器侧轮询：拿一个任务（如有），否则空。"""
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=wait)
        except asyncio.TimeoutError:
            return None

    def deliver(self, task_id: str, result: dict) -> bool:
        """浏览器返回结果。"""
        fut = self.pending.pop(task_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(result)
        return True


@dataclass
class BrowserSession:
    """业务代码看到的浏览器代理。注入到 site.operations() 的处理函数里。"""

    bus: RpcBus

    async def fetch(self, url: str, method: str = "GET",
                    headers: dict | None = None,
                    body: Any = None, **kwargs) -> dict:
        """让浏览器替我们 fetch 一个 URL。返回 {ok, status, url, headers, body}。"""
        return await self.bus.send(
            "fetch_url", url=url, method=method,
            headers=headers or {}, body=body, **kwargs,
        )

    async def eval(self, code: str) -> dict:
        """在浏览器里 eval 一段 JS。返回 {ok, value}。"""
        return await self.bus.send("eval", code=code)

    async def cookie(self) -> str:
        """返回 document.cookie 全文。"""
        r = await self.bus.send("cookie")
        return r.get("value", "") if isinstance(r, dict) else ""

    async def gen_token(self, op: str = "gen_stoken", **kwargs) -> dict:
        """通用 token 生成 RPC（每个 plugin 自定义自己的 op 名字）。"""
        return await self.bus.send(op, **kwargs)
