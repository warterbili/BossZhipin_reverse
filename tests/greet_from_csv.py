"""从 CSV 取前 N 个职位，逐个打招呼，随机间隔 [interval_min, interval_max] 秒。

用法:
  python tests/greet_from_csv.py
  python tests/greet_from_csv.py --csv data/csv/boss_jobs.csv --count 20 --min 3 --max 4
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:9999"


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"❌ CSV 不存在: {path}", file=sys.stderr); sys.exit(1)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=str(ROOT / "data" / "csv" / "boss_jobs.csv"))
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--min", type=float, default=3.0, dest="imin")
    p.add_argument("--max", type=float, default=4.0, dest="imax")
    p.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    args = p.parse_args()

    csv_path = Path(args.csv)
    rows = load_csv(csv_path)
    print(f"\n从 {csv_path} 读到 {len(rows)} 条")

    targets = rows[:args.count]
    print(f"准备招呼前 {len(targets)} 个 (随机间隔 {args.imin}~{args.imax}s):\n")
    for i, j in enumerate(targets):
        print(f"  [{i+1:2d}] {j.get('jobName',''):20s} {j.get('salaryDesc',''):15s} {j.get('brandName','')[:30]}")

    if not args.yes:
        if input("\n确认 (y/n): ").strip().lower() != "y":
            print("取消"); return

    print()
    ok = fail = skip = 0
    for i, j in enumerate(targets):
        sid = j.get("securityId")
        jid = j.get("encryptJobId") or j.get("jobId")
        lid = j.get("lid", "")
        if not (sid and jid):
            print(f"  [{i+1:2d}] {j.get('jobName','')} → 缺 ID, 跳过")
            skip += 1; continue

        print(f"  [{i+1:2d}/{len(targets)}] {j.get('jobName','')} ({j.get('brandName','')[:30]}) ", end="", flush=True)
        try:
            r = requests.post(f"{API}/api/sites/boss/op/greet", json={
                "security_id": sid, "job_id": jid, "lid": lid,
                "query": j.get("query", ""), "city": int(j.get("city", 101020100) or 101020100),
            }, timeout=20).json()
        except Exception as e:
            print(f"❌ {e}"); fail += 1; continue

        # operations.greet 返回顶层 code/message + data=zpData
        code = r.get("code")
        msg = r.get("message", "")
        zd = r.get("data") or {}
        if code == 0:
            ok += 1
            # showGreeting=true 时附带默认问候语；false 表示"已招呼/已设置自定义"，仍是成功
            greet = zd.get("greeting") or "(默认问候语已发送)"
            print(f"✅ {greet[:30]}")
        else:
            fail += 1
            print(f"⚠️ code={code} {msg[:60]}")

        # 随机间隔
        if i < len(targets) - 1:
            sleep_s = random.uniform(args.imin, args.imax)
            time.sleep(sleep_s)

    print(f"\n完成: ✅ {ok} · ❌ {fail} · ⏭ {skip}  (耗时 ≈ {len(targets) * (args.imin + args.imax) / 2:.0f}s)")


if __name__ == "__main__":
    main()
