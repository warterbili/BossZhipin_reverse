from __future__ import annotations

import re
import unittest

from core.patching import apply_js_patches, find_balanced_end
from sites._base import JsPatch


class PatchingTests(unittest.TestCase):
    def test_sub_and_body_patches_share_one_engine(self):
        source = 'function Bm(){if(true){return "}";}return 1;}new Array(1e9)'
        patches = [
            JsPatch(name="bomb", mode="sub", pattern=re.compile(r"new Array\(1e\d+\)"), replacement="new Array(1)"),
            JsPatch(name="Bm", pattern=re.compile(r"function Bm\(\)\{"), replacement_body="{}"),
        ]

        result = apply_js_patches(source, patches)

        self.assertEqual(result.text, "function Bm(){}new Array(1)")
        self.assertEqual(result.counts, {"bomb": 1, "Bm": 1})

    def test_unbalanced_body_is_rejected(self):
        with self.assertRaises(ValueError):
            find_balanced_end("if(true){", len("if(true){"))


if __name__ == "__main__":
    unittest.main()
