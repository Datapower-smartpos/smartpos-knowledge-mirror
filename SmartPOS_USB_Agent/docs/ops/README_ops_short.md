# SmartPOS USB — памятка для техподдержки (короткая)

## Что собирать при обращении

**Минимальный пакет:**

- ZIP-отчёт из трея: «Сохранить отчёт (ZIP)» → `smartpos_usb_export.zip`  
  (внутри: `db/`, `logs/`, `traces/` по маске)
- Снимок статуса: результат `GET http://127.0.0.1:8765/api/status` в файл
- Версии окружения:
  - `python --version`
  - `dotnet --list-runtimes`
  - `wmic os get caption,version` или `winver`

## Как включить трассировки

Открыть `config.json`, поставить:

```json
"policy": {
  "traces": {
    "enabled": true
  }
}
```

(Опционально) ограничить объём:

```json
"max_dir_mb": 50,
"file_rotate_kb": 1024
```

Применить без перезапуска:

```bash
curl -X POST http://127.0.0.1:8765/api/policy/reload
```

## Как выгрузить

**Через трей:** «Сохранить отчёт (ZIP)» — файл появится в «Загрузки».

**Через API:**

```bash
curl -X POST -H "X-API-Key: <ключ>" -o smartpos_usb_export.zip "http://127.0.0.1:8765/api/export?mask=db,logs,traces"
```

## Частые проблемы

- **401 Unauthorized:** Нужен заголовок `X-API-Key`. Ключ лежит в `config.json` → `auth.shared_secret`.
- **Служба не отвечает:** перезапустить службу Windows **SmartPOS USB Agent**, либо
  
```bash
  python smartpos_usb_service_v14.py --console
  ```

- **Не растут трассы:** проверьте `policy.traces.enabled`, квоту каталога, фильтры `include_ports` / `include_vidpid`.

## Полезные пути

- БД: `./db/smartpos_usb.db`
- Логи: `./logs/*.log`
- Трассы: `./traces/*.bin`
- Трей EXE: `SmartPOS.UsbTray.exe`

## Контрольная команда (быстрый тест)

```bash
curl -X POST -H "X-API-Key: <ключ>" http://127.0.0.1:8765/api/preflight
```

Должно вернуть пример вида:

```json
{ "ok": true, "...": "..." }
```

и создать запись в БД `preflight_runs`.

## Диагностика (инженерный UX-скрипт)

Для быстрой диагностики агента используйте интерактивный PowerShell-скрипт из релизного ZIP:
- Расположение: tools\ux\SmartPOS-USB-UX.ps1  (в MSI/EXE не устанавливается)
- Назначение: статус службы/API, preflight, policy-reload, service-restart, export-zip, подсветка ошибок
- Требования: права администратора, PowerShell доступен

Запуск (из корня распакованного пакета/репозитория):
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  powershell -NoLogo -ExecutionPolicy Bypass -File ".\tools\ux\SmartPOS-USB-UX.ps1" -Verbose # детальные логи
  
```
powershell -NoLogo -ExecutionPolicy Bypass -File ".\tools\ux\SmartPOS-USB-UX.ps1"  # меню (при запуске без опций)
```

Быстрые операции:
- Status → проверка службы SmartPOS_USB_Service и GET /api/status
- Policy Reload → POST /api/policy/reload
- Service Restart → рестарт через API, затем fallback sc.exe
- Export ZIP → сбор логов/трасс по маске

Примечание: UX-скрипт не предназначен для постоянной установки на POS-кассы; хранится в ZIP для инженеров/саппорта.

## Установка (Inno)
Запустите `SmartPOS_USB_Agent_1.4.1_Setup.exe`. Во время установки введите API Key — он будет записан в `%ProgramData%\SmartPOS\usb_agent\config.json`.

### Проверка

```powershell
& "$env:ProgramFiles\SmartPOS_USB_Agent\src\python\run_usb_devctl.bat" --selftest --out "$env:TEMP\spusb_selftest.zip"
Get-Service SmartPOS_USB_Agent | Format-List Name,Status,StartType
Get-WinEvent -LogName Application -MaxEvents 50 | ? { $_.ProviderName -eq 'SmartPOS_USB_Agent' } | select TimeCreated,Message
