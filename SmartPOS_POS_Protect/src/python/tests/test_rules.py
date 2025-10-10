#!/usr/bin/env python3
"""
Тесты для модуля rules.py

Тестирует работу RuleEngine и матчинг правил.

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import json
import sys
import pathlib

# Добавляем путь к модулям
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rules import RuleEngine

def test_spooler_rule_match():
    """Тест матчинга правила для Spooler."""
    # Загружаем правила из конфигурации
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # Тестовые события для Spooler (только EventLog события)
    events = [
        {"type": "eventlog", "provider": "Service Control Manager", "event_id": 7031}
    ]
    
    # Тестируем матчинг
    matched = engine.match(events)
    
    # Проверяем, что правило PRINT_SPOOLER_STUCK сработало
    spooler_matched = any(x["issue_code"] == "PRINT_SPOOLER_STUCK" for x in matched)
    assert spooler_matched, f"Expected PRINT_SPOOLER_STUCK rule to match, got: {matched}"
    
    print("✅ test_spooler_rule_match passed")

def test_wer_rule_match():
    """Тест матчинга правила для WER событий."""
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # Тестовые WER события
    events = [
        {"type": "wer", "proc": "test.exe", "bucket": "AppCrash_test.exe_123"},
        {"type": "wer", "proc": "plugins_nms.exe", "bucket": "AppCrash_plugins_nms.exe_456"}
    ]
    
    matched = engine.match(events)
    
    # Проверяем, что правило SIMPLE_WER_CRASH сработало
    assert any(x["issue_code"] == "SIMPLE_WER_CRASH" for x in matched), \
        f"Expected SIMPLE_WER_CRASH rule to match, got: {matched}"
    
    print("✅ test_wer_rule_match passed")

def test_disk_io_rule_match():
    """Тест матчинга правила для Disk I/O."""
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # Тестовые события Disk I/O
    events = [
        {"type": "eventlog", "provider": "Disk", "event_id": 51},
        {"type": "eventlog", "provider": "Disk", "event_id": 153},
        {"type": "eventlog", "provider": "storahci"},
        {"type": "eventlog", "provider": "volmgr"},
        {"type": "eventlog", "provider": "Ntfs"}
    ]
    
    matched = engine.match(events)
    
    # Проверяем, что правило DISK_IO_WARN сработало
    assert any(x["issue_code"] == "DISK_IO_WARN" for x in matched), \
        f"Expected DISK_IO_WARN rule to match, got: {matched}"
    
    print("✅ test_disk_io_rule_match passed")

def test_no_match():
    """Тест случая, когда правила не срабатывают."""
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # События, которые не должны срабатывать
    events = [
        {"type": "eventlog", "provider": "SomeOtherProvider", "event_id": 9999},
        {"type": "wer", "proc": "unknown.exe", "bucket": "UnknownBucket"}
    ]
    
    matched = engine.match(events)
    
    # Проверяем, что никаких правил не сработало
    assert len(matched) == 0, f"Expected no rules to match, got: {matched}"
    
    print("✅ test_no_match passed")

def test_rule_structure():
    """Тест структуры правил."""
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # Проверяем, что правила загружены
    assert len(engine.rules) > 0, "No rules loaded"
    
    # Проверяем структуру первого правила
    first_rule = engine.rules[0]
    assert "name" in first_rule, "Rule missing 'name' field"
    assert "match" in first_rule, "Rule missing 'match' field"
    assert "issue_code" in first_rule, "Rule missing 'issue_code' field"
    assert "plan" in first_rule, "Rule missing 'plan' field"
    
    print("✅ test_rule_structure passed")

if __name__ == "__main__":
    print("Running rules tests...")
    
    try:
        test_rule_structure()
        test_spooler_rule_match()
        test_wer_rule_match()
        test_disk_io_rule_match()
        test_no_match()
        
        print("\n🎉 All rules tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
