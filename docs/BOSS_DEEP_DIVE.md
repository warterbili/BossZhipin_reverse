# Boss 直聘 反爬 / 反调试 深度说明书

> 本项目对 boss 直聘（zhipin.com）整套前端防护的逆向沉淀：反调试七层、`__zp_stoken__` token 算法、
> seed 生命周期、cookie 编码根因，以及三种数据获取方案的取舍。所有结论均经实测验证（随机性结论 ≥3 次复现）。
> token / seed 是会话临时数据，文中只用**截断尾部 / 占位**，不写完整值。
>
> 仅供授权安全研究 / 学习交流，禁止用于未授权或违法用途（见 [`docs/法律安全`](../README.md#-法律--安全)）。

---

## 0. 全景图

```
┌─ 反调试层 (main.js / app~* / vendor-*) ──────────────────────────────┐
│  Bm 退站+blur+OOM · Rm 原生篡改检测 · XCID/XCIT devtools探针+刷屏      │
│  console.clear 循环清屏 · 内存炸弹 · Ef 键盘 · 时序检测                 │
│   → mitm 用 sites/boss/patches.py 一套名字稳定的正则全部中和           │
├─ token 层 (zpAegis + 账号专属 security-js) ──────────────────────────┤
│  请求需带 __zp_stoken__ cookie                                        │
│  __zp_stoken__ = new ABC().z(seed, ts校正)   (ABC 在 security iframe) │
│  seed ← 服务端 code:37 下发 → 缓存 localStorage['passport_config']    │
│  token 入 cookie 必须 URL 编码（否则 + → 空格 损坏）                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. 反调试七层（原理 + 中和方式）

反调试**被复制进每个 webpack bundle**（SEO 的 `main.js`、SPA 的 `app~*`/`vendor-*`），minify 名各不同，
但**类方法名 `XCID`/`XCIT` 跨 bundle 共享**，`console.clear`/内存炸弹是结构稳定的表达式 —— 所以
`sites/boss/patches.py` 用**名字稳定的正则**一套覆盖所有 bundle（实测 main.js 命中 30、vendor-1 命中 19）。

| 层 | 检测/攻击 | 中和（patches.py） |
|---|---|---|
| `Bm()` | 检测到 DevTools/原生被 hook → `window.open("","_self")`+`close()`+`history.back()`+注入 blur(20px)/display:none 遮罩 + 上报 `method_modify` + 内存炸弹 | `mode="body"` 清空函数体 |
| `Rm()` | 原生方法篡改检测（`[native code]` toString / `instanceof Location`） | `function Rm(){return;` |
| `XCID()`/`XCIT()` | ~500ms 循环：`createElement("div").__defineGetter__("id",…)` + `console.log` 探针做 devtools 检测，并刷屏 | 两种写法都置空（转译 `key:"XCID",value:function(){` + ES6 `XCID(){`） |
| console flood/clear | `_f/Df/If` 包装 log/table/clear，`jf(){If()}` 被 `setInterval(…,500)` 刷屏+清屏 | 只杀**包装器定义**4 种写法，绝不碰业务 `X.clear()` 调用 |
| 内存炸弹 | `new Array(1eN).fill(…)` / `"x".repeat(1eN)` ×循环×递归，撑爆内存（method_modify 命中后引爆） | `1eN → 1` |
| `Ef` | Ctrl/Cmd+Shift/Alt+I/J 快捷键检测（keyCode 73/74） | （次要，可选补） |
| `__defineSetter__`+`Xm<535` | 时序/帧间隔 devtools 检测 | （次要，可选补） |

### ⚠️ 核心心法：「绕过，别翻转」

`Bm` 的门是 `if(n && i && a && o)` —— 四项**全 true = 环境干净**走安全分支；**else 分支才是惩罚**
（上报 `method_modify` + 内存炸弹）。把门翻成 `if(false)` = **无条件跳进惩罚分支 = 自爆**（内存炸弹是
`else` 里的密集分配 `.fill()` ×循环×递归 + 被全局引用持有 GC 收不掉，几百毫秒 OOM）。
**正确做法是把整个检测函数/方法置空 `return`，门两边都不进。**

### 内存炸弹为什么正常不爆、改门就爆

炸弹是**惩罚分支里的按需分配代码**，平时不执行：真 Chrome 无 hook → `n,i,a,o` 全 true → 走安全分支。
`new Array(1e9)` 单独很便宜（稀疏数组）；真正吃内存的是 `.fill()` 密集化 × 循环 × 递归 × 被持有不回收。

---

## 2. `__zp_stoken__` token 算法

```js
__zp_stoken__ = new ABC().z(seed, parseInt(ts) + 60*(480 + new Date().getTimezoneOffset())*1000)
```

- `ABC` 定义在**账号专属的 security 脚本** `/web/passport/zp/security-js/<rotating-name>.js`
  （`<name>` 会轮换，如 `7c91433f.js`，不是账号 id）。它加载进一个 **iframe**；顶层 `window.ABC` 是
  undefined，要从 `window.frames[i].ABC` 拿。
- 真正调 `(new ABC).z(...)` 的网关 `r()` 在 **`app~2.<hash>.js`**（SPA bundle），**不是 main.js**
  （main.js 也有一份 `setGatewayCookie`/`r`，那是 SEO build 的）。
- `z()` **非确定性**：同 `(seed, ts)` 每次输出不同 token（内部掺 canvas/WebGL 设备指纹 + 随机数）。
  所以服务端不是重算校验，而是验签。
- `z()` 读设备指纹（canvas `fillText`+`toDataURL`、WebGL 厂商/渲染器、屏幕）—— 这也是纯算/补环境难做的
  原因（指纹每天可能切换）。

---

## 3. seed 生命周期（已实测验证）

```
请求无有效 __zp_stoken__ → 服务端返回 code:37 + 下发 seed → 缓存进 localStorage['passport_config']
   → 网关读 seed → new ABC().z(seed, ts) → 生成 token → 入 cookie(URL编码)
   → 一个 seed 约可复用 5 次；token 失效/被flag → 新 37 → 新 seed
```

- **seed 是服务端生成、下发的，不是客户端算的。** 证据：**纯 Python（无浏览器、无 JS）发请求，就在
  `code:37` 响应体里直接收到 `zpData.{seed, name, ts}`**（`name` = 当前 security-js 文件名）。客户端零
  seed 生成逻辑，把服务端 seed **原样**喂给 `z()`。
- **缓存：`localStorage['passport_config']`** 存的就是那份 37 响应（含服务端中文文案“您的环境存在异常.”，
  客户端造不出 → 进一步证明 seed 来自服务端）。主动刷新 token 时从缓存读 seed，**不必每次再发 37**。
- **复用上限 ~5 次**（实测 3/3：第 1–5 个 token 被接受，第 6 起 `code:37`；是次数限制，非时间）。
- **正常浏览几乎抓不到 37**：warm 会话 0 个 `code:37`、缓存 seed 恒定 —— 所以“正常抓包看不到 seed 下发”，
  因为它只在缓存空/过期/被风控时下发一次，之后全靠 `passport_config` 复用。

---

## 4. ⚠️ cookie 编码 —— 最容易踩、也最该记住的坑

`z()` 产出的 token **含 `+` 和 `/`**。浏览器原生 `Cookie.set` 存进 cookie 的是 **URL 编码后**的值
（`+`→`%2B`, `/`→`%2F`）。**若把裸 token 直接塞 cookie**，服务端 URL-decode 会把 `+` 解成**空格** →
token 损坏 → `code:37「您的环境存在异常」`。

实测隔离（**同一 token 值，只改编码**）：

| cookie 写法 | 结果 |
|---|---|
| 裸 token（不编码） | `code:37`（3/3） |
| `encodeURIComponent(token)` / `quote(token, safe='')` | `code:0`，拿到数据（3/3） |

- **走 `fetch_url`（浏览器自己发）** → 浏览器原生处理编码，**无需关心**。本项目主路径。
- **浏览器之外用 token** → 入 cookie 前**必须 URL 编码**。`gen_stoken` 已直接返回 `token_encoded`。

> 调试铁律：**“浏览器能成、自己 replay 不成”时，第一步永远是 byte-diff 两边真实 cookie/请求** ——
> 这个编码差异（`…/` vs `…%2F`）一眼可见。别先去猜算法/参数/seed（作者本人在这上面绕了很久）。

---

## 5. 三种数据获取方案对比

| | (A) mitm 浏览器发 | (B) RPC 调 gen_stoken | (C) 文件替换 + 外部 Python |
|---|---|---|---|
| 谁发请求 | **浏览器**（`fetch_url`） | 浏览器算 token，Python 发 | Python 发 |
| token | 浏览器原生（含编码） | `gen_stoken` 返回 `token_encoded` | 自己 `quote()` 编码 |
| 需要暴露 ABC | 否（数据流用不到） | 是 | 是 |
| 反调试 | mitm `patches.py` 中和 | 同左 | 文件替换中和 |
| 稳定性 / 省心 | ★★★ 最稳 | ★★ | ★★（编码对了就稳） |
| 适用 | **默认**：低中 QPS、要登录态/真 TLS | 想拿 token 值做别的 | 想脱离浏览器、自建请求管线 |

- **(A) 是本项目主路径**，也是最推荐的：浏览器把 TLS/sec-ch-ua/cookie 漂移/`__zp_stoken__`/编码全包了。
- **(B)/(C)** 是“自己生成 token 拿出去用”，关键是别忘了 **URL 编码**。可跑通的例子见
  [`tests/gen_external_request.py`](../tests/gen_external_request.py)。

---

## 6. 逆向方法论（踩坑沉淀）

- **捕获要文件替换源码本身**：JS prototype hook 会被 JSVMP 混淆绕过、也有“调用早于 hook”的时序问题。
  可靠做法是**文件替换 security-js 并在末尾追加 wrapper**（同一执行环境 → 绕不过）；并且要 patch
  **调用真正所在的 bundle**（token 网关在 `app~2`，不是 main.js）。
- **先 diff，再猜**：浏览器能成/自己不成 → 先逐字节比对两边请求与 cookie。
- **不要把假设当结论**：本次逆向里“iframe 被销毁 / 必须 set/zpToken 祝福 / 风控升级 / seed 一次性”等
  说法都曾被当结论、最后被推翻。随机性结论务必 ≥3 次复现。

---

## 7. 升级了怎么办

反调试 JS 升级 → `cli.py health boss` 报 patch 失配 → 重新下载 main.js → 跑 `analysis/find_bm.py`
重定位 → 改 `sites/boss/patches.py` 的 pattern（通常变量名变了、结构没变）。token/seed/编码逻辑
长期稳定，一般不需要动。
