#!/usr/bin/env python3
"""Планировщик действий для SmartPOS POS Protect."""

from typing import Dict, Any, Callable, Optional
import subprocess, time, json, sys, shlex

# Реестр доступных действий
ACTIONS: Dict[str, Callable[[Dict[str, Any]], bool]] = {}

def _retry_wrap(fn: Callable[[Dict[str, Any]], bool], retries:int=0, backoff_base:float=0.5):
    """Обёртка для повторных попыток выполнения действий."""
    def _inner(args: Dict[str, Any]) -> bool:
        attempt = 0
        while True:
            ok = fn(args)
            if ok or attempt >= retries:
                return ok
            time.sleep((2 ** attempt) * backoff_base)
            attempt += 1
    return _inner

def _run_ps(cmd: str, timeout_sec: int = 30, dry: bool = True) -> bool:
    """Выполнение PowerShell команд с поддержкой dry-run."""
    if dry:
        print(json.dumps({"action":"ps", "cmd":cmd, "dry_run":True}))
        return True
    proc = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", cmd],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout_sec)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        return False

# --- Атомарные действия (безопасные, с dry-run) ---
def restart_service(args: Dict[str, Any]) -> bool:
    """Перезапуск службы Windows."""
    name = args.get("name", "Spooler")
    return _run_ps(f"Restart-Service -Name {shlex.quote(name)} -Force", timeout_sec=args.get("timeout_sec",30), dry=args.get("dry", True))

def clear_print_queue(args: Dict[str, Any]) -> bool:
    """Очистка очереди печати."""
    # Очистка директории Spool + останов/запуск службы
    ps = r"Stop-Service -Name Spooler -Force; " \
         r"Remove-Item -Path 'C:\Windows\System32\spool\PRINTERS\*' -Force -ErrorAction SilentlyContinue; " \
         r"Start-Service -Name Spooler"
    return _run_ps(ps, timeout_sec=args.get("timeout_sec",30), dry=args.get("dry", True))

def collect_wer_bundle(args: Dict[str, Any]) -> bool:
    """Сбор WER отчётов в архив."""
    # Упрощённо: собираем свежие отчёты в zip (путь можно расширить)
    ps = r"$d=$env:TEMP+'\wer_bundle'; New-Item -Force -ItemType Directory $d | Out-Null; " \
         r"Get-ChildItem 'C:\ProgramData\Microsoft\Windows\WER\ReportArchive' -Recurse -ErrorAction SilentlyContinue | " \
         r"Copy-Item -Destination $d -Recurse -Force -ErrorAction SilentlyContinue; " \
         r"Compress-Archive -Path $d\* -DestinationPath $d+'.zip' -Force"
    return _run_ps(ps, timeout_sec=args.get("timeout_sec",60), dry=args.get("dry", True))

def link_smart(args: Dict[str, Any]) -> bool:
    """Плейсхолдер интеграции со SMART/USB отчётами."""
    # Плейсхолдер интеграции со SMART/USB отчётами (создаём ссылку/маркер)
    print(json.dumps({"action":"link_smart","note":"link to SMART summary queued"}))
    return True

def plan_chkdsk(args: Dict[str, Any]) -> bool:
    """Планирование проверки диска при следующей перезагрузке."""
    vol = args.get("volume", "C:")
    ps = f"schtasks /Create /TN PosProtect\\PlanChkdsk /TR \"cmd /c echo y|chkdsk {vol} /f\" /SC ONSTART /RL HIGHEST /F"
    return _run_ps(ps, timeout_sec=args.get("timeout_sec",15), dry=args.get("dry", True))

def run_sfc(args: Dict[str, Any]) -> bool:
    """Запуск System File Checker."""
    ps = r"sfc /scannow"
    return _run_ps(ps, timeout_sec=args.get("timeout_sec",1800), dry=args.get("dry", True))

def run_dism(args: Dict[str, Any]) -> bool:
    """Запуск DISM для восстановления образа системы."""
    ps = r"Dism /Online /Cleanup-Image /RestoreHealth"
    return _run_ps(ps, timeout_sec=args.get("timeout_sec",3600), dry=args.get("dry", True))

def reset_wu_components(args: Dict[str, Any]) -> bool:
    """Сброс компонентов Windows Update."""
    ps = r"net stop wuauserv; net stop bits; net stop cryptsvc; " \
         r"Ren %systemroot%\SoftwareDistribution SoftwareDistribution.bak; " \
         r"Ren %systemroot%\system32\catroot2 catroot2.bak; " \
         r"net start cryptsvc; net start bits; net start wuauserv"
    return _run_ps(ps, timeout_sec=args.get("timeout_sec",120), dry=args.get("dry", True))

# Регистрация действий
ACTIONS.update({
  "restart_service": _retry_wrap(restart_service, retries=1),
  "clear_print_queue": _retry_wrap(clear_print_queue, retries=0),
  "collect_wer_bundle": _retry_wrap(collect_wer_bundle, retries=0),
  "link_smart": _retry_wrap(link_smart, retries=0),
  "plan_chkdsk": _retry_wrap(plan_chkdsk, retries=0),
  "run_sfc": _retry_wrap(run_sfc, retries=0),
  "run_dism": _retry_wrap(run_dism, retries=0),
  "reset_wu_components": _retry_wrap(reset_wu_components, retries=0)
})

def execute_action(action_name: str, args: Dict[str, Any]) -> bool:
    """Выполнение действия по имени."""
    if action_name not in ACTIONS:
        print(json.dumps({"action":"error", "message":f"Unknown action: {action_name}"}))
        return False
    
    try:
        return ACTIONS[action_name](args)
    except Exception as e:
        print(json.dumps({"action":"error", "message":str(e)}))
        return False

def list_available_actions() -> list:
    """Список доступных действий."""
    return list(ACTIONS.keys())

if __name__ == "__main__":
    # Тестирование действий
    print("Available actions:", list_available_actions())
    
    # Тест dry-run режима
    print("\nTesting dry-run mode:")
    execute_action("restart_service", {"name": "Spooler", "dry": True})
    execute_action("collect_wer_bundle", {"dry": True})
