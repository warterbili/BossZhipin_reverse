# mitm-rpc 环境体检
# 检查所有依赖，输出报告，必要时给修复建议

$ErrorActionPreference = 'Continue'
$Project = Split-Path -Parent $PSScriptRoot

function CheckOK($what, $detail = "")  { Write-Host "  ✅ $what" -ForegroundColor Green; if ($detail) { Write-Host "     $detail" -ForegroundColor DarkGray } }
function CheckBad($what, $hint = "")   { Write-Host "  ❌ $what" -ForegroundColor Red; if ($hint) { Write-Host "     $hint" -ForegroundColor Yellow } }
function CheckWarn($what, $hint = "")  { Write-Host "  ⚠️  $what" -ForegroundColor Yellow; if ($hint) { Write-Host "     $hint" -ForegroundColor DarkYellow } }

Write-Host ""
Write-Host "==================== mitm-rpc 体检 ====================" -ForegroundColor Cyan
$err = 0

# ─── Python ───
Write-Host "`n[Python]"
$py = Get-Command python -EA SilentlyContinue
if (-not $py) {
    CheckBad "Python 未安装" "下载: https://www.python.org/downloads/ (选 3.10+)"
    $err++
} else {
    $ver = (python --version 2>&1) -replace 'Python ',''
    $verNum = [version]($ver -split '\+' | Select-Object -First 1)
    if ($verNum -lt [version]"3.10") {
        CheckBad "Python $ver" "需要 3.10+"; $err++
    } else { CheckOK "Python $ver" }
}

# ─── venv ───
Write-Host "`n[venv]"
$venv = "$Project\.venv"
$venvPy = "$venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    CheckWarn ".venv 未创建" "运行: python -m venv .venv"
    $err++
} else { CheckOK ".venv 存在" $venvPy }

# ─── Python deps ───
Write-Host "`n[Python 依赖]"
if (Test-Path $venvPy) {
    $deps = @("fastapi", "uvicorn", "mitmproxy", "requests")
    foreach ($d in $deps) {
        $r = & $venvPy -c "import importlib, sys; m=importlib.import_module('$d'); print(getattr(m,'__version__','?'))" 2>$null
        if ($LASTEXITCODE -eq 0) { CheckOK "$d $r" } else { CheckBad "$d 未装" "运行: .\.venv\Scripts\pip install -r requirements.txt"; $err++ }
    }
} else { CheckWarn "(skip, venv 没建)" }

# ─── Chrome ───
Write-Host "`n[Chrome]"
$chromes = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
    "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
)
$found = $null
foreach ($c in $chromes) {
    if (Test-Path $c) { $found = $c; break }
}
if ($found) {
    $cv = (Get-Item $found).VersionInfo.ProductVersion
    CheckOK "Chrome v$cv" $found
} else {
    CheckBad "未找到 Chrome / Edge" "下载: https://www.google.com/chrome/"
    $err++
}

# ─── mitmproxy CA cert ───
Write-Host "`n[mitmproxy CA 证书]"
$cer = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
if (Test-Path $cer) {
    CheckOK "证书已生成" $cer
    # 用 certutil 反查 Root store
    $store = certutil -user -store Root mitmproxy 2>&1 | Out-String
    if ($store -match "mitmproxy") {
        CheckOK "已加入用户 Trusted Root"
    } else {
        CheckWarn "未加入 Trusted Root" "运行: .\scripts\setup_cert.ps1"
        $err++
    }
} else {
    CheckWarn "证书未生成" "运行: .\scripts\setup_cert.ps1"
    $err++
}

# ─── 端口占用 ───
Write-Host "`n[端口检查]"
foreach ($p in @(8888, 9999, 19222)) {
    $conn = Get-NetTCPConnection -LocalPort $p -EA SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $proc = Get-Process -Id $conn.OwningProcess -EA SilentlyContinue
        CheckWarn "端口 $p 被占用" "进程: $($proc.ProcessName) (PID $($conn.OwningProcess))"
    } else { CheckOK "$p 空闲" }
}

# ─── 插件 ───
Write-Host "`n[站点插件]"
if (Test-Path $venvPy) {
    $sites = & $venvPy -c "import os, sys; sys.path.insert(0, r'$Project'); import importlib, pkgutil; pkg=importlib.import_module('sites'); names=[n for _,n,p in pkgutil.iter_modules(pkg.__path__) if p and not n.startswith('_')]; print(','.join(names))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $sites) {
        CheckOK "已加载: $sites"
    } else {
        CheckWarn "(无法导入 sites)"
    }
}

# ─── 总结 ───
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($err -eq 0) {
    Write-Host "✅ 一切正常，可以跑 .\scripts\start.ps1" -ForegroundColor Green
} else {
    Write-Host "⚠️  有 $err 项需要处理。或直接跑 .\scripts\setup.ps1 自动修复" -ForegroundColor Yellow
}
Write-Host ""
exit $err
