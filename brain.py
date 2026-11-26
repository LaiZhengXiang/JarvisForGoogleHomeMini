"""
The brain - asks an AI to think of an answer.

Same plan as UniLife Copilot:
  1. Groq (fast, free) - try model A, then model B (each model has its own free quota)
  2. Gemini - backup if Groq is busy
If everyone fails we raise BrainError, and the caller decides what to do.
"""

import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = [
    ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("qwen/qwen3.8-27b", {"reasoning_format": "hidden"}),
]
GEMINI_MODEL = "gemini-3.5-flash"
TIMEOUT = 30

PERSONA = """You are JARVIS, Zheng Xiang's personal assistant. He is a university student in Malaysia.
Your words are spoken out loud by a Google Home Mini, so:
- keep answers short: 1-3 sentences unless he asks for more
- plain spoken sentences only: no markdown, no bullet points, no emojis
- reply in the language he writes in (English, or Chinese if he writes Chinese)
- write the way people TALK, not the way they write: use contractions (it's, you'll, don't),
  mix short and longer sentences, and start naturally sometimes ("Alright,", "Well,", "Ooh,", "好啦，", "嗯，")
- use commas where a person would take a small breath; avoid long lists and formal words
Be warm, a little witty, and helpful.
Be honest about what you can do. Right now you can only chat and speak on the Home Mini.
You can NOT yet set reminders, read UniLife deadlines, check news or read PDFs.
If he asks for one of those, say clearly that you can't do it yet (it's coming soon),
so he doesn't rely on it. Never say "I'll remind you" or "I've set that"."""


class BrainError(Exception):
    pass


def _ask_groq(model: str, extra: dict, messages: list[dict]) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise BrainError("GROQ_API_KEY is not set")
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages, **extra},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _ask_gemini(messages: list[dict]) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise BrainError("GEMINI_API_KEY is not set")
    # Gemini wants: one "system instruction" + turns with role "user" / "model".
    system = " ".join(m["content"] for m in messages if m["role"] == "system")
    turns = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages if m["role"] != "system"
    ]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": key},
        json={"systemInstruction": {"parts": [{"text": system}]}, "contents": turns},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def think(messages: list[dict]) -> str:
    """messages = [{"role": "user"/"assistant", "content": "..."}, ...]
    Returns JARVIS's answer as plain text."""
    messages = [{"role": "system", "content": PERSONA}] + messages

    attempts = [(f"Groq {m}", lambda m=m, x=x: _ask_groq(m, x, messages)) for m, x in GROQ_MODELS]
    attempts.append(("Gemini", lambda: _ask_gemini(messages)))

    for name, ask in attempts:
        try:
            answer = ask().strip()
            if answer:
                print(f"[brain] answered by {name}")
                return answer
        except Exception as e:  # busy, quota, no internet, bad key...
            print(f"[brain] {name} failed: {str(e)[:120]}")
    raise BrainError("All AI providers failed. Check the internet and API keys.")


def for_speaking(text: str) -> str:
    """Remove symbols the voice would read out loud: markdown (* # ...) and
    quote marks in English and Chinese (" “ ” ‘ ’ 「 」 『 』)."""
    text = re.sub(r"[*_#`>|~\"“”‘’「」『』]", "", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    print(think([{"role": "user", "content": "Say hi to me in one short sentence."}]))
