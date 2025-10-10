#!/usr/bin/env python3
"""Тонкий слой для загрузки матрицы правил SmartPOS POS Protect."""

from typing import Dict, Any, List
import json, pathlib

class RuleEngine:
    def __init__(self, cfg: Dict[str, Any]):
        # Позволяем как inline-правилам, так и внешнему файлу
        self.cfg = cfg
        self.rules = cfg.get("rules", [])
        
        # Если нет inline правил, загружаем из внешнего файла
        if not self.rules:
            rules_file = pathlib.Path(__file__).parent.parent.parent / "config" / "pos_protect_rules.json"
            if rules_file.exists():
                with open(rules_file, "r", encoding="utf-8") as f:
                    rules_data = json.load(f)
                    self.rules = rules_data.get("rules", [])
    
    def match(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # минимальная реализация матчинга под внешнюю матрицу
        matched = []
        for r in self.rules:
            win = int(r.get("match", {}).get("window_sec", 900))
            conds = r.get("match", {}).get("any", [])
            if any(_event_matches(e, conds) for e in events):
                item = {
                  "issue_code": r["issue_code"],
                  "severity": r.get("severity", "low"),
                  "dedup_key": r.get("dedup_key", r["issue_code"]),
                  "repeat_thresholds": r.get("repeat_thresholds", [1]),
                  "plan": r.get("plan", [])
                }
                matched.append(item)
        return matched

def _event_matches(e: Dict[str, Any], conds: List[Dict[str, Any]]) -> bool:
    """Проверка соответствия события условиям правила."""
    import re
    
    # Маппинг полей события для совместимости с правилами
    event_mapped = {
        "type": "eventlog" if e.get("source", "").startswith("EventLog") else "wer",
        "provider": e.get("provider"),
        "event_id": e.get("event_id"),
        "level": e.get("level"),
        "bucket": e.get("bucket"),
        "bucket_regex": e.get("bucket_regex"),
        "app_regex": e.get("app_regex"),
        "proc": e.get("proc"),
        "faulting_module": e.get("faulting_module"),
        "exception_code": e.get("exception_code")
    }
    
    for c in conds:
        ok = True
        for k, v in c.items():
            if k.endswith("_regex"):
                field = k[:-6]
                if not re.search(v, str(event_mapped.get(field, "")), re.IGNORECASE):
                    ok = False; break
            else:
                if event_mapped.get(k) != v:
                    ok = False; break
        if ok:
            return True
    return False

def build_plans(issues: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Построение планов на основе проблем с использованием RuleEngine."""
    # Если в cfg нет правил, загружаем из внешнего файла
    if not cfg.get("rules"):
        engine = RuleEngine({})  # Пустая конфигурация заставит загрузить из файла
    else:
        engine = RuleEngine(cfg)
    
    # Преобразуем issues в события для матчинга
    events = []
    for issue in issues:
        evidence = issue.get("evidence", {})
        
        # Извлекаем bucket из path для WER событий
        bucket = evidence.get("bucket")
        if not bucket and evidence.get("source") == "WER":
            path = evidence.get("path", "")
            if path:
                import os
                folder_name = os.path.basename(path)
                bucket = folder_name
        
        event = {
            "source": evidence.get("source", ""),
            "provider": evidence.get("provider"),
            "event_id": evidence.get("event_id"),
            "level": evidence.get("level"),
            "bucket": bucket,
            "bucket_regex": evidence.get("bucket_regex"),
            "app_regex": evidence.get("app_regex"),
            "proc": evidence.get("proc"),
            "faulting_module": evidence.get("faulting_module"),
            "exception_code": evidence.get("exception_code")
        }
        events.append(event)
    
    # Получаем совпадающие правила
    matched_rules = engine.match(events)
    
    # Преобразуем в планы
    plans = []
    for rule in matched_rules:
        plan = {
            "issue": {
                "issue_code": rule["issue_code"],
                "severity": rule["severity"],
                "evidence": {}
            },
            "plan": []
        }
        
        # Преобразуем план из правила в формат планировщика
        for step in rule.get("plan", []):
            plan_step = {
                "action": step.get("action"),
                "args": step.get("args", {}),
                "timeout_sec": step.get("timeout_sec", 30),
                "retries": step.get("retries", 0)
            }
            plan["plan"].append(plan_step)
        
        plans.append(plan)
    
    return plans

if __name__ == "__main__":
    # Тестирование RuleEngine
    test_cfg = {
        "rules": [
            {
                "name": "TEST_RULE",
                "match": {
                    "any": [
                        {"type": "eventlog", "provider": "Service Control Manager", "event_id": 7031}
                    ],
                    "window_sec": 900
                },
                "issue_code": "TEST_ISSUE",
                "severity": "medium",
                "dedup_key": "test:key",
                "repeat_thresholds": [1, 3],
                "plan": [
                    {"action": "restart_service", "args": {"name": "Spooler"}, "timeout_sec": 15}
                ]
            }
        ]
    }
    
    engine = RuleEngine(test_cfg)
    test_events = [
        {"type": "eventlog", "provider": "Service Control Manager", "event_id": 7031}
    ]
    
    matched = engine.match(test_events)
    print("Test matched rules:", matched)
