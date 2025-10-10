import json, time, pathlib
from shared.log import jlog, get_service_logger
from shared.pipeline import load_cfg, pipeline_tick, get_metrics
from remediate.planner import execute_plans

# Инициализация ротирующего логгера для сервиса
service_logger = get_service_logger()

def tick(cfg):
    """Выполнение одного тика сервиса с логированием."""
    try:
        # Унифицированный pipeline
        result = pipeline_tick(cfg, verbose=False)
        
        # Логирование ошибок коллекторов
        if result.get("errors"):
            for error in result["errors"]:
                jlog({"subsystem":"pos_protect","action":"collector_error","result":"error",
                      "labels":{"component":error["component"],"error":error["error"][:200]}})
        
        # Логирование результатов сбора
        jlog({"subsystem":"pos_protect","action":"evt_collected","result":"success",
              "labels":{"count":result["eventlog_count"]}})
        
        if result["wer_count"] > 0:
            jlog({"subsystem":"pos_protect","action":"wer_collected","result":"success",
                  "labels":{"count":result["wer_count"]}})
        
        # Выполнение планов
        plans_result = execute_plans(result["plans"], cfg)
        
        # Логирование итогового результата
        jlog({"subsystem":"pos_protect","action":"tick","result":"ok",
              "labels":{"issues":len(result["issues"]),"plans":len(result["plans"])}})
        
        # Дополнительное логирование в файл с метриками
        service_logger.info({
            "action": "tick_completed",
            "result": "success",
            "metrics": result.get("metrics", {}),
            "issues_count": len(result["issues"]),
            "plans_count": len(result["plans"]),
            "eventlog_count": result["eventlog_count"],
            "wer_count": result["wer_count"]
        })
        
        return plans_result
        
    except Exception as e:
        jlog({"subsystem":"pos_protect","action":"tick","result":"error","labels":{"err":str(e)}})
        service_logger.error({
            "action": "tick_failed",
            "result": "error",
            "error": str(e),
            "metrics": get_metrics()
        })
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
