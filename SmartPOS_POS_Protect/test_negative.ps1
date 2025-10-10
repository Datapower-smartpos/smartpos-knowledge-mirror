$ErrorActionPreference='Continue'
Write-Host "== NEGATIVE: нет прав на HKLM =="
Write-Host "(manual) Запустите enable_wer.ps1 без админ-прав: ожидается ошибка доступа"


Write-Host "== NEGATIVE: мало места на диске =="
$cfg = Get-Content "$PSScriptRoot\..\config.json" | ConvertFrom-Json
$cfg.wer_dump_minfree_mb = 999999
$cfg | ConvertTo-Json | Set-Content "$PSScriptRoot\..\config.json"
Invoke-WebRequest http://127.0.0.1:11888/api/policy/reload | Out-Null
Write-Host "Проверьте в logs/collector.log, что DumpType переключился на Mini"


Write-Host "== NEGATIVE: нет Python =="
Write-Host "Ожидаем, что export_eventlog.ps1 сообщит об отсутствии Python и завершится с ошибкой"
try { & "$PSScriptRoot\..\eventlog_export\export_eventlog.ps1" -OutDir 'C:\POS\export\eventlog' } catch { Write-Host $_.Exception.Message }