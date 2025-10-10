#requires -RunAsAdministrator
<#
.SYNOPSIS
  Enables and configures Event Logs needed for SmartPOS POS Protect diagnostics (LTSC 2021 defaults).
  - Enables PrintService/Operational
  - Increases System/Application log sizes
  - Sets retention
  - Verifies current status
#>

Write-Host "== SmartPOS POS Protect: enabling EventLog channels ==" -ForegroundColor Cyan

function Set-Log($name, $maxMB) {
  $bytes = [int]$maxMB * 1MB
  wevtutil sl $name /ms:$bytes /rt:true
  Write-Host "Configured $name max size: $maxMB MB, retention: true"
}

# Core logs
Set-Log -name "System" -maxMB 256
Set-Log -name "Application" -maxMB 256

# Enable PrintService/Operational for detailed printing pipeline diagnostics
$printOp = "Microsoft-Windows-PrintService/Operational"
wevtutil sl $printOp /e:true
Set-Log -name $printOp -maxMB 128

# Optional: enable additional storage logs if present
$storageLogs = @(
  "Microsoft-Windows-Storage-Storport/Operational",
  "Microsoft-Windows-Ntfs/Operational"
)
foreach ($log in $storageLogs) {
  try { wevtutil sl $log /e:true; Set-Log -name $log -maxMB 128 } catch { }
}

# Show summary
Write-Host "`n== Effective settings ==" -ForegroundColor Cyan
wevtutil gl System | Select-String -Pattern "maximum", "retention"
wevtutil gl Application | Select-String -Pattern "maximum", "retention"
wevtutil gl $printOp | Select-String -Pattern "enabled", "maximum", "retention"

Write-Host "`nDone."
