"""Boss 直聘 (zhipin.com) 插件。"""
from __future__ import annotations

import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import requests

from sites._base import HealthCheckResult, HtmlInject, SitePlugin
from .patches import BOSS_PATCHES
from .operations import BOSS_OPERATIONS


HERE = Path(__file__).parent
INJECTION_JS = (HERE / "injection.js").read_text(encoding="utf-8")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)
ENTRYPOINTS = [
    "https://www.zhipin.com/",
    "https://www.zhipin.com/web/geek/jobs",
]
FALLBACK_JS_URLS = [
    "https://static.zhipin.com/zhipin-geek-seo/v5457/web/geek/js/main.js",
]
SCRIPT_SRC_RE = re.compile(
    r"<script[^>]+src=[\"']([^\"']+\.js(?:\?[^\"']*)?)[\"']",
    re.IGNORECASE,
)


def _fetch_text(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return r.text


def _is_patch_target_js(url: str) -> bool:
    return "zhipin-geek-seo" in url or "zhipin-geek-spa" in url


def _is_spa_js(url: str) -> bool:
    return "zhipin-geek-spa" in url


def _short_url(url: str) -> str:
    """Keep health output compact while preserving the moving version/hash."""
    for marker in ("static.zhipin.com/", "img.bosszhipin.com/"):
        if marker in url:
            return url.split(marker, 1)[1]
    return url.rsplit("/", 1)[-1]


def _discover_js_urls() -> tuple[list[str], dict[str, str]]:
    urls: list[str] = []
    detail: dict[str, str] = {}
    for page in ENTRYPOINTS:
        html = _fetch_text(page)
        if not html:
            detail[f"page_error:{page}"] = "fetch failed"
            continue
        for m in SCRIPT_SRC_RE.finditer(html):
            url = urllib.parse.urljoin(page, m.group(1))
            if _is_patch_target_js(url) and url not in urls:
                urls.append(url)
    if not urls:
        detail["fallback"] = "entrypoint discovery found no patch target JS"
        urls.extend(FALLBACK_JS_URLS)
    return urls, detail


def _fetch_bundle(url: str) -> tuple[str, str | None]:
    return url, _fetch_text(url)


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
        """下载当前线上 JS，检查每个 patch 签名至少还能命中一个适用 bundle。"""
        ts = time.time()
        ok_list: list[str] = []
        missing: list[str] = []
        snippets: dict[str, str] = {}

        urls, detail = _discover_js_urls()
        bundles: list[tuple[str, str]] = []
        worker_count = min(8, max(1, len(urls)))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            for url, js in pool.map(_fetch_bundle, urls):
                if js is None:
                    snippets[f"err:{url}"] = "fetch failed"
                    continue
                bundles.append((url, js))

        for patch in self.patches:
            candidates = [
                (url, js) for url, js in bundles
                if not getattr(patch, "spa_only", False) or _is_spa_js(url)
            ]
            hits = [url for url, js in candidates if patch.pattern.search(js)]
            if hits:
                suffix = f"+{len(hits) - 1}" if len(hits) > 1 else ""
                ok_list.append(f"{patch.name}@{_short_url(hits[0])}{suffix}")
            else:
                scope = "spa-bundles" if getattr(patch, "spa_only", False) else "current-js"
                key = f"{patch.name}@{scope}"
                missing.append(key)
                snippets[key] = ""

        all_ok = len(missing) == 0
        fix_prompt = ""
        if missing:
            fix_prompt = (
                "Boss 反爬 JS 升级了。请帮我更新 sites/boss/patches.py 里的签名。\n"
                f"丢失的 patch: {missing}\n"
                "已检查当前线上 JS: " + ", ".join(_short_url(u) for u, _ in bundles[:8]) + "\n"
                "下载后用 analysis/find_bm.py / decode_strings.py 重新定位"
                "（通常是变量名变了，结构没变）。"
            )

        detail_out = {
            "entrypoints": ENTRYPOINTS,
            "checked_urls": urls,
            "downloaded_urls": [url for url, _ in bundles],
            **detail,
        }
        if snippets:
            detail_out["errors"] = snippets

        return HealthCheckResult(
            site=self.name, ok=all_ok, timestamp=ts,
            patches_ok=ok_list, patches_missing=missing,
            fix_prompt=fix_prompt,
            detail=detail_out,
        )


PLUGIN = BossPlugin()
