# BossZhipin Reverse · mitm-rpc

> 把已登录的浏览器变成 RPC 客户端，用来绕过反爬/反调试。**站点无关 · 插件式 · CLI 优先 · AI 友好**。
>
> **本仓库内置 Boss 直聘插件作为完整范例**，架构本身可扩展任意站点（拉勾 / 抖音 / 小红书...）。看 [docs/PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md)。

```
你的脚本  ──HTTP──▶  本地 FastAPI  ──任务队列──▶  浏览器（已登录）  ──fetch──▶  目标站点
                          ▲
                    mitm 在网络层 patch 反调试 JS
                    并注入 RPC poller，让 Python 远程驱动浏览器发请求
```

不解算法、不伪造指纹、**用真实浏览器替你发请求**。所有反爬最难的部分（TLS/sec-ch-ua/cookie 漂移/`__zp_stoken__`）都被原生处理。

**当前内置**：[Boss 直聘](sites/boss/) (search / greet / auto_greet / capture)
**扩展**：写一个 `sites/<name>/` 目录就加了新站点（约 100 行）

---

## ⚡ 5 分钟跑通

```powershell
git clone https://github.com/warterbili/BossZhipin_reverse
cd mitm-rpc

# 一次性安装（venv + mitm CA 证书）
.\scripts\setup.ps1

# 一键启全部 (FastAPI + mitm + Chrome)
.\.venv\Scripts\python cli.py go
```

弹出来的 Chrome 里登录目标站点（**不要按 F12**）。

另开一个终端，开始用：

```powershell
# 搜职位
python cli.py search "算法工程师"

# 搜 + 过滤 + 自动招呼
python cli.py greet "算法工程师" 5 --min-salary 25 --brand 大厂 -y

# 任意 plugin 操作
python cli.py op boss search query=Python city=101020100

# 远程调浏览器
python cli.py rpc eval "Object.keys(window).length"
python cli.py rpc cookie

# 实时看请求流（先 cli.py capture on）
python cli.py capture watch
```

---

## 🎯 CLI 命令全集

```
启动:
  cli.py go                                      一键启 server + mitm + chrome
  cli.py serve                                   只启 FastAPI

业务:
  cli.py sites                                   列站点 + 操作
  cli.py search <query> [--city N --page-size N]
  cli.py greet <query> [N] [--min-salary K --brand X --exclude kw1 kw2 -i -y]
  cli.py op <site> <op> key=val key=val          调任意操作

抓包:
  cli.py capture on / off / status / clear
  cli.py capture list [--limit N --q substring]
  cli.py capture get <idx>                       看完整请求
  cli.py capture watch                           SSE 实时流

远程浏览器:
  cli.py rpc eval "<js>"
  cli.py rpc cookie
  cli.py rpc fetch <url>

存储:
  cli.py storage backends                        看可用后端
  cli.py storage use jsonl                       默认
  cli.py storage use sqlite --path ./data/db.sqlite
  cli.py storage use csv --root ./data/csv
  cli.py storage use mysql --host x --user y --password z --database d
  cli.py storage tables / read <table>

健康:
  cli.py health                                  反爬补丁还匹配最新 JS 吗
  cli.py health <site>

管道（数据处理钩子）:
  cli.py pipeline list                           看注册的处理器
  cli.py pipeline reload                         改了 pipelines/*.py 后重载

stats                                            RPC 计数等
```

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────┐
│  CLI (cli.py) / 第三方脚本 / curl / Postman          │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────────────┐
│  FastAPI (core/server.py, port 9999)                │
│   /api/sites · /api/health · /api/capture           │
│   /api/storage · /api/pipelines                     │
│   /rpc/req · /rpc/poll · /rpc/result                │
│   /docs (auto-generated OpenAPI UI)                 │
└──────────────────┬──────────────────────────────────┘
                   │ asyncio.Queue
┌──────────────────▼──────────────────────────────────┐
│  Browser (Chrome, 独立 user-data-dir)                │
│   - mitm 注入的 RPC poller (poll → exec → return)    │
│   - 站点专属 inject (e.g. Boss 把 ABC 暴露到顶层)     │
│   - 真实 cookie / TLS / UA / sec-ch-ua              │
└──────────────────┬──────────────────────────────────┘
                   │ fetch / xhr
