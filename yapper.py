"""
The yapper - JARVIS talks to you by himself, at random times, like a chatty friend.

Every so often (random, so it feels human) he picks a topic:
  weather  ·  news  ·  market  ·  fun (fun fact / this day in history / random thought)

Token saving:
  - real facts are fetched by plain code (sources.py) = 0 tokens
  - the AI only gets a tiny summary and writes 1-3 spoken sentences (~300-500 tokens)
  - a daily limit, quiet hours, and no yapping when the Home Mini is busy

Rules live in SETTINGS (saved in SQLite, changeable from the dashboard).
"""

import random
import re
import threading
import time
from datetime import datetime, timedelta

import brain
import db
import sources

TOPICS = ["weather", "news", "market", "fun"]

DEFAULTS = {
    "enabled": True,
    "min_minutes": 5,    # testing values - make these 60 / 120 later
    "max_minutes": 10,
    "start_hour": 9,     # yaps only between 9am...
    "end_hour": 23,      # ...and 11pm
    "daily_limit": 60,   # never more than this many yaps a day (token safety net)
}

# Default Media Receiver (our MP3s) and the idle screen. Any other app = something else is playing.
OUR_APPS = {None, "CC1AD845", "E8C28D3C"}

STYLE = ("Call him Zheng Xiang. You're yapping to him out of the blue, like a chatty friend dropping by. "
         "He didn't ask, so open casually (\"Hey,\", \"Oh, by the way,\", \"Quick one,\"). "
         "1-3 short spoken sentences, English, no lists, no markdown. Local time: {now}.")


def settings() -> dict:
    return {k: db.get_setting(f"yapper.{k}", v) for k, v in DEFAULTS.items()}


def update_settings(changes: dict) -> dict:
    for k, v in changes.items():
        if k in DEFAULTS:
            db.set_setting(f"yapper.{k}", v)
    return settings()


# ---------- building one yap ----------
def _prompt_weather() -> tuple[str, str | None]:
    return f"Tell him the Penang weather in a casual way, with a tip if useful (umbrella, water). Data: {sources.weather()}", None


def _prompt_news() -> tuple[str, str | None]:
    fresh = [n for n in sources.news()[:15] if not db.already_said("news", n["title"])]
    if not fresh:
        return _prompt_fun()
    pick = random.choice(fresh[:6])
    return (f"Share this Malaysia headline casually, then add a short natural reaction (\"wow\", \"that's big\"). "
            f"STRICT: say ONLY what the headline says. Do NOT add any background, names, numbers, causes "
            f"or history that are not in the headline - you may be wrong. "
            f"Headline: \"{pick['title']}\" ({pick['source']})."), pick["title"]


def _prompt_market() -> tuple[str, str | None]:
    fresh = [n for n in sources.market() if not db.already_said("market", n["title"])]
    if not fresh:
        return _prompt_fun()
    pick = random.choice(fresh[:5])  # a little variety among the biggest moves
    where = "on Bursa Malaysia" if pick["region"] == "Malaysia" else "on the stock market"
    return (f"Tell him about this hot stock news {where}. He knows NOTHING about stocks, so explain simply: "
            f"what happened and, in plain words, what a move like that means (e.g. 'a 14% jump in a day is huge'). "
            f"Describe the company ONLY if it's a household name (Nvidia, Apple, Tesla, Google, Microsoft, Amazon, "
            f"Maybank, Petronas, Tenaga...); otherwise just say 'a company called X'. "
            f"STRICT: use ONLY the facts in the headline. Never add reasons, expectations, analysts, prices or dates "
            f"that aren't in it. It's from the last day, so don't say 'right now'. Never give investment advice, "
            f"and don't add disclaimers like 'no advice' or 'that's all the news says' - just end naturally. "
            f"Headline: \"{pick['title']}\" ({pick['source']})."), pick["title"]


FUN_KINDS = ["a surprising fun fact", "a 'this day in history' moment for today's date",
             "a tiny clever joke", "a random interesting thought or question to ponder",
             "a fun fact about Penang or Malaysia", "a fun fact about science or space"]


