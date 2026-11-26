# JARVIS

A personal assistant that talks through a Google Home Mini.
The laptop is the brain (Python); the Home Mini is just the mouth.

## Roadmap

- [x] **1. Mouth test** – Python makes the Home Mini say "Hello Zheng Xiang"
- [x] **2. Timer** – the script runs by itself at 8am
- [ ] **3. Brain** – Gemini writes the message (reminders, a joke, a fun news story)
- [ ] **4. Dashboard** – a web page (FastAPI) to type messages, set the schedule and see a log
- [ ] **5. Agent** – it checks UniLife deadlines before speaking

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

