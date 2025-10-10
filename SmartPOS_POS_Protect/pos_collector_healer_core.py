# -*- coding: utf-8 -*-
"""
SmartPOS POS-Protect: Collector/Healer core (v1.1.0-test)
- HTTP API on loopback
- Index WER dumps, ETW files, EventLog exports
- Heal: restart services, restart ETW session
- Storage: SQLite + JSONL
"""
import os
import json
import time
import threading
import http.server
import socketserver
import logging
import hashlib
import zipfile
import shutil
import sqlite3
import traceback
import subprocess
from datetime import datetime

APP_VERSION = "1.1.0-test"

DEFAULT_CFG = {
    "api_key": "CHANGE_ME",
    "listen": "127.0.0.1",
    "port": 11888,
    "data_root": "C:/POS",
    "quota_mb": 1024,
    "retention_days": 14,
    "wer_dump_minfree_mb": 2048,
    "export_masks_default": ["wer", "etl", "logs", "db", "eventlog"],
    "targets": [],
    "sku": "BASE"
}

# ---- Logging ----
LOGDIR = os.path.abspath(os.path.join(os.getcwd(), "logs"))
os.makedirs(LOGDIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOGDIR, "collector.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ---- Config ----
def load_cfg(path="config.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in DEFAULT_CFG.items():
                cfg.setdefault(k, v)
            return cfg
    except Exception:
        logging.exception("Config load failed, using defaults")
        return DEFAULT_CFG.copy()

CFG = load_cfg()

DATA_ROOT = CFG["data_root"]
DIR_WER    = os.path.join(DATA_ROOT, "wer")
DIR_ETL    = os.path.join(DATA_ROOT, "etl")
DIR_EXPORT = os.path.join(DATA_ROOT, "export")
DIR_DB     = os.path.join(DATA_ROOT, "db")
for d in (DATA_ROOT, DIR_WER, DIR_ETL, DIR_EXPORT, DIR_DB, LOGDIR):
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as e:
        logging.error("mkdir %s failed: %s", d, e)

DB_PATH = os.path.join(DIR_DB, "collector.db")

# ---- SQLite ----
SCHEMA = """
CREATE TABLE IF NOT EXISTS wer_index(
  id INTEGER PRIMARY KEY,
  process TEXT, path TEXT, size INTEGER, ctime TEXT
);
CREATE TABLE IF NOT EXISTS etl_index(
  id INTEGER PRIMARY KEY,
  path TEXT, size INTEGER, ctime TEXT
);
CREATE TABLE IF NOT EXISTS events(
  ts TEXT, level TEXT, msg TEXT
);
"""

def db_init():
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()

def db_log(level, msg):
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(
            "INSERT INTO events(ts,level,msg) VALUES(?,?,?)",
            (datetime.utcnow().isoformat(), level, msg)
        )
        con.commit()
    finally:
        con.close()

# ---- Disk/Quota ----
def get_free_mb(path):
    try:
        total, used, free = shutil.disk_usage(path)
        return int(free/1024/1024)
    except Exception:
        logging.exception("disk_usage failed")
        return 0

def enforce_quota(root=DATA_ROOT, limit_mb=CFG["quota_mb"]):
    paths = []
    for base in (DIR_WER, DIR_ETL, LOGDIR, DIR_DB):
        for r, _, files in os.walk(base):
            for f in files:
                p = os.path.join(r, f)
                try:
                    st = os.stat(p)
                    paths.append((p, st.st_size, st.st_mtime))
                except:
                    pass
    total = sum(s for _, s, _ in paths)
    if total <= limit_mb * 1024 * 1024:
        return
    paths.sort(key=lambda x: x[2])  # oldest first
    for p, s, _ in paths:
        try:
            os.remove(p)
            total -= s
            logging.info("quota: removed %s", p)
            if total <= limit_mb * 1024 * 1024:
                break
        except Exception as e:
            logging.warning("quota: rm %s failed: %s", p, e)

# ---- WER controls ----
try:
    import winreg
    WER_LOCALDUMPS = r"SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting\\LocalDumps"
    def set_dump_type(dump_type: int):
        try:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, WER_LOCALDUMPS)
            winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, int(dump_type))
            winreg.CloseKey(key)
            logging.info("WER DumpType set to %s", dump_type)
            db_log("INFO", f"WER DumpType set to {dump_type}")
            return True
        except Exception:
            logging.exception("Failed to set DumpType")
            return False
except Exception:
    def set_dump_type(dump_type: int):
        logging.warning("winreg not available; cannot set DumpType")
        return False

# ---- Indexers ----
def index_wer():
    con = sqlite3.connect(DB_PATH)
    try:
        for r, _, files in os.walk(DIR_WER):
            for f in files:
                if f.lower().endswith((".dmp", ".wer")):
                    p = os.path.join(r, f)
                    try:
                        st = os.stat(p)
                        con.execute(
                            "INSERT INTO wer_index(process,path,size,ctime) VALUES(?,?,?,?)",
                            (os.path.basename(r), p, st.st_size, datetime.utcfromtimestamp(st.st_ctime).isoformat())
                        )
                    except Exception as e:
                        logging.debug("skip %s: %s", p, e)
        con.commit()
    finally:
        con.close()

