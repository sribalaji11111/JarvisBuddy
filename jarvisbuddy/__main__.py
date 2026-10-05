"""Run with:  python -m jarvisbuddy          (face + voice, say "Hey Jarvis ...")
              python -m jarvisbuddy --text   (type instead of talking)
              python -m jarvisbuddy --no-face"""

from __future__ import annotations

import argparse
import os
import threading

from .assistant import Assistant
from .config import Config
from .voice import Speaker


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvisbuddy", description="Your desktop robot buddy.")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("--mute", action="store_true", help="print replies without speaking them")
    parser.add_argument("--no-face", action="store_true", help="don't show the animated face window")
    parser.add_argument("--no-wake-word", action="store_true", help="treat everything heard as a command")
    args = parser.parse_args(argv)

    config = Config.from_env()
    speaker = Speaker(config.voice_style, config.voice_name, config.voice_rate, enabled=not args.mute)

    face = None
    if not args.no_face:
        try:
            from .face import Face

            face = Face(title=config.assistant_name, on_close=lambda: os._exit(0))
        except Exception as e:  # no display, tkinter missing...
            print(f"(Face window unavailable: {e}.)")

    assistant = Assistant(config, speak=speaker.say, ui=face)
    if face is not None:
        face.canvas.bind("<Button-1>", lambda e: threading.Thread(target=assistant.poke, daemon=True).start())

    if not config.ai_enabled:
        print("(Tip: add ANTHROPIC_API_KEY to .env so Jarvis can chat about anything.)")

    def run() -> None:
        try:
            if args.text:
                assistant.run_text()
                return
            try:
                from .voice import Listener

                listener = Listener(config.speech_language)
            except Exception as e:
                print(f"(Microphone unavailable: {e}. Switching to text mode.)")
                assistant.run_text()
                return
            assistant.run_voice(listener, always_listen=args.no_wake_word)
        except KeyboardInterrupt:
            assistant.say(f"Bye bye {config.user_name}!", "sleepy")
        finally:
            if face is not None:
                face.close()

    if face is None:
        run()
        return
    # tkinter must own the main thread; the assistant talks and listens in the background.
    threading.Thread(target=run, daemon=True).start()
    try:
        face.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
