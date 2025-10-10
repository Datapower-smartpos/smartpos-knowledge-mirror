# SmartPOS_POS_Protect tools

This folder contains helper scripts to initialize Windows diagnostics for the POS Protect agent.

## Что делают утилиты
    • evt_enable.ps1 (Administrator PowerShell)
        ◦ включает канал Microsoft-Windows-PrintService/Operational,
        ◦ увеличивает размеры логов System/Application и включает retention,
        ◦ опционально включает некоторые storage-каналы (если есть),
        ◦ печатает краткую сводку настроек.
    • wer_enable.ps1 (Administrator PowerShell)
        ◦ включает Windows Error Reporting,
        ◦ настраивает LocalDumps: C:\ProgramData\Microsoft\Windows\WER\LocalDumps, DumpCount=50, DumpType=MiniDump,
        ◦ запускает WerSvc (если доступно).
Оба скрипта многократно перезапускаемы (идемпотентны).

## Использование
Open **PowerShell as Administrator** and run:

    Set-Location <repo-root>\SmartPOS_POS_Protect\tools
    .\evt_enable.ps1
    .\wer_enable.ps1

These scripts are **idempotent** and safe to re-run.
