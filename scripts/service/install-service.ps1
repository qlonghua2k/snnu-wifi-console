param(
  [string]$ServiceName = "SNNUWifiKeepalive",
  [switch]$RunNow,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-BundleRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

function Resolve-AppRoot {
  $bundleRoot = Resolve-BundleRoot
  if ((Split-Path -Leaf $bundleRoot) -eq "_internal") {
    return (Split-Path -Parent $bundleRoot)
  }
  return $bundleRoot
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

function Resolve-Python {
  param([string]$RepoRoot, [string]$ConfigPath)
  $candidates = @()
  $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
  $candidates += $venvPython
  if (Test-Path -Path $ConfigPath) {
    try {
      $cfg = (Get-Content -Path $ConfigPath -Raw) | ConvertFrom-Json
      if ($cfg.pythonPath) { $candidates += $cfg.pythonPath }
    } catch { }
  }
  $cmdObj = Get-Command python -ErrorAction SilentlyContinue
  if ($cmdObj) { $candidates += $cmdObj.Source }
  $cmdObj = Get-Command py -ErrorAction SilentlyContinue
  if ($cmdObj) { $candidates += $cmdObj.Source }
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -Path $candidate)) { return $candidate }
  }
  throw "Python not found. Run scripts\env\bootstrap-venv.ps1 or set pythonPath in config."
}

$bundleRoot = Resolve-BundleRoot
$appRoot = Resolve-AppRoot
$configPath = Join-Path $appRoot "config\snnu-config.json"
$serviceScript = Join-Path $bundleRoot "scripts\service\snnu_service.py"
$serviceExe = Join-Path $appRoot "SNNUWifiKeepaliveService.exe"

if (!(Test-Path -Path $serviceExe) -and !(Test-Path -Path $serviceScript)) {
  throw "Service wrapper not found: $serviceExe or $serviceScript"
}
if (-not (Test-IsAdmin)) { throw "Administrator privileges required." }

if (Test-Path -Path $serviceExe) {
  $serviceLauncher = $serviceExe
  $serviceScriptArg = ""
} else {
  $py = Resolve-Python -RepoRoot $appRoot -ConfigPath $configPath
  Ensure-PyWin32 -Py $py
  $serviceLauncher = $py
  $serviceScriptArg = $serviceScript
}

function Invoke-ServiceWrapper {
  param([string]$Verb)
  if ($serviceScriptArg) {
    & $serviceLauncher $serviceScriptArg $Verb
  } else {
    & $serviceLauncher $Verb
  }
}

$exists = (& sc.exe query $ServiceName 2>$null) -match "SERVICE_NAME"
if ($exists) {
  if (-not $Force) { throw "Service already exists: $ServiceName. Use -Force to recreate." }
  try { Invoke-ServiceWrapper "stop" | Out-Null } catch { }
  try { Invoke-ServiceWrapper "remove" | Out-Null } catch { }
  Start-Sleep -Seconds 2
}

$installOutput = Invoke-ServiceWrapper "install"
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
  Invoke-ServiceWrapper "start" | Out-Null
}

Write-Host "Service installed: $ServiceName"
