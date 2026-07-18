from __future__ import annotations

import unittest
from unittest.mock import patch

from sites.boss import BOSS_PATCHES, PLUGIN


class BossHealthTests(unittest.TestCase):
    def test_entrypoint_failure_cannot_pass_against_an_old_fallback_bundle(self):
        with patch("sites.boss._fetch_text", return_value=None):
            result = PLUGIN.health_check(lambda: None)

        self.assertFalse(result.ok)
        self.assertEqual(len(result.patches_missing), len(BOSS_PATCHES))
        self.assertEqual(result.detail["checked_urls"], [])
        self.assertIn("discovery_error", result.detail)


if __name__ == "__main__":
    unittest.main()
