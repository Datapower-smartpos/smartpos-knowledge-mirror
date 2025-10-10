param([string]$IssPath='installer\inno\SmartPOS_USB_Agent.iss')
$ErrorActionPreference='Stop'
function Resolve-IssPath([string]$p){
  $c=@($p,(Join-Path (Get-Location).Path $p),'.\SmartPOS_USB_Agent.iss','..\inno\SmartPOS_USB_Agent.iss','..\..\installer\inno\SmartPOS_USB_Agent.iss')
  foreach($i in $c){ if(Test-Path $i){ return (Resolve-Path $i).Path } }
  throw "ISS file not found. Tried:`n - " + ($c -join "`n - ")
}
try{$path=Resolve-IssPath $IssPath; Write-Host "[INFO] Checking: $path"; $txt=Get-Content -Raw -Path $path -Encoding UTF8}catch{Write-Error $_.Exception.Message; exit 1}
$checks=@(
  @{Name='Version';     Ok=($txt -match '#define\s+AppVersion\s+"1\.4\.1"')},
  @{Name='AppName';     Ok=($txt -match '#define\s+AppName\s+"SmartPOS USB Agent"')},
  @{Name='DirName';     Ok=($txt -match 'DefaultDirName=\{pf\}\\SmartPOS_USB_Agent')},
  @{Name='NoEllipsis';  Ok=(-not ($txt -match '\.\.\.'))},
  @{Name='SingleRun';   Ok=(($txt -split '\[Run\]').Count -le 2)},
  @{Name='HasCLI';      Ok=($txt -match 'usb_devctl_cli\.py')},
  @{Name='HasService';  Ok=($txt -match 'smartpos_usb_service_v14\.py')},
  @{Name='HasCore';     Ok=($txt -match 'usb_agent_core\.py')},
  @{Name='HasTrace';    Ok=($txt -match 'trace_wrappers_v2\.py')},
  @{Name='HasScripts';  Ok=($txt -match 'install_service\.ps1') -and ($txt -match 'uninstall_service\.ps1')},
  @{Name='HasWatchdog'; Ok=($txt -match 'install_watchdog\.ps1') -and ($txt -match 'uninstall_watchdog\.ps1')},
  @{Name='NoTray';      Ok=(-not ($txt -match 'SmartPOS\.UsbTray\.exe'))},
  @{Name='ApiKeyDlg';   Ok=($txt -match "CreateInputQueryPage\(wpSelectDir,\s*'API Key'")},
  @{Name='ConfigSave';  Ok=($txt -match '\{commonappdata\}\\SmartPOS\\usb_agent\\config\.json')},
  @{Name='RunPS';       Ok=($txt -match 'powershell\.exe";\s*Parameters:\s*"-ExecutionPolicy Bypass -File ""\{app\}\\installer\\scripts\\install_service\.ps1""') -and ($txt -match 'powershell\.exe";\s*Parameters:\s*"-ExecutionPolicy Bypass -File ""\{app\}\\tools\\install_watchdog\.ps1""')}
)
$failed=$checks|?{ -not $_.Ok }
if($failed){ "FAILED checks:`n - " + (($failed|%{$_.Name}) -join "`n - "); exit 2 } else { "OK: ISS looks correct for v1.4.1"; exit 0 }
