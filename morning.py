"""
Step 2 - Morning message.

Windows Task Scheduler runs this at 8am (see setup_timer.ps1).
There is no terminal window when it runs on a timer, so everything it
prints goes into logs/jarvis.log - open that file to see what happened.

Run it by hand to test:  python morning.py
"""

import sys
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "logs" / "jarvis.log"


def morning_message() -> str:
    now = datetime.now()
    day = now.strftime("%A, %d %B").replace(" 0", " ")  # "Thursday, 27 November"
    return f"Good morning Zheng Xiang. It's {day}, {now:%I:%M %p}. Time to start the day!"


if __name__ == "__main__":
    # Send all output (and errors) to the log file, so we can read it later.
    LOG_FILE.parent.mkdir(exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} morning.py ===")

    from say_hello import say  # imported after the redirect so its messages are logged too

    say(morning_message())
