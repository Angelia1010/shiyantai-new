<#
.SYNOPSIS
   项目启动主脚本 - 终极稳定版
.DESCRIPTION
   修复已知问题：
   1. 解决conda激活问题
   2. 修复路径处理错误
   3. 增强错误恢复能力
   4. 改进进程管理
.ENCODING
   必须保存为UTF-8 with BOM格式
#>

#region 编码强制设置
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 | Out-Null
#endregion

function Write-UTF8 {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        [string]$Color = "White",
        [string]$BackgroundColor = "Black",
        [switch]$NoNewline
    )
    
    try {
        if ($NoNewline) {
            Write-Host $Message -ForegroundColor $Color -BackgroundColor $BackgroundColor -NoNewline
        } else {
            Write-Host $Message -ForegroundColor $Color -BackgroundColor $BackgroundColor
        }
    }
    catch {
        [Console]::WriteLine($Message)
    }
    
    try {
        $Message | Out-File -Append -FilePath "$PSScriptRoot\operation.log" -Encoding utf8 -Force
    } catch {}
}

$ErrorActionPreference = "Stop"

# 初始化日志
try {
    "=== 脚本启动于 $(Get-Date) ===" | Out-File "$PSScriptRoot\operation.log" -Encoding utf8 -Force
} catch {}

Write-UTF8 "=== 环境初始化 ===" -Color Magenta
Write-UTF8 "脚本目录: $PSScriptRoot" -Color Cyan
Write-UTF8 "系统版本: $([System.Environment]::OSVersion.VersionString)" -Color Cyan
Write-UTF8 "PowerShell版本: $($PSVersionTable.PSVersion)" -Color Cyan

function Initialize-Conda {
    Write-UTF8 "`n=== Conda 初始化 ===" -Color Magenta
    
    # 尝试自动初始化 Conda
    try {
        $condaHook = conda shell.powershell hook | Out-String
        if (-not [string]::IsNullOrWhiteSpace($condaHook)) {
            Invoke-Expression $condaHook
            Write-UTF8 "Conda 初始化成功" -Color Green
            return $true
        }
    } catch {
        Write-UTF8 "[警告] Conda 自动初始化失败: $_" -Color Yellow
    }

    # 备用方案：手动添加 Conda 到 PATH
    $condaPaths = @(
        "$env:USERPROFILE\miniconda3",
        "$env:USERPROFILE\Anaconda3",
        "$env:ProgramData\Miniconda3",
        "$env:ProgramData\Anaconda3"
    )

    foreach ($path in $condaPaths) {
        $condaPath = Join-Path $path "Scripts\conda.exe"
        if (Test-Path $condaPath) {
            $env:Path = "$([System.Environment]::GetEnvironmentVariable('PATH', 'User'));$path\Scripts;$path\Library\bin"
            Write-UTF8 "手动添加 Conda 路径: $path" -Color Yellow
            return $true
        }
    }

    Write-UTF8 "[严重错误] 未找到 Conda 安装，请先安装 Miniconda/Anaconda" -Color Red
    return $false
}

