#!/usr/bin/env python3
"""
Анализ событий для настройки правил SmartPOS POS Protect.

Этот скрипт анализирует события, собранные системой SmartPOS POS Protect,
и предоставляет детальную информацию для настройки правил в pos_protect_rules.json.

Использование:
    python analyze_events.py

Вывод:
    - Общее количество событий и проблем
    - Анализ WER событий с примерами процессов и путей
    - Анализ EventLog событий с топ-провайдерами
    - Детальная информация о каждой обнаруженной проблеме

Этот скрипт помогает:
    1. Понять, какие типы событий собираются системой
    2. Настроить правила в pos_protect_rules.json под реальные события
    3. Отладить проблемы с матчингом правил
    4. Оптимизировать конфигурацию коллекторов

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

from shared.pipeline import load_cfg, pipeline_tick

def analyze_events():
    cfg = load_cfg()
    result = pipeline_tick(cfg, verbose=False)
    
    print("=== АНАЛИЗ СОБЫТИЙ ===")
    print(f"Всего событий: {len(result['events'])}")
    print(f"Всего проблем: {len(result['issues'])}")
    print()
    
    # WER события
    wer_events = [e for e in result['events'] if e.get('source') == 'WER']
    print("=== WER СОБЫТИЯ ===")
    print(f"WER событий: {len(wer_events)}")
    if wer_events:
        print("Примеры WER событий:")
        for i, e in enumerate(wer_events[:3]):
            print(f"  WER {i+1}: proc={e.get('proc')}, path={e.get('path', '')[:50]}...")
    print()
    
    # EventLog события
    evt_events = [e for e in result['events'] if e.get('source', '').startswith('EventLog')]
    print("=== EVENTLOG СОБЫТИЯ ===")
    print(f"EventLog событий: {len(evt_events)}")
    
    # Подсчет провайдеров
    providers = {}
    for e in evt_events:
        provider = e.get('provider', 'None')
        providers[provider] = providers.get(provider, 0) + 1
    
    print("Топ провайдеры:")
    for p, c in sorted(providers.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {p}: {c} событий")
    print()
    
    # Анализ проблем
    print("=== ПРОБЛЕМЫ ===")
    for i, issue in enumerate(result['issues']):
        print(f"Проблема {i+1}: {issue['issue_code']} (severity: {issue['severity']})")
        evidence = issue.get('evidence', {})
        print(f"  source: {evidence.get('source')}")
        print(f"  proc: {evidence.get('proc')}")
        print(f"  provider: {evidence.get('provider')}")
        print(f"  event_id: {evidence.get('event_id')}")
        print()

if __name__ == "__main__":
    analyze_events()
