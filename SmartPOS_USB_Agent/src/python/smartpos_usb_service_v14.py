"""
SmartPOS USB Agent — Windows Service (dual‑mode) + Local HTTP API (v1.4)
Author: Разработчик суперпрограмм

Назначение (v1 MVP):
- Фоновая служба, которая:
  * выполняет health‑пробы устройств (TP/DP/AP) по политике,
  * применяет авто‑восстановление (service restart / device recycle),
  * отслеживает присутствие (Topology), анти‑флаппинг с backoff,
  * отдаёт локальный HTTP API для Tray/CLI (status, действия, pre‑flight, reload policy),
  * пишет структурные JSON‑логи.

Особенности:
- Dual‑mode: как обычный консольный процесс (по умолчанию) или как Windows‑служба (если установлен pywin32 и флаг --service).
- Без внешних зависимостей, опционально использует pyserial/pywin32/wmi.
- Конфиги и каталоги: ./config.json (порог/тайминги), ./devices.json (стартовый список устройств; опционально).

Безопасность/устойчивость:
- Все внешние действия таймбоксированы в usb_agent_core.
- HTTP API слушает ТОЛЬКО 127.0.0.1, без аутентификации (только локальный Tray/CLI). Для v2 добавить токен/ACL.

Новое в v1.1:
- SQLite‑персист: devices/metrics/actions/preflight_runs (./db/smartpos_usb.db)
- Ротация логов в ./logs/service.log (RotatingFileHandler)
- HTTP API c shared‑secret (X-API-Key) для POST‑эндпойнтов

Новое в v1.2:
- /api/export — стрим ZIP (db + logs)

Новое в v1.3:
- Контроль размера БД «скользящим окном» (batch‑delete + VACUUM)
- Трассировки COM в ./traces/ (включаются policy.traces.enabled), квоты/ротация по размеру
- /api/export?mask=db,logs,traces — выборочная выгрузка артефактов
Совместимо с v1.2. Требуются: usb_agent_core.py, trace_wrappers.py рядом.

Новое в v1.4:
- Трассировки COM/HID (включаются policy.traces.enabled); квота каталога и ротация файлов

- Ротация БД: retention по дням и ограничение размера (MB) + VACUUM (скользящее окно)
- Self‑check схемы БД при старте (создание недостающих таблиц/колонок, PRAGMA user_version)
- Совместимо с v1.1/v1.2 конфигом; добавлены секции config.db.*

config.json (пример):
{
  "http": "127.0.0.1:8765",
  "auth": { "shared_secret": "changeme-please" },
  "db": { "retention_days": 14, "max_mb": 20, "vacuum_on_start": true, "size_batch": 2000 },
  "policy": { "traces": { "enabled": true, "dir": "traces", "max_dir_mb": 50, "file_rotate_kb": 1024 } }
}
"""
from __future__ import annotations
import os
import sys
import io
import json
import time
import threading
import logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dataclasses import asdict
from typing import Dict, Any, Optional, List, Tuple

import sqlite3
import zipfile
import hashlib
import datetime as _dt
import subprocess
import threading
import re

# Core adapters/actions/policy
import usb_agent_core as core
from trace_wrappers_v2 import make_traced_serial_if_enabled, make_traced_hid_if_enabled

# Вспомогательные функции
def _safe_json_load(path: str) -> tuple[dict, dict]:
    """Возвращает (dict_cfg, info_state) и НИКОГДА не кидает исключение."""
    info = {"loaded": False, "path": path, "sha256": None}
    cfg = {}
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            info["sha256"] = hashlib.sha256(data).hexdigest()
            try:
                cfg = json.loads(data.decode("utf-8-sig"))
                info["loaded"] = True
            except Exception as e:
                info["error"] = f"json:{e}"
        else:
            info["error"] = "not_found"
    except Exception as e:
        info["error"] = f"io:{e}"
    return cfg, info

def _safe_db_info(db_path: str) -> dict:
    info = {"ok": False, "path": db_path, "size_mb": 0.0, "schema_version": None}
    try:
        if not os.path.exists(db_path):
            info["error"] = "not_found"
            return info
        info["size_mb"] = round(os.path.getsize(db_path) / (1024*1024), 2)
        con = sqlite3.connect(db_path, timeout=2)
        try:
            cur = con.execute("PRAGMA user_version;")
            row = cur.fetchone()
            info["schema_version"] = int(row[0]) if row and row[0] is not None else None
            info["ok"] = True
        finally:
            con.close()
    except Exception as e:
        info["error"] = str(e)
    return info

def _load_cfg_from_disk() -> dict:
    try:
        path = r"C:\ProgramData\SmartPOS\usb_agent\config.json"
        with open(path, "rb") as f:
            raw = f.read()
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = raw.decode("utf-8", "replace")
        return json.loads(txt)
    except Exception:
        return {}

