param([ValidateSet('BASE','HID')][string]$Profile='BASE')
$ErrorActionPreference='Stop'
$map=@{ BASE='etw_profile_base.reg'; HID='etw_profile_hid.reg' }
$reg=Join-Path $PSScriptRoot $map[$Profile]
reg import $reg | Out-Null
try { & logman stop SmartPOS_Autologger -ets | Out-Null } catch {}
Start-Sleep -Milliseconds 500
try { & logman start SmartPOS_Autologger -ets | Out-Null } catch {}
Write-Host "[OK] ETW profile applied: $Profile"