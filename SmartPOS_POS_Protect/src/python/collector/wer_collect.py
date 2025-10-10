import os, glob, datetime, re
from datetime import datetime, timedelta
from pathlib import Path

def filetime_to_iso(ft_str: str) -> str | None:
    """Конвертация FILETIME в ISO8601."""
    try:
        ft = int(ft_str)
        # FILETIME 100-ns ticks since 1601-01-01
        return (datetime(1601, 1, 1) + timedelta(microseconds=ft/10)).isoformat()
    except Exception:
        return None

def _read_wer_text(path: str) -> str:
    """Чтение WER файла с попытками разных кодировок."""
    for enc in ("utf-16-le", "utf-8-sig", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _extract(wer: str, patterns: list[str]) -> str | None:
    """Извлечение значения по паттернам."""
    for p in patterns:
        m = re.search(p, wer, flags=re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None

def parse_wer_fields(wer_text: str) -> dict:
    """Парсинг полей из WER файла с улучшенным извлечением."""
    # Извлечение имени процесса в правильном порядке
    proc = _extract(wer_text, [
        r"^NsAppName=(.+)$",
        r"^AppName=(.+)$", 
        r"^PackageFullName=(.+)$",
        r"^Sig\[0\]\.Value=(.+)$"
    ])
    
    # Извлечение модуля с ошибкой
    fault = _extract(wer_text, [
        r"^Sig\[3\]\.Value=(.+)$",
        r"^FaultingModule(?:Name)?=(.+)$"
    ])
    
    # Извлечение кода исключения
    exc = _extract(wer_text, [
        r"^Sig\[6\]\.Value=(.+)$",
        r"^ExceptionCode=(.+)$"
    ])
    
    # Извлечение времени отчета (FILETIME)
    rtime_raw = _extract(wer_text, [
        r"^ReportCreationTime=(.+)$",
        r"^EventTime=(.+)$",
        r"^UploadTime=(.+)$"
    ])
    
    # Конвертация FILETIME в ISO8601
    rtime = None
    if rtime_raw:
        rtime = filetime_to_iso(rtime_raw)
    
    return {
        "proc": proc,
        "faulting_module": fault,
        "exception_code": exc,
        "report_time": rtime,
        "report_time_raw": rtime_raw
    }

def _is_recent_dir(d: Path, lookback_days: int) -> bool:
    """Проверка свежести директории по LastWriteTime."""
    try:
        return datetime.fromtimestamp(d.stat().st_mtime) >= datetime.now() - timedelta(days=lookback_days)
    except Exception:
        return False

def _is_recent_by_wer_time(wer_data: dict, lookback_days: int) -> bool:
    """Проверка свежести по времени из Report.wer."""
    try:
        report_time = wer_data.get("report_time")
        if not report_time:
            return True  # Если нет времени в WER, полагаемся на LastWriteTime
        
        # Парсинг ISO8601 времени
        wer_dt = datetime.fromisoformat(report_time.replace('Z', '+00:00'))
        return wer_dt >= datetime.now() - timedelta(days=lookback_days)
    except Exception:
        return True  # При ошибке считаем свежим

def collect_wer(cfg):
    """Сбор WER отчетов с улучшенной фильтрацией и дедупликацией."""
    res = []
    seen_keys = set()  # Дедупликация по ключу
    
    # Определяем корневые директории на основе конфигурации
    roots = [r"C:\ProgramData\Microsoft\Windows\WER\ReportArchive"]
    
    # Добавляем ReportQueue только если включено
    if cfg.get("include_report_queue", False):
        roots.append(r"C:\ProgramData\Microsoft\Windows\WER\ReportQueue")
    
    lookback_days = cfg.get("lookback_days", 7)
    max_reports = cfg.get("max_reports_per_tick", 50)
    max_duplicates = cfg.get("max_duplicates_per_tick", 3)
    
    for root in roots:
        if not os.path.exists(root):
            continue
            
        dirs_found = 0
        dirs_filtered = 0
        
        for d in glob.glob(os.path.join(root, "*")):
            try:
                d_path = Path(d)
                dirs_found += 1
                
                # Фильтр по свежести директории (LastWriteTime)
                if not _is_recent_dir(d_path, lookback_days):
                    dirs_filtered += 1
                    continue
                
                # Попытка доступа к директории
                try:
                    files = os.listdir(d)
                except PermissionError:
                    # Пропускаем директории без доступа
                    continue
                proc = None
                wer_data = {}
                
                # Поиск Report.wer для извлечения полей
                wer_file = None
                for f in files:
                    if f.lower() == "report.wer":
                        wer_file = os.path.join(d, f)
                        break
                
                # Извлечение данных из Report.wer
                if wer_file:
                    try:
                        wer_text = _read_wer_text(wer_file)
                        wer_data = parse_wer_fields(wer_text)
                        proc = wer_data.get("proc")
                        
                        # Дополнительная фильтрация по времени из WER
                        if not _is_recent_by_wer_time(wer_data, lookback_days):
                            continue
                            
                    except Exception as e:
                        pass
                
                # Fallback: поиск по имени .exe файла
                if not proc:
                    for f in files:
                        if f.lower().endswith(".exe"):
                            proc = f.rsplit(".", 1)[0]
                            break
                
                # Создание ключа дедупликации
                dedup_key = f"{proc or ''}|{wer_data.get('faulting_module', '')}|{wer_data.get('exception_code', '')}"
                
                # Проверка дедупликации
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                
                # Определение времени события (приоритет времени из WER)
                event_time = wer_data.get("report_time")
                if not event_time:
                    try:
                        # Используем время модификации директории как fallback
                        event_time = datetime.fromtimestamp(d_path.stat().st_mtime).isoformat()
                    except Exception:
                        event_time = datetime.now().isoformat()
                
                # Создание записи с дополнительным контекстом
                record = {
                    "source": "WER",
                    "crash": True,
                    "proc": proc,
                    "path": d,
                    "ts": event_time,
                    "faulting_module": wer_data.get("faulting_module"),
                    "exception_code": wer_data.get("exception_code"),
                    "dedup_key": dedup_key,
                    "report_time_raw": wer_data.get("report_time_raw")
                }
                
                res.append(record)
                
                # Ограничение количества отчетов
                if len(res) >= max_reports:
                    break
                    
            except Exception:
                continue
    
    # Логируем успешный сбор WER событий
    if res:
        import json
        diag = {"subsystem":"pos_protect","action":"wer_collected","result":"success",
                "labels":{"count":len(res),"lookback_days":lookback_days,"roots":roots}}
        print(json.dumps(diag, ensure_ascii=False))
    
    return res
