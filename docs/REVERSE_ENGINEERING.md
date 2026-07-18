# 反爬逆向方法论

> 基于 Boss 直聘的实战，提炼的通用方法论。
> **不在本仓库放任何目标站的源代码** —— 你需要自己去 `analysis/` 文件夹本地下载。

## 目标站常见反爬层

```
┌──────────────────────────────────────────┐
│  L1: 反调试 (主线威胁)                     │
│   · DevTools 探测 (window 尺寸 / console)  │
│   · debugger 死循环 (DevTools 暂停)        │
│   · 检测到就 redirect / OOM 攻击 / logout │
├──────────────────────────────────────────┤
│  L2: 请求签名                              │
│   · 每请求带 token (动态生成)              │
│   · token 算法在混淆过的 JS 里             │
│   · 服务端可主动让 token 失效要求重算       │
├──────────────────────────────────────────┤
│  L3: 浏览器指纹                            │
│   · TLS / sec-ch-ua / Canvas / WebGL ...  │
│   · 需要真实浏览器才能完美匹配             │
├──────────────────────────────────────────┤
│  L4: 行为分析                              │
│   · 鼠标轨迹、点击间隔、滚动模式            │
│   · 通常作为风控信号而不是硬拦              │
└──────────────────────────────────────────┘
```

## mitm-rpc 的破法

| 层 | 我们的策略 |
|---|---|
| L1 反调试 | **mitm patch JS**，把检测函数体清空 |
| L2 签名 | **借浏览器自己算** (RPC + injection 暴露算法对象) |
| L3 指纹 | **不伪造**，用真实 Chrome |
| L4 行为 | 节流 + 间隔（人手式操作） |

---

## 实战流程：定位反调试函数

以 Boss 的 `Bm` 为例。**完全离线分析**，不和反爬碰头。

### Step 1. 拉到目标站的 main.js

```bash
curl https://target/main.js > analysis/main.js
```

通常 main.js 数百 KB 到几 MB，混淆过。

### Step 2. 用关键字快速定位反调试

反调试函数有几个**绕不开的副作用**，肯定会出现：
- `window.open("", "_self")` — 把页跳到 about:blank
- `window.close()` — 关 tab
- `history.back()` — 退回上页
- `document.body.innerHTML = ""` — 清屏
- `new Array(1e9)` — OOM 攻击

但这些都被字符串解码器混淆了，不会字面出现 `"_self"`。所以转换搜索策略：

**搜结构而非字面**。比如 `Bm` 的特征：
```js
function Bm(){var e,t,n=Rm(),i=window[XXX(Om)]&&"[object HTMLDocument]"===...
```

`XXX` 是混淆解码器（可能叫 L/z/A...）。这种结构稳定。正则：
```python
r"function\s+Bm\s*\(\s*\)\s*\{var\s+e,\s*t,\s*n\s*=\s*Rm\s*\(\s*\)\s*,\s*i\s*=\s*window\["
```

### Step 3. 反混淆字符串解码器

混淆代码里 `window[L("c:Jwcu>;")]` 这种。L 是解码函数。

找它：在 main.js 里搜 `function L(e){` 或 `var L = function(e){`，找带 `charCodeAt` / `fromCharCode` / `atob` / 自定义字母表的小函数。

复刻它的逻辑用 Python 跑一遍，把 main.js 里所有 `L("...")` 调用都解码出来 → 你就能读出反调试函数到底在干啥了。

### Step 4. patch 它

mitm 拦到 main.js 时，用括号配对找到函数体边界，整段替换为 `{}`。

```python
# sites/<site>/patches.py
JsPatch(
    name="anti_debug_main",
    pattern=re.compile(r"function\s+Bm\s*\(\s*\)\s*\{var\s+e,\s*t,\s*n\s*=\s*Rm\s*\(\s*\)\s*,\s*i\s*=\s*window\["),
    replacement_body="{}",
)
```

`core/mitm_addon.py` 自动用 `_find_balanced_end` 找函数尾。

### Step 5. 反爬升级处理

每次目标站改了 JS，签名可能失配。健康检查会发现：
```bash
python cli.py health boss
# patches_missing=[Bm@current-js] 或 [XCID-es6@spa-bundles]
```

这时按 `detail.downloaded_urls` 下载失配的当前 bundle（带 `SKILL.md`）喂给 AI，它能快速找出新 pattern。

---

## 实战流程：让浏览器算签名