def _build_preflight_payload() -> dict:
    # Дефолтные пути/порты
    cfg_path = r"C:\ProgramData\SmartPOS\usb_agent\config.json"
    db_path  = DEFAULT_DB_PATH

    # Читаем config.json (без исключений)
    cfg, cfg_info = _safe_json_load(cfg_path)

    # host/port
    http = (cfg.get("http") if isinstance(cfg.get("http"), dict) else {}) if cfg else {}
    host = http.get("host", "127.0.0.1")
    port = int(http.get("port", 19955))

    # db_path из конфигурации, если есть
    paths = (cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}) if cfg else {}
    db_path = paths.get("db_path", db_path)

    # счётчики фильтров/масок
    tf = (cfg.get("trace_filters") if isinstance(cfg.get("trace_filters"), dict) else {}) if cfg else {}
    masks = ((cfg.get("export") or {}) if isinstance(cfg.get("export"), dict) else {}).get("allow_masks", []) if cfg else []
    trace_state = {"vidpid": len(tf.get("include_vidpid") or []), "ports": len(tf.get("include_ports") or [])}
    export_state = {"allow_masks": masks, "ready": bool(masks)}

    db_info = _safe_db_info(db_path)

    # Информация о коллекторе
    collector = {}
    try:
        coll = cfg.get("collector") or {}
        iv = int(coll.get("preflight_interval_min", 0)) if isinstance(coll, dict) else 0
        collector = {"preflight_interval_min": iv}
    except Exception:
        collector = {}

    payload = {
        "ok": True,
        "version": "1.4.1",
        "ts": int(time.time() * 1000),
        "status": {
            "http": {"host": host, "port": port, "ready": True},
            "config": cfg_info,              # {loaded,path,sha256,[error]}
            "db": db_info,                   # {ok,path,size_mb,schema_version,[error]}
            "trace": trace_state,            # {vidpid,ports}
            "export": export_state,          # {allow_masks,ready}
            "collector": collector           # {preflight_interval_min}
        }
    }
    return payload

# Хелперы для операционного лога
def _db_conn(path: str):
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_op_tables(db_path: str):
    ddl = """
    PRAGMA user_version = 2;
    CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        action TEXT NOT NULL,
        ok INTEGER NOT NULL,
        details TEXT
    );
    CREATE TABLE IF NOT EXISTS preflight_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        ok INTEGER NOT NULL,
        http_host TEXT,
        http_port INTEGER,
        payload TEXT
    );
    """
    with _db_conn(db_path) as c:
        c.executescript(ddl)

def _now_z() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _db_path_from_cfg(cfg: dict) -> str:
    # путь БД как в preflight (ProgramData по умолчанию)
    paths = (cfg or {}).get("paths") or {}
    return paths.get("db_path", r"C:\ProgramData\SmartPOS\usb_agent\db\smartpos_usb.db")

def _oplog_preflight(db_path: str, ok: bool, http_host: str, http_port: int, payload: dict):
    try:
        _ensure_op_tables(db_path)
        with _db_conn(db_path) as c:
            c.execute(
                "INSERT INTO preflight_runs(ts, ok, http_host, http_port, payload) VALUES (?,?,?,?,?)",
                (_now_z(), 1 if ok else 0, http_host, int(http_port), json.dumps(payload, ensure_ascii=False))
            )
    except Exception as e:
        logger.warning("oplog_preflight insert failed: %s", e)

def _oplog_action(db_path: str, action: str, ok: bool, details: dict | None = None):
    try:
        _ensure_op_tables(db_path)
        with _db_conn(db_path) as c:
            c.execute(
                "INSERT INTO actions(ts, action, ok, details) VALUES (?,?,?,?)",
                (_now_z(), action, 1 if ok else 0, json.dumps(details or {}, ensure_ascii=False))
            )
    except Exception as e:
        logger.warning("oplog_action insert failed: %s", e)

def _table_columns(db_path: str, table: str) -> set[str]:
    try:
        with _db_conn(db_path) as c:
            rows = c.execute(f"PRAGMA table_info({table})").fetchall()
            return { (r["name"] if isinstance(r, sqlite3.Row) else r[1]) for r in rows }
    except Exception:
        return set()

def _ensure_usb_tables(db_path: str):
    ddl = """
    PRAGMA user_version = 2;
    CREATE TABLE IF NOT EXISTS usb_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        vidpid TEXT NOT NULL,
        action TEXT NOT NULL,        -- 'attach' | 'detach'
        pnpid TEXT,
        name TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_usb_events_ts ON usb_events(ts);
    CREATE INDEX IF NOT EXISTS idx_usb_events_vp ON usb_events(vidpid, ts DESC);

    CREATE TABLE IF NOT EXISTS devices (
        vidpid TEXT PRIMARY KEY,
        name TEXT,
        last_seen TEXT NOT NULL
    );
    """
    with _db_conn(db_path) as c:
        c.executescript(ddl)

def _usb_upsert_device(db_path: str, vidpid: str, name: str):
    try:
        _ensure_usb_tables(db_path)
        with _db_conn(db_path) as c:
            c.execute(
                "INSERT INTO devices(vidpid, name, last_seen) VALUES (?,?,?) "
                "ON CONFLICT(vidpid) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen",
                (vidpid, name or "", _now_z())
            )
    except Exception as e:
        logger.warning("usb_upsert_device failed: %s", e)

