# JARVIS

A personal assistant that talks through a Google Home Mini.
The laptop is the brain (Python); the Home Mini is just the mouth.

## Roadmap

- [x] **1. Mouth test** – Python makes the Home Mini say "Hello Zheng Xiang"
- [x] **2. Timer** – the script runs by itself at 8am
- [x] **3. Brain server** – JARVIS runs nonstop (FastAPI); chat with AI (Groq first, Gemini backup)
- [x] **4. Dashboard** – a chat page and a "say this" box, like UniLife Copilot
- [ ] **5. Reminders** – any time (8:00, 11:45, ...), once or daily, set from the dashboard or by chat
- [ ] **6. Agent** – UniLife deadlines, news, PDFs, songs

## Run step 1

Laptop and Home Mini must be on the same Wi-Fi.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python say_hello.py
python say_hello.py "Any sentence you like"
```

### Talk mode: type anything, the Home Mini says it

```powershell
python talk.py
```

Press Enter on an empty line (or type `quit`) to stop.
Lines with Chinese characters (e.g. `吃饱了吗`) are spoken in Mandarin automatically.

If Windows asks whether Python may use the network, allow it on **private** networks –
the Home Mini has to download the MP3 from your laptop.

## Step 2: the 8am timer

`setup_timer.ps1` creates a Windows Task Scheduler task, **JARVIS morning**, that runs `morning.py` every day at 8am.

```powershell
powershell -ExecutionPolicy Bypass -File setup_timer.ps1               # every day at 8am
powershell -ExecutionPolicy Bypass -File setup_timer.ps1 -Time 7:30am  # change the time
Start-ScheduledTask -TaskName "JARVIS morning"                         # test it right now
Unregister-ScheduledTask -TaskName "JARVIS morning" -Confirm:$false    # remove it
```

There's no window when it runs on the timer, so check `logs/jarvis.log` to see what happened.
The laptop must be on, or asleep **and plugged in** (Windows only wakes it for tasks on mains power).

## Step 3: the JARVIS server

Needs a `.env` file (never committed) with `GROQ_API_KEY=...` and, for the backup, `GEMINI_API_KEY=...`.

```powershell
.venv\Scripts\python server.py
```

Open **http://127.0.0.1:8000** for the dashboard (chat, "Say this", speaker status),
or http://127.0.0.1:8000/docs to try the API directly:

| Endpoint | What it does |
|---|---|
| `GET /api/status` | Is JARVIS awake? Which speaker? |
| `POST /api/say` `{"text": "..."}` | The Home Mini says the text |
| `POST /api/chat` `{"message": "...", "speak": true}` | JARVIS answers (and says it out loud) |
| `GET /api/history` | The conversation so far |
| `POST /api/history/clear` | Start a new conversation |

Files: `brain.py` (AI), `mouth.py` (speaker connection that stays open), `server.py` (FastAPI), `static/` (the dashboard).

Long replies are spoken sentence by sentence: the first sentence starts in about a second,
while the rest is prepared in the background.

### Voices

JARVIS speaks with Microsoft's natural neural voices through `edge-tts` (free, no key), and falls back to the plain Google voice if that fails.
Change them in `VOICES` / `VOICE_TUNING` at the top of `say_hello.py`.

| Language | Voice | Tuning |
|---|---|---|
| English | `en-US-AndrewMultilingualNeural` (warm conversation voice) | none |
| Chinese | `zh-CN-YunjianNeural` (energetic Mandarin man) | none |

