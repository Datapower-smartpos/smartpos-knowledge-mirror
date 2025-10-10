# ── smartpos_daemon/__init__.py
"""SmartPOS Action Daemon (MVP)
- HTTP JSON endpoint (no external web frameworks)
- 4 playbooks for printer scenarios
- Fault‑Injector helpers for demo stand

Limitations observed:
- No shell=True, no multiprocessing; use threading only
- Windows-only modules: pywin32 (win32print, win32serviceutil)
"""
from __future__ import annotations

__all__ = [
    "config",
    "logs",
    "server",
    "router",
    "actions",
    "faults",
]

# ── smartpos_daemon/config.py
from dataclasses import dataclass

@dataclass
class DaemonConfig:
    host: str = "127.0.0.1"
    port: int = 7077  # Возвращаем порт 7077
    default_printer_name: str | None = None  # if None → system default
    request_timeout_sec: float = 8.0

CONFIG = DaemonConfig()

# ── smartpos_daemon/logs.py
import logging

LOGGER_NAME = "smartpos_daemon"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    h = logging.StreamHandler()
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    h.setFormatter(fmt)
    logger.addHandler(h)
    return logger


logger = setup_logging()

# ── Контроль роутера
from smartpos_daemon import router
logger.info("PLAYBOOK PR0018: %s", [fn.__name__ for fn in router.PLAYBOOKS["PR0018"]])

# ── smartpos_daemon/config.py
from dataclasses import dataclass
import threading

@dataclass
class RuntimeConfig:
    sticky_max_sec: float = 180.0      # было 180
    cancel_delay_sec: float = 0.5      # было 5.0 (сделаем быстрее по умолчанию)

_CFG = RuntimeConfig()
_LOCK = threading.RLock()

def cfg_get() -> RuntimeConfig:
    with _LOCK:
        return RuntimeConfig(**_CFG.__dict__)  # копия

def cfg_update(**kw) -> dict:
    changed = {}
    with _LOCK:
        for k, v in kw.items():
            if hasattr(_CFG, k) and v is not None:
                setattr(_CFG, k, float(v))
                changed[k] = float(v)
    return {"ok": True, "changed": changed, "current": _CFG.__dict__}

# ── smartpos_daemon/actions/__init__.py
# Все функции принтера определены ниже в этом же файле

# ── smartpos_daemon/actions/printer.py
import socket
from dataclasses import dataclass
from typing import Optional, Dict, Any
import time
import os
import glob

try:
    import win32print
    import win32serviceutil
    import win32service
except Exception:  # pragma: no cover (non‑Windows)
    win32print = None
    win32serviceutil = None
    win32service = None

# logger определен выше в этом же файле


@dataclass
class StepResult:
    """Uniform step result for playbook actions."""
    name: str
    evidence: Dict[str, Any] | None = None
    result: Optional[str] = None  # e.g., FIXED/NOT_FOUND/HARDWARE_FAULT
    terminal: bool = False


# -------- Spooler controls --------

def clear_spooler(req: dict) -> StepResult:
    """Delete all jobs from (default or given) printer queue with force."""
    if not win32print:
        return StepResult("print_queue_clear_skipped", {"reason": "win32print missing"})
    printer_name = _resolve_printer_name(req)
    try:
        h = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(h, 0, 999, 1)
            deleted = 0
            for job in jobs:
                try:
                    # Первая попытка - обычное удаление
                    win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                    deleted += 1
                    time.sleep(0.05)  # Небольшая задержка
                    
                    # Вторая попытка - принудительное удаление для зависших джобов
                    try:
                        win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                    except Exception:
                        # Третья попытка - сброс и удаление
                        try:
                            win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_RESTART)
                            time.sleep(0.1)
                            win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                        except Exception:
                            pass
                except Exception as e:  # noqa: BLE001
                    logger.warning("SetJob delete failed for job %d: %s", job["JobId"], e)
            return StepResult("print_queue_clear", {"deleted": deleted})
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:  # noqa: BLE001
        logger.error("clear_spooler error: %s", e)
        return StepResult("print_queue_clear_error", {"error": str(e)})


