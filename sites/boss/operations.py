"""Boss 业务操作 —— 通过 BrowserSession 调浏览器发请求。

每个操作签名: async def f(sess: BrowserSession, **kwargs) -> dict
返回 dict，含 _persist=table_name 时会被 server 自动落到 storage。
"""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any

from core.rpc import BrowserSession


# ─────────────────── search jobs ───────────────────

async def search(sess: BrowserSession, query: str = "", city: int = 101020100,
                 page: int = 1, page_size: int = 30) -> dict:
    """搜索职位，返回 jobList。"""
    qs = urllib.parse.urlencode({
        "scene": 1, "query": query, "city": city,
        "page": page, "pageSize": page_size,
    })
    referer = (
        f"https://www.zhipin.com/web/geek/jobs"
        f"?query={urllib.parse.quote(query)}&city={city}"
    )
    r = await sess.fetch(
        f"https://www.zhipin.com/wapi/zpgeek/search/joblist.json?{qs}",
        method="GET",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": referer,
            "x-requested-with": "XMLHttpRequest",
        },
    )
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    if r.get("status") != 200:
        return {"ok": False, "error": f"status={r.get('status')}",
                "body": r.get("body", "")[:500]}
    data = json.loads(r["body"])
    if data.get("code") != 0:
        return {"ok": False, "code": data.get("code"),
                "message": data.get("message"), "raw": data}
    jobs = data.get("zpData", {}).get("jobList") or []
    return {
        "ok": True, "count": len(jobs), "jobs": jobs,
        "_persist": "boss_jobs",  # 自动持久化到 storage
        "items": [{"query": query, "page": page, **j} for j in jobs],
    }


# ─────────────────── greet ───────────────────

async def greet(sess: BrowserSession, security_id: str = "", job_id: str = "",
                lid: str = "", query: str = "", city: int = 101020100) -> dict:
    """对一个职位发起打招呼。需要 security_id / job_id / lid。"""
    qs = urllib.parse.urlencode({
        "securityId": security_id, "jobId": job_id, "lid": lid,
        "_": int(time.time() * 1000),
    })
    referer = (
        f"https://www.zhipin.com/web/geek/jobs"
        f"?query={urllib.parse.quote(query)}&city={city}"
    )
    r = await sess.fetch(
        f"https://www.zhipin.com/wapi/zpgeek/friend/add.json?{qs}",
        method="POST",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.zhipin.com",
            "Referer": referer,
            "x-requested-with": "XMLHttpRequest",
        },
        body="sessionId=",
    )
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    try:
        data = json.loads(r.get("body", ""))
    except Exception:
        return {"ok": False, "raw": r.get("body", "")[:500]}
    persist = {
        "_persist": "boss_greetings",
        "security_id": security_id, "job_id": job_id, "query": query,
        "code": data.get("code"), "message": data.get("message"),
        "data": data.get("zpData", {}),
    }
    return {"ok": True, "data": data, **persist}


# ─────────────────── batch greet ───────────────────

async def auto_greet(sess: BrowserSession, query: str = "算法工程师",
                     count: int = 3, city: int = 101020100,
                     interval: float = 5.0, page: int = 1) -> dict:
    """搜 + 批量打招呼。"""
    s = await search(sess, query=query, city=city, page=page)
    if not s.get("ok"):
        return s
    jobs = s["jobs"][:count]
    results = []
    for i, j in enumerate(jobs):
        sid = j.get("securityId")
        jid = j.get("encryptJobId") or j.get("jobId")
        lid = j.get("lid", "")
        if not (sid and jid):
            results.append({"job": j.get("jobName"), "skipped": True})
            continue
        r = await greet(sess, security_id=sid, job_id=jid, lid=lid,
                        query=query, city=city)
        results.append({
            "job": j.get("jobName"), "boss": j.get("brandName"),
            "ok": r.get("ok"), "code": r.get("data", {}).get("code"),
        })
        if i < len(jobs) - 1:
            import asyncio
            await asyncio.sleep(interval)
    return {"ok": True, "results": results}


# ─────────────────── debug ops ───────────────────