function Start-Redis {
    $redisPath = Join-Path $PSScriptRoot "redis\redis-server.exe"
    $redisConfig = Join-Path $PSScriptRoot "redis\redis.windows.conf"
    $redisPort = 6380

    Write-UTF8 "`n=== Redis服务初始化 ===" -Color Magenta
    Write-UTF8 "Redis路径: $redisPath" -Color DarkGray

    if (-not (Test-Path $redisPath)) {
        $errorMsg = @"
[Redis配置错误]
未找到Redis可执行文件！
预期路径: $redisPath
请检查:
1. Redis是否解压到项目下的redis目录
2. 是否从项目根目录运行脚本
3. 路径是否包含特殊字符
"@
        throw $errorMsg
    }

    # 端口占用检查
    Write-UTF8 "`n[$(Get-Date)] 检查端口 $redisPort..." -Color Cyan
    try {
        $portInUse = Test-NetConnection -ComputerName localhost -Port $redisPort -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($portInUse) {
            $conn = Get-NetTCPConnection -LocalPort $redisPort -ErrorAction SilentlyContinue | 
                    Where-Object { $_.State -eq 'Established' }
            
            if ($conn) {
                $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                if ($process) {
                    Write-UTF8 "发现占用进程: $($process.Name) (PID: $($process.Id))" -Color Yellow
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 2
                }
            }
        }
    }
    catch {
        Write-UTF8 "[端口检查警告] $_" -Color Yellow
    }

    # 启动Redis
    Write-UTF8 "`n[$(Get-Date)] 启动Redis服务..." -Color Green
    try {
        $redisProcess = Start-Process -FilePath $redisPath `
            -ArgumentList "$redisConfig" `
            -WorkingDirectory (Join-Path $PSScriptRoot "redis") `
            -WindowStyle Normal `
            -PassThru

        # 等待启动
        $timeout = 20
        $startTime = Get-Date
        do {
            $elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds)
            Write-UTF8 "等待Redis启动...($elapsed/$timeout秒)" -Color DarkGray -NoNewline
            Write-Host "`r" -NoNewline
            
            Start-Sleep -Seconds 1
            $portReady = Test-NetConnection -ComputerName localhost -Port $redisPort -InformationLevel Quiet -WarningAction SilentlyContinue
            
            if ((Get-Date) - $startTime -gt [TimeSpan]::FromSeconds($timeout)) {
                throw "Redis启动超时（超过${timeout}秒）"
            }
        } while (-not $portReady)

        Write-UTF8 "`n[$(Get-Date)] Redis启动成功 (PID: $($redisProcess.Id))" -Color Green
        return $redisProcess
    }
    catch {
        Write-UTF8 "[Redis启动失败] $_" -Color Red
        if (Test-Path "$PSScriptRoot\redis\redis.log") {
            $logContent = Get-Content "$PSScriptRoot\redis\redis.log" -Tail 10 -ErrorAction SilentlyContinue
            Write-UTF8 "Redis日志片段:`n$logContent" -Color Yellow
        }
        throw
    }
}

function Start-PythonServices {
    param(
        [string]$condaEnv = "base",
        [switch]$SkipActivation = $false
    )
    
    $services = @(
        "file_monitor_service.py",
        "db_server.py",
        "llm_analysis_server.py"
    )
    
    $serviceDir = Join-Path $PSScriptRoot "app\services"
    Write-UTF8 "`n=== Python服务初始化 ===" -Color Magenta
    Write-UTF8 "服务目录: $serviceDir" -Color DarkGray

    if (-not (Test-Path $serviceDir)) {
        $errorMsg = @"
[目录配置错误]
未找到服务目录！
预期路径: $serviceDir
请检查:
1. 项目结构是否正确
2. 是否从项目根目录运行
3. 路径是否包含中文或特殊字符
"@
        throw $errorMsg
    }

    try {
        Set-Location -Path $serviceDir -ErrorAction Stop

        # Conda环境处理
        if (-not $SkipActivation) {
            Write-UTF8 "`n[$(Get-Date)] 准备Python环境..." -Color Cyan
            
            # 检查conda可用性
            try {
                $condaInfo = conda info --json 2>$null | ConvertFrom-Json
                Write-UTF8 "Conda版本: $($condaInfo.conda_version)" -Color DarkGray
            } catch {
                throw "Conda不可用！请确认: 1) Conda已安装 2) Conda在PATH中"
            }

            # 激活环境（改进版）
            Write-UTF8 "激活环境: $condaEnv" -Color DarkGray
            try {
                # 方法1：标准激活
                conda activate $condaEnv
                
                # 方法2：备用激活方式
                if ($LASTEXITCODE -ne 0) {
                    $activatePath = Join-Path (conda info --base) "Scripts\activate"
                    if (Test-Path $activatePath) {
                        & $activatePath $condaEnv
                    }
                }
                
                # 方法3：直接设置环境变量
                if ($LASTEXITCODE -ne 0) {
                    $envPath = Join-Path (conda info --base) "envs\$condaEnv"
                    if (Test-Path $envPath) {
                        $env:CONDA_PREFIX = $envPath
                        $env:PATH = "$envPath;$envPath\Scripts;$envPath\Library\bin;" + $env:PATH
                    }
                }
                
                if ($LASTEXITCODE -ne 0 -and -not (Test-Path env:CONDA_PREFIX)) {
                    throw "无法激活环境 '$condaEnv'，可用环境: $(conda env list --json | ConvertFrom-Json).envs"
                }
            } catch {
                Write-UTF8 "[环境激活警告] $_" -Color Yellow
            }

            # 验证Python
            $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
            if (-not $pythonPath) {
                throw "Python 解释器未找到！"
            }
            Write-UTF8 "Python路径: $pythonPath" -Color DarkGray
            Write-UTF8 "Python版本: $(python --version 2>&1)" -Color DarkGray
        }

        # 启动服务
        foreach ($service in $services) {
            try {
                $servicePath = Join-Path $serviceDir $service
                if (-not (Test-Path $servicePath)) {
                    Write-UTF8 "[警告] 跳过服务: $service (文件不存在)" -Color Yellow
                    continue
                }

                Write-UTF8 "`n[$(Get-Date)] 启动服务: $service" -Color Green
                $logFile = "$serviceDir\logs\$service-$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
                
                # 创建日志目录
                if (-not (Test-Path "$serviceDir\logs")) {
                    New-Item -ItemType Directory -Path "$serviceDir\logs" -Force | Out-Null
                }

                # 启动进程
                $process = Start-Process -FilePath python `
                    -ArgumentList "-u", "$service" `
                    -WorkingDirectory $serviceDir `
                    -NoNewWindow `
                    -PassThru `
                    -RedirectStandardOutput $logFile `
                    -RedirectStandardError "$logFile.error"
                
                # 验证启动
                Start-Sleep -Seconds 3
                if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
                    $errorContent = Get-Content "$logFile.error" -Tail 10 -ErrorAction SilentlyContinue
                    $errorMsg = @"
服务启动失败: $service
可能原因:
1. 缺少依赖包 (运行: pip install -r requirements.txt)
2. 脚本语法错误
3. 端口冲突
错误日志:
$errorContent
"@
                    throw $errorMsg
                }
                
                Write-UTF8 "[状态] 运行中 (PID: $($process.Id))" -Color Green
                Write-UTF8 "[日志] $logFile" -Color DarkGray
            }
            catch {
                Write-UTF8 "[服务错误] $_" -Color Red
                continue
            }
        }
    }
    catch {
        Write-UTF8 "[Python环境错误] $_" -Color Red
        throw
    }
}

