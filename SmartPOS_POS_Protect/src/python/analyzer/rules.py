# Импорт build_plans из нового модуля rules.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from rules import build_plans
