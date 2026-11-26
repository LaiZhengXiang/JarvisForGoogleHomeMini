"""
Step 1 - Mouth test.

Makes the Google Home Mini say a sentence.

How it works (3 small jobs):
  1. gTTS turns the text into an MP3 file (Google's voice).
  2. A tiny web server on this laptop shares that MP3 on the Wi-Fi.
  3. pychromecast finds the Home Mini and tells it:
     "play the MP3 at this address".

Run:  python say_hello.py
      python say_hello.py "Any sentence you like"
"""

import http.server
import socket
import sys
import threading
import time
from pathlib import Path

import pychromecast
from gtts import gTTS

SPEAKER_NAME = None  # e.g. "Bedroom speaker". None = use the first Google speaker found.
PORT = 8765
AUDIO_DIR = Path(__file__).parent / "audio"


def make_mp3(text: str) -> Path:
    """Job 1: text -> MP3 file."""
    AUDIO_DIR.mkdir(exist_ok=True)
    mp3 = AUDIO_DIR / "message.mp3"
    gTTS(text=text, lang="en").save(mp3)
    return mp3


def laptop_ip() -> str:
    """Find this laptop's address on the Wi-Fi (e.g. 192.168.1.23)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # no data is sent; this just picks the Wi-Fi card
        return s.getsockname()[0]


downloaded = threading.Event()  # becomes "set" when the Home Mini fetches the MP3


class AudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(AUDIO_DIR), **kwargs)

    def log_message(self, fmt, *args):
        print(f"  speaker downloaded the MP3 (from {self.client_address[0]})")
        downloaded.set()


def start_web_server() -> http.server.ThreadingHTTPServer:
    """Job 2: share the audio folder on the Wi-Fi so the Home Mini can download it."""
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), AudioHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def find_speaker():
    """Job 3a: look for Google speakers on the Wi-Fi."""
    print("Looking for Google speakers on the Wi-Fi...")
    casts, browser = pychromecast.get_chromecasts(timeout=10)
    if not casts:
        browser.stop_discovery()
        sys.exit("No speaker found. Is the laptop on the same Wi-Fi as the Home Mini?")

    for c in casts:
        print(f"  found: {c.cast_info.friendly_name}  ({c.cast_info.model_name})")

    if SPEAKER_NAME:
        casts = [c for c in casts if c.cast_info.friendly_name == SPEAKER_NAME]
        if not casts:
            browser.stop_discovery()
            sys.exit(f'No speaker called "{SPEAKER_NAME}". Use one of the names above.')

    return casts[0], browser


def say(text: str) -> None:
    mp3 = make_mp3(text)
    server = start_web_server()
    url = f"http://{laptop_ip()}:{PORT}/{mp3.name}?t={int(time.time())}"  # ?t= stops caching

    speaker, browser = find_speaker()
    speaker.wait()
    print(f'Speaking on "{speaker.cast_info.friendly_name}": {text}')

    # Job 3b: tell the Home Mini to play our MP3.
    # Sometimes the first request is lost while the speaker starts its player,
    # so we try up to 3 times until the speaker actually downloads the file.
    mc = speaker.media_controller
    for attempt in range(3):
        mc.play_media(url, "audio/mpeg")
        if downloaded.wait(timeout=8):
            break
        print("  no download yet, asking again...")
    else:
        browser.stop_discovery()
        server.shutdown()
        sys.exit("The speaker never downloaded the MP3. Check Windows Firewall lets Python in.")

    # Wait while it talks. gTTS MP3s are about 4 KB per second of speech.
    seconds = mp3.stat().st_size / 4000
    time.sleep(seconds + 2)

    browser.stop_discovery()
    server.shutdown()
    print("Done.")


if __name__ == "__main__":
    say(" ".join(sys.argv[1:]) or "Hello Zheng Xiang")
