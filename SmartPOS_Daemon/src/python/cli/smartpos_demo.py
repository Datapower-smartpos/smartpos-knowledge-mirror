import json, os, argparse, sys, re

def find_config(start_dir: str) -> tuple[str, dict]:
    """
    Ищет config_smartpos.json или config.json, поднимаясь вверх от start_dir до корня диска.
    Возвращает (путь, данные). Бросает FileNotFoundError если не найдено.
    """
    cur = os.path.abspath(start_dir)
    tried = []
    while True:
        cand1 = os.path.join(cur, "config_smartpos.json")
        cand2 = os.path.join(cur, "config.json")
        for path in (cand1, cand2):
            tried.append(path)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return path, json.load(f)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    raise FileNotFoundError("Config not found. Tried: " + " | ".join(tried))

def main():
    parser = argparse.ArgumentParser(description="SmartPOS Demo (offline)")
    # По умолчанию стартуем поиск от папки, где лежит этот файл (…\src\python\cli)
    default_start = os.path.dirname(__file__)
    parser.add_argument("--base", default=default_start, help="Start folder to search config upwards")
    args = parser.parse_args()

    cfg_path, cfg = find_config(args.base)
    # Ожидаем, что база знаний лежит относительно корня проекта (где конфиг)
    project_root = os.path.dirname(cfg_path)
    dataset_path = os.path.join(project_root, "data", "kb_core", "phrases_pr.json")

    # Ленивая проверка, чтобы сообщение было понятным
    if not os.path.exists(dataset_path):
        # пробуем вариант, если data рядом со src
        alt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "kb_core", "phrases_pr.json"))
        if os.path.exists(alt):
            dataset_path = alt
        else:
            raise FileNotFoundError(f"Не найдена база фраз: {dataset_path}")

    from smartpos.intent_classifier import IntentClassifier
    from smartpos.http_client import run_playbook
    from smartpos.gui_templates import make_gui_messages

    classifier = IntentClassifier(dataset_path=dataset_path)

    print("=== SmartPOS MVP (офлайн) ===")
    print(f"[config] {cfg_path}")
    print('Введите фразу кассира (например, "печать висит"). Пустая строка — выход.')

    while True:
        try:
            user = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            break

        # Guard: ignore PowerShell/URL/command-like inputs
        cmd_like = bool(re.search(r"(?i)^(invoke-webrequest|curl|wget|get-printer|set-printer|netstat|tasklist|wmic|ping|powershell|http://|https://|[A-Za-z]:\\)", user))
        if cmd_like:
            print("[hint] Похоже, вы вставили команду PowerShell/URL. Запустите её в окне PowerShell, а сюда вводите фразы кассира (пример: 'печать висит').")
            continue

        res = classifier.classify_intent(user)
        print(f"[intent] code={res['problem_code']} conf={res['confidence']}")
        chosen = res["problem_code"]
        if res["needed_clarification"]:
            alts = [a["code"] for a in res["alternatives"]]
            print("[hint] Низкая уверенность. Выберите код:")
            options = [chosen] + alts
            for i, c in enumerate(options, 1):
                print(f"  {i}) {c}")
            pick = input("Выбор (Enter = 1): ").strip()
            if pick.isdigit():
                idx = int(pick)
                if 1 <= idx <= len(options):
                    chosen = options[idx-1]
        payload = {
            "ticket_id": "SP-EXPO-0001",
            "problem_code": chosen,
            "problem_code": res["problem_code"],
            "device": { "type": "receipt_printer", "name": cfg.get("printer_name","POS_Receipt"), "conn": "USB" },
            "context": { "beautify": False, "purge": cfg.get("auto_purge","soft"), "raw_user": user }
        }
        ok, resp = run_playbook(cfg.get("daemon_url","http://127.0.0.1:8181"), payload)
        if not ok:
            print("[daemon] нет связи или ошибка:", resp)
            continue
        msgs = make_gui_messages(resp, is_admin=cfg.get("is_admin", False))
        print("[cashier]", msgs["cashier"])
        print("[tech]   ", msgs["tech"])

if __name__ == "__main__":
    main()
