@echo off
REM Live diagnosis test: writes normal + fault-injected data files row by row, like the test bench does.
REM Usage: double-click (2 normal + 7 typical faults), or add arguments, e.g.
REM   --cases all   /   --source D:\data   /   --speed 4   /   --to D:\live   /   --no-wait
REM This file is ASCII only on purpose: cmd.exe misreads batch files containing Chinese text on some PCs.
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
if exist "%ProgramFiles%\BenchCheck\python\python.exe" set "PY=%ProgramFiles%\BenchCheck\python\python.exe"
if not defined PY if exist "%~dp0deploy\windows\build\stage\python\python.exe" set "PY=%~dp0deploy\windows\build\stage\python\python.exe"
if not defined PY set "PY=python"
REM Always run the scripts from this repository (the installed Python only provides the runtime)
"%PY%" -c "import sys, runpy; sys.path.insert(0, r'%~dp0.'); runpy.run_module('pump_test_bench.tools.simulate_live_data', run_name='__main__', alter_sys=True)" %*
echo.
pause
