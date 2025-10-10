#!/usr/bin/env python3
"""
Простой smoke тест для pipeline (без эмодзи)

Базовые тесты для проверки работоспособности основного pipeline.

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import time
import json
import sys
import pathlib
from types import SimpleNamespace

# Добавляем путь к модулям
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from shared.pipeline import pipeline_tick, load_cfg
from shared.logging_rotating import get_json_logger

def test_smoke_pipeline():
    """Базовый smoke тест pipeline."""
    print("Running smoke pipeline test...")
    
    # Создаем временный логгер
    log = get_json_logger("test", "logs/test_smoke.log")
    
    # Минимальная конфигурация для теста
    cfg = {
        "collector": {
            "eventlog": {
                "enabled": True,
                "lookback_days": 1,
                "channels": [
                    {
                        "log": "System",
                        "providers": ["Service Control Manager"],
                        "days_lookback": 1
                    }
                ],
                "max_events_per_tick": 10,
                "wer": {
                    "enabled": True,
                    "lookback_days": 1,
                    "max_reports_per_tick": 5,
                    "include_report_queue": False,
                    "critical_processes": [],
                    "ignore_processes": []
                }
            }
        },
        "safety_guards": {
            "working_hours": {"start": 0, "end": 24},
            "dangerous_actions_block": [],
            "max_actions_per_hour": 10,
            "confirm_required": False
        },
        "classifier": {
            "critical_processes": [],
            "ignore_processes": [],
            "max_duplicates_per_tick": 3
        }
    }
    
    try:
        # Запускаем pipeline
        result = pipeline_tick(cfg, verbose=True)
        
        # Проверяем базовую структуру результата
        assert "events" in result, "Result missing 'events' field"
        assert "issues" in result, "Result missing 'issues' field"
        assert "plans" in result, "Result missing 'plans' field"
        assert "eventlog_count" in result, "Result missing 'eventlog_count' field"
        assert "wer_count" in result, "Result missing 'wer_count' field"
        assert "errors" in result, "Result missing 'errors' field"
        assert "metrics" in result, "Result missing 'metrics' field"
        
        # Проверяем типы данных
        assert isinstance(result["events"], list), "Events should be a list"
        assert isinstance(result["issues"], list), "Issues should be a list"
        assert isinstance(result["plans"], list), "Plans should be a list"
        assert isinstance(result["eventlog_count"], int), "EventLog count should be int"
        assert isinstance(result["wer_count"], int), "WER count should be int"
        assert isinstance(result["errors"], list), "Errors should be a list"
        assert isinstance(result["metrics"], dict), "Metrics should be a dict"
        
        # Логируем результат
        log.info({
            "action": "smoke_test_completed",
            "result": "success",
            "events_count": len(result["events"]),
            "issues_count": len(result["issues"]),
            "plans_count": len(result["plans"]),
            "metrics": result["metrics"]
        })
        
        print("OK test_smoke_pipeline passed")
        return True
        
    except Exception as e:
        log.error({
            "action": "smoke_test_failed",
            "result": "error",
            "error": str(e)
        })
        print(f"ERROR: test_smoke_pipeline failed: {e}")
        return False

def test_pipeline_with_real_config():
    """Тест pipeline с реальной конфигурацией."""
    print("Running pipeline with real config test...")
    
    try:
        # Загружаем реальную конфигурацию
        cfg = load_cfg()
        
        # Запускаем pipeline
        result = pipeline_tick(cfg, verbose=False)
        
        # Проверяем, что pipeline выполнился без критических ошибок
        assert "events" in result, "Result missing 'events' field"
        assert "issues" in result, "Result missing 'issues' field"
        assert "plans" in result, "Result missing 'plans' field"
        
        # Проверяем метрики
        metrics = result.get("metrics", {})
        assert isinstance(metrics, dict), "Metrics should be a dict"
        
        print(f"OK test_pipeline_with_real_config passed - Events: {len(result['events'])}, Issues: {len(result['issues'])}, Plans: {len(result['plans'])}")
        return True
        
    except Exception as e:
        print(f"ERROR: test_pipeline_with_real_config failed: {e}")
        return False

def test_metrics_integration():
    """Тест интеграции метрик в pipeline."""
    print("Running metrics integration test...")
    
    try:
        cfg = load_cfg()
        
        # Запускаем pipeline
        result = pipeline_tick(cfg, verbose=False)
        
        # Проверяем метрики
        metrics = result.get("metrics", {})
        assert isinstance(metrics, dict), "Metrics should be a dict"
        
        # Проверяем наличие основных метрик
        expected_metrics = [
            "eventlog_events_collected",
            "wer_events_collected", 
            "issues_classified",
            "plans_generated"
        ]
        
        for metric in expected_metrics:
            assert metric in metrics, f"Missing metric: {metric}"
            assert isinstance(metrics[metric], int), f"Metric {metric} should be int"
            assert metrics[metric] >= 0, f"Metric {metric} should be non-negative"
        
        print("OK test_metrics_integration passed")
        return True
        
    except Exception as e:
        print(f"ERROR: test_metrics_integration failed: {e}")
        return False

if __name__ == "__main__":
    print("Running pipeline smoke tests...")
    
    tests = [
        test_smoke_pipeline,
        test_pipeline_with_real_config,
        test_metrics_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"ERROR: Test {test.__name__} failed with exception: {e}")
    
    print(f"\nTest Results: {passed}/{total} passed")
    
    if passed == total:
        print("SUCCESS: All pipeline smoke tests passed!")
        sys.exit(0)
    else:
        print("ERROR: Some tests failed")
        sys.exit(1)
