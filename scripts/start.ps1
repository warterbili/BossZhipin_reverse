# mitm-rpc 一键启动脚本
# 顺序：FastAPI → mitm → Chrome
# Ctrl+C 退出 Chrome 后这里也会清理两个后台

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Project ".venv\Scripts"

if (-not (Test-Path "$Venv\python.exe")) {
    Write-Host "[!] 未发现 .venv，自动跑 setup ..." -ForegroundColor Yellow
    & "$PSScriptRoot\setup.ps1"
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# 检查 mitm 证书
$store = certutil -user -store Root mitmproxy 2>&1 | Out-String
if ($store -notmatch "mitmproxy") {
    Write-Host "[!] mitm CA 证书未装，自动安装..." -ForegroundColor Yellow
    & "$PSScriptRoot\setup_cert.ps1"
}

# 1. 检查端口
$ports = @(8888, 9999, 19222)
foreach ($p in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $p -EA SilentlyContinue
    if ($conn) {
        Write-Host "[!] 端口 $p 被占用 (pid $($conn.OwningProcess))，杀掉..." -ForegroundColor Yellow
        Stop-Process -Id $conn.OwningProcess -Force -EA SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

Write-Host "==================== mitm-rpc 启动 ====================" -ForegroundColor Cyan
Write-Host " FastAPI dashboard : http://127.0.0.1:9999"
Write-Host " mitm proxy        : 127.0.0.1:8888"
Write-Host " Chrome debug port : 19222"
Write-Host "========================================================" -ForegroundColor Cyan

# 2. FastAPI（独立窗口，方便看日志）
$fastapi = Start-Process -FilePath "$Venv\uvicorn.exe" `
    -ArgumentList @("core.server:app", "--host", "127.0.0.1", "--port", "9999", "--log-level", "warning") `
    -WorkingDirectory $Project -PassThru -WindowStyle Normal

Start-Sleep -Seconds 2

# 3. mitm
$mitm = Start-Process -FilePath "$Venv\mitmdump.exe" `
    -ArgumentList @("-s", "core/mitm_addon.py", "--listen-port", "8888",
                    "--set", "console_eventlog_verbosity=info") `
    -WorkingDirectory $Project -PassThru -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "★ 服务已启动。打开浏览器访问 http://127.0.0.1:9999" -ForegroundColor Green
Write-Host "★ 启动 Chrome (按 Ctrl+C 退出会清理一切): " -ForegroundColor Green
Write-Host ""

# 4. Chrome（前台，按 Ctrl+C 终止整个工作流）
try {
    & "$Venv\python.exe" "$Project\core\browser.py" "https://www.zhipin.com/"
} finally {
    Write-Host ""
    Write-Host "[+] 清理后台进程..." -ForegroundColor Yellow
    if ($fastapi -and -not $fastapi.HasExited) { Stop-Process -Id $fastapi.Id -Force -EA SilentlyContinue }
    if ($mitm -and -not $mitm.HasExited) { Stop-Process -Id $mitm.Id -Force -EA SilentlyContinue }
}
