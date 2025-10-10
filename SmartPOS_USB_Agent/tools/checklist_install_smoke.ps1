# SmartPOS USB Agent — Install Smoke Checklist
# Purpose: Run post-install checks and print PASS/FAIL summary. Exit code 0 = PASS, 1 = FAIL.
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\tools\checklist_install_smoke.ps1 [-AppDir "C:\Program Files\SmartPOS_USB_Agent"]
# Notes:
#   - RU/EN messages
#   - No admin required (service/event log reads usually allowed). If permission is denied, the script degrades gracefully.
#   - Only std PowerShell (no external modules)

param(
  [string]$AppDir = "$env:ProgramFiles\SmartPOS_USB_Agent",
  [int]$TimeoutSec = 20,
  [string]$ZipOut = "",
  [switch]$NoEventLog,
  [switch]$Verbose,
  # Service/Watchdog checks
  [string]$ServiceName = "SmartPOS_USB_Agent",
  [string]$EventSource = "SmartPOS_USB_Agent",
  [switch]$SinceBoot,       # считать, что проверка идёт после ребута (фильтровать события и ожидать Running)
  [switch]$CheckWatchdog    # проверять WatchdogPing в Event Log
)

$ErrorActionPreference = 'Stop'

# ------------------ helpers ------------------
$Global:Checks = @()
function Add-CheckResult {
  param([string]$Name, [bool]$Ok, [string]$Msg = "")
  $Global:Checks += [pscustomobject]@{ Name = $Name; Ok = $Ok; Message = $Msg }
  $tag = if ($Ok) { 'PASS' } else { 'FAIL' }
  $color = if ($Ok) { 'Green' } else { 'Red' }
  Write-Host "[$tag] $Name" -ForegroundColor $color
  if ($Msg) { Write-Host "  $Msg" }
}

function Invoke-SafeBlock {
  param([scriptblock]$Block, [string]$OnError = "")
  try { & $Block } catch { if ($OnError) { Write-Host $OnError -ForegroundColor Yellow }; return $null }
}

function Test-JsonValid {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return $false, "File not found / Файл не найден: $Path" }
  $raw = Get-Content -Raw -Encoding UTF8 -Path $Path
  try { $raw | ConvertFrom-Json | Out-Null; return $true, $null } catch { return $false, "Invalid JSON / Невалидный JSON: $($_.Exception.Message)" }
}

# When we need to filter events "since last boot"
function Get-LastBootTime {
  try { return (Get-CimInstance Win32_OperatingSystem).LastBootUpTime } catch { return (Get-Date).AddHours(-24) }
}

# ------------------ paths ------------------
$BatPath = Join-Path $AppDir 'src\python\run_usb_devctl.bat'
$CfgDir = Join-Path $env:ProgramData 'SmartPOS\usb_agent'
$CfgPath = Join-Path $CfgDir 'config.json'

Write-Host "AppDir: $AppDir" -ForegroundColor Cyan
Write-Host "ProgramData cfg: $CfgPath" -ForegroundColor Cyan
if ($Verbose) { Write-Host "Verbose ON" -ForegroundColor DarkGray }

# 1) App files
Add-CheckResult -Name 'BAT present / Наличие BAT' -Ok (Test-Path $BatPath) -Msg $BatPath

# 2) Config JSON in ProgramData
$ok, $msg = Test-JsonValid -Path $CfgPath
$msgText = if ($msg) { $msg } else { 'OK' }
Add-CheckResult -Name 'Config JSON valid / Конфиг валиден' -Ok $ok -Msg $msgText

# 3) CLI --help
if (Test-Path $BatPath) {
  $pinfo = New-Object System.Diagnostics.ProcessStartInfo
  $pinfo.FileName = $BatPath
  $pinfo.Arguments = '--help'
  $pinfo.UseShellExecute = $false
  $pinfo.RedirectStandardOutput = $true
  $pinfo.RedirectStandardError = $true
  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $pinfo
  [void]$proc.Start()
  if (-not $proc.WaitForExit($TimeoutSec * 1000)) { try { $proc.Kill() }catch {} }
  $out = $proc.StandardOutput.ReadToEnd() + "`n" + $proc.StandardError.ReadToEnd()
  $hasSig = ($out -match '(SmartPOS|USB|Agent|Help|Usage|Использование|Помощь)')
  Add-CheckResult -Name 'CLI --help output / Вывод --help' -Ok $hasSig -Msg ($out.Trim()[0..[Math]::Min($out.Length, 300) -as [int]] -join '')
}
else {
  Add-CheckResult -Name 'CLI --help output / Вывод --help' -Ok $false -Msg 'BAT not found'
}

