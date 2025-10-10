# smartpos_daemon/faults.py
"""
Помощники инжектора неисправностей для демо-стенда (офлайн).
- «Залипающий» печатный джоб, удерживающий StartDoc/StartPage открытыми до сигнала отмены
- Переключение профиля ширины чека 58↔80 мм с ПРИМЕНЕНИЕМ к активному модулю печати

Цели:
- Без shell=True, без multiprocessing
- Все дескрипторы закрываются при отмене, чтобы избежать долгого состояния «Удаление…»
"""

from __future__ import annotations

import time
import threading
from typing import Optional, Dict, List

try:
    import win32print
except Exception:  # pragma: no cover (не Windows-среда)
    win32print = None  # type: ignore[assignment]

from run_daemon import logger
from smartpos_daemon.actions.printer import PROFILE_58, PROFILE_80

__all__ = [
    "make_sticky_job",
    "cancel_sticky_jobs",
    "set_wrong_width_profile",
    "set_correct_width_profile",
    "sticky_status",
    "status_override_set",
    "status_override_get",
    "status_override_clear",
]

# Состояние рантайма
_fault_threads: List[threading.Thread] = []
_sticky_ctxs: List[Dict] = []  # [{thread, cancel: threading.Event, printer}]
_current_profile_for_demo = PROFILE_80
_status_override = {"until": 0.0, "paper_out": None, "door_open": None}  # TTL-оверрайд статуса


# ---------- вспомогательные функции ----------

def _default_printer_name() -> str:
    """Вернуть имя принтера по умолчанию (если доступен win32print)."""
    if win32print:
        try:
            return win32print.GetDefaultPrinter()
        except Exception:
            pass
    return "DEFAULT"


# ---------- «Залипающий» джоб (демонстрация зависшей очереди) ----------

def make_sticky_job(printer_name: Optional[str] = None, payload: Optional[bytes] = None) -> dict:
    """
    Создать «залипающий» RAW-джоб: держим открытыми StartDoc/StartPage (без End*),
    пока не придёт сигнал отмены. Делается ОТМЕНЯЕМЫМ, чтобы демо оставалось быстрым.

    Возвращает: {"ok": bool, "printer": name} при успехе, либо {"ok": False, "error": "..."}.
    """
    if not win32print:
        return {"ok": False, "error": "win32print missing"}

    name = printer_name or _default_printer_name()
    payload = payload or b"\x1b@"
    cancel_evt = threading.Event()

    def _worker(pname: str, cancel: threading.Event):
        h = None
        try:
            h = win32print.OpenPrinter(pname)
            win32print.StartDocPrinter(h, 1, ("SMARTPOS_STUCK", None, "RAW"))
            # НЕ вызываем StartPagePrinter - тогда джоб будет висеть в очереди без страницы
            # НЕ вызываем WritePrinter - тогда джоб будет висеть в очереди без данных
            # НЕ вызываем EndPagePrinter и EndDocPrinter - это заставит джоб "залипнуть"
            # Ждём сигнал отмены (≤ 180 с как предохранитель)
            end = time.time() + 180.0
            while time.time() < end and not cancel.is_set():
                time.sleep(0.1)
        except Exception as e:  # noqa: BLE001
            logger.warning("sticky job worker error: %s", e)
        finally:
            # Только при отмене закрываем джоб
            if cancel.is_set():
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

    t = threading.Thread(target=_worker, args=(name, cancel_evt), daemon=True)
    t.start()
    _fault_threads.append(t)
    _sticky_ctxs.append({"thread": t, "cancel": cancel_evt, "printer": name})
    logger.info("faults: sticky job started on %s", name)
    return {"ok": True, "printer": name}


