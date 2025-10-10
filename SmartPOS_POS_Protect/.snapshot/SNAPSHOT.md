POS_Protect snapshot (branch: feature/USB_smart_standalone, commit: 64747c6)
Generated: 2025-10-05T21:18:50

-----8<----- BEGIN FILE: SmartPOS_POS_Protect/config/pos_protect_policies.json
{
  "version": "1.0",
  "windows_profile": "LTSC2021",
  "collector": {
    "enable_diagnostic_profile": true,
    "eventlog": {
      "lookback_days": 1,
      "channels": [
        {
          "log": "System",
          "providers": [
            "Service Control Manager",
            "Microsoft-Windows-PrintService",
            "Microsoft-Windows-Disk",
            "Microsoft-Windows-Ntfs",
            "Microsoft-Windows-Kernel-Power"
          ],
          "days_lookback": 1
        },
        {
          "log": "Application",
          "providers": [
            ".NET Runtime",
            "Application Error"
          ],
          "days_lookback": 1
        }
      ],
      "max_events_per_tick": 200,
      "wer": {
        "enabled": true,
        "lookback_days": 7,
        "max_reports_per_tick": 50,
        "critical_processes": [
          "smartpos_agent.exe",
          "pos_frontend.exe",
          "pos_printer_service.exe"
        ],
        "ignore_processes": [
          "AmneziaVPN.exe",
          "AmneziaVPN-service.exe",
          "Dell.DigitalDelivery.exe",
          "Dell.TechHub.*"
        ],
        "dedup_key": [
          "proc",
          "faulting_module",
          "exception_code"
        ]
      }
    },
    "reliability": {
      "enabled": true,
      "days_lookback": 7
    },
    "services": {
      "watch": [
        "Spooler"
      ],
      "restart_threshold_per_hour": 3
    },
    "verbose": true
  },
  "classifier": {
    "critical_processes": [
      "smartpos_agent.exe",
      "pos_frontend.exe",
      "pos_printer_service.exe",
      "SmartPOS",
      "POS",
      "CashRegister",
      "Terminal",
      "PrintService",
      "Spooler"
    ],
    "ignore_processes": [
      "AmneziaVPN.exe",
      "AmneziaVPN-service.exe",
      "Dell.DigitalDelivery.exe",
      "Dell.TechHub.*",
      "MicrosoftEdge",
      "Edge",
      "Chrome",
      "Firefox",
      "Notepad",
      "Calculator",
      "Paint",
      "Windows Update",
      "WinGet",
      "CBS",
      "TrustedInstaller",
      "wuauclt",
      "wuaueng",
      "wuauserv",
      "wuuhosdeployment"
    ],
    "max_duplicates_per_tick": 3,
    "access_violation_codes": [
      "c0000005"
    ],
    "sev_rules": [
      {
        "when_proc_in": "critical_processes",
        "severity": "CRIT"
      },
      {
        "when_proc_in": "ignore_processes",
        "severity": "IGNORE"
      },
      {
        "default": true,
        "severity": "WARN"
      }
    ],
    "exception_mapping": {
      "c0000005": "AccessViolation",
      "c0000006": "InPageError",
      "c000001d": "IllegalInstruction",
      "c0000025": "NoncontinuableException",
      "c0000026": "InvalidDisposition",
      "c000008f": "ArrayBoundsExceeded",
      "c0000094": "IntegerDivideByZero",
      "c0000096": "PrivilegedInstruction",
      "c00000fd": "StackOverflow"
    }
  },
  "rules": [
    {
      "match": {
        "source": "EventLog.System",
        "provider": "Disk",
        "event_id": [
          51,
          153
        ]
      },
      "issue_code": "DISK_IO_WARN",
      "severity": "WARN",
      "hint": "РџСЂРѕРІРµСЂСЊС‚Рµ РєР°Р±РµР»СЊ/РїРѕСЂС‚; СЃРєРѕСЂСЂРµР»РёСЂРѕРІР°С‚СЊ СЃРѕ SMART; РїСЂРё РїРѕРІС‚РѕСЂР°С… вЂ” РїР»Р°РЅРѕРІС‹Р№ chkdsk.",
      "plan": [
        {
          "do": "link_smart",
          "timeout_ms": 2000
        },
        {
          "do": "schedule",
          "task": "plan_chkdsk",
          "window": "02:00-05:00",
          "if_repeated_within_min": 60
        }
      ],
      "rate_limit_per_hour": 3
    },
    {
      "match": {
        "source": "EventLog.System",
        "provider": "Service Control Manager",
        "event_id": [
          7031,
          7034
        ],
        "service": "Spooler"
      },
      "issue_code": "PRINT_SPOOLER_STUCK",
      "severity": "WARN",
      "plan": [
        {
          "do": "restart_service",
          "name": "Spooler",
          "timeout_ms": 15000
        },
        {
          "do": "clear_print_queue",
          "if_idle_minutes": 10
        }
      ],
      "rate_limit_per_hour": 6
    },
    {
      "match": {
        "source": "WER",
        "crash": true,
        "proc_mask": [
          "*POS*"
        ]
      },
      "issue_code": "POS_APP_CRASH",
      "severity": "WARN",
      "plan": [
        {
          "do": "collect_wer_bundle"
        },
        {
          "do": "mark_for_review"
        }
      ]
    }
  ],
  "hardening": {
    "allow_undocumented": false,
    "power": {
      "usb_selective_suspend": "Disable"
    },
    "defender": {
      "add_exclusions": [
        "C:\\\\SmartPOS\\\\logs",
        "C:\\\\SmartPOS\\\\agent"
      ]
    }
  },
  "safety_guards": {
    "work_hours_block": [
      "07:30-23:30"
    ],
    "dangerous_actions": [
      "plan_chkdsk",
      "run_dism_restorehealth",
      "reset_wmi"
    ],
    "require_off_hours": true
  }
}
-----8<----- END FILE: SmartPOS_POS_Protect/config/pos_protect_policies.json

