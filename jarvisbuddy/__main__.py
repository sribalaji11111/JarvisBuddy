"""Run with:  python -m jarvisbuddy               (face + voice, say "Hey Jarvis ...")
              python -m jarvisbuddy --text        (type instead of talking)
              python -m jarvisbuddy --fullscreen  (face fills the screen)
              python -m jarvisbuddy --check       (see what's working)
              python -m jarvisbuddy --learn       (learn from today's chats)
              python -m jarvisbuddy --mcp-server  (offer the laptop tools to other MCP apps)"""

from __future__ import annotations

import argparse
import importlib.util
import os
import threading

from .assistant import Assistant
from .config import Config
from .voice import make_speaker


def _ollama_ready(config: Config) -> bool:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{config.ollama_url}/api/tags", timeout=1.5) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
        return any(n.split(":")[0] == config.ollama_model.split(":")[0] for n in names)
    except (OSError, ValueError):
        return False


def check(config: Config) -> None:
    """Print what's set up and what's missing."""
    def has(module: str) -> bool:
        return importlib.util.find_spec(module) is not None

    rows = [
        ("Windows voice (pywin32)", has("win32com"), "pip install pywin32"),
        ("Cute neural voice (edge-tts + pygame)", has("edge_tts") and has("pygame"),
         "pip install edge-tts pygame, then JARVIS_VOICE_ENGINE=neural"),
        ("Offline speech recognition (faster-whisper)", has("faster_whisper") and has("sounddevice"),
         "pip install faster-whisper sounddevice"),
        ("Online speech recognition (SpeechRecognition + PyAudio)", has("speech_recognition") and has("pyaudio"),
         "pip install SpeechRecognition PyAudio"),
        (f"Offline brain (Ollama running with {config.ollama_model})", _ollama_ready(config),
         "install Ollama from https://ollama.com, then run setup.bat"),
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
        ("Safe delete to Recycle Bin (send2trash)", has("send2trash"), "pip install send2trash"),
        ("MCP (server and extra servers)", has("mcp"), "pip install mcp"),
        (f"Extra MCP servers ({config.mcp_servers_file.name})", config.mcp_servers_file.is_file(),
         "optional: list servers there, same format as Claude Desktop"),
    ]
    for name, ok, fix in rows:
        print(f"  {'OK ' if ok else '-- '} {name}" + ("" if ok else f"   ->  {fix}"))
    print(f"\n  Memory and notes: {config.data_dir}")


def setup(config: Config) -> None:
    """Install every library and download every model Jarvis can use."""
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    print("1/4  Installing libraries...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(root / "requirements.txt")])

    print(f"2/4  Downloading the offline speech model ({config.whisper_model})...")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(config.whisper_model, device="cpu", compute_type="int8")
        print("     Speech model ready.")
    except Exception as e:
        print(f"     Couldn't get the speech model: {e}")

    print(f"3/4  Setting up the offline brain (Ollama + {config.ollama_model})...")
    ollama = shutil.which("ollama") or next(
        (str(p) for p in [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"] if p.is_file()), None)
    if ollama is None and shutil.which("winget"):
        print("     Installing Ollama with winget...")
        subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama",
                        "--accept-package-agreements", "--accept-source-agreements"])
        ollama = shutil.which("ollama") or next(
            (str(p) for p in [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"]
             if p.is_file()), None)
    if ollama:
        subprocess.run([ollama, "pull", config.ollama_model])
    else:
        print("     Ollama isn't installed. Get it from https://ollama.com/download, then run setup again.")

    print("4/4  Checking everything...")
    check(Config.from_env())
    print("\nAll set! Start Jarvis with run.bat.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvisbuddy", description="Your desktop robot buddy.")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("--mute", action="store_true", help="print replies without speaking them")
    parser.add_argument("--no-face", action="store_true", help="don't show the animated face window")
    parser.add_argument("--fullscreen", action="store_true", help="face fills the screen (Esc to exit)")
    parser.add_argument("--no-wake-word", action="store_true", help="treat everything heard as a command")
    parser.add_argument("--check", action="store_true", help="show which features are ready")
    parser.add_argument("--learn", action="store_true", help="learn from today's conversations, then exit")
    parser.add_argument("--mcp-server", action="store_true", help="run the laptop tools as an MCP server")
    parser.add_argument("--setup", action="store_true", help="install all libraries and download the models")
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.check:
        check(config)
        return
    if args.setup:
        setup(config)
        return
    if args.mcp_server:
        from .mcp_server import main as serve

        serve()
        return
    if args.learn:
        from . import learn
        from .local_brain import make_brain
        from .memory import Memory
        from .skills import MOODS

        memory = Memory(config.memory_file)
        brain = make_brain(config, memory, MOODS)
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

    hub = None
    if config.mcp_servers_file.is_file():
        try:
            from .mcp_hub import McpHub

            hub = McpHub(config.mcp_servers_file).start()
            print(f"(Connected {len(hub.tools)} tools from your MCP servers.)")
            for error in hub.errors:
                print(f"(MCP server problem: {error})")
        except Exception as e:
            print(f"(Couldn't start MCP servers: {e})")

    assistant = Assistant(config, speak=speaker.say, ui=face, mcp_hub=hub)
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
                from .voice import make_listener

                listener = make_listener(config.stt_engine, config.speech_language, config.whisper_model)
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
