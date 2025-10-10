def classify_events(events, cfg=None):
    """Классификация событий с маппингом исключений, дедупликацией и настраиваемыми порогами."""
    if cfg is None:
        cfg = {}
    
    # Настройки из конфигурации
    classifier_cfg = cfg.get("classifier", {})
    critical_processes = classifier_cfg.get("critical_processes", [])
    ignore_processes = classifier_cfg.get("ignore_processes", [])
    max_duplicates_per_tick = classifier_cfg.get("max_duplicates_per_tick", 3)
    
    # WER-специфичные настройки из резолверной конфигурации
    wer_policy = cfg.get("__resolved", {}).get("wer", {})
    wer_critical_processes = wer_policy.get("critical_processes", [])
    wer_ignore_processes = wer_policy.get("ignore_processes", [])
    
    # Объединяем списки процессов (приоритет у classifier)
    critical_processes = critical_processes + wer_critical_processes
    ignore_processes = ignore_processes + wer_ignore_processes
    
    # Маппинг исключений
    exception_mapping = {
        "c0000005": "AccessViolation",
        "c0000006": "InPageError",
        "c000001d": "IllegalInstruction",
        "c0000025": "NoncontinuableException",
        "c0000026": "InvalidDisposition",
        "c000008f": "ArrayBoundsExceeded",
        "c0000094": "IntegerDivideByZero",
        "c0000096": "PrivilegedInstruction",
        "c00000fd": "StackOverflow"
    }
    
    # Системные апдейтеры для фильтрации
    system_updaters = [
        "Windows Update", "WinGet", "CBS", "TrustedInstaller",
        "wuauclt", "wuaueng", "wuauserv", "wuuhosdeployment",
        "svchost.exe_wuauserv", "svchost.exe_wuuhosdeployment"
    ]
    
    # Дедупликация: seen-ключи на тик
    seen_keys = set()
    issues = []
    
    for e in events:
        src = e.get("source", "")
        provider = e.get("provider")
        eid = e.get("event_id")
        message = e.get("message", "")
        
        # Обработка LiveKernelEvent
        if src.startswith("EventLog.System") and provider == "Microsoft-Windows-Kernel-General":
            # LiveKernelEvent обычно имеют специфические ID
            if eid in (1, 2, 3, 4, 5):  # Типичные ID для LiveKernelEvent
                issues.append({
                    "issue_code": "KERNEL_LIVE_EVENT",
                    "severity": "INFO",
                    "evidence": e
                })
            continue
        
        # Обработка системных апдейтеров
        if src.startswith("EventLog.System") and provider in system_updaters:
            # Проверяем, не критический ли процесс
            if not any(crit_proc.lower() in provider.lower() for crit_proc in critical_processes):
                # Короткий summary для системных обновлений
                issues.append({
                    "issue_code": "SYSTEM_UPDATE",
                    "severity": "INFO",
                    "evidence": {
                        **e,
                        "summary": f"Windows Update activity: {provider}"
                    }
                })
            continue
        
        # Подавление svchost.exe_wuauserv/wuuhosdeployment.dll_unloaded
        if (src.startswith("EventLog.System") and 
            provider == "Microsoft-Windows-Kernel-General" and
            ("svchost.exe_wuauserv" in message or "wuuhosdeployment.dll_unloaded" in message)):
            # Это типичный след удаления/обновления компонентов
            # Подавляем, если нет серии в последние X часов (пока просто пропускаем)
            continue
        
        # Обработка WER событий с улучшенной классификацией
        if src == "WER" and e.get("crash"):
            proc = e.get("proc", "") or ""
            faulting_module = e.get("faulting_module", "") or ""
            exception_code = e.get("exception_code", "") or ""
            
            # Дедупликация по ключу
            dedup_key = f"{proc}|{faulting_module}|{exception_code}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            
            # Маппинг исключений
            exception_type = exception_mapping.get(exception_code.lower(), "UnknownException")
            
            # Определение серьезности по процессам
            severity = "WARN"  # По умолчанию
            if proc and any(crit_proc.lower() in proc.lower() for crit_proc in critical_processes):
                severity = "CRIT"
            elif proc and any(ignore_proc.lower() in proc.lower() for ignore_proc in ignore_processes):
                severity = "IGNORE"
            
            # Пропускаем игнорируемые процессы
            if severity == "IGNORE":
                continue
            
            # Создание evidence с дополнительной информацией
            evidence = e.copy()
            evidence["exception_type"] = exception_type
            evidence["dedup_key"] = dedup_key
            
            issues.append({
                "issue_code": "POS_APP_CRASH",
                "severity": severity,
                "evidence": evidence
            })
        
        # Обработка EventLog событий (существующая логика)
        elif src.startswith("EventLog.System") and provider == "Service Control Manager" and eid in (7031, 7034):
            issues.append({"issue_code": "PRINT_SPOOLER_STUCK", "severity": "WARN", "evidence": e})
        elif src.startswith("EventLog.System") and provider in ("Disk", "storahci", "volmgr", "Ntfs") and eid in (51, 153):
            issues.append({"issue_code": "DISK_IO_WARN", "severity": "WARN", "evidence": e})
    
    return issues
