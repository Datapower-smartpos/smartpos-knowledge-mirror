param([string]$PrinterName = "POS_Receipt")
Start-Process notepad.exe
Write-Host "Opened Notepad for manual test print to $PrinterName"
