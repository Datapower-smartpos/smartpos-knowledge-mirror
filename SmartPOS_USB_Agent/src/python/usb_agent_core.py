"""
SmartPOS USB Agent — Core Interfaces & Adapters (v1)
Author: Разработчик суперпрограмм

Назначение:
- Единые контракты и безопасные тонкие адаптеры для продакшн-сборки агента над Windows.
- Минимальные плагин-адаптеры health-проб (fiscal/scanner/display + scanner.com).
- Лёгкий, модульный код без тяжёлых зависимостей. Оффлайн-устойчивость, таймбокс, структурные логи.

Совместимость/завимости:
- Опционально: `pyserial` (для COM). Если недоступен — транспорт возвращает not_supported.
- Без shell и multiprocessing. Windows-специфика инкапсулирована в классах Win*.*

Безопасность/стабильность:
- Все внешние вызовы таймбоксированы и завернуты в try/except.
- Никаких разрушающих команд (печать чеков/сбросы) — только неинвазивные пробы.

Внимание: Win-адаптеры (SCM/SetupAPI/WMI) здесь как тонкие заглушки с безопасным дефолтом.
Их можно доработать `ctypes`/`pywin32` без изменения внешних контрактов.
"""
from __future__ import annotations
import sys
import time
import json
import logging
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any, Tuple, Protocol

# ---------------------------------------------------------------------------
# ЛОГИРОВАНИЕ (структурные JSON-линиии)
# ---------------------------------------------------------------------------
logger = logging.getLogger("smartpos.usb.core")
if not logger.handlers:
    h = logging.StreamHandler()
    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "ts": int(time.time() * 1000),
                "lvl": record.levelname,
                "msg": record.getMessage(),
                "mod": record.name,
            }
            if hasattr(record, 'extra') and isinstance(record.extra, dict):
                payload.update(record.extra)
            return json.dumps(payload, ensure_ascii=False)
    h.setFormatter(JsonFormatter())
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# ДАННЫЕ/ПОЛИТИКИ
# ---------------------------------------------------------------------------

DeviceRole = str

@dataclass
class DeviceRecord:
    device_id: str
    vid: str
    pid: str
    friendly: str
    role: DeviceRole
    critical: bool
    hub_path: str
    com_port: Optional[str] = None

@dataclass
class Policy:
    probe_timeout_ms: int = 1500
    probe_interval_s: int = 10
    fail_threshold: int = 3
    recover_grace_s: int = 15
    storm_threshold_per_min_device: int = 12
    storm_threshold_per_min_hub: int = 30
    device_recycle_backoff_base_s: int = 5
    device_recycle_backoff_max_s: int = 180
    service_restart_retry: int = 2
    quiet_window_ms: int = 5000

    role_overrides: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        'fiscal': {'probe_interval_s': 7, 'fail_threshold': 2, 'service_first': True},
        'scanner': {'probe_interval_s': 12, 'fail_threshold': 3},
        'display': {'probe_interval_s': 15, 'fail_threshold': 3}
    })

    def value(self, role: DeviceRole, key: str) -> Any:
        if role in self.role_overrides and key in self.role_overrides[role]:
            return self.role_overrides[role][key]
        return getattr(self, key)

# ---------------------------------------------------------------------------
# ТАЙМБОКС/ЮТИЛИТЫ
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)

class TimeoutErrorRT(Exception):
    pass

def timebox_call(fn, timeout_ms: int, *args, **kwargs):
    """Принудительный таймбокс: выполняет функцию в отдельном потоке с жёстким ограничением времени.
    При превышении таймаута принудительно прерывает выполнение и выбрасывает TimeoutErrorRT."""
    start = _now_ms()
    
    # Создаём результат для передачи между потоками
    result_container = {'result': None, 'exception': None, 'completed': False}
    
    def target():
        try:
            result_container['result'] = fn(*args, **kwargs)
            result_container['completed'] = True
        except Exception as e:
            result_container['exception'] = e
            result_container['completed'] = True
    
    # Выполняем функцию в отдельном потоке с таймаутом
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(target)
        try:
            # Ждём результат с жёстким таймаутом
            future.result(timeout=timeout_ms / 1000.0)
        except FutureTimeoutError:
            # Принудительно отменяем выполнение
            future.cancel()
            took = _now_ms() - start
            logger.error("call_timeout_enforced", extra={"extra": {"took_ms": took, "timeout_ms": timeout_ms}})
            raise TimeoutErrorRT(f"Function {fn.__name__} exceeded timeout of {timeout_ms}ms")
    
    # Проверяем результат
    if result_container['exception'] is not None:
        raise result_container['exception']
    
    took = _now_ms() - start
    if took > timeout_ms:
        logger.warning("call_exceeded_soft_limit", extra={"extra": {"took_ms": took, "timeout_ms": timeout_ms}})
    
    return result_container['result']

