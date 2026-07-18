"""Internal capability boundary used by the Boss Zhipin implementation.

The repository currently supports only ``sites/boss``.  ``SitePlugin`` keeps
Boss patches, injections, health checks, and operations isolated; it is not a
claim that additional targets have been implemented or validated.  See
``docs/PLUGIN_GUIDE.md`` for the boundary's design reference.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class JsPatch:
    """JS patch 规则。两种模式:

    mode="body"（默认）—— 函数体替换:
        pattern 匹配到 'function NAME() {' 的开头，mitm 用大括号配对找到函数体并整体替换成
        replacement_body（默认空函数体 '{}'）。适合【函数型】检测点 (Bm / Rm / XCID …)。

    mode="sub" —— 纯正则替换:
        直接 re.sub(pattern, replacement, js)。适合【表达式型】检测点，它们不是完整函数、无法靠
        “清空函数体”处理，例如 console.clear 包装器、内存炸弹 new Array(1eN) / .repeat(1eN)。
        replacement 支持 \\1 反向引用。

    name:  显示名 ; notes: 说明（教学用）
    """
    name: str
    pattern: re.Pattern
    replacement_body: str = "{}"      # mode="body"
    notes: str = ""
    mode: str = "body"                # "body" | "sub"
    replacement: str = ""             # mode="sub" 的替换串（可含 \1 反向引用）
    spa_only: bool = False            # 只应在 SPA bundle(app~*/vendor-*)里校验；SEO main.js 不要求命中


@dataclass
class HtmlInject:
    """HTML 响应注入规则。

    url_pattern:    URL 子串匹配（'/web/passport/zp/security.html' / 'zhipin.com'）
    script:         要注入到 <head> 之后的 <script>...</script> 字符串
    inject_marker:  脚本里包含的标志字符串，用于避免重复注入
    """
    url_pattern: str
    script: str
    inject_marker: str


@dataclass
class HealthCheckResult:
    site: str
    ok: bool
    timestamp: float
    patches_ok: list[str] = field(default_factory=list)
    patches_missing: list[str] = field(default_factory=list)
    fix_prompt: str = ""  # 给 AI 看的提示，告诉它怎么修补
    detail: dict[str, Any] = field(default_factory=dict)


class SitePlugin(ABC):
    """Boss 能力边界的内部抽象基类。"""

    name: str = ""
    domains: list[str] = []  # ["zhipin.com", "static.zhipin.com"]
    patches: list[JsPatch] = []
    injections: list[HtmlInject] = []

    def matches_host(self, host: str) -> bool:
        host = (host or "").lower()
        return any(d in host for d in self.domains)

    @abstractmethod
    def operations(self) -> dict[str, Callable]:
        """返回 {操作名: 调用函数}，函数接受 BrowserSession 和 kwargs。

        BrowserSession.fetch(url, method, headers, body) → 让浏览器去发请求
        BrowserSession.eval(code) → 在浏览器内执行任意 JS
        """
        ...

    @abstractmethod
    def health_check(self, fetch_main_js: Callable[[], str | None]) -> HealthCheckResult:
        """检查 patch 是否还匹配最新 JS。"""
        ...
