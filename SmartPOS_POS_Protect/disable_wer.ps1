$ErrorActionPreference='Stop'
reg import "$PSScriptRoot\wer_disable_rollback.reg"
Restart-Service WerSvc -Force
Write-Host "[OK] WER disabled & cleaned"