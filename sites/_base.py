"""Site plugin abstract base class.

每个目标站点 = 一个 sites/<name>/ 目录，里面定义:
  - patches.py: mitm 要 patch 的 JS 函数签名
  - operations.py: 暴露给 UI/API 的业务操作 (search/greet/...)
  - injection.js: 注入到该站点页面的 JS（通常是把加密类暴露到顶层）
  - selftest.py: 健康检查（检测 patch 是否还匹配最新 JS）

新增站点的最小实现见 docs/PLUGIN_GUIDE.md
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class JsPatch:
    """JS 函数体替换规则。

    name:        显示名（"Bm", "function t"）
    pattern:     找到目标函数声明的正则（必须捕获到 'function NAME() {' 的开头）
    replacement: 函数体替换为啥（默认空函数体）
    notes:       说明（教学用）
    """
    name: str
    pattern: re.Pattern
    replacement_body: str = "{}"
    notes: str = ""


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
    """站点插件基类。子类实现下列字段/方法即可。"""

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
