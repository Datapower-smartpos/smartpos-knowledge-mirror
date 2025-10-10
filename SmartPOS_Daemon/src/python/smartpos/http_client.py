import json, urllib.request, urllib.error

def run_playbook(daemon_url: str, payload: dict) -> tuple[bool, dict | str]:
    """Вызов локального Action Daemon: POST /action/run"""
    try:
        req = urllib.request.Request(
            url=f"{daemon_url}/action/run",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return True, data
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)
