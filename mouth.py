"""
The mouth - a Home Mini connection that stays open.

say_hello.py finds the speaker, speaks once and closes. The JARVIS server
runs all day, so here we connect once and keep the speaker + web server ready.
If the speaker disappears (Wi-Fi blip, unplugged) we reconnect next time.
"""

import threading

import say_hello


class MouthError(Exception):
    pass


class Mouth:
    def __init__(self):
        self.server = say_hello.start_web_server()  # shares the MP3s on the Wi-Fi
        self.speaker = None
        self.browser = None
        self.lock = threading.Lock()  # one sentence at a time, never two at once

    def _connect(self):
        try:
            self.speaker, self.browser = say_hello.find_speaker()
        except SystemExit as e:  # find_speaker() exits when nothing is found
            raise MouthError(str(e))
        self.speaker.wait()

    def _disconnect(self):
        if self.browser:
            self.browser.stop_discovery()
        self.speaker = self.browser = None

    @property
    def speaker_name(self) -> str | None:
        return self.speaker.cast_info.friendly_name if self.speaker else None

    def say(self, text: str) -> None:
        """Speak one line. Waits until the speaker has finished."""
        with self.lock:
            for attempt in range(2):  # second go = reconnect and try again
                try:
                    if self.speaker is None:
                        self._connect()
                    if say_hello.speak(self.speaker, text):
                        return
                except MouthError:
                    raise
                except Exception as e:
                    print(f"[mouth] problem talking to the speaker: {e}")
                self._disconnect()
            raise MouthError("The speaker didn't play it. Is it on the same Wi-Fi?")

    def close(self):
        self._disconnect()
        self.server.shutdown()
