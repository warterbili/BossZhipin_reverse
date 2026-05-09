# 插件指南

## 加新站点（约 100 行）

新建 `sites/<sitename>/` 目录：

```
sites/example/
├── __init__.py        ← 主入口，定义 ExamplePlugin
├── patches.py         ← 反调试函数签名（regex）
├── operations.py      ← 业务操作（搜索/动作/查询）
└── injection.js       ← 注入到该站页面的 JS（可选）
```

### 1. 写 `__init__.py`

```python
from sites._base import SitePlugin, JsPatch, HtmlInject, HealthCheckResult
from .patches import EXAMPLE_PATCHES
from .operations import EXAMPLE_OPERATIONS
from pathlib import Path
import time, re, requests


class ExamplePlugin(SitePlugin):
    name = "example"                                # 唯一标识
    domains = ["example.com"]                       # 哪些域名归这个 plugin 管
    patches = EXAMPLE_PATCHES                       # mitm 要 patch 的 JS 函数
    injections = [
        HtmlInject(
            url_pattern="example.com",
            script="<script>" + (Path(__file__).parent / "injection.js").read_text() + "</script>",
            inject_marker="__EXAMPLE_LOADED__",
        ),
    ]

    def operations(self):
        return EXAMPLE_OPERATIONS

    def health_check(self, _):
        # 自己判断 patches 是否还匹配最新 JS
        ts = time.time()
        ok, miss = [], []
        try:
            js = requests.get("https://example.com/main.js", timeout=10).text
            for p in self.patches:
                (ok if p.pattern.search(js) else miss).append(p.name)
        except Exception:
            return HealthCheckResult(self.name, False, ts, fix_prompt="拉 JS 失败")
        return HealthCheckResult(
            site=self.name, ok=len(miss) == 0, timestamp=ts,
            patches_ok=ok, patches_missing=miss,
            fix_prompt="" if not miss else f"丢失 {miss}, 重新跑 analysis 找新签名",
        )


PLUGIN = ExamplePlugin()                            # 必须导出 PLUGIN
```

### 2. 写 `patches.py`

```python
import re
from sites._base import JsPatch

EXAMPLE_PATCHES = [
    JsPatch(
        name="anti_debug_check",
        pattern=re.compile(r"function\s+evilCheck\s*\(\s*\)\s*\{var\s+_=window"),
        replacement_body="{}",     # 函数体清空
        notes="检测 DevTools 的关键函数",
    ),
]
```

`pattern` 必须能匹配到 `function NAME() {` 的开头位置。匹配后 mitm 用括号配对找到 `}`，把整段函数体替换成 `replacement_body`。

### 3. 写 `operations.py`

```python
from core.rpc import BrowserSession
import json, urllib.parse


async def search(sess: BrowserSession, query: str = "", **kw) -> dict:
    """通过浏览器发请求，返回结果。"""
    qs = urllib.parse.urlencode({"q": query})
    r = await sess.fetch(
        f"https://example.com/api/search?{qs}",
        headers={"Referer": "https://example.com/", "Accept": "application/json"},
    )
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    data = json.loads(r["body"])
    return {
        "ok": True,
        "items": data.get("items", []),
        "_persist": "example_items",   # 自动存到 storage 的 example_items 表
    }


EXAMPLE_OPERATIONS = {"search": search}
```

每个 operation 是 `async def f(sess: BrowserSession, **kwargs)`，返回 `dict`。如果 dict 含 `_persist=table_name` 字段，server 会把 `items` 写到指定 table（先过 pipeline）。

### 4. 写 `injection.js`（可选）

仅当需要把目标站的某个对象暴露到顶层时。看 [`sites/boss/injection.js`](../sites/boss/injection.js) 的例子（暴露 iframe 里的 `ABC` 加密类）。

可以在脚本里注册自定义 RPC op 到 `window.__MITMRPC_OPS__`：

```js
window.__MITMRPC_OPS__.compute_token = function(task) {
  return { ok: true, token: window.__SOMETHING__.compute(task.input) };
};
```

然后 Python 通过 `sess.bus.send("compute_token", input=...)` 调它。

### 5. 重启 server，CLI 验证

```powershell
# 重启 server
python cli.py go

# 验证 plugin 加载
python cli.py sites
# 应该看到 example 出现在列表

python cli.py op example search query=test
```

---

## 加新存储后端

```python
# storage/redis_storage.py
import json
from ._base import Storage, register

@register("redis")
class RedisStorage(Storage):
    def __init__(self, url: str = "redis://127.0.0.1:6379/0"):
        import redis
        self.r = redis.from_url(url)

    def write(self, table, record):
        self.r.lpush(f"mitmrpc:{table}", json.dumps(record, ensure_ascii=False))

    def read(self, table, limit=100, **f):
        items = self.r.lrange(f"mitmrpc:{table}", 0, limit - 1)
        return [json.loads(x) for x in items]
```

放到 `storage/redis_storage.py` 就被自动注册（`storage/__init__.py` 里 `from . import *` 触发）。

`cli.py storage backends` 会列出来；`cli.py storage use redis --url redis://...` 切换。

---

## 加新 pipeline 钩子

`pipelines/` 下任意 `.py` 文件，使用 `@on()` 装饰器。

```python
# pipelines/my_processor.py
from pipelines import on
import requests, csv, time

# 1. 过滤记录
@on("record", table="example_items")
def drop_old(record):
    if time.time() - record.get("created_at", 0) > 86400 * 7:
        return None  # 一周以上的丢掉
    return record

# 2. 转换记录
@on("record")  # 不指定 table = 所有 record 都过
def add_metadata(record):
    record["_processed_by"] = "my_processor"
    return record

# 3. 副作用（不丢/不改原 record）
@on("greet:after")
def push_to_dingtalk(result):
    if result.get("ok"):
        requests.post("https://oapi.dingtalk.com/...", json=result)
    return result

# 4. 监听抓包流
@on("capture")
def log_to_csv(record):
    if "/api/" in record.get("url", ""):
        with open("./api_log.csv", "a") as f:
            csv.writer(f).writerow([record["ts"], record["method"], record["url"]])
    return record
```

**支持的事件**：
- `record:<table>` `record:*` `record` —— 存储前
- `capture` —— mitm 抓到新请求
- `<op_name>:after` —— operation 完成（如 `search:after`、`greet:after`）

返回值：
- `None` → 丢弃（仅对 `record` 生效）
- `dict` → 替换原数据继续
- 其它 → 原样继续

放完 `.py` 后 `cli.py pipeline reload` 让 server 重新加载。
