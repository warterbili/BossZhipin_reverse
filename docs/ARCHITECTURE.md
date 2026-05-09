# Architecture

## 核心思想

**别和反爬硬刚，让目标站的真实浏览器替你发请求。**

反爬最难解的部分（TLS 指纹 / sec-ch-ua / 动态生成的 token / 同源策略）都由真实浏览器自然处理。我们只在网络层把反调试代码 patch 掉（让 F12 / 浏览器自动化能跑），其他什么都不假装。

## 数据流

```
        [ Python 脚本 / CLI ]                      [ 真实浏览器 ]
                │                                        │
                │ 1. POST /rpc/req                       │
                │   {op:"fetch_url", url, ...}           │
                ▼                                        │
       ┌──────────────────┐                              │
       │  FastAPI :9999   │                              │
       │  · 把任务放队列    │                              │
       │  · 等结果         │                              │
       └────────┬─────────┘                              │
                │                                        │
                │ 2. asyncio Queue.put                   │
                │                                        │
                │       浏览器轮询 ←─── 3. GET /rpc/poll ──┤
                │                                        │
                │       4. 浏览器执行 ─→ fetch (带真实
                │       cookie/TLS 指纹) ──→ 目标站点
                │                                        │
                │       5. fetch 响应                     │
                │                                        │
                │       6. POST /rpc/result/{id} ←──────┤
                │       {ok, status, body, headers}      │
                ▼                                        │
       ┌──────────────────┐                              │
       │  resolve Future  │                              │
       └────────┬─────────┘                              │
                │                                        │
                │ 7. 返回给调用方                          │
                ▼                                        │
        [ Python 拿到响应数据 ]
```

## 关键组件

### `core/mitm_addon.py` — 网络层

mitmproxy addon。开机时扫 `sites/` 加载所有插件。每个 HTTP 响应：
- **JS 文件**：跑插件的 `patches`，匹配的函数体置空（关键反调试代码 → 无操作）
- **HTML 文件**：注入两段 script 到 `<head>`：
  - 通用 RPC poller（拉任务、执行 fetch/eval、回传结果）
  - 站点专属脚本（如 Boss 的 ABC 桥接）
- **业务接口**：抓包 → POST 给 server → 走 pipeline + SSE 推送

### `core/server.py` — FastAPI 服务

唯一对外接口。提供：
- `/rpc/req` `/rpc/poll` `/rpc/result/{id}` —— 浏览器 ↔ Python RPC 桥
- `/api/sites` `/api/sites/<name>/op/<op>` —— 调用插件操作
- `/api/health/<name>` —— 健康检查（patch 是否还匹配）
- `/api/capture/*` —— 抓包管理 + SSE 实时流
- `/api/storage/*` —— 切换/读取存储
- `/api/pipelines` —— 看注册的处理器

### `core/rpc.py` — RPC 协议

`RpcBus` 维护任务队列 + 等待中 Future。`BrowserSession` 是业务代码用的代理：
```python
await sess.fetch(url, method, headers, body)  # 浏览器去 fetch
await sess.eval("location.href")              # 远程跑 JS
await sess.cookie()                           # 拿 document.cookie
await sess.bus.send("custom_op", **payload)   # 自定义 op
```

### `sites/<name>/` — 站点插件

每个目标站一个目录。只关注**该站特定的事**：
- `patches.py`: 反调试函数签名（用 regex 匹配）
- `operations.py`: 业务操作（搜、招呼、查详情...）
- `injection.js`: 注入到该站页面的脚本
- `selftest.py` / `__init__.py.health_check()`: 健康检查

### `storage/` — 存储后端

抽象接口：`Storage.write(table, record)` / `Storage.read(table, limit, **filters)`。
内置 `jsonl` / `sqlite` / `csv` / `excel` / `mysql`，加新后端 = 一个文件 + `@register("name")` 装饰器。

### `pipelines/` — 数据处理钩子

事件总线：`@on("record", table="...")`、`@on("capture")`、`@on("greet:after")`...
用户在 `pipelines/` 下放 `.py` 就被自动加载。处理器可以**过滤、转换、转发**记录。

## 启动顺序（`cli.py go`）

1. 启 `core.server:app` (uvicorn :9999)
2. 启 `mitmdump -s core/mitm_addon.py` (:8888)
3. 启 Chrome 实例 (独立 profile + proxy=:8888 + remote-debugging-port=:19222)
4. 等 Chrome 关闭 → 清理两个后台进程

## 反爬升级时

每个 plugin 实现 `health_check()`。它去拉最新 main.js，跑所有 `patches.pattern.search(js)`，任何失配就：
- `health_check()` 返回 `ok=False, patches_missing=[...], fix_prompt="..."`
- `cli.py health` 显示红
- AI 拿 `fix_prompt` + 最新 main.js → 返回新的 patch regex

这是项目"自我修复"能力的核心。