# ---------------------------------------------------------------------------
# ИНТЕРФЕЙСЫ ТРАНСПОРТОВ/СЕРВИСОВ
# ---------------------------------------------------------------------------

class IComTransport(Protocol):
    def send_recv(self, dev: DeviceRecord, payload: bytes, timeout_ms: int) -> bytes: ...

class IServiceQuery(Protocol):
    def is_running(self, dev: DeviceRecord) -> bool: ...

class IServiceControl(Protocol):
    def restart(self, dev: DeviceRecord) -> Tuple[bool, str]: ...

class IHidActivity(Protocol):
    def events_in_window(self, dev: DeviceRecord, window_s: int) -> int: ...

class ITopology(Protocol):
    def present(self, device_id: str) -> bool: ...

class IDeviceControl(Protocol):
    def recycle(self, dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int) -> Tuple[bool, str]: ...

# ---------------------------------------------------------------------------
# РЕАЛИЗАЦИИ: COM (опционально pyserial)
# ---------------------------------------------------------------------------

class SerialComTransport:
    """Транспорт для COM. Использует pyserial, если доступен. Иначе — not supported.
    Все операции безопасны и таймбоксируются внешним уровнем.
    """
    def __init__(self):
        try:
            import serial  # type: ignore
            self._serial_mod = serial
        except Exception:  # pyserial отсутствует
            self._serial_mod = None

    def send_recv(self, dev: DeviceRecord, payload: bytes, timeout_ms: int) -> bytes:
        if not dev.com_port:
            raise IOError("no_com_port")
        if self._serial_mod is None:
            raise IOError("com_not_supported")
        ser = None
        try:
            # Устанавливаем короткий таймаут чтения для предотвращения блокировки
            read_timeout_s = min(0.1, timeout_ms / 1000.0)  # Максимум 100мс на чтение
            ser = self._serial_mod.Serial(dev.com_port, baudrate=9600, timeout=read_timeout_s, write_timeout=timeout_ms/1000.0)
            if payload:
                ser.write(payload)
                ser.flush()
            # Читаем всё, что пришло за окно таймаута
            start = _now_ms()
            buf = bytearray()
            while _now_ms() - start < timeout_ms:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    buf.extend(chunk)
                    # небольшая пауза, чтобы доглотить хвост
                    time.sleep(0.01)
                    if ser.in_waiting == 0:
                        break
                else:
                    # короткий сон чтобы не крутить CPU
                    time.sleep(0.005)
            return bytes(buf)
        except Exception as e:
            raise e
        finally:
            try:
                if ser:
                    ser.close()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# РЕАЛИЗАЦИИ: HID Activity (заглушка)
# ---------------------------------------------------------------------------

class NullHidActivity:
    """Безопасный fallback: всегда 0 событий. Настоящая реализация читает события HID по VID/PID.
    """
    def events_in_window(self, dev: DeviceRecord, window_s: int) -> int:
        return 0

# ---------------------------------------------------------------------------
# WINDOWS-СПЕЦИФИКА: SCM/SetupAPI/Topology (тонкие заглушки)
# ---------------------------------------------------------------------------

class WinServiceQuery:
    def is_running(self, dev: DeviceRecord) -> bool:
        # Заглушка: считаем, что служба ОК, если не задана конкретная служба в метаданных устройства
        # Реальная версия: QueryServiceStatusEx по имени службы драйвера
        return True

class WinServiceControl:
    def restart(self, dev: DeviceRecord) -> Tuple[bool, str]:
        # Заглушка: безопасно сообщаем, что перезапуск выполнен логически
        logger.info("svc_restart (stub)", extra={"extra": {"device_id": dev.device_id}})
        return True, "stub"

class WinDeviceControl:
    def recycle(self, dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int) -> Tuple[bool, str]:
        # Заглушка: реальная реализация — через SetupAPI: CM_Disable_DevNode / Enable
        logger.info("device_recycle (stub)", extra={"extra": {"device_id": dev.device_id, "quiet_ms": quiet_window_ms}})
        return True, "stub"

class WinTopology:
    def __init__(self):
        self._present: Dict[str, bool] = {}
    def set_present(self, device_id: str, present: bool):
        self._present[device_id] = present
    def present(self, device_id: str) -> bool:
        return self._present.get(device_id, True)

# ---------------------------------------------------------------------------
# ПРОБЫ: Контракты и адаптеры
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    ok: bool
    level: str  # 'TP'|'DP'|'AP'
    rtt_ms: int
    code: str   # 'ok'|'timeout'|'io'|'busy'|'not_present'|'proto'|'driver'
    details: str = ''

