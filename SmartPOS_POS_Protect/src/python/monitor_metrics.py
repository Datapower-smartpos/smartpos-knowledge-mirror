#!/usr/bin/env python3
"""
Мониторинг метрик SmartPOS POS Protect.

Отображает текущие метрики системы и историю работы.

Использование:
    python monitor_metrics.py [--reset] [--watch]

Опции:
    --reset    Сбросить все метрики
    --watch    Непрерывный мониторинг (каждые 5 секунд)

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import sys
import time
import argparse
from shared.pipeline import get_metrics, reset_metrics

def print_metrics(metrics):
    """Вывести метрики в читаемом формате."""
    print("\n=== МЕТРИКИ SMARTPOS POS PROTECT ===")
    print(f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)
    
    if not metrics:
        print("Нет данных метрик")
        return
    
    # Группируем метрики по категориям
    collection_metrics = {k: v for k, v in metrics.items() if 'collected' in k}
    error_metrics = {k: v for k, v in metrics.items() if 'error' in k}
    processing_metrics = {k: v for k, v in metrics.items() if any(x in k for x in ['classified', 'generated'])}
    
    if collection_metrics:
        print("📊 СБОР ДАННЫХ:")
        for name, value in collection_metrics.items():
            print(f"  {name}: {value}")
    
    if processing_metrics:
        print("\n⚙️ ОБРАБОТКА:")
        for name, value in processing_metrics.items():
            print(f"  {name}: {value}")
    
    if error_metrics:
        print("\n❌ ОШИБКИ:")
        for name, value in error_metrics.items():
            print(f"  {name}: {value}")
    
    print("-" * 40)

def watch_metrics():
    """Непрерывный мониторинг метрик."""
    print("Запуск непрерывного мониторинга метрик...")
    print("Нажмите Ctrl+C для остановки")
    
    try:
        while True:
            metrics = get_metrics()
            print_metrics(metrics)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nМониторинг остановлен")

def main():
    parser = argparse.ArgumentParser(description="Мониторинг метрик SmartPOS POS Protect")
    parser.add_argument("--reset", action="store_true", help="Сбросить все метрики")
    parser.add_argument("--watch", action="store_true", help="Непрерывный мониторинг")
    
    args = parser.parse_args()
    
    if args.reset:
        reset_metrics()
        print("Метрики сброшены")
        return
    
    if args.watch:
        watch_metrics()
    else:
        metrics = get_metrics()
        print_metrics(metrics)

if __name__ == "__main__":
    main()
