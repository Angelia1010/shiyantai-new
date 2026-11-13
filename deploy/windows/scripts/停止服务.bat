@echo off
REM Stop the background services. Runs as administrator.
REM This file is ASCII only on purpose: cmd.exe misreads batch files containing Chinese text on some PCs.
chcp 65001 >nul
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0installer_tools.py" stop
echo.
pause