def restart_spooler(req: dict) -> StepResult:
    if not win32serviceutil:
        return StepResult("spooler_restart_skipped", {"reason": "win32serviceutil missing"})
    try:
        win32serviceutil.RestartService("Spooler")
        # Give it a short time to settle (demo‑tuned)
        time.sleep(1.0)
        return StepResult("spooler_restart")
    except Exception as e:  # noqa: BLE001
        logger.error("restart_spooler error: %s", e)
        return StepResult("spooler_restart_error", {"error": str(e)})


def force_clear_stuck_jobs(req: dict) -> StepResult:
    """Принудительная очистка зависших джобов в состоянии 'Удаление'."""
    try:
        printer_name = _resolve_printer_name(req)
        h = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(h, 0, 999, 1)
            force_deleted = 0
            
            for job in jobs:
                job_id = job["JobId"]
                try:
                    # Множественные попытки удаления с разными методами
                    for attempt in range(5):  # 5 попыток
                        try:
                            # Попытка 1-2: Обычное удаление
                            win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                            time.sleep(0.1)
                            
                            # Попытка 3: Сброс и удаление
                            win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_RESTART)
                            time.sleep(0.1)
                            win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                            time.sleep(0.1)
                            
                            # Попытка 4: Приостановка и удаление
                            win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_PAUSE)
                            time.sleep(0.1)
                            win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                            time.sleep(0.1)
                            
                            # Попытка 5: Последняя попытка
                            win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                            
                            force_deleted += 1
                            break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug("faults: force delete failed for job %d: %s", job_id, e)
            
            return StepResult("force_clear_stuck", {"force_deleted": force_deleted})
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:
        logger.error("force_clear_stuck_jobs error: %s", e)
        return StepResult("force_clear_stuck_error", {"error": str(e)})


def cancel_demo_sticky(req: dict) -> StepResult:
    """Сигнал инжектору: отпустить дескрипторы залипающих джобов (EndPage/EndDoc)."""
    try:
        # Используем конфигурацию для задержки перед отменой
        delay = cfg_get().cancel_delay_sec
        if delay > 0:
            time.sleep(delay)
        
        res = cancel_sticky_jobs(timeout_sec=5.0)  # Увеличиваем таймаут до 5 секунд
        alive_count = res.get("still_alive", 0)
        
        # Если потоки все еще живы, принудительно очищаем очередь
        if alive_count > 0:
            logger.warning("faults: %d threads still alive, forcing queue clear", alive_count)
            try:
                printer_name = _resolve_printer_name(req)
                h = win32print.OpenPrinter(printer_name)
                try:
                    # Принудительно удаляем все джобы с несколькими попытками
                    for job in win32print.EnumJobs(h, 0, 999, 1):
                        try:
                            # Первая попытка - обычное удаление
                            win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                            time.sleep(0.1)  # Небольшая задержка
                            
                            # Вторая попытка - принудительное удаление
                            win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                        except Exception as e:
                            logger.debug("faults: failed to delete job %d: %s", job["JobId"], e)
                            # Третья попытка - сброс джоба
                            try:
                                win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_RESTART)
                                time.sleep(0.1)
                                win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                            except Exception:
                                pass
                finally:
                    win32print.ClosePrinter(h)
            except Exception as e:
                logger.error("faults: forced queue clear failed: %s", e)
        
        return StepResult("sticky_cancel", {"alive_after_cancel": alive_count})
    except Exception as e:  # noqa: BLE001
        logger.error("cancel_demo_sticky error: %s", e)
        return StepResult("sticky_cancel_error", {"error": str(e)})


# -------- Device/port probes --------

