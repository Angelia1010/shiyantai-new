@echo off
chcp 65001 >nul
REM 改完代码后双击本文件，重新生成安装包（deploy\windows\output\BenchCheck-Setup-版本号.exe）
REM 打包前请关闭正在运行的前端开发服务（npm run dev 的窗口）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\windows\pack.ps1" %*
echo.
pause
