Write-Host "Force purge spooler (admin required)..."
Stop-Service Spooler -Force
Remove-Item -Path "C:\Windows\System32\spool\PRINTERS\*" -Recurse -Force
Start-Service Spooler
Write-Host "Done (hard)."