-----8<----- BEGIN FILE: SmartPOS_POS_Protect/src/python/shared/pipeline.py
#!/usr/bin/env python3
"""РЈРЅРёС„РёС†РёСЂРѕРІР°РЅРЅС‹Р№ pipeline РґР»СЏ SmartPOS POS Protect."""

import json, pathlib, sys
from analyzer.rules import build_plans
from analyzer.classify import classify_events
from collector.evt_collect import collect_eventlog
from collector.wer_collect import collect_wer

# Р”РѕР±Р°РІР»СЏРµРј СЂРѕРґРёС‚РµР»СЊСЃРєСѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ РІ Python path РґР»СЏ РёРјРїРѕСЂС‚Р° РјРѕРґСѓР»РµР№
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# РЈРЅРёС„РёС†РёСЂРѕРІР°РЅРЅС‹Р№ РїСѓС‚СЊ Рє РєРѕРЅС„РёРіСѓ (СЂР°Р±РѕС‚Р°РµС‚ РёР· Р»СЋР±РѕР№ РґРёСЂРµРєС‚РѕСЂРёРё)
ROOT = pathlib.Path(__file__).resolve().parents[3]
CFG = ROOT / "config" / "pos_protect_policies.json"

def load_cfg():
    """Р—Р°РіСЂСѓР·РєР° РєРѕРЅС„РёРіСѓСЂР°С†РёРё."""
    with open(CFG, "r", encoding="utf-8") as f:
        return json.load(f)

