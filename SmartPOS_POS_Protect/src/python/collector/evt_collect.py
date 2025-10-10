import subprocess, json, datetime, shutil

def _ps(cmd: str, timeout=60):
    """Запуск PowerShell/pwsh без shell=True, с безопасными таймаутами."""
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return None, "no_powershell"
    cp = subprocess.run([exe, "-NoProfile", "-Command", cmd],
                        capture_output=True, text=True, timeout=timeout)
    if cp.returncode != 0:
        print(json.dumps({"subsystem":"pos_protect","action":"ps_error","result":"error",
                          "labels":{"rc":cp.returncode,"stderr":(cp.stderr or "").strip()}}))
        return None, "ps_error"
    return cp.stdout, None

def collect_eventlog(cfg, lookback_days=1):
    start_days = lookback_days if lookback_days is not None else 1
    max_events = cfg.get("max_events_per_tick", 200)
    evts = []
    
    for chan in cfg.get("channels", []):
        log = chan["log"]
        providers = chan.get("providers", [])
        chan_lookback = chan.get("days_lookback", start_days)
        
        # Безопасная форма без FilterHashtable
        provider_filter = ""
        if providers:
            # $_.ProviderName может быть null — подстрахуемся через ToString()
            ors = " -or ".join([f"([string]$_.ProviderName) -eq '{p}'" for p in providers])
            provider_filter = f"| Where-Object {{ {ors} }} "

        ps = (
            f"Get-WinEvent -LogName '{log}' "
            f"| Where-Object {{ $_.TimeCreated -ge (Get-Date).AddDays(-{chan_lookback}) }} "
            f"{provider_filter}"
            f"| Select-Object -First {max_events} TimeCreated, Id, ProviderName, Message "
            f"| ConvertTo-Json -Compress"
        )

        try:
            stdout, err = _ps(ps)
            if err or stdout is None:
                # нет PowerShell — выходим «тихо», пусть агент продолжит жить
                diag = {"subsystem":"pos_protect","action":"ps_no_powershell","result":"error",
                        "labels":{"log":log,"error":err}}
                print(json.dumps(diag, ensure_ascii=False))
                continue
        except subprocess.TimeoutExpired:
            # Таймаут PowerShell команды
            diag = {"subsystem":"pos_protect","action":"ps_timeout","result":"error",
                    "labels":{"log":log,"timeout":60,"cmd_preview":ps[:100]}}
            print(json.dumps(diag, ensure_ascii=False))
            continue

        out = stdout.strip() or "[]"
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            
            chan_events = 0
            for e in data or []:
                evts.append({
                    "source": f"EventLog.{log}",
                    "provider": e.get("ProviderName"),
                    "event_id": e.get("Id"),
                    # PowerShell отдаёт /Date(…)/ — не парсим, просто прокидываем
                    "ts": e.get("TimeCreated"),
                    "message": e.get("Message"),
                })
                chan_events += 1
            
            # Логируем успешный сбор событий
            if chan_events > 0:
                diag = {"subsystem":"pos_protect","action":"evt_collected","result":"success",
                        "labels":{"log":log,"count":chan_events,"providers":len(providers)}}
                print(json.dumps(diag, ensure_ascii=False))
                
        except Exception as ex:
            diag = {"subsystem":"pos_protect","action":"json_parse_error","result":"error",
                    "labels":{"log":log,"err":str(ex)[:240],"output_preview":out[:100]}}
            print(json.dumps(diag, ensure_ascii=False))
    
    return evts
