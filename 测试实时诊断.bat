@echo off
chcp 65001 >nul
REM 实时故障诊断测试：模拟试验台边测边写数据文件，检查实时显示、自动诊断与诊断结论。
REM 先启动系统（安装版开机自动运行；开发时运行 python -m pump_test_bench.app.services.supervisor）。
REM 用法：双击（快速测试）；或在命令行加参数，如  测试实时诊断.bat --cases all  /  --source D:\我的数据  /  --speed 1
cd /d "%~dp0"
set "PY="
if exist "%ProgramFiles%\BenchCheck\python\python.exe" set "PY=%ProgramFiles%\BenchCheck\python\python.exe"
if not defined PY if exist "%~dp0deploy\windows\build\stage\python\python.exe" set "PY=%~dp0deploy\windows\build\stage\python\python.exe"
if not defined PY set "PY=python"
echo 使用 Python：%PY%
"%PY%" -m pump_test_bench.tools.live_diagnosis_test --healthy "%~dp0标准台性能录取数据\标准台性能录取数据" %*
echo.
pause
