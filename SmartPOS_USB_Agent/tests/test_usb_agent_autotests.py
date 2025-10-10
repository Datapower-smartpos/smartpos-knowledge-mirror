# -*- coding: utf-8 -*-
"""
Минимальные smoke-тесты для SmartPOS USB Agent.
Цели:
- Проверить структуру проекта и наличие ключевых путей/файлов.
- Безопасно (без прав администратора) прогнать `run_usb_devctl.bat --help` и убедиться,
  что скрипт отвечает и печатает текст (RU/EN), не зависает.

Требования:
- Строго stdlib; без shell=True; с таймаутом и понятными логами при сбоях.
- Тесты устойчивы на Windows (CRLF), офлайн, минимальные ожидания окружения.

Запуск: включается обычным `pytest` как часть набора.
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
BAT = SRC / "python" / "run_usb_devctl.bat"


@pytest.mark.parametrize(
    "p",
    [pytest.param(SRC, id="src exists"), pytest.param(ROOT / "tests", id="tests exists")],
)
def test_project_paths_exist(p: Path) -> None:
    """Минимальная проверка структуры проекта."""
    assert p.exists() and p.is_dir(), f"Path missing: {p}"


@pytest.mark.skipif(platform.system() != "Windows", reason="run_usb_devctl.bat актуален только для Windows")
def test_run_usb_devctl_bat_exists_and_crlf() -> None:
    """Проверяем существование BAT и CRLF."""
    assert BAT.exists() and BAT.is_file(), f"Not found: {BAT}"
    head = BAT.read_bytes()[:2048]
    assert b"\r\n" in head, "Expected CRLF line endings in BAT"


@pytest.mark.skipif(platform.system() != "Windows", reason="CLI BAT smoke: Windows only")
def test_run_usb_devctl_bat_help_smoke(tmp_path: Path) -> None:
    """Безопасный запуск `run_usb_devctl.bat --help` без shell=True с таймаутом."""
    assert BAT.exists(), f"Not found: {BAT}"

    cmd = [str(BAT), "--help"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(tmp_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("run_usb_devctl.bat --help timed out (>15s)")

    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    combined = (out + "\n" + err).strip()
    assert combined, "No output produced by run_usb_devctl.bat --help"

    tokens = ("SmartPOS", "USB", "Agent", "Help", "Usage", "Использование", "Помощь")
    assert any(t.lower() in combined.lower() for t in tokens), (
        "Help output doesn't look like our CLI.\n"
        f"Return code: {proc.returncode}\n"
        f"Output:\n{combined}"
    )


def test_tools_folder_has_make_release() -> None:
    """Проверяем наличие скрипта сборки релиза."""
    path = TOOLS / "make_release_zip.ps1"
    assert path.exists() and path.is_file(), f"File missing: {path}"