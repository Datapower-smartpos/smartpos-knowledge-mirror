# -*- coding: utf-8 -*-
"""
PyTest smoke-тест для unified usb_devctl_cli.py
Проверяет локальный экспорт ZIP через команду selftest-export
(без HTTP и без внешних зависимостей).
"""
from __future__ import annotations
import sys
from pathlib import Path


def _import_cli_module():
    """Импортируем src/python/usb_devctl_cli.py как модуль без установки пакета.
    Добавляем src/python в sys.path относительно корня репозитория.
    """
    root = Path(__file__).resolve().parents[1]  # <repo-root>
    cli_dir = root / 'src' / 'python'
    if str(cli_dir) not in sys.path:
        sys.path.insert(0, str(cli_dir))
    import importlib
    return importlib.import_module('usb_devctl_cli')


def test_selftest_export_smoke(capsys):
    cli = _import_cli_module()
    rc = cli.main(['selftest-export'])
    captured = capsys.readouterr().out.strip()
    assert rc == 0, f"expected rc=0, got {rc}, out={captured!r}"
    assert captured.startswith('{') and '"ok": true' in captured.lower(), f"unexpected output: {captured}"
