param(
  [string]$TaskName = "SNNU WiFi Keepalive",
  [string]$ConfigPath = "",
  [switch]$RunNow,
  [switch]$Highest
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

$repoRoot = Resolve-RepoRoot
$scriptPath = Join-Path $repoRoot "scripts\network\wifi-keepalive.ps1"
$resolvedConfigPath = Resolve-ConfigPath -Path $ConfigPath

if (!(Test-Path -Path $scriptPath)) { throw "Script not found: $scriptPath" }
if (!(Test-Path -Path $resolvedConfigPath)) { throw "Config not found: $resolvedConfigPath" }

$taskCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -ConfigPath `"$resolvedConfigPath`""

Write-Host "Creating scheduled task: $TaskName"

$schtasksArgs = @(
  "/Create",
  "/F",
  "/SC", "ONLOGON",
  "/TN", $TaskName,
  "/TR", $taskCmd,
  "/RL", "HIGHEST",
  "/RU", $env:USERNAME,
  "/IT"
)

$null = & schtasks.exe @schtasksArgs

if ($RunNow) {
  & schtasks.exe /Run /TN $TaskName | Out-Null
  Write-Host "Task started."
}

Write-Host "Done."
