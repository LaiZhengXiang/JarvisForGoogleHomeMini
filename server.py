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
  GET  /api/yapper          yapper settings, next yap time, today's count
  POST /api/yapper/settings {"enabled": true, "min_minutes": 5, ...}
  POST /api/yapper/now      {"topic": "weather" | "news" | "market" | "fun" | null}
"""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import brain
import db
import yapper as yap
from mouth import Mouth, MouthError

mouth: Mouth | None = None
yapper: yap.Yapper | None = None
history: list[dict] = []  # the conversation so far (kept in memory until step 5 adds SQLite)
HISTORY_LIMIT = 20        # only send the last 20 messages to the AI, to keep it fast


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mouth, yapper
    mouth = Mouth()  # start the MP3 web server when JARVIS wakes up
    mouth.warm_up()  # and look for the Home Mini straight away
    # Yaps also go into the chat, so you can reply "tell me more".
    yapper = yap.Yapper(mouth, on_yap=lambda text: history.append({"role": "assistant", "content": text}))
    yapper.start()
    print("[jarvis] awake")
    yield
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
    return {"cleared": True}


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

    history.append({"role": "user", "content": message})
    try:
        answer = brain.think(history[-HISTORY_LIMIT:])
    except brain.BrainError as e:
        history.pop()  # forget the question we couldn't answer
        raise HTTPException(503, str(e))
    history.append({"role": "assistant", "content": answer})

    if req.speak:
        # Reply on screen straight away; the speaker talks in the background.
        background.add_task(speak_quietly, brain.for_speaking(answer))
    return {"reply": answer}


if __name__ == "__main__":
    # 127.0.0.1 = only this laptop can use JARVIS for now (not other people on the Wi-Fi).
    uvicorn.run(app, host="127.0.0.1", port=8000)
