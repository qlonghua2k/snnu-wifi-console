param(
  [string]$Profile = "SNNU"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$profileLogRoot = Join-Path $repoRoot "logs\profile"
if (!(Test-Path -Path $profileLogRoot)) { New-Item -ItemType Directory -Force -Path $profileLogRoot | Out-Null }

$temp = Join-Path $profileLogRoot ([guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $temp | Out-Null

try {
  Write-Host "Exporting profile..."
  netsh wlan export profile name="$Profile" folder="$temp" key=clear | Out-Null

  $xmlFiles = @(Get-ChildItem -Path $temp -Filter "*.xml" -File)
  if ($xmlFiles.Count -ne 1) {
    throw "Profile export failed or produced unexpected files. Connect to Wi-Fi once and retry."
  }

  $xml = $xmlFiles[0]
  [xml]$profileXml = Get-Content -LiteralPath $xml.FullName -Encoding UTF8
  $exportedName = [string]$profileXml.WLANProfile.name
  if ($exportedName -ne $Profile) {
    throw "Exported profile '$exportedName' does not match requested profile '$Profile'."
  }

  Write-Host "Importing as all-user profile..."
  netsh wlan add profile filename="$($xml.FullName)" user=all | Out-Null
  netsh wlan set profileparameter name="$Profile" connectionmode=auto | Out-Null

  Write-Host "Done. Auto-connect enabled for all users."
}
finally {
  if (Test-Path -LiteralPath $temp) {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
  }
}