以 Boss 的 `__zp_stoken__` 为例。

### 怎么发现

1. 抓包看一个失败的接口，发现响应：
   ```json
   {"code":37,"message":"您的环境存在异常","zpData":{"seed":"...","ts":...,"name":"2b21582d"}}
   ```
2. 读未混淆的 main.js（其它部分），找到 `setGatewayCookie` / `__zp_stoken__` 字眼附近：
   ```js
   loadGatewayScript(SECURITY_SCRIPT_PATH + name + ".js", () => {
     a = s.contentWindow.ABC
     i = (new a).z(seed, parseInt(ts) + 60*(480 + getTimezoneOffset())*1e3)
     Cookie.set("__zp_stoken__", i, ...)
   })
   ```
3. 关键：`s` 是个 iframe，ABC 是 iframe 加载的 `<security_name>.js` 在 iframe window 上注册的类。算法在 ABC.z()，但**重度混淆 + 控制流平坦化**，纯算几乎不可能。

### 怎么破

不解算法。直接**借浏览器**：

1. mitm 注入 `injection.js` 到目标站页面，每次扫描 iframe，把 `iframe.contentWindow.ABC` 暴露到 `window.__SITE_ABC__`
2. mitm 同时注入 RPC poller，注册 op `gen_stoken`：
   ```js
   window.__MITMRPC_OPS__.gen_stoken = function(task) {
     return { token: (new window.__SITE_ABC__).z(task.seed, task.ts) };
   };
   ```
3. Python 通过 `sess.bus.send("gen_stoken", seed=..., ts=...)` 拿 token

零算法逆向，浏览器替你跑。

### seed 是怎么来的（已实测确认）

- **seed 是服务端生成、下发的，不是客户端算的。** 证据：纯 Python（无浏览器、无 JS）发请求，
  在 `code:37` 响应体里直接收到 `zpData.{seed, name, ts}`（`name` = 当前 security-js 文件名，会轮换）。
- 浏览器把这份 37 响应**缓存进 `localStorage['passport_config']`**；之后主动刷新 token 时从缓存读
  seed，**不必每次再发 37**（正常浏览几乎抓不到 37）。
- **一个 seed 约可复用 5 次**（实测 3/3：前 5 个 token 被接受，第 6 起 `code:37`），用满后再触发一次
  37 拿新 seed。
- `ABC.z(seed, ts)` 把服务端 seed **原样**用，内部再掺 canvas/WebGL 设备指纹 + 随机数，所以同一
  `(seed, ts)` 每次输出不同 token（防重放）。

### ⚠️ cookie 编码（最容易踩、也最该写进项目的坑）

`z()` 产出的 token **含 `+` 和 `/`**。浏览器原生 `Cookie.set` 存进 cookie 的是 **URL 编码后**的值
（`+`→`%2B`, `/`→`%2F`）。**若把裸 token 直接塞 cookie**，服务端 `URL-decode` 会把 `+` 解成**空格** →
token 损坏 → `code:37「您的环境存在异常」`。

实测隔离（同一 token，只改编码）：

| cookie 写法 | 结果 |
|---|---|
| 裸 token（不编码） | `code:37`（3/3） |
| `encodeURIComponent(token)` / `quote(token, safe='')` | `code:0`，拿到数据 |

所以：
- **走 `fetch_url`（浏览器自己发请求）** → 浏览器原生处理编码，**无需关心**。这是本项目数据路径，最省心。
- **在浏览器之外用 token**（自己 `requests` 发） → 入 cookie 前**必须 URL 编码**。`gen_stoken` 已直接
  返回 `token_encoded` 供外部使用。一个可跑通的例子见 [`tests/gen_external_request.py`](../tests/gen_external_request.py)。

> 调试经验：当“浏览器能成、自己 replay 不成”时，**第一步永远是把两边真实请求/cookie 逐字节 diff** —
> 这个编码差异（`…/` vs `…%2F`）一眼就能看出来，别先去猜算法/参数。

---

## 工具清单

`analysis/` 里推荐放（**仅本地**）：

```
analysis/
├── main.js                 目标站主 JS（curl 下来）
├── main_v<old>.js          上次的版本，diff 看变化
├── find_bm.py              你写的字符串/regex 搜索脚本
├── decode_strings.py       字符串解码器复刻
└── notes.md                逆向笔记
```

`.gitignore` 已经排除整个 `analysis/`，不会上传。
