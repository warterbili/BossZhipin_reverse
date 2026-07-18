"""通用 mitm addon：从 sites/ 加载所有插件，按域名匹配 patch + 注入。

启动:
    mitmdump -s core/mitm_addon.py --listen-port 8888
"""
from __future__ import annotations

import importlib
import json
import pathlib
import pkgutil
import re
import time
import traceback
from typing import Any

from mitmproxy import ctx, http

# 让本文件能被 mitmdump 直接加载（独立运行不依赖项目作为 package）
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sites._base import SitePlugin, HtmlInject  # noqa: E402
from core.patching import apply_js_patches  # noqa: E402

# ─────────────────────── 插件加载 ───────────────────────

PLUGINS: list[SitePlugin] = []


def _startup_log(level: str, message: str) -> None:
    """Log during mitmdump startup; remain importable in unit-test contexts."""
    logger = getattr(ctx, "log", None)
    if logger is not None:
        getattr(logger, level)(message)


def _load_plugins() -> None:
    """扫描 sites/ 下的所有子模块，找 SitePlugin 子类实例化。"""
    PLUGINS.clear()
    sites_pkg = importlib.import_module("sites")
    for finder, mod_name, is_pkg in pkgutil.iter_modules(sites_pkg.__path__):
        if not is_pkg or mod_name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"sites.{mod_name}")
        except Exception as e:
            _startup_log("warn", f"[plugin] load fail {mod_name}: {e}")
            continue
        # 找模块顶层导出的 SitePlugin 子类的 *实例*（约定: PLUGIN = ClassName())
        plugin = getattr(mod, "PLUGIN", None)
        if plugin is None:
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and issubclass(obj, SitePlugin) and obj is not SitePlugin:
                    plugin = obj()
                    break
        if plugin is None:
            _startup_log("warn", f"[plugin] {mod_name}: no SitePlugin found")
            continue
        PLUGINS.append(plugin)
        _startup_log(
            "alert",
            f"[plugin] loaded: {plugin.name} ({len(plugin.patches)} patches, "
            f"{len(plugin.injections)} injections)",
        )


_load_plugins()

# ─────────────────────── 通用 RPC 注入 ───────────────────────
# Boss HTML 使用通用 RPC poller；ABC 暴露等 Boss 特定逻辑由 HtmlInject 提供。
RPC_POLLER_JS = """<script>(function(){
  if (window.__MITMRPC_LOADED__) return;
  window.__MITMRPC_LOADED__ = true;
  var TAG = '[mitmrpc]';
  var _warn = console.warn.bind(console);

  // 节流式 reload 拦截 (防反调试 reload-loop)
  var lastReload = 0, reloadCount = 0;
  try {
    var origReload = Location.prototype.reload;
    Object.defineProperty(Location.prototype, 'reload', {
      value: function(){
        var now = Date.now();
        reloadCount = (now - lastReload < 1000) ? reloadCount + 1 : 1;
        lastReload = now;
        if (reloadCount >= 2) {
          _warn(TAG, 'reload BLOCKED #' + reloadCount);
          return;
        }
        return origReload.apply(this, arguments);
      },
      writable: true, configurable: true,
    });
  } catch(e){}

  // outerWidth / outerHeight 假装无 DevTools
  try {
    Object.defineProperty(window, 'outerWidth', {get:function(){return window.innerWidth;}, configurable:true});
    Object.defineProperty(window, 'outerHeight',{get:function(){return window.innerHeight+80;}, configurable:true});
  } catch(e){}

  // RPC 轮询
  function loop(){
    fetch('http://127.0.0.1:9999/rpc/poll', {credentials:'omit'})
      .then(function(r){return r.json();})
      .then(function(task){
        if (!task || !task.op) { setTimeout(loop, 200); return; }
        var done = function(result){
          fetch('http://127.0.0.1:9999/rpc/result/' + task.id, {
            method:'POST', credentials:'omit',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify(result),
          }).finally(function(){ setTimeout(loop, 50); });
        };
        try {
          if (task.op === 'eval') {
            done({ok:true, value: String((0,eval)(task.code))}); return;
          }
          if (task.op === 'cookie') {
            done({ok:true, value: document.cookie}); return;
          }
          if (task.op === 'fetch_url') {
            fetch(task.url, {
              method: task.method || 'GET',
              headers: task.headers || {},
              body: task.body,
              credentials: 'include', mode: 'cors',
            }).then(function(r){
              var hdrs = {};
              r.headers.forEach(function(v,k){hdrs[k]=v;});
              return r.text().then(function(text){
                done({ok:true, status:r.status, url:r.url, headers:hdrs, body:text});
              });
            }).catch(function(e){
              done({ok:false, error:'fetch failed: '+String(e)});
            });
            return;
          }
          // 其它 op 由站点专属注入脚本扩展 (它们会注册到 window.__MITMRPC_OPS__)
          if (window.__MITMRPC_OPS__ && window.__MITMRPC_OPS__[task.op]) {
            try {
              var r = window.__MITMRPC_OPS__[task.op](task);
              if (r && typeof r.then === 'function') r.then(done, function(e){done({ok:false, error:String(e)});});
              else done(r);
            } catch(e){
              done({ok:false, error:String(e && (e.stack||e.message||e))});
            }
            return;
          }
          done({ok:false, error:'unknown op: ' + task.op});
        } catch(e){
          done({ok:false, error:String(e && (e.stack||e.message||e))});
        }
      })
      .catch(function(){ setTimeout(loop, 1000); });
  }
  setTimeout(loop, 500);
  _warn(TAG, '★ ready at', location.href);
})();</script>"""


