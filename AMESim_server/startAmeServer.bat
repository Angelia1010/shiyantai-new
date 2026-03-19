@echo off
REM 设置代码页为UTF-8（确保文件保存为UTF-8带BOM），以正确显示中文
chcp 65001 >nul

REM 检查环境变量是否存在
if not defined AME (
    echo 环境变量 AME 未定义，请先设置该环境变量！
    pause
    exit /b
)

REM 读取环境变量，并在后面追加一段路径（如 "\python"）
set "PYTHON_DIR=%AME%\sys\python\win64"

REM 显示使用的Python路径（可选）
echo 使用的Python路径为：%PYTHON_DIR%

REM 检查Flask是否已安装
echo 检查Flask依赖...
"%PYTHON_DIR%\python.exe" -m pip show flask >nul 2>&1
if errorlevel 1 (
    echo 正在安装Flask依赖...
    "%PYTHON_DIR%\python.exe" -m pip install -r requirements.txt
)

REM 利用该路径下的python解释器运行相对路径下的python脚本
echo 启动AMESim Flask服务器...
"%PYTHON_DIR%\python.exe" "./src/AmeSimuSessionServer.py"

pause
