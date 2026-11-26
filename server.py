"""
Step 3 - The JARVIS server (the always-awake brain).

Start it:   .venv\\Scripts\\python server.py
Then open:  http://127.0.0.1:8000/docs   (FastAPI's built-in test page)

Endpoints:
  GET  /api/status   is JARVIS alive? which speaker?
  POST /api/say      {"text": "..."}                       -> the Home Mini says it
  POST /api/chat     {"message": "...", "speak": true}     -> JARVIS thinks, answers,
                                                              and (optionally) says it
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

import brain
from mouth import Mouth, MouthError

mouth: Mouth | None = None
history: list[dict] = []  # the conversation so far (kept in memory until step 5 adds SQLite)
HISTORY_LIMIT = 20        # only send the last 20 messages to the AI, to keep it fast


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mouth
    mouth = Mouth()  # start the MP3 web server when JARVIS wakes up
    print("[jarvis] awake")
    yield
    mouth.close()
    print("[jarvis] asleep")


app = FastAPI(title="JARVIS", lifespan=lifespan)


class SayRequest(BaseModel):
    text: str


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


@app.post("/api/say")
def say(req: SayRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Nothing to say.")
    try:
        mouth.say(text)  # waits until it's spoken, so you know it worked
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
