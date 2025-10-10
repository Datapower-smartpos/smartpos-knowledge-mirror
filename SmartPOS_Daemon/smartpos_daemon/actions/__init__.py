# smartpos_daemon/actions/__init__.py
from .printer import (
    StepResult,
    clear_spooler,
    restart_spooler,
    usb_presence_check,
    tcp9100_probe,
    escpos_probe,
    test_print_layout,
    ensure_width_profile,
    cancel_demo_sticky,   # ← добавить
    soft_purge_printer,
)
from .printer_status import read_printer_status
