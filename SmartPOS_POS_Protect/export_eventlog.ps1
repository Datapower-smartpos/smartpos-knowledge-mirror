param(
[string]$OutDir='C:\POS\export\eventlog',
[string]$Logs='Application,System,Microsoft-Windows-PrintService/Operational,Microsoft-Windows-PrintService/Admin,Microsoft-Windows-Diagnostics-Performance/Operational'
)
$ErrorActionPreference='Stop'
$py = (Get-Command python -ErrorAction SilentlyContinue)
if(-not $py){ throw 'Python is not installed or not in PATH' }
python "$PSScriptRoot\eventlog_export.py" $OutDir $Logs
Write-Host "[OK] EventLog exported to $OutDir"