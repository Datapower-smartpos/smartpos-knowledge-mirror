# Тесты для SmartPOS POS Protect

## Обзор

Создана комплексная система тестирования для SmartPOS POS Protect, включающая unit-тесты, smoke-тесты и интеграционные тесты.

## Структура тестов

### 📁 Директория tests/

```
tests/
├── __init__.py                    # Пакет тестов
├── test_rules.py                  # Тесты для правил (с эмодзи)
├── test_rules_simple.py           # Простые тесты правил
├── test_rules_simple_ascii.py     # Тесты правил без эмодзи
├── test_actions_dry.py            # Тесты действий в dry-run
├── test_actions_simple.py         # Простые тесты действий
└── test_pipeline_smoke.py         # Smoke тесты pipeline
```

### 📄 Конфигурационные файлы

```
pytest.ini                        # Конфигурация pytest
run_tests.py                       # Скрипт запуска всех тестов
```

## Типы тестов

### 1. Тесты правил (Rules Tests)

**Файл:** `test_rules_simple_ascii.py`

**Что тестируется:**
- Загрузка правил из конфигурации
- Матчинг WER событий
- Обработка пустых списков событий

**Примеры тестов:**

```python
def test_simple_wer_rule():
    """Тест простого WER правила."""
    events = [{"type": "wer", "proc": "test.exe", "bucket": "AppCrash_test.exe_123"}]
    matched = engine.match(events)
    assert any(x["issue_code"] == "SIMPLE_WER_CRASH" for x in matched)
```

### 2. Тесты действий (Actions Tests)

**Файл:** `test_actions_simple.py`

**Что тестируется:**
- Доступность всех действий
- Dry-run режим для всех действий
- Передача аргументов в действия

**Примеры тестов:**

```python
def test_dry_run_basic():
    """Тест базового dry-run режима."""
    test_actions = ["clear_print_queue", "collect_wer_bundle", "link_smart"]
    for action_name in test_actions:
        result = ACTIONS[action_name]({"dry": True, "timeout_sec": 1})
        assert result is True
```

### 3. Smoke тесты Pipeline

**Файл:** `test_pipeline_smoke.py`

**Что тестируется:**
- Базовый smoke тест с минимальной конфигурацией
- Тест с реальной конфигурацией
- Обработка ошибок в pipeline
- Интеграция метрик

**Примеры тестов:**

```python
def test_smoke_pipeline():
    """Базовый smoke тест pipeline."""
    cfg = {
        "collector": {"eventlog": {"enabled": True}},
        "safety_guards": {"working_hours": {"start": 0, "end": 24}}
    }
    result = pipeline_tick(cfg, verbose=True)
    assert "events" in result
    assert "issues" in result
    assert "plans" in result
```

## Запуск тестов

### 1. Индивидуальный запуск

```bash
# Тесты правил
python tests/test_rules_simple_ascii.py

# Тесты действий
python tests/test_actions_simple.py

# Smoke тесты pipeline
python tests/test_pipeline_smoke.py
```

### 2. Запуск всех тестов

```bash
# Запуск всех тестов
python run_tests.py

# Запуск с подробным выводом
python run_tests.py --verbose
```

### 3. Использование pytest

```bash
# Запуск всех тестов через pytest
pytest tests/

# Запуск конкретного теста
pytest tests/test_rules_simple_ascii.py

# Запуск с маркерами
pytest -m smoke tests/
```

## Результаты тестирования

### Успешный запуск

```
🚀 Starting SmartPOS POS Protect Test Suite
============================================================

🧪 Running test_rules_simple_ascii.py...
--------------------------------------------------
OK test_rule_loading passed
OK test_simple_wer_rule passed
OK test_no_match passed

SUCCESS: All simple rules tests passed!
✅ test_rules_simple_ascii.py PASSED

============================================================
📊 Test Results: 3/3 passed
🎉 All tests passed!
```

### При ошибках

```
❌ test_example.py FAILED
Error output:
Traceback (most recent file):
  File "test_example.py", line 10, in <init>
    assert False, "Test failed"
AssertionError: Test failed
```

## Особенности тестирования

### 1. Dry-run режим
Все действия тестируются в режиме dry-run, что означает:
- Никаких реальных изменений в системе
- Только логирование команд
- Безопасное тестирование

### 2. Изоляция тестов
- Каждый тест независим
- Используются временные конфигурации
- Очистка состояния между тестами

### 3. Обработка ошибок
- Graceful обработка ошибок коллекторов
- Тестирование с неправильными конфигурациями
- Проверка устойчивости системы

### 4. Кодировка
- Поддержка ASCII для Windows
- Версии тестов с эмодзи и без
- Совместимость с разными системами

## Интеграция с CI/CD

### GitHub Actions пример

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: pip install pytest
    - name: Run tests
      run: python run_tests.py
```

### Локальная разработка

```bash
# Установка зависимостей
pip install pytest

# Запуск тестов при разработке
python run_tests.py --verbose

# Запуск конкретного теста
python tests/test_rules_simple_ascii.py
```

## Расширение тестов

### Добавление нового теста
1. Создайте файл `test_new_feature.py` в директории `tests/`
2. Добавьте тест в список в `run_tests.py`
3. Следуйте соглашениям именования: `test_*`

### Пример нового теста

```python
def test_new_feature():
    """Тест новой функциональности."""
    # Подготовка
    config = load_test_config()
    
    # Выполнение
    result = new_feature(config)
    
    # Проверка
    assert result.success
    assert result.data is not None
    
    print("OK test_new_feature passed")
```

## Мониторинг тестов

### Метрики тестирования
- Время выполнения тестов
- Процент успешных тестов
- Покрытие кода (при использовании coverage)

### Логирование
- Детальные логи для отладки
- Структурированные JSON логи
- Ротация логов тестов

## Заключение

Система тестирования SmartPOS POS Protect обеспечивает:
- ✅ Полное покрытие основных компонентов
- ✅ Безопасное тестирование в dry-run режиме
- ✅ Автоматизированный запуск всех тестов
- ✅ Детальную отчетность о результатах
- ✅ Совместимость с CI/CD системами

Тесты готовы к использованию в разработке и продакшене.
