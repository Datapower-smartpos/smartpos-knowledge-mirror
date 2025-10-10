#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SmartPOS USB Agent — Unified CLI (v1.4.1)

Назначение:
- Объединяет функционал usb_devctl_cli (v1) и usb_devctl_cli_v_2 (v2) в едином файле.
- Совместим с сервисом smartpos_usb_service_v14 (HTTP API: /api/status, /api/preflight, /api/action/*, /api/export?mask, /api/policy/reload).
- Без внешних зависимостей (stdlib only), оффлайн-совместим (локальный экспорт ZIP), с логированием/тайм-аутами/кодами ошибок.

Команды:
  status                   — GET /api/status
  preflight                — POST /api/preflight
  policy-reload            — POST /api/policy/reload
  action <name>            — POST /api/action/<name>
  service-restart          — Попытка перезапустить Windows-службу (или через action fallback)
  dump-sample-config       — Вывести шаблон config.json
  export-zip               — Экспорт логов/БД: локально (оффлайн) или через HTTP API
  selftest-export          — Локальный smoke-тест export ZIP (для быстрой проверки без pytest)

Выходные коды:
  0 — успех, 1 — ошибка ввода/вывода, 2 — сетевые/HTTP ошибки, 3 — системные ошибки (служба), 130 — прервано пользователем
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
import traceback
import zipfile
import fnmatch
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

try:
    # Python 3
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except Exception:  # pragma: no cover
    Request = object  # type: ignore
    def urlopen(*a, **k):  # type: ignore
        raise RuntimeError("urllib not available")
    class URLError(Exception): pass  # type: ignore
    class HTTPError(Exception): pass  # type: ignore

APP_NAME = "SmartPOS USB Agent CLI"
DEFAULT_API = "http://127.0.0.1:8731"
CONFIG_PATH = os.path.join(os.getenv('ProgramData', '.'), 'SmartPOS', 'usb_agent', 'config.json')
LOG = logging.getLogger("usb_devctl_cli")

# ------------------------ Logging -------------------------
class DualLogger:
    """Stdout для информсообщений, stderr для ошибок. JSON-строки не форматируем.
    """
    def __init__(self, level=logging.INFO):
        self.level = level
        logging.basicConfig(level=level, format='[%(asctime)s] %(levelname)s: %(message)s')

    def info(self, msg: str, *args):
        logging.getLogger().info(msg, *args)

    def warning(self, msg: str, *args):
        logging.getLogger().warning(msg, *args)

    def error(self, msg: str, *args):
        logging.getLogger().error(msg, *args)

LOGGER = DualLogger()

# ------------------------ Config -------------------------

def load_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    """Безопасно загружаем config.json. Возвращаем {} при ошибке.
    Структура ожидается: {"api_key": "...", ...}
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("config root must be object")
            return data
    except FileNotFoundError:
        LOGGER.warning("config.json not found: %s", path)
        return {}
    except Exception as e:  # устойчивость к кривому JSON
        LOGGER.error("config.json load failed: %s", e)
        return {}

# ------------------------ HTTP helpers --------------------

def _api_url(base: str, path: str) -> str:
    if base.endswith('/'):
        base = base[:-1]
    if not path.startswith('/'):
        path = '/' + path
    return base + path

def http_request(method: str, url: str, api_key: Optional[str] = None, timeout: float = 3.0, data: Optional[bytes] = None,
                 headers: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, Any] | bytes]:
    """Универсальный HTTP запрос (GET/POST) с тайм-аутом и X-API-Key.
    Возвращает (status_code, json_or_bytes). Ошибки как код 0 с пустым ответом.
    """
    try:
        hdrs = headers.copy() if headers else {}
        if api_key:
            hdrs['X-API-Key'] = api_key
        if method.upper() == 'POST' and data is None:
            data = b''
        req = Request(url, data=data, headers=hdrs, method=method.upper())
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, 'status', 200)
            content_type = resp.headers.get('Content-Type', '')
            body = resp.read()
            if 'application/json' in content_type.lower():
                try:
                    return status, json.loads(body.decode('utf-8'))
                except Exception:
                    return status, body
            return status, body
    except HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b''
        LOGGER.error("HTTPError %s: %s", e.code, e.reason)
        return int(getattr(e, 'code', 0)), body
    except URLError as e:
        LOGGER.error("URLError: %s", getattr(e, 'reason', e))
        return 0, b''
    except Exception as e:
        LOGGER.error("HTTP request failed: %s", e)
        return 0, b''

# ------------------------ Zip export (local) ---------------

def export_local_zip(root: Path, mask: str, out_zip: Path) -> Path:
    """Оффлайн-экспорт: собрать ZIP из файлов по маске под root.
    Маска поддерживает glob (fnmatch). Папки игнорируются. Создаёт родительскую папку out_zip.
    """
    root = root.resolve()
    out_zip = out_zip.resolve()
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    files_added = 0
    with zipfile.ZipFile(str(out_zip), 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(root):
            for name in files:
                full = Path(base) / name
                rel = full.relative_to(root)
                if fnmatch.fnmatch(str(rel), mask):
                    z.write(str(full), arcname=str(rel))
                    files_added += 1
    LOGGER.info("zip created: %s (files: %d)", out_zip, files_added)
    return out_zip

# ------------------------ Commands ------------------------

def cmd_status(args) -> int:
    api = args.api or DEFAULT_API
    cfg = load_config()
    api_key = args.api_key or cfg.get('api_key')
    url = _api_url(api, '/api/status')
    code, body = http_request('GET', url, api_key=api_key, timeout=args.timeout)
    if code == 200:
        # печатаем как есть
        if isinstance(body, (bytes, bytearray)):
            sys.stdout.write(body.decode('utf-8', 'replace'))
        else:
            sys.stdout.write(json.dumps(body, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0
    return 2

def cmd_preflight(args) -> int:
    api = args.api or DEFAULT_API
    cfg = load_config()
    api_key = args.api_key or cfg.get('api_key')
    url = _api_url(api, '/api/preflight')
    code, body = http_request('POST', url, api_key=api_key, timeout=args.timeout)
    sys.stdout.write((body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False)).decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0 if code and code < 300 else 2

def cmd_policy_reload(args) -> int:
    api = args.api or DEFAULT_API
    cfg = load_config()
    api_key = args.api_key or cfg.get('api_key')
    url = _api_url(api, '/api/policy/reload')
    code, body = http_request('POST', url, api_key=api_key, timeout=args.timeout)
    sys.stdout.write((body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False)).decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0 if code and code < 300 else 2

def cmd_action(args) -> int:
    api = args.api or DEFAULT_API
    cfg = load_config()
    api_key = args.api_key or cfg.get('api_key')
    url = _api_url(api, f'/api/action/{args.name}')
    code, body = http_request('POST', url, api_key=api_key, timeout=args.timeout)
    sys.stdout.write((body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False)).decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0 if code and code < 300 else 2

# --- Windows service helpers (fallback for service-restart) ---

def _windows_restart_service(service_name: str, timeout_sec: float = 15.0) -> bool:
    if platform.system().lower() != 'windows':
        LOGGER.error("service control only supported on Windows")
        return False
    try:
        # Stop
        p1 = subprocess.run(["sc", "stop", service_name], capture_output=True, timeout=10, check=False)
        time.sleep(0.5)
        # Start
        p2 = subprocess.run(["sc", "start", service_name], capture_output=True, timeout=10, check=False)
        ok = (p2.returncode == 0)
        if not ok:
            LOGGER.error("sc start failed: %s", p2.stderr.decode('utf-8', 'ignore'))
        return ok
    except Exception as e:
        LOGGER.error("service restart failed: %s", e)
        return False

def cmd_service_restart(args) -> int:
    # 1) Try action endpoint if provided
    api = args.api or DEFAULT_API
    cfg = load_config()
    api_key = args.api_key or cfg.get('api_key')
    if api:
        url = _api_url(api, '/api/action/service-restart')
        code, body = http_request('POST', url, api_key=api_key, timeout=args.timeout)
        if code and code < 300:
            sys.stdout.write("{\"ok\":true,\"via\":\"api\"}\n")
            return 0
        LOGGER.warning("API restart failed or unavailable (code=%s), trying local SC...", code)
    # 2) Fallback to local SC
    name = args.service_name or 'SmartPOS_USB_Service'
    ok = _windows_restart_service(name)
    sys.stdout.write(json.dumps({"ok": ok, "via": "sc"}))
    sys.stdout.write("\n")
    return 0 if ok else 3

# --- dump-sample-config ---

def cmd_dump_sample_config(args) -> int:
    sample = {
        "api_key": "",
        "debug": False,
        "notes": "place this file at %ProgramData%/SmartPOS/usb_agent/config.json"
    }
    sys.stdout.write(json.dumps(sample, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0

# --- export-zip ---

def cmd_export_zip(args) -> int:
    """Два режима:
    - local: оффлайн сборка ZIP по маске под --root
    - http : запрос к /api/export?mask=... и сохранение тела ответа (ZIP) в --out
    """
    out = Path(args.out).resolve()
    if args.local:
        root = Path(args.root or ".").resolve()
        if not root.exists():
            LOGGER.error("root not found: %s", root)
            return 1
        try:
            export_local_zip(root, args.mask, out)
            return 0
        except Exception as e:
            LOGGER.error("local zip failed: %s", e)
            return 1
    # HTTP mode
    api = args.api or DEFAULT_API
    cfg = load_config()
    api_key = args.api_key or cfg.get('api_key')
    url = _api_url(api, f'/api/export?mask={args.mask}')
    code, body = http_request('GET', url, api_key=api_key, timeout=max(args.timeout, 5.0))
    if code and code < 300 and isinstance(body, (bytes, bytearray)):
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(str(out), 'wb') as f:
                f.write(body)
            LOGGER.info("zip downloaded: %s (bytes: %d)", out, len(body))
            return 0
        except Exception as e:
            LOGGER.error("save zip failed: %s", e)
            return 1
    LOGGER.error("http export failed (code=%s)", code)
    return 2

# --- selftest-export (smoke) ---

def cmd_selftest_export(args) -> int:
    """Проводит локальный smoke-тест export_local_zip на временной директории.
    создаёт временную структуру (logs/a.log, db/smartpos_usb.db), вызывает export_local_zip(**/*.log) и проверяет содержимое ZIP
    Запуск: python usb_devctl_cli.py selftest-export
    Вернёт JSON с результатом и код возврата 0/1.
    """
    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix="spusb_"))
    try:
        # подготовка файлов
        (tmpdir / 'logs').mkdir(parents=True, exist_ok=True)
        (tmpdir / 'db').mkdir(parents=True, exist_ok=True)
        (tmpdir / 'logs' / 'a.log').write_text('x', encoding='utf-8')
        (tmpdir / 'logs' / 'b.txt').write_text('y', encoding='utf-8')
        (tmpdir / 'db' / 'smartpos_usb.db').write_text('sqlite-mock', encoding='utf-8')
        out = tmpdir / 'out.zip'
        export_local_zip(tmpdir, '**/*.log', out)
        with zipfile.ZipFile(str(out), 'r') as z:
            names = sorted(z.namelist())
        ok = names == ['logs/a.log']
        sys.stdout.write(json.dumps({"ok": ok, "files": names, "zip": str(out)}))
        sys.stdout.write("\n")
        return 0 if ok else 1
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        LOGGER.error("selftest failed: %s", e)
        return 1
    finally:
        try:
            # cleanup в конце (оставляем zip для отладки при --keep не указан)
            if not getattr(args, 'keep', False):
                for p in sorted(tmpdir.rglob('*'), reverse=True):
                    try:
                        p.unlink()
                    except IsADirectoryError:
                        p.rmdir()
                tmpdir.rmdir()
        except Exception:
            pass

# ------------------------ Argparse ------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='usb_devctl_cli', description=APP_NAME)
    p.add_argument('--api', default=DEFAULT_API, help=f'Base API URL (default: {DEFAULT_API})')
    p.add_argument('--api-key', default=None, help='API Key (override, иначе из config.json)')
    p.add_argument('--timeout', type=float, default=3.0, help='HTTP timeout seconds (default 3.0)')

    sp = p.add_subparsers(dest='cmd', required=True)

    sp.add_parser('status', help='GET /api/status').set_defaults(func=cmd_status)
    sp.add_parser('preflight', help='POST /api/preflight').set_defaults(func=cmd_preflight)
    sp.add_parser('policy-reload', help='POST /api/policy/reload').set_defaults(func=cmd_policy_reload)

    ap = sp.add_parser('action', help='POST /api/action/<name>')
    ap.add_argument('name', help='action name (e.g. recycle)')
    ap.set_defaults(func=cmd_action)

    sr = sp.add_parser('service-restart', help='Перезапуск службы (через API или локально через SC)')
    sr.add_argument('--service-name', default='SmartPOS_USB_Service', help='Имя службы (fallback)')
    sr.set_defaults(func=cmd_service_restart)

    sp.add_parser('dump-sample-config', help='Вывести шаблон config.json').set_defaults(func=cmd_dump_sample_config)

    ez = sp.add_parser('export-zip', help='Экспорт ZIP: локально или через HTTP API')
    ez.add_argument('--mask', default='**/*.log', help='Глоб-маска файлов (default **/*.log)')
    ez.add_argument('--out', required=True, help='Путь к ZIP-файлу')
    ez.add_argument('--local', action='store_true', help='Собрать ZIP локально (оффлайн режим)')
    ez.add_argument('--root', default='.', help='Корневая папка для локального экспорта')
    ez.set_defaults(func=cmd_export_zip)

    st = sp.add_parser('selftest-export', help='Локальный smoke-тест export ZIP')
    st.add_argument('--keep', action='store_true', help='Не удалять временные файлы')
    st.set_defaults(func=cmd_selftest_export)

    return p

# ------------------------ Main ----------------------------

def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        LOGGER.error("fatal: %s\n%s", e, traceback.format_exc())
        return 1

if __name__ == '__main__':
    sys.exit(main())
