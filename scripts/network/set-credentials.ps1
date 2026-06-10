param(
  [string]$ConfigPath = "",
  [string]$Username = ""
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
  if (!(Test-Path -Path $Path)) { throw "Config not found: $Path" }
  $raw = Get-Content -Path $Path -Raw
  return ($raw | ConvertFrom-Json)
}

function Save-Config {
  param([object]$Config, [string]$Path)
  $json = $Config | ConvertTo-Json -Depth 8
  $json | Set-Content -Path $Path -Encoding UTF8
}

$resolvedConfigPath = Resolve-ConfigPath -Path $ConfigPath
$config = Load-Config -Path $resolvedConfigPath

if (-not [string]::IsNullOrWhiteSpace($Username)) {
  $config.credentials.username = $Username
}

$password = Read-Host "Password (plaintext)"
$config.credentials.password = $password
if ($config.credentials.PSObject.Properties.Name -contains "protectedPassword") {
  $config.credentials.PSObject.Properties.Remove("protectedPassword")
}

Save-Config -Config $config -Path $resolvedConfigPath
Write-Host "Saved plaintext password to config."