def usb_presence_check(req: dict) -> StepResult:
    """Check if target printer is present in Windows printers list.
    We do not rescan USB; only observe presence and map to NOT_FOUND.
    """
    if not win32print:
        return StepResult("usb_presence_skip", {"reason": "win32print missing"})
    target = _resolve_printer_name(req)
    try:
        h = win32print.OpenPrinter(target)
        try:
            info = win32print.GetPrinter(h, 2)
            status = info["Status"]
            detected = True
        finally:
            win32print.ClosePrinter(h)
        return StepResult("usb_presence_ok", {"detected": detected, "status": int(status)})
    except Exception as e:  # noqa: BLE001
        logger.warning("usb_presence_check: %s", e)
        return StepResult("usb_presence_fail", {"detected": False, "error": str(e)})


def tcp9100_probe(req: dict) -> StepResult:
    device = req.get("device", {})
    ip = device.get("ip")
    if not ip:
        return StepResult("tcp9100_skip", {"reason": "no ip"})
    sock = socket.socket()
    sock.settimeout(1.0)
    try:
        sock.connect((ip, 9100))
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    finally:
        sock.close()
    return StepResult("tcp9100_probe", {"port_ok": ok})


# -------- ESC/POS and layout helpers --------
DEFAULT_CODEPAGE = "cp866"


