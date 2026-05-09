"""Boss 直聘 (zhipin.com) 插件。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import requests

from sites._base import HealthCheckResult, HtmlInject, JsPatch, SitePlugin
from .patches import BOSS_PATCHES
from .operations import BOSS_OPERATIONS


HERE = Path(__file__).parent
INJECTION_JS = (HERE / "injection.js").read_text(encoding="utf-8")


class BossPlugin(SitePlugin):
    name = "boss"
    domains = ["zhipin.com", "static.zhipin.com"]

    patches = BOSS_PATCHES

    injections = [
        HtmlInject(
            url_pattern="zhipin.com",
            script=f"<script>{INJECTION_JS}</script>",
            inject_marker="__BOSS_PLUGIN_LOADED__",
        ),
    ]

    def operations(self) -> dict[str, Callable]:
        return BOSS_OPERATIONS

    def health_check(self, fetch_main_js: Callable[[], str | None]) -> HealthCheckResult:
        """下载 Boss 的 main.js，检查所有 patch 签名是否还匹配。"""
        ts = time.time()
        ok_list: list[str] = []
        missing: list[str] = []
        snippets: dict[str, str] = {}

        urls = [
            "https://static.zhipin.com/zhipin-geek-seo/v5457/web/geek/js/main.js",
            "https://static.zhipin.com/zhipin-geek-seo/v5447/web/geek/js/main.js",
        ]

        for url in urls:
            try:
                r = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/148.0.0.0 Safari/537.36",
                })
                if r.status_code != 200:
                    continue
                js = r.text
            except Exception as e:
                snippets[f"err:{url}"] = str(e)
                continue
            for patch in self.patches:
                key = f"{patch.name}@{url.rsplit('/',1)[-1]}"
                m = patch.pattern.search(js)
                if m:
                    ok_list.append(key)
                else:
                    missing.append(key)
                    snippets[key] = ""

        all_ok = len(missing) == 0
        fix_prompt = ""
        if missing:
            fix_prompt = (
                "Boss 反爬 JS 升级了。请帮我更新 sites/boss/patches.py 里的签名。\n"
                f"丢失的 patch: {missing}\n"
                "Boss 的 main.js 在这: " + urls[0] + "\n"
                "下载后用 analysis 里的 find_bm.py / decode_strings.py 重新定位"
                "（通常是变量名变了，结构没变）。"
            )

        return HealthCheckResult(
            site=self.name, ok=all_ok, timestamp=ts,
            patches_ok=ok_list, patches_missing=missing,
            fix_prompt=fix_prompt,
            detail={"checked_urls": urls},
        )


PLUGIN = BossPlugin()