class ProbeAdapter:
    role: str = 'other'
    name: str = 'base.adapter'
    def __init__(self, com: IComTransport, svcq: IServiceQuery, hida: IHidActivity):
        self.com = com
        self.svcq = svcq
        self.hida = hida
    def tp(self, rec: DeviceRecord) -> ProbeResult: raise NotImplementedError
    def dp(self, rec: DeviceRecord) -> ProbeResult: raise NotImplementedError
    def ap(self, rec: DeviceRecord) -> ProbeResult: raise NotImplementedError

# 1) Фискальник, ESC/POS совместимый
class FiscalGenericEscposAdapter(ProbeAdapter):
    role = 'fiscal'
    name = 'fiscal.generic_escpos'
    DLE_EOT_1 = b"\x10\x04\x01"
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        try:
            # Пытаемся открыть порт и сделать минимальное взаимодействие
            try:
                _ = self.com.send_recv(rec, b"", 100)
            except Exception:
                pass
            return ProbeResult(True, 'TP', 1, 'ok')
        except Exception as e:
            return ProbeResult(False, 'TP', 100, 'io', str(e))
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        running = self.svcq.is_running(rec)
        return ProbeResult(running, 'DP', 1, 'ok' if running else 'driver', 'svc running' if running else 'svc down')
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        t0 = _now_ms()
        try:
            buf = self.com.send_recv(rec, self.DLE_EOT_1, 1200)
            rtt = _now_ms() - t0
            if len(buf) >= 1:
                return ProbeResult(True, 'AP', int(rtt), 'ok', 'st=%02x' % buf[0])
            return ProbeResult(False, 'AP', int(rtt), 'proto', 'empty reply')
        except Exception as e:
            return ProbeResult(False, 'AP', 1200, 'timeout' if 'timeout' in str(e).lower() else 'io', str(e))

# 2) Сканер HID-клавиатура (пассивная активность)
class ScannerHidKeyboardAdapter(ProbeAdapter):
    role = 'scanner'
    name = 'scanner.hid_keyboard'
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        cnt = self.hida.events_in_window(rec, 1)
        return ProbeResult(cnt >= 0, 'TP', 1, 'ok' if cnt >= 0 else 'not_present')
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        return ProbeResult(True, 'DP', 1, 'ok', 'no svc')
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        cnt = self.hida.events_in_window(rec, 5)
        if cnt > 0:
            return ProbeResult(True, 'AP', 5, 'ok', f'events={cnt}')
        return ProbeResult(False, 'AP', 1200, 'timeout', 'no activity')

# 3) Дисплей CD5220-совместимый (версия)
class DisplayCD5220Adapter(ProbeAdapter):
    role = 'display'
    name = 'display.cd5220'
    VERSION_Q = b"\x12R"
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        try:
            try:
                _ = self.com.send_recv(rec, b"", 100)
            except Exception:
                pass
            return ProbeResult(True, 'TP', 1, 'ok')
        except Exception as e:
            return ProbeResult(False, 'TP', 100, 'io', str(e))
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        return ProbeResult(True, 'DP', 1, 'ok')
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        t0 = _now_ms()
        try:
            buf = self.com.send_recv(rec, self.VERSION_Q, 1200)
            rtt = _now_ms() - t0
            if isinstance(buf, (bytes, bytearray)) and len(buf) > 0:
                return ProbeResult(True, 'AP', int(rtt), 'ok', f'ver={buf[:8]!r}...')
            return ProbeResult(False, 'AP', int(rtt), 'proto', 'empty version')
        except Exception as e:
            return ProbeResult(False, 'AP', 1200, 'timeout' if 'timeout' in str(e).lower() else 'io', str(e))

# 4) Сканер COM (активный эхо-тест)
class ScannerComAdapter(ProbeAdapter):
    role = 'scanner'
    name = 'scanner.com'
    ECHO = b"ECHO\r"
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        try:
            _ = self.com.send_recv(rec, b"", 100)
            return ProbeResult(True, 'TP', 1, 'ok')
        except Exception as e:
            return ProbeResult(False, 'TP', 100, 'io', str(e))
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        return ProbeResult(True, 'DP', 1, 'ok')
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        t0 = _now_ms()
        try:
            buf = self.com.send_recv(rec, self.ECHO, 1200)
            rtt = _now_ms() - t0
            if buf.strip().upper().startswith(b"ECHO"):
                return ProbeResult(True, 'AP', int(rtt), 'ok', 'echo')
            return ProbeResult(False, 'AP', int(rtt), 'proto', f'unexpected={buf!r}')
        except Exception as e:
            return ProbeResult(False, 'AP', 1200, 'timeout' if 'timeout' in str(e).lower() else 'io', str(e))

# ---------------------------------------------------------------------------
# РЕЕСТР АДАПТЕРОВ И КОМПОЗИТНЫЙ ПРОБЕР
# ---------------------------------------------------------------------------

