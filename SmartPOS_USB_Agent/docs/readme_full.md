# SmartPOS USB Agent — README (полный)
Автор: Разработчик суперпрограмм  
Версия пакета: 1.4 (октябрь 2025)

> Этот документ суммирует всю работу из текущей сессии: общая концепция, архитектура, реализованные модули, инсталляторы, конфигурация, команды запуска/тестирования, отладка, безопасность, edge‑cases и дорожная карта. Всё описанное ниже отражено в файлах на канвасе.

---
## 0) Бизнес‑контекст и цели
Рабочее место кассира на POS‑ПК должно **непрерывно** принимать заказы и платежи. Основные риски связаны с USB‑периферией: фискальные регистраторы, дисплеи покупателя, сканеры штрих‑кодов. По опросам клиентов, приоритетны:
- Автоматическое **отключение/перезапуск USB‑портов** и сервисов при сбоях;
- Диагностика **отключений/отвалов** USB‑устройств;
- Постоянный **контроль связности** с фискальником, дисплеем, сканером;
- Быстрый **экспорт артефактов** (БД, логи, трассировки) для техподдержки;
- Простое локальное управление через **трей‑утилиту**.

**TOP‑5 сценариев** первой очереди (реализованы):
1. Health‑пробы устройств + автоматическое восстановление (перезапуск устройства/службы) с бэкоффом.
2. Диагностика присутствия устройства на шине и фиксация событий в БД.
3. Управление из трея: статус, Preflight, ручной recycle, экспорт ZIP.
4. Экспорт с маской (`db,logs,traces`) для быстрой эскалации.
5. Tracing COM/HID c квотой/ротацией для воспроизводимости инцидентов.

---
## 1) Архитектура (логическая и программная)
### Логическая схема
- **Orchestrator**: хранит состояние устройств, запускает периодические health‑пробы, принимает решения о восстановлении (recycle USB / restart service) согласно политике.
- **AdapterRegistry** (из `usb_agent_core.py`): абстрагирует работы с устройствами/сервисами/шиной.
- **CompositeHealthProbe**: нормализует быстрые проверки ответа от устройств (по COM/HID/сервисам).
- **ActionDeviceControl / ActionServiceControl**: исполняют выбранные действия (рециклы/рестарты) с тихим окном.
- **HTTP API (loopback)**: локальный REST для статуса, префлайта, действий и экспорта.
- **Tray**: человеко‑машинный интерфейс кассира/инженера (статус/действия/экспорт).
- **Хранилище**: SQLite (журналирование метрик/действий), ежедневная ретеншн‑очистка и «скользящее окно» по размеру.
- **Tracing**: неблокирующая запись сырых COM/HID потоков с ротацией и квотой каталога.

