from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import core.mitm_addon as addon


class FakeRequest:
    host = "www.zhipin.com"
    path = "/wapi/example.json"
    pretty_url = "https://www.zhipin.com/wapi/example.json"
    method = "GET"
    headers = {"accept": "application/json"}

    @staticmethod
    def get_text():
        return ""


class FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    @staticmethod
    def get_text():
        return '{"code":0}'


class FakeFlow:
    request = FakeRequest()
    response = FakeResponse()


class CaptureGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture_dir = Path(__file__).resolve().parent.parent / "tmp" / "test-capture-gate"
        cls.capture_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        flag = cls.capture_dir / "_enabled"
        flag.unlink(missing_ok=True)
        cls.capture_dir.rmdir()

    def test_capture_off_stops_forwarding(self):
        (self.capture_dir / "_enabled").unlink(missing_ok=True)
        with patch.object(addon, "CAPTURE_DIR", self.capture_dir), patch.object(addon, "_post_to_server") as post:
            addon._capture(FakeFlow())
        post.assert_not_called()

    def test_capture_on_forwards_business_response(self):
        (self.capture_dir / "_enabled").touch()
        with patch.object(addon, "CAPTURE_DIR", self.capture_dir), patch.object(addon, "_post_to_server") as post:
            addon._capture(FakeFlow())
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
