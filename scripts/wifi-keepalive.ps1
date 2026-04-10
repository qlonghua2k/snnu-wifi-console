param(
  [string]$ConfigPath = "",
  [switch]$Once,
  [switch]$Status
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

function Resolve-RepoRoot {
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $PSCommandPath }
  if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  if (-not $scriptDir) { return (Get-Location).Path }
  return (Split-Path -Parent $scriptDir)
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

function Ensure-ConfigDefaults {
  param($Config)
  if (-not $Config.intervalSeconds) { $Config.intervalSeconds = 60 }
  if (-not $Config.loginCooldownSeconds) { $Config.loginCooldownSeconds = 60 }
  if (-not $Config.loginMaxCooldownSeconds) { $Config.loginMaxCooldownSeconds = 600 }
  if (-not $Config.logRotateMB) { $Config.logRotateMB = 5 }
  if (-not $Config.logRotateKeep) { $Config.logRotateKeep = 3 }
  if (-not $Config.statePath) { $Config.statePath = "logs\\state.json" }
  if (-not $Config.triggerPath) { $Config.triggerPath = "logs\\trigger.once" }
  if (-not $Config.pythonPath) { $Config.pythonPath = "C:\\ProgramData\\anaconda3\\envs\\snnu\\python.exe" }
  return $Config
}

function Resolve-LogPath {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return (Join-Path (Resolve-RepoRoot) "logs\wifi-keepalive.log")
  }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path (Resolve-RepoRoot) $Path)
}

function Resolve-StatePath {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return (Join-Path (Resolve-RepoRoot) "logs\state.json")
  }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path (Resolve-RepoRoot) $Path)
}

function Resolve-TriggerPath {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return (Join-Path (Resolve-RepoRoot) "logs\trigger.once")
  }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path (Resolve-RepoRoot) $Path)
}

function Rotate-Log {
  param(
    [string]$Path,
    [int]$MaxBytes,
    [int]$Keep
  )
  if (!(Test-Path -Path $Path)) { return }
  $item = Get-Item -Path $Path -ErrorAction SilentlyContinue
  if ($null -eq $item) { return }
  if ($item.Length -lt $MaxBytes) { return }

  for ($i = $Keep - 1; $i -ge 1; $i--) {
    $src = "$Path.$i"
    $dst = "$Path." + ($i + 1)
    if (Test-Path -Path $src) {
      Move-Item -Force -Path $src -Destination $dst
    }
  }
  Move-Item -Force -Path $Path -Destination "$Path.1"
}

