#!/usr/bin/env python3
"""Унифицированный pipeline для SmartPOS POS Protect."""

import json, pathlib, sys
from analyzer.rules import build_plans
from analyzer.classify import classify_events
from collector.evt_collect import collect_eventlog
from collector.wer_collect import collect_wer
from .metrics import global_metrics

# Добавляем родительскую директорию в Python path для импорта модулей
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# Унифицированный путь к конфигу (работает из любой директории)
ROOT = pathlib.Path(__file__).resolve().parents[3]
CFG = ROOT / "config" / "pos_protect_policies.json"

def validate_cfg(cfg: dict):
    """Валидация схемы конфигурации."""
    col = cfg.get("collector", {})
    ok_evt = isinstance(col.get("eventlog"), dict)
    ok_wer = isinstance(col.get("wer"), dict) or (
        isinstance(col.get("eventlog"), dict) and isinstance(col["eventlog"].get("wer"), dict)
    )
    if not ok_evt:
        raise ValueError("config: collector.eventlog missing or not an object")
    if not ok_wer:
        raise ValueError("config: wer config missing (collector.wer or collector.eventlog.wer)")

def _resolve_collectors(cfg: dict):
    """Резолвер конфигурации коллекторов с поддержкой обеих схем."""
    col = (cfg.get("collector") or {})
    evt = (col.get("eventlog") or {})

    # EventLog
    evt_conf = evt

    # WER: поддерживаем обе схемы
    wer_conf = (col.get("wer") or evt.get("wer") or {})
    wer_schema = "collector.wer" if "wer" in col else ("collector.eventlog.wer" if "wer" in evt else None)

    return evt_conf, wer_conf, wer_schema

def load_cfg():
    """Загрузка конфигурации с валидацией."""
    with open(CFG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    
    # Валидация схемы
    validate_cfg(cfg)
    
    return cfg

def pipeline_tick(cfg, verbose=False):
    """Унифицированный pipeline для сбора, классификации и планирования."""
    if verbose:
        print("Loading configuration...", file=sys.stderr)
    
    # Создаем копию конфигурации, чтобы избежать мутации входного параметра
    cfg_copy = cfg.copy()
    
    # Резолвер конфигурации коллекторов
    evt_conf, wer_conf, wer_schema = _resolve_collectors(cfg_copy)
    
    # Предупреждение о nested-схеме
    if wer_schema == "collector.eventlog.wer":
        print(json.dumps({
            "subsystem":"pos_protect","action":"cfg_schema",
            "result":"compat","labels":{"wer_schema": wer_schema}
        }))
    
    # Сбор событий с обработкой ошибок
    eventlog_events = []
    wer_events = []
    errors = []
    
    # Изолированный сбор EventLog событий
    try:
        if verbose:
            print("Collecting event log data...", file=sys.stderr)
        eventlog_events = collect_eventlog(evt_conf)
        global_metrics.inc("eventlog_events_collected", len(eventlog_events))
        if verbose:
            print(f"Collected {len(eventlog_events)} events", file=sys.stderr)
    except Exception as e:
        global_metrics.inc("eventlog_collection_errors")
        errors.append({"component":"eventlog","error":str(e)})
        eventlog_events = []
        if verbose:
            print(f"EventLog collection error: {e}", file=sys.stderr)
    
    # Изолированный сбор WER событий
    try:
        wer_events = collect_wer(wer_conf) if wer_conf.get("enabled") else []
        global_metrics.inc("wer_events_collected", len(wer_events))
        if verbose and wer_conf.get("enabled"):
            print(f"Total events after WER: {len(eventlog_events) + len(wer_events)}", file=sys.stderr)
    except Exception as e:
        global_metrics.inc("wer_collection_errors")
        errors.append({"component":"wer","error":str(e)})
        wer_events = []
        if verbose:
            print(f"WER collection error: {e}", file=sys.stderr)
    
    # Объединение всех событий
    all_events = [*eventlog_events, *wer_events]
    
    # Добавляем резолверную конфигурацию в копию cfg для классификатора
    cfg_copy.setdefault("__resolved", {})["wer"] = wer_conf
    
    # Классификация событий
    if verbose:
        print("Classifying events...", file=sys.stderr)
    issues = classify_events(all_events, cfg_copy)
    global_metrics.inc("issues_classified", len(issues))
    
    # Построение планов
    plans = build_plans(issues, cfg_copy)
    global_metrics.inc("plans_generated", len(plans))
    
    return {
        "events": all_events,
        "issues": issues,
        "plans": plans,
        "eventlog_count": len(eventlog_events),
        "wer_count": len(wer_events),
        "errors": errors,
        "wer_schema": wer_schema,
        "metrics": global_metrics.get_all()
    }

def get_metrics():
    """Получить текущие метрики системы."""
    return global_metrics.get_all()

def reset_metrics():
    """Сбросить все метрики."""
    global_metrics.reset()
