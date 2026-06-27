// Boss 直聘专属注入脚本
// 1. 把 iframe 里的加密类 ABC 暴露到 window.__BOSS_ABC__
// 2. 注册 gen_stoken op 到 window.__MITMRPC_OPS__（被 core RPC poller 调用）
(function(){
  if (window.__BOSS_PLUGIN_LOADED__) return;
  window.__BOSS_PLUGIN_LOADED__ = true;
  var TAG = '[boss]';
  var _warn = console.warn.bind(console);

  // 自动扫描 iframes 找 ABC
  function exposeABC(){
    if (window.__BOSS_ABC__) return true;
    try {
      for (var i = 0; i < window.frames.length; i++) {
        try {
          var fw = window.frames[i];
          if (fw && fw.ABC && typeof fw.ABC === 'function') {
            window.__BOSS_ABC__ = fw.ABC;
            _warn(TAG, '★ ABC exposed from frame', i);
            return true;
          }
        } catch(e) {}
      }
    } catch(e) {}
    return false;
  }
  if (!exposeABC()) {
    var t = setInterval(function(){
      if (exposeABC()) clearInterval(t);
    }, 200);
    setTimeout(function(){ clearInterval(t); }, 5 * 60 * 1000);
  }

  // 注册站点专属 RPC ops
  window.__MITMRPC_OPS__ = window.__MITMRPC_OPS__ || {};

  // gen_stoken: 用 ABC.z(seed, ts_corrected) 算 __zp_stoken__
  //
  // ⚠️ COOKIE 编码（踩过坑，务必看）：
  //   z() 产出的 token 含 '+' 和 '/'。浏览器原生 Cookie.set 存的是 URL 编码后的值
  //   （'+'→%2B, '/'→%2F）。若把【裸 token】塞进 cookie，服务端 URL-decode 会把 '+' 解成空格 →
  //   token 损坏 → code:37「您的环境存在异常」。
  //   所以在【浏览器之外】用这个 token（Python/Go 等），入 cookie 前必须 encodeURIComponent /
  //   quote(token, safe='')。本 op 直接把 token_encoded 一并返回，外部用它即可。
  //   （走 fetch_url 让浏览器自己发请求时，浏览器原生处理编码，无需关心——见 README。）
  window.__MITMRPC_OPS__.gen_stoken = function(task){
    var ABC = window.__BOSS_ABC__;
    if (typeof ABC !== 'function') {
      return {ok: false, error: 'ABC not exposed yet'};
    }
    var ts = parseInt(task.ts) + 60 * (480 + (new Date()).getTimezoneOffset()) * 1000;
    var token = (new ABC()).z(task.seed, ts);
    return {ok: true, token: token, token_encoded: encodeURIComponent(token), ts_used: ts};
  };

  _warn(TAG, '★ boss plugin loaded');
})();
