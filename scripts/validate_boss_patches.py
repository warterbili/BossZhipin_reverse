"""Apply Boss patches to current live bundles and validate the resulting JavaScript."""
from __future__ import annotations

import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.patching import apply_js_patches  # noqa: E402
from sites.boss import _discover_js_urls, _fetch_bundle, _is_spa_js, _short_url  # noqa: E402
from sites.boss.patches import BOSS_PATCHES  # noqa: E402


def check_javascript(source: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["node", "--check", "-"],
        input=source.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    error = result.stderr.decode("utf-8", errors="replace").strip()
    return result.returncode == 0, error[-500:]


def main() -> int:
    if not shutil.which("node"):
        print("ERROR: Node.js is required for post-patch syntax validation.", file=sys.stderr)
        return 2

    urls, discovery_detail = _discover_js_urls()
    if discovery_detail:
        for key, value in discovery_detail.items():
            print(f"WARN: {key}: {value}")

    downloaded = []
    failures = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(urls)))) as pool:
        for url, source in pool.map(_fetch_bundle, urls):
            if source is None:
                failures.append(f"download failed: {url}")
            else:
                downloaded.append((url, source))

    scoped_counts: Counter[str] = Counter()
    syntax_failures = []
    changed_bundles = 0
    for url, source in downloaded:
        result = apply_js_patches(source, BOSS_PATCHES)
        if result.text != source:
            changed_bundles += 1
        for patch in BOSS_PATCHES:
            if patch.spa_only and not _is_spa_js(url):
                continue
            scoped_counts[patch.name] += result.counts.get(patch.name, 0)

        syntax_ok, error = check_javascript(result.text)
        if not syntax_ok:
            syntax_failures.append(f"{_short_url(url)}: {error}")

        hits = ", ".join(f"{name}x{count}" for name, count in result.counts.items())
        state = "changed" if hits else "unchanged"
        print(f"OK  {_short_url(url)} [{state}{': ' + hits if hits else ''}]")

    missing = [patch.name for patch in BOSS_PATCHES if scoped_counts[patch.name] == 0]
    failures.extend(f"missing patch: {name}" for name in missing)
    failures.extend(f"syntax failed: {item}" for item in syntax_failures)

    print(
        f"\nSUMMARY: discovered={len(urls)} downloaded={len(downloaded)} "
        f"changed={changed_bundles} patch_types={len(scoped_counts)} "
        f"syntax_ok={len(downloaded) - len(syntax_failures)}"
    )
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    print("VERDICT: current Boss bundles remain patchable and syntactically valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
