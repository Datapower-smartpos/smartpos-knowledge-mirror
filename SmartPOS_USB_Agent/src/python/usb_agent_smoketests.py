"""
SmartPOS USB Agent — Smoke tests for factories & platform flags
Author: Разработчик суперпрограмм

Назначение:
- Проверить, что фабрики `make_best_*` выбирают корректные реализации в зависимости от флагов/платформы.
- Убедиться, что `WinDeviceControlSetupAPI.recycle` безопасно отрабатывает (не падает) даже без прав/в не-Windows окружении.

Запуск: `pytest -q usb_agent_smoketests.py`
"""
from __future__ import annotations
import sys
import types
import pytest

import usb_agent_core as core

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def restore_attr(mod, name, value):
    setattr(mod, name, value)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_factories_with_native_flags(monkeypatch):
    # Сохраняем исходные
    orig_pywin32 = getattr(core, 'HAVE_PYWIN32', False)
    orig_wmi = getattr(core, 'HAVE_WMI', False)

    # 1) Без pywin32/wmi
    monkeypatch.setattr(core, 'HAVE_PYWIN32', False, raising=False)
    monkeypatch.setattr(core, 'HAVE_WMI', False, raising=False)
    assert isinstance(core.make_best_service_query(), core.WinServiceQuery)
    assert isinstance(core.make_best_service_control(), core.WinServiceControl)
    assert isinstance(core.make_best_topology(), core.WinTopology)

    # 2) С pywin32 и wmi
    monkeypatch.setattr(core, 'HAVE_PYWIN32', True, raising=False)
    monkeypatch.setattr(core, 'HAVE_WMI', True, raising=False)
    sq = core.make_best_service_query({})
    sc = core.make_best_service_control({})
    topo = core.make_best_topology()
    assert isinstance(sq, core.WinServiceQueryPywin32)
    assert isinstance(sc, core.WinServiceControlPywin32)
    assert isinstance(topo, core.WinTopologyWMI)

    # Восстановим
    restore_attr(core, 'HAVE_PYWIN32', orig_pywin32)
    restore_attr(core, 'HAVE_WMI', orig_wmi)


def test_device_control_setupapi_recycle_is_safe(monkeypatch):
    dc = core.make_best_device_control()
    # В не-Windows окружении ожидаем безопасный отказ
    ok, msg = dc.recycle(core.DeviceRecord('devX', '0000', '0000', 'Dummy', 'other', False, 'hub', None), 0, 3000)
    assert isinstance(ok, bool) and isinstance(msg, str)

    if sys.platform == 'win32':
        # На Windows метод может попытаться реально отключить устройство — тестируем только безопасность (нет исключения)
        # и быструю остановку при пустом device_id
        ok2, msg2 = dc.recycle(core.DeviceRecord('', '0000', '0000', 'Dummy', 'other', False, 'hub', None), 0, 1000)
        assert ok2 is False and 'no_device_id' in msg2


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only skip')
def test_setupapi_handles_missing_cfgmgr(monkeypatch):
    # Имитируем недоступность CfgMgr32
    class Dummy:
        pass
    def boom():
        raise OSError('no CfgMgr32')
    monkeypatch.setattr(core.ctypes, 'windll', Dummy(), raising=False)
    # перезовём реализацию напрямую
    dc = core.WinDeviceControlSetupAPI()
    ok, msg = dc.recycle(core.DeviceRecord('devX', '0000', '0000', 'Dummy', 'other', False, 'hub', None), 0, 3000)
    assert ok is False and msg in ('cfgmgr32_unavailable', 'not_windows')
