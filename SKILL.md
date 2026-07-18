---
name: boss-zhipin-reverse
description: Maintain, diagnose, and verify this Boss Zhipin browser-assisted reverse-engineering project. Use for Boss anti-debug patch upgrades, mitmproxy response rewriting, RPC browser execution, __zp_stoken__ analysis, login-state operations, capture, storage, regression testing, and documentation consistency. Treat Boss Zhipin as the only supported target; the plugin boundary is an internal code organization detail, not a claim of proven multi-site support.
---

# Boss Zhipin Reverse

## Mission and scope

Work on Boss Zhipin only. Treat `sites/boss/` as the product and the generic-looking plugin classes as internal boundaries that keep the code testable.

Do not describe this repository as a proven multi-site framework. No second target has been validated.

Keep every scratch script, downloaded target bundle, log, and temporary report under this repository's `tmp/` directory. Before creating one, state its absolute path. Do not put temporary material in another project or commit `tmp/`, `data/`, target JavaScript, cookies, tokens, or browser profiles.

Read the source relevant to the task:

- Anti-debug work: `sites/boss/patches.py`, `core/patching.py`, `core/mitm_addon.py`, then `docs/BOSS_DEEP_DIVE.md`.
- RPC work: `core/rpc.py`, RPC poller in `core/mitm_addon.py`, `core/server.py`, then `sites/boss/injection.js`.
- Business API work: `sites/boss/operations.py`, the corresponding FastAPI route, storage, and pipeline behavior.
- Claims about prior testing: compare README with the evidence table in this Skill and rerun time-sensitive checks.

## Architecture truth

The main path is browser-assisted RPC:

```text
CLI or API caller
  -> FastAPI creates a task and Future
  -> global asyncio.Queue
  -> injected browser poller gets the task
  -> the logged-in Boss page runs fetch with credentials=include
  -> browser posts the result
  -> Python parses, pipelines, and persists it
```

The browser supplies the real login state, TLS fingerprint, UA/client hints, cookies, and Boss token behavior. Python controls what to request and how to process the response.

The anti-debug path is a prerequisite, not an optional helper:

```text
Boss HTTPS response
  -> mitmproxy decrypts it
  -> JavaScript response is patched in memory
  -> HTML receives Boss injection plus RPC poller
  -> Chrome executes the modified response
```

If patching or HTML injection fails, the page may retreat, blur, clear the console, allocate memory, or never start the RPC client.

## Response rewriting versus file replacement

Use precise terminology:

- Implemented: mitm response rewriting. `flow.response.get_text()` is patched and returned with `flow.response.set_text()`.
- Implemented: HTML response injection after a literal `<head>` tag.
- Not implemented: a URL-to-local-file replacement map.
- Not implemented: automatic replacement of rotating `security-js` files or appending wrappers to a local copy.
- Not implemented: versioned local bundle overrides, rollback, or replacement-file hashes.

The "file replacement + external Python" path in `docs/BOSS_DEEP_DIVE.md` is a research technique, not a finished project feature. Do not claim otherwise. `tests/gen_external_request.py` still asks the browser RPC to generate a token.

## Boss anti-debug model

The dangerous logic is copied across SEO and SPA bundles. Minified local names change, but some method names and side-effect shapes are stable.

| Layer | Behavior | Current neutralization |
|---|---|---|
| `Bm()` | DevTools/tamper failure leads to retreat, close/back, blur, report, and memory punishment | Balanced function-body replacement with `{}` |
| `function t()` with `Sign.encryptPwd()` | Secondary integrity comparison and punishment | Balanced function-body replacement with `{}` |
| `Rm()` | Native-function and object integrity checks | Early `return` |
| `XCID/XCIT` transpiled | Getter/console DevTools probe in Babel class output | Early `return` |
| `XCID/XCIT` ES6 | Same probe in SPA class syntax | Early `return`; health scope is SPA only |
| Memory bombs | Huge dense arrays and repeated strings | Reduce allocation/repeat count to `1` |
| Console clearing | Several wrapper shapes repeatedly clear/flood console | Replace only wrapper definitions |
| Reload loop | Repeated reload after detection | Runtime throttle in injected poller |
| Window-size probe | `outerWidth/outerHeight` difference | Runtime getters in injected poller |
| `Ef` shortcut detection | Detects DevTools keyboard combinations | Researched but not currently patched |
| Setter/timing probe | Setter and frame/timing based detection | Researched but not currently patched |

### Control-flow rule

Neutralize the detector; do not blindly invert its condition.

For the known `Bm` chain, the clean branch requires all checks to pass and the `else` branch performs reporting and memory punishment. Replacing the condition with `false` forces the punishment branch. Replace the complete detector body or method entry so neither branch runs.

### Patch engine order

`core/patching.py` is the single patch implementation used by runtime mitm and validation:

1. Apply `mode="sub"` expression substitutions.
2. Find every `mode="body"` function signature in the already-substituted text.
3. Sort body hits from the end of the file toward the start.
4. Find the matching closing brace while skipping quoted strings and block comments.
5. Replace the full body and report per-rule counts.

The brace scanner is intentionally small. It does not fully parse JavaScript regex literals, template literals, or line comments. Any new body signature must be tested against current real bundles and followed by JavaScript syntax validation.

## Anti-debug upgrade workflow

Follow this order. A green regex search alone is not enough.

1. Run the signature health check:

```powershell
python scripts/healthcheck.py boss
```

2. Run real patch application and post-patch syntax validation:

```powershell
python scripts/validate_boss_patches.py
```

This downloads current bundles in memory, applies the exact runtime engine, requires every patch type to match an appropriate bundle, and runs `node --check` on every result.

