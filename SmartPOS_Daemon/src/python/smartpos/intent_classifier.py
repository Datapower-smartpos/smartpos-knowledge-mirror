from __future__ import annotations
import json
import logging
import os
import re
from typing import Dict, List, Optional

LOG_PATH = os.environ.get("SMARTPOS_LOG", "smartpos_agent.log")
logging.basicConfig(level=logging.INFO, filename=LOG_PATH)

class IntentResult(dict):
    """Результат классификации намерения кассира."""

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

def _load_dataset(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: [_normalize(t) for t in v] for k, v in data.items()}

def _keyword_score(query: str, phrases: List[str], keywords: List[str]) -> float:
    """
    Улучшенная эвристика:
    - +1.5 за каждое ключевое слово
    - +3.0 за точное совпадение одной из эталонных фраз
    - +1.0 за частичное совпадение
    - +0.5 * общих токенов между запросом и эталонной фразой
    """
    q = _normalize(query)
    score = 0.0
    for kw in keywords:
        if kw in q:
            score += 1.5
    qtoks = set(q.split())
    for p in phrases:
        if p == q:
            score += 3.0
        elif p in q or q in p:
            score += 1.0
        ptoks = set(p.split())
        common = qtoks & ptoks
        if common:
            score += 0.5 * len(common)
    return score

def _code_keywords() -> Dict[str, List[str]]:
    return {
        "PR0022": ["пропал", "usb", "не видит", "устройство", "питание", "диспетчер"],
        "PR0018": ["очередь", "висит", "задание", "спулер", "не удаляется", "крутится"],
        "PR0001": ["бумага", "нет бумаги", "рулон", "paper out"],
        "PR0015": ["крышка", "cover open", "защёлк", "датчик крышки"],
        "PR0006": ["ширина", "80", "обрезает", "не влазит", "узко"],
        "PR0017": ["ширина", "режет", "сдвиг", "58", "cut off"]
    }


def _strong_signals_width(q: str) -> float:
    """
    Выделяем сильные маркеры «неверная ширина/обрезает»:
    - упоминания 80/58 мм
    - слова обрезает/режет/край/не влазит/ширина
    - 'cut off'
    Возвращает добавочный скор (0..4).
    """
    score = 0.0
    ql = q.lower()
    # 80/58 мм / mm
    if re.search(r'\b(80|58)\s*(мм|mm)\b', ql):
        score += 1.5
    # явные слова
    for kw in ["обрезает", "режет", "край", "ширина", "не влазит", "не влезает", "не помещается", "узкая печать", "cut off"]:
        if kw in ql:
            score += 0.6
    # упоминания сторон
    for kw in ["справа", "слева", "правый", "левый"]:
        if kw in ql:
            score += 0.3
    return min(score, 4.0)

class IntentClassifier:
    """
    Офлайн-классификатор для SmartPOS: keyword/fuzzy fallback.
    Если будет локальный FAISS-индекс, можно догрузить его отдельно.
    """

    def __init__(self, dataset_path: str, faiss_index_path: Optional[str] = None):
        self.dataset = _load_dataset(dataset_path)
        self.faiss_enabled = False
        self.faiss_index_path = faiss_index_path
        self.kwords = _code_keywords()
        try:
            if faiss_index_path and os.path.exists(faiss_index_path):
                import faiss  # опционально
                self.faiss = faiss
                self.faiss_enabled = True
                logging.info("FAISS index detected at %s", faiss_index_path)
        except Exception as e:
            logging.warning("FAISS disabled: %s", e)
            self.faiss_enabled = False

    def classify_intent(self, user_text: str) -> IntentResult:
        query = _normalize(user_text)
        scores = []
        for code, phrases in self.dataset.items():
            s = _keyword_score(query, phrases, self.kwords.get(code, []))
            # Сильные сигналы ширины для PR0006/PR0017
            if code in ("PR0006", "PR0017"):
                s += _strong_signals_width(query)
            scores.append((code, s, "kw"))

        # (Опционально) добавить FAISS-скоринг при наличии индекса
        if self.faiss_enabled:
            try:
                pass
            except Exception as e:
                logging.error("FAISS scoring error: %s", e)

        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[0]
        alt = [{"code": c, "score": round(s, 2)} for c, s, _ in scores[1:4]]
        max_s = top[1] if top[1] > 0 else 1.0
        conf = min(0.95, max(0.3, top[1] / (max_s + 2.0)))
        need_clar = conf < 0.75

        rationale_bits = []
        for kw in self.kwords.get(top[0], []):
            if kw in query:
                rationale_bits.append(kw)

        return IntentResult(
            problem_code=top[0],
            confidence=round(conf, 2),
            short_rationale=f"ключевые: {', '.join(rationale_bits[:3])}" if rationale_bits else "совпадение по фразам",
            needed_clarification=need_clar,
            alternatives=alt
        )
