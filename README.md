# JARVIS

A personal assistant that talks through a Google Home Mini.
The laptop is the brain (Python); the Home Mini is just the mouth.

## Roadmap

- [x] **1. Mouth test** – Python makes the Home Mini say "Hello Zheng Xiang"
- [ ] **2. Timer** – the script runs by itself at 8am
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

If Windows asks whether Python may use the network, allow it on **private** networks –
the Home Mini has to download the MP3 from your laptop.
