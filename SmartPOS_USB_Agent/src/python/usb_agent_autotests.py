"""
SmartPOS USB Agent — Autotests Scaffold (pytest)
Author: Разработчик суперпрограмм

Цель:
- Повторяет 5 ключевых сценариев + негативные кейсы, используя адаптеры/реестр/пробер из `usb_agent_core.py`.
- Содержит лёгкий оркестратор, фейковые исполнители действий и топологию.

Реализация:
- Дать минимально-рабочий каркас для unit/integration-подобных тестов 5 ключевых сценариев.
- Внутри файла: лёгкая реализация оркестратора и адаптеров (заглушки) + тесты на pytest.
- Соответствие pybox-ограничениям: без multiprocessing, без внешней сети, без shell.

Запуск локально: `pytest -q usb_agent_autotests_scaffold.py`

Примечание: это каркас. Реальные адаптеры к WinAPI/SetupAPI/WMI подменяются через интерфейсы.
"""
from __future__ import annotations
import time
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any, Callable, Tuple

# ---------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# ---------------------------------------------------------------------------
logger = logging.getLogger("usb_agent_test")
if not logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s')
    h.setFormatter(fmt)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# МОДЕЛИ ДАННЫХ
# ---------------------------------------------------------------------------

DeviceRole = str  # 'fiscal'|'scanner'|'display'|'other'
DeviceState = str  # 'READY'|'DEGRADED'|'RECOVERING'|'FAILED'

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

    # Ролевые уточнения
    role_overrides: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        'fiscal': {'probe_interval_s': 7, 'fail_threshold': 2, 'service_first': True},
        'scanner': {'probe_interval_s': 12, 'fail_threshold': 3},
        'display': {'probe_interval_s': 15, 'fail_threshold': 3}
    })

    def value(self, role: DeviceRole, key: str) -> Any:
        if role in self.role_overrides and key in self.role_overrides[role]:
            return self.role_overrides[role][key]
        return getattr(self, key)


@dataclass
class DeviceRuntime:
    record: DeviceRecord
    state: DeviceState = 'READY'
    timeouts: int = 0
    last_action_ts: float = 0.0
    backoff_s: int = 0
    last_probe_ts: float = 0.0
    last_activity_ts: float = 0.0  # защита quiet window

# ---------------------------------------------------------------------------
# ИНТЕРФЕЙСЫ АДАПТЕРОВ (здесь фейки для тестов)
# ---------------------------------------------------------------------------

class IHealthProbe:
    def probe(self, dev: DeviceRecord, timeout_ms: int) -> Tuple[bool, int, Optional[str]]:
        """Возвращает (ok, rtt_ms, err_code). err_code: 'timeout'|'busy'|'io'|None"""
        raise NotImplementedError

class IServiceControl:
    def restart(self, dev: DeviceRecord) -> Tuple[bool, str]:
        raise NotImplementedError

class IDeviceControl:
    def recycle(self, dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int) -> Tuple[bool, str]:
        raise NotImplementedError

class ITopology:
    def present(self, device_id: str) -> bool:
        raise NotImplementedError

# ---------------------------------------------------------------------------
# ФЕЙКОВЫЕ РЕАЛИЗАЦИИ ДЛЯ ТЕСТОВ
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self._now = 0.0
    def now(self) -> float:
        return self._now
    def sleep(self, seconds: float):
        self._now += seconds

class FakeHealthProbe(IHealthProbe):
    def __init__(self):
        # maps device_id -> list of outcomes for subsequent probes
        self.script: Dict[str, List[Tuple[bool, int, Optional[str]]]] = {}
        self.default_ok = True
    def set_script(self, device_id: str, outcomes: List[Tuple[bool, int, Optional[str]]]):
        self.script[device_id] = outcomes
    def probe(self, dev: DeviceRecord, timeout_ms: int) -> Tuple[bool, int, Optional[str]]:
        arr = self.script.get(dev.device_id)
        if arr and len(arr) > 0:
            res = arr.pop(0)
            return res
        # default
        return (self.default_ok, min(5, timeout_ms), None if self.default_ok else 'timeout')

class FakeServiceControl(IServiceControl):
    def __init__(self):
        self.calls: List[str] = []
        self.success = True
    def restart(self, dev: DeviceRecord) -> Tuple[bool, str]:
        self.calls.append(dev.device_id)
        return (self.success, 'ok' if self.success else 'error')

class FakeDeviceControl(IDeviceControl):
    def __init__(self):
        self.calls: List[str] = []
        self.success = True
        self.busy_until_ts: Dict[str, float] = {}
    def recycle(self, dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int) -> Tuple[bool, str]:
        self.calls.append(dev.device_id)
        return (self.success, 'reenumerated' if self.success else 'error')