### Программные блоки
- `smartpos_usb_service_v14.py` — агент/служба + HTTP API **v1.4**;
- `usb_agent_core.py` — ядро адаптеров (дано из вложения, совместимо);
- `trace_wrappers_v2.py` — обёртки трассировки COM/HID (квоты/фильтры/ротация);
- **Tray (.NET WinForms)**: `SmartPOS.UsbTray` (проект C#) — предпочтительный трей‑клиент;
- **Tray (PowerShell)**: `SmartPOS_USB_Tray_v2.ps1` — лёгкий совместимый вариант;
- **Инсталляторы**: Inno Setup (`Installer/SmartPOS_USB_Agent_Installer_v2_sanity.iss`) и WiX (`installer/SmartPOS_USB_Agent_v2_sanity.wxs`);
- **Примеры/README**: `examples_pack/README_and_samples.txt` (содержит примеры `config.json`, `devices.json`, генераторы иконки и трасс);
- **Тесты (ручной набор)**: `tests/hand_tests.md`;
- **Памятка для поддержки**: `ops/README_ops_short.md`;
- **Watchdog**: `tools/install_watchdog.ps1`, `tools/uninstall_watchdog.ps1`.

---
## 2) Структура проекта (рекомендуемая)

```
./
├── dist/
├── docs/
│ ├── API-ключи.docx
│ ├── config-json-структура и настройки.docx
│ ├── Examples Pack_readme And Samples.docx
│ ├── Pack_build Zip Guide.pdf
│ ├── Poller - альтернативы по подписке.docx
│ ├── Readme Cashiers Pos Quick Aid.docx
│ ├── Readme Engineers Usb Dev Ctl.docx
│ ├── Readme Full.pdf
│ ├── readme_full.md
│ ├── Smart Pos Usb Agent V1.4.docx
│ ├── Smart Pos Usb Pilot Package.docx
│ ├── Smart Pos Usb Reliability Architecture V1 (концепт).docx
│ ├── Tests_hand Tests.docx
│ ├── Проверки работы Watchdog.docx
│ └── ops/
│ ├── README_ops_short.docx
│ └── README_ops_short.md
│
├── examples_pack/
│ └── examples_pack_readme_and_samples.md        # примеры config/devices/логи/трассы
│
├── installer/
│ ├── assets/
│ │ └── SmartPOS_USB_Agent.ico.txt
│ ├── inno/
│ │ └── SmartPOS_USB_Agent.iss                   # Inno Setup (санити‑чеки)
│ ├── scripts/
│ │ ├── install_service.ps1
│ │ └── uninstall_service.ps1
│ └── wix/
│ └── SmartPOS_USB_Agent.wxs                     # WiX MSI (санити‑чеки)
│
├── src/
│ ├── dotnet/SmartPOS.UsbTray/                   # .NET WinForms трей
│ │ ├── smart_pos_usb_tray.txt
│ │ ├── smart_pos_usb_tray3.txt
│ │ ├── smart_pos_usb_tray4.txt
│ │ ├── smart_pos_usb_tray_program.cs
│ │ ├── smart_pos_usb_tray_smart_pos_usb_tray.txt
│ │ ├── smart_pos_usb_tray_v_2.txt
│ │ └── smart_pos_usb_tray_win_forms.cs
│ └── python/
│ ├── run_usb_devctl.bat
│ ├── smartpos_usb_service_v14.py                # служба + HTTP API (loopback)
│ ├── trace_wrappers_v2.py                       # трассировка COM/HID (квоты/фильтры)
│ ├── usb_agent_core.py                          # ядро адаптеров (из вложения)
│ ├── usb_agent_smoketests.py
│ ├── usb_devctl_cli.py
│ ├── db/
│ │ ├── smartpos_usb.db
│ │ ├── smartpos_usb.db-shm
│ │ ├── smartpos_usb.db-wal
│ │ └── smartpos_usb.db.bak_YYYYMMDD_HHMMSS
│ ├── helpers/init.py
│ ├── logs/service.log
│ └── pycache/
│
├── tests/
│ ├── test_cli_export_smoke.py
│ ├── test_config_and_hot_reload.py
│ ├── test_export_zip_mask.py
│ ├── test_sqlite_retention.py
│ └── usb_agent_autotests.py
│
└── tools/
├── install_watchdog.ps1
├── make_release_zip.ps1
├── Test-InnoIss.ps1
├── uninstall_watchdog.ps1
└── ux/
├── config.json
├── service_name_map.json
└── SmartPOS-USB-UX.ps1оматически
```

> Примечание: актуальная структура должна также поддерживать требования эталона и обновляться в паре с `structure.md` при изменениях. :contentReference[oaicite:0]{index=0}

---
## 3) Конфигурация (`config.json`)
Пример базовой конфигурации (см. также `examples_pack/README_and_samples.txt`):

```json
{
  "http": "127.0.0.1:8765",
  "auth": { "shared_secret": "changeme-please" },
  "db": {
    "retention_days": 14,
    "max_mb": 20,
    "vacuum_on_start": true,
    "size_batch": 2000
  },
  "policy": {
    "probe_timeout_ms": 1500,
    "probe_interval_s": 10,
    "fail_threshold": 3,
    "device_recycle_backoff_base_s": 5,
    "device_recycle_backoff_max_s": 180,
    "quiet_window_ms": 5000,
    "role_overrides": {
      "fiscal":  { "probe_interval_s": 7,  "fail_threshold": 2, "service_first": true },
      "scanner": { "probe_interval_s": 12, "fail_threshold": 3 },
      "display": { "probe_interval_s": 15, "fail_threshold": 3 }
    },
    "traces": {
      "enabled": true,
      "dir": "traces",
      "max_dir_mb": 50,
      "file_rotate_kb": 1024,
      "filter": {
        "include_ports": [],
        "exclude_ports": [],
        "include_vidpid": [],
        "exclude_vidpid": []
      }
    }
  }
}
```

**Авторизация:** если `auth.shared_secret` непустой, все `POST` требуют заголовок `X-API-Key`.  
**HTTP Bind:** только `127.0.0.1` (локальный доступ) для снижения поверхности атаки.

---
## 4) Служба/агент (`smartpos_usb_service_v14.py`)
### Назначение
- Поддерживает инвентарь USB‑устройств (по `devices.json`), периодические проверки доступности, стратегию восстановления.
- Логирует метрики и действия в SQLite (`db/smartpos_usb.db`) со схемой:
  - `devices(device_id, vid, pid, friendly, role, critical, hub_path, com_port)`
  - `metrics(ts, device_id, state, rtt_ms, err_code)`
  - `actions(ts, device_id, action, ok, detail)`
  - `preflight_runs(ts, overall)`
- Управляет **ретеншном** по дням и **окном по размеру** (MB) с `VACUUM` при необходимости.

### Трассировки
Подключает `trace_wrappers_v2`:
- **COM**: перехват `read()/write()`, файлы `traces/COM_TX_*.bin` и `traces/COM_RX_*.bin`
- **HID**: duck‑typing обёртка `TracedHidActivity`: `send/report → HID_TX_*`, `read/get_report → HID_RX_*`
- Квоты и ротация: `policy.traces.max_dir_mb` и `file_rotate_kb`
- Фильтры: `filter.include_ports/exclude_ports`, `filter.include_vidpid/exclude_vidpid`

### HTTP API (loopback)
- `GET  /api/status` — снимок состояния устройств
- `POST /api/preflight` — разовая проверка всех устройств (суммарный статус пишется в `preflight_runs`)
- `POST /api/action/device/{id}/recycle` — ручной recycle USB‑устройства
- `POST /api/action/service/{id}/restart` — перезапуск связанной службы (если определена политикой)
- `POST /api/policy/reload` — горячая подгрузка `policy` из `config.json`
- `POST /api/export?mask=db,logs,traces` — ZIP с выбранными артефактами

**Защита:** все `POST` требуют `X-API-Key`, если ключ задан; доступ только с `127.0.0.1`.

### Запуск
- Консоль: `python smartpos_usb_service_v14.py --console`
- Служба (pywin32): `python smartpos_usb_service_v14.py --service install|start|stop|remove`
- Переопределить порт (при разработке): `python smartpos_usb_service_v14.py --console --http 127.0.0.1:9999`

---
## 5) Трей‑клиенты (пока не используется)
### .NET WinForms (рекомендуется) — `SmartPOS.UsbTray`
- Меню: **Статус**, **Проверить (Preflight)**, **Восстановить выбранное…**, **Сохранить отчёт (ZIP)**, Выход.
- Отображает общий индикатор (зелёный/жёлтый/красный) по `/api/status`.
- Читает ключ из переменной окружения `SMARTPOS_USB_APIKEY` (если не пустой — добавляется в `POST`).
- Сборка: `dotnet publish SmartPOS.UsbTray/SmartPOS.UsbTray.csproj -c Release -r win-x64 --self-contained false`

### PowerShell (альтернативно) — `SmartPOS_USB_Tray_v2.ps1`
- Те же действия и экспорт ZIP в `~/Downloads/smartpos_usb_export.zip`.
- Добавляет `X-API-Key` при наличии.

---
## 6) Инсталляторы и развёртывание — уточнение путей и требований
- Проверяет наличие **Python 3.9+ (x64)** и **.NET Desktop Runtime**.
- Кладёт службу v1.4, `usb_agent_core.py`, `trace_wrappers_v2.py`, и **SmartPOS.UsbTray.exe**.
- Создаёт `db/`, `logs/`, `traces/`.
- Регистрация службы через `installer/scripts/install_service.ps1` (pywin32), fallback — Планировщик.
- Автозапуск трея через `HKCU\...\Run`.

- Добавьте в [Files] `src\python\run_usb_devctl.bat` и ярлык в [Icons].
- В [Run] ровно 2 строки: PowerShell-установка службы и watchdog.
- Диалог ввода **API Key** должен писать ключ в `%ProgramData%\SmartPOS\usb_agent\config.json` (валидный JSON).  
Проверки и шаги деплоя — по deployment checklist. :contentReference[oaicite:3]{index=3}

### WiX (`installer/wix/SmartPOS_USB_Agent.wxs`)
- `<File Source="..\..\src\python\run_usb_devctl.bat" .../>`, `<ComponentRef Id="cmpRunBat"/>`, ярлык на BAT.
- Сборка `candle/light` с `-ext WixUtilExtension`.

### WiX MSI — `installer/SmartPOS_USB_Agent_v2_sanity.wxs`
- AppSearch по реестру (.NET Desktop Runtime x64, Python 3.9+ x64); LaunchCondition блокирует установку при отсутствии.
- Кладёт те же файлы, настраивает автозапуск EXE‑трея.

### Watchdog (опционально)
- Установка: `powershell -ExecutionPolicy Bypass -File tools/install_watchdog.ps1 -AppDir <путь> -IntervalMinutes 2`
- Удаление: `powershell -ExecutionPolicy Bypass -File tools/uninstall_watchdog.ps1`
- Логика: периодически пингует `/api/status`, пытается стартовать службу, при неуспехе — поднимает агента в консоли.

---
## 7) Примеры данных и генераторы
Всё собрано в `examples_pack/README_and_samples.txt`:
- **`config.json`** — безопасные дефолты + `policy.traces`;
- **`devices.json`** — 3 устройства (fiscal/scanner/display) с тестовыми VID:PID/COM;
- **`tools/make_app_ico.ps1`** — генерация минималистичного `app.ico` (16×16);
- **`logs/service.log`** — образец логов;
- **`tools/make_sample_traces.py`** — генерация файлов в `traces/` (COM/HID).

---
## 8) Тестирование (ручной sanity pack)
Полный сценарий — см. `tests/hand_tests.md`. Ключевые команды:

```bash
# статус
curl http://127.0.0.1:8765/api/status
# префлайт
curl -X POST -H "X-API-Key: <ключ>" http://127.0.0.1:8765/api/preflight
# ручной recycle
curl -X POST -H "X-API-Key: <ключ>" "http://127.0.0.1:8765/api/action/device/<url-encoded-id>/recycle"
# экспорт
curl -X POST -H "X-API-Key: <ключ>" -o smartpos_usb_export.zip "http://127.0.0.1:8765/api/export?mask=db,logs,traces"
```

## Тестирование

### Быстрый прогон (PowerShell)

```powershell
cd C:\AI\Repo\smartpos-knowledge-usb\SmartPOS_USB_Agent
New-Item -Type Directory -Force dist | Out-Null
$env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"
python -m pytest --% -q -rA --maxfail=1 --disable-warnings -o log_cli=true -o log_cli_level=INFO --junitxml=dist\pytest-report.xml
```
  
Точечные запуски

```powershell
pytest -q tests\test_sqlite_retention.py
pytest -q tests\test_export_zip_mask.py
pytest -q tests\test_config_and_hot_reload.py
pytest -q tests\test_cli_export_smoke.py
pytest -q tests\usb_agent_autotests.py
```

Ожидаемый результат: код возврата 0, все тесты PASSED.
Артефакты CI: dist\pytest-report.xml.

RU/EN logs включены (log_cli=true). При ошибках приложите traceback и содержимое последних строк логов.

### Ожидаемые точки отказа и план починки по тестам

Документ `docs\tests_expected_fails_and_repair.md`  описывает **5 тестовых направлений** (модули и сценарии), типичные причины падений на Windows
(в т.ч. IoT/LTSC), а также детальные шаги локализации и исправлений. Материал предназначен для оперативной диагностики
(«что делать, если тест покраснел»), обеспечения оффлайн‑устойчивости и выполнения ограничений по pybox/stdlib.

---

## Рекомендации по добивке `usb_agent_autotests.py`
- Добавить smoke-кейсы: `import` ключевых модулей, проверка `--help` `run_usb_devctl.bat`/CLI, проверка наличия `%ProgramData%\SmartPOS\usb_agent\config.json` (мок/временная папка), формат логов.
- Все вызовы подпроцессов — без `shell=True`, аргументы списком.

---

Готов двигаться к п.3 «Инсталляторы». Если ок, дам диффы для Inno (`[Files]/[Icons]/[Run]`) и WiX (`<File/

### Юнит- и интеграционные тесты
- Минимальный набор в репозитории:
  - `tests/test_sqlite_retention.py`
  - `tests/test_export_zip_mask.py`
  - `tests/test_config_and_hot_reload.py`
  - `tests/test_cli_export_smoke.py`
  - `tests/usb_agent_autotests.py`
- Запуск: `python -m pytest -q` → **ожидаемый код возврата 0**.  
или

```powershell
cd C:\AI\Repo\smartpos-knowledge-usb\SmartPOS_USB_Agent
New-Item -Type Directory -Force dist | Out-Null
$env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"
python -m pytest -q -rA --maxfail=1 --disable-warnings -o log_cli=true -o log_cli_level=INFO --junitxml="dist\pytest-report.xml"
```

- При релизе сохраняйте артефакт `junit.xml` (по необходимости).  
- Автотест-скелет `usb_agent_autotests.py` описан в соответствующем разделе README. :contentReference[oaicite:4]{index=4}

### SmartPOS USB Agent — Smoke Checklist после инсталляции
из корня SmartPOS_USB_Agent либо с явным путём установки:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\checklist_install_smoke.ps1
# либо явно указать путь установки
powershell -ExecutionPolicy Bypass -File .\tools\checklist_install_smoke.ps1 -AppDir "C:\Program Files\SmartPOS_USB_Agent"
```

#### Параметры:
-ZipOut "<path>" — куда складывать ZIP из --selftest (если не задан, создаётся во временной папке).
-NoEventLog — пропустить проверку журнала событий.
-Verbose — подробный вывод (например, конечный путь ZIP).
Он проверяет:
- наличие run_usb_devctl.bat;
- валидность %ProgramData%\SmartPOS\usb_agent\config.json;
- --help и --selftest у BAT (с таймаутами);
- статус службы SmartPOS_USB_Agent (и StartType=Automatic);
- записи в Application Event Log (провайдер SmartPOS_USB_Agent).

#### Настраиваемые имена службы и источника событий:
-ServiceName - имя службы для проверки
-EventSource - источник событий в журнале
#### Проверка после ребута:
-SinceBoot - фильтрует события только после последнего ребута
Добавляет проверку "Service Running after reboot"
#### Проверка Watchdog:
-CheckWatchdog - проверяет наличие событий WatchdogPing
#### Отдельная проверка "EventLog WatchdogPing"
Улучшенная фильтрация событий:
Функция Get-LastBootTime() для определения времени ребута
Фильтрация по времени и типу событий
Поиск событий ServiceStarted и WatchdogPing

Выводит PASS/FAIL по каждому пункту и завершает с кодом 0 при успехе, 1 — если что-то упало.
Сообщения двуязычные (RU/EN), без требований admin и без внешних модулей.

Примеры использования:
- Базовая проверка
.\checklist_install_smoke.ps1

- Проверка с Watchdog
.\checklist_install_smoke.ps1 -CheckWatchdog

- Проверка после ребута
.\checklist_install_smoke.ps1 -SinceBoot

- Полная проверка
.\checklist_install_smoke.ps1 -SinceBoot -CheckWatchdog -Verbose

- С настройкой имен
.\checklist_install_smoke.ps1 -ServiceName "MyService" -EventSource "MyApp"
Результат:
Скрипт теперь предоставляет более детальную диагностику установки и работы SmartPOS USB Agent, включая проверки службы,
событий и watchdog функциональности!

---
## 9) Инженерные утилиты - UX-скрипт (инженерный): `tools/ux/SmartPOS-USB-UX.ps1`

Интерактивная PowerShell-оболочка для инженеров/саппорта: статус службы/API, preflight, policy-reload, рестарт сервиса, экспорт ZIP, быстрые SQL-счётчики БД и «хвост» логов.
(цветные статусы, меню, обёртка над CLI, проверка Python/админ-прав, поиск service_name_map.json).
Его не стоит ставить на кассы через MSI — держим как инженерный инструмент в репозитории и релизном ZIP.
Ключевые функции и параметры скрипта — в исходнике: подсветка, меню, поиск конфигов, вызовы usb_devctl_cli.py (status, recycle, service-restart, dump-sample-config) и т.д.

- **Не ставится** через MSI/EXE, хранится в релизном ZIP как инженерный инструмент.
- **Требования:** PowerShell, запуск с повышенными правами.
- **Запуск:**
  
  ```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  powershell -NoLogo -ExecutionPolicy Bypass -File ".\tools\ux\SmartPOS-USB-UX.ps1" -Verbose

Для быстрой диагностики агента используйте интерактивный PowerShell-скрипт из релизного ZIP:
- Расположение: tools\ux\SmartPOS-USB-UX.ps1  (в MSI/EXE не устанавливается)
- Назначение: статус службы/API, preflight, policy-reload, service-restart, export-zip, подсветка ошибок
- Требования: права администратора, PowerShell доступен

Запуск (из корня распакованного пакета/репозитория):
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  powershell -NoLogo -ExecutionPolicy Bypass -File ".\tools\ux\SmartPOS-USB-UX.ps1" -Verbose

Быстрые операции:
Status (GET /api/status), Preflight (POST /api/preflight), Policy Reload (POST /api/policy/reload), Service Restart (API → fallback sc.exe), Export ZIP (POST /api/export?mask=...).
- Status → проверка службы SmartPOS_USB_Service и GET /api/status
- Policy Reload → POST /api/policy/reload
- Service Restart → рестарт через API, затем fallback sc.exe
- Export ZIP → сбор логов/трасс по маске
Стандарты вывода: двухъязычные сообщения RU/EN, явное логирование путей и проверок (см. стиль скриптов).

Примечание: UX-скрипт не предназначен для постоянной установки на POS-кассы; хранится в ZIP для инженеров/саппорта.

---

```
### CLI и ярлык: `src/python/run_usb_devctl.bat

Для вызова типовых действий используйте **BAT-обёртку** (без установки Python в системе клиента):

```bat
:: Примеры
run_usb_devctl.bat status
run_usb_devctl.bat preflight
run_usb_devctl.bat export db,logs,traces
run_usb_devctl.bat service-restart
& "$env:ProgramFiles\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" --help
& "$env:ProgramFiles\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" --selftest --out "$env:TEMP\spusb_out.zip"
```

В примерах и документах замените вызовы python ...usb_devctl_cli.py на run_usb_devctl.bat. Python-вариант оставляем как альтернативу в examples_pack.
---

## 10) Безопасность и ресурсы
- **Поверхность API**: только loopback (`127.0.0.1`).
- **Auth**: `X-API-Key` на всех `POST` при заданном `auth.shared_secret`.
- **Защита диска**: квота `traces` (MB) + ротация файлов; БД — ретеншн + «скользящее окно» + `VACUUM`.
- **Отказоустойчивость**: ошибки записи трасс игнорируются (не мешают работе кассы); fallback‑запуск агента через Планировщик.

- Нормы оформления скриптов (.py/.ps1/.bat):
> Все новые или изменённые скрипты обязаны соответствовать единому стилю SmartPOS: двуязычные сообщения, явные проверки путей и прав,
> лог-файлы создаются всегда, отказоустойчивость и fallback-поведение. См. «Стиль кода и политика обработки скриптов».

---
## 11) Edge‑cases, которые учтены
- Отсутствие/повреждение `config.json`/`devices.json` — используются дефолты, логируются предупреждения.
- Пустой API‑ключ — `POST` без заголовка работают.
- Превышение квоты `traces/` — удаление старейших файлов; при невозможности — запись пропускается.
- Переполнение БД — пакетное удаление самых старых метрик/действий до целевого размера.
- Устройства временно отсутствуют на шине — состояния `DEGRADED/FAILED` + обратимые попытки восстановления.

---
## 12) Дорожная карта (опционально)
- HID‑транспорт «родной» (вместо duck‑typing) при появлении API в `usb_agent_core`.
- Диалог ввода API‑ключа в MSI/EXE (post‑install) и запись в `config.json`.
- Подпись EXE/MSI (codesign).
- Расширенные отчёты: мини‑дамп состояния Windows USB Topology (по флагу).

---
## 13) Быстрый старт (для пилота)
1. Положить в одну папку: `smartpos_usb_service_v14.py`, `usb_agent_core.py`, `trace_wrappers_v2.py`, `config.json`, `devices.json`, `SmartPOS.UsbTray.exe` (или использовать PowerShell‑трей), `app.ico` (необязательно).
2. Запустить службу в консоли: `python smartpos_usb_service_v14.py --console`.
3. Запустить трей EXE: двойной клик по `SmartPOS.UsbTray.exe`.
4. Проверить `GET /api/status` и выполнить `Preflight`.
5. Выгрузить ZIP («Сохранить отчёт (ZIP)») и убедиться, что в архиве есть `db/`, `logs/`, `traces/`.

---
## 14)Автотесты агента: `usb_agent_autotests.py`

**Назначение.** Лёгкий, полностью самодостаточный каркас автотестов под `pytest`, покрывающий 5 ключевых сценариев оркестратора USB-агента и негативные кейсы. Используются фейковые адаптеры/реестр/пробер и упрощённая модель времени, что позволяет гонять тесты оффлайн, без доступа к железу и без сторонних зависимостей.

> Примечание: в шапке файла встречается имя `usb_agent_autotests_scaffold.py`, фактическое имя — `usb_agent_autotests.py`.

### Что проверяет

1. **Автовосстановление “повисшего” устройства**: порог таймаутов → перезапуск профильной службы (для `role=fiscal` приоритизируется `service_first`) → при необходимости `device_recycle`.
2. **Обрыв устройства (disconnect)**: корректная деградация статуса (`FAILED/DEGRADED`), открытие инцидента с `hint=possible_cable`.
3. **Контроль канала с фискальником**: очередность действий при повторных таймаутах (сервис → recycle) и возврат в `READY`.
4. **Пре-флайт-последовательность (упрощённо)**: кратковременный флап и закрытие инцидента после стабилизации.
5. **USB-шторм/питание**: рост `backoff` для повторных `recycle`, анти-флаппинг.

**Негативные/edge-кейсы**

- Нет прав/ошибка драйвера на `recycle` → корректная деградация состояния.
- Изменение `COM` после `recycle` (ренумерация) → фиксация нового порта.
- Валидация конверта сообщений `make_envelope(...)` (форма полей).

### Внутренности файла (кратко)

- **Модели и политика**: `DeviceRecord`, `Policy` (в т.ч. `role_overrides`), `DeviceRuntime`.
- **Фейки инфраструктуры**: `FakeClock`, `FakeHealthProbe`, `FakeServiceControl`, `FakeDeviceControl`, `FakeTopology`.
- **Оркестратор**: простая `state-machine` с инцидентами и приоритетом действий (service vs recycle), уважение `quiet_window_ms` и экспоненциальный `backoff`.
- **Каталог health-проб (концепт v1)**: уровни `TP/DP/AP`, единый формат результата, таблицы для ролей `fiscal/scanner/display`, эскалация и маппинг кодов ошибок → `hint`/действие.
- **Адаптеры v1**: `fiscal.generic_escpos`, `scanner.hid_keyboard`, `display.cd5220` + транспортные фейки `FakeCom/FakeSvc/FakeHid`, реестр адаптеров и композитный пробер `CompositeHealthProbe`.

### Ограничения среды и совместимость

- Совместимо с pybox-ограничениями: **без** `multiprocessing`, внешней сети, shell-вызовов; только стандартная библиотека.
- Тесты не трогают реальный Windows/драйверы/службы — всё через фейки; это **юнит/интеграционные** проверки логики оркестрации.

### Как запускать

```bash
# точечный прогон файла
pytest -q usb_agent_autotests.py

# или общий прогон репозитория
python -m pytest -q
```

**Ожидание:** код возврата 0 при зелёных тестах; для CI можно сохранять `junit.xml`.

### Как расширять

- Добавляйте сценарии в духе существующих (`make_stand()`, `advance(...)`, скриптуемые ответы `probe.set_script(...)`).
- Для новых ролей/моделей — реализуйте лёгкий адаптер (TP/DP/AP) и зарегистрируйте в `AdapterRegistry`.
- Негативные кейсы: мусорные ответы, несоответствие кодировок, долгие RTT, нестабильная топология (`present_map`).

### Критерии готовности (для релиза)

- Все 5 сценариев и edge-кейсы зелёные.
- Поведение оркестратора соответствует политике ролей (`fail_threshold`, `service_first`, `device_recycle_*`, `quiet_window_ms`).
- Логи тестов информативны; в README зафиксированы команды запуска и область покрытия.

## 15)Сборка релиза и хеш
- Команда:

```powershell
cd C:\AI\Repo\smartpos-knowledge-usb\SmartPOS_USB_Agent
powershell -ExecutionPolicy Bypass -File .\tools\make_release_zip.ps1 -Version 1.4.1
```

- Результат ожидаем: `.\dist\SmartPOS_USB_Agent_v1.4.1.zip` + `.\dist\SmartPOS_USB_Agent_v1.4.1.zip.sha256.txt`
- Включите в отчёт: список вошедших файлов по каталогам, результаты автотестов/ручных сценариев, SHA256 архива.  
Смотрите deployment checklist и общий dev-чеклист для релиза. :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6}

Проверка SHA256 вручную (если нужно):

```powershell
Get-FileHash .\dist\SmartPOS_USB_Agent_v1.4.1.zip -Algorithm SHA256 |
  ForEach-Object { "$($_.Hash)  SmartPOS_USB_Agent_v1.4.1.zip" } |
  Set-Content .\dist\SmartPOS_USB_Agent_v1.4.1.zip.sha256.txt -Encoding ASCII
Get-Content .\dist\SmartPOS_USB_Agent_v1.4.1.zip.sha256.txt
```

## 16) Благодарности и заметки для команды
- `usb_agent_core.py` — используем вашу копию «как есть» из вложения пользователя.
- Все новые артефакты создавались с ориентацией на слабые POS‑ПК: минимум зависимостей, отсутствие тяжёлых фоновых задач, терпимость к сбоям I/O.
- Любые расхождения/пожелания по ролям устройств, интервалам, стратегиям восстановления — правятся через `config.json` без рестарта (через `/api/policy/reload`).

---
## 17) Контакт и сопровождение
Для интеграции/релиза запросите:
- минимально поддерживаемую версию Windows (x64),
- финальную иконку/брендинг,
- план по codesign.

Готов оперативно доработать: MSI‑диалоги, проверку .NET Desktop Runtime автоскачкой, расширенную диагностику HID, и т.д.
