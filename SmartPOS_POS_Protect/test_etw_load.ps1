1..2000 | % { Start-Job { Get-Process | Out-Null } } | Out-Null
Start-Sleep 3
Get-Job | Remove-Job -Force