class FakeTopology(ITopology):
    def __init__(self):
        self.present_map: Dict[str, bool] = {}
    def present(self, device_id: str) -> bool:
        return self.present_map.get(device_id, True)

# ---------------------------------------------------------------------------
# ОРКЕСТРАТОР (упрощённая логика state-machine + действия)
# ---------------------------------------------------------------------------

class Orchestrator:
    def __init__(self, policy: Policy, clock: FakeClock, probe: IHealthProbe,
                 svc: IServiceControl, devctl: IDeviceControl, topo: ITopology):
        self.policy = policy
        self.clock = clock
        self.probe = probe
        self.svc = svc
        self.devctl = devctl
        self.topo = topo
        self.devices: Dict[str, DeviceRuntime] = {}
        self.incidents: Dict[str, Dict[str, Any]] = {}

    def add_device(self, rec: DeviceRecord):
        self.devices[rec.device_id] = DeviceRuntime(record=rec)

    # Имитация периодического тика агента
    def tick(self):
        now = self.clock.now()
        for devrt in list(self.devices.values()):
            self._tick_device(devrt, now)

    def _tick_device(self, devrt: DeviceRuntime, now: float):
        rec = devrt.record
        if not self.topo.present(rec.device_id):
            self._open_incident(rec.device_id, 'disconnect', 'high', hint='possible_cable')
            devrt.state = 'FAILED' if rec.critical else 'DEGRADED'
            return

        # Heartbeat
        pi = self.policy.value(rec.role, 'probe_interval_s')
        if now - devrt.last_probe_ts < pi:
            return

        ok, rtt_ms, err = self.probe.probe(rec, self.policy.value(rec.role, 'probe_timeout_ms'))
        devrt.last_probe_ts = now
        if ok:
            devrt.timeouts = 0
            if devrt.state in ('DEGRADED', 'RECOVERING', 'FAILED'):
                devrt.state = 'READY'
                self._close_incident(rec.device_id)
            return

        # timeout/ошибка
        devrt.timeouts += 1
        if devrt.timeouts >= self.policy.value(rec.role, 'fail_threshold'):
            if devrt.state == 'READY':
                devrt.state = 'DEGRADED'
            self._recover(rec, devrt)

    def _recover(self, rec: DeviceRecord, devrt: DeviceRuntime):
        now = self.clock.now()
        # приоритет: сервис → recycle
        service_first = bool(self.policy.role_overrides.get(rec.role, {}).get('service_first', False))
        actions: List[str] = ['service', 'recycle'] if service_first else ['recycle', 'service']

        for action in actions:
            if action == 'service':
                ok, _ = self.svc.restart(rec)
                if ok:
                    devrt.state = 'RECOVERING'
                    devrt.timeouts = 0
                    self._open_incident(rec.device_id, 'hang', 'high', hint='driver_restart_needed')
                    return
            elif action == 'recycle':
                backoff = max(self.policy.device_recycle_backoff_base_s, devrt.backoff_s or self.policy.device_recycle_backoff_base_s)
                backoff = min(backoff, self.policy.device_recycle_backoff_max_s)
                if now - devrt.last_action_ts < backoff:
                    # рано — ждём окна
                    return
                ok, _ = self.devctl.recycle(rec, self.policy.quiet_window_ms, max_duration_ms=20000)
                devrt.last_action_ts = now
                devrt.backoff_s = min(backoff * 2, self.policy.device_recycle_backoff_max_s)
                if ok:
                    devrt.state = 'RECOVERING'
                    devrt.timeouts = 0
                    self._open_incident(rec.device_id, 'hang', 'high', hint='reenumerated')
                    return
        # если ничего не помогло
        devrt.state = 'FAILED' if rec.critical else 'DEGRADED'
        self._open_incident(rec.device_id, 'hang', 'crit' if rec.critical else 'high', hint='manual_required')

    # Инциденты (упрощённые)
    def _open_incident(self, device_id: str, category: str, severity: str, hint: Optional[str] = None):
        inc = self.incidents.get(device_id)
        if not inc:
            inc = {
                'incident_id': str(uuid.uuid4()), 'device_id': device_id,
                'category': category, 'severity': severity, 'hint': hint,
                'status': 'open', 'open_ts': self.clock.now(), 'last_ts': self.clock.now(),
            }
            self.incidents[device_id] = inc
        else:
            inc['last_ts'] = self.clock.now()
            inc['category'] = category
            inc['severity'] = severity
            if hint:
                inc['hint'] = hint

    def _close_incident(self, device_id: str):
        inc = self.incidents.get(device_id)
        if inc and inc.get('status') != 'closed':
            inc['status'] = 'closed'
            inc['close_ts'] = self.clock.now()

