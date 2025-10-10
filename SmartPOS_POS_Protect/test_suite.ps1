$ErrorActionPreference='Continue'
Write-Host "== WER crash test =="
& "$PSScriptRoot\test_crash_dummy.ps1"
Start-Sleep 2
Write-Host "== Check dump presence =="
Get-ChildItem C:\POS\wer -Recurse -Include *.dmp,*.wer | Select-Object -First 3 | Format-Table FullName,Length


Write-Host "== ETW generation =="
& "$PSScriptRoot\test_etw_load.ps1"
Start-Sleep 2
Get-ChildItem C:\POS\etl -Recurse -Include *.etl | Select-Object -First 3 | Format-Table FullName,Length


Write-Host "== Export EventLog =="
& "$PSScriptRoot\..\eventlog_export\export_eventlog.ps1" -OutDir 'C:\POS\export\eventlog'
Get-ChildItem C:\POS\export\eventlog -Include *.evtx,*.csv -Recurse | Select-Object -First 4 | Format-Table Name,Length


Write-Host "== Export ZIP =="
$api = (Get-Content "$PSScriptRoot\..\config.json" | ConvertFrom-Json).api_key
Invoke-WebRequest -UseBasicParsing -Headers @{"X-API-Key"=$api} "http://127.0.0.1:11888/api/export?mask=wer,etl,logs,db,eventlog"