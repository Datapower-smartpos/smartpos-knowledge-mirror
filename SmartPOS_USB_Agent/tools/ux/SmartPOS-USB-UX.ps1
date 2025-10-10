# SmartPOS USB Agent — Engineering UX Script (v1.4.1)
# Language: RU/EN mixed for field engineers
# Encoding: UTF-8 with BOM (required for Cyrillic)
# Purpose: Quick diagnostic and operations helper for SmartPOS USB Agent
# Paths: single backslashes, absolute where possible
# Logs: writes to %ProgramData%\SmartPOS\usb_agent\logs\ux_script.log
# Notes: No admin-only commands unless explicitly stated; safe read-only defaults

param(
    [switch]$Test,
    [string]$ServiceName = 'SmartPOS_USB_Agent',
    [string]$AgentRoot = "$env:ProgramData\SmartPOS\usb_agent",
    [int]$TimeoutSec = 60
)
[System.Net.ServicePointManager]::Expect100Continue = $false

# ===== Constants =====
$ErrorActionPreference = 'Stop'
$LogDir = Join-Path $AgentRoot 'logs'
$LogFile = Join-Path $LogDir 'ux_script.log'
$ConfigPath = Join-Path $AgentRoot 'config.json'
$ExportDir = Join-Path $AgentRoot 'export_tmp'
# Базовый адрес по умолчанию
$HttpBase = 'http://127.0.0.1:19955'
# Авто-определение хоста/порта из config.json с фолбэком на 127.0.0.1:19955
try {
    if (Test-Path $ConfigPath) {
        $cfg = Get-Content -Path $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.http -and $cfg.http.host -and $cfg.http.port) {
            $HttpBase = "http://$($cfg.http.host):$($cfg.http.port)"
        }
    }
} catch { Write-UXLog "[CONF][WARN] Автоопределение HttpBase не удалось: $($_.Exception.Message)" }


# ===== Helpers =====
function Write-UXLog {
    param([string]$Message)
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "[$ts] $Message"
    $line | Out-File -FilePath $LogFile -Append -Encoding utf8
    Write-Host $line
}

function Invoke-HttpJson {
    param([string]$Url,[int]$TimeoutSec=10)
    try {
        $resp = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSec -UseBasicParsing
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
            return ($resp.Content | ConvertFrom-Json)
        } else {
            throw "HTTP $($resp.StatusCode)"
        }
    } catch {
        Write-UXLog "[HTTP][ERROR] $Url => $($_.Exception.Message)"
        return $null
    }
}

function Test-EventLogSource {
    param([string]$Source='SmartPOS_USB_Agent',[string]$LogName='Application')
    try {
        if (-not [System.Diagnostics.EventLog]::SourceExists($Source)) {
            New-EventLog -LogName $LogName -Source $Source -ErrorAction SilentlyContinue | Out-Null
        }
        return $true
    } catch {
        Write-UXLog "[EVT][WARN] Cannot create source: $($_.Exception.Message)"
        return $false
    }
}

function Write-AgentEvent {
    param([string]$Message,[string]$EntryType='Information',[int]$EventId=1001)
    try {
        if (Test-EventLogSource -Source 'SmartPOS_USB_Agent' -LogName 'Application') {
            Write-EventLog -LogName 'Application' -Source 'SmartPOS_USB_Agent' -EventId $EventId -EntryType $EntryType -Message $Message
        }
    } catch {
        Write-UXLog "[EVT][ERROR] $Message => $($_.Exception.Message)"
    }
}

# ===== Menu =====
function Show-Menu {
    Write-Host "`n=== SmartPOS USB Agent — UX-меню (v1.4.1) ==="
    Write-Host "1) Статус службы"
    Write-Host "2) Предпроверка (/api/preflight)"
    Write-Host "3) Экспорт ZIP по маске (/api/export?mask=)"
    Write-Host "4) Горячая перезагрузка политики (/api/policy/reload)"
    Write-Host "5) Показать путь к config.json и наличие API Key"
    Write-Host "6) Ротация логов (локально)"
    Write-Host "7) Быстрый тест Watchdog (автоперезапуск + журнал событий)"
    Write-Host "8) Показать счётчики БД (actions / preflight_runs)"
	Write-Host "9) Быстрая проверка содержимого БД (последние записи)"
    Write-Host "0) Выход"
}