3. If a rule is missing, inspect `detail.downloaded_urls` from the Boss health report. Download only the failed bundle under `tmp/`, for example:

```powershell
New-Item -ItemType Directory -Force tmp\boss-analysis
Invoke-WebRequest <bundle-url> -OutFile tmp\boss-analysis\current.js
```

4. Locate stable side effects and surrounding structure. Search for `XCID`, `XCIT`, `Sign.encryptPwd`, large `Array`, large `repeat`, console wrappers, navigation/blur/report paths, and callers of the missing function.

5. Recover the branch meaning before editing. Determine which branch is clean and which triggers retreat/report/OOM.

6. Prefer the narrowest stable structure:

- Use a stable method/function name plus nearby structural calls when available.
- Avoid a short minified local variable as the only anchor.
- For generic bomb expressions, inspect every match context to rule out legitimate business code.
- Use `spa_only=True` only for health scoping; runtime still applies matching rules wherever they occur.

7. Update `sites/boss/patches.py`, then rerun both checks.

8. Start the full stack, log in, verify injection markers, then verify DevTools behavior:

```powershell
python cli.py go
python cli.py rpc eval "JSON.stringify({href:location.href,rpc:!!window.__MITMRPC_LOADED__,boss:!!window.__BOSS_PLUGIN_LOADED__,ops:Object.keys(window.__MITMRPC_OPS__||{})})"
```

9. Open DevTools only after login. Verify no retreat, blur, reload loop, console flood, or memory growth. This is the dynamic anti-debug proof.

10. Run read-only RPC and Boss operations before any side-effecting action:

```powershell
python cli.py rpc cookie
python cli.py search "Python"
python cli.py op boss list_cities
python cli.py op boss list_industries
python cli.py op boss list_chats
```

Never run `greet`, `greet_selected`, or `auto_greet` without explicit user confirmation of the target and count.

## Health-check interpretation

`sites/boss/__init__.py` discovers the current Boss home and geek-jobs entrypoint scripts, downloads SEO and SPA bundles, and checks patch signatures.

Interpret evidence correctly:

- Signature hit: the regex still sees a candidate structure.
- Patch validator pass: the runtime rewrite completes and resulting JavaScript parses.
- Injection marker pass: the real page received Boss and RPC scripts.
- F12 pass: the current browser session survives the anti-debug behavior.
- Business operation pass: login state and API path work end to end.

Do not promote a lower level as proof of a higher level.

## RPC implementation and limits

`RpcBus.send()` creates a short task id, stores a Future, puts a task on one global queue, and waits up to the request timeout. Browser tabs poll `/rpc/poll`; the first tab to receive a task executes it and posts to `/rpc/result/{id}`.

Built-in browser operations:

- `eval`: execute JavaScript and return `String(value)`.
- `cookie`: return `document.cookie`.
- `fetch_url`: browser `fetch` with `credentials: "include"`.
- `gen_stoken`: Boss-specific operation registered by `sites/boss/injection.js`.

Known limits:

- No browser-session, tab, or origin affinity; keep one active Boss work tab for deterministic execution.
- No heartbeat, retry, backpressure, or browser-side fetch cancellation.
- A server timeout does not cancel an already-running browser fetch.
- `eval` loses structured values unless the caller uses `JSON.stringify`.
- RPC statistics describe delivery, not Boss business success.
- The local API exposes `eval` without an application token; keep it bound to `127.0.0.1`.

## Boss token path

The normal data path does not need to call `gen_stoken`: browser `fetch_url` uses the browser's existing cookie and token behavior.

Use `gen_stoken` only when testing an external request path:

1. An external request receives `code:37` and `zpData.seed/name/ts`.
2. RPC calls the iframe-provided `ABC.z(seed, corrected_ts)`.
3. Use `token_encoded`, not the raw token, in an external cookie.
4. Retry the same request and compare exact cookies and headers before changing algorithms.

Raw `+` in the token must be percent-encoded or server decoding can turn it into a space.

## Business and persistence semantics

Boss operations live in `sites/boss/operations.py`. A result containing `_persist` is persisted only when it returns through `core/server.py`.

For nested/batch operations, return explicit persistable `items`; do not assume an inner function's `_persist` marker will be processed automatically.

Treat `code == 0` as Boss business success. Transport success and valid JSON are not sufficient.

Read-only operations should be used for regression first. Greeting operations are real side effects and require confirmation.

## Test evidence and boundaries

Previously verified with a real logged-in browser:

- mitm TLS interception and CA setup.
- Boss and RPC injection markers.
- RPC `eval`, `cookie`, and browser `fetch_url`.
- `search`, `list_cities`, `list_industries`, `list_chats`, `gen_stoken`, and one real `greet`.
- User-observed F12 survival without retreat, flood, or OOM.
- JSONL, SQLite, and CSV read/write plus pipeline filtering.

Not proven as live production paths:

- Multi-page search and both batch greeting operations at scale.
- `get_history_msg` against current live API.
- MySQL with a real server.
- Any second website/plugin.
- A true local-file replacement system.

Live Boss versions, login state, cookies, and F12 behavior drift. Rerun current checks instead of treating this snapshot as permanent.

## Regression commands

Run non-writing syntax and unit checks with bytecode disabled:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/healthcheck.py boss
python scripts/validate_boss_patches.py
```

Run `scripts/doctor.ps1` when environment, Chrome, proxy, or certificate setup is in doubt.

## Reporting standard

When reporting project state, separate:

1. Source inspection.
2. Unit or mock verification.
3. Current live bundle verification.
4. Real browser/injection verification.
5. Logged-in Boss API verification.
6. Side-effecting verification performed with user approval.

Include exact bundle versions, operation names, result codes, skipped checks, and remaining risks. Never report "fully working" from healthcheck output alone.