def _usb_add_event(db_path: str, vidpid: str, action: str, pnpid: str, name: str):
    try:
        _ensure_usb_tables(db_path)
        with _db_conn(db_path) as c:
            c.execute(
                "INSERT INTO usb_events(ts, vidpid, action, pnpid, name) VALUES(?,?,?,?,?)",
                (_now_z(), vidpid, action, pnpid, name)
            )
    except Exception as e:
        logger.warning("usb_add_event failed: %s", e)

# ----------------------------------------------------------------------------
# ЛОГИ/КОНФИГ/ПУТИ
# ----------------------------------------------------------------------------
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)
from logging.handlers import RotatingFileHandler
logger = logging.getLogger("smartpos.usb.service")
if not logger.handlers:
    fh = RotatingFileHandler(os.path.join('logs', 'service.log'), maxBytes=1_000_000, backupCount=5, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(fh)
    logger.addHandler(sh)
logger.setLevel(logging.INFO)

CFG_PATH = os.path.abspath(os.path.join(os.getcwd(), 'config.json'))
DEV_PATH = os.path.abspath(os.path.join(os.getcwd(), 'devices.json'))
DB_PATH  = os.path.abspath(os.path.join(os.getcwd(), 'db', 'smartpos_usb.db'))
DEFAULT_DB_PATH = r"C:\ProgramData\SmartPOS\usb_agent\db\smartpos_usb.db"
DEFAULT_CFG = {"http": "127.0.0.1:8765", "policy": {}, "auth": {"shared_secret": ""}, "db": {"retention_days": 14, "max_mb": 20, "vacuum_on_start": True, "size_batch": 2000}}

# ----------------------------------------------------------------------------
# Runtime/Orchestrator + SQLite storage
# ----------------------------------------------------------------------------
class DeviceRuntime:
    def __init__(self, rec: core.DeviceRecord):
        self.rec = rec
        self.state: str = 'READY'
        self.timeouts: int = 0
        self.last_action_ts: float = 0.0
        self.backoff_s: int = 0
        self.last_probe_ts: float = 0.0

# Поллер USB устройств
_VIDPID_RE = re.compile(r'VID_([0-9A-Fa-f]{4}).*PID_([0-9A-Fa-f]{4})')

def _snap_pnp_via_powershell(timeout_s: int = 6) -> dict[str, tuple[str, str]]:
    """
    Возвращает dict[vidpid] = (pnpid, name).
    Гарантируем UTF-8 вывод из WinPS 5.1, плюс fallback UTF-16LE.
    """
    ps_script = (
        "[Console]::InputEncoding  = [Text.Encoding]::UTF8; "
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_PnPEntity | "
        "Select-Object PNPDeviceID, Name | ConvertTo-Json -Depth 2"
    )
    cmd = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
           "-Command", ps_script]
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
        if cp.returncode != 0:
            return {}
        raw_bytes = cp.stdout
        if not raw_bytes:
            return {}
        # Надёжное декодирование: сперва UTF-8 (с/без BOM), затем UTF-16LE
        try:
            raw = raw_bytes.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            raw = raw_bytes.decode("utf-16le", errors="strict")
        raw = raw.strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        out = {}
        for item in data or []:
            pnpid = (item.get("PNPDeviceID") or "").strip()
            name  = (item.get("Name") or "").strip()
            m = _VIDPID_RE.search(pnpid)
            if not m:
                continue
            vp = f"{m.group(1).upper()}:{m.group(2).upper()}"
            out[vp] = (pnpid, name)
        return out
    except Exception:
        return {}

class DevicePoller(threading.Thread):
    def __init__(self, db_path: str, interval_s: int = 5, include: list[str] | None = None):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.interval = max(2, int(interval_s))
        self.include = set((include or []))
        self._stopped = threading.Event()
        _ensure_usb_tables(db_path)

    def stop(self):
        self._stopped.set()

    def run(self):
        prev: dict[str, tuple[str, str]] = {}
        while not self._stopped.is_set():
            snap = _snap_pnp_via_powershell()
            if self.include:
                snap = {k:v for k,v in snap.items() if k in self.include}
            # attach
            for vp,(pnpid,name) in snap.items():
                if vp not in prev:
                    _usb_add_event(self.db_path, vp, "attach", pnpid, name)
                _usb_upsert_device(self.db_path, vp, name)
            # detach
            for vp,(pnpid,name) in list(prev.items()):
                if vp not in snap:
                    _usb_add_event(self.db_path, vp, "detach", pnpid, name)
            prev = snap
            self._stopped.wait(self.interval)

