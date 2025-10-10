# smartpos_daemon/actions/printer.py
import win32print, win32serviceutil
import time
import win32service
import socket
import logging
import os, glob

logger = logging.getLogger(__name__)

class StepResult:
    def __init__(self, name, evidence=None, result=None, terminal=False):
        self.name = name; self.evidence = evidence or {}; self.result = result; self.terminal = terminal


def clear_spooler(req):
    """Delete all jobs from default printer queue (returns deleted count)."""
    h = win32print.OpenPrinter(win32print.GetDefaultPrinter())
    deleted = 0
    try:
        for job in win32print.EnumJobs(h, 0, 999, 1):
            try:
                win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                deleted += 1
            except Exception:
                pass
    finally:
        win32print.ClosePrinter(h)
    return StepResult("print_queue_clear", {"deleted": deleted})

def clear_queue_fast(printer_name=None):
    h = win32print.OpenPrinter(printer_name or win32print.GetDefaultPrinter())
    deleted = 0
    try:
        for job in win32print.EnumJobs(h, 0, 999, 1):
            try:
                win32print.SetJob(h, job["JobId"], 0, None, win32print.JOB_CONTROL_DELETE)
                deleted += 1
            except Exception as e:
                # логируй e, но продолжай
                pass
    finally:
        win32print.ClosePrinter(h)
    return {"deleted": deleted}

def has_long_running_jobs(printer_name=None, threshold_sec=3.0):
    h = win32print.OpenPrinter(printer_name or win32print.GetDefaultPrinter())
    try:
        snapshot = {j["JobId"]: time.time() for j in win32print.EnumJobs(h, 0, 999, 1)}
    finally:
        win32print.ClosePrinter(h)
    time.sleep(threshold_sec)
    h = win32print.OpenPrinter(printer_name or win32print.GetDefaultPrinter())
    try:
        stuck = []
        for j in win32print.EnumJobs(h, 0, 999, 1):
            if j["JobId"] in snapshot:
                stuck.append(j["JobId"])
        return {"stuck_jobs": stuck}
    finally:
        win32print.ClosePrinter(h)


def restart_spooler_sync(timeout_stop=5.0, timeout_start=5.0):
    svc = "Spooler"
    # stop
    try:
        win32serviceutil.StopService(svc)
    except Exception:
        pass  # может уже быть остановлен
    t0 = time.time()
    while time.time() - t0 < timeout_stop:
        try:
            status = win32serviceutil.QueryServiceStatus(svc)[1]
            if status == win32service.SERVICE_STOPPED:
                break
        except Exception:
            break
        time.sleep(0.1)
    # start
    win32serviceutil.StartService(svc)
    t1 = time.time()
    while time.time() - t1 < timeout_start:
        status = win32serviceutil.QueryServiceStatus(svc)[1]
        if status == win32service.SERVICE_RUNNING:
            break
        time.sleep(0.1)
    time.sleep(0.5)  # демо-пауза, чтобы мониторы портов «проснулись»
    return {
        "stopped_in": round(t1 - t0, 3),
        "running_in": round(time.time() - t1, 3),
    }


def restart_spooler(req):
    """Playbook wrapper: restart spooler and return StepResult with timings."""
    try:
        metrics = restart_spooler_sync()
        return StepResult("spooler_restart", metrics)
    except Exception as e:  # noqa: BLE001
        need_admin = ("OpenSCManager" in str(e)) or ("Access is denied" in str(e))
        return StepResult("spooler_restart_error", {"error": str(e), "need_admin": need_admin})


def cancel_demo_sticky(req):
    """Сигнал инжектору: отпустить дескрипторы залипающих джобов (EndPage/EndDoc)."""
    # 1) сначала пробуем «правильный» модуль faults
    try:
        from smartpos_daemon import faults as f
        res = f.cancel_sticky_jobs()
        return StepResult("sticky_cancel", {"alive_after_cancel": res.get("still_alive", 0), "path": "faults"})
    except Exception as e1:
        # 2) если инжектор живёт внутри run_daemon.py — гасим его
        try:
            import run_daemon as rd  # у тебя он точно есть
            res = rd.cancel_sticky_jobs()
            return StepResult("sticky_cancel", {"alive_after_cancel": res.get("still_alive", 0), "path": "run_daemon"})
        except Exception as e2:
            return StepResult("sticky_cancel_error", {"errors": [str(e1), str(e2)]})


# --- МЯГКАЯ зачистка очереди без прав администратора ---
def soft_purge_printer(req: dict) -> StepResult:
    """
    «Мягкая» зачистка: PRINTER_CONTROL_PURGE через SetPrinter.
    Обычно работает без админ-прав и убирает хвосты «Удаление».
    """
    if not win32print:
        return StepResult("printer_soft_purge_skip", {"reason": "win32print missing"})
    name = _resolve_printer_name(req)
    try:
        h = win32print.OpenPrinter(name)
        try:
            win32print.SetPrinter(h, 0, None, win32print.PRINTER_CONTROL_PURGE)
            return StepResult("printer_soft_purge", {"purge": "ok", "printer": name})
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:  # noqa: BLE001
        return StepResult("printer_soft_purge_error", {"error": str(e)})


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
        line,
        f"Chars per line: {profile.chars_per_line}",
        "-" * profile.chars_per_line,
        "END TEST",
    ]
    try:
        printer_name = _resolve_printer_name(req)
        h = win32print.OpenPrinter(printer_name)
        try:
            job_id = win32print.StartDocPrinter(h, 1, (title, None, "RAW"))
            win32print.StartPagePrinter(h)
            for line_text in lines:
                win32print.WritePrinter(h, (line_text + "\n").encode(profile.codepage))
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
            return StepResult("test_print_layout", {"job_id": job_id, "chars": profile.chars_per_line})
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:  # noqa: BLE001
        logger.warning("test_print_layout failed: %s", e)
        return StepResult("test_print_error", {"error": str(e)})


def _resolve_printer_name(req: dict) -> str:
    """Resolve printer name from request or use default."""
    device = req.get("device", {})
    printer_name = device.get("printer_name")
    if printer_name:
        return printer_name
    return win32print.GetDefaultPrinter()


if __name__ == "__main__":
    # Тестирование функций
    print("Тестирование функций принтера...")
    
    # Тест очистки очереди печати
    print("\n1. Тест clear_spooler:")
    try:
        result = clear_spooler(None)
        print(f"Результат: {result.name}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Тест быстрой очистки очереди
    print("\n2. Тест clear_queue_fast:")
    try:
        result = clear_queue_fast()
        print(f"Удалено заданий: {result['deleted']}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Тест проверки зависших заданий
    print("\n3. Тест has_long_running_jobs:")
    try:
        result = has_long_running_jobs()
        print(f"Зависшие задания: {result['stuck_jobs']}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Тест перезапуска службы печати (осторожно!)
    print("\n4. Тест restart_spooler_sync (только если нужно):")
    print("ВНИМАНИЕ: Этот тест перезапустит службу печати!")
    response = input("Продолжить? (y/N): ")
    if response.lower() == 'y':
        try:
            result = restart_spooler_sync()
            print(f"Остановка за: {result['stopped_in']}с, запуск за: {result['running_in']}с")
        except Exception as e:
            print(f"Ошибка: {e}")
    else:
        print("Тест пропущен.")
    
    print("\nТестирование завершено.")