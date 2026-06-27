"""Boss 反调试函数签名（mitm 拦到 *.js 时按这些规则中和整条反调试链）。

Boss 把同一套反调试【复制进每个 webpack bundle】（SEO 的 main.js、SPA 的 app~* / vendor-*），
minify 名各不同，但**类方法名 XCID / XCIT 跨 bundle 共享**、且 console.clear / 内存炸弹是结构稳定的
表达式 —— 所以下面用**名字稳定的正则**，一套规则覆盖所有 bundle。

两类模式（见 sites/_base.py JsPatch）:
  - mode="body": 找到 'function X(){' 用大括号配对清空函数体。用于【函数型】检测 (Bm / Rm)。
  - mode="sub" : 纯 re.sub。用于【表达式型】检测 (XCID/XCIT 方法、console.clear 包装器、内存炸弹)。

⚠️ 心法「绕过，别翻转」: 反调试的门 if(n&&i&&a&&o) 全 true 才是干净分支，else 是惩罚分支(上报+内存炸弹)。
   把门翻成 if(false) = 强制走惩罚分支 = 自爆。正确做法是把整个检测【函数/方法置空 return】，门两边都不进。

升级失配（healthcheck 红灯）时：重新下载 main.js → 跑 analysis/find_bm.py → 调下面的 pattern。
完整逐层原理见 docs/BOSS_DEEP_DIVE.md。
"""
from __future__ import annotations

import re

from sites._base import JsPatch


BOSS_PATCHES: list[JsPatch] = [
    # ───────────────────────── 函数型（清空函数体） ─────────────────────────
    # Bm: 主反调试动作 —— 检测到 DevTools/native被hook 后 退站(open/close/history.back)+blur遮罩
    #     + 上报 method_modify + 内存炸弹。结构: function Bm(){var e,t,n=Rm(),i=window[XXX(Om)]
    JsPatch(
        name="Bm",
        pattern=re.compile(
            r"function\s+Bm\s*\(\s*\)\s*\{var\s+e,\s*t,\s*n\s*=\s*Rm\s*\(\s*\)\s*,\s*i\s*=\s*window\["
        ),
        replacement_body="{}",
        notes="主反调试函数（退站+blur+上报+OOM），整体置空",
    ),
    # function t(){if(Sign.encryptPwd(),...): 篡改检测，签名不一致触发 OOM
    JsPatch(
        name="function-t-encryptPwd",
        pattern=re.compile(
            r"function\s+t\s*\(\s*\)\s*\{\s*if\s*\(\s*Sign\.encryptPwd\s*\(\s*\)"
        ),
        replacement_body="{}",
        notes="二级篡改检测，判 Sign.pwdDetail 不一致就 OOM",
    ),

    # ───────────────────────── 表达式型（纯正则替换） ─────────────────────────
    # XCID / XCIT: ~500ms 循环跑的 DevTools 探针 + console 刷屏（createElement('div').__defineGetter__
    #   + console.log 探针）。跨 bundle 同名，两种写法：ES6 `XCID(){` 和 babel `key:"XCID",value:function(){`
    JsPatch(name="XCID-transpiled", mode="sub", notes="devtools探针+刷屏(转译写法)",
            pattern=re.compile(r'key:"XCID",value:function\(\)\{'),
            replacement='key:"XCID",value:function(){return;'),
    JsPatch(name="XCIT-transpiled", mode="sub", notes="探针搭建(转译写法)",
            pattern=re.compile(r'key:"XCIT",value:function\(\)\{'),
            replacement='key:"XCIT",value:function(){return;'),
    JsPatch(name="XCID-es6", mode="sub", spa_only=True, notes="devtools探针+刷屏(ES6类方法, SPA bundle)",
            pattern=re.compile(r'\bXCID\(\)\{'), replacement='XCID(){return;'),
    JsPatch(name="XCIT-es6", mode="sub", spa_only=True, notes="探针搭建(ES6类方法, SPA bundle)",
            pattern=re.compile(r'\bXCIT\(\)\{'), replacement='XCIT(){return;'),
    # Rm: native-method-tamper 检测（[native code]/instanceof）。Bm 死后已无效，置空兜底。
    JsPatch(name="Rm", mode="sub", notes="原生方法篡改检测，兜底置空",
            pattern=re.compile(r'function Rm\(\)\{'), replacement='function Rm(){return;'),
    # 内存炸弹: new Array(1eN).fill(...) / "x".repeat(1eN)（×循环×递归，撑爆内存）。把单位量砍到 1。
    JsPatch(name="bomb-Array", mode="sub", notes="内存炸弹: 巨型 Array 分配 → 1",
            pattern=re.compile(r'new Array\(1e\d+\)'), replacement='new Array(1)'),
    JsPatch(name="bomb-repeat", mode="sub", notes="内存炸弹: 巨型 repeat → 1",
            pattern=re.compile(r'\.repeat\(1e\d+\)'), replacement='.repeat(1)'),
    # console.clear 刷屏链（jf→If→pg.clear）。只杀【包装器定义】4 种写法，绝不碰业务里的 X.clear() 调用。
    JsPatch(name="clear-arrow", mode="sub", spa_only=True, notes="console.clear 包装器(箭头, SPA bundle)",
            pattern=re.compile(r'\(\)=>\w+\.clear\(\)'), replacement='()=>{}'),
    JsPatch(name="clear-fn", mode="sub", notes="console.clear 包装器(function)",
            pattern=re.compile(r'function\(\)\{return \w+\.clear\(\)\}'), replacement='function(){}'),
    JsPatch(name="clear-assign", mode="sub", spa_only=True, notes="console.clear 包装器(else分支赋值, SPA bundle)",
            pattern=re.compile(r'(\.table,\w+=)\w+\.clear\b'), replacement=r'\1function(){}'),
    JsPatch(name="clear-comma", mode="sub", notes="console.clear 包装器(非IE逗号表达式尾,最易漏)",
            pattern=re.compile(r'(\.table),\w+\.clear\)'), replacement=r'\1,function(){})'),
]
