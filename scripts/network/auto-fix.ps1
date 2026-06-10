param(
  [string]$Profile = "",
  [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

function Resolve-ConfigPath {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return (Join-Path (Resolve-RepoRoot) "config\snnu-config.json")
  }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path (Resolve-RepoRoot) $Path)
}

function Load-Config {
  param([string]$Path)
  $raw = Get-Content -Path $Path -Raw
  return ($raw | ConvertFrom-Json)
}

function Save-Config {
  param([object]$Config, [string]$Path)
  $json = $Config | ConvertTo-Json -Depth 8
  $json | Set-Content -Path $Path -Encoding UTF8
}

function Resolve-ProjectPython {
  param([string]$RepoRoot, [object]$Config)
  $candidates = @()
  $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
  $candidates += $venvPython
  if ($Config.pythonPath) { $candidates += $Config.pythonPath }
  $cmdObj = Get-Command python -ErrorAction SilentlyContinue
  if ($cmdObj) { $candidates += $cmdObj.Source }
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -Path $candidate)) { return $candidate }
  }
  return ""
}

$repoRoot = Resolve-RepoRoot
$cfgPath = Resolve-ConfigPath -Path $ConfigPath
$config = Load-Config -Path $cfgPath

$targetProfile = $Profile
if ([string]::IsNullOrWhiteSpace($targetProfile)) {
  $targetProfile = if ($config.profileName) { $config.profileName } else { $config.ssid }
}

$py = Resolve-ProjectPython -RepoRoot $repoRoot -Config $config
if ($py -and ((-not $config.pythonPath) -or !(Test-Path -Path $config.pythonPath))) {
  $config.pythonPath = $py
  Save-Config -Config $config -Path $cfgPath
}

$profiles = @()
$output = netsh wlan show profiles
foreach ($line in $output) {
  if ($line -match "(All User Profile|所有用户配置文件)\s*:\s*(.+)$") {
    $profiles += $Matches[2].Trim()
  }
}

$repoRoot = Resolve-RepoRoot
$fixScript = Join-Path $repoRoot "scripts\network\fix-wifi-profile.ps1"

if ($profiles -contains $targetProfile) {
  Write-Host "All-User profile OK: $targetProfile"
} else {
  Write-Host "All-User profile missing. Converting: $targetProfile"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $fixScript -Profile $targetProfile
}

Write-Host "Auto-fix completed."