# ===== Actions =====
function Do-ServiceStatus {
    Write-Host "-- Проверка службы Windows --"
    try {
        $svc = Get-Service -Name $ServiceName -ErrorAction Stop
        Write-Host "Service: $($svc.DisplayName) [$ServiceName] => $($svc.Status)"
        Write-UXLog "[SVC] $ServiceName => $($svc.Status)"
    } catch {
        Write-UXLog "[SVC][ERROR] $ServiceName => $($_.Exception.Message)"
        Write-Host "Служба не найдена"
    }
    $st = Invoke-HttpJson "$HttpBase/api/status" -TimeoutSec $TimeoutSec
    if ($st) { Write-Host ($st | ConvertTo-Json -Depth 5) }
}

function DoPreflight {
    try {
        $body = "{}"
        $resp = Invoke-RestMethod -Uri "$HttpBase/api/preflight" `
            -Method Post -ContentType "application/json" `
            -Body $body -TimeoutSec $TimeoutSec
        # resp уже объект; просто выведем его как JSON
        Write-Host ($resp | ConvertTo-Json -Depth 5)
    } catch {
        Write-UXLog "[HTTP][ОШИБКА] $HttpBase/api/preflight => $($_.Exception.Message)"
    }
}
# алиас на старое имя, если в switch остался дефисный вариант
Set-Alias -Name Do-Preflight -Value DoPreflight -Scope Script -ErrorAction SilentlyContinue


function Do-ExportZip {
    if (-not (Test-Path $ExportDir)) { New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null }
    $mask = Read-Host "Введите маску (например: logs/*.log;db/*.sqlite)"
    $url = "$HttpBase/api/export?mask=$([uri]::EscapeDataString($mask))"
    Write-Host "HTTP-запрос: $url"
    try {
        $tmp = Join-Path $ExportDir ("export_" + (Get-Date).ToString('yyyyMMdd_HHmmss') + '.zip')
        Invoke-WebRequest -Uri $url -OutFile $tmp -TimeoutSec ($TimeoutSec*2) -UseBasicParsing
        Write-UXLog "[EXPORT] Saved: $tmp"
        Write-AgentEvent "Export ZIP saved: $tmp" 'Information' 1201
        Write-Host "Saved => $tmp"
    } catch {
        Write-UXLog "[EXPORT][ERROR] $url => $($_.Exception.Message)"
        Write-AgentEvent "Export ZIP failed: $($_.Exception.Message)" 'Error' 1202
        Write-Host "Export failed"
    }
}

function Do-ReloadPolicy {
    try {
        $resp = Invoke-WebRequest -Uri "$HttpBase/api/policy/reload" `
          -Method Post -ContentType "application/json" -Body "{}" `
          -TimeoutSec $TimeoutSec -UseBasicParsing
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
            $r = $resp.Content | ConvertFrom-Json
            Write-Host ($r | ConvertTo-Json -Depth 5)
        } else { throw "HTTP $($resp.StatusCode)" }
    } catch { Write-UXLog "[HTTP][ОШИБКА] $HttpBase/api/policy/reload => $($_.Exception.Message)" }
}


function Do-ShowConfig {
    Write-Host "Путь к конфигу: $ConfigPath"
    if (Test-Path $ConfigPath) {
        $json = Get-Content -Path $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $hasKey = $null -ne $json.api_key -and ($json.api_key.ToString().Length -gt 0)
        Write-Host "API Key присутствует: $hasKey"
        Write-UXLog "[CONF] api_key_present=$hasKey"
    } else {
        Write-Host "config.json не найден"
        Write-UXLog "[CONF][WARN] config.json not found"
    }
}

