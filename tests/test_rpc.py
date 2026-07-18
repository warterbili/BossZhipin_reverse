from __future__ import annotations

import asyncio
import unittest

from fastapi import HTTPException

from core.rpc import RpcBus


class RpcBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_error_is_counted_as_error(self):
        bus = RpcBus()
        waiting = asyncio.create_task(bus.send("fetch_url", timeout=1))
        task = await bus.poll(wait=0.1)

        self.assertIsNotNone(task)
        bus.deliver(task["id"], {"ok": False, "error": "blocked"})
        result = await waiting

        self.assertFalse(result["ok"])
        self.assertEqual(bus.stats, {"req": 1, "ok": 0, "err": 1, "timeout": 0})

    async def test_timeout_cleans_pending_future(self):
        bus = RpcBus()

        with self.assertRaises(HTTPException) as raised:
            await bus.send("cookie", timeout=0.01)

        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(bus.pending, {})
        self.assertEqual(bus.stats["timeout"], 1)

    async def test_cancellation_cleans_pending_future(self):
        bus = RpcBus()
        waiting = asyncio.create_task(bus.send("cookie", timeout=1))
        await bus.poll(wait=0.1)
        waiting.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await waiting

        self.assertEqual(bus.pending, {})


if __name__ == "__main__":
    unittest.main()
