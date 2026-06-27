"""演示：在【浏览器之外】用 __zp_stoken__ 发请求（gen → URL编码 → requests）。

和项目主路径（fetch_url 让浏览器自己发）不同，这里展示“自己生成 token + 自己发请求”这条路。
关键点只有一个：**token 入 cookie 前必须 URL 编码**，否则服务端把 '+' 解成空格，token 损坏 → code:37。

前置：
  1. 已按 README 起好 server + mitm + 登录浏览器（gen_stoken op 可用）。
  2. 提供你这条登录会话的 cookie（zp_at / wt2 / bst 等），见下方 LOGIN_COOKIES。
     —— 这些是你自己的会话凭据，别提交进仓库。

流程（已实测 3/3 可拿到数据）：
  外部 requests 发 joblist → code:37 + zpData.{seed, ts}
  → 调项目 RPC: gen_stoken(seed, ts) → 浏览器算 token，返回 token_encoded
  → 把 token_encoded 塞进 __zp_stoken__ cookie → requests 重发 → code:0 + 数据
"""
import os
import json
import urllib.parse
import requests

SERVER = os.environ.get("MITMRPC_SERVER", "http://127.0.0.1:9999")  # 项目的 FastAPI server
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
JOBLIST = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
PARAMS = {"scene": 1, "query": "java", "city": 101010100, "page": 1, "pageSize": 30}
HEADERS = {"user-agent": UA, "accept": "application/json, text/plain, */*",
           "referer": "https://www.zhipin.com/web/geek/job?query=java&city=101010100",
           "x-requested-with": "XMLHttpRequest"}

# 你这条登录会话的 cookie（从浏览器导出；勿提交）。__zp_stoken__ 由本脚本生成，不要放这里。
LOGIN_COOKIES = json.loads(os.environ.get("BOSS_LOGIN_COOKIES", "{}"))  # e.g. {"zp_at": "...", "wt2": "...", "bst": "..."}


def gen_stoken(seed: str, ts: int) -> dict:
    """调项目的 gen_stoken op（浏览器算 token），返回 {token, token_encoded, ts_used}。"""
    r = requests.post(f"{SERVER}/api/sites/boss/op/gen_stoken",
                      json={"seed": seed, "ts": ts}, timeout=30)
    return r.json()


def main():
    s = requests.Session()
    s.headers.update(HEADERS)
    for k, v in LOGIN_COOKIES.items():
        if k != "__zp_stoken__":
            s.cookies.set(k, v, domain=".zhipin.com")

    # 1) 触发一次 challenge，拿服务端下发的 seed/ts
    j = s.get(JOBLIST, params=PARAMS, timeout=15).json()
    if j.get("code") != 37:
        print(f"没拿到 challenge（code={j.get('code')}）。可能 token 还有效；删掉 __zp_stoken__ 再试。")
        return
    seed, ts = j["zpData"]["seed"], j["zpData"]["ts"]
    print(f"1) challenge: seed={seed[:10]}… ts={ts}")

    # 2) 让浏览器算 token（项目 RPC）
    g = gen_stoken(seed, ts)
    if not g.get("ok"):
        print(f"gen_stoken 失败: {g}")
        return
    token = g["token"]
    # 3) ★★★ 关键：入 cookie 前 URL 编码（否则服务端 '+'→空格 损坏 → code:37）
    enc = g.get("token_encoded") or urllib.parse.quote(token, safe="")
    print(f"2) token len={len(token)}  → URL-encoded len={len(enc)}")

    # 4) 外部 requests 带上编码后的 token 发请求
    s.cookies.set("__zp_stoken__", enc, domain=".zhipin.com")
    j2 = s.get(JOBLIST, params=PARAMS, timeout=15).json()
    jobs = (j2.get("zpData") or {}).get("jobList") or []
    print(f"3) 外部请求 → code={j2.get('code')} jobs={len(jobs)}")
    for job in jobs[:5]:
        print(f"   - {job.get('jobName')} | {job.get('brandName')} | {job.get('salaryDesc')}")
    print("\nVERDICT:", "脱离浏览器 + 自生成 token 拿到数据 ✅" if jobs else f"被拒 code={j2.get('code')}")


if __name__ == "__main__":
    main()
