param(
  [switch]$Enable,
  [switch]$Disable,
  [switch]$Status
)

$ErrorActionPreference = "Stop"

if (($Enable.ToBool() + $Disable.ToBool() + $Status.ToBool()) -ne 1) {
  throw "Specify exactly one of -Enable, -Disable, or -Status."
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]
[void][Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
[void][Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]

function Await-WinRt {
  param(
    [object]$Operation,
    [type]$ResultType
  )
  $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
      $_.Name -eq "AsTask" -and
      $_.IsGenericMethodDefinition -and
      $_.GetParameters().Count -eq 1
    } |
    Select-Object -First 1
  if (-not $method) { throw "Unable to locate WinRT AsTask helper." }
  $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
  $task.Wait()
  return $task.Result
}

$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if (-not $profile) { throw "No internet connection profile is available for Mobile Hotspot." }

$manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
if (-not $manager) { throw "Unable to create Mobile Hotspot manager." }

if ($Status) {
  Write-Host "Hotspot state: $($manager.TetheringOperationalState)"
  exit 0
}

if ($Enable) {
  $result = Await-WinRt -Operation $manager.StartTetheringAsync() -ResultType ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
} else {
  $result = Await-WinRt -Operation $manager.StopTetheringAsync() -ResultType ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
}

if ($result.Status -ne "Success") {
  throw "Mobile Hotspot operation failed: $($result.Status)"
}

Write-Host "Mobile Hotspot operation completed: $($result.Status)"
