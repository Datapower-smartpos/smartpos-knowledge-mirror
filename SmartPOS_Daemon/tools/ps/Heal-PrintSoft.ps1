param([string]$PrinterName = "POS_Receipt")
Write-Host "Cancel sticky..."
Get-PrintJob -PrinterName $PrinterName -ErrorAction SilentlyContinue | Remove-PrintJob -ErrorAction SilentlyContinue
Write-Host "Clear spooler queue (soft)..."
Get-Service -Name Spooler | Stop-Service -Force
Remove-Item -Path "C:\Windows\System32\spool\PRINTERS\*" -Force -ErrorAction SilentlyContinue
Get-Service -Name Spooler | Start-Service
Write-Host "Done (soft)."
