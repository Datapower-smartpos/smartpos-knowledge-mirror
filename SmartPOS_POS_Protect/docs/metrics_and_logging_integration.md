# Интеграция метрик и ротирующих логов в SmartPOS POS Protect

## Созданные файлы

### 1. `shared/metrics.py`
**Легкие метрики для отслеживания статистики работы системы.**

**Основные функции:**
- `Metrics.inc(name, val=1)` - увеличить счетчик метрики
- `Metrics.get(name)` - получить значение метрики
- `Metrics.get_all()` - получить все метрики
- `Metrics.reset()` - сбросить все метрики

**Использование:**

```python
from shared.metrics import Metrics, global_metrics

# Локальные метрики
metrics = Metrics()
metrics.inc("events_processed", 10)
print(metrics.get("events_processed"))  # 10

# Глобальные метрики (используются в pipeline)
global_metrics.inc("errors", 1)
```

### 2. `shared/logging_rotating.py`
**Ротирующий JSON логгер с ограничением размера файла.**

**Основные функции:**
- `JsonLogger.info(obj)` - записать информационное сообщение
- `JsonLogger.error(obj)` - записать сообщение об ошибке
- `get_json_logger(tag, log_file, max_mb, backup_count)` - создать логгер

**Использование:**

```python
from shared.logging_rotating import get_json_logger

logger = get_json_logger("my_component", "logs/my.log", 10, 5)
logger.info({"action": "test", "result": "success"})
```

### 3. `shared/log.py` (обновлен)
**Унифицированное логирование с поддержкой ротации.**

**Новые функции:**
- `get_rotating_logger(component, log_file, max_mb, backup_count)` - получить ротирующий логгер
- `get_service_logger()` - логгер для сервиса
- `get_cli_logger()` - логгер для CLI
- `get_collector_logger()` - логгер для коллекторов
- `get_analyzer_logger()` - логгер для анализатора

**Использование:**

```python
from shared.log import jlog, get_service_logger

# Простое логирование в stdout
jlog({"action": "test", "result": "success"})

# Ротирующее логирование в файл
logger = get_service_logger()
logger.info({"action": "tick_completed", "metrics": {...}})
```

### 4. `shared/pipeline.py` (обновлен)
**Интеграция метрик в pipeline.**

**Новые функции:**
- `get_metrics()` - получить текущие метрики
- `reset_metrics()` - сбросить все метрики

**Автоматические метрики:**
- `eventlog_events_collected` - количество собранных EventLog событий
- `wer_events_collected` - количество собранных WER событий
- `issues_classified` - количество классифицированных проблем
- `plans_generated` - количество сгенерированных планов
- `eventlog_collection_errors` - ошибки сбора EventLog
- `wer_collection_errors` - ошибки сбора WER

### 5. `pos_protect_service.py` (обновлен)
**Интеграция ротирующего логгера в сервис.**

**Изменения:**
- Добавлен `service_logger` для записи в файл
- Логирование метрик в файл при каждом тике
- Логирование ошибок с метриками

### 6. `monitor_metrics.py`
**Скрипт для мониторинга метрик системы.**

**Использование:**

```bash
# Показать текущие метрики
python monitor_metrics.py

# Сбросить все метрики
python monitor_metrics.py --reset

# Непрерывный мониторинг (каждые 5 секунд)
python monitor_metrics.py --watch
```

## Интеграция в существующий код

### Минимальная интеграция
Если у вас уже есть свой логгер, можно пропустить интеграцию ротирующих логов и использовать только метрики:

```python
from shared.metrics import global_metrics

# В любом месте кода
global_metrics.inc("my_custom_metric", 1)
```

### Полная интеграция
Замените существующий логгер на ротирующий:

```python
# Было:
print("Some message")

# Стало:
from shared.log import get_service_logger
logger = get_service_logger()
logger.info({"message": "Some message"})
```

## Преимущества

1. **Метрики:**
   - Отслеживание производительности системы
   - Мониторинг ошибок
   - Статистика работы коллекторов

2. **Ротирующие логи:**
   - Автоматическая ротация по размеру
   - Сохранение истории логов
   - Структурированный JSON формат
   - Разделение логов по компонентам

3. **Унификация:**
   - Единый интерфейс для всех компонентов
   - Предустановленные конфигурации
   - Совместимость с существующим кодом

## Файлы логов

По умолчанию логи сохраняются в директории `logs/`:
- `logs/service.log` - логи сервиса
- `logs/cli.log` - логи CLI
- `logs/collector.log` - логи коллекторов
- `logs/analyzer.log` - логи анализатора

Каждый файл ротируется при достижении максимального размера (по умолчанию 5-10 МБ) с сохранением указанного количества бэкапов (по умолчанию 3-5 файлов).
