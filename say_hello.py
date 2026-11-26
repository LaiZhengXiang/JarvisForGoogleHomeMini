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

import edge_tts
import pychromecast
from gtts import gTTS

SPEAKER_NAME = None  # e.g. "Bedroom speaker". None = use the first Google speaker found.
PORT = 0  # filled in when the web server starts
AUDIO_DIR = Path(__file__).parent / "audio"

# Voices. edge-tts uses Microsoft's natural "neural" voices (free, no key needed).
# Hear them all:  .venv\Scripts\edge-tts --list-voices
VOICES = {
    "en": "en-IE-ConnorNeural",    # Irish gentleman (picked by ear on the Home Mini)
    "zh": "zh-CN-YunyangNeural",   # steady Mandarin man, newsreader style
}
# Tuning per language: rate = speed, pitch = how deep. Lower + slower = calmer, more "gentleman".
VOICE_TUNING = {
    "en": {"rate": "+5%", "pitch": "-4Hz"},
    "zh": {"rate": "+2%", "pitch": "-6Hz"},
}

LEAD_IN_SECONDS = 1.0  # silence before the words, so the speaker is awake when they start


def pick_language(text: str) -> str:
    """Any Chinese character -> "zh", otherwise "en".
    (The Mandarin voice can still read English words mixed in.)"""
    if any("一" <= ch <= "鿿" for ch in text):
        return "zh"
    return "en"


def _tts(text: str, path: Path) -> None:
    """Text -> MP3. Natural edge-tts voice first; the plain Google voice as backup."""
    lang = pick_language(text)
    try:
        edge_tts.Communicate(text, VOICES[lang], **VOICE_TUNING[lang]).save_sync(str(path))
        if path.stat().st_size > 0:
            return
    except Exception as e:
        print(f"  edge-tts failed ({e}), using the Google voice instead")
    gTTS(text=text, lang="zh-CN" if lang == "zh" else "en").save(path)


def frame_info(header: bytes) -> tuple[int, float]:
    """Read an MP3 frame header -> (bytes per frame, seconds per frame).
    Both voices give MPEG-2 Layer III, but this also handles MPEG-1."""
    mpeg1 = (header[1] >> 3) & 1
    bitrate_i = header[2] >> 4
    rate_i = (header[2] >> 2) & 3
    if mpeg1:
        kbps = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320][bitrate_i]
        hz = [44100, 48000, 32000][rate_i]
        return 144 * kbps * 1000 // hz, 1152 / hz
    kbps = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160][bitrate_i]
    hz = [22050, 24000, 16000][rate_i]
    return 72 * kbps * 1000 // hz, 576 / hz


def mp3_seconds(mp3: Path) -> float:
    data = mp3.read_bytes()
    frame_bytes, frame_seconds = frame_info(data[:4])
    return len(data) / frame_bytes * frame_seconds


def make_mp3(text: str) -> Path:
    """Job 1: text -> MP3 file, with a little silence in front.

    The Home Mini's amplifier sleeps when idle and swallows the first moment of
    sound while it wakes up. Without the silence, short lines like "hi" vanish.
    """
    AUDIO_DIR.mkdir(exist_ok=True)
    for old in AUDIO_DIR.glob("*.mp3"):  # tidy up clips older than 1 hour
        if time.time() - old.stat().st_mtime > 3600:
            old.unlink(missing_ok=True)
    # A new name each time, so two scripts speaking at once don't overwrite each other.
    mp3 = AUDIO_DIR / f"msg-{time.time_ns()}.mp3"
    _tts(text, mp3)

    speech = mp3.read_bytes()
    header = speech[:4]  # copy the exact MP3 format the voice used
    frame_bytes, frame_seconds = frame_info(header)
    silent_frame = header + bytes(frame_bytes - 4)  # all zeros after the header = silence
    frames = int(LEAD_IN_SECONDS / frame_seconds)
    mp3.write_bytes(silent_frame * frames + speech)
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

    def log_request(self, code="-", size="-"):
        # Only count a real, successful download (code 200), not errors.
        if str(getattr(code, "value", code)) == "200":
            print(f"  speaker downloaded the MP3 (from {self.client_address[0]})")
            downloaded.set()
        else:
            print(f"  speaker asked for the MP3 but got error {code}")

    def log_message(self, fmt, *args):
        pass  # keep the screen quiet


def start_web_server() -> http.server.ThreadingHTTPServer:
    """Job 2: share the audio folder on the Wi-Fi so the Home Mini can download it."""
    # Port 0 = "Windows, give me any free port". A fixed port would clash when two
    # scripts run at once (talk.py + the 8am timer) - Windows lets both grab it.
    global PORT
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), AudioHandler)
    PORT = server.server_address[1]
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


def speak(speaker, text: str) -> bool:
    """Job 3b: make the speaker say one line. Returns False if it never downloaded the MP3.
    The web server must already be running."""
    mp3 = make_mp3(text)
    url = f"http://{laptop_ip()}:{PORT}/{mp3.name}?t={time.time()}"  # ?t= stops caching
    print(f'Speaking on "{speaker.cast_info.friendly_name}": {text}')

    # Sometimes the first request is lost while the speaker starts its player,
    # so we try up to 3 times until the speaker actually downloads the file.
    mc = speaker.media_controller
    downloaded.clear()
    for attempt in range(3):
        mc.play_media(url, "audio/mpeg")
        if downloaded.wait(timeout=8):
            break
        print("  no download yet, asking again...")
    else:
        return False

    # Wait while it talks (length worked out from the MP3 frames).
    seconds = mp3_seconds(mp3)
    time.sleep(seconds + 2)
    return True


def say(text: str) -> None:
    """Say one line, then tidy up."""
    server = start_web_server()
    speaker, browser = find_speaker()
    speaker.wait()
    try:
        ok = speak(speaker, text)
    finally:
        browser.stop_discovery()
        server.shutdown()
    if not ok:
        sys.exit("The speaker never downloaded the MP3. Check Windows Firewall lets Python in.")
    print("Done.")


if __name__ == "__main__":
    say(" ".join(sys.argv[1:]) or "Hello Zheng Xiang")
