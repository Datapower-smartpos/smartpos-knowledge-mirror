# OPS MEMO (коротко)

1) Включить WER/ETW: Admin PowerShell → `./enable_wer.ps1` ; `./enable_etw.ps1`
2) Проверить статус: `http://127.0.0.1:11888/api/status`
3) Сменить профиль ETW: `./profiles/etw/apply_etw_profile.ps1 -Profile HID`
4) Экспорт EventLog: Трэй → «Экспорт EventLog» или `./eventlog_export/export_eventlog.ps1`
5) Экспорт ZIP: Трэй → «Экспорт (WER,ETL,LOG,DB,EventLog)»
6) Откат ETW: `reg import ./profiles/etw/etw_disable.reg; logman stop SmartPOS_Autologger -ets`
