@echo off
chcp 65001 >nul
REM 查看服务是否在运行
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0installer_tools.py" status
echo.
pause