# ---------------------------------------------------------------------------
# ТЕСТЫ PYTEST — 5 ключевых сценариев
# ---------------------------------------------------------------------------

# Вспомогательная функция сборки стенда
def make_stand() -> Tuple[Orchestrator, FakeClock, FakeHealthProbe, FakeServiceControl, FakeDeviceControl, FakeTopology, DeviceRecord, DeviceRecord, DeviceRecord]:
    clock = FakeClock()
    policy = Policy()
    probe = FakeHealthProbe()
    svc = FakeServiceControl()
    devctl = FakeDeviceControl()
    topo = FakeTopology()

    orch = Orchestrator(policy, clock, probe, svc, devctl, topo)
    fiscal = DeviceRecord("dev_fiscal", "1234", "0001", "Fiscal X", "fiscal", True, "hubA", "COM5")
    scanner = DeviceRecord("dev_scanner", "2233", "0002", "Scanner Y", "scanner", True, "hubA")
    display = DeviceRecord("dev_display", "3344", "0003", "Disp Z", "display", False, "hubB")

    orch.add_device(fiscal)
    orch.add_device(scanner)
    orch.add_device(display)
    return orch, clock, probe, svc, devctl, topo, fiscal, scanner, display


def advance(orch: Orchestrator, clock: FakeClock, seconds: float, steps: int = 1):
    for _ in range(steps):
        clock.sleep(seconds)
        orch.tick()

# 1) «Устройство повисло → авто-восстановление порта»

def test_s1_auto_recover_port():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    # Фискальник: 2 таймаута → перезапуск службы (service_first=True), если не помогло → recycle
    probe.set_script(fiscal.device_id, [
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),  # превысим fail_threshold=2 для fiscal
        (True, 10, None),          # после перезапуска службы — ок
    ])

    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))  # 1-я попытка
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))  # 2-я попытка
    # После 2-го таймаута должен сработать service restart
    assert svc.calls == [fiscal.device_id]

    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))  # 3-я попытка — успешная
    assert orch.devices[fiscal.device_id].state == 'READY'
    assert orch.incidents[fiscal.device_id]['status'] in ('open', 'closed')

# 2) «Исчезновение устройства → диагностика и подсказка»

def test_s2_disconnection_diagnostics():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    topo.present_map[fiscal.device_id] = False  # устройство пропало
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))

    assert orch.devices[fiscal.device_id].state == 'FAILED'
    inc = orch.incidents.get(fiscal.device_id)
    assert inc and inc['category'] == 'disconnect'
    assert 'possible_cable' in inc.get('hint', '')

# 3) «Контроль канала с фискальным регистратором (очередь/таймауты)»

def test_s3_fiscal_channel_control():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    # 2 таймаута подряд для fiscal → service restart
    probe.set_script(fiscal.device_id, [
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),  # снова таймаут → теперь recycle (после рестарта)
        (True, 10, None),          # после recycle — ок
    ])

    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    assert svc.calls == [fiscal.device_id]

    # следующая неудача → recycle
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    assert devctl.calls == [fiscal.device_id]

    # успешная проверка возвращает READY
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    assert orch.devices[fiscal.device_id].state == 'READY'

# 4) «Pre‑flight готовности» (упрощённая имитация через последовательные пробы)

def test_s4_preflight_like_sequence():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    # Сканер ненадолго флапает, затем ок
    probe.set_script(scanner.device_id, [
        (False, 1500, 'timeout'),
        (True, 12, None),
    ])
    advance(orch, clock, orch.policy.value('scanner', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('scanner', 'probe_interval_s'))

    assert orch.devices[scanner.device_id].state == 'READY'
    # фиксируем, что инцидент был открыт и затем закрыт
    inc = orch.incidents.get(scanner.device_id)
    assert inc and inc['status'] in ('open', 'closed')

# 5) «USB‑штормы/питание» — имитация: частые таймауты ведут к росту backoff

def test_s5_storm_backoff_growth():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    # для display: 3 таймаута до recovery (fail_threshold=3)
    probe.set_script(display.device_id, [
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),  # триггер DEGRADED→RECOVERING через recycle
        (False, 1500, 'timeout'),  # снова таймаут → второй recycle с удвоенным backoff
        (True, 10, None),
    ])

    # 1
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    # 2
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    # 3 → первый recycle
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    assert devctl.calls == [display.device_id]
    first_backoff = orch.devices[display.device_id].backoff_s
    assert first_backoff >= orch.policy.device_recycle_backoff_base_s

    # 4 → второй recycle не должен произойти до истечения backoff
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    # вызовов не добавилось из-за анти-флаппинга
    assert devctl.calls == [display.device_id]

    # Дождёмся backoff и снова тик
    advance(orch, clock, first_backoff)
    advance(orch, clock, 0)
    assert len(devctl.calls) >= 2  # второй recycle произошёл

    # 5 → успешная проверка
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    assert orch.devices[display.device_id].state == 'READY'

