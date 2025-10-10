# -*- coding: utf-8 -*-
"""
Unit-тест: парсинг config.json и hot-reload по mtime.
Строго stdlib, оффлайн. Эмулирует смену файла и проверяет, что колбэк получает обновления.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

CONFIG_DEFAULT = {"api_key": "", "debug": False}


def read_config(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else dict(CONFIG_DEFAULT)
    except FileNotFoundError:
        return dict(CONFIG_DEFAULT)
    except Exception:
        return dict(CONFIG_DEFAULT)


class ConfigWatcher:
    def __init__(self, path: str, on_change):
        self.path = path
        self.on_change = on_change
        self._mt = 0.0

    def poll(self):
        mt = os.path.getmtime(self.path) if os.path.exists(self.path) else 0.0
        if mt != self._mt:
            self._mt = mt
            self.on_change(read_config(self.path))

    def start(self, interval: float = 0.05, ticks: int = 4):
        for _ in range(ticks):
            self.poll()
            time.sleep(interval)


def test_parse_and_hot_reload(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"api_key":"A","debug":false}', encoding='utf-8')
    seen = []

    def on_change(obj: dict):
        seen.append(obj.get('api_key', ''))

    w = ConfigWatcher(str(cfg), on_change)
    # tick#1 — первая загрузка
    w.start(interval=0.05, ticks=1)
    # меняем файл
    time.sleep(0.06)
    cfg.write_text('{"api_key":"B","debug":true}', encoding='utf-8')
    # tick#2 — подхватили изменения
    w.start(interval=0.05, ticks=2)

    assert seen == ['A', 'B']