def pipeline_tick(cfg, verbose=False):
    """РЈРЅРёС„РёС†РёСЂРѕРІР°РЅРЅС‹Р№ pipeline РґР»СЏ СЃР±РѕСЂР°, РєР»Р°СЃСЃРёС„РёРєР°С†РёРё Рё РїР»Р°РЅРёСЂРѕРІР°РЅРёСЏ."""
    if verbose:
        print("Loading configuration...", file=sys.stderr)
  
    # РЎР±РѕСЂ EventLog СЃРѕР±С‹С‚РёР№
    if verbose:
        print("Collecting event log data...", file=sys.stderr)
    events = collect_eventlog(cfg["collector"]["eventlog"])
    if verbose:
        print(f"Collected {len(events)} events", file=sys.stderr)
    
    # РЎР±РѕСЂ WER СЃРѕР±С‹С‚РёР№
    if cfg["collector"]["eventlog"].get("wer", {}).get("enabled"):
        if verbose:
            print("Collecting WER data...", file=sys.stderr)
        wer_events = collect_wer(cfg["collector"]["eventlog"]["wer"])
        events += wer_events
        if verbose:
            print(f"Total events after WER: {len(events)}", file=sys.stderr)
    
    # РљР»Р°СЃСЃРёС„РёРєР°С†РёСЏ СЃРѕР±С‹С‚РёР№
    if verbose:
        print("Classifying events...", file=sys.stderr)
    issues = classify_events(events, cfg)
    
    # РџРѕСЃС‚СЂРѕРµРЅРёРµ РїР»Р°РЅРѕРІ
    plans = build_plans(issues, cfg)
    
    return {
        "events": events,
        "issues": issues,
        "plans": plans,
        "eventlog_count": len(events) - (len(wer_events) if cfg["collector"]["eventlog"].get("wer", {}).get("enabled") else 0),
        "wer_count": len(wer_events) if cfg["collector"]["eventlog"].get("wer", {}).get("enabled") else 0
    }

-----8<----- END FILE: SmartPOS_POS_Protect/src/python/shared/pipeline.py

-----8<----- BEGIN FILE: SmartPOS_POS_Protect/src/python/cli/pos_protect_cli.py
import json, pathlib, sys

# Р”РѕР±Р°РІР»СЏРµРј СЂРѕРґРёС‚РµР»СЊСЃРєСѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ РІ Python path РґР»СЏ РёРјРїРѕСЂС‚Р° РјРѕРґСѓР»РµР№
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from shared.pipeline import load_cfg, pipeline_tick

if __name__ == "__main__":
    cfg = load_cfg()
    result = pipeline_tick(cfg, verbose=True)
  
    print("Results:", file=sys.stderr)
    print(json.dumps(result["issues"], ensure_ascii=False, indent=2))

-----8<----- END FILE: SmartPOS_POS_Protect/src/python/cli/pos_protect_cli.py

-----8<----- BEGIN FILE: SmartPOS_POS_Protect/src/python/pos_protect_service.py
import json, time, pathlib
from shared.log import jlog
from shared.pipeline import load_cfg, pipeline_tick
from remediate.planner import execute_plans

def tick(cfg):
    """Р’С‹РїРѕР»РЅРµРЅРёРµ РѕРґРЅРѕРіРѕ С‚РёРєР° СЃРµСЂРІРёСЃР° СЃ Р»РѕРіРёСЂРѕРІР°РЅРёРµРј."""
    try:
        # РЈРЅРёС„РёС†РёСЂРѕРІР°РЅРЅС‹Р№ pipeline
        result = pipeline_tick(cfg, verbose=False)
  
        # Р›РѕРіРёСЂРѕРІР°РЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ СЃР±РѕСЂР°
        jlog({"subsystem":"pos_protect","action":"evt_collected","result":"success",
              "labels":{"count":result["eventlog_count"]}})
        
        if result["wer_count"] > 0:
            jlog({"subsystem":"pos_protect","action":"wer_collected","result":"success",
                  "labels":{"count":result["wer_count"]}})
        
        # Р’С‹РїРѕР»РЅРµРЅРёРµ РїР»Р°РЅРѕРІ
        plans_result = execute_plans(result["plans"], cfg)
        
        # Р›РѕРіРёСЂРѕРІР°РЅРёРµ РёС‚РѕРіРѕРІРѕРіРѕ СЂРµР·СѓР»СЊС‚Р°С‚Р°
        jlog({"subsystem":"pos_protect","action":"tick","result":"ok",
              "labels":{"issues":len(result["issues"]),"plans":len(result["plans"])}})
        
        return plans_result
        
    except Exception as e:
        jlog({"subsystem":"pos_protect","action":"tick","result":"error","labels":{"err":str(e)}})
        raise

def main():
    cfg = load_cfg()
    while True:
        try:
            tick(cfg)
        except Exception as e:
            jlog({"subsystem":"pos_protect","action":"tick","result":"error","labels":{"err":str(e)}})
        time.sleep(60)

if __name__ == "__main__":
    main()

-----8<----- END FILE: SmartPOS_POS_Protect/src/python/pos_protect_service.py
