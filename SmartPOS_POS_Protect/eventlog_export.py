# -*- coding: utf-8 -*-
"""
SmartPOS EventLog Exporter (EVTX/CSV) — без внешних зависимостей
"""
import os, sys, subprocess, datetime
from pathlib import Path


DEFAULT_LOGS = [
'Application',
'System',
'Microsoft-Windows-PrintService/Operational',
'Microsoft-Windows-PrintService/Admin',
'Microsoft-Windows-Diagnostics-Performance/Operational'
]


class EventLogExporter:
def __init__(self, out_dir: str, logs=None):
self.out_dir = Path(out_dir)
self.logs = logs or DEFAULT_LOGS
self.out_dir.mkdir(parents=True, exist_ok=True)
def _run(self, args):
return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
def export_evtx(self):
results = []
ts = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
for log in self.logs:
safe = log.replace('/', '%4')
dst = self.out_dir / f'{safe}_{ts}.evtx'
r = self._run(['wevtutil', 'epl', log, str(dst)])
results.append((log, dst, r.returncode, r.stderr.decode('utf-8','ignore')))
return results
def export_csv(self, max_events: int = 2000):
results = []
ts = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
for log in self.logs:
safe = log.replace('/', '%4')
dst = self.out_dir / f'{safe}_{ts}.csv'
ps = ("Get-WinEvent -LogName '" + log + "' | "
f"Select-Object -First {max_events} | "
"Export-Csv -NoTypeInformation -Path '" + str(dst) + "'")
r = self._run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-Command', ps])
results.append((log, dst, r.returncode, r.stderr.decode('utf-8','ignore')))
return results


if __name__ == '__main__':
out = sys.argv[1] if len(sys.argv) > 1 else 'C:/POS/export/eventlog'
logs = sys.argv[2].split(',') if len(sys.argv) > 2 else None
exp = EventLogExporter(out, logs)
ev = exp.export_evtx()
cv = exp.export_csv(2000)
print('\n'.join([f'EVTX {x[0]} -> {x[1]} rc={x[2]}' for x in ev]))
print('\n'.join([f'CSV {x[0]} -> {x[1]} rc={x[2]}' for x in cv]))