def cancel_sticky_jobs(timeout_sec: float = 2.0) -> dict:
    """
    Послать сигнал всем «залипающим» джобам — выполнить EndPage/EndDoc и
    быстро освободить дескрипторы.
    Возвращает: {"ok": bool, "still_alive": int}
    """
    # Послать сигнал отмены
    for ctx in list(_sticky_ctxs):
        try:
            ctx["cancel"].set()
        except Exception:
            pass

    # Дождаться завершения с таймаутом
    end = time.time() + timeout_sec
    alive = 0
    for ctx in list(_sticky_ctxs):
        t: threading.Thread = ctx.get("thread")
        if not t:
            continue
        remain = max(0.0, end - time.time())
        t.join(remain)
        if t.is_alive():
            alive += 1
        else:
            try:
                _sticky_ctxs.remove(ctx)
            except ValueError:
                pass

    ok = alive == 0
    logger.info("faults: sticky cancel %s (alive=%d)", "OK" if ok else "PARTIAL", alive)
    return {"ok": ok, "still_alive": alive}


def sticky_status() -> dict:
    """Небольшая телеметрия для отладки демо: количество активных «залипших» потоков."""
    return {"active": sum(1 for c in _sticky_ctxs if c.get("thread") and c["thread"].is_alive())}


# ---------- Эмуляция статуса принтера (paper_out / door_open) ----------
def status_override_set(paper_out: bool | None = None, door_open: bool | None = None, ttl_sec: float = 60.0) -> dict:
    """Включить эмуляцию статуса принтера на ttl_sec секунд."""
    now = time.time()
    if paper_out is None and door_open is None:
        return {"ok": False, "error": "nothing to override"}
    _status_override.update({
        "paper_out": bool(paper_out) if paper_out is not None else _status_override["paper_out"],
        "door_open": bool(door_open) if door_open is not None else _status_override["door_open"],
        "until": now + float(ttl_sec),
    })
    return {"ok": True, "override": _status_override.copy()}

def status_override_get() -> dict:
    """Текущий оверрайд и признак активности (с авто-истечением TTL)."""
    now = time.time()
    active = _status_override["until"] > now
    if not active:
        # истёк — очищаем
        _status_override.update({"until": 0.0, "paper_out": None, "door_open": None})
    return {"active": active, "paper_out": _status_override["paper_out"], "door_open": _status_override["door_open"], "until": _status_override["until"]}

def status_override_clear() -> dict:
    """Полностью отключить эмуляцию статуса принтера."""
    _status_override.update({"until": 0.0, "paper_out": None, "door_open": None})
    return {"ok": True}


# ---------- Переключение профиля ширины (58 ↔ 80 мм) ----------

def set_wrong_width_profile() -> dict:
    """
    Переключить демо-профиль на 58 мм И применить его к активному модулю печати,
    чтобы следующая тест-печать сразу использовала 58 мм (эффект «обрезанного» текста).
    """
    global _current_profile_for_demo
    _current_profile_for_demo = PROFILE_58
    try:
        # Применить к живому модулю печати (локальный импорт, чтобы избежать циклов при импорте)
        from smartpos_daemon.actions import printer as _ap  # локальный импорт во избежание циклических зависимостей
        _ap._current_profile = PROFILE_58  # noqa: SLF001 (намеренно для демо)
    except Exception as e:  # noqa: BLE001
        logger.warning("faults: failed to apply 58mm profile to runtime: %s", e)
    logger.info("faults: width profile set to 58mm for demo")
    return {"ok": True, "paper_mm": 58}


def set_correct_width_profile() -> dict:
    """
    Вернуть профиль на 80 мм И применить его к активному модулю печати.
    """
    global _current_profile_for_demo
    _current_profile_for_demo = PROFILE_80
    try:
        from smartpos_daemon.actions import printer as _ap
        _ap._current_profile = PROFILE_80  # noqa: SLF001
    except Exception as e:  # noqa: BLE001
        logger.warning("faults: failed to apply 80mm profile to runtime: %s", e)
    logger.info("faults: width profile set to 80mm for demo")
    return {"ok": True, "paper_mm": 80}
