# -*- coding: utf-8 -*-
"""
SmartPOS USB Agent — helpers package

Зачем этот файл нужен?
- Делает папку `helpers` полноценным Python‑пакетом (устойчиво для тулчейнов/IDE и старых утилит).
- Исключает проблемы с относительными импортами (`from helpers import ...`).
- Даёт единый мини‑утилитарный API без побочных эффектов.

Особенности
- Без тяжёлых зависимостей и без I/O при импорте.
- Логгер по умолчанию не добавляет хендлеров (NullHandler), чтобы не плодить дубликаты.
"""
from __future__ import annotations
import logging
from typing import Optional

__all__ = ["get_logger", "__version__"]
__version__ = "1.4.1"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Вернёт логгер без лишних побочных эффектов.

    - Если хендлеры не настроены выше по иерархии, добавляется NullHandler, чтобы
      избежать предупреждений «No handler could be found…» в сторонних тулчейнах.
    - Уровни/формат настраиваются в вызывающей стороне (служба/CLI).
    """
    logger_name = name or "smartpos.helpers"
    logger = logging.getLogger(logger_name)
    # Не навешиваем форматтеры/хендлеры здесь — это обязанность верхнего уровня
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
