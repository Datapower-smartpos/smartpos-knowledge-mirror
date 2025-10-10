# actions/printer_status.py
import time
import win32print
try:
    from smartpos_daemon import faults as _faults
except Exception:
    _faults = None
from smartpos_daemon.actions.printer import StepResult  # единый формат шага
from smartpos_daemon.actions.printer import _resolve_printer_name  # используем ваш резолвер

PRINTER_STATUS_PAPER_OUT = 0x00000020
PRINTER_STATUS_DOOR_OPEN = 0x00400000


def get_printer_status(printer_name: str) -> dict:
    h = win32print.OpenPrinter(printer_name)
    try:
        info = win32print.GetPrinter(h, 2)
        st = info["Status"]
        return {
            "paper_out": bool(st & PRINTER_STATUS_PAPER_OUT),
            "door_open": bool(st & PRINTER_STATUS_DOOR_OPEN),
        }
    finally:
        win32print.ClosePrinter(h)


def _apply_override(status: dict) -> tuple[dict, bool]:
    """Наложить эмуляцию статуса (если активна). Возвращает (статус, overridden?)."""
    overridden = False
    if _faults is None:
        return status, False
    try:
        ov = _faults.status_override_get()
        if ov.get("active"):
            if ov.get("paper_out") is not None:
                status["paper_out"] = bool(ov["paper_out"])
                overridden = True
            if ov.get("door_open") is not None:
                status["door_open"] = bool(ov["door_open"])
                overridden = True
    except Exception:
        pass
    return status, overridden


def read_printer_status(req: dict) -> StepResult:
    """Playbook-шаг: получить (с учётом оверрайда) статус принтера."""
    try:
        name = _resolve_printer_name(req)
        st = get_printer_status(name)
        st, ov = _apply_override(st)
        st["source"] = "override" if ov else "winspool"
        return StepResult("printer_status", st)
    except Exception as e:
        return StepResult("printer_status_error", {"error": str(e)})