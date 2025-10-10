# -*- coding: utf-8 -*-
"""
Unit-тест: sqlite retention/rotation
Проверяет удаление старых записей по порогу времени.
Строго stdlib. Подходит для слабых POS.
"""
from __future__ import annotations
import sqlite3
import time
import json

RETENTION_DAYS = 7


def _create_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts INTEGER, payload TEXT)")
    now = int(time.time())
    # старые записи
    for i in range(3):
        cur.execute(
            "INSERT INTO events(ts, payload) VALUES(?, ?)",
            (now - RETENTION_DAYS * 86400 - 100 * (i + 1), json.dumps({"i": i})),
        )
    # свежие записи
    for i in range(3):
        cur.execute(
            "INSERT INTO events(ts, payload) VALUES(?, ?)",
            (now - 100 * (i + 1), json.dumps({"n": i})),
        )
    conn.commit()


def _retention_rotate(conn: sqlite3.Connection, days: int) -> int:
    cutoff = int(time.time()) - days * 86400
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM events")
    return int(cur.fetchone()[0])


def test_retention_rotation(tmp_path):
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    try:
        _create_db(conn)
        remaining = _retention_rotate(conn, RETENTION_DAYS)
        assert remaining == 3
    finally:
        conn.close()
