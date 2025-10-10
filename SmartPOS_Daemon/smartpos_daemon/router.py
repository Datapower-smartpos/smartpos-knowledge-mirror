# smartpos_daemon/router.py
from .actions import (
    clear_spooler,
    restart_spooler,   # это обёртка вокруг sync-версии
    tcp9100_probe,
    usb_presence_check,
    escpos_probe,
    test_print_layout,
    ensure_width_profile,
    cancel_demo_sticky,   # ← добавить
    soft_purge_printer,
    read_printer_status,
)
# Если используешь отмену инжектора позже:
# from .faults import cancel_sticky_jobs


PLAYBOOKS = {
    "PR0022": [usb_presence_check, clear_spooler, escpos_probe, test_print_layout],
    "PR0018": [cancel_demo_sticky, clear_spooler, restart_spooler, test_print_layout],
    "PR0001": [read_printer_status, escpos_probe, test_print_layout],
    "PR0015": [read_printer_status, escpos_probe, test_print_layout],
    "PR0006": [ensure_width_profile, test_print_layout],
    "PR0017": [ensure_width_profile, test_print_layout],
}


def run_playbook(req):
    code = req["problem_code"]
    steps = PLAYBOOKS.get(code, [])
    
    # Опции витрины для PR0018:
    # context.purge: "soft" | "hard" | "auto"
    # (совместимость) context.beautify=true == "hard"
    if code == "PR0018":
        base = [cancel_demo_sticky, clear_spooler, restart_spooler]
        purge = (req.get("context", {}).get("purge")
                 or ("hard" if req.get("context", {}).get("beautify") else None))
        if purge == "soft":
            steps = base + [soft_purge_printer, test_print_layout]
        elif purge == "hard":
            steps = base + [force_purge_spooler, test_print_layout]
        elif purge == "auto":
            steps = base + [soft_purge_printer, force_purge_spooler, test_print_layout]
        else:
            steps = base + [test_print_layout]
    
    res = {"actions_done": [], "evidence": {}}
    for step in steps:
        out = step(req)
        res["actions_done"].append(out.name)
        res["evidence"].update(out.evidence)
        if out.terminal:
            res.update({"result_code": out.result})
            break
    return res


# (опционально) Если у вас ниже есть _make_human – добавьте обработку статуса:
#   - если paper_out=True → подсказать «вставьте ленту»,
#   - если door_open=True → «закройте крышку»,
#   источник override/winspool брать из evidence["source"].