"""Run with:  python -m jarvisbuddy               (face + voice, say "Hey Jarvis ...")
              python -m jarvisbuddy --text        (type instead of talking)
              python -m jarvisbuddy --fullscreen  (face fills the screen)
              python -m jarvisbuddy --check       (see what's working)
              python -m jarvisbuddy --learn       (learn from today's chats)"""

from __future__ import annotations

import argparse
import importlib.util
import os
import threading

from .assistant import Assistant
from .config import Config
from .voice import make_speaker


def check(config: Config) -> None:
    """Print what's set up and what's missing."""
    def has(module: str) -> bool:
        return importlib.util.find_spec(module) is not None

    rows = [
        ("Windows voice (pywin32)", has("win32com"), "pip install pywin32"),
        ("Cute neural voice (edge-tts + pygame)", has("edge_tts") and has("pygame"),
         "pip install edge-tts pygame, then JARVIS_VOICE_ENGINE=neural"),
        ("Microphone (SpeechRecognition + PyAudio)", has("speech_recognition") and has("pyaudio"),
         "pip install SpeechRecognition PyAudio"),
        ("Face window (tkinter)", has("tkinter"), "reinstall Python with Tcl/Tk"),
        ("Claude answers (ANTHROPIC_API_KEY)", config.ai_enabled, "add your key to .env"),
        ("Email sending (Gmail app password)", config.email_enabled,
         "add JARVIS_EMAIL_ADDRESS and JARVIS_EMAIL_APP_PASSWORD to .env (without them, drafts open in your mail app)"),
        ("Song search (yt-dlp)", has("yt_dlp"), "pip install yt-dlp"),
        ("Exact volume (pycaw)", has("pycaw"), "pip install pycaw comtypes"),
        ("Brightness", has("screen_brightness_control"), "pip install screen-brightness-control"),
        ("Screenshots (pillow)", has("PIL"), "pip install pillow"),
        ("Typing (pyautogui)", has("pyautogui"), "pip install pyautogui"),
        ("Battery and system (psutil)", has("psutil"), "pip install psutil"),
    ]
    for name, ok, fix in rows:
        print(f"  {'OK ' if ok else '-- '} {name}" + ("" if ok else f"   ->  {fix}"))
    print(f"\n  Memory and notes: {config.data_dir}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvisbuddy", description="Your desktop robot buddy.")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("--mute", action="store_true", help="print replies without speaking them")
    parser.add_argument("--no-face", action="store_true", help="don't show the animated face window")
    parser.add_argument("--fullscreen", action="store_true", help="face fills the screen (Esc to exit)")
    parser.add_argument("--no-wake-word", action="store_true", help="treat everything heard as a command")
    parser.add_argument("--check", action="store_true", help="show which features are ready")
    parser.add_argument("--learn", action="store_true", help="learn from today's conversations, then exit")
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.check:
        check(config)
        return
    if args.learn:
        from . import learn
        from .brain import Brain
        from .memory import Memory
        from .skills import MOODS

        memory = Memory(config.memory_file)
        brain = Brain(config, memory, moods=MOODS)
        print(learn.daily(memory, brain, memory.name or config.user_name, config.assistant_name))
        return

    speaker = make_speaker(config.voice_engine, config.voice_style, config.voice_name,
                           config.voice_rate, enabled=not args.mute)

    face = None
    if not args.no_face:
        try:
            from .face import Face

            face = Face(title=config.assistant_name, on_close=lambda: os._exit(0), fullscreen=args.fullscreen)
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
