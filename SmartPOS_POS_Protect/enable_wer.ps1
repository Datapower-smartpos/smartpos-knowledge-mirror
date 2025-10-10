param([string]$DumpRoot='C:\POS\wer')
$ErrorActionPreference='Stop'
if(-not (Test-Path $DumpRoot)){ New-Item -ItemType Directory -Force -Path $DumpRoot | Out-Null }
Enable-WindowsErrorReporting
Set-Service WerSvc -StartupType Automatic
Start-Service WerSvc
reg import "$PSScriptRoot\wer_enable_full.reg"
Write-Host "[OK] WER enabled. DumpRoot=$DumpRoot"