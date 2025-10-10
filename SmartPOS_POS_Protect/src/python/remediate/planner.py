from shared.log import jlog
from planner.actions import execute_action, list_available_actions

def execute_plans(plans, cfg):
    """Выполнение планов с использованием нового планировщика действий."""
    out = []
    
    # Получаем настройки безопасности
    safety_guards = cfg.get("safety_guards", {})
    dangerous_actions = safety_guards.get("dangerous_actions_block", [])
    max_actions_per_hour = safety_guards.get("max_actions_per_hour", 5)
    
    # Проверяем рабочее время
    working_hours = safety_guards.get("working_hours", {"start": 8, "end": 22})
    import datetime
    current_hour = datetime.datetime.now().hour
    is_working_hours = working_hours["start"] <= current_hour < working_hours["end"]
    
    action_count = 0
    
    for p in plans:
        issue = p["issue"]
        plan_steps = p.get("plan", [])
        
        for step in plan_steps:
            action_name = step.get("action") or step.get("do")
            if not action_name:
                continue
                
            # Проверка безопасности
            if action_name in dangerous_actions and is_working_hours:
                jlog({"subsystem":"pos_protect","action":"safety_block","result":"blocked",
                      "labels":{"action":action_name,"reason":"dangerous_during_work_hours"}})
                continue
                
            if action_count >= max_actions_per_hour:
                jlog({"subsystem":"pos_protect","action":"rate_limit","result":"blocked",
                      "labels":{"reason":"max_actions_per_hour_exceeded"}})
                break
                
            # Подготовка аргументов
            args = step.get("args", {})
            args["timeout_sec"] = step.get("timeout_sec", 30)
            args["dry"] = cfg.get("dry_run", True)  # По умолчанию dry-run
            
            # Выполнение действия
            success = execute_action(action_name, args)
            action_count += 1
            
            if success:
                jlog({"subsystem":"pos_protect","action":"execute_action","result":"ok",
                      "labels":{"action":action_name,"issue":issue["issue_code"]}})
            else:
                jlog({"subsystem":"pos_protect","action":"execute_action","result":"error",
                      "labels":{"action":action_name,"issue":issue["issue_code"]}})
        
        out.append({"issue": issue["issue_code"], "executed": len(plan_steps)})
        jlog({"subsystem":"pos_protect","action":"execute_plan","result":"ok",
              "labels":{"issue":issue["issue_code"]}})
    
    return out
