"""
JARVIS's memory - one SQLite file (jarvis.db, never committed).

  settings  key -> value (e.g. yapper on/off, how often)
  said      things already told you (headlines, facts) so he doesn't repeat himself
  yaps      a log of every yap: when, which topic, what he said
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

DB_FILE = Path(__file__).parent / "jarvis.db"
_lock = threading.Lock()
_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript("""
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS said (topic TEXT, item TEXT, at TEXT, PRIMARY KEY (topic, item));
CREATE TABLE IF NOT EXISTS yaps (id INTEGER PRIMARY KEY, at TEXT, topic TEXT, text TEXT);
""")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_setting(key: str, default):
    with _lock:
        row = _conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with _lock, _conn:
        _conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))


def already_said(topic: str, item: str) -> bool:
    with _lock:
        return _conn.execute("SELECT 1 FROM said WHERE topic = ? AND item = ?", (topic, item)).fetchone() is not None


def remember_said(topic: str, item: str) -> None:
    with _lock, _conn:
        _conn.execute("INSERT OR REPLACE INTO said VALUES (?, ?, ?)", (topic, item, _now()))
        # forget things older than 14 days, so the table stays small
        _conn.execute("DELETE FROM said WHERE at < ?", ((datetime.now() - timedelta(days=14)).isoformat(),))


def recent_said(topic: str, limit: int = 8) -> list[str]:
    with _lock:
        rows = _conn.execute("SELECT item FROM said WHERE topic = ? ORDER BY at DESC LIMIT ?", (topic, limit)).fetchall()
    return [r["item"] for r in rows]


def log_yap(topic: str, text: str) -> None:
    with _lock, _conn:
        _conn.execute("INSERT INTO yaps (at, topic, text) VALUES (?, ?, ?)", (_now(), topic, text))


def yaps_today() -> int:
    today = datetime.now().date().isoformat()
    with _lock:
        return _conn.execute("SELECT COUNT(*) FROM yaps WHERE at >= ?", (today,)).fetchone()[0]


def recent_yaps(limit: int = 5) -> list[dict]:
    with _lock:
        rows = _conn.execute("SELECT at, topic, text FROM yaps ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