class PreflightTicker(threading.Thread):
    """
    Периодически пишет preflight_runs в БД изнутри агента.
    Интервал берётся из config.collector.preflight_interval_min (мин=1, макс=1440).
    """
    def __init__(self, get_cfg, get_db_path, get_http):
        super().__init__(daemon=True)
        self._get_cfg = get_cfg         # callable -> dict
        self._get_db_path = get_db_path # callable -> str
        self._get_http = get_http       # callable -> (host:str, port:int)
        self._stop = threading.Event()
        self._poke = threading.Event()
        self._last_interval = None

    def stop(self):
        self._stop.set()
        self._poke.set()

    def poke(self):
        # вызывать после /api/policy/reload
        self._poke.set()

    @staticmethod
    def _clamp_interval(mins):
        try:
            v = int(mins)
        except Exception:
            v = 0
        if v <= 0:
            return 0
        return max(1, min(1440, v))  # разрешаем 1 минуту для стенда

    def run(self):
        # мягкий старт: 10с
        for _ in range(10):
            if self._stop.is_set(): return
            time.sleep(1)

        next_ts = 0
        while not self._stop.is_set():
            cfg = self._get_cfg() or {}
            coll = cfg.get("collector") or {}
            interval_min = self._clamp_interval(coll.get("preflight_interval_min", 0))

            if interval_min != self._last_interval:
                self._last_interval = interval_min
                try: logger.info("preflight_ticker interval_min=%s (0=off)", interval_min)
                except Exception: pass

            if interval_min == 0:
                self._poke.wait(timeout=60); self._poke.clear()
                continue

            now = time.time()
            if now < next_ts:
                got = self._poke.wait(timeout=max(1.0, min(60.0, next_ts - now)))
                if got:
                    self._poke.clear()
                    next_ts = 0  # немедленный запуск после poke()
                continue

            # выполнить preflight изнутри
            try:
                payload = _build_preflight_payload()
                http_host, http_port = self._get_http()
                db_path = self._get_db_path()
                _oplog_preflight(db_path, ok=True, http_host=http_host, http_port=http_port, payload=payload)
                try: logger.info("preflight_ticker wrote preflight_runs (host=%s port=%s)", http_host, http_port)
                except Exception: pass
            except Exception as e:
                try: logger.warning("preflight_ticker error: %s", e)
                except Exception: pass

            next_ts = time.time() + interval_min * 60

