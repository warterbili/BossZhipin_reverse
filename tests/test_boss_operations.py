from __future__ import annotations

import json
import unittest

from sites.boss.operations import auto_greet, greet, greet_selected


class FakeSession:
    def __init__(self, greet_code: int = 0):
        self.greet_code = greet_code

    async def fetch(self, url: str, **kwargs):
        if "joblist.json" in url:
            body = {
                "code": 0,
                "zpData": {"jobList": [{
                    "securityId": "sid",
                    "encryptJobId": "jid",
                    "jobName": "demo",
                    "brandName": "demo-brand",
                }]},
            }
        else:
            body = {
                "code": self.greet_code,
                "message": "Success" if self.greet_code == 0 else "blocked",
                "zpData": {},
            }
        return {"ok": True, "status": 200, "body": json.dumps(body)}


class BossOperationTests(unittest.IsolatedAsyncioTestCase):
    async def test_greet_business_code_controls_ok(self):
        result = await greet(FakeSession(greet_code=37), security_id="sid", job_id="jid")

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], 37)

    async def test_auto_greet_does_not_mark_code_37_as_success(self):
        result = await auto_greet(FakeSession(greet_code=37), count=1, interval=0)

        self.assertEqual(result["success"], 0)
        self.assertFalse(result["all_succeeded"])
        self.assertFalse(result["results"][0]["ok"])
        self.assertEqual(result["_persist"], "boss_greetings")
        self.assertEqual(result["items"][0]["code"], 37)

    async def test_selected_greetings_return_persistable_records(self):
        jobs = [{"securityId": "sid", "encryptJobId": "jid", "jobName": "demo"}]

        result = await greet_selected(FakeSession(), jobs=jobs, interval=0)

        self.assertEqual(result["success"], 1)
        self.assertTrue(result["all_succeeded"])
        self.assertEqual(result["_persist"], "boss_greetings")
        self.assertEqual(result["items"][0]["code"], 0)


if __name__ == "__main__":
    unittest.main()
