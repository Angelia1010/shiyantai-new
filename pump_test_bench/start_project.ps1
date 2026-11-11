<#
.SYNOPSIS
  启动平台后端服务：任务服务(5001)、文件服务(5002)、大模型分析服务(8999)。
.DESCRIPTION
  在仓库根目录以 "python -m" 方式启动各服务，每个服务一个窗口；配置读取仓库根目录的 .env。
  AMESim 服务需要 AMESim 自带的 Python，请单独运行 AMESim_server\startAmeServer.bat。
.PARAMETER CondaEnv
  conda 环境名，默认 backend503（见 environment.yml）。传空字符串则使用当前 PATH 中的 python。
.PARAMETER SkipLlm
  不启动大模型分析服务。
#>
param(
    [string]$CondaEnv = "backend503",
    [switch]$SkipLlm
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $repoRoot ".env"))) {
    Write-Host "未找到 $repoRoot\.env，请先复制 .env.example 为 .env 并填写 SECRET_KEY、ADMIN_PASSWORD、DATA_ROOTS。" -ForegroundColor Red
    exit 1
}

if ($CondaEnv) {
    $hook = conda shell.powershell hook | Out-String
    Invoke-Expression $hook
    conda activate $CondaEnv
}
$python = (Get-Command python).Source
Write-Host "使用 Python: $python ($(python --version 2>&1))" -ForegroundColor Cyan

$services = @(
    "pump_test_bench.app.services.task_service",
    "pump_test_bench.app.services.file_service"
)
if (-not $SkipLlm) {
    $services += "pump_test_bench.app.services.llm_service"
}

foreach ($module in $services) {
    Write-Host "启动 $module" -ForegroundColor Green
    Start-Process -FilePath $python -ArgumentList "-m", $module -WorkingDirectory $repoRoot
}

Write-Host "全部服务已启动，日志位于 $repoRoot\logs。关闭对应窗口即可停止服务。" -ForegroundColor Cyan
