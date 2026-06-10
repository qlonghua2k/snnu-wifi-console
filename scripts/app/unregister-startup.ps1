param(
  [string]$Name = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Name)) {
  $Name = "SNNU Wi-Fi " + [string]([char]0x63A7) + [string]([char]0x5236) + [string]([char]0x53F0)
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $runKey -Name $Name -ErrorAction SilentlyContinue) {
  Remove-ItemProperty -Path $runKey -Name $Name -ErrorAction Stop
  Write-Host "Startup unregistered: $Name"
} else {
  Write-Host "Startup entry not found: $Name"
}
