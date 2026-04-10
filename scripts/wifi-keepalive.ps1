param(
  [string]$ConfigPath = "",
  [switch]$Once,
  [switch]$Status
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent $scriptDir)
}

function Resolve-ConfigPath {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return (Join-Path (Resolve-RepoRoot) "config\snnu-config.json")
  }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path (Resolve-RepoRoot) $Path)
}

function Resolve-Python {
  param([string]$ConfigPath)
  if (Test-Path -Path $ConfigPath) {
    try {
      $cfg = (Get-Content -Path $ConfigPath -Raw) | ConvertFrom-Json
      if ($cfg.pythonPath -and (Test-Path -Path $cfg.pythonPath)) { return $cfg.pythonPath }
    } catch { }
  }
  $cmdObj = (Get-Command python -ErrorAction SilentlyContinue)
  if ($cmdObj) { return $cmdObj.Source }
  $cmdObj = (Get-Command py -ErrorAction SilentlyContinue)
  if ($cmdObj) { return $cmdObj.Source }
  throw "Python not found. Set pythonPath in config or add Python to PATH."
}

$repoRoot = Resolve-RepoRoot
$resolvedConfig = Resolve-ConfigPath -Path $ConfigPath
$keepalive = Join-Path $repoRoot "web\keepalive.py"
if (!(Test-Path -Path $keepalive)) { throw "Python keepalive script not found: $keepalive" }

$py = Resolve-Python -ConfigPath $resolvedConfig
$argsList = @($keepalive, "--config", $resolvedConfig)
if ($Once) { $argsList += "--once" }
if ($Status) { $argsList += "--status" }

& $py @argsList
exit $LASTEXITCODE