async def list_chats(sess: BrowserSession, page: int = 1, size: int = 50) -> dict:
    """获取与 boss 们的聊天列表（含 last 消息、未读数、boss 信息）。"""
    r = await sess.fetch(
        "https://www.zhipin.com/wapi/zprelation/friend/getGeekFriendList.json",
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": "https://www.zhipin.com/web/geek/chat",
        },
        body=f"page={page}&size={size}",
    )
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    data = json.loads(r["body"])
    if data.get("code") != 0:
        return {"ok": False, "code": data.get("code"), "message": data.get("message")}
    chats = (data.get("zpData") or {}).get("result") or []
    # 简化字段，方便落表
    items = [{
        "encrypt_boss_id": c.get("encryptBossId"),
        "boss_name": c.get("name"),
        "boss_title": c.get("title"),
        "brand": c.get("brandName"),
        "encrypt_job_id": c.get("encryptJobId"),
        "job_id": c.get("jobId"),
        "last_msg": c.get("lastMsg"),
        "last_time": c.get("lastTime"),
        "last_ts": c.get("lastTS"),
        "unread": c.get("unreadMsgCount"),
        "chat_status": c.get("chatStatus"),
        "from_me": (c.get("lastMessageInfo") or {}).get("fromId"),
        "to": (c.get("lastMessageInfo") or {}).get("toId"),
        "msg_status": (c.get("lastMessageInfo") or {}).get("status"),
        "filtered": c.get("isFiltered"),
        "security_id": c.get("securityId"),
    } for c in chats]
    return {
        "ok": True, "count": len(items), "chats": items,
        "_persist": "boss_chats", "items": items,
    }


async def get_history_msg(sess: BrowserSession, boss_id: str = "",
                          max_msg_id: int = 0, count: int = 30) -> dict:
    """拉某个 boss 的历史聊天消息。boss_id = encryptBossId。"""
    if not boss_id:
        return {"ok": False, "error": "需要 boss_id (encryptBossId)"}
    r = await sess.fetch(
        f"https://www.zhipin.com/wapi/zpchat/geek/historyMsg"
        f"?bossId={boss_id}&maxMsgId={max_msg_id}&count={count}",
        headers={"Accept": "application/json", "Referer": "https://www.zhipin.com/web/geek/chat"},
    )
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    data = json.loads(r["body"])
    return {"ok": data.get("code") == 0, "code": data.get("code"),
            "data": data.get("zpData", {})}


async def get_cookie(sess: BrowserSession) -> dict:
    return {"ok": True, "cookie": await sess.cookie()}


async def list_industries(sess: BrowserSession, flat: bool = True) -> dict:
    """从 Boss 拉权威行业代码列表。

    Args:
        flat: True 拍平成一维 list；False 保留 二级嵌套结构

    返回字段:
        互联网/AI (100000)
          ├─ 互联网 (100020)
          ├─ 电子商务 (100001)
          ├─ 计算机软件 (100021)
          ...
        电子/通信/半导体 (101400)
          └─ 半导体/芯片 (101405)
          ...
    """
    r = await sess.fetch("https://www.zhipin.com/wapi/zpCommon/data/industry.json")
    if not r.get("ok") or r.get("status") != 200:
        return {"ok": False, "error": "fetch failed", "raw": r}
    data = json.loads(r["body"])
    if data.get("code") != 0:
        return {"ok": False, "code": data.get("code"), "message": data.get("message")}
    z = data.get("zpData") or []

    if not flat:
        # 保留嵌套：name/code + children
        nested = [{
            "name": top.get("name"), "code": top.get("code"),
            "children": [{"name": s.get("name"), "code": s.get("code")}
                         for s in (top.get("subLevelModelList") or [])],
        } for top in z]
        return {"ok": True, "count_top": len(nested), "industries": nested}

    # flat: 一维 list, 含 parent
    out: list[dict] = []
    for top in z:
        out.append({
            "name": top.get("name"), "code": top.get("code"),
            "parent": None, "is_top": True,
        })
        for s in top.get("subLevelModelList") or []:
            out.append({
                "name": s.get("name"), "code": s.get("code"),
                "parent": top.get("name"), "is_top": False,
            })
    return {"ok": True, "count": len(out), "industries": out}


