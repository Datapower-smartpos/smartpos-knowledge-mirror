import json, pathlib, sys

# Добавляем родительскую директорию в Python path для импорта модулей
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from shared.pipeline import load_cfg, pipeline_tick

if __name__ == "__main__":
    cfg = load_cfg()
    result = pipeline_tick(cfg, verbose=True)
    
    print("Results:", file=sys.stderr)
    print(json.dumps(result["issues"], ensure_ascii=False, indent=2))