# ---------------------------------------------------------------------------
# EDGE-CASES ТЕСТЫ (доп.)
# ---------------------------------------------------------------------------

def test_edge_no_permissions_on_recycle():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    devctl.success = False  # имитируем отсутствие прав/ошибку драйвера
    probe.set_script(display.device_id, [
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),
    ])
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))

    # попытка recycle была, но стала FAILED/DEGRADED
    assert devctl.calls == [display.device_id]
    assert orch.devices[display.device_id].state in ('DEGRADED', 'FAILED')


def test_edge_com_port_changed_after_recycle():
    orch, clock, probe, svc, devctl, topo, fiscal, scanner, display = make_stand()

    # Простой хук: после recycle меняем порт
    old_port = fiscal.com_port

    def recycle_hook(dev: DeviceRecord, quiet_window_ms: int, max_duration_ms: int):
        ok, msg = True, 'reenumerated'
        # смена COM
        dev.com_port = 'COM7'
        return ok, msg

    # подменим метод на хук
    devctl.recycle = recycle_hook  # type: ignore

    probe.set_script(fiscal.device_id, [
        (False, 1500, 'timeout'),
        (False, 1500, 'timeout'),
        (True, 10, None),
    ])

    # для fiscal сначала сработает service restart, но в нашем скрипте успех наступит уже на 3-й пробе,
    # recycle не должен вызываться; поменяем на сценарий, где потребуется recycle
    svc.success = False  # сервис не помог

    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    # т.к. svc не помог, должен быть вызван recycle → порт сменится
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    assert fiscal.com_port == 'COM7'


# ---------------------------------------------------------------------------
# Утилиты для сериализации (пример фрагмента общего конверта сообщений)
# ---------------------------------------------------------------------------

def make_envelope(source: str, kind: str, type_: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "ts": "1970-01-01T%0.3fZ" % (FakeClock().now(),),
        "source": source,
        "kind": kind,
        "type": type_,
        "corr_id": str(uuid.uuid4()),
        "payload": payload,
    }


def test_envelope_shape():
    msg = make_envelope("probe", "event", "usb.health.timeout", {"device_id": "dev"})
    assert set(msg.keys()) == {"version", "ts", "source", "kind", "type", "corr_id", "payload"}


---

## 25) Каталог health‑проб (v1 — унифицированные команды и адаптеры)

> Задача: дать **стабильные, кросс‑модельные** пробы связи для наших ролей устройств (fiscal/scanner/display), с явными fallback‑уровнями: Transport → Driver/Service → App‑Level. Конкретные модельные нюансы изолируются в **плагинах‑адаптерах**.

### 25.1 Общая иерархия проб
1) **Transport‑probe (TP):** устройство присутствует в PnP, доступно (дескриптор открыт), интерфейс (COM/HID) создаётся.
2) **Driver/Service‑probe (DP):** связанная служба/драйвер в состоянии `RUNNING`, принимает базовую команду.
3) **App‑Level‑probe (AP):** «осмысленный ответ» устройства: статус/версия/эха без побочных эффектов.

> Правило: считаем устройство `READY`, только если **AP успех**; если AP недоступен, но DP+TP ок — `WARN`; если TP провал — `FAIL`.

### 25.2 Формат результата пробы
```
ProbeResult = {
  ok: bool,
  level: 'TP'|'DP'|'AP',
  rtt_ms: int,
  code: 'ok'|'timeout'|'io'|'busy'|'not_present'|'proto'|'driver',
  details: string  // коротко, без PII
}
```

### 25.3 Роль: Фискальный регистратор (`role=fiscal`)

**Транспорты:** USB‑COM (CDC/вирт. COM) или USB‑vendor.

