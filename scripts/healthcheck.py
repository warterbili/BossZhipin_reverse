"""命令行健康检查 —— 看每个站点 patch 还能不能匹配最新 JS。

不依赖浏览器，纯 requests 拉远端 JS 跑正则。
适合 cron 或 CI。

用法:
    python scripts/healthcheck.py          # 检查所有站点
    python scripts/healthcheck.py boss     # 只检查 boss
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib
import pkgutil

from sites._base import SitePlugin


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    plugins: list[SitePlugin] = []
    sites_pkg = importlib.import_module("sites")
    for _f, name, is_pkg in pkgutil.iter_modules(sites_pkg.__path__):
        if not is_pkg or name.startswith("_"):
            continue
        if target and name != target:
            continue
        mod = importlib.import_module(f"sites.{name}")
        plugin = getattr(mod, "PLUGIN", None)
        if plugin is None:
            continue
        plugins.append(plugin)

    if not plugins:
        print(f"未找到插件 (target={target})")
        return 1

    bad = 0
    for p in plugins:
        print(f"\n=== {p.name} ===")
        rep = p.health_check(lambda: None)
        for ok in rep.patches_ok:
            print(f"  ✅ {ok}")
        for miss in rep.patches_missing:
            print(f"  ❌ {miss}")
        if not rep.ok:
            bad += 1
            print()
            print(rep.fix_prompt)
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
