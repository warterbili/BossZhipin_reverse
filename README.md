# BossZhipin Reverse · mitm-rpc

> 把已登录的真实浏览器变成 RPC 执行端，专门用于 Boss 直聘反调试研究与登录态接口验证。**Boss 专项 · mitm 改写 · 浏览器 RPC · AI 可维护**。
>
> 仓库目前只将 **Boss 直聘** 视为支持目标。`SitePlugin` 边界保留为内部组织方式，不代表其他站点已适配或实测。

```
你的脚本  ──HTTP──▶  本地 FastAPI  ──任务队列──▶  浏览器（已登录）  ──fetch──▶  目标站点
                          ▲
                    mitm 在网络层 patch 反调试 JS
                    并注入 RPC poller，让 Python 远程驱动浏览器发请求
```

不解算法、不伪造指纹、**用真实浏览器替你发请求**。所有反爬最难的部分（TLS/sec-ch-ua/cookie 漂移/`__zp_stoken__`）都被原生处理。

**Boss 能力**：search / search_pages / greet / greet_selected / auto_greet / list_chats / get_history_msg / list_cities / list_industries / get_cookie / gen_stoken / capture

> 📖 **想看 Boss 整套防护是怎么逆出来的？** → **[`docs/BOSS_DEEP_DIVE.md`](docs/BOSS_DEEP_DIVE.md)**：
> 反调试七层 + 中和、`__zp_stoken__` 算法、**seed 生命周期（服务端下发 / passport_config 缓存 / ~5 次复用）**、
> **cookie 编码根因**、三种数据获取方案对比、逆向方法论。这是本仓库沉淀的 Boss 反爬技术说明书。

---

## ✅ 当前实测状态

本仓库不是空架子，核心链路已按真实登录态跑通：

| 模块 | 实测结果 |
|---|---|
| mitm TLS | 已能解密 Boss 直聘 HTTPS 流量 |
| 反调试 patch | `Bm` / `Rm` / `XCID` / `XCIT` / console.clear / 内存炸弹当前签名命中；实际改写后的 SEO/SPA bundle 已通过 Node 语法检查 |
| DevTools | 登录后打开 F12，页面不退站、不刷屏、不 OOM |
| RPC | 真实浏览器 `eval` / `cookie` / `fetch_url` 闭环通过 |
| Boss 业务 | search / list_cities / list_industries / list_chats / gen_stoken / greet 均已跑通 |
| 存储与管道 | jsonl / sqlite / csv 写读通过，pipeline 去重/过滤生效 |

`greet` 会真实给招聘者发消息，批量使用前请先确认目标和间隔策略。

---

## ⚡ 5 分钟跑通

```powershell
git clone https://github.com/warterbili/BossZhipin_reverse
cd BossZhipin_reverse

# 一次性安装（venv + mitm CA 证书）
.\scripts\setup.ps1

# 一键启全部 (FastAPI + mitm + Chrome)
.\.venv\Scripts\python cli.py go
```

弹出来的 Chrome 里登录目标站点。首次登录阶段建议先别按 F12；登录完成后如需调试，再打开 DevTools 验证 patch 状态。

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
BossZhipin_reverse/
├── cli.py                      ★ 用户主入口
├── core/
│   ├── server.py               FastAPI: RPC + API + Capture
│   ├── mitm_addon.py           mitmproxy addon
│   ├── patching.py              运行时/验证器共用的 JS patch 引擎
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
│   ├── healthcheck.py          当前 bundle 签名健康检查
│   └── validate_boss_patches.py 实际改写 + Node 语法验证
├── docs/
│   ├── ARCHITECTURE.md
│   ├── BOSS_DEEP_DIVE.md
│   ├── PLUGIN_GUIDE.md
│   └── REVERSE_ENGINEERING.md
├── tests/
│   ├── gen_external_request.py 外部 requests + gen_stoken 示例
│   ├── greet_from_csv.py       从 CSV 批量打招呼示例
│   └── test_*.py               patch/抓包开关/业务语义回归
├── SKILL.md                    AI Agent 用文档
└── data/                       运行时（gitignored）
```

---

## 🧩 为什么仍保留 SitePlugin

`sites/_base.py` 与 `sites/boss/` 的边界用于隔离 Boss 特定的 patch、注入和业务接口，方便独立健康检查与回归。
它是内部代码组织方式，而不是对外承诺的多站点框架。[docs/PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md) 仅作为边界设计参考保留。

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

当前实际触发的事件: `record`（可用 `table=...` 过滤）/ `capture` / `<operation>:after`

---

## ⚠️ 在浏览器之外用 `__zp_stoken__`？先看编码

走本项目主路径（`fetch_url`，**浏览器自己发请求**）时，token 的生成、cookie 编码、TLS 全由浏览器原生处理，
**你什么都不用管**。

但如果你想**自己生成 token 拿到浏览器外面用**（`gen_stoken` + 自己 `requests` 发）：token 里含 `+` 和 `/`，
**入 cookie 前必须 URL 编码**（`encodeURIComponent` / `quote(token, safe='')`），否则服务端把 `+` 解成空格 →
token 损坏 → `code:37`。`gen_stoken` 已直接返回 `token_encoded` 供外部使用。

- seed 来源、缓存、复用次数、编码隔离实验 → [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md)
- 可跑通的外部请求例子 → [`tests/gen_external_request.py`](tests/gen_external_request.py)

> 调试铁律：“浏览器能成、自己 replay 不成”时，**先 byte-diff 两边真实 cookie/请求**，别先猜算法。

---

## 🩺 反爬升级了？

UI 健康灯红 / `cli.py health` 报 patch 失配时：

1. `cli.py health boss` 会先拉当前入口页，自动发现最新 SEO / SPA JS bundle，再逐个检查 patch 签名
2. 把失配的 bundle 下载到本项目 `tmp/boss-analysis/`，连同 [`SKILL.md`](SKILL.md) 交给 AI 定位
3. AI 确认安全/惩罚分支后更新 `sites/boss/patches.py`
4. 运行 `python scripts/validate_boss_patches.py`，验证真实改写和全部 JS 语法
5. 登录后再做注入标记、F12 和只读 Boss 接口回归

`SKILL.md` 是为 AI Agent 写的项目说明书 —— 任何 AI 拿到都能上手。

---

## 📜 法律 / 安全

- 仅供学习反爬和**个人合理使用**
- 不要用于大规模采集 / 攻击 / 商业爬虫
- 目标站源代码（main.js 等）只能临时放在本项目 `tmp/`，不进入 Git
- 使用违反目标站用户协议的，后果自负

## License

MIT
