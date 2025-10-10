#!/usr/bin/env python3
"""
Простой тест для правил (без эмодзи)

Тестирует базовую функциональность RuleEngine.

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import json
import sys
import pathlib

# Добавляем путь к модулям
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rules import RuleEngine

def test_simple_wer_rule():
    """Тест простого WER правила."""
    # Загружаем правила из конфигурации
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # Тестовое WER событие
    events = [
        {"type": "wer", "proc": "test.exe", "bucket": "AppCrash_test.exe_123"}
    ]
    
    # Тестируем матчинг
    matched = engine.match(events)
    
    # Проверяем, что правило SIMPLE_WER_CRASH сработало
    wer_matched = any(x["issue_code"] == "SIMPLE_WER_CRASH" for x in matched)
    assert wer_matched, f"Expected SIMPLE_WER_CRASH rule to match, got: {matched}"
    
    print("OK test_simple_wer_rule passed")

def test_rule_loading():
    """Тест загрузки правил."""
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
    
    print("OK test_rule_loading passed")

def test_no_match():
    """Тест случая, когда правила не срабатывают."""
    rules_path = pathlib.Path(__file__).parent.parent.parent.parent / "config" / "pos_protect_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    engine = RuleEngine(rules_data)
    
    # События, которые не должны срабатывать (пустой список)
    events = []
    
    matched = engine.match(events)
    
    # Проверяем, что никаких правил не сработало
    assert len(matched) == 0, f"Expected no rules to match, got: {matched}"
    
    print("OK test_no_match passed")

if __name__ == "__main__":
    print("Running simple rules tests...")
    
    try:
        test_rule_loading()
        test_simple_wer_rule()
        test_no_match()
        
        print("\nSUCCESS: All simple rules tests passed!")
        
    except Exception as e:
        print(f"\nERROR: Test failed: {e}")
        sys.exit(1)
