<#
.SYNOPSIS
  把打包需要的两个工具（Node.js、Inno Setup）下载到本项目的 deploy\windows\tools 中。

.DESCRIPTION
  只需运行一次：
      powershell -ExecutionPolicy Bypass -File deploy\windows\get_tools.ps1
  - Node.js：下载免安装版（zip）解压到 tools\node，不修改系统环境变量；
  - Inno Setup：静默安装到 tools\innosetup（当前用户，不需要管理员权限）。
  build_installer.ps1 会优先使用这里的工具。tools 目录不提交到 git。
  默认先从国内镜像下载 Node.js，失败再从官网下载。

.PARAMETER NodeVersion
  Node.js 版本，默认 18.20.8（前端用的 vue-cli 4 在 18 上验证过）。
.PARAMETER InnoVersion
  Inno Setup 版本，默认 6.6.1。
#>
param(
    [string]$NodeVersion = "18.20.8",
    [string]$InnoVersion = "6.6.1"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Here  = $PSScriptRoot
$Tools = Join-Path $Here "tools"
$Cache = Join-Path $Here "cache"
New-Item -ItemType Directory -Force -Path $Tools, $Cache | Out-Null

function Fail($text) { Write-Host "`n[失败] $text" -ForegroundColor Red; exit 1 }
function Get-File([string[]]$urls, $file) {
    if (Test-Path $file) { Write-Host "使用已下载的文件：$file"; return }
    foreach ($url in $urls) {
        Write-Host "下载 $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile "$file.part" -UseBasicParsing
            Move-Item "$file.part" $file -Force
            return
        } catch {
            Write-Host "  失败：$($_.Exception.Message)" -ForegroundColor Yellow
            Remove-Item "$file.part" -ErrorAction SilentlyContinue
        }
    }
    Fail "下载失败。可以用浏览器打开上面任一地址下载，把文件放到 $file 后重新运行本脚本。"
}

# ---------------------------------------------------------------- Node.js（免安装版）
$nodeDir = Join-Path $Tools "node"
if (Test-Path (Join-Path $nodeDir "node.exe")) {
    Write-Host "Node.js 已存在：$nodeDir（$(& (Join-Path $nodeDir 'node.exe') --version)）" -ForegroundColor Green
} else {
    $name = "node-v$NodeVersion-win-x64"
    $zip = Join-Path $Cache "$name.zip"
    Get-File @("https://npmmirror.com/mirrors/node/v$NodeVersion/$name.zip",
               "https://nodejs.org/dist/v$NodeVersion/$name.zip") $zip
    Write-Host "解压到 $nodeDir"
    $tmp = Join-Path $Cache "node-extract"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    if (Test-Path $nodeDir) { Remove-Item $nodeDir -Recurse -Force }
    Move-Item (Join-Path $tmp $name) $nodeDir
    Remove-Item $tmp -Recurse -Force
    Write-Host "Node.js 就绪：$(& (Join-Path $nodeDir 'node.exe') --version)" -ForegroundColor Green
}

# ---------------------------------------------------------------- Inno Setup
$innoDir = Join-Path $Tools "innosetup"
if (Test-Path (Join-Path $innoDir "ISCC.exe")) {
    Write-Host "Inno Setup 已存在：$innoDir" -ForegroundColor Green
} else {
    $exe = Join-Path $Cache "innosetup-$InnoVersion.exe"
    Get-File @("https://files.jrsoftware.org/is/6/innosetup-$InnoVersion.exe",
               "https://jrsoftware.org/download.php/is.exe") $exe
    Write-Host "安装到 $innoDir（静默安装，约 1 分钟）"
    $innoArgs = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER", "/NOICONS", "/DIR=`"$innoDir`"")
    $p = Start-Process -FilePath $exe -ArgumentList $innoArgs -Wait -PassThru
    if ($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $innoDir "ISCC.exe"))) {
        Fail "Inno Setup 安装失败（退出码 $($p.ExitCode)）。可以双击 $exe 手动安装，安装位置选 $innoDir。"
    }
    Write-Host "Inno Setup 就绪：$innoDir" -ForegroundColor Green
}

Write-Host "`n两个工具都已就绪，接下来运行打包脚本：" -ForegroundColor Cyan
Write-Host "powershell -ExecutionPolicy Bypass -File deploy\windows\build_installer.ps1 -PipIndex https://pypi.tuna.tsinghua.edu.cn/simple -NpmRegistry https://registry.npmmirror.com"
