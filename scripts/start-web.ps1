param(
  [int]$Port = 8608
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent $scriptDir)
}

$repoRoot = Resolve-RepoRoot
$configPath = Join-Path $repoRoot "config\snnu-config.json"
$py = ""

$existing = & wmic process where "commandline like '%\\web\\app.py%'" get ProcessId /format:list
$already = $false
foreach ($line in $existing) {
  if ($line -match "ProcessId=(\d+)") { $already = $true; break }
}
if ($already) { exit 0 }

if (Test-Path -Path $configPath) {
  try {
    $cfg = (Get-Content -Path $configPath -Raw) | ConvertFrom-Json
    if ($cfg.pythonPath) { $py = $cfg.pythonPath }
  } catch { }
}

if ([string]::IsNullOrWhiteSpace($py) -or -not (Test-Path -Path $py)) {
  $cmdObj = (Get-Command python -ErrorAction SilentlyContinue)
  if ($cmdObj) { $py = $cmdObj.Source }
}

if ([string]::IsNullOrWhiteSpace($py) -or -not (Test-Path -Path $py)) {
  $cmdObj = (Get-Command py -ErrorAction SilentlyContinue)
  if ($cmdObj) { $py = $cmdObj.Source }
}

if ($py -match "python.exe$") {
  $pyw = $py -replace "python.exe$", "pythonw.exe"
  if (Test-Path -Path $pyw) { $py = $pyw }
}

if ([string]::IsNullOrWhiteSpace($py)) { throw "Python not found." }

$env:SNNU_WEB_PORT = $Port
Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList "`"$repoRoot\web\app.py`"" -WorkingDirectory $repoRoot | Out-Null
