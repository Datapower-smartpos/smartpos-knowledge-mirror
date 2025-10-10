# SmartPOS USB Agent — uninstall_service.ps1 (v1.4.1)
# Останавливает и удаляет Windows-службу "SmartPOS_USB_Service".

[CmdletBinding()]
param(
  [string]$ServiceName = 'SmartPOS_USB_Service'
)

$ErrorActionPreference = 'Stop'

function Info($m){ Write-Host "[INFO] $m" }
function Fail($m){ Write-Error $m }

try {
  $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
  if ($svc) {
    Info "Stopping service..."
    try { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 } catch {}
    Info "Deleting service..."
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 1
  } else {
    Info "Service not found: $ServiceName"
  }
  Write-Host "OK"
  exit 0
}
catch {
  Fail "Uninstall failed: $($_.Exception.Message)"
  exit 1
}