┌──────────────────▼──────────────────────────────────┐
│  mitm (core/mitm_addon.py, port 8888)               │
│   - 加载 sites/* 插件                                 │
│   - patch 反调试 JS (Bm/t() → 空函数)                 │
│   - inject HTML (RPC poller + 站点专属脚本)           │
│   - 抓包推送给 server (走 pipeline + SSE)             │
└──────────────────┬──────────────────────────────────┘
                   │ TLS
                目标站点
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 📁 目录

```
mitm-rpc/
├── cli.py                      ★ 用户主入口
├── core/
│   ├── server.py               FastAPI: RPC + API + Capture
│   ├── mitm_addon.py           mitmproxy addon
│   ├── rpc.py                  浏览器 ↔ python 协议
│   └── browser.py              Chrome 启动器
├── sites/
│   ├── _base.py                SitePlugin ABC
│   └── boss/
│       ├── __init__.py         BossPlugin
│       ├── patches.py          反调试函数签名
│       ├── operations.py       业务操作
│       └── injection.js        注入到 Boss 页面
├── storage/                    存储后端
│   ├── jsonl_storage.py / sqlite / csv / excel / mysql
├── pipelines/                  ★ 数据处理钩子
│   ├── example_filter.py       (示例: 删低薪)
│   ├── example_dedup.py        (示例: 去重)
│   └── example_webhook.py      (示例: 发外部)
├── scripts/
│   ├── setup.ps1               一次性安装
│   ├── doctor.ps1              环境体检
│   └── healthcheck.py          CLI 健康检查
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PLUGIN_GUIDE.md
│   └── REVERSE_ENGINEERING.md
├── SKILL.md                    AI Agent 用文档
└── data/                       运行时（gitignored）
```

---

## 🧩 加新站点

```python
# sites/example/__init__.py
import re
from sites._base import SitePlugin, JsPatch

class ExamplePlugin(SitePlugin):
    name = "example"
    domains = ["example.com"]
    patches = [
        JsPatch(
            name="anti_debug",
            pattern=re.compile(r"function\s+evilCheck\s*\(\)"),
            replacement_body="{}",
        ),
    ]
    def operations(self):
        async def hello(sess, **kw):
            r = await sess.fetch("https://example.com/api")
            return {"ok": True, "data": r}
        return {"hello": hello}
    def health_check(self, _):
        return HealthCheckResult(site=self.name, ok=True, ...)

PLUGIN = ExamplePlugin()
```

完整指南：[docs/PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md)

---

## 🔌 数据钩子（pipelines）

爬到的数据可以走多层处理，用户随便写 .py 文件：

```python
# pipelines/my_filter.py
from pipelines import on

@on("record", table="boss_jobs")
def drop_low_salary(record):
    if salary_k(record["salaryDesc"]) < 20:
        return None  # 丢弃
    return record

@on("greet:after")
def notify_slack(result):
    requests.post("https://hooks.slack.com/...", json=result)
    return result
```

事件: `record:<table>` / `capture` / `greet:after` / `search:after` / `health:fail`

---

## 🩺 反爬升级了？

UI 健康灯红 / `cli.py health` 报 patch 失配时：

1. 把目标站的最新 main.js 喂给任意 AI（Claude/GPT），附上 [`SKILL.md`](SKILL.md)
2. AI 自动定位新签名，给你新的 `JsPatch` 正则
3. 改 `sites/<name>/patches.py` 即可

`SKILL.md` 是为 AI Agent 写的项目说明书 —— 任何 AI 拿到都能上手。

---

## 📜 法律 / 安全

- 仅供学习反爬和**个人合理使用**
- 不要用于大规模采集 / 攻击 / 商业爬虫
- 目标站源代码（main.js 等）不在本仓库，只在你本地 `analysis/` 目录（.gitignore）
- 使用违反目标站用户协议的，后果自负

## License

MIT
