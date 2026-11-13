@echo off
chcp 65001 >nul
REM 模拟试验台实时产出数据：按时间一行一行往一个目录里写数据文件（正常数据 + 注入了故障的数据）。
REM 在系统工作台“数据目录”填写脚本给出的写入目录并打开“自动诊断”，即可在页面上看实时显示与诊断结论。
REM 用法：双击（正常 2 个 + 典型故障 7 个）；或加参数，如  测试实时诊断.bat --cases all  /  --source D:\我的数据  /  --speed 4
cd /d "%~dp0"
set "PY="
if exist "%ProgramFiles%\BenchCheck\python\python.exe" set "PY=%ProgramFiles%\BenchCheck\python\python.exe"
if not defined PY if exist "%~dp0deploy\windows\build\stage\python\python.exe" set "PY=%~dp0deploy\windows\build\stage\python\python.exe"
if not defined PY set "PY=python"
REM 始终运行仓库里的最新脚本（安装版自带的 Python 默认只读安装目录里的程序）
"%PY%" -c "import sys, runpy; sys.path.insert(0, r'%~dp0.'); runpy.run_module('pump_test_bench.tools.simulate_live_data', run_name='__main__', alter_sys=True)" --healthy "%~dp0标准台性能录取数据\标准台性能录取数据" %*
echo.
pause
