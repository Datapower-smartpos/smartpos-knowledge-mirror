#!/usr/bin/env python3
"""
Легкие метрики для SmartPOS POS Protect.

Простой счетчик метрик для отслеживания статистики работы системы.
Поддерживает инкремент счетчиков и получение значений.

Использование:
    from shared.metrics import Metrics
    
    metrics = Metrics()
    metrics.inc("events_collected")
    metrics.inc("errors", 5)
    print(metrics.get("events_collected"))  # 1
    print(metrics.get("errors"))  # 5

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

from collections import defaultdict

class Metrics:
    """Простой счетчик метрик."""
    
    def __init__(self):
        """Инициализация счетчика метрик."""
        self._c = defaultdict(int)
    
    def inc(self, name: str, val: int = 1) -> None:
        """
        Увеличить счетчик метрики.
        
        Args:
            name: Имя метрики
            val: Значение для увеличения (по умолчанию 1)
        """
        self._c[name] += val
    
    def get(self, name: str) -> int:
        """
        Получить значение метрики.
        
        Args:
            name: Имя метрики
            
        Returns:
            Значение метрики или 0, если метрика не найдена
        """
        return self._c.get(name, 0)
    
    def get_all(self) -> dict:
        """
        Получить все метрики.
        
        Returns:
            Словарь со всеми метриками
        """
        return dict(self._c)
    
    def reset(self) -> None:
        """Сбросить все метрики."""
        self._c.clear()
    
    def __str__(self) -> str:
        """Строковое представление метрик."""
        return f"Metrics({dict(self._c)})"

# Глобальный экземпляр метрик для использования в системе
global_metrics = Metrics()

if __name__ == "__main__":
    # Тестирование метрик
    metrics = Metrics()
    
    # Тест базовой функциональности
    metrics.inc("test_counter")
    metrics.inc("test_counter", 5)
    metrics.inc("another_counter", 10)
    
    print("Test metrics:")
    print(f"test_counter: {metrics.get('test_counter')}")  # 6
    print(f"another_counter: {metrics.get('another_counter')}")  # 10
    print(f"nonexistent: {metrics.get('nonexistent')}")  # 0
    print(f"All metrics: {metrics.get_all()}")
    
    # Тест сброса
    metrics.reset()
    print(f"After reset: {metrics.get_all()}")