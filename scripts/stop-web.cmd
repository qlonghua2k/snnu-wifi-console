@echo off
setlocal

for /f "tokens=2 delims=," %%A in ('wmic process where "commandline like '%%\\web\\app.py%%'" get CommandLine^,ProcessId /format:csv ^| findstr /i "web\\app.py"') do (
  taskkill /PID %%A /F >nul 2>nul
)

exit /b 0
