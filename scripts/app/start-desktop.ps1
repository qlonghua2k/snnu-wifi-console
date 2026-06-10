param(
  [switch]$NoBootstrap,
  [switch]$RestartExisting,
  [switch]$Minimized
)

$ErrorActionPreference = "Stop"

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

$repoRoot = Resolve-RepoRoot

if (!(Test-Admin)) {
  $argsList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
  if ($NoBootstrap) { $argsList += "-NoBootstrap" }
  if ($RestartExisting) { $argsList += "-RestartExisting" }
  if ($Minimized) { $argsList += "-Minimized" }
  Start-Process -Verb RunAs -FilePath "powershell.exe" -ArgumentList ($argsList -join " ") -WorkingDirectory $repoRoot | Out-Null
  exit 0
}

$bootstrap = Join-Path $repoRoot "scripts\env\bootstrap-venv.ps1"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!$NoBootstrap -and (!(Test-Path -Path $venvPython))) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap
}

if (!(Test-Path -Path $venvPython)) {
  throw "Project Python not found. Run scripts\env\bootstrap-venv.ps1 first."
}

$py = $venvPython
$pyw = $py -replace "python.exe$", "pythonw.exe"
if (Test-Path -Path $pyw) { $py = $pyw }

$app = Join-Path $repoRoot "desktop\app.py"
$appArgs = @("`"$app`"")
if ($Minimized) { $appArgs += "--minimized" }

if ($RestartExisting) {
  $escapedApp = [regex]::Escape($app)
  Get-CimInstance Win32_Process |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $escapedApp } |
    ForEach-Object {
      try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch { }
    }
}

Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList ($appArgs -join " ") -WorkingDirectory $repoRoot | Out-Null
