param(
  [string]$PipIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple",
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

$repoRoot = Resolve-RepoRoot
$packagingDir = Join-Path $repoRoot "packaging"
$artifactsDir = Join-Path $repoRoot "artifacts"
$dist = Join-Path $artifactsDir "dist"
$build = Join-Path $artifactsDir "build"

$bootstrap = Join-Path $repoRoot "scripts\env\bootstrap-venv.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap

$py = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pipArgs = @("-m", "pip", "install", "-r", (Join-Path $packagingDir "requirements-build.txt"))
if (![string]::IsNullOrWhiteSpace($PipIndexUrl)) {
  $pipArgs += @("-i", $PipIndexUrl)
}
& $py @pipArgs
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install build dependencies."
}

if ($Clean) {
  if (Test-Path -Path $dist) { Remove-Item -LiteralPath $dist -Recurse -Force }
  if (Test-Path -Path $build) { Remove-Item -LiteralPath $build -Recurse -Force }
}

New-Item -ItemType Directory -Force -Path $packagingDir, $artifactsDir | Out-Null

Get-ChildItem -Path (Join-Path $repoRoot "desktop"), (Join-Path $repoRoot "scripts") -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force

& $py -m PyInstaller `
  --noconfirm `
  --distpath "$dist" `
  --workpath "$build" `
  "$packagingDir\SNNU WiFi Console.spec"

$appDir = Join-Path $dist "SNNU WiFi Console"

& $py -m PyInstaller `
  --noconfirm `
  --onefile `
  --name "SNNUWifiKeepaliveService" `
  --distpath "$appDir" `
  --workpath (Join-Path $build "service") `
  --specpath "$build" `
  --hidden-import "win32timezone" `
  (Join-Path $repoRoot "scripts\service\snnu_service.py")
if ($LASTEXITCODE -ne 0) {
  throw "Failed to build keepalive service wrapper."
}

& $py -m PyInstaller `
  --noconfirm `
  --onefile `
  --name "SNNUAdminHelperService" `
  --distpath "$appDir" `
  --workpath (Join-Path $build "admin-helper") `
  --specpath "$build" `
  --hidden-import "win32timezone" `
  --add-data "$repoRoot\scripts;scripts" `
  (Join-Path $repoRoot "scripts\admin\admin_helper.py")
if ($LASTEXITCODE -ne 0) {
  throw "Failed to build admin helper wrapper."
}

Get-ChildItem -Path (Join-Path $repoRoot "desktop"), (Join-Path $repoRoot "scripts") -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force

$exe = Join-Path $appDir "SNNU WiFi Console.exe"
if (!(Test-Path -Path $exe)) { throw "Build output not found: $exe" }
$serviceExe = Join-Path $appDir "SNNUWifiKeepaliveService.exe"
if (!(Test-Path -Path $serviceExe)) { throw "Build output not found: $serviceExe" }
$adminHelperExe = Join-Path $appDir "SNNUAdminHelperService.exe"
if (!(Test-Path -Path $adminHelperExe)) { throw "Build output not found: $adminHelperExe" }

$shortcutName = "SNNU Wi-Fi " + [string]([char]0x63A7) + [string]([char]0x5236) + [string]([char]0x53F0) + ".lnk"
$shortcut = Join-Path $repoRoot $shortcutName
$shortcutTemp = Join-Path $repoRoot "SNNU-WiFi-Console.lnk"
if (Test-Path -Path $shortcutTemp) { Remove-Item -LiteralPath $shortcutTemp -Force }
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutTemp)
$link.TargetPath = $exe
$link.WorkingDirectory = Split-Path -Parent $exe
$link.IconLocation = "$exe,0"
$link.Save()
Move-Item -LiteralPath $shortcutTemp -Destination $shortcut -Force

Write-Host "Built: $exe"
Write-Host "Service wrapper: $serviceExe"
Write-Host "Admin helper wrapper: $adminHelperExe"
Write-Host "Shortcut: $shortcut"
