$ErrorActionPreference='Stop'
try { & logman stop SmartPOS_Autologger -ets | Out-Null } catch {}
reg import "$PSScriptRoot\etw_autologger_disable.reg"
Write-Host "[OK] ETW Autologger disabled"