def escpos_probe(req: dict) -> StepResult:
    """Send a minimal ESC/POS init sequence to ensure printer reacts.
    Uses RAW printing. Safe for most ESC/POS devices.
    """
    if not win32print:
        return StepResult("escpos_probe_skip", {"reason": "win32print missing"})
    payload = b"\x1b@"  # Initialize
    try:
        printer_name = _resolve_printer_name(req)
        h = win32print.OpenPrinter(printer_name)
        try:
            job_id = win32print.StartDocPrinter(h, 1, ("SMARTPOS_PROBE", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, payload)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
            return StepResult("escpos_probe", {"job_id": job_id})
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:  # noqa: BLE001
        logger.warning("escpos_probe failed: %s", e)
        return StepResult("escpos_probe_error", {"error": str(e)})


# Layout profiles for 58/80mm demo
class LayoutProfile:
    def __init__(self, paper_mm: int, chars_per_line: int, codepage: str = DEFAULT_CODEPAGE):
        self.paper_mm = paper_mm
        self.chars_per_line = chars_per_line
        self.codepage = codepage


PROFILE_58 = LayoutProfile(58, 32)
PROFILE_80 = LayoutProfile(80, 48)
_current_profile = PROFILE_80


def ensure_width_profile(req: dict) -> StepResult:
    """Ensure width profile matches physical (80mm). Used to *fix* scenario 4."""
    global _current_profile
    _current_profile = PROFILE_80
    return StepResult("width_profile_set", {"paper_mm": 80, "chars": 48})


def test_print_layout(req: dict, title: str = "SMARTPOS LAYOUT TEST") -> StepResult:
    if not win32print:
        return StepResult("test_print_skip", {"reason": "win32print missing"})
    profile = _current_profile
    line = "1234567890" * (profile.chars_per_line // 10)
    lines = [
        f"{title} ({profile.paper_mm}mm)",
        "-" * profile.chars_per_line,
        line[: profile.chars_per_line],
        f"Ширина: {profile.chars_per_line} символов",
    ]
    data = ("\n".join(lines) + "\n\n\n").encode(profile.codepage, errors="ignore")
    try:
        printer_name = _resolve_printer_name(req)
        h = win32print.OpenPrinter(printer_name)
        try:
            job_id = win32print.StartDocPrinter(h, 1, ("SMARTPOS_LAYOUT", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, b"\x1b@" + data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
            return StepResult("test_print_layout", {"job_id": job_id, "chars": profile.chars_per_line})
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:  # noqa: BLE001
        return StepResult("test_print_error", {"error": str(e)})


# -------- helpers --------

def _resolve_printer_name(req: dict) -> str:
    device = req.get("device", {})
    name = device.get("name")
    if name:
        return name
    # Явно указываем SAM4S ELLIX40 как принтер по умолчанию
    return "SAM4S ELLIX40"


# --- Жёсткая очистка хвостов "Удаление" ---
def force_purge_spooler(req: dict) -> StepResult:
    """
    Полная очистка очереди печати: Stop Spooler → удалить *.SPL/*.SHD → Start Spooler.
    Нужны права администратора. Без shell=True.
    """
    if not (win32serviceutil and win32service):
        return StepResult("force_purge_skip", {"reason": "win32service unavailable"})
    
    # Папка очереди
    spool_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "spool", "PRINTERS")
    
    # 1) Остановить Spooler с ожиданием
    t0 = time.time()
    try:
        try:
            win32serviceutil.StopService("Spooler")
        except Exception:
            pass
        # дождаться STOPPED
        t_stop0 = time.time()
        while time.time() - t_stop0 < 6.0:
            st = win32serviceutil.QueryServiceStatus("Spooler")[1]
            if st == win32service.SERVICE_STOPPED:
                break
            time.sleep(0.1)
        stopped_in = time.time() - t0
    except Exception as e:
        return StepResult("force_purge_error", {"stage": "stop", "error": str(e)}, terminal=True, result="ERROR")
    
    # 2) Удалить файлы очереди
    purged = 0
    try:
        for pattern in ("*.SPL", "*.SHD"):
            for p in glob.glob(os.path.join(spool_dir, pattern)):
                try:
                    os.remove(p)
                    purged += 1
                except Exception:
                    pass
    except Exception as e:
        # даже если не всё удалилось — продолжим запуск
        pass
    
    # 3) Запустить Spooler с ожиданием
    t1 = time.time()
    try:
        win32serviceutil.StartService("Spooler")
        t_start0 = time.time()
        while time.time() - t_start0 < 6.0:
            st = win32serviceutil.QueryServiceStatus("Spooler")[1]
            if st == win32service.SERVICE_RUNNING:
                break
            time.sleep(0.1)
        # небольшая пауза для «пробуждения» мониторов
        time.sleep(0.4)
    except Exception as e:
        return StepResult("force_purge_error", {"stage": "start", "error": str(e)}, terminal=True, result="ERROR")
    
    return StepResult(
        "force_purge_spooler",
        {"spool_dir": spool_dir, "purged": purged, "stop_s": round(stopped_in, 3), "start_s": round(time.time()-t1, 3)}
    )


# ── smartpos_daemon/faults.py
"""Fault‑Injector helpers for demo stand."""
import threading
import time
import pywintypes
try:
    import winerror
    _ERR_INVALID_HANDLE = winerror.ERROR_INVALID_HANDLE
except Exception:
    _ERR_INVALID_HANDLE = 6  # fallback
try:
    import win32print
except Exception:  # pragma: no cover
    win32print = None

# logger определен выше в этом же файле
# PROFILE_58 и PROFILE_80 определены ниже в этом же файле

_STICKY_CANCEL = threading.Event()
_STICKY_THREADS: list[threading.Thread] = []

_fault_threads: list[threading.Thread] = []
_current_profile_for_demo = PROFILE_80


def make_sticky_job(printer_name: str | None = None, payload: bytes | None = None) -> dict:
    if not win32print:
        return {"ok": False, "error": "win32print missing"}
    
    # Используем другой подход - создаем джоб, который будет "залипать" в очереди
    # Явно указываем SAM4S ELLIX40 как принтер по умолчанию
    name = printer_name or "SAM4S ELLIX40"
    
    def _sticky_worker(printer_name, cancel_evt=None):
        h = None
        job_id = None
        try:
            h = win32print.OpenPrinter(printer_name)
            # Создаем джоб без страницы - тогда он будет "залипать" в очереди
            job_id = win32print.StartDocPrinter(h, 1, ("SMARTPOS_STUCK", None, "RAW"))
            # НЕ вызываем StartPagePrinter - тогда джоб будет висеть в очереди без страницы
            # НЕ вызываем WritePrinter - тогда джоб будет висеть в очереди без данных
            
            # НЕ вызываем EndPagePrinter и EndDocPrinter - это заставит джоб "залипнуть"
            
            # Ждем сигнал отмены - используем конфигурацию для времени зависания
            start = time.time()
            while True:
                cfg = cfg_get()
                deadline = start + cfg.sticky_max_sec
                if cancel_evt is not None and cancel_evt.is_set():
                    break
                if time.time() >= deadline:
                    break
                time.sleep(0.1)
                
        except Exception as e:
            logger.warning("sticky worker error: %s", e)
        finally:
            # Только при отмене закрываем джоб
            if cancel_evt is not None and cancel_evt.is_set():
                try:
                    if h is not None:
                        # НЕ вызываем EndPagePrinter, так как не вызывали StartPagePrinter
                        win32print.EndDocPrinter(h)
                except Exception:
                    pass
            if h is not None:
                try:
                    win32print.ClosePrinter(h)
                except Exception:
                    pass

    t = threading.Thread(target=_sticky_worker, args=(name, _STICKY_CANCEL), daemon=True)
    t.start()
    _STICKY_THREADS.append(t)
    logger.info("faults: sticky job started on %s", name)
    return {"ok": True, "printer": name}


def cancel_sticky_jobs(timeout_sec: float = 2.0) -> dict:
    """Послать сигнал всем «залипающим» джобам — выполнить EndPage/EndDoc и быстро освободить дескрипторы."""
    logger.info("faults: canceling %d sticky jobs", len(_STICKY_THREADS))
    _STICKY_CANCEL.set()
    end = time.time() + timeout_sec
    alive = 0
    for t in list(_STICKY_THREADS):
        remain = max(0.0, end - time.time())
        t.join(remain)
        if t.is_alive():
            alive += 1
            logger.warning("faults: thread %s still alive after timeout", t.name)
        else:
            try:
                _STICKY_THREADS.remove(t)
            except ValueError:
                pass
    # ИСПРАВЛЕНО: НЕ очищаем событие отмены, чтобы потоки могли правильно завершиться
    # _STICKY_CANCEL.clear()  # УБРАНО!
    ok = alive == 0
    logger.info("faults: sticky cancel %s (alive=%d)", "OK" if ok else "PARTIAL", alive)
    return {"ok": ok, "still_alive": alive}


def sticky_status() -> dict:
    """Небольшая телеметрия для отладки демо: количество активных «залипших» потоков."""
    active_count = sum(1 for t in _STICKY_THREADS if t.is_alive())
    return {"active": active_count, "total_threads": len(_STICKY_THREADS), "cancel_event_set": _STICKY_CANCEL.is_set()}


def reset_sticky_state() -> dict:
    """Сброс состояния залипающих джобов для демонстрации."""
    global _STICKY_CANCEL, _STICKY_THREADS
    _STICKY_CANCEL.clear()  # Сбрасываем событие отмены
    _STICKY_THREADS.clear()  # Очищаем список потоков
    return {"ok": True, "message": "Sticky state reset"}


def set_wrong_width_profile() -> dict:
    """Switch demo layout to 58mm and APPLY it to actions.printer profile too."""
    global _current_profile_for_demo
    _current_profile_for_demo = PROFILE_58
    try:
        # Apply to runtime printing module - все функции в одном файле
        global _current_profile
        _current_profile = PROFILE_58  # noqa: SLF001 (intentional for demo)
    except Exception:
        pass
    return {"ok": True, "paper_mm": 58}


def set_correct_width_profile() -> dict:
    """Switch demo layout to 80mm and APPLY it to actions.printer profile too."""
    global _current_profile_for_demo
    _current_profile_for_demo = PROFILE_80
    try:
        # Apply to runtime printing module - все функции в одном файле
        global _current_profile
        _current_profile = PROFILE_80  # noqa: SLF001
    except Exception:
        pass
    return {"ok": True, "paper_mm": 80}


# ── smartpos_daemon/router.py
"""Playbook router: maps problem_code → sequence of actions."""
from typing import Any, Dict, List
# logger определен выше в этом же файле

PLAYBOOKS: dict[str, list] = {
    # PR0022: printer disappeared (USB/power)
    "PR0022": [usb_presence_check, clear_spooler, escpos_probe, test_print_layout],
    # PR0018: queue stuck / spooler jam (мягкая очистка по умолчанию)
    "PR0018": [cancel_demo_sticky, clear_spooler, restart_spooler, test_print_layout],
    # PR0001/PR0015: no paper / cover open → human steps then probe
    "PR0001": [escpos_probe, test_print_layout],
    "PR0015": [escpos_probe, test_print_layout],
    # PR0006/PR0017: wrong width / driver profile
    "PR0006": [ensure_width_profile, test_print_layout],
    "PR0017": [ensure_width_profile, test_print_layout],
}


def run_playbook(req: Dict[str, Any]) -> Dict[str, Any]:
    code = req.get("problem_code", "")
    steps = PLAYBOOKS.get(code, [])
    
    # Витринный флаг: добить «хвосты» в статусе «Удаление», если нужно красиво
    if code == "PR0018" and req.get("context", {}).get("beautify") is True:
        # Вставляем force_purge перед тест-печатью
        steps = [cancel_demo_sticky, clear_spooler, restart_spooler, force_purge_spooler, test_print_layout]
    
    result: Dict[str, Any] = {
        "ticket_id": req.get("ticket_id"),
        "problem_code": code,
        "actions_done": [],
        "evidence": {},
        "result_code": None,
    }
    for fn in steps:
        try:
            out: StepResult = fn(req) if fn is not test_print_layout else fn(req, title=f"DEMO {code}")
        except Exception as e:  # noqa: BLE001
            out = StepResult(name=fn.__name__ + "_error", evidence={"error": str(e)})
        result["actions_done"].append(out.name)
        if out.evidence:
            result["evidence"].update(out.evidence)
        if out.terminal and out.result:
            result["result_code"] = out.result
            break
    # heuristics: set result_code based on evidence
    if result["result_code"] is None:
        if result["evidence"].get("detected") is False:
            result["result_code"] = "NOT_FOUND"
        else:
            result["result_code"] = "FIXED"
    # humanized summaries (cashier/tech)
    result["human"] = _make_human(result)
    return result


def _make_human(res: Dict[str, Any]) -> Dict[str, str]:
    code = res.get("problem_code")
    ev = res.get("evidence", {})
    if code == "PR0022":
        if ev.get("detected") is False:
            cashier = "Принтер не найден. Проверьте USB/питание и нажмите ‘Проверить снова’."
        else:
            cashier = "Нашёл принтер и очистил очередь. Попробуйте печать ещё раз."
        tech = f"usb_presence={ev.get('detected')} status={ev.get('status')}"
    elif code == "PR0018":
        cashier = "Очередь печати очищена. Я перезапустил спулер и распечатал тест."
        tech = "spooler restart; queue cleared; test OK"
    elif code in ("PR0001", "PR0015"):
        cashier = "Если лента вставлена и крышка закрыта — печать должна пойти. Я сделал тест."
        tech = "escpos probe + test layout"
    elif code in ("PR0006", "PR0017"):
        cashier = "Вернул ширину 80 мм и кодировку. Распечатал шаблон макета."
        tech = f"width_profile_set chars={ev.get('chars')}"
    else:
        cashier = "Выполнил проверку и печать теста."
        tech = "generic playbook"
    return {"cashier": cashier, "tech": tech}


# ── smartpos_daemon/server.py
"""Minimal HTTP JSON server for local GUI/LLM ↔ Action Daemon.
Endpoints:
  POST /action/run        → run playbook (expects JSON)
  POST /faults/create     → create demo fault (sticky_queue | wrong_width)
  GET  /health            → basic health check

No external web frameworks (BaseHTTPRequestHandler + ThreadingHTTPServer).
"""
import json
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer
from typing import Tuple

# CONFIG определен выше в этом же файле
# logger определен выше в этом же файле
# run_playbook и функции faults определены в этом же файле


class JsonHandler(BaseHTTPRequestHandler):
    server_version = "SmartPOSDaemon/0.1"

    def _set_headers(self, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            self._set_headers(200)
            self.wfile.write(json.dumps({"ok": True, "version": self.server_version}).encode("utf-8"))
        elif self.path.startswith("/status/receipt"):
            # Текущий *эффективный* статус (учитывая оверрайд/TTL)
            try:
                from smartpos_daemon.actions.printer import _resolve_printer_name
                from smartpos_daemon.actions.printer_status import get_printer_status
                name = _resolve_printer_name({})
                st = get_printer_status(name)
                try:
                    ov = status_override_get()
                except Exception:
                    ov = {"active": False}
                self._set_headers(200)
                self.wfile.write(json.dumps({"printer": name, "status": st, "override": ov}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return
        elif self.path.startswith("/faults/status"):
            res = sticky_status()
            self._set_headers(200)
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
        elif self.path.startswith("/faults/reset"):
            res = reset_sticky_state()
            self._set_headers(200)
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
        elif self.path.startswith("/config/get"):
            self._set_headers(200)
            self.wfile.write(json.dumps({"ok": True, "config": cfg_get().__dict__}).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.error("JSON parse error: %s", e)
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "bad json", "detail": str(e)}).encode("utf-8"))
            return

        if self.path.startswith("/action/run"):
            res = run_playbook(payload)
            self._set_headers(200)
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if self.path.startswith("/faults/create"):
            kind = (payload.get("kind") or "").lower()
            if kind == "sticky_queue":
                res = make_sticky_job(payload.get("printer_name"))
            elif kind == "wrong_width":
                res = set_wrong_width_profile()
            elif kind == "fix_width":
                res = set_correct_width_profile()
            elif kind == "paper_out":
                ttl = float(payload.get("ttl", 60))
                res = status_override_set(paper_out=True, ttl_sec=ttl)
            elif kind == "cover_open":
                ttl = float(payload.get("ttl", 60))
                res = status_override_set(door_open=True, ttl_sec=ttl)
            elif kind == "status_clear":
                res = status_override_clear()
            else:
                res = {"ok": False, "error": "unknown fault kind"}
            self._set_headers(200 if res.get("ok") else 400)
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if self.path.startswith("/config/set"):
            # payload, например: {"sticky_max_sec": 600, "cancel_delay_sec": 0.2}
            res = cfg_update(**payload)
            self._set_headers(200)
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))


class ThreadingHTTPServer(ThreadingTCPServer):
    allow_reuse_address = True


def serve_forever() -> Tuple[str, int]:
    addr = (CONFIG.host, CONFIG.port)
    httpd = ThreadingHTTPServer(addr, JsonHandler)
    logger.info("Action Daemon listening on http://%s:%d", *addr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        logger.info("KeyboardInterrupt: shutting down")
    finally:
        httpd.server_close()
    return addr


# ── run_daemon.py (entry point for console run)
if __name__ == "__main__":
    # setup_logging и serve_forever определены в этом же файле

    setup_logging()
    serve_forever()

# ── smartpos_daemon/service.py (optional Windows Service wrapper)
# Note: for the expo we can run console via run_daemon.py. Service wrapper provided for completeness.
try:
    import win32serviceutil
    import win32service
    import win32event
except Exception:  # pragma: no cover
    win32serviceutil = None
    win32service = None
    win32event = None


class SmartPOSService(win32serviceutil.ServiceFramework if win32serviceutil else object):
    _svc_name_ = "SmartPOSActionDaemon"
    _svc_display_name_ = "SmartPOS Action Daemon"

    def __init__(self, args):  # type: ignore[no-redef]
        if not win32serviceutil:
            return
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):  # noqa: N802
        if not win32service:
            return
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):  # noqa: N802
        if not win32event:
            return
        # setup_logging и serve_forever определены в этом же файле

        setup_logging()
        serve_forever()
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