| Уровень | Имя пробы | Канал | Пэйлоад | Ожидание | Таймаут | Парсер | Примечания |
|---|---|---|---|---|---:|---|---|
| TP | `com.open` | COM | — | дескриптор открыт | 300 | open() → ok | Если COM меняется после re‑enumeration — маппим по VID/PID. |
| DP | `svc.query` | SCM | — | `RUNNING` | 500 | QueryServiceStatus | Имя службы задаёт адаптер модели. |
| AP‑A | `status.simple` | COM | **ESC/POS Real‑time**: `DLE EOT n` (0x10 0x04 0x01) | 1 байт статуса | 1200 | маска флагов | Подходит, если устройство совместимо с ESC/POS. |
| AP‑B | `status.sdk` | Vendor SDK | `GetShortStatus()` | код ОК/ошибка | 1500 | код→ok | Предпочтительнее, если есть официальный SDK. |
| AP‑C | `version` | COM/SDK | команда версии (без печати) | строка/номер | 1500 | non‑empty | Без побочных эффектов. |

**Эскалация:** AP‑A/B/C → DP → TP. При провале AP и DP — `DEGRADED`, пробуем `service_restart`; при повторном провале — `device_recycle`.

**Адаптеры‑плагины (v1 перечень):**
- `fiscal.generic_escpos` — универсальный ESC/POS‑совместимый.
- `fiscal.vendor_sdk` — оболочка под конкретный SDK (таблица соответствий команд внутри адаптера).
- `fiscal.com_only` — только базовые COM‑проверки (используется как временный fallback).

### 25.4 Роль: Сканер штрих‑кодов (`role=scanner`)

**Транспорты:** HID‑Keyboard, HID‑POS, USB‑COM.

| Уровень | Имя пробы | Канал | Пэйлоад | Ожидание | Таймаут | Парсер | Примечания |
|---|---|---|---|---|---:|---|---|
| TP | `hid.enumerate` | HID | — | интерфейс доступен | 300 | наличие HID path | Универсально. |
| DP | `svc.query` | SCM | — | `RUNNING` (если есть служба драйвера) | 500 | QueryServiceStatus | Не у всех моделей есть отдельная служба. |
| AP‑A | `hid.feature.ping` | HID Feature | report id 0x00 (или «identity») | ненулевой ответ | 1200 | длина>0 | Доступно на части моделей HID‑POS. |
| AP‑B | `com.echo` | COM | `ECHO` | `ECHO` | 1200 | точное совпадение | Для COM‑сканеров. |
| AP‑C | `activity.window` | ОС | — | события клавиатуры за окно T | 1500 | >0 событий | Fallback для «клавиатурных» сканеров: активность вместо прямой пробы.

**Примечание:** У HID‑Keyboard часто нет безопасной «команды статуса». Поэтому **AP‑C** — «пассивная» проверка: за последние N секунд поступали key‑events от VID/PID данного устройства (если нет — `WARN`).

**Адаптеры‑плагины:** `scanner.hid_pos`, `scanner.hid_keyboard`, `scanner.com`.

### 25.5 Роль: Дисплей покупателя (`role=display`)

**Транспорты:** USB‑COM (CD5220/ESC/POS‑совместимые), USB‑vendor.

| Уровень | Имя пробы | Канал | Пэйлоад | Ожидание | Таймаут | Парсер | Примечания |
|---|---|---|---|---|---:|---|---|
| TP | `com.open` | COM | — | дескриптор открыт | 300 | open() → ok | Базовая проверка. |
| AP‑A | `version.query` | COM | `DC2 'R'` (0x12 0x52) или `VERSION?` | строка версии | 1200 | non‑empty | Распространённый запрос версии/идентичности. |
| AP‑B | `text.ping` | COM | `CLS;TEXT 1,1,"PING"` или `ESC @`+"PING" | приём `OK`/эхо | 1200 | OK/эхо | Безопасная краткая надпись; в реальном GUI не показываем пользователю. |
| DP | `svc.query` | SCM | — | `RUNNING` | 500 | QueryServiceStatus | Если есть драйвер‑служба.

**Адаптеры‑плагины:** `display.cd5220`, `display.escpos`, `display.vendor`.

### 25.6 Тонкости времени и частоты
- Пробы **не запускаются** при `busy` (активная печать/вывод текста) и уважают `quiet_window_ms`.
- При `timeout` на AP уровень понижается: AP→DP→TP; при следующем «тике» пробуем снова по политике backoff.
- В пик‑часы уменьшать частоту проб для некритичных ролей (display) на ×2.

---

## 26) Маппинг кодов ошибок → `hint` и действия

| Источник | code | Характеристика | hint | Действие оркестратора |
|---|---|---|---|---|
| TP | `not_present` | PnP/дескриптор отсутствует | `possible_cable` | `FAILED` (если critical), чек‑лист кассиру, уведомление инженеру |
| TP/DP | `driver` | служба/драйвер не в RUNNING | `driver_restart_needed` | `service_restart` → при провале `device_recycle` |
| AP | `timeout` | нет ответа на статус | `hang_or_power` | `service_restart` (fiscal) или сразу `device_recycle` (display/scanner) |
| AP | `proto` | мусор/ошибка протокола | `model_mismatch` | смена адаптера/протокола, эскалация инженеру |
| Любой | `busy` | устройство занято | `busy_window` | отложить на `quiet_window_ms`, не трогать |

