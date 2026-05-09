"""Boss main.js 反调试函数签名。

mitm 拦截到 main.js 时，会用这里的正则定位函数体并清空。

如果 Boss 升级导致签名失配（healthcheck 红灯）：
  1. analysis/main.js 重新下载: curl https://static.zhipin.com/.../main.js -o analysis/main.js
  2. 跑 analysis/find_bm.py 找新的关键字位置
  3. 调整下面的 pattern
"""
from __future__ import annotations

import re

from sites._base import JsPatch


BOSS_PATCHES: list[JsPatch] = [
    # Bm: 主反调试函数. 检测到 native 函数被 hook 时分配大量内存 OOM 攻击.
    # 结构特征: function Bm(){var e,t,n=Rm(),i=window[XXX(Om)]
    # XXX 是字符串解码器 (L / z / 其它)，因 bundle 而异，所以用 \w+
    JsPatch(
        name="Bm",
        pattern=re.compile(
            r"function\s+Bm\s*\(\s*\)\s*\{var\s+e,\s*t,\s*n\s*=\s*Rm\s*\(\s*\)\s*,\s*i\s*=\s*window\["
        ),
        replacement_body="{}",
        notes="主反调试函数，检测到 DevTools 后做 4 件事 + OOM",
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
]