def index_etl():
    con = sqlite3.connect(DB_PATH)
    try:
        for r, _, files in os.walk(DIR_ETL):
            for f in files:
                if f.lower().endswith(".etl"):
                    p = os.path.join(r, f)
                    try:
                        st = os.stat(p)
                        con.execute(
                            "INSERT INTO etl_index(path,size,ctime) VALUES(?,?,?)",
                            (p, st.st_size, datetime.utcfromtimestamp(st.st_ctime).isoformat())
                        )
                    except Exception as e:
                        logging.debug("skip %s: %s", p, e)
        con.commit()
    finally:
        con.close()

# ---- Export ZIP ----
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def _add_tree(z, base_dir, root):
    for r, _, files in os.walk(base_dir):
        for f in files:
            p = os.path.join(r, f)
            z.write(p, arcname=os.path.relpath(p, root))

def do_export(mask):
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(DIR_EXPORT, f"export_{ts}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        root = DATA_ROOT
        if "wer" in mask:
            _add_tree(z, DIR_WER, root)
        if "etl" in mask:
            _add_tree(z, DIR_ETL, root)
        if "logs" in mask:
            _add_tree(z, LOGDIR, root)
        if "db" in mask and os.path.exists(DB_PATH):
            z.write(DB_PATH, arcname=os.path.relpath(DB_PATH, root))
        if "eventlog" in mask:
            ev_dir = os.path.join(DIR_EXPORT, "eventlog")
            if os.path.isdir(ev_dir):
                _add_tree(z, ev_dir, root)
    digest = sha256_of(out)
    with open(out + ".sha256", "w") as f:
        f.write(digest)
    logging.info("Exported %s (%s)", out, digest)
    db_log("INFO", f"export {os.path.basename(out)} {digest}")
    return out, digest

# ---- Healer actions ----
def restart_service(name: str):
    try:
        subprocess.run(["sc", "stop", name], check=False, capture_output=True)
        time.sleep(1)
        subprocess.run(["sc", "start", name], check=False, capture_output=True)
        db_log("INFO", f"service {name} restarted")
        return True
    except Exception:
        logging.exception("svc restart failed: %s", name)
        return False

def restart_etw_session():
    try:
        subprocess.run(["logman", "stop", "SmartPOS_Autologger", "-ets"], check=False, capture_output=True)
        time.sleep(1)
        subprocess.run(["logman", "start", "SmartPOS_Autologger", "-ets"], check=False, capture_output=True)
        db_log("INFO", "ETW session restarted")
        return True
    except Exception:
        logging.exception("restart_etw_session failed")
        return False

# ---- Maintenance loop ----
def maintenance():
    while True:
        try:
            free_mb = get_free_mb(DATA_ROOT)
            want_full = free_mb >= CFG["wer_dump_minfree_mb"]
            set_dump_type(2 if want_full else 1)
            index_wer()
            index_etl()
            enforce_quota()
        except Exception:
            logging.exception("maintenance iteration failed")
        time.sleep(60)

# ---- HTTP API ----
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = f"PosCollectorHealer/{APP_VERSION}"

    def _auth(self):
        key = self.headers.get("X-API-Key", "")
        return key and key == CFG["api_key"]

    def do_GET(self):
        global CFG
        if self.path.startswith("/api/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            payload = {
                "version": APP_VERSION,
                "time": datetime.utcnow().isoformat(),
                "free_mb": get_free_mb(DATA_ROOT),
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if self.path.startswith("/api/export"):
            if not self._auth():
                self.send_error(401, "Unauthorized")
                return
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            mask = q.get("mask", [",".join(CFG["export_masks_default"])])[0].split(",")
            out, digest = do_export(mask)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"zip": out, "sha256": digest}).encode("utf-8"))
            return

        if self.path.startswith("/api/policy/reload"):
            if not self._auth():
                self.send_error(401, "Unauthorized")
                return
            CFG = load_cfg()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        self.send_error(404)

    def log_message(self, fmt, *args):
        logging.info("HTTP %s - %s", self.address_string(), fmt % args)

def run_server():
    with socketserver.TCPServer((CFG["listen"], CFG["port"]), Handler) as httpd:
        httpd.allow_reuse_address = True
        logging.info("HTTP listening on %s:%s", CFG["listen"], CFG["port"])
        db_log("INFO", f"listen {CFG['listen']}:{CFG['port']}")
        httpd.serve_forever()

def main():
    db_init()
    t = threading.Thread(target=maintenance, daemon=True)
    t.start()
    run_server()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("fatal crash")
        with open(os.path.join(LOGDIR, "fatal.trace"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())

# Записываем как ANSI (Default)


