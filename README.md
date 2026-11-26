# JARVIS

A personal assistant that talks through a Google Home Mini.
The laptop is the brain (Python); the Home Mini is just the mouth.

## Roadmap

- [x] **1. Mouth test** – Python makes the Home Mini say "Hello Alex"
- [x] **2. Timer** – the script runs by itself at 8am
- [x] **3. Brain server** – JARVIS runs nonstop (FastAPI); chat with AI (Groq first, Gemini backup)
- [x] **4. Dashboard** – a JARVIS-style HUD: animated core, chat, clock, Penang weather, yapper and "say this"
- [x] **5a. Yapper** – JARVIS drops by at random times with Penang weather, Malaysia news, hot stock news and fun facts
- [x] **5b. Reminders** – any time (8:00, 11:45, ...), once or daily, set from the dashboard or by chat
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

## Auto-start (replaces the old 8am timer)

`setup_autostart.ps1` creates a Windows task, **JARVIS server**, that starts JARVIS hidden every time you log in
(and restarts him if he crashes). Output goes to `logs/server.log`. The 8am greeting is now a daily reminder.

```powershell
powershell -ExecutionPolicy Bypass -File setup_autostart.ps1   # set it up (once)
Start-ScheduledTask -TaskName "JARVIS server"                   # start now
Stop-ScheduledTask  -TaskName "JARVIS server"                   # stop
```

The laptop must be on and awake for JARVIS to speak (he doesn't wake it from sleep).

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

**Radio effect:** `radio.py` gives the voice a light earpiece / comms-channel sound (band-pass filter, a little drive and hiss).
Turn it off with `RADIO_EFFECT = False` in `say_hello.py`, or change the strength in `radio.SETTINGS`.

## Step 5a: the yapper

JARVIS talks to you by himself at random times, like a chatty friend. Turn him on/off, see the next yap,
or press **Yap now** in the dashboard's Yapper card. Yaps also show up in the chat, so you can reply.

| Topic | Facts from (free, no key, 0 AI tokens) |
|---|---|
| Weather | Open-Meteo forecast for Penang |
| Malaysia news | Google News Malaysia RSS (headlines only) |
| Market | Google News: big stock moves in the last day (global + Bursa), explained for a beginner |
| Fun | the AI (true, textbook-level facts only) |

**Token saving:** code fetches the facts and caches them (weather 30 min, news 1 hour); the AI only gets a
tiny summary and writes 1-3 sentences (~300-500 tokens a yap). Plus a daily limit, quiet hours (9am-11pm),
and no yapping while the Home Mini plays something else. Already-told headlines and facts are remembered
in `jarvis.db` (SQLite, never committed) so he doesn't repeat himself.

Settings (in `yapper.DEFAULTS`, changeable via `POST /api/yapper/settings`): every 5-10 min while testing -
set `min_minutes`/`max_minutes` to 60/120 for normal use.

## Step 5b: reminders

Say it in chat ("remind me in 10 minutes to stretch", "every day at 12:30 remind me to eat lunch",
"what reminders do I have?", "cancel the lunch one") or use the Reminders panel on the HUD.
Saved in SQLite, so they survive restarts. The chat history is saved there too.

- **once** reminders go off one time, then disappear; **daily** ones repeat
- **say** = your words ("Hey Alex, reminder: ..."); **think** = JARVIS writes it, with the date and Penang weather
  (the 8am morning briefing is one of these)
- if the laptop was asleep, a reminder up to 2 hours late still goes off; older ones are skipped

How chat reminders work: the AI adds a hidden line like `REMINDER_ADD: {"time": "11:45", ...}` to its reply;
the server checks it, saves the reminder and removes the line before you see or hear the reply.
If saving fails, JARVIS says so instead of pretending.