# 4) Self-test export
if (Test-Path $BatPath) {
  $zip = if ([string]::IsNullOrWhiteSpace($ZipOut)) { Join-Path $env:TEMP ('spusb_selftest_{0:yyyyMMdd_HHmmss}.zip' -f (Get-Date)) } else { $ZipOut }
  if ($Verbose) { Write-Host "ZIP target: $zip" -ForegroundColor DarkGray }
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $BatPath
  $psi.Arguments = "--selftest --out `"$zip`""
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $p = New-Object System.Diagnostics.Process; $p.StartInfo = $psi; [void]$p.Start()
  if (-not $p.WaitForExit($TimeoutSec * 1000)) { try { $p.Kill() }catch {} }
  $okZip = Test-Path $zip
  $zipMsg = if ($okZip) { $zip } else { 'No ZIP produced / ZIP не создан' }
  Add-CheckResult -Name 'Self-test export / Самотест экспорт' -Ok $okZip -Msg $zipMsg
}
else {
  Add-CheckResult -Name 'Self-test export / Самотест экспорт' -Ok $false -Msg 'BAT not found'
}

# 5) Service status (graceful if absent)
$svc = Invoke-SafeBlock { Get-Service -Name $ServiceName -ErrorAction Stop }
if ($svc) {
  Add-CheckResult -Name 'Service installed / Служба установлена' -Ok $true -Msg ("Status={0}, StartType={1}, Name={2}" -f $svc.Status, $svc.StartType, $ServiceName)
  Add-CheckResult -Name 'Service StartType=Automatic' -Ok ($svc.StartType -eq 'Automatic') -Msg $svc.StartType
  if ($SinceBoot) {
    Add-CheckResult -Name 'Service Running after reboot / Служба запущена после ребута' -Ok ($svc.Status -eq 'Running') -Msg $svc.Status
  }
}
else {
  Add-CheckResult -Name 'Service installed / Служба установлена' -Ok $false -Msg 'Service not found / Служба не найдена'
}

# 6) Event Log (watchdog/service)
if ($NoEventLog) {
  Add-CheckResult -Name 'Event Log (skipped) / Журнал событий (пропущен)' -Ok $true -Msg 'NoEventLog switch set'
}
else {
  $events = Invoke-SafeBlock { Get-WinEvent -LogName Application -MaxEvents 500 }
  if ($events) {
    $flt = $events | Where-Object { $_.ProviderName -eq $EventSource }
    if ($SinceBoot) {
      $boot = Get-LastBootTime
      $flt = $flt | Where-Object { $_.TimeCreated -ge $boot }
    }
    $started = $flt | Where-Object { $_.Message -match 'ServiceStarted' } | Select-Object -First 1
    $ping = if ($CheckWatchdog) { $flt | Where-Object { $_.Message -match 'WatchdogPing' } | Select-Object -First 1 } else { $null }
    $top = $flt | Select-Object -First 10 TimeCreated, Message
    if ($top) { 
      $evMsg = ($top | Out-String).Trim()
      Add-CheckResult -Name 'Event Log entries / Записи в журнале' -Ok $true -Msg $evMsg
    }
    $startedMsg = if ($started) { "OK" }else { "Not found" }
    Add-CheckResult -Name 'EventLog ServiceStarted' -Ok ([bool]$started) -Msg $startedMsg
    if ($CheckWatchdog) {
      $pingMsg = if ($ping) { "OK" }else { "Not found" }
      Add-CheckResult -Name 'EventLog WatchdogPing' -Ok ([bool]$ping) -Msg $pingMsg
    }
  }
  else {
    Add-CheckResult -Name 'Event Log entries / Записи в журнале' -Ok $false -Msg 'Cannot read Application log'
  }
}

# ------------------ summary ------------------
$fail = $Checks | Where-Object { -not $_.Ok }
Write-Host "`n==== SUMMARY / ИТОГ ====" -ForegroundColor Cyan
$Checks | ForEach-Object { 
  $status = if ($_.Ok) { 'OK' } else { 'FAIL' }
  Write-Host ("- {0}: {1}" -f $_.Name, $status)
}

if ($fail) {
  Write-Host "`nSome checks failed / Есть ошибки." -ForegroundColor Red
  exit 1
}
else {
  Write-Host "`nAll checks passed / Все проверки пройдены." -ForegroundColor Green
  exit 0
}