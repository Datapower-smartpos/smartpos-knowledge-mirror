# SmartPOS USB Agent — Uninstall Watchdog (v1.4.1)
param([string]$TaskName='SmartPOS_USB_Watchdog')
$ErrorActionPreference='Stop'
try{ 
  if(Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue){
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop | Out-Null
    Write-Host "[OK] Watchdog task '$TaskName' removed."
  } else {
    Write-Host "[INFO] Watchdog task '$TaskName' not found."
  }
}catch{ Write-Error "[ERR] $($_.Exception.Message)"; exit 1 }