function Do-RotateLogs {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $files = Get-ChildItem -Path $LogDir -File -ErrorAction SilentlyContinue
    foreach ($f in $files) {
        if ($f.Length -gt 10MB) {
            $arch = Join-Path $LogDir ($f.BaseName + '_' + (Get-Date -Format 'yyyyMMddHHmmss') + '.log')
            Copy-Item $f.FullName $arch -Force
            Clear-Content $f.FullName -ErrorAction SilentlyContinue
            Write-UXLog "[LOGROTATE] $($f.Name) -> $([IO.Path]::GetFileName($arch))"
        }
    }
}

function Do-WatchdogQuickTest {
    Write-Host "=== 7) Быстрый тест Watchdog ==="
    Write-Host "Останавливаем службу (ожидается автоперезапуск сторожем ~30 с)"
    try {
        Stop-Service -Name $ServiceName -Force -ErrorAction Stop
        Write-UXLog "[WDT][STEP] Service stopped"
        Write-AgentEvent "Watchdog test: service stopped by UX" 'Warning' 1701
    } catch {
        Write-UXLog "[WDT][ERROR] Stop-Service => $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 5
    # Poll for restart
    $restarted = $false
    for ($i=0; $i -lt 12; $i++) {
        try {
            $svc = Get-Service -Name $ServiceName -ErrorAction Stop
            if ($svc.Status -eq 'Running') { $restarted=$true; break }
        } catch { }
        Start-Sleep -Seconds 5
    }
    if ($restarted) {
        Write-UXLog "[WDT][PASS] Service restarted by Watchdog"
        Write-AgentEvent "Watchdog PASS: service restarted automatically" 'Information' 1702
        Write-Host "УСПЕХ: служба перезапущена"
    } else {
        Write-UXLog "[WDT][FAIL] Service did not restart"
        Write-AgentEvent "Watchdog FAIL: service did not restart" 'Error' 1703
        Write-Host "ОТКАЗ: автоперезапуск не обнаружен"
    }
    # Event Log tail
    Write-Host "Последние записи журнала приложений для источника SmartPOS_USB_Agent:"
    try {
        $events = Get-WinEvent -LogName Application -MaxEvents 30 | Where-Object {$_.ProviderName -eq 'SmartPOS_USB_Agent'}
        $events | Select-Object TimeCreated, Id, LevelDisplayName, Message | Format-Table -AutoSize
    } catch {
        Write-UXLog "[EVT][WARN] Cannot read Event Log => $($_.Exception.Message)"
    }
}

function Do-ShowDbCounters {
  try {
    $db = 'C:\ProgramData\SmartPOS\usb_agent\db\smartpos_usb.db'

    # Проверим, что файл БД есть
    if (-not (Test-Path $db)) {
      Write-Host "[DB] Файл не найден: $db"
      return
    }

    # Определяем, чем запускать Python (совместимо с PS 5.1)
    $cmdInfo = Get-Command python -ErrorAction SilentlyContinue
    $cmd = $null
    $args = @('-')  # читать код из stdin
    if ($cmdInfo) {
      $cmd = $cmdInfo.Source
    } else {
      $cmdInfo = Get-Command py -ErrorAction SilentlyContinue
      if ($cmdInfo) {
        $cmd = $cmdInfo.Source
        $args = @('-3','-')
      }
    }
    if (-not $cmd) {
      Write-Host "[PY][ОШИБКА] Не найден python/py в PATH. Установите Python 3.x и перезапустите консоль."
      return
    }

    # Python-код читается из stdin
    $py = @'
import sqlite3, json, os, sys
db = r"__DB__"
if not os.path.exists(db):
    print("DB not found:", db); sys.exit(2)
con = sqlite3.connect(db); con.row_factory = sqlite3.Row
tables = [r['name'] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", tables)

def count(tbl):
    try:
        c = con.execute("SELECT COUNT(*) FROM {}".format(tbl)).fetchone()[0]
        print("{}: {}".format(tbl, c))
    except Exception as e:
        print("{}: <err {}>".format(tbl, e))

for t in ("actions","preflight_runs"):
    if t in tables: count(t)
con.close()
'@

    # Подставим путь к БД (удвоим только обратные слэши)
    $py = $py -replace '__DB__', ($db -replace '\\','\\')

    Write-Host "[DB] Счётчики (actions / preflight_runs):"
    # ВАЖНО: НЕ подавляем вывод!
    $py | & $cmd @args
  } catch {
    Write-Host "[PY][ОШИБКА] $($_.Exception.Message)"
  }
}

# --- вспомогательно: берём путь к БД из config.json или по умолчанию
function Get-DbPath {
  try {
    $cfgPath = "C:\ProgramData\SmartPOS\usb_agent\config.json"
    $default = "C:\ProgramData\SmartPOS\usb_agent\db\smartpos_usb.db"
    if (Test-Path $cfgPath) {
      $cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($cfg.paths -and $cfg.paths.db_path) { return $cfg.paths.db_path }
    }
    return $default
  } catch { return "C:\ProgramData\SmartPOS\usb_agent\db\smartpos_usb.db" }
}

# --- пункт 9: последние записи БД по ключевым таблицам (PS 5.1 совместимо)
function Do-ShowDbTail {
  try {
    $db = Get-DbPath
    if (-not (Test-Path $db)) {
      Write-Host "[DB] Файл не найден: $db"
      return
    }

    # Определяем, чем запускать Python (PS 5.1-совместимо)
    $cmdInfo = Get-Command python -ErrorAction SilentlyContinue
    $cmd = $null; $args = @('-')   # читать код из stdin
    if ($cmdInfo) {
      $cmd = $cmdInfo.Source
    } else {
      $cmdInfo = Get-Command py -ErrorAction SilentlyContinue
      if ($cmdInfo) { $cmd = $cmdInfo.Source; $args = @('-3','-') }
    }
    if (-not $cmd) {
      Write-Host "[PY][ОШИБКА] Не найден python/py в PATH. Установите Python 3.x и перезапустите консоль."
      return
    }

    # Код на Python: печать количества и хвоста по таблицам
    $py = @'
import sqlite3, json, os
db = r"__DB__"
if not os.path.exists(db):
    print("DB not found:", db); raise SystemExit(2)
con = sqlite3.connect(db); con.row_factory = sqlite3.Row
tables = ("actions","preflight_runs","devices","usb_events")
for t in tables:
    try:
        cnt = con.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]
        rows = con.execute("SELECT * FROM {} ORDER BY rowid DESC LIMIT 10".format(t)).fetchall()
        print("{}: {}".format(t, cnt))
        for r in rows:
            print(" ", json.dumps(dict(r), ensure_ascii=False))
    except Exception as e:
        print(t, "<err>", e)
con.close()
'@

    # Подставим путь (удвоим только обратные слэши) и выполним
    $py = $py -replace '__DB__', ($db -replace '\\','\\')
    Write-Host "[DB] Последние записи (по 10 шт. на таблицу):"
    $py | & $cmd @args
  } catch {
    Write-Host "[PY][ОШИБКА] $($_.Exception.Message)"
  }
}

# ===== Main =====
if ($Test) {
    Write-Host "[ТЕСТОВЫЙ РЕЖИМ]"
    Write-UXLog "[TEST] UX script started"
}

while ($true) {
    Show-Menu
    $choice = Read-Host 'Выберите пункт меню'
    switch ($choice) {
        '1' { Do-ServiceStatus }
        '2' { Do-Preflight }
        '3' { Do-ExportZip }
        '4' { Do-ReloadPolicy }
        '5' { Do-ShowConfig }
        '6' { Do-RotateLogs }
        '7' { Do-WatchdogQuickTest }
		'8' { Do-ShowDbCounters }
		'9' { Do-ShowDbTail }
        '0' { return  }
        default { Write-Host 'Неизвестная команда' }
    }
}

Write-UXLog '[EXIT] UX script finished'
