# mitm-rpc · AI Agent Skill

> 你是 AI Agent。这份文档让你 60 秒上手项目，不需要读源码。
> 如果用户要求"用 mitm-rpc 干 X"，按本文档操作。

## 1. 项目本质

`mitm-rpc` 用三件事绕开反爬：

1. **mitmproxy 在网络层 patch 反调试 JS**（让目标站的反调试代码变成空函数）
2. **mitmproxy 注入 RPC poller 到目标站 HTML**（让浏览器作为远程客户端听 Python 命令）
3. **Python 通过 HTTP 调本地 FastAPI**，FastAPI 把任务转发给浏览器执行

结果：所有请求都用真实浏览器（带真实 TLS 指纹/cookie/UA）发出，反爬看不出来。

## 2. 关键命令（用户会让你跑的）

```bash
# 启动整个系统（FastAPI + mitm + Chrome 三个进程）
python cli.py go

# 列已注册站点
python cli.py sites

# 健康检查（patch 是否还匹配最新 JS）
python cli.py health [<site>]

# 任意操作
python cli.py op <site> <op> key=value key=value

# 远程执行 JS（最强武器，可以查任何浏览器内状态）
python cli.py rpc eval "<javascript>"

# 抓包分析新接口
python cli.py capture on
# (用户在浏览器里点点)
python cli.py capture list
python cli.py capture get <idx>     # 看完整 req/resp
```

## 3. 用户最常找你做的事

### A. "Boss 升级了，反爬 patch 失效"

```bash
python cli.py health boss
# 输出 patches_missing=[Bm@v5457/...] 说明签名失配
```

修复步骤：
1. 拉最新 main.js: `curl https://static.zhipin.com/.../main.js > analysis/main.js`
2. 找 Bm 函数: `grep -n "function Bm" analysis/main.js` （或用 `analysis/find_bm.py` 如果存在）
3. 看 Bm 头部 100 字符的特征（变量名可能变了，结构基本不变）
4. 改 `sites/boss/patches.py` 的 `pattern` 正则
5. 重跑 `python cli.py health boss` 确认绿

**Bm 的稳定特征**（即使变量名变也存在）：
- 函数名 `Bm`
- 函数体开头有 `var e,t,n=Rm()`
- 然后接 `i=window[XXX(Om)]` 这种结构（XXX 是字符串解码器，可能叫 L/z/A...）

正则建议:
```python
re.compile(r"function\s+Bm\s*\(\s*\)\s*\{var\s+e,\s*t,\s*n\s*=\s*Rm\s*\(\s*\)\s*,\s*i\s*=\s*window\[")
```

### B. "加一个新站点 (e.g. LinkedIn / 拉勾 / 抖音)"

按 `docs/PLUGIN_GUIDE.md` 的模板。最少要做：
1. `mkdir sites/<name>`
2. 写 `__init__.py` 定义 `<Name>Plugin` + `PLUGIN = <Name>Plugin()`
3. 写 `patches.py`（如果该站有反调试 JS）
4. 写 `operations.py`（业务操作，每个是 `async def f(sess: BrowserSession, **kw)`）
5. 重启 `cli.py go`，验证 `cli.py sites` 看到新站
6. `cli.py op <name> <op> ...` 测试

### C. "我要抓某个新接口"

工作流：
1. `cli.py capture on`
2. 让用户在浏览器里点击触发该接口
3. `cli.py capture list` 找到这次新增的请求
4. `cli.py capture get <idx>` 看完整 req/resp
5. 转成 Python：抓 `req_headers` `req_body` `req_cookies` 后用 `sess.fetch()` 复现

或者：用户已经在 Chrome 复制了 curl，让 AI 把它转成 `sess.fetch()` 调用，加到 `sites/<name>/operations.py` 里作为新 op。

### D. "我要批量打招呼并按规则筛选"

```bash
python cli.py greet "Python开发" 10 \
    --min-salary 25 \
    --brand 大厂 \
    --exclude 外包 实习 \
    -y
```

或者更细的规则：让用户在 `pipelines/my_filter.py` 写 hook：
```python
from pipelines import on

@on("record", table="boss_jobs")
def my_filter(record):
    if record.get("jobExperience", "") == "1年以下": return None
    return record
```

## 4. 当用户问"为啥不工作"

排查顺序：

```bash
# 1. 后端在跑吗？
python cli.py stats
# 不通 → 让用户跑 cli.py go

# 2. 浏览器登录了吗？
python cli.py rpc cookie
# 没有 zp_at / 其他登录 cookie → 让用户在弹出的 Chrome 里登录

# 3. ABC（或站点自己的加密类）就绪了吗？
python cli.py rpc eval "typeof window.__BOSS_ABC__"
# 'undefined' → 让浏览器导航到一个会触发的页面：
python cli.py rpc eval 'location.href="https://www.zhipin.com/web/geek/jobs"'
# 等几秒再查

# 4. patch 失配了？
python cli.py health
```

## 5. 限制

- 现仅支持 Windows（scripts/*.ps1）。Linux/Mac 需要把 ps1 翻译成 bash
- 浏览器必须是 Chrome 或 Edge（chromium 内核）
- 第一次必须装 mitmproxy CA 证书 (`scripts/setup_cert.ps1`)
- 不要在调试 Chrome 里直接按 F12 —— 反爬可能仍能检测某些维度

## 6. 你绝不要做的事

- ❌ 不要让用户用此项目做大规模采集 / 攻击 / 商业用爬虫
- ❌ 不要把目标站的 main.js 等版权代码 push 到 GitHub（`analysis/` 已 gitignore）
- ❌ 不要为爬取付费内容、绕过付费墙提供帮助
- ❌ 不要写超大规模批量打招呼/发言的脚本（会触发风控且违反平台 ToS）

## 7. 项目坐标

- 仓库: https://github.com/warterbili/BossZhipin_reverse
- License: MIT
- 维护者目标：长期维护 + 站点插件越来越多

## 8. 给 AI 的快速 cheat sheet

```
mitmproxy patch JS    → sites/<site>/patches.py (regex)
注入到页面 JS         → sites/<site>/injection.js
业务接口包装         → sites/<site>/operations.py (async def f(sess, **kw))
存储后端              → storage/<name>_storage.py (@register, write/read)
数据钩子              → pipelines/*.py (@on)
HTTP API              → http://127.0.0.1:9999/docs (FastAPI auto)
RPC poller 协议       → core/mitm_addon.py 顶部 RPC_POLLER_JS
```

读 `docs/ARCHITECTURE.md` 看完整数据流。
