param(
  [string]$ServiceName = "SNNUWifiKeepalive",
  [switch]$RunNow,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent $scriptDir)
}

function Test-IsAdmin {
  $current = [Security.Principal.WindowsIdentity]::GetCurrent()
  if ($current.Name -eq "NT AUTHORITY\SYSTEM") { return $true }
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-PyWin32 {
  param([string]$Py)
  & $Py -c "import win32serviceutil" 2>$null
  if ($LASTEXITCODE -eq 0) { return }
  Write-Host "pywin32 missing. Installing..."
  & $Py -m pip install pywin32
  & $Py -c "import win32serviceutil"
  if ($LASTEXITCODE -ne 0) { throw "pywin32 install failed." }
}

$repoRoot = Resolve-RepoRoot
$configPath = Join-Path $repoRoot "config\snnu-config.json"
$serviceScript = Join-Path $repoRoot "scripts\snnu_service.py"

if (!(Test-Path -Path $serviceScript)) { throw "Service script not found: $serviceScript" }
if (-not (Test-IsAdmin)) { throw "Administrator privileges required." }

$py = "C:\ProgramData\anaconda3\envs\snnu\python.exe"
if (Test-Path -Path $configPath) {
  try {
    $cfg = (Get-Content -Path $configPath -Raw) | ConvertFrom-Json
    if ($cfg.pythonPath) { $py = $cfg.pythonPath }
  } catch { }
}

if (!(Test-Path -Path $py)) {
  $cmdObj = (Get-Command python -ErrorAction SilentlyContinue)
  if ($cmdObj) { $py = $cmdObj.Source }
}

if (!(Test-Path -Path $py)) { throw "Python not found. Set pythonPath in config." }

Ensure-PyWin32 -Py $py

$exists = (& sc.exe query $ServiceName 2>$null) -match "SERVICE_NAME"
if ($exists) {
  if (-not $Force) { throw "Service already exists: $ServiceName. Use -Force to recreate." }
  try { & $py $serviceScript stop | Out-Null } catch { }
  try { & $py $serviceScript remove | Out-Null } catch { }
  Start-Sleep -Seconds 2
}

$installOutput = & $py $serviceScript install
if ($LASTEXITCODE -ne 0) {
  throw "Service install failed. $installOutput"
}

& sc.exe description $ServiceName "Keep SNNU Wi-Fi connected and auto-login to portal." | Out-Null
& sc.exe failure $ServiceName reset= 60 actions= restart/5000/restart/5000/restart/5000 | Out-Null
& sc.exe failureflag $ServiceName 1 | Out-Null
& sc.exe config $ServiceName start= delayed-auto | Out-Null
& sc.exe config $ServiceName depend= WlanSvc | Out-Null

Start-Sleep -Seconds 1
$verify = (& sc.exe query $ServiceName 2>$null) -match "SERVICE_NAME"
if (-not $verify) { throw "Service install failed. sc query did not find service." }

if ($RunNow) {
  & $py $serviceScript start | Out-Null
}

Write-Host "Service installed: $ServiceName"
