SmartPOS USB Agent — README & Samples (v1.4.1)

Назначение
- Быстрые примеры запуска сервиса/CLI, экспорта логов, smoke‑тестов.
- Готовые сниппеты PowerShell/cURL для инженеров и техподдержки.
- Полный «шпаргалочный» список всех команд проекта: юнит-тесты, ручные тесты, сборка MSI/EXE, выпуск ZIP, проверка логов.

Требования окружения
- Windows 10/11 x64.
- Python 3.9+ x64 (для службы и CLI, PATH содержит `python`/`pythonw`).
- WiX Toolset (candle.exe, light.exe) + подключение `WixUtilExtension`.
- Inno Setup Compiler (unicode).
- Права администратора на установку службы/задач Планировщика.
- .NET Desktop Runtime x64 НЕ требуется для агента (нужен только для отдельного Tray MSI, если используется).

Ключевые пути
- Каталог установки: `%ProgramFiles%\SmartPOS_USB_Agent`
- Исходники (локальный репозиторий): `C:\AI\SmartPOS\USB_smart_standalone`
- Конфиг: `%ProgramData%\SmartPOS\usb_agent\config.json`
- Служба: `SmartPOS_USB_Service`
- Watchdog (Планировщик): `SmartPOS_USB_Watchdog`

Пример config.json
{
  "api_key": "",
  "created_utc": "2025-01-01T00:00:00Z",
  "debug": false
}

Безопасность и политика
- Конфигурация хранится в %ProgramData%. Права на запись требуются админские.
- CLI поддерживает заголовок X-API-Key (передаётся через --api-key или берётся из config.json).

────────────────────────────────────────────────────────────────
РАЗДЕЛ A — CLI / HTTP API

A1. Статус / Префлайт / Перезагрузка правил
# Статус (GET /api/status)
"%ProgramFiles%\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" status
Альтернатива (если нужен чистый Python-вызов)
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" status

# Префлайт (POST /api/preflight)
"%ProgramFiles%\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" preflight --api-key YOUR_KEY
Альтернатива (если нужен чистый Python-вызов):
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" preflight --api-key YOUR_KEY
# Перезагрузка правил (POST /api/policy/reload)
"%ProgramFiles%\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" policy-reload
Альтернатива (если нужен чистый Python-вызов):
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" policy-reload

A2. Действия и перезапуск службы
# POST /api/action/<name> — пример: recycle
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" action recycle
# Перезапуск службы: API → fallback sc.exe
"%ProgramFiles%\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" service-restart
Альтернатива (если нужен чистый Python-вызов):
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" service-restart

A3. Экспорт ZIP — два режима
# HTTP-режим (служба должна работать)
"%ProgramFiles%\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" export-zip --mask "*.log" --out "C:\Temp\usb_export.zip"
или
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" export-zip --mask "*.log" --out "C:\Temp\usb_export.zip"
# Локальный (оффлайн) от корня установки
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" export-zip --local --root "%ProgramFiles%\SmartPOS_USB_Agent" --mask "**\*.log" --out "C:\Temp\usb_export_offline.zip"

A4. Smoke-тест CLI (без сети)
python "%ProgramFiles%\SmartPOS_USB_Agent\src\python\usb_devctl_cli.py" selftest-export
# Ожидаем JSON вида: {"ok": true, "files": ["logs/a.log"], ...}

A5. Прямые вызовы HTTP (curl)
curl http://127.0.0.1:8731/api/status
curl -X POST http://127.0.0.1:8731/api/preflight -H "X-API-Key: YOUR_KEY"
curl -X POST http://127.0.0.1:8731/api/policy/reload -H "X-API-Key: YOUR_KEY"
curl -L "http://127.0.0.1:8731/api/export?mask=*.log" -o C:\Temp\export.zip -H "X-API-Key: YOUR_KEY"

Полезные маски (glob)
*.log             — все .log в текущей папке
**\*.log          — все .log рекурсивно
logs\*.log        — только из папки logs
**\*.{log,txt}    — лог+txt (если оболочка поддерживает группы расширений)
**\usb_*.json     — все json с префиксом usb_

────────────────────────────────────────────────────────────────
РАЗДЕЛ B — Служба и Watchdog