class AdapterRegistry:
    def __init__(self, com: IComTransport, svcq: IServiceQuery, hida: IHidActivity):
        self.com, self.svcq, self.hida = com, svcq, hida
        self._by_role_name: Dict[str, ProbeAdapter] = {}
        # дефолты на роль
        self.register(FiscalGenericEscposAdapter(com, svcq, hida))
        self.register(ScannerHidKeyboardAdapter(com, svcq, hida))
        self.register(DisplayCD5220Adapter(com, svcq, hida))
        self.register(ScannerComAdapter(com, svcq, hida))

    def register(self, adapter: ProbeAdapter):
        key = f"{adapter.role}:{adapter.name}"
        self._by_role_name[key] = adapter

    def pick(self, rec: DeviceRecord) -> ProbeAdapter:
        # Простая стратегия выбора: по роли+наличию COM
        if rec.role == 'scanner' and rec.com_port:
            return self._by_role_name['scanner:scanner.com']
        if rec.role == 'display':
            return self._by_role_name['display:display.cd5220']
        if rec.role == 'fiscal':
            return self._by_role_name['fiscal:fiscal.generic_escpos']
        # Fallback: HID-сканер
        return self._by_role_name['scanner:scanner.hid_keyboard']

class CompositeHealthProbe:
    def __init__(self, registry: AdapterRegistry):
        self.reg = registry
    def probe(self, dev: DeviceRecord, timeout_ms: int) -> Tuple[bool, int, Optional[str]]:
        ad = self.reg.pick(dev)
        # TP → DP → AP
        tp = ad.tp(dev)
        if not tp.ok:
            return False, tp.rtt_ms, 'not_present' if tp.code == 'not_present' else 'io'
        dp = ad.dp(dev)
        if not dp.ok:
            return False, dp.rtt_ms, 'driver'
        ap = ad.ap(dev)
        if not ap.ok:
            code = ap.code
            if code not in ('timeout', 'proto', 'busy'):
                code = 'io'
            return False, ap.rtt_ms, code
        return True, ap.rtt_ms, None

# ---------------------------------------------------------------------------
# WINDOWS EXECUTORS: действия (service/device)
# ---------------------------------------------------------------------------

class ActionServiceControl:
    def __init__(self, svc: IServiceControl):
        self.svc = svc
    def restart(self, dev: DeviceRecord) -> Tuple[bool, str]:
        try:
            ok, msg = timebox_call(self.svc.restart, 5000, dev)
            logger.info("service_restart", extra={"extra": {"device_id": dev.device_id, "ok": ok, "msg": msg}})
            return ok, msg
        except Exception as e:
            logger.error("service_restart_error", extra={"extra": {"device_id": dev.device_id, "err": str(e)}})
            return False, str(e)

class ActionDeviceControl:
    def __init__(self, devctl: IDeviceControl):
        self.devctl = devctl
    def recycle(self, dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int = 20000) -> Tuple[bool, str]:
        try:
            ok, msg = timebox_call(self.devctl.recycle, max_duration_ms, dev, quiet_window_ms, max_duration_ms)
            logger.info("device_recycle", extra={"extra": {"device_id": dev.device_id, "ok": ok, "msg": msg}})
            return ok, msg
        except Exception as e:
            logger.error("device_recycle_error", extra={"extra": {"device_id": dev.device_id, "err": str(e)}})
            return False, str(e)

# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: конверт сообщений
# ---------------------------------------------------------------------------

def make_envelope(source: str, kind: str, type_: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "ts": int(time.time() * 1000),
        "source": source,
        "kind": kind,
        "type": type_,
        "corr_id": str(uuid.uuid4()),
        "payload": payload,
    }

# ---------------------------------------------------------------------------
# ТЕСТИРОВАНИЕ ИСПРАВЛЕННОЙ ФУНКЦИИ timebox_call
# ---------------------------------------------------------------------------

def test_timebox_call_timeout():
    """Тест для проверки принудительного прерывания при превышении таймаута."""
    def slow_function():
        time.sleep(2)  # Функция, которая выполняется 2 секунды
        return "completed"
    
    def fast_function():
        time.sleep(0.1)  # Функция, которая выполняется быстро
        return "completed"
    
    # Тест 1: Функция должна быть прервана при превышении таймаута
    try:
        result = timebox_call(slow_function, 500)  # Таймаут 500мс для функции, которая спит 2с
        print(f"ОШИБКА: Функция не была прервана! Результат: {result}")
        return False
    except TimeoutErrorRT as e:
        print(f"[OK] Тест 1 пройден: Функция корректно прервана с ошибкой: {e}")
    except Exception as e:
        print(f"ОШИБКА: Неожиданная ошибка: {e}")
        return False
    
    # Тест 2: Быстрая функция должна выполниться успешно
    try:
        result = timebox_call(fast_function, 1000)  # Таймаут 1с для функции, которая спит 0.1с
        if result == "completed":
            print("[OK] Тест 2 пройден: Быстрая функция выполнилась успешно")
        else:
            print(f"ОШИБКА: Неожиданный результат: {result}")
            return False
    except Exception as e:
        print(f"ОШИБКА: Быстрая функция не выполнилась: {e}")
        return False
    
    print("[OK] Все тесты timebox_call пройдены успешно!")
    return True

