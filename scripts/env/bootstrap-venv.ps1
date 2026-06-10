param(
  [string]$PythonPath = "",
  [string]$PipIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

function Invoke-Checked {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
  }
}

function Get-PythonMinor {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path) -or !(Test-Path -Path $Path)) { return "" }
  try {
    return ((& $Path -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") | Select-Object -First 1).Trim()
  } catch {
    return ""
  }
}

function Add-Candidate {
  param([System.Collections.ArrayList]$Candidates, [string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) { return }
  if ((Test-Path -Path $Path) -and -not $Candidates.Contains($Path)) {
    [void]$Candidates.Add($Path)
  }
}

function Resolve-BasePython {
  param([string]$PreferredPath)
  $wanted = @("3.12", "3.10")
  $candidates = [System.Collections.ArrayList]::new()

  Add-Candidate -Candidates $candidates -Path $PreferredPath
  Add-Candidate -Candidates $candidates -Path $env:SNNU_BOOTSTRAP_PYTHON

  $conda = Get-Command conda -ErrorAction SilentlyContinue
  if ($conda) {
    try {
      $envInfo = (& $conda.Source env list --json) | ConvertFrom-Json
      foreach ($envPath in $envInfo.envs) {
        Add-Candidate -Candidates $candidates -Path (Join-Path $envPath "python.exe")
      }
    } catch { }
  }

  $cmdObj = (Get-Command python -ErrorAction SilentlyContinue)
  if ($cmdObj) { Add-Candidate -Candidates $candidates -Path $cmdObj.Source }

  foreach ($target in $wanted) {
    foreach ($candidate in $candidates) {
      if ((Get-PythonMinor -Path $candidate) -eq $target) {
        return $candidate
      }
    }
  }

  $seen = ($candidates | ForEach-Object { "$_ [$((Get-PythonMinor -Path $_))]" }) -join "; "
  throw "Python 3.12 or 3.10 is required for this project. Checked: $seen"
}

function Ensure-Config {
  param([string]$RepoRoot)
  $configPath = Join-Path $RepoRoot "config\snnu-config.json"
  if (!(Test-Path -Path $configPath)) {
    $example = Join-Path $RepoRoot "config\snnu-config.example.json"
    if (!(Test-Path -Path $example)) { throw "Config template not found: $example" }
    Copy-Item -Path $example -Destination $configPath
  }
  return $configPath
}

$repoRoot = Resolve-RepoRoot
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $repoRoot "requirements.txt"
$configPath = Ensure-Config -RepoRoot $repoRoot

if ($Force -and (Test-Path -Path $venvDir)) {
  Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (!(Test-Path -Path $venvPython)) {
  $basePython = Resolve-BasePython -PreferredPath $PythonPath
  Write-Host "Creating .venv with $basePython"
  Invoke-Checked -FilePath $basePython -Arguments @("-m", "venv", $venvDir)
}

if (!(Test-Path -Path $venvPython)) {
  throw "Failed to create virtual environment: $venvDir"
}

Write-Host "Installing dependencies..."
Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
$pipArgs = @("-m", "pip", "install", "-r", $requirements)
if (![string]::IsNullOrWhiteSpace($PipIndexUrl)) {
  $pipArgs += @("-i", $PipIndexUrl)
}
Invoke-Checked -FilePath $venvPython -Arguments $pipArgs

$cfg = (Get-Content -Path $configPath -Raw) | ConvertFrom-Json
$cfg.pythonPath = $venvPython
$cfg | ConvertTo-Json -Depth 12 | Set-Content -Path $configPath -Encoding UTF8

Write-Host "Ready: $venvPython"
