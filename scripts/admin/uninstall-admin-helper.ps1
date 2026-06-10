param(
  [string]$ServiceName = "SNNUAdminHelper"
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
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
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

if (-not (Test-IsAdmin)) { throw "Administrator privileges required." }

$bundleRoot = Resolve-BundleRoot
$appRoot = Resolve-AppRoot
$configPath = Join-Path $appRoot "config\snnu-config.json"
$serviceScript = Join-Path $bundleRoot "scripts\admin\admin_helper.py"
$serviceExe = Join-Path $appRoot "SNNUAdminHelperService.exe"

if (Test-Path -Path $serviceExe) {
  $serviceLauncher = $serviceExe
  $serviceScriptArg = ""
} else {
  if (!(Test-Path -Path $serviceScript)) { throw "Admin helper wrapper not found: $serviceScript" }
  $py = Resolve-Python -RepoRoot $appRoot -ConfigPath $configPath
  $serviceLauncher = $py
  $serviceScriptArg = $serviceScript
}

function Invoke-AdminWrapper {
  param([string]$Verb)
  if ($serviceScriptArg) {
    & $serviceLauncher $serviceScriptArg $Verb
  } else {
    & $serviceLauncher $Verb
  }
}

$exists = (& sc.exe query $ServiceName 2>$null) -match "SERVICE_NAME"
if (-not $exists) {
  Write-Host "Service not found: $ServiceName"
  exit 0
}

try { Invoke-AdminWrapper "stop" | Out-Null } catch { }
try { Invoke-AdminWrapper "remove" | Out-Null } catch { }

Write-Host "Admin helper removed: $ServiceName"
