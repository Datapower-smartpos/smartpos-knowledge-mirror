# -*- coding: utf-8 -*-
"""
Unit-тест: экспорт ZIP по маске
Строго stdlib. Проверяет, что в архив попадают только файлы по маске.
"""
from __future__ import annotations
import zipfile
from pathlib import Path


def export_zip(base_dir: Path, mask: str, out_zip: Path) -> Path:
    base = Path(base_dir)
    out_zip = Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(out_zip), 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in base.glob(mask):
            if p.is_file():
                z.write(str(p), arcname=str(p.relative_to(base)))
    return out_zip


def test_export_mask(tmp_path):
    base = tmp_path
    (base / "a.log").write_text("x", encoding="utf-8")
    (base / "b.txt").write_text("y", encoding="utf-8")
    (base / "c.log").write_text("z", encoding="utf-8")
    out = base / "export.zip"
    export_zip(base, "*.log", out)
    with zipfile.ZipFile(str(out), 'r') as z:
        names = sorted(z.namelist())
    assert names == ['a.log', 'c.log']
