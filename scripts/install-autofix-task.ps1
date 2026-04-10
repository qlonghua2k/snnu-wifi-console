param(
  [string]$TaskName = "SNNU Wifi AutoFix"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\auto-fix.ps1"
if (!(Test-Path -Path $scriptPath)) { throw "Script not found: $scriptPath" }

$taskCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$schtasksArgs = @(
  "/Create",
  "/F",
  "/SC", "ONSTART",
  "/TN", $TaskName,
  "/TR", $taskCmd,
  "/RL", "HIGHEST",
  "/RU", "SYSTEM"
)

& schtasks.exe @schtasksArgs | Out-Null
Write-Host "Auto-fix task installed: $TaskName"
