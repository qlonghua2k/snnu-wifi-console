param(
  [string]$Name = "",
  [string]$ExecutablePath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

function Quote-Arg {
  param([string]$Value)
  return '"' + ($Value -replace '"', '\"') + '"'
}

$repoRoot = Resolve-RepoRoot
if ([string]::IsNullOrWhiteSpace($Name)) {
  $Name = "SNNU Wi-Fi " + [string]([char]0x63A7) + [string]([char]0x5236) + [string]([char]0x53F0)
}

if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
  $distExe = Join-Path $repoRoot "artifacts\dist\SNNU WiFi Console\SNNU WiFi Console.exe"
  if (Test-Path -Path $distExe) {
    $ExecutablePath = $distExe
  }
}

if (![string]::IsNullOrWhiteSpace($ExecutablePath) -and (Test-Path -Path $ExecutablePath)) {
  $command = "$(Quote-Arg $ExecutablePath) --minimized"
} else {
  $startScript = Join-Path $repoRoot "scripts\app\start-desktop.ps1"
  if (!(Test-Path -Path $startScript)) { throw "Startup target not found." }
  $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $(Quote-Arg $startScript) -NoBootstrap -Minimized"
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (!(Test-Path -Path $runKey)) {
  New-Item -Path $runKey -Force | Out-Null
}
Set-ItemProperty -Path $runKey -Name $Name -Value $command -Type String
Write-Host "Startup registered: $Name"
