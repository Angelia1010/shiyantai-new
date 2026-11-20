@echo off
REM Rebuild the installer after code changes: deploy\windows\output\BenchCheck-Setup-<version>.exe
REM Close the frontend dev server (npm run dev) before packaging.
REM This file is ASCII only on purpose: cmd.exe misreads batch files containing Chinese text on some PCs.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\windows\pack.ps1" %*
echo.
pause