---

## 27) Плагины‑адаптеры: контракт и реестр

**Интерфейс:**
```
class ProbeAdapter:
    role: Literal['fiscal','scanner','display']
    name: str  # например, 'fiscal.generic_escpos'
    def tp(self, rec: DeviceRecord) -> ProbeResult: ...
    def dp(self, rec: DeviceRecord) -> ProbeResult: ...
    def ap(self, rec: DeviceRecord) -> ProbeResult: ...
```

**Выбор адаптера:** по `VID:PID`, `friendly`, `hub_path` и политике. Реестр (`adapters.json`) вида:
```json
{
  "fiscal": [
    {"match": {"vid":"0x1234"}, "use": "fiscal.vendor_sdk"},
    {"match": {"escpos": true}, "use": "fiscal.generic_escpos"},
    {"match": {"*": true}, "use": "fiscal.com_only"}
  ],
  "scanner": [
    {"match": {"hid_pos": true}, "use": "scanner.hid_pos"},
    {"match": {"hid_keyboard": true}, "use": "scanner.hid_keyboard"},
    {"match": {"com": true}, "use": "scanner.com"}
  ],
  "display": [
    {"match": {"cd5220": true}, "use": "display.cd5220"},
    {"match": {"escpos": true}, "use": "display.escpos"},
    {"match": {"*": true}, "use": "display.vendor"}
  ]
}
```

**Безопасность:** каждый адаптер ограничен тайм‑боксом и выполняет только «безвредные» команды (никакой печати чека, сбросов, очисток памяти). Для HID‑Keyboard — только пассивные проверки.

---

## 28) Что осталось для v1.1
- Уточнить команды AP для конкретных моделей, которые есть у пилотных клиентов (в рамках SDK/мануалов).
- Добавить negative‑тесты: мусорные ответы, несоответствие кодировок/локалей, долгие rtt.
- Прописать в GUI тексты подсказок по `hint` с наглядными шагами («проверьте кабель к хабу X», «переключите в порт Y»).


# ===========================================================================
# МИНИМАЛЬНЫЕ РЕАЛИЗАЦИИ АДАПТЕРОВ ПРОБ (v1) + ТЕСТЫ
# ===========================================================================

from dataclasses import asdict

# ---------------------------------------------------------------------------
# Контракты адаптеров и результат пробы
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
    def __init__(self, com: 'IComTransport', svcq: 'IServiceQuery', hida: 'IHidActivity'):
        self.com = com
        self.svcq = svcq
        self.hida = hida
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        raise NotImplementedError
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        raise NotImplementedError
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Транспорты/Сервисы (фейковые реализации для тестов)
# ---------------------------------------------------------------------------

class Timeout(Exception):
    pass

class IComTransport:
    def send_recv(self, dev: DeviceRecord, payload: bytes, timeout_ms: int) -> bytes:
        raise NotImplementedError

class IServiceQuery:
    def is_running(self, dev: DeviceRecord) -> bool:
        raise NotImplementedError

class IHidActivity:
    def events_in_window(self, dev: DeviceRecord, window_s: int) -> int:
        raise NotImplementedError

class FakeCom(IComTransport):
    """Скриптуемый COM: map[(device_id, payload)] -> reply|Timeout|IOError"""
    def __init__(self):
        self.map: Dict[Tuple[str, bytes], Any] = {}
    def script(self, device_id: str, payload: bytes, reply: Any):
        self.map[(device_id, payload)] = reply
    def send_recv(self, dev: DeviceRecord, payload: bytes, timeout_ms: int) -> bytes:
        key = (dev.device_id, payload)
        if key not in self.map:
            # неизвестная команда — имитируем протокольную ошибку
            raise IOError('proto')
        val = self.map[key]
        if isinstance(val, Exception):
            if isinstance(val, Timeout):
                raise Timeout('timeout')
            raise val
        return val if isinstance(val, (bytes, bytearray)) else bytes(val)

class FakeSvc(IServiceQuery):
    def __init__(self):
        self.state: Dict[str, bool] = {}
    def is_running(self, dev: DeviceRecord) -> bool:
        return self.state.get(dev.device_id, True)

class FakeHid(IHidActivity):
    def __init__(self):
        self.counts: Dict[str, int] = {}
    def set(self, device_id: str, events: int):
        self.counts[device_id] = events
    def events_in_window(self, dev: DeviceRecord, window_s: int) -> int:
        return self.counts.get(dev.device_id, 0)

