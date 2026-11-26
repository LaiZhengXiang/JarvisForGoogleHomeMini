"""
JARVIS's memory - one SQLite file (jarvis.db, never committed).

  settings  key -> value (e.g. yapper on/off, how often)
  said      things already told you (headlines, facts) so he doesn't repeat himself
  yaps      a log of every yap: when, which topic, what he said
  reminders things to say at a time (once or daily)
  messages  the chat history, so it survives a restart
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
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    time TEXT NOT NULL,      -- "HH:MM"
    date TEXT,               -- "YYYY-MM-DD" for once; NULL for daily
    repeat TEXT NOT NULL,    -- "once" or "daily"
    kind TEXT NOT NULL,      -- "say" (exact words) or "think" (AI writes it)
    text TEXT NOT NULL,
    last_fired TEXT,         -- date it last went off (daily ones)
    created TEXT
);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, at TEXT);
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


# ---------- reminders ----------
def add_reminder(time: str, date: str | None, repeat: str, kind: str, text: str) -> dict:
    with _lock, _conn:
        cur = _conn.execute(
            "INSERT INTO reminders (time, date, repeat, kind, text, created) VALUES (?, ?, ?, ?, ?, ?)",
            (time, date, repeat, kind, text, _now()))
    return get_reminder(cur.lastrowid)


def get_reminder(rid: int) -> dict | None:
    with _lock:
        row = _conn.execute("SELECT * FROM reminders WHERE id = ?", (rid,)).fetchone()
    return dict(row) if row else None


def list_reminders() -> list[dict]:
    with _lock:
        rows = _conn.execute("SELECT * FROM reminders ORDER BY repeat DESC, date, time").fetchall()
    return [dict(r) for r in rows]


def delete_reminder(rid: int) -> bool:
    with _lock, _conn:
        return _conn.execute("DELETE FROM reminders WHERE id = ?", (rid,)).rowcount > 0


def mark_fired(rid: int, day: str) -> None:
    with _lock, _conn:
        _conn.execute("UPDATE reminders SET last_fired = ? WHERE id = ?", (day, rid))


# ---------- chat history ----------
def add_message(role: str, content: str) -> None:
    with _lock, _conn:
        _conn.execute("INSERT INTO messages (role, content, at) VALUES (?, ?, ?)", (role, content, _now()))


def load_messages(limit: int = 200) -> list[dict]:
    with _lock:
        rows = _conn.execute("SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_messages() -> None:
    with _lock, _conn:
        _conn.execute("DELETE FROM messages")

