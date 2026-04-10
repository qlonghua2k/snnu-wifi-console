param(
  [string]$ServiceName = "SNNUAdminHelper"
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
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) { throw "Administrator privileges required." }

$repoRoot = Resolve-RepoRoot
$configPath = Join-Path $repoRoot "config\snnu-config.json"
$serviceScript = Join-Path $repoRoot "scripts\admin_helper.py"

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

$exists = (& sc.exe query $ServiceName 2>$null) -match "SERVICE_NAME"
if (-not $exists) {
  Write-Host "Service not found: $ServiceName"
  exit 0
}

try { & $py $serviceScript stop | Out-Null } catch { }
try { & $py $serviceScript remove | Out-Null } catch { }

Write-Host "Admin helper removed: $ServiceName"
