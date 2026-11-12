<#
.SYNOPSIS
  生成“标准台校验系统”的 Windows 安装包（一键打包）。

.DESCRIPTION
  在一台能联网的 Windows 电脑上，于仓库任意位置运行：
      powershell -ExecutionPolicy Bypass -File deploy\windows\build_installer.ps1
  依次完成：
    1. 下载 Python 嵌入式运行环境（只下载一次，缓存在 deploy\windows\cache）；
    2. 安装后端依赖（requirements-runtime.txt）到这份 Python 中；
    3. 编译前端（digital-twin-platform → dist）；
    4. 组装安装目录（deploy\windows\build\stage）并做启动自检；
    5. 调用 Inno Setup 生成安装包 deploy\windows\output\BenchCheck-Setup-<版本>.exe。
  打包电脑需要：Node.js（16 或 18 LTS，带 npm）、Inno Setup 6。目标电脑什么都不用装。

.PARAMETER Version
  安装包版本号，默认读取 deploy\windows\VERSION。
.PARAMETER PythonVersion
  嵌入式 Python 版本，默认 3.11.9（与开发环境一致）。
.PARAMETER PipIndex
  pip 镜像，如 https://pypi.tuna.tsinghua.edu.cn/simple（国内网络建议填写）。
.PARAMETER NpmRegistry
  npm 镜像，如 https://registry.npmmirror.com。
.PARAMETER SkipFrontend
  不重新编译前端，直接使用已有的 digital-twin-platform\dist。
.PARAMETER CleanFrontend
  删除已有的前端依赖（node_modules），用 npm ci 全新安装。默认已有依赖时直接使用。
.PARAMETER NoInstaller
  只组装 stage 目录，不生成安装包（用于检查）。
#>
param(
    [string]$Version = "",
    [string]$PythonVersion = "3.11.9",
    [string]$PipIndex = "",
    [string]$NpmRegistry = "",
    [switch]$SkipFrontend,
    [switch]$CleanFrontend,
    [switch]$NoInstaller
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest 不显示进度条时快得多
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Here  = $PSScriptRoot
$Root  = (Resolve-Path (Join-Path $Here "..\..")).Path
$Cache = Join-Path $Here "cache"
$Build = Join-Path $Here "build"
$Stage = Join-Path $Build "stage"
$Out   = Join-Path $Here "output"
if (-not $Version) { $Version = (Get-Content (Join-Path $Here "VERSION") -Raw).Trim() }

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`n[失败] $text" -ForegroundColor Red; exit 1 }
# 依次尝试多个地址（国内镜像在前）；$check 用于确认下载到的是需要的文件，而不是网页
function Download([string[]]$urls, $file, [scriptblock]$check) {
    if ((Test-Path $file) -and (& $check $file)) { Write-Host "使用缓存：$file"; return }
    Remove-Item $file -ErrorAction SilentlyContinue
    foreach ($url in $urls) {
        Write-Host "下载 $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile "$file.part" -UseBasicParsing -UserAgent "Mozilla/5.0"
            if (& $check "$file.part") { Move-Item "$file.part" $file -Force; return }
            Write-Host "  下载到的不是需要的文件，换下一个地址" -ForegroundColor Yellow
        } catch {
            Write-Host "  失败：$($_.Exception.Message)" -ForegroundColor Yellow
        }
        Remove-Item "$file.part" -ErrorAction SilentlyContinue
    }
    Fail "下载失败。可以用浏览器打开上面任一地址下载，把文件放到 $file 后重新运行。"
}
$IsZip = { param($f) (Get-Item $f).Length -gt 1MB -and ([System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($f)[0..1]) -eq "PK") }
$IsGetPip = { param($f) (Get-Item $f).Length -gt 100KB -and ((Get-Content $f -TotalCount 40 -Encoding UTF8) -join "`n") -match "pip" }
function Invoke-Checked($exe, [string[]]$arguments, $what) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "$what（退出码 $LASTEXITCODE）" }
}

Write-Host "标准台校验系统 安装包打包  版本 $Version" -ForegroundColor Green
Write-Host "仓库：$Root"
New-Item -ItemType Directory -Force -Path $Cache, $Build, $Out | Out-Null

