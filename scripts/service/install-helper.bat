@echo off
setlocal
cd /d %~dp0..\..

net session >nul 2>nul
if %errorlevel% neq 0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\admin\install-admin-helper.ps1" -RunNow
pause