B1. Установка/переустановка/удаление службы
# Установка (если ставили MSI/EXE — уже выполнено)
powershell -ExecutionPolicy Bypass -File "%ProgramFiles%\SmartPOS_USB_Agent\installer\scripts\install_service.ps1"
# Форс-переустановка
powershell -ExecutionPolicy Bypass -File "%ProgramFiles%\SmartPOS_USB_Agent\installer\scripts\install_service.ps1" -ForceReinstall
# Удаление
powershell -ExecutionPolicy Bypass -File "%ProgramFiles%\SmartPOS_USB_Agent\installer\scripts\uninstall_service.ps1"

B2. Watchdog (Планировщик задач)
# Установка watchdog
powershell -ExecutionPolicy Bypass -File "%ProgramFiles%\SmartPOS_USB_Agent\tools\install_watchdog.ps1" -TaskName SmartPOS_USB_Watchdog -IntervalSec 30
# Удаление watchdog
powershell -ExecutionPolicy Bypass -File "%ProgramFiles%\SmartPOS_USB_Agent\tools\uninstall_watchdog.ps1" -TaskName SmartPOS_USB_Watchdog

B3. Быстрые проверки статуса
Get-Service SmartPOS_USB_Service
sc query SmartPOS_USB_Service
Get-ScheduledTask -TaskName SmartPOS_USB_Watchdog
Get-EventLog -LogName Application -Source SmartPOS_USB_Agent -Newest 20

────────────────────────────────────────────────────────────────
РАЗДЕЛ C — Тесты (локальный репозиторий)

C1. Юнит-тесты (stdlib, без сети)
cd C:\AI\SmartPOS\USB_smart_standalone
python -m pytest -q
# Должны существовать:
# tests\test_sqlite_retention.py
# tests\test_export_zip_mask.py
# tests\test_config_and_hot_reload.py
# tests\test_cli_export_smoke.py

C2. Ручные тесты (Hand Tests — краткий план)
# Служба
Get-Service SmartPOS_USB_Service
# API
curl http://127.0.0.1:8731/api/status
curl http://127.0.0.1:8731/api/preflight
curl "http://127.0.0.1:8731/api/export?mask=*.log" -o export.zip
# Watchdog:
1) завершите процесс трея (если он установлен отдельным MSI) → поднимется; служба контролируется в любом случае (но пока трей не ставим)

2) Start-ScheduledTask -TaskName SmartPOS_USB_Watchdog

3) Stop-Service SmartPOS_USB_Service -Force → подождать 5–30 сек → Get-Service SmartPOS_USB_Service должен вновь показать Running.

4) Проверить Event Log: Get-EventLog -LogName Application -Source SmartPOS_USB_Agent -Newest 20 | Select TimeGenerated,EntryType,Message

5) Start-Sleep -Seconds 8

# Hot-reload: правьте %ProgramData%\SmartPOS\usb_agent\config.json (api_key) → сервис подхватит без рестарта службы

# Инженерный UX-скрипт (PowerShell)
Разрешить выполнение для сессии и запустить меню UX - работает локально рядом с исходниками, не требует установки агента
Команды:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell -NoLogo -ExecutionPolicy Bypass -File ".\tools\ux\SmartPOS-USB-UX.ps1" -Verbose

────────────────────────────────────────────────────────────────
РАЗДЕЛ D — Сборка и выпуск

D1. Сборка MSI (WiX Toolset)
cd C:\AI\SmartPOS\USB_smart_standalone
# Компиляция .wxs (требуется WixUtilExtension)
candle.exe installer\wix\SmartPOS_USB_Agent.wxs -ext WixUtilExtension -out build\SmartPOS_USB_Agent.wixobj
# Линковка MSI
light.exe build\SmartPOS_USB_Agent.wixobj -ext WixUtilExtension -o dist\SmartPOS_USB_Agent_v1.4.1.msi

D2. Сборка EXE (Inno Setup)
# Откройте installer\inno\SmartPOS_USB_Agent.iss в Inno Setup Compiler и соберите
# либо командой ISCC (если установлена):
ISCC.exe installer\inno\SmartPOS_USB_Agent.iss

D3. Сборка релизного ZIP + SHA256
cd C:\AI\SmartPOS\USB_smart_standalone\tools
powershell -ExecutionPolicy Bypass -File .\make_release_zip.ps1 -Version 1.4.1
# Результат:
# dist\SmartPOS_USB_Agent_v1.4.1.zip
# dist\SmartPOS_USB_Agent_v1.4.1.zip.sha256.txt

