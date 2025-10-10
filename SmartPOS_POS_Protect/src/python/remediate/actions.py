import subprocess, os
from shared.log import jlog

def restart_service(name, timeout_ms=15000):
    try:
        cmd = f"Restart-Service -Name '{name}' -ErrorAction SilentlyContinue"
        subprocess.run(["powershell","-NoProfile","-Command", cmd], timeout=timeout_ms/1000)
        jlog({"subsystem":"pos_protect","action":"restart_service","result":"ok","labels":{"service":name}})
    except Exception as e:
        jlog({"subsystem":"pos_protect","action":"restart_service","result":"error","labels":{"service":name,"err":str(e)}})

def clear_print_queue(if_idle_minutes=10):
    # WARNING: This is a stub. Add idle detection before clearing in production.
    spool=r"C:\Windows\System32\spool\PRINTERS"
    try:
        for f in os.listdir(spool):
            p=os.path.join(spool,f)
            if os.path.isfile(p): os.remove(p)
        jlog({"subsystem":"pos_protect","action":"clear_print_queue","result":"ok"})
    except Exception as e:
        jlog({"subsystem":"pos_protect","action":"clear_print_queue","result":"error","labels":{"err":str(e)}})

def link_smart():
    jlog({"subsystem":"pos_protect","action":"link_smart","result":"ok"})

def collect_wer_bundle(path):
    jlog({"subsystem":"pos_protect","action":"collect_wer_bundle","result":"ok","labels":{"path":path}})

def plan_chkdsk():
    jlog({"subsystem":"pos_protect","action":"plan_chkdsk","result":"scheduled"})
