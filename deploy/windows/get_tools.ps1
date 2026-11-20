<#
.SYNOPSIS
  把打包需要的两个工具（Node.js、Inno Setup）下载到本项目的 deploy\windows\tools 中。

.DESCRIPTION
  只需运行一次：
      powershell -ExecutionPolicy Bypass -File deploy\windows\get_tools.ps1
  - Node.js：下载免安装版（zip）解压到 tools\node，不修改系统环境变量；
  - Inno Setup：优先从 npm 国内镜像获取（npm 包 innosetup-compiler 自带 ISCC.exe，不需要访问 GitHub），
    放到 tools\innosetup；不行时再尝试官方安装程序（GitHub）与 winget；
  - 安装向导的中文界面文字随项目提供（ChineseSimplified-partial.isl），不需要下载。
  build_installer.ps1 会优先使用这里的工具。tools 目录不提交到 git。
  默认先从国内镜像下载 Node.js，失败再从官网下载。

.PARAMETER NodeVersion
  Node.js 版本，默认 18.20.8（前端用的 vue-cli 4 在 18 上验证过）。
.PARAMETER InnoVersion
  从 GitHub 下载官方安装程序时的备用版本号（默认 6.7.4）。
.PARAMETER NpmRegistry
  npm 镜像，默认 https://registry.npmmirror.com。
#>
param(
    [string]$NodeVersion = "18.20.8",
    [string]$InnoVersion = "6.7.4",
    [string]$NpmInnoVersion = "6.3.1",
    [string]$NpmRegistry = "https://registry.npmmirror.com"
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
# 检查下载的文件确实是需要的类型（下载到网页时不能用）：exe 以 "MZ" 开头，zip 以 "PK" 开头
function Test-Download($file, $kind) {
    if (-not (Test-Path $file)) { return $false }
    $info = Get-Item $file
    if ($info.Length -lt 1MB) { return $false }
    $fs = [System.IO.File]::OpenRead($file)
    try { $b = New-Object byte[] 2; [void]$fs.Read($b, 0, 2) } finally { $fs.Close() }
    $sig = [System.Text.Encoding]::ASCII.GetString($b)
    return ($kind -eq "exe" -and $sig -eq "MZ") -or ($kind -eq "zip" -and $sig -eq "PK")
}


function Get-File([string[]]$urls, $file, $kind, [switch]$Optional) {
    if (Test-Download $file $kind) { Write-Host "使用已下载的文件：$file"; return $true }
    Remove-Item $file -ErrorAction SilentlyContinue   # 之前下载坏了的文件
    foreach ($url in $urls) {
        if (-not $url) { continue }
        Write-Host "下载 $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile "$file.part" -UseBasicParsing -UserAgent "Mozilla/5.0"
            if (Test-Download "$file.part" $kind) {
                Move-Item "$file.part" $file -Force
                return $true
            }
            Write-Host "  下载到的不是有效的安装文件（可能是网页），换下一个地址" -ForegroundColor Yellow
        } catch {
            Write-Host "  失败：$($_.Exception.Message)" -ForegroundColor Yellow
        }
        Remove-Item "$file.part" -ErrorAction SilentlyContinue
    }
    if ($Optional) { return $false }
    Fail "下载失败。可以用浏览器打开上面任一地址下载，把文件放到 $file 后重新运行本脚本。"
}

# 从 GitHub 查 Inno Setup 6 的最新安装程序地址（官网的下载放在 GitHub 上）
function Find-InnoUrl {
    try {
        $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/jrsoftware/issrc/releases?per_page=30" `
            -UseBasicParsing -UserAgent "Mozilla/5.0"
        foreach ($r in $releases) {
            if ($r.prerelease -or $r.draft) { continue }
            $asset = $r.assets | Where-Object { $_.name -match '^innosetup-6\.\d+\.\d+\.exe$' } | Select-Object -First 1
            if ($asset) { Write-Host "GitHub 上 Inno Setup 6 的最新版：$($asset.name)"; return $asset.browser_download_url }
        }
    } catch {
        Write-Host "查询 GitHub 失败：$($_.Exception.Message)" -ForegroundColor Yellow
    }
    return $null
}

