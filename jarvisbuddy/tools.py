"""Laptop tools that Claude can call to control your computer.

The same tools are used in two places:
  * Jarvis's own brain (brain.py) calls them when you ask for something the quick built-in
    commands don't cover, like "close Chrome and open my Downloads folder".
  * The MCP server (mcp_server.py) offers them to any MCP app, such as Claude Desktop.

Tools marked `risky` change something that's hard to undo (email, deleting or moving files,
shutting down, running commands, closing apps). Jarvis always asks you out loud before
running one, and only goes ahead on a clear yes.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

from .actions import Actions
from .config import Config
from .mailer import Mailer, subject_from
from .memory import Memory

MAX_OUTPUT = 3000  # characters of command output / file text sent back to Claude


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, dict[str, Any]]
    func: Callable[..., str]
    required: tuple[str, ...] = ()
    risky: bool = False
    read_only: bool = False
    # How to describe the action when asking for confirmation, e.g. "delete {path}".
    confirm: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description + (" Jarvis asks the user to confirm first." if self.risky else ""),
            "input_schema": {
                "type": "object",
                "properties": self.params,
                "required": list(self.required),
            },
        }

    def question(self, args: dict[str, Any]) -> str:
        try:
            action = self.confirm.format(**{k: args.get(k, "") for k in self.params})
        except (KeyError, IndexError):
            action = self.name.replace("_", " ")
        return f"Should I {action}?"

    def run(self, args: dict[str, Any]) -> str:
        return self.func(**{k: v for k, v in args.items() if k in self.params})


def _s(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": description, **extra}


def _i(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "integer", "description": description, **extra}


KNOWN_FOLDERS = ("desktop", "downloads", "documents", "pictures", "music", "videos")


def resolve_path(path: str) -> Path:
    """Understand "downloads", "desktop/notes.txt", "~/x" and full paths."""
    raw = path.strip().strip('"')
    first, _, rest = raw.replace("\\", "/").partition("/")
    if first.lower() in KNOWN_FOLDERS:
        base = Path.home() / first.capitalize()
        return (base / rest).resolve() if rest else base
    if first.lower() in ("home", "~"):
        return (Path.home() / rest).resolve()
    return Path(raw).expanduser().resolve()


def build_tools(config: Config, actions: Actions, memory: Memory, mailer: Mailer,
                speak: Callable[[str], None] | None = None) -> dict[str, Tool]:
    is_windows = platform.system() == "Windows"
    tools: list[Tool] = []

    def tool(name: str, description: str, params: dict | None = None, required: tuple = (),
             risky: bool = False, read_only: bool = False, confirm: str = "") -> Callable:
        def register(fn: Callable[..., str]) -> Callable[..., str]:
            tools.append(Tool(name, description, params or {}, fn, required, risky, read_only, confirm))
            return fn
        return register

    # --- apps and windows ----------------------------------------------------

    @tool("open_app", "Open an app by name, e.g. notepad, calculator, chrome, vs code, spotify, settings.",
          {"name": _s("App name as the user said it")}, ("name",))
    def open_app(name: str) -> str:
        if actions.open_app(name.lower()):
            memory.record_app(name.lower())
            return f"Opened {name}."
        return f"Couldn't find an app called {name}."

    @tool("close_app", "Close a running app by name (unsaved work may be lost).",
          {"name": _s("App name, e.g. notepad, chrome")}, ("name",), risky=True, confirm="close {name}")
    def close_app(name: str) -> str:
        return f"Closed {name}." if actions.close_app(name.lower()) else f"{name} doesn't seem to be open."

    @tool("list_running_apps", "List the apps currently running, biggest first.", read_only=True)
    def list_running_apps() -> str:
        try:
            import psutil
        except ImportError:
            return "psutil isn't installed."
        usage: dict[str, float] = {}
        for p in psutil.process_iter(["name", "memory_info"]):
            name, mem = p.info.get("name"), p.info.get("memory_info")
            if name and mem:
                usage[name] = usage.get(name, 0) + mem.rss
        top = sorted(usage.items(), key=lambda kv: -kv[1])[:20]
        return "\n".join(f"{n}: {m / 2**20:.0f} MB" for n, m in top)

    @tool("list_windows", "List the titles of open windows.", read_only=True)
    def list_windows() -> str:
        try:
            import pygetwindow as gw
        except ImportError:
            return "Window control needs pyautogui (which installs pygetwindow)."
        titles = [t for t in gw.getAllTitles() if t.strip()]
        return "\n".join(titles[:40]) or "No windows found."

    @tool("focus_window", "Bring the first window whose title contains the text to the front.",
          {"title": _s("Part of the window title, e.g. 'Chrome' or 'Notepad'")}, ("title",))
    def focus_window(title: str) -> str:
        try:
            import pygetwindow as gw
        except ImportError:
            return "Window control needs pyautogui."
        matches = gw.getWindowsWithTitle(title)
        if not matches:
            return f"No window matching {title}."
        win = matches[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        return f"Switched to {win.title}."

    @tool("window_action", "Minimize, maximize or restore the active window, or show the desktop.",
          {"action": _s("What to do", enum=["minimize", "maximize", "restore", "show_desktop"])}, ("action",))
    def window_action(action: str) -> str:
        try:
            import pyautogui
        except ImportError:
            return "Window control needs pyautogui."
        keys = {"minimize": ("win", "down"), "maximize": ("win", "up"),
                "restore": ("win", "down"), "show_desktop": ("win", "d")}[action]
        pyautogui.hotkey(*keys)
        return "Done."

    @tool("press_keys", "Press a keyboard shortcut in the active window, e.g. 'ctrl+s', 'alt+tab', 'win+e', 'enter'.",
          {"keys": _s("Keys joined with +")}, ("keys",))
    def press_keys(keys: str) -> str:
        try:
            import pyautogui
        except ImportError:
            return "Keyboard control needs pyautogui."
        pyautogui.hotkey(*[k.strip().lower() for k in keys.split("+")])
        return f"Pressed {keys}."

    @tool("type_text", "Type text into the active window, as if on the keyboard.",
          {"text": _s("Text to type")}, ("text",))
    def type_text(text: str) -> str:
        return "Typed." if actions.type_text(text) else "Typing needs pyautogui."

    @tool("clipboard", "Read the clipboard, or put text on it.",
          {"action": _s("read or write", enum=["read", "write"]), "text": _s("Text to copy (for write)")},
          ("action",))
    def clipboard(action: str, text: str = "") -> str:
        try:
            import pyperclip
        except ImportError:
            return "Clipboard needs pyperclip (installed with pyautogui)."
        if action == "write":
            pyperclip.copy(text)
            return "Copied to the clipboard."
        return (pyperclip.paste() or "(empty)")[:MAX_OUTPUT]

    # --- web and media -------------------------------------------------------

    @tool("open_website", "Open a website or URL in the browser.", {"url": _s("URL or domain")}, ("url",))
    def open_website(url: str) -> str:
        actions.open_url(url if "://" in url else f"https://{url}")
        return f"Opened {url}."

    @tool("web_search", "Search Google in the browser.", {"query": _s("Search words")}, ("query",))
    def web_search(query: str) -> str:
        actions.open_url(f"https://www.google.com/search?q={quote_plus(query)}")
        return f"Searched for {query}."

    @tool("play_youtube", "Play a song or video on YouTube (opens and starts the top result).",
          {"query": _s("Song, artist or video")}, ("query",))
    def play_youtube(query: str) -> str:
        found = actions.play_youtube(query)
        memory.record_song(query)
        return f"Playing {query}." if found else f"Opened YouTube results for {query}."

    @tool("media_control", "Control whatever is playing (YouTube, Spotify...).",
          {"action": _s("Media key", enum=["play_pause", "next", "previous"])}, ("action",))
    def media_control(action: str) -> str:
        return "Done." if actions.media_key(action) else "Media keys only work on Windows."

    # --- sound, screen and power ---------------------------------------------

    @tool("set_volume", "Set the speaker volume (0-100), or turn it up/down a bit, or toggle mute.",
          {"level": _i("Exact level 0-100", minimum=0, maximum=100),
           "change": _s("Instead of a level", enum=["up", "down", "mute"])})
    def set_volume(level: int | None = None, change: str | None = None) -> str:
        if level is not None:
            actions.set_volume(int(level))
            return f"Volume set to {level}."
        key = {"up": "volume_up", "down": "volume_down", "mute": "mute"}.get(change or "")
        if not key:
            return "Give a level or a change."
        actions.media_key(key, 1 if key == "mute" else 5)
        return "Done."

    @tool("set_brightness", "Set the screen brightness (0-100).",
          {"level": _i("Brightness 0-100", minimum=0, maximum=100)}, ("level",))
    def set_brightness(level: int) -> str:
        return f"Brightness {level}." if actions.set_brightness(int(level)) else "Can't change brightness here."

    @tool("screenshot", "Take a screenshot and save it to Pictures/JarvisBuddy.")
    def screenshot() -> str:
        path = actions.screenshot()
        return f"Saved {path}." if path else "Screenshots need pillow."

    @tool("lock_screen", "Lock the laptop.")
    def lock_screen() -> str:
        return "Locked." if actions.lock_screen() else "Only works on Windows."

    @tool("power", "Shut down or restart the laptop (in 60 seconds).",
          {"action": _s("What to do", enum=["shut down", "restart"])}, ("action",),
          risky=True, confirm="{action} the laptop")
    def power(action: str) -> str:
        ok = actions.shutdown(restart=action == "restart")
        return f"{action.capitalize()} in 60 seconds." if ok else "Only works on Windows."

    @tool("cancel_shutdown", "Cancel a pending shutdown or restart.")
    def cancel_shutdown() -> str:
        actions.cancel_shutdown()
        return "Cancelled."

    @tool("system_status", "CPU, memory, battery and disk usage.", read_only=True)
    def system_status() -> str:
        status = actions.system_status()
        if status is None:
            return "psutil isn't installed."
        disk = shutil.disk_usage(Path.home())
        status["disk_free_gb"] = round(disk.free / 2**30, 1)
        return ", ".join(f"{k}: {v}" for k, v in status.items())

    @tool("weather", "Current weather for a city.", {"city": _s("City name")}, read_only=True)
    def weather(city: str = "") -> str:
        return actions.weather(city) or "Weather service unreachable."

    # --- files ---------------------------------------------------------------

    @tool("list_folder", "List files in a folder. Accepts desktop, downloads, documents, pictures, "
          "music, videos or a full path.", {"path": _s("Folder")}, ("path",), read_only=True)
    def list_folder(path: str) -> str:
        folder = resolve_path(path)
        if not folder.is_dir():
            return f"{folder} isn't a folder."
        items = sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
        return f"{folder}:\n" + "\n".join(f"{'[folder] ' if p.is_dir() else ''}{p.name}" for p in items)

    @tool("find_files", "Find files by name (part of the name) under a folder.",
          {"name": _s("Part of the file name"), "folder": _s("Where to look (default: home)")},
          ("name",), read_only=True)
    def find_files(name: str, folder: str = "home") -> str:
        root, hits = resolve_path(folder), []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "AppData")]
            hits += [str(Path(dirpath) / f) for f in filenames if name.lower() in f.lower()]
            if len(hits) >= 30:
                break
        return "\n".join(hits) or f"No files matching {name}."

    @tool("open_path", "Open a file or folder with its default app.", {"path": _s("File or folder")}, ("path",))
    def open_path(path: str) -> str:
        target = resolve_path(path)
        if not target.exists():
            return f"{target} doesn't exist."
        if is_windows:
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return f"Opened {target}."

    @tool("read_text_file", "Read a text file (first few thousand characters).",
          {"path": _s("File")}, ("path",), read_only=True)
    def read_text_file(path: str) -> str:
        target = resolve_path(path)
        try:
            return target.read_text(encoding="utf-8", errors="replace")[:MAX_OUTPUT]
        except OSError as e:
            return f"Couldn't read {target}: {e}"

    @tool("write_text_file", "Create or overwrite a text file.",
          {"path": _s("File"), "content": _s("Text to write")}, ("path", "content"),
          risky=True, confirm="write to {path}")
    def write_text_file(path: str, content: str) -> str:
        target = resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {target}."

    @tool("create_folder", "Create a folder.", {"path": _s("Folder to create")}, ("path",))
    def create_folder(path: str) -> str:
        target = resolve_path(path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Created {target}."

    @tool("move_file", "Move or rename a file or folder.",
          {"source": _s("What to move"), "destination": _s("New location or name")},
          ("source", "destination"), risky=True, confirm="move {source} to {destination}")
    def move_file(source: str, destination: str) -> str:
        src, dst = resolve_path(source), resolve_path(destination)
        if not src.exists():
            return f"{src} doesn't exist."
        shutil.move(str(src), str(dst))
        return f"Moved to {dst}."

    @tool("delete_file", "Delete a file or folder (to the Recycle Bin when possible).",
          {"path": _s("File or folder")}, ("path",), risky=True, confirm="delete {path}")
    def delete_file(path: str) -> str:
        target = resolve_path(path)
        if not target.exists():
            return f"{target} doesn't exist."
        if target in (Path.home(), Path(target.anchor)) or target.name.lower() in KNOWN_FOLDERS and target.parent == Path.home():
            return "I won't delete a main folder like that."
        try:
            from send2trash import send2trash

            send2trash(str(target))
            return f"Moved {target.name} to the Recycle Bin."
        except ImportError:
            return "I need the send2trash package to delete safely (to the Recycle Bin)."

    # --- communication, memory and time ---------------------------------------

    @tool("send_email", "Send an email. Use a saved contact name or an address.",
          {"to": _s("Contact name or email address"), "subject": _s("Subject (optional)"),
           "body": _s("Message")}, ("to", "body"), risky=True, confirm="send this email to {to}: {body}")
    def send_email(to: str, body: str, subject: str = "") -> str:
        address = memory.contact(to) or (to if "@" in to else None)
        if not address:
            return f"No email address saved for {to}. Ask the user for it, or to save the contact."
        subject = subject or subject_from(body)
        if not mailer.ready:
            actions.mail_draft(address, subject, body)
            return "Email isn't set up, so a draft opened in the mail app for the user to send."
        mailer.send(address, subject, body)
        return f"Sent to {address}."

    @tool("save_contact", "Save a contact's email address.",
          {"name": _s("Name"), "email": _s("Email address")}, ("name", "email"))
    def save_contact(name: str, email: str) -> str:
        memory.save_contact(name, email)
        return f"Saved {name}."

    @tool("remember", "Save a lasting fact about the user to memory.",
          {"fact": _s("Short third-person fact, e.g. 'Sri loves dosa'")}, ("fact",))
    def remember(fact: str) -> str:
        return "Saved." if memory.add_fact(fact) else "Already knew that."

    @tool("set_timer", "Set a timer or reminder that Jarvis will say out loud.",
          {"seconds": _i("Seconds from now", minimum=1), "message": _s("What to say when it goes off")},
          ("seconds",))
    def set_timer(seconds: int, message: str = "Your timer is done!") -> str:
        actions.schedule(int(seconds), lambda: speak and speak(message))
        return f"Timer set for {seconds} seconds."

    @tool("take_note", "Add a note to the notes file.", {"note": _s("The note")}, ("note",))
    def take_note(note: str) -> str:
        config.notes_file.parent.mkdir(parents=True, exist_ok=True)
        with config.notes_file.open("a", encoding="utf-8") as f:
            f.write(f"{note}\n")
        return "Noted."

    # --- anything else --------------------------------------------------------

    @tool("run_command", "Run a PowerShell command on the laptop and get its output. Use for anything "
          "the other tools can't do (Wi-Fi status, installed programs, settings...). Prefer read-only commands.",
          {"command": _s("PowerShell command")}, ("command",), risky=True, confirm="run this command: {command}")
    def run_command(command: str) -> str:
        shell = ["powershell", "-NoProfile", "-Command", command] if is_windows else ["bash", "-lc", command]
        try:
            result = subprocess.run(shell, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return "The command took too long and was stopped."
        output = (result.stdout + result.stderr).strip() or f"(no output, exit code {result.returncode})"
        return output[:MAX_OUTPUT]

    return {t.name: t for t in tools}


class ToolRunner:
    """Runs tools for Claude, asking the user first for risky ones."""

    def __init__(self, tools: dict[str, Tool], confirm: Callable[[str], bool],
                 extra: Any | None = None) -> None:
        self.tools = tools
        self.confirm = confirm
        self.extra = extra  # an McpHub with tools from other MCP servers
        self._lock = threading.Lock()

    def schemas(self) -> list[dict[str, Any]]:
        schemas = [t.schema() for t in self.tools.values()]
        if self.extra is not None:
            schemas += self.extra.schemas()
        return schemas

    def run(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Returns (result text, is_error)."""
        tool = self.tools.get(name)
        if tool is None and self.extra is not None and self.extra.has(name):
            if self.extra.is_risky(name) and not self.confirm(self.extra.question(name, args)):
                return "The user said no, so this wasn't done.", False
            return self.extra.call(name, args)
        if tool is None:
            return f"Unknown tool {name}.", True
        if tool.risky and not self.confirm(tool.question(args)):
            return "The user said no, so this wasn't done.", False
        try:
            return tool.run(args), False
        except Exception as e:
            return f"Error: {e}", True
