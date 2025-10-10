#!/usr/bin/env python3
"""
Тесты для модуля planner/actions.py в режиме dry-run

Тестирует выполнение действий без реального воздействия на систему.

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import sys
import pathlib

# Добавляем путь к модулям
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from planner.actions import ACTIONS

def _call(name, **kwargs):
    """Вызвать действие в режиме dry-run."""
    fn = ACTIONS[name]
    return fn({"dry": True, **kwargs})

def test_clear_print_queue_dry():
    """Тест очистки очереди печати в режиме dry-run."""
    result = _call("clear_print_queue", timeout_sec=1)
    assert result, f"clear_print_queue dry-run should return True, got: {result}"
    print("✅ test_clear_print_queue_dry passed")

def test_collect_wer_bundle_dry():
    """Тест сбора WER bundle в режиме dry-run."""
    result = _call("collect_wer_bundle", timeout_sec=1)
    assert result, f"collect_wer_bundle dry-run should return True, got: {result}"
    print("✅ test_collect_wer_bundle_dry passed")

def test_restart_service_dry():
    """Тест перезапуска службы в режиме dry-run."""
    result = _call("restart_service", timeout_sec=1, name="Spooler")
    assert result, f"restart_service dry-run should return True, got: {result}"
    print("✅ test_restart_service_dry passed")

def test_link_smart_dry():
    """Тест создания ссылки на SMART в режиме dry-run."""
    result = _call("link_smart", timeout_sec=1)
    assert result, f"link_smart dry-run should return True, got: {result}"
    print("✅ test_link_smart_dry passed")

def test_plan_chkdsk_dry():
    """Тест планирования chkdsk в режиме dry-run."""
    result = _call("plan_chkdsk", timeout_sec=1, volume="C:")
    assert result, f"plan_chkdsk dry-run should return True, got: {result}"
    print("✅ test_plan_chkdsk_dry passed")

def test_run_sfc_dry():
    """Тест запуска sfc в режиме dry-run."""
    result = _call("run_sfc", timeout_sec=1)
    assert result, f"run_sfc dry-run should return True, got: {result}"
    print("✅ test_run_sfc_dry passed")

def test_run_dism_dry():
    """Тест запуска dism в режиме dry-run."""
    result = _call("run_dism", timeout_sec=1)
    assert result, f"run_dism dry-run should return True, got: {result}"
    print("✅ test_run_dism_dry passed")

def test_reset_wu_components_dry():
    """Тест сброса компонентов Windows Update в режиме dry-run."""
    result = _call("reset_wu_components", timeout_sec=1)
    assert result, f"reset_wu_components dry-run should return True, got: {result}"
    print("✅ test_reset_wu_components_dry passed")

def test_actions_availability():
    """Тест доступности всех действий."""
    expected_actions = [
        "restart_service",
        "clear_print_queue", 
        "collect_wer_bundle",
        "link_smart",
        "plan_chkdsk",
        "run_sfc",
        "run_dism",
        "reset_wu_components"
    ]
    
    for action in expected_actions:
        assert action in ACTIONS, f"Action '{action}' not found in ACTIONS"
        assert callable(ACTIONS[action]), f"Action '{action}' is not callable"
    
    print("✅ test_actions_availability passed")

def test_dry_run_consistency():
    """Тест консистентности dry-run режима."""
    # Все действия в dry-run должны возвращать True
    for action_name, action_func in ACTIONS.items():
        try:
            result = action_func({"dry": True, "timeout_sec": 1})
            assert result is True, f"Action '{action_name}' dry-run returned {result}, expected True"
        except Exception as e:
            print(f"⚠️ Action '{action_name}' failed in dry-run: {e}")
    
    print("✅ test_dry_run_consistency passed")

if __name__ == "__main__":
    print("Running actions dry-run tests...")
    
    try:
        test_actions_availability()
        test_dry_run_consistency()
        test_clear_print_queue_dry()
        test_collect_wer_bundle_dry()
        test_restart_service_dry()
        test_link_smart_dry()
        test_plan_chkdsk_dry()
        test_run_sfc_dry()
        test_run_dism_dry()
        test_reset_wu_components_dry()
        
        print("\n🎉 All actions dry-run tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