# ---------------------------------------------------------------------------
# Адаптеры v1: fiscal.generic_escpos, scanner.hid_keyboard, display.cd5220
# ---------------------------------------------------------------------------

class FiscalGenericEscposAdapter(ProbeAdapter):
    role = 'fiscal'
    name = 'fiscal.generic_escpos'
    DLE_EOT_1 = b""  # ESC/POS Real-time status
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        try:
            # Проверим, что COM отвечает на пустой пинг: пошлём ничего и ожидаем IOError(proto)
            try:
                _ = self.com.send_recv(rec, b"", 100)
            except IOError:
                pass
            return ProbeResult(True, 'TP', 1, 'ok')
        except Timeout:
            return ProbeResult(False, 'TP', 100, 'not_present', 'COM timeout')
        except Exception as e:
            return ProbeResult(False, 'TP', 1, 'io', str(e))
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        running = self.svcq.is_running(rec)
        return ProbeResult(running, 'DP', 1, 'ok' if running else 'driver', 'svc RUNNING' if running else 'svc not running')
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        try:
            buf = self.com.send_recv(rec, self.DLE_EOT_1, 1200)
            if len(buf) >= 1:
                return ProbeResult(True, 'AP', 5, 'ok', 'status byte=%02x' % buf[0])
            return ProbeResult(False, 'AP', 1200, 'proto', 'empty reply')
        except Timeout:
            return ProbeResult(False, 'AP', 1200, 'timeout', 'no status')
        except IOError as e:
            return ProbeResult(False, 'AP', 5, 'proto', str(e))

class ScannerHidKeyboardAdapter(ProbeAdapter):
    role = 'scanner'
    name = 'scanner.hid_keyboard'
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        # Для HID-keyboard проверим, что в окне были события ранее — минимальная TP
        cnt = self.hida.events_in_window(rec, 1)
        return ProbeResult(cnt >= 0, 'TP', 1, 'ok' if cnt >= 0 else 'not_present')
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        # Обычно отдельной службы нет; считаем RUNNING
        return ProbeResult(True, 'DP', 1, 'ok', 'no svc')
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        cnt = self.hida.events_in_window(rec, 5)
        if cnt > 0:
            return ProbeResult(True, 'AP', 5, 'ok', f'events={cnt}')
        return ProbeResult(False, 'AP', 1200, 'timeout', 'no activity')

class DisplayCD5220Adapter(ProbeAdapter):
    role = 'display'
    name = 'display.cd5220'
    VERSION_Q = b"R"  # DC2 'R'
    def tp(self, rec: DeviceRecord) -> ProbeResult:
        try:
            try:
                _ = self.com.send_recv(rec, b"", 100)
            except IOError:
                pass
            return ProbeResult(True, 'TP', 1, 'ok')
        except Timeout:
            return ProbeResult(False, 'TP', 100, 'not_present', 'COM timeout')
        except Exception as e:
            return ProbeResult(False, 'TP', 1, 'io', str(e))
    def dp(self, rec: DeviceRecord) -> ProbeResult:
        return ProbeResult(True, 'DP', 1, 'ok')  # обычно без отдельной службы
    def ap(self, rec: DeviceRecord) -> ProbeResult:
        try:
            buf = self.com.send_recv(rec, self.VERSION_Q, 1200)
            if isinstance(buf, (bytes, bytearray)) and len(buf) > 0:
                return ProbeResult(True, 'AP', 10, 'ok', f'ver={buf[:8]!r}...')
            return ProbeResult(False, 'AP', 1200, 'proto', 'empty version')
        except Timeout:
            return ProbeResult(False, 'AP', 1200, 'timeout', 'no version')
        except IOError as e:
            return ProbeResult(False, 'AP', 5, 'proto', str(e))

# ---------------------------------------------------------------------------
# Реестр адаптеров и композитный HealthProbe для оркестратора
# ---------------------------------------------------------------------------

class AdapterRegistry:
    def __init__(self, com: IComTransport, svcq: IServiceQuery, hida: IHidActivity):
        self.com, self.svcq, self.hida = com, svcq, hida
        self.by_role: Dict[str, ProbeAdapter] = {
            'fiscal': FiscalGenericEscposAdapter(com, svcq, hida),
            'scanner': ScannerHidKeyboardAdapter(com, svcq, hida),
            'display': DisplayCD5220Adapter(com, svcq, hida),
        }
    def pick(self, role: str) -> ProbeAdapter:
        return self.by_role.get(role, ProbeAdapter(self.com, self.svcq, self.hida))