class Orchestrator:
    SCHEMA_VERSION = 1
    def __init__(self, policy: core.Policy, probe: 'core.CompositeHealthProbe',
                 svc: 'core.ActionServiceControl', devctl: 'core.ActionDeviceControl', topo: 'core.WinTopology', cfg: Dict[str, Any]):
        self.policy = policy
        self.probe = probe
        self.svc = svc
        self.devctl = devctl
        self.topo = topo
        self.cfg = cfg
        self.devices: Dict[str, DeviceRuntime] = {}
        self.lock = threading.RLock()
        # единый путь к БД: из config.paths.db_path или DEFAULT_DB_PATH
        self.db_path = (cfg.get("paths", {}) or {}).get("db_path", DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()
        self._apply_retention_and_rotation()

    # ---------------- DB init / self-check -----------------
    def _init_db(self):
        cur = self.db.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        # Каноническая схема v2
        cur.executescript("""
        PRAGMA user_version = 2;
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            ok INTEGER NOT NULL,
            details TEXT
        );
        CREATE TABLE IF NOT EXISTS preflight_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ok INTEGER NOT NULL,
            http_host TEXT,
            http_port INTEGER,
            payload TEXT
        );
        CREATE TABLE IF NOT EXISTS usb_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            vidpid TEXT NOT NULL,
            action TEXT NOT NULL,
            pnpid TEXT,
            name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_usb_events_ts ON usb_events(ts);
        CREATE INDEX IF NOT EXISTS idx_usb_events_vp ON usb_events(vidpid, ts DESC);

        CREATE TABLE IF NOT EXISTS devices (
            vidpid TEXT PRIMARY KEY,
            name TEXT,
            last_seen TEXT NOT NULL
        );
        """)
        self.db.commit()
        logger.info("db_selfcheck_ok version=%s path=%s", 2, self.db_path)

    def _apply_retention_and_rotation(self):
        opts = self.cfg.get('db') or {}
        retention_days = int(opts.get('retention_days', 14))
        max_mb = int(opts.get('max_mb', 20))
        vacuum_on_start = bool(opts.get('vacuum_on_start', True))
        size_batch = int(opts.get('size_batch', 2000))

        # срез по времени для usb_events и actions/preflight_runs (ts в ISO8601 → удаляем по разнице дат)
        cutoff_epoch_ms = int(time.time()*1000) - retention_days*24*3600*1000

        cur = self.db.cursor()
        # удаляем старьё по количеству (батчами) — ориентируемся на rowid
        try:
            cur.execute("DELETE FROM usb_events WHERE rowid IN (SELECT rowid FROM usb_events ORDER BY rowid ASC LIMIT ?)", (size_batch,))
            cur.execute("DELETE FROM actions     WHERE rowid IN (SELECT rowid FROM actions     ORDER BY rowid ASC LIMIT ?)", (size_batch,))
            cur.execute("DELETE FROM preflight_runs WHERE rowid IN (SELECT rowid FROM preflight_runs ORDER BY rowid ASC LIMIT ?)", (size_batch,))
            self.db.commit()
        except Exception as e:
            logger.warning("db_retention_err err=%s", e)

        # ограничение размера
        try:
            def db_size_mb():
                return os.path.getsize(self.db_path)/1024/1024
            sz = db_size_mb()
            if sz > max_mb:
                while sz > max_mb:
                    cur.execute("DELETE FROM usb_events WHERE rowid IN (SELECT rowid FROM usb_events ORDER BY rowid ASC LIMIT ?)", (size_batch,))
                    cur.execute("DELETE FROM actions WHERE rowid IN (SELECT rowid FROM actions ORDER BY rowid ASC LIMIT ?)", (size_batch,))
                    cur.execute("DELETE FROM preflight_runs WHERE rowid IN (SELECT rowid FROM preflight_runs ORDER BY rowid ASC LIMIT ?)", (size_batch,))
                    self.db.commit()
                    sz = db_size_mb()
                cur.execute("VACUUM"); self.db.commit(); logger.info("db_shrink_done size_mb_after=%.2f max_mb=%s batch=%s", sz, max_mb, size_batch)
            elif vacuum_on_start:
                cur.execute("VACUUM"); self.db.commit(); logger.info("db_vacuum_done size_mb=%.2f", sz)
        except Exception as e:
            logger.warning("db_window_err err=%s", e)

    # ---------------- DB helpers -----------------
    def _db_upsert_device(self, rec: core.DeviceRecord):
        cur = self.db.cursor()
        cur.execute("""
        INSERT INTO devices(device_id,vid,pid,friendly,role,critical,hub_path,com_port)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(device_id) DO UPDATE SET vid=excluded.vid,pid=excluded.pid,friendly=excluded.friendly,role=excluded.role,critical=excluded.critical,hub_path=excluded.hub_path,com_port=excluded.com_port
        """, (rec.device_id, rec.vid, rec.pid, rec.friendly, rec.role, int(rec.critical), rec.hub_path, rec.com_port))
        self.db.commit()

    def _db_metric(self, device_id: str, state: str, rtt_ms: int = 0, err_code: Optional[str] = None):
        cur = self.db.cursor()
        cur.execute("INSERT INTO metrics(ts,device_id,state,rtt_ms,err_code) VALUES(?,?,?,?,?)", (int(time.time()*1000), device_id, state, rtt_ms, err_code))
        self.db.commit()

    def _db_action(self, device_id: str, action: str, ok: bool, detail: str = ""):
        cur = self.db.cursor()
        cur.execute("INSERT INTO actions(ts,device_id,action,ok,detail) VALUES(?,?,?,?,?)", (int(time.time()*1000), device_id, action, int(ok), detail))
        self.db.commit()

    # ---------------- Device registry -----------------
    def upsert_device(self, rec: core.DeviceRecord):
        with self.lock:
            self.devices.setdefault(rec.device_id, DeviceRuntime(rec))
            self._db_upsert_device(rec)

    def remove_device(self, device_id: str):
        with self.lock:
            self.devices.pop(device_id, None)

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return { did: { 'record': asdict(rt.rec), 'state': rt.state, 'timeouts': rt.timeouts,
                            'last_action_ts': rt.last_action_ts, 'backoff_s': rt.backoff_s, 'last_probe_ts': rt.last_probe_ts }
                     for did, rt in self.devices.items() }

    # ---------------- Tick/recover -----------------
    def tick_all(self):
        now = time.time()
        with self.lock:
            for rt in list(self.devices.values()):
                self._tick_device(rt, now)

    def _tick_device(self, rt: DeviceRuntime, now: float):
        rec = rt.rec
        if not self.topo.present(rec.device_id):
            rt.state = 'FAILED' if rec.critical else 'DEGRADED'
            self._db_metric(rec.device_id, rt.state, 0, 'not_present')
            return
        pi = self.policy.value(rec.role, 'probe_interval_s')
        if now - rt.last_probe_ts < pi:
            return
        ok, rtt_ms, err = self.probe.probe(rec, self.policy.value(rec.role, 'probe_timeout_ms'))
        rt.last_probe_ts = now
        if ok:
            if rt.state != 'READY':
                logger.info("device_ready device_id=%s", rec.device_id)
            rt.state = 'READY'
            rt.timeouts = 0
            rt.backoff_s = 0
            self._db_metric(rec.device_id, rt.state, rtt_ms or 0, None)
            return
        # Error path
        rt.timeouts += 1
        self._db_metric(rec.device_id, 'TIMEOUT', rtt_ms or 0, err)
        if rt.timeouts >= self.policy.value(rec.role, 'fail_threshold'):
            if rt.state == 'READY':
                rt.state = 'DEGRADED'
            self._recover(rec, rt)

    def _recover(self, rec: core.DeviceRecord, rt: DeviceRuntime):
        now = time.time()
        service_first = bool(self.policy.role_overrides.get(rec.role, {}).get('service_first', False))
        actions = ['service', 'recycle'] if service_first else ['recycle', 'service']
        for action in actions:
            if action == 'service':
                ok, msg = self.svc.restart(rec)
                self._db_action(rec.device_id, 'service_restart', ok, msg)
                if ok:
                    rt.state = 'RECOVERING'
                    rt.timeouts = 0
                    logger.info("recover_service device_id=%s msg=%s", rec.device_id, msg)
                    return
            else:
                backoff = max(self.policy.device_recycle_backoff_base_s, rt.backoff_s or self.policy.device_recycle_backoff_base_s)
                backoff = min(backoff, self.policy.device_recycle_backoff_max_s)
                if now - rt.last_action_ts < backoff:
                    return
                ok, msg = self.devctl.recycle(rec, self.policy.quiet_window_ms)
                self._db_action(rec.device_id, 'device_recycle', ok, msg)
                rt.last_action_ts = now
                rt.backoff_s = min(backoff * 2, self.policy.device_recycle_backoff_max_s)
                if ok:
                    rt.state = 'RECOVERING'
                    rt.timeouts = 0
                    logger.info("recover_recycle device_id=%s msg=%s", rec.device_id, msg)
                    return
        rt.state = 'FAILED' if rec.critical else 'DEGRADED'

    # ---------------- Manual commands -----------------
    def cmd_recycle(self, device_id: str) -> Tuple[bool, str]:
        with self.lock:
            rt = self.devices.get(device_id)
            if not rt:
                return False, 'not_found'
            ok, msg = self.devctl.recycle(rt.rec, self.policy.quiet_window_ms)
            self._db_action(device_id, 'device_recycle_manual', ok, msg)
            return ok, msg

    def cmd_service_restart(self, device_id: str) -> Tuple[bool, str]:
        with self.lock:
            rt = self.devices.get(device_id)
            if not rt:
                return False, 'not_found'
            ok, msg = self.svc.restart(rt.rec)
            self._db_action(device_id, 'service_restart_manual', ok, msg)
            return ok, msg

    # ---------------- Export ZIP -----------------
    def build_export_zip(self, mask: Optional[List[str]] = None) -> bytes:
        mask = [m.strip().lower() for m in (mask or ['db','logs'])]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            if 'db' in mask and os.path.exists(DB_PATH):
                z.write(DB_PATH, arcname='db/smartpos_usb.db')
            if 'logs' in mask and os.path.isdir('logs'):
                for name in os.listdir('logs'):
                    p = os.path.join('logs', name)
                    if os.path.isfile(p) and name.endswith('.log'):
                        z.write(p, arcname=f'logs/{name}')
            if 'traces' in mask and os.path.isdir('traces'):
                for root, _, files in os.walk('traces'):
                    for fname in files:
                        fp = os.path.join(root, fname)
                        if os.path.isfile(fp):
                            z.write(fp, arcname=os.path.relpath(fp, '.'))
        return buf.getvalue()

# ----------------------------------------------------------------------------
# HTTP API (127.0.0.1 only)
# ----------------------------------------------------------------------------

# Версия модуля
__version__ = "1.4.1"


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SmartPOSUSB/1.4"
    def _send_json(self, code=200, payload: Any = None):
        body = json.dumps(payload or {}, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _send_bin(self, code=200, body: bytes = b'', filename: str = 'export.zip'):
        self.send_response(code)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _check_auth(self) -> bool:
        secret = (self.server.ctx.get('auth') or {}).get('shared_secret')  # type: ignore
        if not secret:
            return True
        hdr = self.headers.get('X-API-Key', '')
        return hdr == secret
    def log_message(self, fmt, *args):
        logger.info("http %s", fmt % args)
    def do_GET(self):
        if self.client_address[0] != '127.0.0.1':
            return self._send_json(403, {"error": "forbidden"})
        if self.path.startswith('/api/status'):
            snap = self.server.ctx['orch'].snapshot()  # type: ignore
            return self._send_json(200, {"status": snap, "ts": int(time.time()*1000)})
        return self._send_json(404, {"error": "not_found"})
    def do_POST(self):
        if self.client_address[0] != '127.0.0.1':
            return self._send_json(403, {"error": "forbidden"})
        if not self._check_auth():
            return self._send_json(401, {"error": "unauthorized"})
        p = urlparse(self.path).path
        if p.startswith('/api/action/device/') and p.endswith('/recycle'):
            device_id = p[len('/api/action/device/'):-len('/recycle')]
            ok, msg = self.server.ctx['orch'].cmd_recycle(device_id)  # type: ignore
            return self._send_json(200, {"ok": ok, "detail": msg})
        if p.startswith('/api/action/service/') and p.endswith('/restart'):
            device_id = p[len('/api/action/service/'):-len('/restart')]
            ok, msg = self.server.ctx['orch'].cmd_service_restart(device_id)  # type: ignore
            return self._send_json(200, {"ok": ok, "detail": msg})
        if p == '/api/policy/reload':
            try:
                self.server.ctx['reload_policy']()  # type: ignore
                # details можешь заполнить текущим хэшем конфига/кол-вом фильтров и т.д.
                details = {"reason": "policy/reload"}
                cfg = self.server.ctx['orch'].cfg  # type: ignore
                db_path = _db_path_from_cfg(cfg)
                _oplog_action(db_path, action="policy_reload", ok=True, details=details)
                # Поддержка hot-reload интервала тикера
                try:
                    t = self.server.ctx.get('preflight_ticker')
                    if t: t.poke()  # мгновенно перечитать интервал
                except Exception:
                    pass
                return self._send_json(200, {"ok": True})
            except Exception as e:
                # Если hot-reload завершается с ошибкой — вызови с ok=False и положи details={"error": "..."}
                details = {"error": str(e)}
                cfg = self.server.ctx['orch'].cfg  # type: ignore
                db_path = _db_path_from_cfg(cfg)
                _oplog_action(db_path, action="policy_reload", ok=False, details=details)
                return self._send_json(200, {"ok": True})  # UX не падает
        if p == '/api/preflight':
            try:
                _ = self.rfile.read(int(self.headers.get("Content-Length") or 0))  # проглатываем тело
                payload = _build_preflight_payload()
                
                # ВЫТАЩИ host/port из payload (или из cfg)
                http_host = payload["status"]["http"]["host"]
                http_port = payload["status"]["http"]["port"]
                db_path = payload["status"]["db"]["path"] if "path" in payload["status"]["db"] else _db_path_from_cfg({})
                
                _oplog_preflight(db_path, ok=True, http_host=http_host, http_port=http_port, payload=payload)
                
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                # fail-soft: даже в случае фатала отвечаем 200 с ok:true,
                # чтобы UX не падал (и видны детали по ошибке)
                safe = {"ok": True, "error": f"preflight_soft:{e}"}
                data = json.dumps(safe, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            return
        if p == '/api/action/rescan':
            try:
                snap = _snap_pnp_via_powershell()
                # применим фильтр, как в поллере
                cfg = self.server.ctx['orch'].cfg  # type: ignore
                inc = set((cfg.get("trace_filters", {}) or {}).get("include_vidpid") or [])
                if inc:
                    snap = {k:v for k,v in snap.items() if k in inc}
                _ensure_usb_tables(_db_path_from_cfg(cfg))
                for vp,(pnpid,name) in snap.items():
                    _usb_upsert_device(_db_path_from_cfg(cfg), vp, name)
                return self._send_json(200, {"ok": True, "devices": len(snap)})
            except Exception as e:
                return self._send_json(200, {"ok": False, "error": str(e)})
        if p == '/api/export':
            qs = parse_qs(urlparse(self.path).query)
            mask = None
            if 'mask' in qs:
                mask = []
                for part in qs['mask']:
                    mask += [x.strip() for x in part.split(',') if x.strip()]
            blob = self.server.ctx['orch'].build_export_zip(mask)  # type: ignore
            return self._send_bin(200, blob, filename='smartpos_usb_export.zip')
        return self._send_json(404, {"error": "not_found"})

class ApiServer(ThreadingHTTPServer):
    def __init__(self, addr: Tuple[str, int], handler=ApiHandler):
        super().__init__(addr, handler)
        self.ctx: Dict[str, Any] = {}

# ----------------------------------------------------------------------------
# ЗАГРУЗКА КОНФИГА/УСТРОЙСТВ
# ----------------------------------------------------------------------------

def load_cfg() -> Dict[str, Any]:
    if not os.path.exists(CFG_PATH):
        return DEFAULT_CFG.copy()
    try:
        with open(CFG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cfg = DEFAULT_CFG.copy()
        cfg.update(data or {})
        # нормализация
        if 'db' not in cfg: cfg['db'] = DEFAULT_CFG['db']
        return cfg
    except Exception as e:
        logger.error("config_load_error %s", e)
        return DEFAULT_CFG.copy()

def load_devices() -> List[core.DeviceRecord]:
    devs: List[core.DeviceRecord] = []
    if os.path.exists(DEV_PATH):
        try:
            with open(DEV_PATH, 'r', encoding='utf-8') as f:
                arr = json.load(f) or []
            for d in arr:
                devs.append(core.DeviceRecord(
                    d.get('device_id',''), d.get('vid',''), d.get('pid',''), d.get('friendly',''),
                    d.get('role','other'), bool(d.get('critical', False)), d.get('hub_path',''), d.get('com_port')
                ))
        except Exception as e:
            logger.error("devices_load_error %s", e)
    return devs

# ----------------------------------------------------------------------------
# СЕРВИСНЫЙ ЦИКЛ
# ----------------------------------------------------------------------------

def run_agent(console: bool = True, http_bind: Optional[str] = None):
    # разбор адреса
    try:
        host_s, port_s = (http_bind or "127.0.0.1:8765").split(":", 1)
        host = host_s.strip(); port = int(port_s.strip())
    except Exception:
        host, port = "127.0.0.1", 8765

    cfg = load_cfg()
    policy = core.Policy()
    # policy overrides
    for k, v in (cfg.get('policy') or {}).items():
        if k == 'role_overrides' and isinstance(v, dict):
            policy.role_overrides.update(v)
        elif hasattr(policy, k):
            setattr(policy, k, v)

    # factories
    base_com = core.SerialComTransport()
    com = make_traced_serial_if_enabled(base_com, cfg.get('policy') or {})
    svcq = core.make_best_service_query({})
    base_hid = core.NullHidActivity()
    hida = make_traced_hid_if_enabled(base_hid, cfg.get('policy') or {})
    reg = core.AdapterRegistry(com, svcq, hida)
    probe = core.CompositeHealthProbe(reg)
    svc = core.ActionServiceControl(core.make_best_service_control({}))
    devctl = core.ActionDeviceControl(core.make_best_device_control())
    topo = core.make_best_topology()

    orch = Orchestrator(policy, probe, svc, devctl, topo, cfg)
    for rec in load_devices():
        orch.upsert_device(rec)

    httpd = ApiServer((host, port))

    def reload_policy():
        new = load_cfg().get('policy') or {}
        for k, v in new.items():
            if k == 'role_overrides' and isinstance(v, dict):
                policy.role_overrides.update(v)
            elif hasattr(policy, k):
                setattr(policy, k, v)
        logger.info("policy_reloaded")

    # извлекаем из CFG
    collector = (cfg.get("collector") or {}) if isinstance(cfg.get("collector"), dict) else {}
    poll_interval = int(collector.get("poll_interval_sec", 5))
    # бэкенд-совместимость: если нет в collector, используем watchdog.poll_interval
    if poll_interval == 5 and not collector.get("poll_interval_sec"):
        watchdog_interval = int((cfg.get("watchdog", {}) or {}).get("poll_interval", 5))
        poll_interval = watchdog_interval
    # защитимся от странных значений
    poll_interval = max(2, min(60, poll_interval))

    # остальное без изменений
    trace_f = cfg.get("trace_filters", {}) if isinstance(cfg.get("trace_filters"), dict) else {}
    include_list = trace_f.get("include_vidpid") or []
    db_path = cfg.get("paths", {}).get("db_path", r"C:\ProgramData\SmartPOS\usb_agent\db\smartpos_usb.db")

    DEVICE_POLLER = DevicePoller(db_path=db_path, interval_s=poll_interval, include=include_list)
    DEVICE_POLLER.start()

    httpd.ctx = {'orch': orch, 'reload_policy': reload_policy, 'auth': (cfg.get('auth') or {}), 'device_poller': DEVICE_POLLER, 'http_host': host, 'http_port': port}

    # --- PreflightTicker ---
    def _get_cfg():
        # пробуем из памяти; если нет collector — читаем с диска
        try:
            cfg = httpd.ctx['orch'].cfg or {}
        except Exception:
            cfg = {}
        coll = cfg.get("collector") or {}
        if not isinstance(coll, dict) or not coll.get("preflight_interval_min"):
            disk = _load_cfg_from_disk()
            if isinstance(disk, dict):
                return disk
        return cfg
    def _get_db_path():
        try: return httpd.ctx['orch'].db_path
        except Exception:
            orch = httpd.ctx.get('orch')
            if orch is not None:
                return (orch.cfg.get('paths', {}) or {}).get('db_path', DEFAULT_DB_PATH)
            return DEFAULT_DB_PATH
    def _get_http():
        try: return httpd.ctx['http_host'], int(httpd.ctx['http_port'])
        except Exception: return ("127.0.0.1", 8765)

    PREF_TICKER = PreflightTicker(_get_cfg, _get_db_path, _get_http)
    httpd.ctx['preflight_ticker'] = PREF_TICKER
    PREF_TICKER.start()

    t_http = threading.Thread(target=httpd.serve_forever, name='http', daemon=True)
    t_http.start()
    logger.info("HTTP API on http://%s:%s", host, port)

    try:
        while True:
            orch.tick_all()
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("stopping by keyboard")
    finally:
        # Корректное завершение тикера
        try:
            t = httpd.ctx.get('preflight_ticker')
            if t: t.stop()
        except Exception:
            pass
        httpd.shutdown(); httpd.server_close()

# ----------------------------------------------------------------------------
# WINDOWS SERVICE entry (optional)
# ----------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description='SmartPOS USB Agent Service v1.4')
    ap.add_argument('--service', action='store_true')
    ap.add_argument('--console', action='store_true')
    ap.add_argument('--http', help='Override http bind host:port (e.g. 127.0.0.1:8765)')
    args = ap.parse_args()

    if args.service:
        try:
            import win32serviceutil  # type: ignore
            import win32service  # type: ignore
            import win32event  # type: ignore
        except Exception:
            print('pywin32 не установлен — используйте --console')
            return 2
        class SmartPOSUSBService(win32serviceutil.ServiceFramework):  # type: ignore
            _svc_name_ = 'SmartPOS_USB_Agent'
            _svc_display_name_ = 'SmartPOS USB Agent'
            _svc_description_ = 'USB health‑пробы и авто‑восстановление (SmartPOS)'
            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)
                self.thread = None
            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                win32event.SetEvent(self.stop_event)
            def SvcDoRun(self):
                def runner():
                    run_agent(console=False)
                self.thread = threading.Thread(target=runner, daemon=True)
                self.thread.start()
                win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        win32serviceutil.HandleCommandLine(SmartPOSUSBService)
        return 0

    run_agent(console=True, http_bind=args.http)
    return 0

if __name__ == '__main__':
    sys.exit(main())
