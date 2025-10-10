param([string[]]$TargetVidPid=@('VID_04D9&PID_1603'))
$ErrorActionPreference='Stop'
foreach($id in $TargetVidPid){
$keys = Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Enum" -Recurse -ErrorAction SilentlyContinue |
Where-Object { $_.Name -like "*${id}*" -and $_.Name -like "*Device Parameters*" }
foreach($k in $keys){
New-ItemProperty -Path $k.PSPath -Name 'SelectiveSuspendEnabled' -Value 0 -PropertyType DWord -Force | Out-Null
}
}
Write-Host "[OK] USB Selective Suspend disabled for: $($TargetVidPid -join ', ')"