"""示例: 把所有抓到的请求 + 操作结果转发到外部 webhook。

改 WEBHOOK_URL 后启用，或删掉本文件。
"""
import os

import requests

from pipelines import on

# 想用就改这里。也可以从环境变量读。
WEBHOOK_URL = os.environ.get("MITM_RPC_WEBHOOK_URL", "")


def _post(payload: dict) -> None:
    if not WEBHOOK_URL:
        return  # 未配置就什么都不做
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=2)
    except Exception:
        pass


@on("greet:after")
def post_greet(result: dict):
    _post({"event": "greet", "result": result})
    return result


@on("search:after")
def post_search(result: dict):
    _post({
        "event": "search",
        "count": result.get("count"),
        "first_5": (result.get("jobs") or [])[:5],
    })
    return result


@on("capture")
def post_capture(record: dict):
    """抓包后发到外部 (注意流量大的时候自己过滤，这里默认全发)。"""
    if "wapi" in record.get("url", ""):  # 只发业务接口
        _post({"event": "capture", **record})
    return record
