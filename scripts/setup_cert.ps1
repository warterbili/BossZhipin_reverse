# 一次性: 安装 mitmproxy CA 证书到当前用户的 Trusted Root
# 之后 Chrome 走 mitm 才能解密 HTTPS

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Mitmdump = Join-Path $Project ".venv\Scripts\mitmdump.exe"

if (-not (Test-Path $Mitmdump)) {
    Write-Error "未找到 mitmdump，先跑: python -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$CerFile = Join-Path $env:USERPROFILE ".mitmproxy\mitmproxy-ca-cert.cer"
if (-not (Test-Path $CerFile)) {
    Write-Host "[+] 首次启动 mitmdump 生成证书..."
    $p = Start-Process -FilePath $Mitmdump -ArgumentList @("--listen-port", "18888") `
        -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 4
    Stop-Process -Id $p.Id -Force
}
if (-not (Test-Path $CerFile)) { Write-Error "证书未生成: $CerFile"; exit 1 }

Write-Host "[+] 证书路径: $CerFile"
Write-Host "[+] 加入当前用户 Trusted Root..."
$r = Start-Process -FilePath certutil `
    -ArgumentList @("-addstore", "-f", "-user", "Root", "`"$CerFile`"") `
    -Wait -PassThru -WindowStyle Hidden
if ($r.ExitCode -eq 0) {
    Write-Host "[+] ✅ 证书已安装" -ForegroundColor Green
    Write-Host "[+] 接下来跑: .\scripts\start.ps1"
} else {
    Write-Error "certutil 失败 (exit $($r.ExitCode))"
}
