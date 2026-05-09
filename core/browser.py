"""启动一个 Chrome 调试实例（用项目独立 profile，走 mitm 代理）。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def find_chrome() -> str:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        # macOS / Linux 常见路径，便于其他平台用户
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError("未找到 chrome / chromium，请装一个或改 find_chrome()")


def launch(
    proxy: str = "http://127.0.0.1:8888",
    debug_port: int = 19222,
    profile_dir: str | Path | None = None,
    initial_url: str = "about:blank",
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    """启动 Chrome，返回 Popen 句柄。父进程 wait() 直到用户关窗。"""
    chrome = find_chrome()
    if profile_dir is None:
        profile_dir = Path(__file__).resolve().parent.parent / "data" / "chrome-profile"
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    args = [
        chrome,
        f"--proxy-server={proxy}",
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={debug_port}",
        "--no-default-browser-check",
        "--no-first-run",
        "--disable-features=IsolateOrigins,site-per-process",
        "--ignore-certificate-errors",
        "--disable-backgrounding-occluded-windows",
        initial_url,
    ]
    if extra_args:
        args[-1:-1] = extra_args  # insert before url

    print(f"[browser] launching with profile {profile_dir}")
    print(f"[browser] proxy={proxy} debug-port={debug_port}")
    return subprocess.Popen(
        args,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


if __name__ == "__main__":
    proc = launch(initial_url=sys.argv[1] if len(sys.argv) > 1 else "about:blank")
    print(f"[browser] PID={proc.pid}, 关窗或 Ctrl+C 退出")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