function Write-Log {
  param(
    [string]$Message,
    [string]$Level = "INFO"
  )
  $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  $line = "[$timestamp][$Level] $Message"
  Write-Host $line
  if ($script:LogPath) {
    $dir = Split-Path -Parent $script:LogPath
    if (!(Test-Path -Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    if ($script:LogRotateBytes -gt 0) {
      Rotate-Log -Path $script:LogPath -MaxBytes $script:LogRotateBytes -Keep $script:LogRotateKeep
    }
    Add-Content -Path $script:LogPath -Value $line
  }
}

function Test-Trigger {
  if (-not $script:TriggerPath) { return $false }
  if (Test-Path -Path $script:TriggerPath) {
    try { Remove-Item -Force -Path $script:TriggerPath | Out-Null } catch { }
    return $true
  }
  return $false
}

function Sleep-WithTrigger {
  param([int]$Seconds)
  if ($Seconds -le 0) { return $false }
  for ($i = 0; $i -lt $Seconds; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Trigger) { return $true }
  }
  return $false
}

function New-DefaultState {
  param($Config)
  return [pscustomobject]@{
    lastState = "INIT"
    lastError = ""
    lastLoginAttempt = ""
    lastLoginSuccess = ""
    lastOnline = ""
    currentCooldownSeconds = [int]$Config.loginCooldownSeconds
    nextLoginAfter = ""
    lastAdapter = ""
    lastSsid = ""
    lastIp = ""
    lastGateway = ""
    lastPortal = ""
    lastConnectivityOk = $false
  }
}

function Load-State {
  param([string]$Path, $Config)
  if (!(Test-Path -Path $Path)) { return (New-DefaultState -Config $Config) }
  try {
    $raw = Get-Content -Path $Path -Raw
    $state = $raw | ConvertFrom-Json
  } catch {
    return (New-DefaultState -Config $Config)
  }
  if ($null -eq $state) { return (New-DefaultState -Config $Config) }
  if (-not $state.currentCooldownSeconds) { $state.currentCooldownSeconds = [int]$Config.loginCooldownSeconds }
  return $state
}

function Save-State {
  param([object]$State, [string]$Path)
  $dir = Split-Path -Parent $Path
  if (!(Test-Path -Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $json = $State | ConvertTo-Json -Depth 8
  $json | Set-Content -Path $Path -Encoding UTF8
}

function Acquire-Mutex {
  param([string]$Name)
  $created = $false
  $mutex = New-Object System.Threading.Mutex($true, $Name, [ref]$created)
  if (-not $created) {
    $mutex.Dispose()
    return $null
  }
  return $mutex
}

function Test-IsAdmin {
  $current = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WifiAdapter {
  param([string]$PreferredName)
  if (![string]::IsNullOrWhiteSpace($PreferredName)) {
    $adapter = Get-NetAdapter -Name $PreferredName -ErrorAction SilentlyContinue
    if ($adapter) { return $adapter }
  }
  $adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue
  if ($adapters) {
    $wifi = $adapters | Where-Object {
      $_.NdisPhysicalMedium -eq "Native 802.11" -or
      $_.InterfaceDescription -match "Wireless|Wi-Fi|WLAN"
    } | Select-Object -First 1
    if ($wifi) { return $wifi }
  }
  return $null
}

function Get-AdapterList {
  $adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue
  if (-not $adapters) { return @() }
  return $adapters | ForEach-Object {
    [pscustomobject]@{
      Name = $_.Name
      Status = $_.Status
      Description = $_.InterfaceDescription
      IsWireless = ($_.NdisPhysicalMedium -eq "Native 802.11" -or $_.InterfaceDescription -match "Wireless|Wi-Fi|WLAN")
    }
  }
}

function Ensure-AdapterEnabled {
  param($Adapter)
  if ($null -eq $Adapter) { return $false }
  if ($Adapter.Status -eq "Disabled") {
    Write-Log "Adapter $($Adapter.Name) is disabled. Enabling..." "WARN"
    try {
      Enable-NetAdapter -Name $Adapter.Name -Confirm:$false -ErrorAction Stop | Out-Null
      Start-Sleep -Seconds 3
      return $true
    } catch {
      Write-Log "Failed to enable adapter. Admin permission may be required." "ERROR"
      return $false
    }
  }
  return $true
}

function Ensure-Autoconfig {
  param([string]$InterfaceName)
  if ([string]::IsNullOrWhiteSpace($InterfaceName)) { return }
  try {
    netsh wlan set autoconfig enabled=yes interface="$InterfaceName" | Out-Null
  } catch { }
}

function Get-WlanState {
  param([string]$InterfaceName)
  $output = netsh wlan show interfaces
  if (!$output) { return $null }

  $state = ""
  $ssid = ""
  $profile = ""
  $radioSoftwareOff = $false
  foreach ($line in $output) {
    if ($line -match "^\s*(State|状态)\s*:\s*(.+)$") { $state = $Matches[2].Trim() }
    if ($line -match "^\s*SSID\s*:\s*(.+)$") { $ssid = $Matches[1].Trim() }
    if ($line -match "^\s*(Profile|配置文件)\s*:\s*(.+)$") { $profile = $Matches[2].Trim() }
    if ($line -match "Software\s+Off|软件\s*关闭|无线\s*电源\s*已关闭") { $radioSoftwareOff = $true }
  }
  return [pscustomobject]@{
    State = $state
    Ssid = $ssid
    Profile = $profile
    RadioSoftwareOff = $radioSoftwareOff
  }
}

function Get-WlanProfiles {
  $profiles = @()
  $output = netsh wlan show profiles
  foreach ($line in $output) {
    if ($line -match "(All User Profile|所有用户配置文件)\s*:\s*(.+)$") {
      $profiles += $Matches[2].Trim()
    }
  }
  return $profiles
}

function Test-AllUserProfile {
  param([string]$Profile)
  if ([string]::IsNullOrWhiteSpace($Profile)) { return $false }
  $profiles = Get-WlanProfiles
  return ($profiles -contains $Profile)
}

function Connect-ToSsid {
  param(
    [string]$Ssid,
    [string]$ProfileName,
    [string]$InterfaceName
  )
  if ([string]::IsNullOrWhiteSpace($Ssid)) { return $false }

  $nameToUse = $ProfileName
  if ([string]::IsNullOrWhiteSpace($nameToUse)) { $nameToUse = $Ssid }

  $profiles = Get-WlanProfiles
  if (-not ($profiles -contains $nameToUse)) {
    Write-Log "Wi-Fi profile not found: $nameToUse. Connect once manually to create it." "WARN"
    return $false
  }

  Write-Log "Connecting to SSID $Ssid (profile $nameToUse)..." "INFO"
  try {
    if ([string]::IsNullOrWhiteSpace($InterfaceName)) {
      netsh wlan connect name="$nameToUse" ssid="$Ssid" | Out-Null
    } else {
      netsh wlan connect name="$nameToUse" ssid="$Ssid" interface="$InterfaceName" | Out-Null
    }
    Start-Sleep -Seconds 5
    return $true
  } catch {
    Write-Log "Failed to connect to $Ssid. $_" "ERROR"
    return $false
  }
}

function Disconnect-Wifi {
  param([string]$InterfaceName)
  try {
    if ([string]::IsNullOrWhiteSpace($InterfaceName)) {
      netsh wlan disconnect | Out-Null
    } else {
      netsh wlan disconnect interface="$InterfaceName" | Out-Null
    }
  } catch { }
}

function Resolve-Password {
  param($Creds)
  if ($Creds -and -not [string]::IsNullOrWhiteSpace($Creds.password)) {
    return $Creds.password
  }
  return ""
}

function Test-Connectivity {
  param($Checks)
  foreach ($check in $Checks) {
    $url = $check.url
    if ([string]::IsNullOrWhiteSpace($url)) { continue }
    try {
      $resp = Invoke-WebRequest -Uri $url -Method Get -UseBasicParsing -TimeoutSec 8 -MaximumRedirection 0
      if ($check.expectStatus -and $resp.StatusCode -ne $check.expectStatus) { continue }
      if ($check.expectBody -and ($resp.Content -notmatch [regex]::Escape($check.expectBody))) { continue }
      if ($resp.BaseResponse -and $resp.BaseResponse.ResponseUri -and $resp.BaseResponse.ResponseUri.Host -eq "202.117.144.205") { continue }
      return $true
    } catch {
      continue
    }
  }
  return $false
}

function Get-IpStatus {
  param([string]$InterfaceAlias)
  try {
    $cfg = Get-NetIPConfiguration -InterfaceAlias $InterfaceAlias -ErrorAction SilentlyContinue
  } catch {
    return $null
  }
  if ($null -eq $cfg) { return $null }
  $ip = ""
  $gw = ""
  if ($cfg.IPv4Address) { $ip = $cfg.IPv4Address.IPAddress }
  if ($cfg.IPv4DefaultGateway) { $gw = $cfg.IPv4DefaultGateway.NextHop }
  return [pscustomobject]@{ IP = $ip; Gateway = $gw }
}

function Invoke-PortalLogin {
  param([string]$ConfigPath)
  $repoRoot = Resolve-RepoRoot
  $scriptPath = Join-Path $repoRoot "web\portal_login.py"
  if (!(Test-Path -Path $scriptPath)) {
    Write-Log "Portal login script not found: $scriptPath" "ERROR"
    return $false
  }
  $pyCmd = $null
  if ($script:Config.pythonPath -and (Test-Path -Path $script:Config.pythonPath)) {
    $pyCmd = $script:Config.pythonPath
  } else {
    $cmdObj = (Get-Command python -ErrorAction SilentlyContinue)
    if ($cmdObj) { $pyCmd = $cmdObj.Source }
    if (-not $pyCmd) {
      $cmdObj = (Get-Command py -ErrorAction SilentlyContinue)
      if ($cmdObj) { $pyCmd = $cmdObj.Source }
    }
    if (-not $pyCmd) {
      $candidates = @(
        "C:\\ProgramData\\anaconda3\\python.exe",
        "C:\\Python311\\python.exe",
        "C:\\Python310\\python.exe",
        "C:\\Python39\\python.exe"
      )
      foreach ($c in $candidates) {
        if (Test-Path -Path $c) { $pyCmd = $c; break }
      }
    }
  }
  if (-not $pyCmd) {
    Write-Log "Python not found. Set pythonPath in config or add to PATH." "ERROR"
    return $false
  }
  if ($pyCmd -is [string]) { $pyCmd = $pyCmd.Trim('"') }
  $args = @($scriptPath, "--config", $ConfigPath, "--all", "--debug")
  $oldPref = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $output = & $pyCmd @args 2>&1
  $exitCode = $LASTEXITCODE
  $ErrorActionPreference = $oldPref
  if ($output) {
    $lines = ($output -split "`r?`n") | Where-Object { $_ -and $_.Trim().Length -gt 0 }
    foreach ($line in $lines) {
      if ($exitCode -ne 0) {
        Write-Log "Portal login output: $line" "WARN"
      } else {
        Write-Log "Portal login output: $line" "INFO"
      }
    }
  }
  return ($exitCode -eq 0)
}

function Get-StatusObject {
  param($Config, [string]$StatePath)
  $adapter = Get-WifiAdapter -PreferredName $Config.adapterName
  $wlan = $null
  if ($adapter) { $wlan = Get-WlanState -InterfaceName $adapter.Name }
  $ip = $null
  if ($adapter) { $ip = Get-IpStatus -InterfaceAlias $adapter.Name }
  $connectivityOk = $false
  try { $connectivityOk = Test-Connectivity -Checks $Config.connectivityChecks } catch { }
  $state = Load-State -Path $StatePath -Config $Config
  $profileName = if ($Config.profileName) { $Config.profileName } else { $Config.ssid }
  $isAllUser = Test-AllUserProfile -Profile $profileName

  return [pscustomobject]@{
    adapter = if ($adapter) { $adapter.Name } else { "" }
    adapterStatus = if ($adapter) { $adapter.Status } else { "" }
    wlanState = if ($wlan) { $wlan.State } else { "" }
    ssid = if ($wlan) { $wlan.Ssid } else { "" }
    ip = if ($ip) { $ip.IP } else { "" }
    gateway = if ($ip) { $ip.Gateway } else { "" }
    connectivityOk = $connectivityOk
    lastState = $state.lastState
    lastError = $state.lastError
    lastLoginAttempt = $state.lastLoginAttempt
    lastLoginSuccess = $state.lastLoginSuccess
    lastOnline = $state.lastOnline
    currentCooldownSeconds = $state.currentCooldownSeconds
    nextLoginAfter = $state.nextLoginAfter
    adapters = Get-AdapterList
    allUserProfile = $isAllUser
  }
}

function Update-State {
  param(
    [object]$State,
    [string]$NewState,
    [string]$ErrorMessage = "",
    [string]$Adapter = "",
    [string]$Ssid = "",
    [string]$Ip = "",
    [string]$Gateway = "",
    [bool]$ConnectivityOk = $false
  )
  $State.lastState = $NewState
  if ($ErrorMessage) { $State.lastError = $ErrorMessage }
  if ($Adapter) { $State.lastAdapter = $Adapter }
  if ($Ssid) { $State.lastSsid = $Ssid }
  if ($Ip) { $State.lastIp = $Ip }
  if ($Gateway) { $State.lastGateway = $Gateway }
  $State.lastConnectivityOk = $ConnectivityOk
}

function Run-Once {
  $config = $script:Config
  $statePath = $script:StatePath
  $stateData = Load-State -Path $statePath -Config $config
  $now = Get-Date
  $isAdmin = Test-IsAdmin

  try {
    $svc = Get-Service -Name "WlanSvc" -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -ne "Running") {
      Start-Service -Name "WlanSvc" -ErrorAction SilentlyContinue | Out-Null
      Start-Sleep -Seconds 2
    }
  } catch { }

  $adapter = Get-WifiAdapter -PreferredName $config.adapterName
  if ($null -eq $adapter) {
    Update-State -State $stateData -NewState "NO_ADAPTER" -ErrorMessage "Wi-Fi adapter not found."
    Save-State -State $stateData -Path $statePath
    Write-Log "Wi-Fi adapter not found." "ERROR"
    return
  }

  if (-not (Ensure-AdapterEnabled -Adapter $adapter)) {
    Update-State -State $stateData -NewState "NEEDS_ADMIN" -ErrorMessage "Adapter disabled. Admin required." -Adapter $adapter.Name
    Save-State -State $stateData -Path $statePath
    return
  }
  Ensure-Autoconfig -InterfaceName $adapter.Name

  $wlan = Get-WlanState -InterfaceName $adapter.Name
  if ($wlan -and $wlan.RadioSoftwareOff) {
    Write-Log "Wi-Fi radio is off. Attempting to enable..." "WARN"
    if ($isAdmin) {
      try { Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch { }
      try { netsh interface set interface name="$($adapter.Name)" admin=enabled | Out-Null } catch { }
      Start-Sleep -Seconds 3
      $wlan = Get-WlanState -InterfaceName $adapter.Name
    }
    if ($wlan -and $wlan.RadioSoftwareOff) {
      Update-State -State $stateData -NewState "RADIO_OFF" -ErrorMessage "Wi-Fi radio is off." -Adapter $adapter.Name
      Save-State -State $stateData -Path $statePath
      Write-Log "Wi-Fi radio is off. Please enable Wi-Fi manually." "WARN"
      return
    }
  }

  $isConnected = $false
  if ($wlan -and ($wlan.State -match "connected|已连接")) { $isConnected = $true }
  if ($isConnected -and [string]::IsNullOrWhiteSpace($wlan.Ssid)) {
    $isConnected = $false
  }

  if ($isConnected -and -not [string]::IsNullOrWhiteSpace($wlan.Ssid) -and $wlan.Ssid -ne $config.ssid) {
    $prevState = $stateData.lastState
    $prevSsid = $stateData.lastSsid
    Update-State -State $stateData -NewState "OTHER_SSID" -Adapter $adapter.Name -Ssid $wlan.Ssid
    Save-State -State $stateData -Path $statePath
    if ($prevState -ne "OTHER_SSID" -or $prevSsid -ne $wlan.Ssid) {
      Write-Log "Connected to other SSID ($($wlan.Ssid)). No action." "INFO"
    }
    return
  }

  if (-not $isConnected) {
    Update-State -State $stateData -NewState "DISCONNECTED" -Adapter $adapter.Name -Ssid $wlan.Ssid
    Connect-ToSsid -Ssid $config.ssid -ProfileName $config.profileName -InterfaceName $adapter.Name | Out-Null
    $wlan = Get-WlanState -InterfaceName $adapter.Name
    $isConnected = $false
    if ($wlan -and ($wlan.State -match "connected|已连接")) { $isConnected = $true }
  }

  $ipStatus = Get-IpStatus -InterfaceAlias $adapter.Name
  $connectivityOk = Test-Connectivity -Checks $config.connectivityChecks
  $connectedToTarget = $false
  if ($wlan -and ($wlan.State -match "connected|已连接") -and $wlan.Ssid -eq $config.ssid) {
    $connectedToTarget = $true
  }

  if ($connectivityOk) {
    Update-State -State $stateData -NewState "ONLINE" -Adapter $adapter.Name -Ssid $wlan.Ssid -Ip $ipStatus.IP -Gateway $ipStatus.Gateway -ConnectivityOk $true
    $stateData.lastOnline = $now.ToString("o")
    $stateData.currentCooldownSeconds = [int]$config.loginCooldownSeconds
    $stateData.nextLoginAfter = ""
    Save-State -State $stateData -Path $statePath
    Write-Log "Connectivity OK." "INFO"
    return
  }

  if ($connectedToTarget) {
    Update-State -State $stateData -NewState "CONNECTED_NO_NET" -Adapter $adapter.Name -Ssid $wlan.Ssid -Ip $ipStatus.IP -Gateway $ipStatus.Gateway -ConnectivityOk $false
    Write-Log "Connected to $($config.ssid) but no internet. Will re-login." "WARN"
  } else {
    Update-State -State $stateData -NewState "DISCONNECTED" -Adapter $adapter.Name -Ssid $wlan.Ssid -Ip $ipStatus.IP -Gateway $ipStatus.Gateway -ConnectivityOk $false
    Save-State -State $stateData -Path $statePath
    Write-Log "Not connected to target SSID. Skip portal login." "INFO"
    return
  }

  $username = $config.credentials.username
  $password = Resolve-Password -Creds $config.credentials
  if ([string]::IsNullOrWhiteSpace($username) -or [string]::IsNullOrWhiteSpace($password)) {
    Update-State -State $stateData -NewState "MISSING_CREDENTIALS" -ErrorMessage "Missing credentials in config."
    Save-State -State $stateData -Path $statePath
    Write-Log "Missing credentials in config. Run set-credentials.ps1." "ERROR"
    return
  }

  if ($stateData.nextLoginAfter) {
    try {
      $nextTime = [datetime]::Parse($stateData.nextLoginAfter)
      if ($now -lt $nextTime) {
        Update-State -State $stateData -NewState "LOGIN_COOLDOWN" -ErrorMessage "Cooldown active."
        Save-State -State $stateData -Path $statePath
        Write-Log "Login cooldown active until $($nextTime.ToString("HH:mm:ss"))" "INFO"
        return
      }
    } catch { }
  }

  Write-Log "Attempting portal login via Python..." "INFO"
  $loginOk = Invoke-PortalLogin -ConfigPath $script:ResolvedConfigPath
  $stateData.lastLoginAttempt = $now.ToString("o")

  if ($loginOk) {
    $stateData.lastLoginSuccess = $now.ToString("o")
    $stateData.currentCooldownSeconds = [int]$config.loginCooldownSeconds
  } else {
    $current = [int]$stateData.currentCooldownSeconds
    $max = [int]$config.loginMaxCooldownSeconds
    if ($current -lt 1) { $current = [int]$config.loginCooldownSeconds }
    $next = [Math]::Min($current * 2, $max)
    $stateData.currentCooldownSeconds = $next
  }

  $stateData.nextLoginAfter = $now.AddSeconds([int]$stateData.currentCooldownSeconds).ToString("o")

  Start-Sleep -Seconds 3
  $connectivityOk = Test-Connectivity -Checks $config.connectivityChecks

  if ($connectivityOk) {
    Update-State -State $stateData -NewState "ONLINE" -Adapter $adapter.Name -Ssid $wlan.Ssid -Ip $ipStatus.IP -Gateway $ipStatus.Gateway -ConnectivityOk $true
    $stateData.lastOnline = (Get-Date).ToString("o")
    Write-Log "Connectivity restored after portal login." "INFO"
  } else {
    if ($connectedToTarget) {
      Write-Log "Still offline. Disconnecting and reconnecting Wi-Fi..." "WARN"
      Disconnect-Wifi -InterfaceName $adapter.Name
      Start-Sleep -Seconds 2
      Connect-ToSsid -Ssid $config.ssid -ProfileName $config.profileName -InterfaceName $adapter.Name | Out-Null
    }
    $err = if ($loginOk) { "Connectivity still failing." } else { "Portal login failed." }
    Update-State -State $stateData -NewState "LOGIN_FAILED" -ErrorMessage $err -Adapter $adapter.Name -Ssid $wlan.Ssid -Ip $ipStatus.IP -Gateway $ipStatus.Gateway -ConnectivityOk $false
    Write-Log "Connectivity still failing. Will retry." "WARN"
  }

  Save-State -State $stateData -Path $statePath
}

$script:ResolvedConfigPath = Resolve-ConfigPath -Path $ConfigPath
$script:Config = Load-Config -Path $script:ResolvedConfigPath
$script:Config = Ensure-ConfigDefaults -Config $script:Config
$script:LogPath = Resolve-LogPath -Path $script:Config.logPath
$script:StatePath = Resolve-StatePath -Path $script:Config.statePath
$script:TriggerPath = Resolve-TriggerPath -Path $script:Config.triggerPath
$script:LogRotateBytes = [int]($script:Config.logRotateMB * 1024 * 1024)
$script:LogRotateKeep = [int]$script:Config.logRotateKeep

if ($Status) {
  $statusObj = Get-StatusObject -Config $script:Config -StatePath $script:StatePath
  $statusObj | ConvertTo-Json -Depth 6
  exit 0
}

$mutex = Acquire-Mutex -Name "Global\SNNUWifiKeepalive"
if ($null -eq $mutex) {
  Write-Log "Another instance is already running. Exiting." "WARN"
  exit 0
}

Write-Log "SNNU Wi-Fi keepalive started." "INFO"

try {
  if ($Once) {
    Run-Once
    exit 0
  }

  while ($true) {
    try {
      Run-Once
    } catch {
      $err = ($_ | Out-String)
      $lines = $err -split "`r?`n"
      foreach ($line in $lines) {
        if ($line -and $line.Trim().Length -gt 0) {
          Write-Log $line "ERROR"
        }
      }
    }
    if (Sleep-WithTrigger -Seconds $script:Config.intervalSeconds) {
      Write-Log "Trigger received. Running immediate cycle." "INFO"
      continue
    }
  }
} finally {
  if ($mutex) { $mutex.ReleaseMutex(); $mutex.Dispose() }
}