D4. Проверка SHA256 вручную (альтернатива)
Get-FileHash -Path .\dist\SmartPOS_USB_Agent_v1.4.1.zip -Algorithm SHA256

D5. Проверка и нормализация Inno .iss (по месту)
# создать скрипт проверки
$dst='tools\Test-InnoIss.ps1'; New-Item -ItemType Directory -Path (Split-Path $dst) -Force | Out-Null
@'
param([string]$IssPath='installer\inno\SmartPOS_USB_Agent.iss')
$ErrorActionPreference='Stop'
$txt=Get-Content -Raw -Path $IssPath -Encoding UTF8
$checks=@(
  @{Name='Version';     Ok=($txt -match '#define\s+AppVersion\s+"1\.4\.1"')},
  @{Name='AppName';     Ok=($txt -match '#define\s+AppName\s+"SmartPOS USB Agent"')},
  @{Name='DirName';     Ok=($txt -match 'DefaultDirName=\{pf\}\\SmartPOS_USB_Agent')},
  @{Name='NoEllipsis';  Ok=(-not ($txt -match '\.\.\.'))},
  @{Name='SingleRun';   Ok=(($txt -split '\[Run\]').Count -le 2)},
  @{Name='HasCLI';      Ok=($txt -match 'usb_devctl_cli\.py')},
  @{Name='HasService';  Ok=($txt -match 'smartpos_usb_service_v14\.py')},
  @{Name='HasCore';     Ok=($txt -match 'usb_agent_core\.py')},
  @{Name='HasTrace';    Ok=($txt -match 'trace_wrappers_v2\.py')},
  @{Name='HasScripts';  Ok=($txt -match 'install_service\.ps1') -and ($txt -match 'uninstall_service\.ps1')},
  @{Name='HasWatchdog'; Ok=($txt -match 'install_watchdog\.ps1') -and ($txt -match 'uninstall_watchdog\.ps1')},
  @{Name='NoTray';      Ok=(-not ($txt -match 'SmartPOS\.UsbTray\.exe'))},
  @{Name='ApiKeyDlg';   Ok=($txt -match "CreateInputQueryPage\(wpSelectDir,\s*'API Key'")},
  @{Name='ConfigSave';  Ok=($txt -match '\{commonappdata\}\\SmartPOS\\usb_agent\\config\.json')},
  @{Name='RunPS';       Ok=($txt -match 'powershell\.exe";\s*Parameters:\s*"-ExecutionPolicy Bypass -File ""\{app\}\\installer\\scripts\\install_service\.ps1""') -and ($txt -match 'powershell\.exe";\s*Parameters:\s*"-ExecutionPolicy Bypass -File ""\{app\}\\tools\\install_watchdog\.ps1""')}
)
$failed=$checks|?{ -not $_.Ok }
if($failed){ "FAILED checks:`n - " + (($failed|%{$_.Name}) -join "`n - ") } else { "OK: ISS looks correct for v1.4.1" }
'@ | Set-Content -Path $dst -Encoding UTF8 -Force

# запуск проверки
powershell -ExecutionPolicy Bypass -File .\tools\Test-InnoIss.ps1 -IssPath .\installer\inno\SmartPOS_USB_Agent.iss

────────────────────────────────────────────────────────────────
РАЗДЕЛ E — Траблшутинг

E1. API не отвечает: убедитесь, что служба запущена (sc query SmartPOS_USB_Service). Проверьте порт 8731 не занят другим процессом.

Если порт 8731 занят: netstat -ano | findstr :8731
# Завершите конфликтующий PID или перенастройте порт сервиса (если поддерживается конфигом)

E2. Нет Event Log записей watchdog
- Возможно, не удалось зарегистрировать Source (нет прав) — не критично, сервис и watchdog всё равно работают..

E3. Конфиг не создаётся при установке
- Проверьте права администратора и наличие записи в `%ProgramData%\SmartPOS\usb_agent\config.json`.

E4. Ошибка MSI при Custom Action (тихий выход)
- Убедитесь, что PowerShell разрешает выполнение (`-ExecutionPolicy Bypass`), и скрипты доступны по путям из `%ProgramFiles%\SmartPOS_USB_Agent`.

E5. Экспорт HTTP падает
- используйте локальный режим (—local), проверьте права на путь вывода.

E6. Watchdog не создаётся
- перезапустите PowerShell от администратора, проверьте, что нет политики запрета задач.

Версия документа: 1.4.1  02.10.25 (cheatsheet full)
