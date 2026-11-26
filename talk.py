"""
Talk mode - type anything, the Home Mini says it.

It finds the speaker once, then keeps listening to your keyboard,
so every line after the first one is quick.

Run:  python talk.py
Stop: press Enter on an empty line, or type "quit".
"""

from say_hello import find_speaker, speak, start_web_server


def main() -> None:
    server = start_web_server()
    speaker, browser = find_speaker()
    speaker.wait()
    print('\nReady! Type a line and press Enter. Empty line or "quit" to stop.\n')

    try:
        while True:
            line = input("You > ").strip()
            if line.lower() in ("", "quit", "exit"):
                break
            if not speak(speaker, line):
                print("  The speaker didn't pick it up. Try again.")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        browser.stop_discovery()
        server.shutdown()
        print("Bye!")


if __name__ == "__main__":
    main()
