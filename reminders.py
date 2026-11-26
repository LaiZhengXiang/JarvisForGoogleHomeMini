"""
Reminders - JARVIS speaks at a time you choose.

  once   "11:45 tomorrow: submit lab"     -> goes off one time, then is deleted
  daily  "12:00 every day: lunch time"    -> goes off every day

  kind "say"   -> says your words: "Hey Alex, reminder: submit lab"
  kind "think" -> the AI writes it, with today's date and Penang weather
                  (e.g. "morning briefing: greet me and tell me the weather")

A clock thread checks every 15 seconds. If the laptop was asleep and a reminder
is less than 2 hours late, it still goes off ("a bit late, but..."). Older ones are skipped.
"""

import re
import threading
from datetime import datetime, timedelta

import brain
import db
import sources

LATE_LIMIT = timedelta(hours=2)
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ReminderError(ValueError):
    pass


def create(time: str, text: str, repeat: str = "once", date: str | None = None, kind: str = "say") -> dict:
    """Check the details, fill in the date for 'once', and save."""
    time = (time or "").strip()
    if len(time) == 4 and time[1] == ":":
        time = "0" + time  # "9:30" -> "09:30"
    if not TIME_RE.match(time):
        raise ReminderError(f"'{time}' isn't a time like 14:30.")
    text = (text or "").strip()
    if not text:
        raise ReminderError("What should I remind you about?")
    if repeat not in ("once", "daily"):
        raise ReminderError("Repeat must be 'once' or 'daily'.")
    if kind not in ("say", "think"):
        raise ReminderError("Kind must be 'say' or 'think'.")

    if repeat == "daily":
        date = None
    else:
        now = datetime.now()
        if not date:  # no date: today if that time is still ahead, otherwise tomorrow
            today_at = datetime.combine(now.date(), datetime.strptime(time, "%H:%M").time())
            date = (now.date() if today_at > now else now.date() + timedelta(days=1)).isoformat()
        try:
            when = datetime.fromisoformat(f"{date}T{time}")
        except ValueError:
            raise ReminderError(f"'{date}' isn't a date like 2026-11-28.")
        if when < now - timedelta(minutes=1):
            raise ReminderError("That time has already passed.")
    return db.add_reminder(time, date, repeat, kind, text)


def describe(r: dict) -> str:
    when = f"every day at {r['time']}" if r["repeat"] == "daily" else f"{r['date']} at {r['time']}"
    return f"#{r['id']} {when}: {r['text']}" + (" (JARVIS writes it)" if r["kind"] == "think" else "")


def _scheduled_for(r: dict, now: datetime) -> datetime:
    day = now.date().isoformat() if r["repeat"] == "daily" else r["date"]
    return datetime.fromisoformat(f"{day}T{r['time']}")


def _message(r: dict, late: bool) -> str:
    if r["kind"] == "say":
        lead = "Hey Alex, a bit late, but here's your reminder: " if late else "Hey Alex, reminder: "
        return lead + r["text"]
    try:
        weather = sources.weather()
    except Exception:
        weather = "weather unavailable"
    now = datetime.now().strftime("%A %d %B %Y, %I:%M %p")
    prompt = (f"It's time for a scheduled message Alex set up. His instruction: \"{r['text']}\". "
              f"Context you may use: local time {now}; {weather}. "
              f"Speak to him directly, 1-3 short spoken sentences, no lists.")
    return brain.think([{"role": "user", "content": prompt}])


class ReminderClock:
    def __init__(self, mouth, on_fire):
        self.mouth = mouth
        self.on_fire = on_fire  # called with the text, so the chat shows it
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(15):
            try:
                self.check()
            except Exception as e:
                print(f"[reminders] check failed: {e}")

    def check(self):
        now = datetime.now()
        today = now.date().isoformat()
        for r in db.list_reminders():
            if r["repeat"] == "daily" and r["last_fired"] == today:
                continue
            when = _scheduled_for(r, now)
            if now < when:
                continue
            late_by = now - when
            if r["repeat"] == "once":
                db.delete_reminder(r["id"])  # once = gone after it fires (or is skipped)
            else:
                db.mark_fired(r["id"], today)
            if late_by > LATE_LIMIT:
                print(f"[reminders] skipped (too late): {describe(r)}")
                continue
            self.fire(r, late=late_by > timedelta(minutes=2))

    def fire(self, r: dict, late: bool = False):
        print(f"[reminders] firing {describe(r)}")
        try:
            text = _message(r, late)
        except Exception as e:  # AI down -> still remind, with the plain words
            print(f"[reminders] AI failed ({e}), saying it plainly")
            text = "Hey Alex, reminder: " + r["text"]
        self.on_fire(text)
        try:
            self.mouth.say(brain.for_speaking(text))
        except Exception as e:
            print(f"[reminders] couldn't speak: {e}")
