# mitm-rpc 一键安装
# 完成: 创建 venv → 装依赖 → 装 mitm CA 证书 → 自检
# 完成后跑 .\scripts\start.ps1 即可

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "==================== mitm-rpc 安装 ====================" -ForegroundColor Cyan
Write-Host ""

# ─── Python 检查 ───
Write-Host "[1/5] 检查 Python..." -ForegroundColor Cyan
$py = Get-Command python -EA SilentlyContinue
if (-not $py) {
    Write-Error "Python 未安装。下载 3.10+ : https://www.python.org/downloads/"
    exit 1
}
$ver = (python --version 2>&1) -replace 'Python ',''
Write-Host "      Python $ver"
$verNum = [version]($ver -split '\+' | Select-Object -First 1)
if ($verNum -lt [version]"3.10") {
    Write-Error "需要 Python 3.10+，当前 $ver"; exit 1
}

# ─── venv ───
Write-Host "[2/5] 创建虚拟环境 .venv ..." -ForegroundColor Cyan
$venv = "$Project\.venv"
$venvPy = "$venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    & python -m venv $venv
    if (-not (Test-Path $venvPy)) { Write-Error "venv 创建失败"; exit 1 }
    Write-Host "      已创建"
} else {
    Write-Host "      已存在，跳过"
}

# ─── 升级 pip + 装依赖 ───
Write-Host "[3/5] 安装依赖（首次几分钟）..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r "$Project\requirements.txt" --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "依赖安装失败"; exit 1 }
Write-Host "      done"

# ─── Chrome 检查 ───
Write-Host "[4/5] 找 Chrome ..." -ForegroundColor Cyan
$chromes = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
)
$found = $null
foreach ($c in $chromes) { if (Test-Path $c) { $found = $c; break } }
if ($found) {
    Write-Host "      $found"
} else {
    Write-Warning "未找到 Chrome。如需绕反爬建议装 Chrome。Edge 也可以但兼容性可能稍差。"
    Write-Host "      下载: https://www.google.com/chrome/"
}

# ─── mitm CA cert ───
Write-Host "[5/5] 安装 mitmproxy CA 证书..." -ForegroundColor Cyan
$cer = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
$mitmdump = "$venv\Scripts\mitmdump.exe"
if (-not (Test-Path $cer)) {
    Write-Host "      生成证书 (首次启动 mitmdump)..."
    $p = Start-Process -FilePath $mitmdump -ArgumentList @("--listen-port", "18888") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 4
    Stop-Process -Id $p.Id -Force -EA SilentlyContinue
}
if (-not (Test-Path $cer)) { Write-Error "证书生成失败"; exit 1 }

# 检查是否已装
$store = certutil -user -store Root mitmproxy 2>&1 | Out-String
if ($store -match "mitmproxy") {
    Write-Host "      证书已在 Trusted Root，跳过"
} else {
    Write-Host "      安装到当前用户 Trusted Root..."
    $r = Start-Process -FilePath certutil `
        -ArgumentList @("-addstore", "-f", "-user", "Root", "`"$cer`"") `
        -Wait -PassThru -WindowStyle Hidden
    if ($r.ExitCode -ne 0) { Write-Error "certutil 失败 (exit $($r.ExitCode))"; exit 1 }
    Write-Host "      done"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "✅ 安装完成！现在运行：" -ForegroundColor Green
Write-Host ""
Write-Host "    .\scripts\start.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "之后控制台访问 http://127.0.0.1:9999" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
