"""mitm-rpc CLI —— 所有功能的命令行入口。

通过 HTTP 调本地 FastAPI（默认 127.0.0.1:9999）。
所有命令都会先确认后端是否在跑（除了 'go' 和 'serve' 这两个启动命令）。

Quick start:
    python cli.py go                  # 一键启所有 (server + mitm + chrome)
    python cli.py search "算法工程师"
    python cli.py greet "算法工程师" 3 --min-salary 20

完整命令:
    sites                      列站点 + 操作
    op <site> <op> k=v ...     调任意操作（最 generic）
    search <query>             搜职位
    greet <query> [N]          搜 + 招呼 (--min-salary --brand --exclude --interactive)

    capture {on|off|status|list|get N|clear|watch}
    health [<site>]            健康检查
    storage {backends|use|tables|read}
    rpc {eval|cookie|fetch}    远程 JS / cookie / fetch

    go                         一键启 server + mitm + chrome
    serve                      只启 FastAPI
    pipeline {list|reload}     数据管道
    stats                      RPC 计数等
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

API = os.environ.get("MITMRPC_API", "http://127.0.0.1:9999")
ROOT = Path(__file__).resolve().parent


# ─────────────── HTTP helpers ───────────────

def _api(method: str, path: str, **kw) -> Any:
    try:
        r = requests.request(method, API + path, timeout=30, **kw)
        if r.status_code >= 400:
            try: detail = r.json().get("detail", r.text)
            except Exception: detail = r.text
            print(f"❌ HTTP {r.status_code}: {detail}", file=sys.stderr)
            sys.exit(1)
        return r.json() if r.text else {}
    except requests.RequestException as e:
        print(f"❌ 后端不通 ({e})。先跑 'python cli.py go' 或 'python cli.py serve'", file=sys.stderr)
        sys.exit(1)


def _post(path: str, body: dict) -> Any:
    return _api("POST", path, json=body)

def _get(path: str) -> Any:
    return _api("GET", path)

def _coerce(v: str):
    """字符串自动推断成 bool/int/float/json"""
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if v.startswith(("[", "{")):
        try: return json.loads(v)
        except Exception: pass
    return v


# ─────────────── go / serve ───────────────

def cmd_go(args):
    """一键启 server + mitm + chrome。前台 wait Chrome 关闭就清理。"""
    venv = ROOT / ".venv" / "Scripts"
    py = venv / ("python.exe" if os.name == "nt" else "python")
    uvicorn = venv / "uvicorn.exe"
    mitmdump = venv / "mitmdump.exe"
    if not py.exists():
        print("❌ .venv 没建。先跑 scripts/setup.ps1", file=sys.stderr); sys.exit(1)

    procs: list[subprocess.Popen] = []
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    print("🚀 启动 FastAPI :9999 ...")
    procs.append(subprocess.Popen(
        [str(uvicorn), "core.server:app", "--host", "127.0.0.1",
         "--port", "9999", "--log-level", "warning"],
        cwd=str(ROOT), creationflags=flags,
    ))
    time.sleep(2)

    print("🚀 启动 mitm :8888 ...")
    procs.append(subprocess.Popen(
        [str(mitmdump), "-s", "core/mitm_addon.py", "--listen-port", "8888",
         "--set", "console_eventlog_verbosity=info"],
        cwd=str(ROOT), creationflags=flags,
    ))
    time.sleep(2)

    print("🚀 启动 Chrome (关闭窗口退出全套) ...")
    chrome_proc = subprocess.Popen(
        [str(py), "core/browser.py", args.url or "https://www.zhipin.com/"],
        cwd=str(ROOT), creationflags=flags,
    )

    print("\n✅ 全套服务跑起来了。访问 http://127.0.0.1:9999 看 API 文档。")
    print("✅ 另开终端用 cli.py 跑命令。Ctrl+C 退出全部。\n")

    try:
        chrome_proc.wait()
    except KeyboardInterrupt:
        chrome_proc.terminate()
    finally:
        print("\n[+] 清理后台进程 ...")
        for p in procs:
            try: p.terminate()
            except Exception: pass
        for p in procs:
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: p.kill()


def cmd_serve(args):
    """只启 FastAPI（不 mitm 不 chrome）。用于已经手动起好它们时。"""
    venv = ROOT / ".venv" / "Scripts"
    uvicorn = venv / "uvicorn.exe"
    if not uvicorn.exists():
        print("❌ .venv 没建", file=sys.stderr); sys.exit(1)
    os.execv(str(uvicorn), [
        str(uvicorn), "core.server:app",
        "--host", args.host, "--port", str(args.port),
        "--log-level", args.log_level,
    ])


# ─────────────── 业务命令 ───────────────

def cmd_sites(args):
    sites = _get("/api/sites")
    for s in sites:
        print(f"\n📦 {s['name']}  域名: {', '.join(s['domains'])}")
        print(f"   操作: {', '.join(s['operations'])}")
        for p in s["patches"]:
            print(f"   patch: {p['name']} — {p['notes']}")


def cmd_op(args):
    params = {}
    for kv in args.params:
        if "=" not in kv:
            print(f"参数格式: key=value (got: {kv})", file=sys.stderr); sys.exit(2)
        k, v = kv.split("=", 1)
        params[k] = _coerce(v)
    print(json.dumps(_post(f"/api/sites/{args.site}/op/{args.op}", params),
                     ensure_ascii=False, indent=2))


def cmd_search(args):
    r = _post(f"/api/sites/{args.site}/op/search", {
        "query": args.query, "city": args.city,
        "page": args.page, "page_size": args.page_size,
    })
    if not r.get("ok"):
        print(f"❌ code={r.get('code')} {r.get('message','')}", file=sys.stderr); sys.exit(1)
    print(f"\n✅ {r['count']} 个职位:\n")
    for i, j in enumerate(r["jobs"]):
        print(f"  [{i:2d}] {j.get('jobName',''):20s} {j.get('salaryDesc',''):14s} "
              f"{j.get('brandName','')[:25]:25s} {j.get('cityName','')}")


def _parse_salary_min(s: str) -> int:
    m = re.match(r"^(\d+)\s*-\s*\d+\s*[Kk]", str(s or ""))
    return int(m.group(1)) if m else 0


def cmd_greet(args):
    """搜 + 批量招呼。支持过滤 / 交互勾选。"""
    s = _post(f"/api/sites/{args.site}/op/search", {
        "query": args.query, "city": args.city,
        "page": args.page, "page_size": 30,
    })
    if not s.get("ok"):
        print(f"❌ search: code={s.get('code')} {s.get('message','')}", file=sys.stderr); sys.exit(1)
    jobs = s["jobs"]

    # 应用过滤器
    def passes(j: dict) -> bool:
        if args.min_salary and _parse_salary_min(j.get("salaryDesc", "")) < args.min_salary:
            return False
        if args.brand and args.brand.lower() not in (j.get("brandName", "") or "").lower():
            return False
        if args.exclude:
            for kw in args.exclude:
                if kw.lower() in (j.get("jobName", "") or "").lower():
                    return False
        return True

    filtered = [j for j in jobs if passes(j)]
    print(f"\n搜到 {len(jobs)} 个，过滤后 {len(filtered)} 个:\n")
    for i, j in enumerate(filtered):
        print(f"  [{i:2d}] {j.get('jobName',''):20s} {j.get('salaryDesc',''):14s} "
              f"{j.get('brandName','')[:30]}")

    # 选取
    if args.interactive:
        raw = input(f"\n输入要招呼的编号（空格分隔, 'all', 回车取消）: ").strip()
        if not raw: print("取消"); return
        if raw == "all":
            sel = filtered[:args.count]
        else:
            idxs = [int(x) for x in raw.split() if x.strip().isdigit()]
            sel = [filtered[i] for i in idxs if 0 <= i < len(filtered)]
    else:
        sel = filtered[:args.count]

    if not sel: print("没匹配的职位"); return

    if not args.yes:
        print(f"\n准备招呼 {len(sel)} 个（间隔 {args.interval}s）:")
        for j in sel: print(f"  → {j.get('jobName','')} ({j.get('brandName','')})")
        if input("\n确认？(y/n): ").strip().lower() != "y":
            print("取消"); return

    ok = fail = 0
    for i, j in enumerate(sel):
        sid, jid = j.get("securityId"), j.get("encryptJobId") or j.get("jobId")
        print(f"  [{i+1}/{len(sel)}] {j.get('jobName')} ", end="", flush=True)
        r = _post(f"/api/sites/{args.site}/op/greet", {
            "security_id": sid, "job_id": jid, "lid": j.get("lid", ""),
            "query": args.query, "city": args.city,
        })
        code = r.get("code")
        if code == 0:
            ok += 1; print("✅")
        else:
            fail += 1; print(f"⚠️ code={code} {r.get('message','')}")
        if i < len(sel) - 1: time.sleep(args.interval)
    print(f"\n完成: ✅ {ok} · ❌ {fail}")


# ─────────────── capture ───────────────

def cmd_capture(args):
    if args.action == "on":
        r = _post("/api/capture/toggle", {"on": True}); print("✅" if r.get("enabled") else "❌"); return
    if args.action == "off":
        _post("/api/capture/toggle", {"on": False}); print("✅"); return
    if args.action == "status":
        print(json.dumps(_get("/api/capture/status"), ensure_ascii=False, indent=2)); return
    if args.action == "list":
        rows = _get(f"/api/capture/list?limit={args.limit}&q={args.q or ''}")
        for i, c in enumerate(rows):
            print(f"  [{i:3d}] {c.get('method',''):4s} {c.get('resp_status',0):3d}  "
                  f"{(c.get('url','') or '')[:120]}")
        return
    if args.action == "get":
        print(json.dumps(_get(f"/api/capture/{args.idx}"), ensure_ascii=False, indent=2)); return
    if args.action == "clear":
        _post("/api/capture/clear", {}); print("✅"); return
    if args.action == "watch":
        # SSE 实时流
        url = f"{API}/api/capture/stream"
        print(f"📡 实时抓包流（Ctrl+C 退出）...\n")
        try:
            with requests.get(url, stream=True, timeout=None) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "): continue
                    try:
                        rec = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    print(f"  {rec.get('method','?'):4s} {rec.get('resp_status',0):3d} "
                          f"{(rec.get('url','') or '')[:120]}")
        except KeyboardInterrupt:
            print("\n停。")


# ─────────────── health ───────────────

def cmd_health(args):
    if args.site:
        print(json.dumps(_get(f"/api/health/{args.site}"), ensure_ascii=False, indent=2)); return
    sites = _get("/api/sites")
    for s in sites:
        r = _get(f"/api/health/{s['name']}")
        flag = "✅" if r["ok"] else "❌"
        print(f"\n{flag} {s['name']}")
        for p in r["patches_ok"]: print(f"   ✅ {p}")
        for p in r["patches_missing"]: print(f"   ❌ {p}")
        if not r["ok"] and r.get("fix_prompt"):
            print(r["fix_prompt"])


# ─────────────── storage ───────────────

# 各后端默认参数（用 cli use 时不传啥就走这个）
_STORAGE_DEFAULTS = {
    "jsonl": {"root": "./data/storage"},
    "sqlite": {"path": "./data/data.sqlite"},
    "csv": {"root": "./data/csv"},
    "excel": {"path": "./data/mitm_rpc.xlsx"},
    "mysql": {"host": "127.0.0.1", "port": 3306, "user": "root",
              "password": "", "database": "mitm_rpc", "charset": "utf8mb4"},
}

def cmd_storage(args):
    if args.action == "backends":
        r = _get("/api/storage/backends")
        print(f"\n当前: {r['current']['backend']} {r['current'].get('options',{})}\n")
        print("可用后端:")
        for b in r["backends"]:
            params = ", ".join(f"{p['name']}={p['default']!r}" for p in b["params"])
            print(f"  · {b['name']:8s} ({params})")
        return
    if args.action == "use":
        # cli storage use csv
        # cli storage use mysql --host 1.2.3.4 --user x --password y --database d
        # cli storage use sqlite --path /data/foo.db
        opts = dict(_STORAGE_DEFAULTS.get(args.backend, {}))
        # 命令行 --xxx 覆盖默认
        for k, v in (args.options or {}).items():
            opts[k] = v
        r = _post("/api/storage/config", {"backend": args.backend, "options": opts})
        print(f"✅ 切换到 {args.backend}: {opts}"); return
    if args.action == "tables":
        for t in _get("/api/storage/tables"):
            print(t)
        return
    if args.action == "read":
        rows = _get(f"/api/storage/{args.table}?limit={args.limit}")
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return


# ─────────────── rpc / pipeline / stats ───────────────

def cmd_rpc(args):
    if args.action == "eval":
        print(json.dumps(_post("/rpc/req", {"op": "eval", "code": args.code}),
                         ensure_ascii=False, indent=2)); return
    if args.action == "cookie":
        r = _post("/rpc/req", {"op": "cookie"})
        print(r.get("value", "")); return
    if args.action == "fetch":
        r = _post("/rpc/req", {"op": "fetch_url", "url": args.url})
        if isinstance(r, dict):
            print(f"status={r.get('status')} url={r.get('url')}")
            print(r.get("body", "")[:5000])
        return


def cmd_pipeline(args):
    if args.action == "list":
        hooks = _get("/api/pipelines").get("hooks", [])
        if not hooks:
            print("无 hook。看 pipelines/example_*.py"); return
        print(f"\n已注册 {len(hooks)} 个处理器:\n")
        for h in hooks:
            f = ", ".join(f"{k}={v!r}" for k, v in (h.get("filter") or {}).items())
            print(f"  · {h['event']:18s} {h['module']:30s} {h['func']}({f})")
            if h.get("doc"): print(f"      ↳ {h['doc']}")
        return
    if args.action == "reload":
        r = _post("/api/pipelines/reload", {})
        print(f"✅ 已重载, {r.get('count', 0)} 个 hook"); return


def cmd_stats(args):
    print(json.dumps(_get("/api/stats"), ensure_ascii=False, indent=2))


# ─────────────── argparse ───────────────

class ParseKVAction(argparse.Action):
    """处理 storage use 的 --key value 参数收集到 dict。"""
    def __call__(self, parser, ns, values, option_string=None):
        opts = getattr(ns, "options", None) or {}
        opts[self.dest] = _coerce(values)
        ns.options = opts


def main():
    p = argparse.ArgumentParser(description="mitm-rpc CLI", formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # 启动
    g = sub.add_parser("go", help="一键启 server + mitm + chrome")
    g.add_argument("url", nargs="?", help="初始 URL (默认 zhipin.com)")
    g.set_defaults(func=cmd_go)

    se = sub.add_parser("serve", help="只启 FastAPI server")
    se.add_argument("--host", default="127.0.0.1")
    se.add_argument("--port", type=int, default=9999)
    se.add_argument("--log-level", default="warning")
    se.set_defaults(func=cmd_serve)

    # 业务
    sub.add_parser("sites", help="列站点 + 操作").set_defaults(func=cmd_sites)

    op = sub.add_parser("op", help="跑任意 plugin 操作")
    op.add_argument("site"); op.add_argument("op"); op.add_argument("params", nargs="*")
    op.set_defaults(func=cmd_op)

    sc = sub.add_parser("search", help="搜职位")
    sc.add_argument("query")
    sc.add_argument("--city", type=int, default=101020100)
    sc.add_argument("--page", type=int, default=1)
    sc.add_argument("--page-size", type=int, default=30)
    sc.add_argument("--site", default="boss")
    sc.set_defaults(func=cmd_search)

    gr = sub.add_parser("greet", help="搜 + 招呼（支持筛选）",
                        epilog="例: cli.py greet 算法 5 --min-salary 20 --brand 阿里")
    gr.add_argument("query")
    gr.add_argument("count", type=int, nargs="?", default=3)
    gr.add_argument("--city", type=int, default=101020100)
    gr.add_argument("--page", type=int, default=1)
    gr.add_argument("--interval", type=float, default=5.0)
    gr.add_argument("--min-salary", type=int, default=0, help="最低薪资 K")
    gr.add_argument("--brand", help="公司名包含")
    gr.add_argument("--exclude", nargs="*", help="标题含这些关键词的跳过")
    gr.add_argument("-i", "--interactive", action="store_true", help="交互勾选哪些")
    gr.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    gr.add_argument("--site", default="boss")
    gr.set_defaults(func=cmd_greet)

    # 抓包
    cap = sub.add_parser("capture", help="抓包")
    cap.add_argument("action", choices=["on", "off", "status", "list", "get", "clear", "watch"])
    cap.add_argument("idx", type=int, nargs="?")
    cap.add_argument("--limit", type=int, default=100)
    cap.add_argument("--q", default="")
    cap.set_defaults(func=cmd_capture)

    # 健康
    he = sub.add_parser("health", help="健康检查")
    he.add_argument("site", nargs="?")
    he.set_defaults(func=cmd_health)

    # 存储
    st = sub.add_parser("storage", help="存储")
    st_sub = st.add_subparsers(dest="action", required=True)
    st_sub.add_parser("backends", help="列后端").set_defaults(func=cmd_storage, action="backends")
    use = st_sub.add_parser("use", help="切到指定后端 (jsonl/sqlite/csv/excel/mysql)")
    use.add_argument("backend", choices=list(_STORAGE_DEFAULTS.keys()))
    # 把所有 storage 选项都允许（mysql 用 --host --port 等，sqlite 用 --path）
    for k in ("host", "port", "user", "password", "database", "charset", "path", "root"):
        use.add_argument(f"--{k}", action=ParseKVAction)
    use.set_defaults(func=cmd_storage, action="use")
    st_sub.add_parser("tables", help="列表名").set_defaults(func=cmd_storage, action="tables")
    rd = st_sub.add_parser("read", help="读数据")
    rd.add_argument("table"); rd.add_argument("--limit", type=int, default=100)
    rd.set_defaults(func=cmd_storage, action="read")

    # rpc
    rp = sub.add_parser("rpc", help="远程 RPC")
    rp_sub = rp.add_subparsers(dest="action", required=True)
    ev = rp_sub.add_parser("eval"); ev.add_argument("code"); ev.set_defaults(func=cmd_rpc, action="eval")
    rp_sub.add_parser("cookie").set_defaults(func=cmd_rpc, action="cookie")
    fe = rp_sub.add_parser("fetch"); fe.add_argument("url"); fe.set_defaults(func=cmd_rpc, action="fetch")

    # pipeline
    pp = sub.add_parser("pipeline", help="数据处理管道")
    pp.add_argument("action", choices=["list", "reload"])
    pp.set_defaults(func=cmd_pipeline)

    sub.add_parser("stats", help="服务统计").set_defaults(func=cmd_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
