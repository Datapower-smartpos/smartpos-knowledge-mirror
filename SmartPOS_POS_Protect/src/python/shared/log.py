#!/usr/bin/env python3
"""
Унифицированное логирование для SmartPOS POS Protect.

Поддерживает как вывод в stdout, так и ротирующие файлы логов.
Автоматически добавляет timestamp к событиям.

Использование:
    from shared.log import jlog, get_rotating_logger
    
    # Простое логирование в stdout
    jlog({"action": "test", "result": "success"})
    
    # Ротирующее логирование в файл
    logger = get_rotating_logger("my_component", "logs/my.log")
    logger.info({"action": "test", "result": "success"})

Автор: SmartPOS POS Protect Team
Версия: 1.1
"""

import json
import sys
import datetime
from logging_rotating import get_json_logger

def jlog(event: dict) -> None:
    """
    Записать событие в stdout с timestamp.
    
    Args:
        event: Словарь с данными события
    """
    event = {"ts": datetime.datetime.utcnow().isoformat() + "Z", **event}
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def get_rotating_logger(component: str, log_file: str = None, max_mb: int = 5, backup_count: int = 3):
    """
    Получить ротирующий логгер для компонента.
    
    Args:
        component: Имя компонента
        log_file: Путь к файлу лога (по умолчанию logs/{component}.log)
        max_mb: Максимальный размер файла в МБ
        backup_count: Количество файлов бэкапа
        
    Returns:
        Настроенный JsonLogger
    """
    if log_file is None:
        log_file = f"logs/{component}.log"
    
    return get_json_logger(component, log_file, max_mb, backup_count)

# Предустановленные логгеры для основных компонентов
def get_service_logger():
    """Получить логгер для сервиса."""
    return get_rotating_logger("pos_protect_service", max_mb=10, backup_count=5)

def get_cli_logger():
    """Получить логгер для CLI."""
    return get_rotating_logger("pos_protect_cli", max_mb=5, backup_count=3)

def get_collector_logger():
    """Получить логгер для коллекторов."""
    return get_rotating_logger("pos_protect_collector", max_mb=10, backup_count=5)

def get_analyzer_logger():
    """Получить логгер для анализатора."""
    return get_rotating_logger("pos_protect_analyzer", max_mb=5, backup_count=3)

if __name__ == "__main__":
    # Тест простого логирования
    print("Testing simple logging:")
    jlog({"action": "test", "result": "success"})
    
    # Тест ротирующего логирования
    print("Testing rotating logging:")
    logger = get_rotating_logger("test_component", "logs/test_component.log")
    logger.info({"action": "test_rotating", "result": "success"})
    logger.error({"action": "test_error", "message": "Test error message"})
    
    print("Logging tests completed.")
