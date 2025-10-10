#!/usr/bin/env python3
"""
Ротирующий JSON логгер для SmartPOS POS Protect.

Обеспечивает ротацию логов с ограничением размера файла и количеством бэкапов.
Автоматически форматирует сообщения в JSON для удобного парсинга.

Использование:
    from shared.logging_rotating import get_json_logger
    
    logger = get_json_logger("pos_protect", "logs/app.log", max_mb=10, backup_count=5)
    logger.info({"action": "test", "result": "success"})
    logger.error({"action": "error", "message": "Something went wrong"})

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import logging
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path

class JsonLogger:
    """JSON логгер с ротацией файлов."""
    
    def __init__(self, name: str, path: str, max_mb: int = 5, backup: int = 3):
        """
        Инициализация JSON логгера.
        
        Args:
            name: Имя логгера
            path: Путь к файлу лога
            max_mb: Максимальный размер файла в МБ
            backup: Количество файлов бэкапа
        """
        self._l = logging.getLogger(name)
        self._l.setLevel(logging.INFO)
        
        # Создаем директорию для логов, если она не существует
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Настраиваем ротирующий обработчик
        h = RotatingFileHandler(
            path, 
            maxBytes=max_mb * 1024 * 1024, 
            backupCount=backup,
            encoding='utf-8'
        )
        
        # Устанавливаем форматтер (только сообщение, без timestamp и уровня)
        fmt = logging.Formatter('%(message)s')
        h.setFormatter(fmt)
        
        # Добавляем обработчик к логгеру
        self._l.addHandler(h)
        
        # Предотвращаем дублирование сообщений
        self._l.propagate = False
    
    def info(self, obj) -> None:
        """
        Записать информационное сообщение.
        
        Args:
            obj: Объект для логирования (будет сериализован в JSON)
        """
        self._l.info(json.dumps(obj, ensure_ascii=False))
    
    def error(self, obj) -> None:
        """
        Записать сообщение об ошибке.
        
        Args:
            obj: Объект для логирования (будет сериализован в JSON)
        """
        self._l.error(json.dumps(obj, ensure_ascii=False))
    
    def warning(self, obj) -> None:
        """
        Записать предупреждение.
        
        Args:
            obj: Объект для логирования (будет сериализован в JSON)
        """
        self._l.warning(json.dumps(obj, ensure_ascii=False))
    
    def debug(self, obj) -> None:
        """
        Записать отладочное сообщение.
        
        Args:
            obj: Объект для логирования (будет сериализован в JSON)
        """
        self._l.debug(json.dumps(obj, ensure_ascii=False))

def get_json_logger(tag: str, log_file: str, rotate_size_mb: int = 5, backup_count: int = 3) -> JsonLogger:
    """
    Создать JSON логгер с ротацией.
    
    Args:
        tag: Имя логгера
        log_file: Путь к файлу лога
        rotate_size_mb: Максимальный размер файла в МБ
        backup_count: Количество файлов бэкапа
        
    Returns:
        Настроенный JsonLogger
    """
    return JsonLogger(tag, log_file, rotate_size_mb, backup_count)

# Предустановленные логгеры для основных компонентов
def get_service_logger() -> JsonLogger:
    """Получить логгер для сервиса."""
    return get_json_logger("pos_protect_service", "logs/service.log", 10, 5)

def get_cli_logger() -> JsonLogger:
    """Получить логгер для CLI."""
    return get_json_logger("pos_protect_cli", "logs/cli.log", 5, 3)

def get_collector_logger() -> JsonLogger:
    """Получить логгер для коллекторов."""
    return get_json_logger("pos_protect_collector", "logs/collector.log", 10, 5)

def get_analyzer_logger() -> JsonLogger:
    """Получить логгер для анализатора."""
    return get_json_logger("pos_protect_analyzer", "logs/analyzer.log", 5, 3)

if __name__ == "__main__":
    # Тестирование логгера
    logger = get_json_logger("test", "logs/test.log", 1, 2)
    
    # Тест различных типов сообщений
    logger.info({"action": "test_start", "message": "Starting test"})
    logger.warning({"action": "test_warning", "message": "This is a warning"})
    logger.error({"action": "test_error", "message": "This is an error"})
    logger.debug({"action": "test_debug", "message": "This is debug info"})
    
    # Тест с русскими символами
    logger.info({"action": "test_unicode", "message": "Тест с русскими символами"})
    
    print("Test logging completed. Check logs/test.log")