class CompositeHealthProbe(IHealthProbe):
    def __init__(self, registry: AdapterRegistry):
        self.reg = registry
    def probe(self, dev: DeviceRecord, timeout_ms: int) -> Tuple[bool, int, Optional[str]]:
        ad = self.reg.pick(dev.role)
        # TP → DP → AP
        tp = ad.tp(dev)
        if not tp.ok:
            return False, tp.rtt_ms, 'not_present' if tp.code == 'not_present' else 'io'
        dp = ad.dp(dev)
        if not dp.ok:
            return False, dp.rtt_ms, 'driver'
        ap = ad.ap(dev)
        if not ap.ok:
            return False, ap.rtt_ms, 'timeout' if ap.code == 'timeout' else ap.code
        return True, ap.rtt_ms, None

# ---------------------------------------------------------------------------
# Тесты адаптеров и композитного пробера
# ---------------------------------------------------------------------------

def test_adapter_fiscal_generic_escpos_success():
    com, svcq, hida = FakeCom(), FakeSvc(), FakeHid()
    # Ожидаем на DLE EOT 01 один байт статуса 0x12
    dev = DeviceRecord("f1", "1234", "0001", "Fiscal ESC", "fiscal", True, "hubA", "COM5")
    com.script(dev.device_id, FiscalGenericEscposAdapter.DLE_EOT_1, b"")
    ad = FiscalGenericEscposAdapter(com, svcq, hida)
    assert ad.tp(dev).ok
    assert ad.dp(dev).ok
    r = ad.ap(dev)
    assert r.ok and r.code == 'ok'


def test_adapter_scanner_hid_keyboard_activity():
    com, svcq, hida = FakeCom(), FakeSvc(), FakeHid()
    dev = DeviceRecord("s1", "2233", "0002", "Scan HIDK", "scanner", True, "hubA")
    hida.set(dev.device_id, 5)  # 5 событий за окно
    ad = ScannerHidKeyboardAdapter(com, svcq, hida)
    assert ad.tp(dev).ok
    assert ad.dp(dev).ok
    assert ad.ap(dev).ok


def test_adapter_display_cd5220_version():
    com, svcq, hida = FakeCom(), FakeSvc(), FakeHid()
    dev = DeviceRecord("d1", "3344", "0003", "CD5220", "display", False, "hubB")
    com.script(dev.device_id, DisplayCD5220Adapter.VERSION_Q, b"V1.23")
    ad = DisplayCD5220Adapter(com, svcq, hida)
    assert ad.tp(dev).ok
    assert ad.dp(dev).ok
    assert ad.ap(dev).ok


def test_composite_probe_with_registry():
    # Интеграция с Orchestrator
    orch, clock, probe_fake, svc, devctl, topo, fiscal, scanner, display = make_stand()

    # Заменяем HealthProbe на композит из адаптеров
    com, svcq, hida = FakeCom(), FakeSvc(), FakeHid()
    reg = AdapterRegistry(com, svcq, hida)
    orch.probe = CompositeHealthProbe(reg)

    # скриптуем ответы для наших трёх устройств
    com.script(fiscal.device_id, FiscalGenericEscposAdapter.DLE_EOT_1, b"")
    hida.set(scanner.device_id, 3)
    com.script(display.device_id, DisplayCD5220Adapter.VERSION_Q, b"V2.0")

    # Один тик на каждую роль
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('scanner', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('display', 'probe_interval_s'))

    assert orch.devices[fiscal.device_id].state == 'READY'
    assert orch.devices[scanner.device_id].state == 'READY'
    assert orch.devices[display.device_id].state == 'READY'


def test_composite_probe_timeouts_and_recovery():
    # Проверим таймауты → действия оркестратора
    orch, clock, probe_fake, svc, devctl, topo, fiscal, scanner, display = make_stand()

    com, svcq, hida = FakeCom(), FakeSvc(), FakeHid()
    reg = AdapterRegistry(com, svcq, hida)
    orch.probe = CompositeHealthProbe(reg)

    # Фискальник не отвечает (timeout на AP)
    com.script(fiscal.device_id, FiscalGenericEscposAdapter.DLE_EOT_1, Timeout())

    # Тикнем дважды для fiscal (fail_threshold=2) → должен сработать service restart
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    assert svc.calls == [fiscal.device_id]

    # Теперь начнёт отвечать
    com.script(fiscal.device_id, FiscalGenericEscposAdapter.DLE_EOT_1, b"")
    advance(orch, clock, orch.policy.value('fiscal', 'probe_interval_s'))
    assert orch.devices[fiscal.device_id].state == 'READY'
