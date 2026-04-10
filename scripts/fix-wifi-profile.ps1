param(
  [string]$Profile = "SNNU"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$temp = Join-Path $repoRoot "logs\profile"
if (!(Test-Path -Path $temp)) { New-Item -ItemType Directory -Force -Path $temp | Out-Null }

Write-Host "Exporting profile..."
netsh wlan export profile name="$Profile" folder="$temp" key=clear | Out-Null

$xml = Get-ChildItem -Path $temp -Filter "*.xml" | Select-Object -First 1
if (-not $xml) { throw "Profile export failed. Connect to Wi-Fi once and retry." }

Write-Host "Importing as all-user profile..."
netsh wlan add profile filename="$($xml.FullName)" user=all | Out-Null
netsh wlan set profileparameter name="$Profile" connectionmode=auto | Out-Null

Write-Host "Done. Auto-connect enabled for all users."