# ---------------------------------------------------------------- Node.js（免安装版）
$nodeDir = Join-Path $Tools "node"
if (Test-Path (Join-Path $nodeDir "node.exe")) {
    Write-Host "Node.js 已存在：$nodeDir（$(& (Join-Path $nodeDir 'node.exe') --version)）" -ForegroundColor Green
} else {
    $name = "node-v$NodeVersion-win-x64"
    $zip = Join-Path $Cache "$name.zip"
    Get-File @("https://npmmirror.com/mirrors/node/v$NodeVersion/$name.zip",
               "https://nodejs.org/dist/v$NodeVersion/$name.zip") $zip "zip" | Out-Null
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
    $installed = $false
    $localNpm = Join-Path $nodeDir "npm.cmd"
    if (Test-Path $localNpm) {
        Write-Host "从 npm 镜像获取 Inno Setup（innosetup-compiler@$NpmInnoVersion，$NpmRegistry）"
        $npmTmp = Join-Path $Cache "inno-npm"
        if (Test-Path $npmTmp) { Remove-Item $npmTmp -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $npmTmp | Out-Null
        $env:Path = "$nodeDir;$env:Path"
        & $localNpm install "innosetup-compiler@$NpmInnoVersion" --prefix $npmTmp --registry $NpmRegistry --no-audit --no-fund --loglevel error
        $bin = Join-Path $npmTmp "node_modules\innosetup-compiler\bin"
        if (Test-Path (Join-Path $bin "ISCC.exe")) {
            if (Test-Path $innoDir) { Remove-Item $innoDir -Recurse -Force }
            Copy-Item $bin $innoDir -Recurse
            $installed = Test-Path (Join-Path $innoDir "ISCC.exe")
        }
        Remove-Item $npmTmp -Recurse -Force -ErrorAction SilentlyContinue
        if (-not $installed) { Write-Host "从 npm 获取失败，改用官方安装程序" -ForegroundColor Yellow }
    }
    if ($installed) { Write-Host "Inno Setup 就绪（来自 npm）：$innoDir" -ForegroundColor Green }
}
if (-not (Test-Path (Join-Path $innoDir "ISCC.exe"))) {
    $exe = Join-Path $Cache "innosetup-6-setup.exe"
    $tag = "is-" + ($InnoVersion -replace '\.', '_')
    $urls = @(
        (Find-InnoUrl),
        "https://github.com/jrsoftware/issrc/releases/download/$tag/innosetup-$InnoVersion.exe",
        "https://files.jrsoftware.org/is/6/innosetup-$InnoVersion.exe"
    )
    if (Get-File $urls $exe "exe" -Optional) {
        Write-Host "安装到 $innoDir（静默安装，约 1 分钟）"
        $innoArgs = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER", "/NOICONS", "/DIR=`"$innoDir`"")
        $p = Start-Process -FilePath $exe -ArgumentList $innoArgs -Wait -PassThru
        $installed = ($p.ExitCode -eq 0) -and (Test-Path (Join-Path $innoDir "ISCC.exe"))
        if (-not $installed) { Write-Host "静默安装未成功（退出码 $($p.ExitCode)）" -ForegroundColor Yellow }
    }
    if (-not $installed -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "改用 winget 安装 Inno Setup 6 到 $innoDir"
        & winget install --id JRSoftware.InnoSetup -e -s winget --silent --location $innoDir `
            --accept-package-agreements --accept-source-agreements
        $installed = Test-Path (Join-Path $innoDir "ISCC.exe")
    }
    if (-not $installed) {
        Fail ("Inno Setup 没有装好。请用浏览器打开 https://jrsoftware.org/isdl.php ，下载 Inno Setup 6 的安装程序（innosetup-6.x.x.exe），" +
              "双击安装，安装位置选：$innoDir ，装好后重新运行本脚本。")
    }
    Write-Host "Inno Setup 就绪：$innoDir" -ForegroundColor Green
}

Write-Host "`n两个工具都已就绪，接下来运行打包脚本：" -ForegroundColor Cyan
Write-Host "powershell -ExecutionPolicy Bypass -File deploy\windows\build_installer.ps1 -PipIndex https://pypi.tuna.tsinghua.edu.cn/simple -NpmRegistry https://registry.npmmirror.com"
