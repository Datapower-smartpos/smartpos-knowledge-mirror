"""
trace_wrappers_v2.py — трассировка COM/HID для SmartPOS USB Agent
Author: Разработчик суперпрограмм

Назначение:
- Оборачивает транспорты/активность для записи сырых байтов в ./traces/
- Управление — через config.json → policy.traces.{enabled,dir,max_dir_mb,file_rotate_kb}

Поддерживаемые обёртки:
- TracedSerialComTransport — поверх core.SerialComTransport (COM TX/RX)
- TracedHidActivity — duck-typing над HID активностью/транспортом: send/report → HID_TX, read/get_report → HID_RX

Пример включения в службе:
    from trace_wrappers_v2 import make_traced_serial_if_enabled, make_traced_hid_if_enabled
    base_serial = core.SerialComTransport()
    serial = make_traced_serial_if_enabled(base_serial, cfg.get('policy') or {})
    hida = core.NullHidActivity()
    hida = make_traced_hid_if_enabled(hida, cfg.get('policy') or {})
"""
from __future__ import annotations
import os, time, threading
from typing import Optional

try:
    import usb_agent_core as core  # type: ignore
except Exception:  # заглушка типов
    core = None  # type: ignore

class _Rotator:
    def __init__(self, base_dir: str, prefix: str, rotate_kb: int, dir_quota_mb: int):
        self.base_dir = base_dir
        self.prefix = prefix
        self.rotate_bytes = max(4*1024, rotate_kb*1024)
        self.dir_quota = max(5*1024*1024, dir_quota_mb*1024*1024)
        os.makedirs(base_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._cur_path = self._mk_path()
        self._cur = open(self._cur_path, 'ab', buffering=0)
        self._enforce_quota()

    def _mk_path(self) -> str:
        ts = time.strftime('%Y%m%d_%H%M%S')
        name = f"{self.prefix}_{ts}.bin"
        return os.path.join(self.base_dir, name)

    def _enforce_quota(self):
        # если суммарный размер > quota — удаляем старейшие файлы        
        files = []
        total = 0
        for n in os.listdir(self.base_dir):
            p = os.path.join(self.base_dir, n)
            if os.path.isfile(p):
                st = os.stat(p)
                files.append((st.st_mtime, p, st.st_size))
                total += st.st_size
        files.sort(key=lambda x: x[0])  # старые сначала
        while total > self.dir_quota and files:
            _, p, sz = files.pop(0)
            try:
                os.remove(p)
                total -= sz
            except OSError:
                break

    def write(self, blob: bytes):
        with self._lock:
            if self._cur.tell() + len(blob) > self.rotate_bytes:
                self._cur.close()
                self._cur_path = self._mk_path()
                self._cur = open(self._cur_path, 'ab', buffering=0)
                self._enforce_quota()
            try:
                self._cur.write(blob)
            except Exception:
                pass

    def close(self):
        with self._lock:
            try:
                self._cur.close()
            except Exception:
                pass

class TracedSerialComTransport:
    """Обёртка над core.SerialComTransport с записью TX/RX в traces/COM_*.bin"""
    def __init__(self, inner: 'core.SerialComTransport', base_dir: str, rotate_kb: int, dir_quota_mb: int):
        self._inner = inner
        self._tx = _Rotator(base_dir, 'COM_TX', rotate_kb, dir_quota_mb)
        self._rx = _Rotator(base_dir, 'COM_RX', rotate_kb, dir_quota_mb)

    # Прокси публичных методов, добавляем запись байтов
    def open(self, port: str, baud: int, timeout_ms: int):
        return self._inner.open(port, baud, timeout_ms)

    def close(self):
        try:
            self._tx.close(); self._rx.close()
        finally:
            return self._inner.close()

    def write(self, handle, data: bytes) -> int:
        try:
            self._tx.write(data)
        finally:
            return self._inner.write(handle, data)

    def read(self, handle, max_bytes: int, timeout_ms: int) -> bytes:
        data = self._inner.read(handle, max_bytes, timeout_ms)
        if data:
            try: self._rx.write(data)
            except Exception: pass
        return data

class TracedHidActivity:
    """Duck-typing обёртка HID: перехватывает send/report/read/get_report, пишет в HID_TX/HID_RX"""
    def __init__(self, inner: object, base_dir: str, rotate_kb: int, dir_quota_mb: int):
        self._inner = inner
        self._tx = _Rotator(base_dir, 'HID_TX', rotate_kb, dir_quota_mb)
        self._rx = _Rotator(base_dir, 'HID_RX', rotate_kb, dir_quota_mb)
    def __getattr__(self, name):
        return getattr(self._inner, name)
    def send(self, *args, **kwargs):
        payload = kwargs.get('data', None) or (args[0] if args else None)
        if isinstance(payload, (bytes, bytearray)):
            try: self._tx.write(bytes(payload))
            except Exception: pass
        return getattr(self._inner, 'send')(*args, **kwargs)
    def report(self, *args, **kwargs):
        payload = kwargs.get('data', None) or (args[0] if args else None)
        if isinstance(payload, (bytes, bytearray)):
            try: self._tx.write(bytes(payload))
            except Exception: pass
        return getattr(self._inner, 'report')(*args, **kwargs)
    def read(self, *args, **kwargs):
        data = getattr(self._inner, 'read')(*args, **kwargs)
        if isinstance(data, (bytes, bytearray)) and data:
            try: self._rx.write(bytes(data))
            except Exception: pass
        return data
    def get_report(self, *args, **kwargs):
        data = getattr(self._inner, 'get_report')(*args, **kwargs)
        if isinstance(data, (bytes, bytearray)) and data:
            try: self._rx.write(bytes(data))
            except Exception: pass
        return data

# Для совместимости внешних фабрик

def make_traced_serial_if_enabled(inner: 'core.SerialComTransport', policy: dict) -> 'core.SerialComTransport':
    tr = (policy or {}).get('traces') or {}
    if not tr.get('enabled'):
        return inner
    base = tr.get('dir', 'traces')
    rot_kb = int(tr.get('file_rotate_kb', 1024))
    quota = int(tr.get('max_dir_mb', 50))
    return TracedSerialComTransport(inner, base, rot_kb, quota)

def make_traced_hid_if_enabled(inner_hid: object, policy: dict) -> object:
    tr = (policy or {}).get('traces') or {}
    if not tr.get('enabled'):
        return inner_hid
    base = tr.get('dir', 'traces')
    rot_kb = int(tr.get('file_rotate_kb', 1024))
    quota = int(tr.get('max_dir_mb', 50))
    return TracedHidActivity(inner_hid, base, rot_kb, quota)
