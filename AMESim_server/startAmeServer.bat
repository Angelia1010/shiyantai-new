@echo off
chcp 65001 >nul
REM 用 AMESim 自带的 Python 启动 AMESim 仿真服务。配置读取仓库根目录的 .env。

if not defined AME (
    echo 环境变量 AME 未定义，请先把它设置为 AMESim 安装目录。
    pause
    exit /b 1
)

set "AME_PYTHON=%AME%\sys\python\win64\python.exe"
REM 切换到仓库根目录，服务以模块方式启动，才能找到 shared 公共包
cd /d "%~dp0.."

"%AME_PYTHON%" -m pip show flask >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖...
    "%AME_PYTHON%" -m pip install -r AMESim_server\requirements.txt
)

echo 启动 AMESim 服务...
"%AME_PYTHON%" -m AMESim_server.src.AmeSimuSessionServer
pause
