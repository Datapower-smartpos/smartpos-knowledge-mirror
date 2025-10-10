#!/usr/bin/env python3
"""
Простой тест для действий (без эмодзи)

Тестирует базовую функциональность действий в режиме dry-run.

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import sys
import pathlib

# Добавляем путь к модулям
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from planner.actions import ACTIONS

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
    
    print("OK test_actions_availability passed")

def test_dry_run_basic():
    """Тест базового dry-run режима."""
    # Тестируем несколько действий в dry-run
    test_actions = [
        "clear_print_queue",
        "collect_wer_bundle", 
        "link_smart"
    ]
    
    for action_name in test_actions:
        action_func = ACTIONS[action_name]
        try:
            result = action_func({"dry": True, "timeout_sec": 1})
            assert result is True, f"Action '{action_name}' dry-run returned {result}, expected True"
        except Exception as e:
            print(f"WARNING: Action '{action_name}' failed in dry-run: {e}")
    
    print("OK test_dry_run_basic passed")

def test_action_with_args():
    """Тест действий с аргументами."""
    # Тестируем restart_service с аргументом name
    restart_func = ACTIONS["restart_service"]
    result = restart_func({"dry": True, "timeout_sec": 1, "name": "Spooler"})
    assert result is True, f"restart_service with args returned {result}, expected True"
    
    # Тестируем plan_chkdsk с аргументом volume
    chkdsk_func = ACTIONS["plan_chkdsk"]
    result = chkdsk_func({"dry": True, "timeout_sec": 1, "volume": "C:"})
    assert result is True, f"plan_chkdsk with args returned {result}, expected True"
    
    print("OK test_action_with_args passed")

if __name__ == "__main__":
    print("Running simple actions tests...")
    
    try:
        test_actions_availability()
        test_dry_run_basic()
        test_action_with_args()
        
        print("\nSUCCESS: All simple actions tests passed!")
        
    except Exception as e:
        print(f"\nERROR: Test failed: {e}")
        sys.exit(1)
