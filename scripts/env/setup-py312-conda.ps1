param(
  [string]$EnvName = "snnu-wifi-py312",
  [string]$Channel = "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge",
  [string]$Proxy = "http://127.0.0.1:7897",
  [switch]$Bootstrap
)

$ErrorActionPreference = "Stop"

if (![string]::IsNullOrWhiteSpace($Proxy)) {
  $env:HTTP_PROXY = $Proxy
  $env:HTTPS_PROXY = $Proxy
}

$conda = Get-Command conda -ErrorAction SilentlyContinue
if (!$conda) {
  throw "Conda not found."
}

$envJson = (& $conda.Source env list --json) | ConvertFrom-Json
$existing = $envJson.envs | Where-Object { (Split-Path -Leaf $_) -eq $EnvName } | Select-Object -First 1

if (!$existing) {
  & $conda.Source create -y -n $EnvName --override-channels -c $Channel python=3.12
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create conda env: $EnvName"
  }
  $envJson = (& $conda.Source env list --json) | ConvertFrom-Json
  $existing = $envJson.envs | Where-Object { (Split-Path -Leaf $_) -eq $EnvName } | Select-Object -First 1
}

if (!$existing) {
  throw "Conda env not found after create: $EnvName"
}

$python = Join-Path $existing "python.exe"
if (!(Test-Path -Path $python)) {
  throw "Python not found in conda env: $python"
}

& $python --version
Write-Host "Conda Python: $python"

if ($Bootstrap) {
  $repoRoot = Split-Path -Parent $PSScriptRoot
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "bootstrap-venv.ps1") -Force -PythonPath $python
}
