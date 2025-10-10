# SmartPOS USB Agent — Install Watchdog (v1.4.1)
# Создаёт задачу Планировщика, которая на старте ОС запускает watchdog_core.ps1.
# Watchdog проверяет сервис SmartPOS_USB_Service и (опционально) Tray, пишет в Event Log.

param(
  [string]$TaskName = 'SmartPOS_USB_Watchdog',
  [int]$IntervalSec = 30
)

$ErrorActionPreference = 'Stop'

Write-Host "[INFO] Installing Watchdog task '$TaskName'..."

# Путь к watchdog_core.ps1
$scriptPath = Join-Path $PSScriptRoot 'watchdog_core.ps1'

# Генерируем watchdog_core.ps1, если отсутствует
if (-not (Test-Path $scriptPath)) {
  @'
param([int]$IntervalSec=30)
$ErrorActionPreference='Continue'
$logSource='SmartPOS_USB_Agent'
try{ if(-not [System.Diagnostics.EventLog]::SourceExists($logSource)){ New-EventLog -LogName Application -Source $logSource } }catch{}
function Write-AppLog($msg,[string]$entryType='Information'){ try{ Write-EventLog -LogName Application -Source $logSource -EntryType $entryType -EventId 1000 -Message $msg }catch{}}
$svcName='SmartPOS_USB_Service'
# Tray не обязателен: проверяем только если exe найден
$trayExe=(Get-ChildItem -Path "$env:ProgramFiles\SmartPOS_USB_Agent" -Recurse -Include SmartPOS.UsbTray.exe -ErrorAction SilentlyContinue | Select-Object -First 1)
while($true){
  try{
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if($null -eq $svc -or $svc.Status -ne 'Running'){
      Write-AppLog "Service '$svcName' not running — attempting start" 'Warning'
      Start-Service -Name $svcName -ErrorAction SilentlyContinue
    }
    if($trayExe){
      $tray = Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($trayExe.Name)) -ErrorAction SilentlyContinue
      if($null -eq $tray){ Write-AppLog "Tray not running — starting $($trayExe.FullName)" 'Warning'; Start-Process -FilePath $trayExe.FullName -WindowStyle Minimized }
    }
  }catch{ Write-AppLog "Watchdog error: $($_.Exception.Message)" 'Error' }
  Start-Sleep -Seconds $IntervalSec
}
'@ | Set-Content -Path $scriptPath -Encoding UTF8 -Force
}

# Регистрируем задачу
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-ExecutionPolicy Bypass -NoLogo -NonInteractive -File `"$scriptPath`" -IntervalSec $IntervalSec"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -RunLevel Highest -LogonType ServiceAccount
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description 'SmartPOS USB Agent Watchdog' -Force | Out-Null

Write-Host "[OK] Watchdog task '$TaskName' installed. Interval: $IntervalSec sec"
