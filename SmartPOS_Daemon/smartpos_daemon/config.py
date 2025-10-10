# smartpos_daemon/config.py
from dataclasses import dataclass
import threading

@dataclass
class RuntimeConfig:
    sticky_max_sec: float = 180.0      # было 180
    cancel_delay_sec: float = 0.5      # было 5.0 (сделаем быстрее по умолчанию)

_CFG = RuntimeConfig()
_LOCK = threading.RLock()

def get() -> RuntimeConfig:
    with _LOCK:
        return RuntimeConfig(**_CFG.__dict__)  # копия

def update(**kw) -> dict:
    changed = {}
    with _LOCK:
        for k, v in kw.items():
            if hasattr(_CFG, k) and v is not None:
                setattr(_CFG, k, float(v))
                changed[k] = float(v)
    return {"ok": True, "changed": changed, "current": _CFG.__dict__}
