<#
.SYNOPSIS
  改完代码后重新生成安装包（一键）。项目根目录的「打包安装包.bat」双击即运行本脚本。

.DESCRIPTION
  1. 打包工具（Node.js、Inno Setup）不在时自动下载（get_tools.ps1）；
  2. 询问新版本号（直接回车 = 上一版本号末位加 1），写入 deploy\windows\VERSION；
  3. 前端代码（digital-twin-platform）在上次编译后改过才重新编译，否则直接用已编译的页面；
  4. 调用 build_installer.ps1 生成安装包（使用国内镜像），完成后打开 output 文件夹。

.PARAMETER Version
  直接指定版本号，不再询问。
.PARAMETER KeepVersion
  不改版本号（重新打同一版本）。
.PARAMETER RebuildFrontend
  无论前端是否改过都重新编译。
#>
param(
    [string]$Version = "",
    [switch]$KeepVersion,
    [switch]$RebuildFrontend
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Here = $PSScriptRoot
$Root = (Resolve-Path (Join-Path $Here "..\..")).Path
$PipIndex = "https://pypi.tuna.tsinghua.edu.cn/simple"
$NpmRegistry = "https://registry.npmmirror.com"

function Fail($text) { Write-Host "`n[失败] $text" -ForegroundColor Red; exit 1 }

Write-Host "==== 标准台校验系统：重新打包 ====" -ForegroundColor Green

# ---------------------------------------------------------------- 1. 打包工具
$tools = Join-Path $Here "tools"
if (-not (Test-Path (Join-Path $tools "node\node.exe")) -or -not (Test-Path (Join-Path $tools "innosetup\ISCC.exe"))) {
    Write-Host "`n打包工具不全，先下载…" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "get_tools.ps1")
    if ($LASTEXITCODE -ne 0) { Fail "下载打包工具失败" }
}

# ---------------------------------------------------------------- 2. 版本号
$versionFile = Join-Path $Here "VERSION"
$old = (Get-Content $versionFile -Raw).Trim()
if (-not $Version) {
    if ($KeepVersion) {
        $Version = $old
    } else {
        $parts = $old.Split(".")
        $parts[-1] = [string]([int]$parts[-1] + 1)
        $suggest = $parts -join "."
        $answer = Read-Host "`n当前版本 $old，新版本号（直接回车 = $suggest）"
        $Version = if ($answer.Trim()) { $answer.Trim() } else { $suggest }
    }
}
if ($Version -notmatch '^\d+(\.\d+){1,3}$') { Fail "版本号格式不对：$Version（应为 1.0.1 这样的数字）" }
Set-Content -Path $versionFile -Value $Version -Encoding ASCII
Write-Host "版本号：$Version"

# ---------------------------------------------------------------- 3. 前端是否需要重新编译
$web = Join-Path $Root "digital-twin-platform"
$distIndex = Join-Path $web "dist\index.html"
$needFrontend = $RebuildFrontend -or -not (Test-Path $distIndex)
if (-not $needFrontend) {
    $built = (Get-Item $distIndex).LastWriteTime
    $sources = @(Get-ChildItem (Join-Path $web "src"), (Join-Path $web "public") -Recurse -File -ErrorAction SilentlyContinue)
    $sources += @(Get-ChildItem $web -File | Where-Object { $_.Name -match '^(package(-lock)?\.json|vue\.config\.js|babel\.config\.js|\.env.*)$' })
    $changed = $sources | Where-Object { $_.LastWriteTime -gt $built } | Select-Object -First 5
    if ($changed) {
        $needFrontend = $true
        Write-Host "前端代码有改动（如 $($changed[0].FullName.Substring($web.Length + 1))），将重新编译前端"
    } else {
        Write-Host "前端代码没有改动，使用已编译的页面（上次编译：$built）"
    }
} else {
    Write-Host "将编译前端"
}

# ---------------------------------------------------------------- 4. 打包
$arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Here "build_installer.ps1"),
               "-Version", $Version, "-PipIndex", $PipIndex, "-NpmRegistry", $NpmRegistry)
if (-not $needFrontend) { $arguments += "-SkipFrontend" }
& powershell @arguments
if ($LASTEXITCODE -ne 0) { Fail "打包失败，请把上面的输出发给维护人员" }

$out = Join-Path $Here "output"
Write-Host "`n==== 打包完成：版本 $Version ====" -ForegroundColor Green
Write-Host "安装包在：$out"
Write-Host "提示：deploy\windows\VERSION 已改为 $Version，记得一起提交到 git。"
Start-Process explorer.exe $out