# 主执行流程
try {
    # 显示横幅
    $banner = @"
==================================================
  项目启动器 - $(Get-Date)
  系统: $([System.Environment]::OSVersion.VersionString)
  PowerShell: $($PSVersionTable.PSVersion)
==================================================
"@
    Write-UTF8 $banner -Color Yellow

    # 初始化 Conda
    if (-not (Initialize-Conda)) {
        throw "Conda 初始化失败，无法继续执行"
    }

    # 执行启动
    $redisProcess = $null
    try {
        $redisProcess = Start-Redis
    } catch {
        Write-UTF8 "[Redis初始化失败] $_" -Color Red
        throw
    }

    try {
        Start-PythonServices
    } catch {
        Write-UTF8 "[Python服务初始化失败] $_" -Color Red
        if ($redisProcess) {
            Stop-Process -Id $redisProcess.Id -Force -ErrorAction SilentlyContinue
        }
        throw
    }

    # 状态报告
    Write-UTF8 "`n[$(Get-Date)] 服务状态汇总" -Color Green
    Write-UTF8 "Redis: 运行中 (PID: $($redisProcess.Id))" -Color Cyan
    
    $pythonProcesses = Get-Process python -ErrorAction SilentlyContinue | 
        Where-Object { $_.Path -and $_.Path.StartsWith($PSScriptRoot) }
    
    if ($pythonProcesses) {
        Write-UTF8 "Python服务:" -Color Cyan
        $pythonProcesses | ForEach-Object {
            Write-UTF8 "- $($_.Name): PID $($_.Id)" -Color DarkGray
        }
    }

    Write-UTF8 "`n[$(Get-Date)] 所有服务已就绪！" -Color Green -BackgroundColor DarkGreen
    Write-UTF8 "按 Ctrl+C 终止服务" -Color DarkGray
    Write-UTF8 "="*50 -Color DarkYellow

    # 保持运行
    while ($true) {
        Start-Sleep -Seconds 60
        Write-UTF8 "[$(Get-Date)] 服务运行中..." -Color DarkGray
    }
}
catch {
    Write-UTF8 "`n[致命错误] $_" -Color White -BackgroundColor DarkRed
    Write-UTF8 "终止于: $(Get-Date)" -Color Red
    
    # 清理资源
    try {
        if ($redisProcess) { Stop-Process -Id $redisProcess.Id -Force -ErrorAction SilentlyContinue }
        Get-Process python -ErrorAction SilentlyContinue | 
            Where-Object { $_.Path -and $_.Path.StartsWith($PSScriptRoot) } | 
            Stop-Process -Force -ErrorAction SilentlyContinue
    } catch {}
    
    exit 1
}