# ---------------------------------------------------------------- 0. 检查工具
Step "检查打包工具"
# 优先使用 get_tools.ps1 下载到项目里的工具（deploy\windows\tools）
$localNode = Join-Path $Here "tools\node"
if (Test-Path (Join-Path $localNode "node.exe")) { $env:Path = "$localNode;$env:Path" }
$iscc = $null
if (-not $NoInstaller) {
    $candidates = @(
        (Join-Path $Here "tools\innosetup\ISCC.exe"),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { $cmd = Get-Command iscc -ErrorAction SilentlyContinue; if ($cmd) { $iscc = $cmd.Source } }
    if (-not $iscc) { Fail "没有找到 Inno Setup（ISCC.exe）。请先运行：powershell -ExecutionPolicy Bypass -File deploy\windows\get_tools.ps1" }
    Write-Host "Inno Setup：$iscc"
}
if (-not $SkipFrontend) {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { Fail "没有找到 Node.js。请先运行：powershell -ExecutionPolicy Bypass -File deploy\windows\get_tools.ps1" }
    $nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
    Write-Host "Node.js：$(& node --version)"
}

# ---------------------------------------------------------------- 1. 清理
Step "准备目录 $Stage"
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

# ---------------------------------------------------------------- 2. Python 运行环境
Step "Python $PythonVersion 嵌入式运行环境"
$pyZip = Join-Path $Cache "python-$PythonVersion-embed-amd64.zip"
Download @("https://mirrors.huaweicloud.com/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip",
           "https://npmmirror.com/mirrors/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip",
           "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip") $pyZip $IsZip
$pyDir = Join-Path $Stage "python"
Expand-Archive -Path $pyZip -DestinationPath $pyDir -Force
$tag = ($PythonVersion.Split(".")[0..1] -join "")
# ._pth：加入程序目录 ..\app，并启用 site（pip 安装的包在 Lib\site-packages）
$pth = Join-Path $pyDir "python$tag._pth"
Set-Content -Path $pth -Encoding ASCII -Value @("python$tag.zip", ".", "..\app", "import site")
$py = Join-Path $pyDir "python.exe"

$getPip = Join-Path $Cache "get-pip.py"
Download @("https://mirrors.aliyun.com/pypi/get-pip.py",
           "https://bootstrap.pypa.io/get-pip.py") $getPip $IsGetPip
$pipArgs = @("--no-warn-script-location", "--disable-pip-version-check")
if ($PipIndex) { $pipArgs += @("-i", $PipIndex) }
Invoke-Checked $py (@($getPip) + $pipArgs) "安装 pip"
Step "安装后端依赖"
$wheelCache = Join-Path $Cache "pip"
Invoke-Checked $py (@("-m", "pip", "install", "-r", (Join-Path $Here "requirements-runtime.txt"), "--cache-dir", $wheelCache) + $pipArgs) "安装依赖"
# 打包后不需要 pip 自身，删掉减小体积
& $py -m pip uninstall -y pip setuptools wheel | Out-Null
Get-ChildItem $pyDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $pyDir -Recurse -Directory -Filter "tests" | Where-Object { $_.FullName -match "site-packages\\(numpy|pandas)\\" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- 3. 前端
$web = Join-Path $Root "digital-twin-platform"
if (-not $SkipFrontend) {
    Step "编译前端"
    Push-Location $web
    try {
        if ($NpmRegistry) { $env:npm_config_registry = $NpmRegistry }
        if ($nodeMajor -ge 17) { $env:NODE_OPTIONS = "--openssl-legacy-provider" }
        $nm = Join-Path $web "node_modules"
        if ((Test-Path (Join-Path $nm ".bin")) -and -not $CleanFrontend) {
            Write-Host "使用已有的前端依赖（node_modules）；需要全新安装时加参数 -CleanFrontend"
        } else {
            Invoke-Checked "npm.cmd" @("ci", "--no-audit", "--no-fund") ("安装前端依赖（npm ci）。如提示文件夹删不掉，" +
                "请先关闭正在运行的前端开发服务（npm run dev 的窗口）和打开该目录的编辑器后重试")
        }
        # 开发服务留下的编译缓存可能被占用或过期，编译前清掉（删不掉也不影响）
        Remove-Item (Join-Path $nm ".cache") -Recurse -Force -ErrorAction SilentlyContinue
        Invoke-Checked "npm.cmd" @("run", "build:prod") "编译前端（npm run build:prod）"
    } finally { Pop-Location }
}
$dist = Join-Path $web "dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) { Fail "没有找到编译好的前端：$dist\index.html" }
Copy-Item $dist (Join-Path $Stage "web") -Recurse

# ---------------------------------------------------------------- 4. 程序
Step "复制程序"
$app = Join-Path $Stage "app"
New-Item -ItemType Directory -Force -Path $app | Out-Null
foreach ($dir in @("shared", "pump_test_bench", "AMESim_server")) {
    # robocopy 退出码小于 8 表示成功
    robocopy (Join-Path $Root $dir) (Join-Path $app $dir) /E /NFL /NDL /NJH /NJS /NP `
        /XD "__pycache__" "tests" "data" "logs" ".pytest_cache" /XF "*.pyc" "*.db" | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "复制 $dir 失败" }
}
Copy-Item (Join-Path $Root ".env.example") $app
# 智能助手（本地大模型）的部署说明，供勾选“智能助手”时参考
New-Item -ItemType Directory -Force -Path (Join-Path $app "DeepSeek-model") | Out-Null
Copy-Item (Join-Path $Root "DeepSeek-model\README.md"), (Join-Path $Root "DeepSeek-model\说明.docx") (Join-Path $app "DeepSeek-model") -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Here "installer_tools.py") $Stage
Copy-Item (Join-Path $Here "scripts\*.bat") $Stage
Set-Content -Path (Join-Path $Stage "VERSION") -Value $Version -Encoding ASCII

# ---------------------------------------------------------------- 5. 自检
Step "启动自检"
Push-Location $app
try {
    Invoke-Checked $py @("-c", "import pandas, numpy, flask, waitress, docx, openpyxl, nptdms, fastapi, uvicorn; import pump_test_bench.app.services.supervisor, pump_test_bench.app.services.task_service, pump_test_bench.app.services.file_service, pump_test_bench.app.services.llm_service; print('依赖与程序模块导入正常')") "导入自检"
} finally { Pop-Location }
$sizeMb = [math]::Round(((Get-ChildItem $Stage -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host "安装目录内容共 $sizeMb MB：$Stage"
if ($NoInstaller) { Write-Host "`n已按 -NoInstaller 跳过生成安装包。" -ForegroundColor Yellow; exit 0 }

# ---------------------------------------------------------------- 6. 安装包
Step "生成安装包"
$isccDir = Split-Path $iscc
# 有完整的中文语言文件就用它；没有时 setup.iss 用项目自带的 ChineseSimplified-partial.isl
$chs = Join-Path $isccDir "Languages\ChineseSimplified.isl"
# 杀毒软件常在安装包 exe 刚写出时锁住扫描，导致“另一个程序正在使用此文件”：
# 每次编译到新的临时目录，失败时等几秒重试，成功后再移到 output
$exeName = "BenchCheck-Setup-$Version.exe"
$exe = Join-Path $Out $exeName
$compiled = $null
for ($try = 1; $try -le 3; $try++) {
    $tmpOut = Join-Path $Build ("iscc-out-" + (Get-Date -Format "HHmmss") + "-$try")
    New-Item -ItemType Directory -Force -Path $tmpOut | Out-Null
    $isccArgs = @("/DAppVersion=$Version", "/DStageDir=$Stage", "/DOutputDir=$tmpOut")
    if (Test-Path $chs) { $isccArgs += "/DChineseIsl=$chs" }
    & $iscc @($isccArgs + @((Join-Path $Here "setup.iss")))
    if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $tmpOut $exeName))) { $compiled = Join-Path $tmpOut $exeName; break }
    if ($try -lt 3) {
        Write-Host "`n第 $try 次编译失败（退出码 $LASTEXITCODE），10 秒后重试…" -ForegroundColor Yellow
        Start-Sleep -Seconds 10
    }
}
if (-not $compiled) {
    Fail ("Inno Setup 编译失败。如果提示“另一个程序正在使用此文件”，多半是杀毒软件在扫描生成的安装包：" +
          "请在 Windows 安全中心 → 病毒和威胁防护 → 排除项 中添加文件夹 $Here ，然后重新运行。")
}
Start-Sleep -Seconds 2
if (Test-Path $exe) { Remove-Item $exe -Force -ErrorAction SilentlyContinue }
if (Test-Path $exe) {
    $exe = Join-Path $Out ("BenchCheck-Setup-$Version-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".exe")
    Write-Host "原来的安装包文件被占用，新安装包另存为 $exe" -ForegroundColor Yellow
}
Move-Item $compiled $exe -Force
Get-ChildItem $Build -Directory -Filter "iscc-out-*" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$exeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "`n完成：$exe（$exeMb MB）" -ForegroundColor Green
Write-Host "把这个文件拷到目标电脑，双击安装即可。"
