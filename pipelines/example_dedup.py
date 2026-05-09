"""示例: 去重 — 已经招呼过的 jobId 不再重复处理。"""
from pipelines import on

# 进程内缓存 (重启会丢)。要持久化的话换成 sqlite。
_seen_jobs: set[str] = set()
_seen_greeted: set[str] = set()


@on("record", table="boss_jobs")
def dedup_jobs(record: dict):
    jid = record.get("encryptJobId") or record.get("jobId")
    if jid and jid in _seen_jobs:
        return None  # 已经存过, 跳过
    if jid:
        _seen_jobs.add(jid)
    return record


@on("record", table="boss_greetings")
def dedup_greetings(record: dict):
    jid = record.get("job_id")
    if jid and jid in _seen_greeted:
        return None
    if jid:
        _seen_greeted.add(jid)
    return record
