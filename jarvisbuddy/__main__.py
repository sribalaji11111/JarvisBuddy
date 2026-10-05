"""Run with:  python -m jarvisbuddy        (voice, say "Hey Jarvis ...")
              python -m jarvisbuddy --text (type instead of talking)"""

from __future__ import annotations

import argparse

from .assistant import Assistant
from .config import Config
from .voice import Speaker


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvisbuddy", description="Your desktop voice assistant.")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("--mute", action="store_true", help="print replies without speaking them")
    parser.add_argument(
        "--no-wake-word", action="store_true", help="treat everything heard as a command"
    )
    args = parser.parse_args(argv)

    config = Config.from_env()
    speaker = Speaker(rate=config.voice_rate, enabled=not args.mute)
    assistant = Assistant(config, speak=lambda t: speaker.say(t, config.assistant_name))

    if not config.ai_enabled:
        print("(Tip: add ANTHROPIC_API_KEY to .env so Jarvis can answer any question.)")

    if args.text:
        assistant.run_text()
        return

    try:
        from .voice import Listener

        listener = Listener()
    except Exception as e:
        print(f"(Microphone unavailable: {e}. Switching to text mode.)")
        assistant.run_text()
        return

    try:
        assistant.run_voice(listener, always_listen=args.no_wake_word)
    except KeyboardInterrupt:
        speaker.say(f"Goodbye {config.user_name}.", config.assistant_name)


if __name__ == "__main__":
    main()