async def list_cities(sess: BrowserSession, hot_only: bool = True) -> dict:
    """从 Boss 拉权威城市代码列表。

    Args:
        hot_only: True 只返回热门城市；False 返回全国所有城市（含区县, 数据量大）
    """
    r = await sess.fetch("https://www.zhipin.com/wapi/zpCommon/data/city.json")
    if not r.get("ok") or r.get("status") != 200:
        return {"ok": False, "error": "fetch failed", "raw": r}
    data = json.loads(r["body"])
    if data.get("code") != 0:
        return {"ok": False, "code": data.get("code"), "message": data.get("message")}
    z = data.get("zpData", {})
    if hot_only:
        items = [{"name": c["name"], "code": c["code"], "tel_code": c.get("cityCode")}
                 for c in (z.get("hotCityList") or [])]
        return {"ok": True, "count": len(items), "cities": items}
    # 全部 (含区县)
    out: list[dict] = []
    def walk(node, parent=""):
        if isinstance(node, dict):
            n = node.get("name")
            c = node.get("code")
            if n and c:
                out.append({"name": n, "code": c, "parent": parent})
            for v in node.values():
                walk(v, n or parent)
        elif isinstance(node, list):
            for x in node:
                walk(x, parent)
    walk(z.get("cityList") or [])
    return {"ok": True, "count": len(out), "cities": out}


async def gen_stoken(sess: BrowserSession, seed: str = "", ts: int = 0) -> dict:
    """直接调浏览器算 stoken（debug 用）。"""
    if ts == 0:
        ts = int(time.time() * 1000)
    return await sess.bus.send("gen_stoken", seed=seed, ts=ts)


async def search_pages(sess: BrowserSession, query: str = "", city: int = 101020100,
                       pages: int = 5, interval: float = 2.0,
                       page_size: int = 30) -> dict:
    """批量翻页搜索. 每翻一页 sleep interval 秒. 所有结果自动落 storage.

    Args:
        query: 关键词
        city: 城市代码 (101020100=上海, 101010100=北京, 101280100=广州...)
        pages: 翻几页
        interval: 每页间隔秒数（防风控）
        page_size: 每页几条
    """
    import asyncio
    all_jobs: list = []
    pages_done = 0
    for p in range(1, pages + 1):
        r = await search(sess, query=query, city=city, page=p, page_size=page_size)
        if not r.get("ok"):
            return {
                "ok": False, "page_failed": p,
                "got_so_far": len(all_jobs), "code": r.get("code"),
                "message": r.get("message"),
            }
        jobs = r.get("jobs") or []
        if not jobs:
            break
        all_jobs.extend(jobs)
        pages_done = p
        if p < pages:
            await asyncio.sleep(interval)
    return {
        "ok": True,
        "total": len(all_jobs),
        "pages_done": pages_done,
        # 自动落 storage (走 pipeline)
        "_persist": "boss_jobs",
        "items": [{"query": query, "city": city, "page_count": pages_done, **j} for j in all_jobs],
    }


async def greet_selected(sess: BrowserSession, jobs: list = None,
                         interval: float = 5.0, query: str = "",
                         city: int = 101020100) -> dict:
    """对一组手动挑选的职位批量打招呼。

    jobs: list of {securityId, encryptJobId|jobId, lid, jobName, brandName}
    """
    if not jobs:
        return {"ok": False, "error": "jobs 为空"}
    import asyncio
    results = []
    for i, j in enumerate(jobs):
        sid = j.get("securityId")
        jid = j.get("encryptJobId") or j.get("jobId")
        lid = j.get("lid", "")
        name = j.get("jobName", "")
        brand = j.get("brandName", "")
        if not (sid and jid):
            results.append({"job": name, "ok": False, "error": "missing id"})
            continue
        r = await greet(sess, security_id=sid, job_id=jid, lid=lid,
                        query=query, city=city)
        d = r.get("data", {})
        results.append({
            "job": name, "brand": brand,
            "ok": r.get("ok") and d.get("code") == 0,
            "code": d.get("code"),
            "message": d.get("message", ""),
        })
        if i < len(jobs) - 1:
            await asyncio.sleep(interval)
    success = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "total": len(jobs), "success": success, "results": results}


# 暴露给 plugin
BOSS_OPERATIONS = {
    "search": search,
    "search_pages": search_pages,
    "greet": greet,
    "greet_selected": greet_selected,
    "auto_greet": auto_greet,
    "list_chats": list_chats,
    "get_history_msg": get_history_msg,
    "list_cities": list_cities,
    "list_industries": list_industries,
    "get_cookie": get_cookie,
    "gen_stoken": gen_stoken,
}