# ─────────────────────── mitm 钩子 ───────────────────────

CAPTURE_DIR = ROOT / "data" / "captures"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
CAPTURE_FILE = CAPTURE_DIR / "live.jsonl"
import urllib.request as _urlreq
import urllib.error as _urlerr


def _post_to_server(rec: dict) -> None:
    """把抓包记录 POST 给 server (走 server pipeline + SSE 推送)。
    server 没起也不报错。"""
    try:
        data = json.dumps(rec, ensure_ascii=False).encode("utf-8")
        req = _urlreq.Request(
            "http://127.0.0.1:9999/api/internal/capture",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _urlreq.urlopen(req, timeout=2).read()
    except (_urlerr.URLError, OSError):
        pass


def _capture(flow: http.HTTPFlow) -> None:
    if not flow.response:
        return
    if not (CAPTURE_DIR / "_enabled").exists():
        return
    host = (flow.request.host or "").lower()
    if not any(p.matches_host(host) for p in PLUGINS):
        return
    static = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp",
              ".ico", ".svg", ".woff", ".woff2", ".map")
    path = (flow.request.path or "").split("?")[0].lower()
    if any(path.endswith(ext) for ext in static):
        return
    try:
        rec = {
            "ts": int(time.time() * 1000),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "host": host,
            "req_headers": dict(flow.request.headers),
            "req_cookies": flow.request.headers.get("cookie", ""),
            "req_body": flow.request.get_text() or "",
            "resp_status": flow.response.status_code,
            "resp_headers": dict(flow.response.headers),
            "resp_body": (flow.response.get_text() or "")[:10000],
        }
        # 推送给 server (走 pipeline + SSE)
        _post_to_server(rec)
    except Exception as e:
        ctx.log.warn(f"[capture] {e}")


def _apply_patches(flow: http.HTTPFlow) -> None:
    if not flow.response or not flow.response.content:
        return
    host = (flow.request.host or "").lower()
    path = flow.request.path or ""
    # 只 patch JS
    if not path.split("?")[0].lower().endswith(".js"):
        return
    plugin = next((p for p in PLUGINS if p.matches_host(host)), None)
    if plugin is None or not plugin.patches:
        return
    try:
        text = flow.response.get_text() or ""
    except Exception:
        return

    result = apply_js_patches(text, plugin.patches)
    if not result.messages:
        return
    flow.response.set_text(result.text)
    ctx.log.alert(
        f"[patch] {plugin.name} {flow.request.path} -> {', '.join(result.messages)}"
    )


def _inject_html(flow: http.HTTPFlow) -> None:
    if not flow.response:
        return
    ct = flow.response.headers.get("content-type", "")
    if "text/html" not in ct:
        return
    host = (flow.request.host or "").lower()
    path = flow.request.path or ""
    plugin = next((p for p in PLUGINS if p.matches_host(host)), None)
    if plugin is None:
        return
    try:
        body = flow.response.get_text() or ""
    except Exception:
        return
    if "<head>" not in body:
        return

    inject_blocks: list[str] = []

    # 站点专属注入（先注入，让站点 setup 在 RPC poller 之前完成）
    for hi in plugin.injections:
        if hi.url_pattern in path or hi.url_pattern in flow.request.pretty_url:
            if hi.inject_marker not in body:
                inject_blocks.append(hi.script)

    # 通用 RPC poller
    if "__MITMRPC_LOADED__" not in body:
        inject_blocks.append(RPC_POLLER_JS)

    if not inject_blocks:
        return
    new_body = body.replace("<head>", "<head>" + "\n".join(inject_blocks), 1)
    flow.response.set_text(new_body)
    ctx.log.alert(f"[inject] {plugin.name} {path} (+{len(inject_blocks)} blocks)")


def response(flow: http.HTTPFlow) -> None:
    try:
        _apply_patches(flow)
        _inject_html(flow)
        _capture(flow)
    except Exception:
        ctx.log.warn("[response] " + traceback.format_exc())