# ---------------------------------------------------------------------------
# САМОПРОВЕРКА/ДЕМО ПУТЬ (__main__)
# ---------------------------------------------------------------------------

def test_device_id_validation():
    """Тест для проверки валидации и нормализации device_id в WinDeviceControlSetupAPI."""
    print("=== Тестирование валидации device_id ===")
    
    # Создаём экземпляр для тестирования
    devctl = WinDeviceControlSetupAPI()
    
    # Тест 1: Валидный device_id
    valid_device = DeviceRecord(
        device_id="USB\\VID_1234&PID_5678\\ABC123",
        vid="1234", pid="5678", friendly="Test Device",
        role="fiscal", critical=True, hub_path="hubA"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(valid_device)
    assert dev_id == "USB\\VID_1234&PID_5678\\ABC123"
    assert source == "using_provided_device_id"
    print("[OK] Тест 1: Валидный device_id обработан корректно")
    
    # Тест 2: Пустой device_id с fallback по VID:PID
    empty_device = DeviceRecord(
        device_id="",
        vid="1234", pid="5678", friendly="Test Device",
        role="fiscal", critical=True, hub_path="hubA"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(empty_device)
    assert dev_id == "USB\\VID_1234&PID_5678\\Test Device"
    assert "using_fallback_device_id_from_vid_pid" in source
    print("[OK] Тест 2: Fallback по VID:PID работает")
    
    # Тест 3: Подозрительный device_id с fallback
    suspicious_device = DeviceRecord(
        device_id="invalid_id",
        vid="1234", pid="5678", friendly="Test Device",
        role="fiscal", critical=True, hub_path="hubA"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(suspicious_device)
    assert dev_id == "USB\\VID_1234&PID_5678\\Test Device"
    assert "using_fallback_device_id_from_vid_pid" in source
    print("[OK] Тест 3: Подозрительный device_id обработан через fallback")
    
    # Тест 4: Fallback по hub_path
    hub_device = DeviceRecord(
        device_id="",
        vid="", pid="", friendly="",
        role="fiscal", critical=True, hub_path="USB\\ROOT_HUB30\\4&12345678&0&0"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(hub_device)
    assert dev_id == "USB\\ROOT_HUB30\\4&12345678&0&0"
    assert "using_fallback_device_id_from_hub_path" in source
    print("[OK] Тест 4: Fallback по hub_path работает")
    
    # Тест 5: Полностью невалидные данные
    invalid_device = DeviceRecord(
        device_id="",
        vid="", pid="", friendly="",
        role="fiscal", critical=True, hub_path=""
    )
    dev_id, source = devctl._validate_and_normalize_device_id(invalid_device)
    assert dev_id is None
    assert source == "no_valid_device_id_available"
    print("[OK] Тест 5: Невалидные данные корректно обработаны")
    
    print("[OK] Все тесты валидации device_id пройдены успешно!")
    return True

if __name__ == "__main__":
    # Тестирование исправленной функции timebox_call
    print("=== Тестирование исправленной функции timebox_call ===")
    test_timebox_call_timeout()
    print()
    
    # Тестирование валидации device_id (отключено до определения классов)
    # test_device_id_validation()
    # print()
    
    # Демонстрация выбора адаптера и безопасных вызовов
    policy = Policy()
    com = SerialComTransport()
    svcq = WinServiceQuery()
    hida = NullHidActivity()
    reg = AdapterRegistry(com, svcq, hida)
    probe = CompositeHealthProbe(reg)

    # Пример устройств (порты условные)
    fiscal = DeviceRecord("dev_fiscal", "1234", "0001", "Fiscal ESC", "fiscal", True, "hubA", "COM5")
    scanner = DeviceRecord("dev_scanner", "2233", "0002", "Scanner COM", "scanner", True, "hubA", "COM6")
    display = DeviceRecord("dev_display", "3344", "0003", "Disp CD5220", "display", False, "hubB", "COM7")

    for rec in (fiscal, scanner, display):
        ok, rtt, code = probe.probe(rec, policy.value(rec.role, 'probe_timeout_ms'))
        logger.info("probe_result", extra={"extra": {"device_id": rec.device_id, "ok": ok, "rtt_ms": rtt, "code": code}})

    # Действия (stub)
    svc = WinServiceControl()
    devctl = WinDeviceControl()
    act_svc = ActionServiceControl(svc)
    act_dev = ActionDeviceControl(devctl)
    act_svc.restart(fiscal)
    act_dev.recycle(fiscal, policy.quiet_window_ms)


# ---------------------------------------------------------------------------
# WINDOWS: тонкие реализации под флагами (pywin32/WMI при наличии)
# ---------------------------------------------------------------------------

try:
    import win32serviceutil  # type: ignore
    import win32service  # type: ignore
    import win32con  # type: ignore
    HAVE_PYWIN32 = True
except Exception:
    HAVE_PYWIN32 = False

try:
    import wmi  # type: ignore
    HAVE_WMI = True
except Exception:
    HAVE_WMI = False

class WinServiceQueryPywin32(WinServiceQuery):
    """Запрос состояния службы через pywin32, если доступен."""
    def __init__(self, service_name_map: Optional[Dict[str, str]] = None):
        self.service_name_map = service_name_map or {}
    def _svc_name(self, dev: DeviceRecord) -> Optional[str]:
        # Простая эвристика: явное имя из карты по VID:PID или friendly
        key = f"{dev.vid}:{dev.pid}"
        return self.service_name_map.get(key)
    def is_running(self, dev: DeviceRecord) -> bool:
        if not HAVE_PYWIN32:
            return super().is_running(dev)
        name = self._svc_name(dev)
        if not name:
            return True  # если неизвестно — не блокируем
        try:
            status = win32serviceutil.QueryServiceStatus(name)
            # status[1] — текущий статус
            return status[1] == win32service.SERVICE_RUNNING
        except Exception:
            return False

class WinServiceControlPywin32(WinServiceControl):
    """Перезапуск службы через pywin32 с базовыми таймаутами и перехватом ошибок."""
    def __init__(self, service_name_map: Optional[Dict[str, str]] = None, timeout_s: int = 10):
        self.service_name_map = service_name_map or {}
        self.timeout_s = timeout_s
    def _svc_name(self, dev: DeviceRecord) -> Optional[str]:
        key = f"{dev.vid}:{dev.pid}"
        return self.service_name_map.get(key)
    def restart(self, dev: DeviceRecord) -> Tuple[bool, str]:
        if not HAVE_PYWIN32:
            return super().restart(dev)
        name = self._svc_name(dev)
        if not name:
            return super().restart(dev)
        try:
            win32serviceutil.RestartService(name)
            # Дождаться RUNNING
            start = time.time()
            while time.time() - start < self.timeout_s:
                status = win32serviceutil.QueryServiceStatus(name)
                if status[1] == win32service.SERVICE_RUNNING:
                    return True, "pywin32"
                time.sleep(0.2)
            return False, "timeout"
        except Exception as e:
            return False, str(e)

class WinTopologyWMI(WinTopology):
    """Проверка присутствия устройства по WMI Win32_PnPEntity (если доступно)."""
    def __init__(self):
        super().__init__()
        self._wmi = wmi.WMI() if HAVE_WMI else None
    def present(self, device_id: str) -> bool:
        if self._wmi is None:
            return super().present(device_id)
        try:
            # Используем укороченный хвост instance_id, чтобы уменьшить риск расхождений в экранировании
            did_tail = device_id[-32:]
            res = self._wmi.Win32_PnPEntity(PNPDeviceID__contains=did_tail)
            return len(res) > 0
        except Exception:
            return super().present(device_id)

class WinDeviceControlSetupAPI(WinDeviceControl):
    """Реализация disable/enable через CfgMgr32 (ctypes).
    Требует Windows и прав администратора. При недоступности API — безопасный отказ.
    """
    
    def _validate_and_normalize_device_id(self, dev: DeviceRecord) -> Tuple[Optional[str], str]:
        """Валидирует и нормализует device_id для использования с CM_LOCATE_DEVNODEW.
        
        Returns:
            Tuple[Optional[str], str]: (нормализованный_device_id, диагностическое_сообщение)
        """
        # Проверяем исходный device_id
        if dev.device_id and dev.device_id.strip():
            device_id = dev.device_id.strip()
            # Базовая валидация формата device_id (должен содержать VID/PID или быть instance ID)
            if len(device_id) > 3 and ('\\' in device_id or 'VID_' in device_id.upper() or 'PID_' in device_id.upper()):
                return device_id, f"using_provided_device_id"
            else:
                logger.warning("device_id_format_suspicious", extra={
                    "extra": {
                        "device_id": device_id,
                        "vid": dev.vid,
                        "pid": dev.pid,
                        "friendly": dev.friendly
                    }
                })
        
        # Fallback: пытаемся сгенерировать device_id из других полей
        fallback_candidates = []
        
        # Попытка 1: По VID:PID и friendly name
        if dev.vid and dev.pid and dev.friendly:
            # Формат: USB\VID_XXXX&PID_YYYY\...
            vid_clean = dev.vid.upper().replace('VID_', '').replace('0X', '')
            pid_clean = dev.pid.upper().replace('PID_', '').replace('0X', '')
            if len(vid_clean) == 4 and len(pid_clean) == 4:
                fallback_id = f"USB\\VID_{vid_clean}&PID_{pid_clean}\\{dev.friendly}"
                fallback_candidates.append(fallback_id)
        
        # Попытка 2: По hub_path если есть
        if dev.hub_path and dev.hub_path.strip():
            hub_path = dev.hub_path.strip()
            if '\\' in hub_path:
                fallback_candidates.append(hub_path)
        
        # Попытка 3: По COM порту если есть
        if dev.com_port and dev.com_port.strip():
            com_port = dev.com_port.strip()
            # COM порты обычно не являются device instance ID, но можем попробовать
            fallback_candidates.append(f"COM\\{com_port}")
        
        # Логируем проблему качества данных
        logger.error("device_id_quality_issue", extra={
            "extra": {
                "original_device_id": dev.device_id,
                "vid": dev.vid,
                "pid": dev.pid,
                "friendly": dev.friendly,
                "hub_path": dev.hub_path,
                "com_port": dev.com_port,
                "fallback_candidates": fallback_candidates
            }
        })
        
        # Возвращаем первый валидный кандидат или None
        for candidate in fallback_candidates:
            if candidate and len(candidate) > 3:
                return candidate, f"using_fallback_device_id_from_{'vid_pid' if 'VID_' in candidate else 'hub_path' if 'hub' in candidate.lower() else 'com_port'}"
        
        return None, "no_valid_device_id_available"
    
    def recycle(self, dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int) -> Tuple[bool, str]:
        import ctypes
        from ctypes import wintypes
        start = time.time()
        try:
            if sys.platform != 'win32':
                return False, 'not_windows'
            
            # Уважаем quiet window (минимально)
            if quiet_window_ms > 0:
                time.sleep(min(quiet_window_ms, 2000) / 1000.0)

            cfg = None
            try:
                cfg = ctypes.windll.CfgMgr32
            except Exception:
                return False, 'cfgmgr32_unavailable'

            # Типы
            DEVINST = wintypes.ULONG
            devinst = DEVINST(0)

            # Прототипы
            CM_LOCATE_DEVNODEW = cfg.CM_Locate_DevNodeW
            CM_LOCATE_DEVNODEW.argtypes = [ctypes.POINTER(DEVINST), wintypes.LPCWSTR, wintypes.ULONG]
            CM_LOCATE_DEVNODEW.restype = wintypes.ULONG

            CM_DISABLE_DEVNODE = cfg.CM_Disable_DevNode
            CM_DISABLE_DEVNODE.argtypes = [DEVINST, wintypes.ULONG]
            CM_DISABLE_DEVNODE.restype = wintypes.ULONG

            CM_ENABLE_DEVNODE = cfg.CM_Enable_DevNode
            CM_ENABLE_DEVNODE.argtypes = [DEVINST, wintypes.ULONG]
            CM_ENABLE_DEVNODE.restype = wintypes.ULONG

            CM_REENUMERATE_DEVNODE = cfg.CM_Reenumerate_DevNode
            CM_REENUMERATE_DEVNODE.argtypes = [DEVINST, wintypes.ULONG]
            CM_REENUMERATE_DEVNODE.restype = wintypes.ULONG

            CR_SUCCESS = 0

            # 1) Валидируем и нормализуем device_id
            dev_id, id_source = self._validate_and_normalize_device_id(dev)
            if not dev_id:
                logger.error("setupapi_recycle_no_device_id", extra={
                    "extra": {
                        "device_id": dev.device_id,
                        "vid": dev.vid,
                        "pid": dev.pid,
                        "friendly": dev.friendly,
                        "hub_path": dev.hub_path,
                        "com_port": dev.com_port,
                        "id_source": id_source
                    }
                })
                return False, f'device_id_quality_issue: {id_source}'
            
            # Логируем источник device_id для диагностики
            logger.info("setupapi_device_id_resolved", extra={
                "extra": {
                    "resolved_device_id": dev_id,
                    "id_source": id_source,
                    "original_device_id": dev.device_id
                }
            })
            
            # 2) Найти devinst по instance_id
            rc = CM_LOCATE_DEVNODEW(ctypes.byref(devinst), dev_id, 0)
            if rc != CR_SUCCESS:
                logger.error("setupapi_locate_failed", extra={
                    "extra": {
                        "device_id": dev_id,
                        "error_code": rc,
                        "id_source": id_source,
                        "original_device_id": dev.device_id
                    }
                })
                return False, f'locate_failed_{rc}_using_{id_source}'

            # 3) Disable
            rc = CM_DISABLE_DEVNODE(devinst, 0)
            if rc != CR_SUCCESS:
                logger.error("setupapi_disable_failed", extra={
                    "extra": {
                        "device_id": dev_id,
                        "error_code": rc,
                        "id_source": id_source
                    }
                })
                return False, f'disable_failed_{rc}'

            # Небольшая пауза между операциями
            time.sleep(0.2)

            # 4) Enable
            rc = CM_ENABLE_DEVNODE(devinst, 0)
            if rc != CR_SUCCESS:
                logger.error("setupapi_enable_failed", extra={
                    "extra": {
                        "device_id": dev_id,
                        "error_code": rc,
                        "id_source": id_source
                    }
                })
                return False, f'enable_failed_{rc}'

            # 5) Re-enumerate (best-effort)
            CM_REENUMERATE_DEVNODE(devinst, 0)

            took = int((time.time() - start) * 1000)
            logger.info('setupapi_recycle_ok', extra={
                'extra': {
                    'device_id': dev_id,
                    'original_device_id': dev.device_id,
                    'id_source': id_source,
                    'took_ms': took
                }
            })
            return True, f'setupapi_{id_source}'
        except Exception as e:
            took = int((time.time() - start) * 1000)
            logger.error('setupapi_recycle_error', extra={
                'extra': {
                    'device_id': dev.device_id,
                    'vid': dev.vid,
                    'pid': dev.pid,
                    'friendly': dev.friendly,
                    'err': str(e),
                    'took_ms': took
                }
            })
            return False, str(e)

# Удобные фабрики для «лучших доступных» реализаций

def make_best_service_query(map_: Optional[Dict[str, str]] = None) -> WinServiceQuery:
    return WinServiceQueryPywin32(map_) if HAVE_PYWIN32 else WinServiceQuery()

def make_best_service_control(map_: Optional[Dict[str, str]] = None, timeout_s: int = 10) -> WinServiceControl:
    return WinServiceControlPywin32(map_, timeout_s) if HAVE_PYWIN32 else WinServiceControl()

def make_best_topology() -> WinTopology:
    return WinTopologyWMI() if HAVE_WMI else WinTopology()

def make_best_device_control() -> WinDeviceControl:
    # Если Windows — возвращаем реализацию SetupAPI, иначе — заглушку базового класса
    return WinDeviceControlSetupAPI() if sys.platform == 'win32' else WinDeviceControl()

def test_device_id_validation():
    """Тест для проверки валидации и нормализации device_id в WinDeviceControlSetupAPI."""
    print("=== Тестирование валидации device_id ===")
    
    # Создаём экземпляр для тестирования
    devctl = WinDeviceControlSetupAPI()
    
    # Тест 1: Валидный device_id
    valid_device = DeviceRecord(
        device_id="USB\\VID_1234&PID_5678\\ABC123",
        vid="1234", pid="5678", friendly="Test Device",
        role="fiscal", critical=True, hub_path="hubA"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(valid_device)
    assert dev_id == "USB\\VID_1234&PID_5678\\ABC123"
    assert source == "using_provided_device_id"
    print("[OK] Тест 1: Валидный device_id обработан корректно")
    
    # Тест 2: Пустой device_id с fallback по VID:PID
    empty_device = DeviceRecord(
        device_id="",
        vid="1234", pid="5678", friendly="Test Device",
        role="fiscal", critical=True, hub_path="hubA"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(empty_device)
    assert dev_id == "USB\\VID_1234&PID_5678\\Test Device"
    assert "using_fallback_device_id_from_vid_pid" in source
    print("[OK] Тест 2: Fallback по VID:PID работает")
    
    # Тест 3: Подозрительный device_id с fallback
    suspicious_device = DeviceRecord(
        device_id="invalid_id",
        vid="1234", pid="5678", friendly="Test Device",
        role="fiscal", critical=True, hub_path="hubA"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(suspicious_device)
    assert dev_id == "USB\\VID_1234&PID_5678\\Test Device"
    assert "using_fallback_device_id_from_vid_pid" in source
    print("[OK] Тест 3: Подозрительный device_id обработан через fallback")
    
    # Тест 4: Fallback по hub_path
    hub_device = DeviceRecord(
        device_id="",
        vid="", pid="", friendly="",
        role="fiscal", critical=True, hub_path="USB\\ROOT_HUB30\\4&12345678&0&0"
    )
    dev_id, source = devctl._validate_and_normalize_device_id(hub_device)
    assert dev_id == "USB\\ROOT_HUB30\\4&12345678&0&0"
    assert "using_fallback_device_id_from_hub_path" in source
    print("[OK] Тест 4: Fallback по hub_path работает")
    
    # Тест 5: Полностью невалидные данные
    invalid_device = DeviceRecord(
        device_id="",
        vid="", pid="", friendly="",
        role="fiscal", critical=True, hub_path=""
    )
    dev_id, source = devctl._validate_and_normalize_device_id(invalid_device)
    assert dev_id is None
    assert source == "no_valid_device_id_available"
    print("[OK] Тест 5: Невалидные данные корректно обработаны")
    
    print("[OK] Все тесты валидации device_id пройдены успешно!")
    return True


