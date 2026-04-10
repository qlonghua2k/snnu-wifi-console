@echo off
setlocal
cd /d %~dp0

net session >nul 2>nul
if %errorlevel% neq 0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~dp0uninstall-helper.bat' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\uninstall-admin-helper.ps1"
pause
