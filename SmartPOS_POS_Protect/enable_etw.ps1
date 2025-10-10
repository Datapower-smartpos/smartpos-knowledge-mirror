param([string]$EtlDir='C:\POS\etl')
$ErrorActionPreference='Stop'
if(-not (Test-Path $EtlDir)){ New-Item -ItemType Directory -Force -Path $EtlDir | Out-Null }
reg import "$PSScriptRoot\etw_autologger_enable.reg"
try { & logman start SmartPOS_Autologger -ets | Out-Null } catch {}
Write-Host "[OK] ETW Autologger configured. ETL dir=$EtlDir"