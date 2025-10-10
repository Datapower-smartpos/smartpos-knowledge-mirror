$cfg = Get-Content "$PSScriptRoot\config.json" | ConvertFrom-Json
$sku = $cfg.sku
$profile = if ($sku -eq 'HID_POS') { 'HID' } else { 'BASE' }
& "$PSScriptRoot\profiles\etw\apply_etw_profile.ps1" -Profile $profile
Write-Host "[OK] SKU=$sku, applied ETW profile: $profile"