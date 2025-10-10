def make_gui_messages(resp: dict, is_admin: bool) -> dict:
    """
    Возвращает 2 строки: cashier/tech + безопасные подсказки и fallback-и.
    """
    cashier = resp["human"]["cashier"]
    tech = resp["human"]["tech"]

    if resp.get("result_code") in ("ERROR","ACCESS_DENIED"):
        cashier = "Нужны права администратора. Запустите демо от имени администратора или нажмите «Мягкая очистка»."
        tech = f"{tech} | reason={resp.get('result_code')}"

    if resp.get("result_code") == "ACCESS_DENIED" and not is_admin:
        cashier += " Я переключил очистку на мягкий режим."
    return {"cashier": cashier, "tech": tech}
