@echo off
setlocal
cd /d %~dp0

for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Get-Content -Raw .\config\snnu-config.json | ConvertFrom-Json).pythonPath } catch { '' }"`) do set "PY=%%A"

if not defined PY (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
      set "PY=py"
    ) else (
      powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework;[System.Windows.MessageBox]::Show('Python not found. Install Python and add to PATH.','SNNU')" >nul 2>nul
      exit /b 1
    )
  )
)

set "PIP_PY=%PY%"
echo %PIP_PY% | findstr /i "pythonw.exe" >nul
if %errorlevel%==0 (
  set "PIP_PY=%PIP_PY:pythonw.exe=python.exe%"
)

%PIP_PY% -c "import flask,requests,bs4" >nul 2>nul
if %errorlevel% neq 0 (
  %PIP_PY% -m pip install -r .\requirements.txt
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0scripts\\start-web.ps1'" >nul 2>nul

exit /b 0