def _prompt_fun() -> tuple[str, str | None]:
    kind = random.choice(FUN_KINDS)
    avoid = db.recent_said("fun")
    extra = f" Don't repeat any of these: {avoid}." if avoid else ""
    return (f"Share {kind}. Only use a well-known, textbook-level fact you are completely sure of, with no "
            f"exact numbers unless you're certain; if unsure, pick a different one.{extra} "
            f"After your answer, add a NEW line: TAG: <3-6 word summary>"), "?"


def make_yap(topic: str) -> tuple[str, str]:
    """Returns (topic actually used, text to say)."""
    builders = {"weather": _prompt_weather, "news": _prompt_news, "market": _prompt_market, "fun": _prompt_fun}
    prompt, key = builders[topic]()
    if key == "?" and topic != "fun":  # news fell back to fun
        topic = "fun"
    now = datetime.now().strftime("%A %d %B, %I:%M %p")
    text = brain.think([{"role": "user", "content": STYLE.format(now=now) + " " + prompt}])

    if topic == "fun":  # pull out the "TAG: ..." part (wherever it is), remember it, don't speak it
        match = re.search(r"\bTAG:\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
        key = match.group(1).strip() if match else text[:60]
        text = text[: match.start()].strip() if match else text.strip()
    if key:
        db.remember_said(topic, key)
    return topic, text


# ---------- the clock ----------
class Yapper:
    def __init__(self, mouth, on_yap):
        self.mouth = mouth
        self.on_yap = on_yap          # called with the text, so the chat can show it
        self.next_at = None
        self.last_topic = None
        self.busy = threading.Lock()  # one yap at a time
        self._stop = threading.Event()

    def start(self):
        self._plan_next()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _plan_next(self):
        s = settings()
        lo, hi = sorted((s["min_minutes"], s["max_minutes"]))
        nxt = datetime.now() + timedelta(minutes=random.uniform(lo, hi))
        # outside awake hours -> move to the start of the next awake window (plus a little randomness)
        if not (s["start_hour"] <= nxt.hour < s["end_hour"]):
            day = nxt.date() if nxt.hour < s["start_hour"] else nxt.date() + timedelta(days=1)
            nxt = datetime.combine(day, datetime.min.time()).replace(hour=s["start_hour"]) + timedelta(minutes=random.uniform(0, 20))
        self.next_at = nxt

    def _speaker_busy(self) -> bool:
        sp = self.mouth.speaker
        try:
            return sp is not None and sp.app_id not in OUR_APPS and not sp.is_idle
        except Exception:
            return False

    def _loop(self):
        while not self._stop.wait(20):
            if self.next_at and datetime.now() >= self.next_at:
                s = settings()
                if not s["enabled"]:
                    pass
                elif db.yaps_today() >= s["daily_limit"]:
                    print("[yapper] daily limit reached, staying quiet")
                elif self._speaker_busy():
                    print("[yapper] Home Mini is playing something else, skipping")
                else:
                    self.yap_now()
                self._plan_next()

    def yap_now(self, topic: str | None = None) -> dict:
        """Yap right away. topic=None picks one at random (not the same as last time)."""
        if not self.busy.acquire(blocking=False):
            return {"skipped": "already yapping"}
        try:
            if topic not in TOPICS:
                topic = random.choice([t for t in TOPICS if t != self.last_topic])
            try:
                topic, text = make_yap(topic)
            except Exception as e:
                print(f"[yapper] couldn't make a {topic} yap: {e}")
                return {"error": str(e)}
            self.last_topic = topic
            db.log_yap(topic, text)
            print(f"[yapper] {topic}: {text}")
            self.on_yap(text)
            try:
                self.mouth.say(brain.for_speaking(text))
            except Exception as e:
                print(f"[yapper] couldn't speak: {e}")
            return {"topic": topic, "text": text}
        finally:
            self.busy.release()
