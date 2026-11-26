"""
Step 3 - The JARVIS server (the always-awake brain).

Start it:   .venv\\Scripts\\python server.py
Then open:  http://127.0.0.1:8000        (the dashboard, step 4)
            http://127.0.0.1:8000/docs   (FastAPI's built-in test page)

Endpoints:
  GET  /api/status   is JARVIS alive? which speaker?
  POST /api/say      {"text": "..."}                       -> the Home Mini says it
  POST /api/chat     {"message": "...", "speak": true}     -> JARVIS thinks, answers,
                                                              and (optionally) says it
  GET  /api/history  the conversation so far (the dashboard loads it on start)
  POST /api/history/clear   start a new conversation
  GET  /api/weather         Penang weather (for the dashboard)
  GET  /api/yapper          yapper settings, next yap time, today's count
  POST /api/yapper/settings {"enabled": true, "min_minutes": 5, ...}
  POST /api/yapper/now      {"topic": "weather" | "news" | "market" | "fun" | null}
  GET  /api/reminders       all reminders
  POST /api/reminders       {"time": "11:45", "text": "...", "repeat": "once"|"daily", "date": null, "kind": "say"}
  POST /api/reminders/{id}/delete
"""

import json
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import brain
import db
import sources
import reminders
import yapper as yap
from mouth import Mouth, MouthError

mouth: Mouth | None = None
yapper: yap.Yapper | None = None
clock: reminders.ReminderClock | None = None
history: list[dict] = db.load_messages()  # the conversation so far (saved in SQLite)
HISTORY_LIMIT = 20        # only send the last 20 messages to the AI, to keep it fast


def remember(role: str, content: str):
    """Add a message to the chat history (on screen and in SQLite)."""
    history.append({"role": role, "content": content})
    db.add_message(role, content)


MORNING = ("Morning briefing: say good morning, today's day and date, and the Penang weather "
           "with a useful tip. Keep it upbeat.")


def seed_morning_reminder():
    """The old 8am morning.py task becomes a normal daily reminder (only created once)."""
    if not db.get_setting("seeded_morning", False):
        reminders.create("08:00", MORNING, repeat="daily", kind="think")
        db.set_setting("seeded_morning", True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mouth, yapper, clock
    mouth = Mouth()  # start the MP3 web server when JARVIS wakes up
    mouth.warm_up()  # and look for the Home Mini straight away
    # Yaps and reminders also go into the chat, so you can reply "tell me more".
    yapper = yap.Yapper(mouth, on_yap=lambda text: remember("assistant", text))
    yapper.start()
    seed_morning_reminder()
    clock = reminders.ReminderClock(mouth, on_fire=lambda text: remember("assistant", text))
    clock.start()
    print("[jarvis] awake")
    yield
    clock.stop()
    yapper.stop()
    mouth.close()
    print("[jarvis] asleep")


app = FastAPI(title="JARVIS", lifespan=lifespan)

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "index.html")


class SayRequest(BaseModel):
    text: str


class YapRequest(BaseModel):
    topic: str | None = None


class ReminderRequest(BaseModel):
    time: str
    text: str
    repeat: str = "once"
    date: str | None = None
    kind: str = "say"


class ChatRequest(BaseModel):
    message: str
    speak: bool = True


def speak_quietly(text: str):
    """Used in the background: a speaker problem shouldn't break the chat."""
    try:
        mouth.say(text)
    except MouthError as e:
        print(f"[jarvis] couldn't speak: {e}")


@app.get("/api/status")
def status():
    return {"awake": True, "speaker": mouth.speaker_name, "messages_in_history": len(history)}


@app.get("/api/history")
def get_history():
    return {"history": history}


@app.post("/api/history/clear")
def clear_history():
    history.clear()
    db.clear_messages()
    return {"cleared": True}


@app.get("/api/weather")
def weather():
    try:
        return sources.weather_data()
    except Exception as e:
        raise HTTPException(503, f"Weather unavailable: {e}")


@app.get("/api/yapper")
def yapper_status():
    return {
        "settings": yap.settings(),
        "next_at": yapper.next_at.isoformat(timespec="seconds") if yapper.next_at else None,
        "yaps_today": db.yaps_today(),
        "recent": db.recent_yaps(5),
    }


@app.post("/api/yapper/settings")
def yapper_settings(changes: dict):
    yap.update_settings(changes)
    yapper._plan_next()  # new timing rules -> pick a new next time
    return yapper_status()


@app.post("/api/yapper/now")
def yapper_now(req: YapRequest, background: BackgroundTasks):
    background.add_task(yapper.yap_now, req.topic)  # thinking + speaking takes a while
    return {"started": True}


@app.get("/api/reminders")
def list_reminders():
    return {"reminders": db.list_reminders()}


@app.post("/api/reminders")
def add_reminder(req: ReminderRequest):
    try:
        return reminders.create(req.time, req.text, req.repeat, req.date, req.kind)
    except reminders.ReminderError as e:
        raise HTTPException(400, str(e))


@app.post("/api/reminders/{rid}/delete")
def delete_reminder(rid: int):
    if not db.delete_reminder(rid):
        raise HTTPException(404, "No reminder with that number.")
    return {"deleted": rid}


ACTION_LINE = re.compile(r"^\s*(REMINDER_ADD|REMINDER_CANCEL):\s*(.+?)\s*$", re.MULTILINE)


def run_reminder_lines(answer: str) -> tuple[str, list[str]]:
    """Find the hidden REMINDER_ADD / REMINDER_CANCEL lines in the AI's answer, carry them out,
    and return (answer without those lines, list of problems)."""
    problems = []
    for action, data in ACTION_LINE.findall(answer):
        try:
            if action == "REMINDER_ADD":
                d = json.loads(data)
                r = reminders.create(d.get("time"), d.get("text"), d.get("repeat", "once"),
                                     d.get("date") or None, d.get("kind", "say"))
                print(f"[jarvis] reminder added by chat: {reminders.describe(r)}")
            else:
                rid = int(re.sub(r"\D", "", data))
                if not db.delete_reminder(rid):
                    problems.append(f"there's no reminder #{rid}")
        except (json.JSONDecodeError, ValueError, reminders.ReminderError) as e:
            problems.append(str(e))
    return ACTION_LINE.sub("", answer).strip(), problems


@app.post("/api/say")
def say(req: SayRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Nothing to say.")
    try:
        mouth.say(brain.for_speaking(text))  # waits until it's spoken, so you know it worked
    except MouthError as e:
        raise HTTPException(503, str(e))
    return {"said": text}


@app.post("/api/chat")
def chat(req: ChatRequest, background: BackgroundTasks):
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Say something first.")

    now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
    current = "; ".join(reminders.describe(r) for r in db.list_reminders()) or "none"
    rules = brain.REMINDER_RULES.format(now=now, reminders=current)
    try:
        answer = brain.think(history[-HISTORY_LIMIT:] + [{"role": "user", "content": message}], extra_system=rules)
    except brain.BrainError as e:
        raise HTTPException(503, str(e))

    answer, problems = run_reminder_lines(answer)
    if problems:  # be honest if a reminder didn't actually get saved
        answer += " Hmm, actually I couldn't save that reminder: " + "; ".join(problems) + "."
    remember("user", message)
    remember("assistant", answer)

    if req.speak:
        # Reply on screen straight away; the speaker talks in the background.
        background.add_task(speak_quietly, brain.for_speaking(answer))
    return {"reply": answer}


if __name__ == "__main__":
    # 127.0.0.1 = only this laptop can use JARVIS for now (not other people on the Wi-Fi).
    uvicorn.run(app, host="127.0.0.1", port=8000)
