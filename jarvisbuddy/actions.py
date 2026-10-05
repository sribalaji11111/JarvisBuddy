"""Things Jarvis can do to your computer. Kept behind one class so tests can swap in a fake."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import threading
import urllib.request
import webbrowser
from typing import Callable
from urllib.parse import quote_plus

# Spoken name -> Windows command (run via `start`, so anything on PATH or registered works).
WINDOWS_APPS: dict[str, str] = {
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "command prompt": "cmd",
    "cmd": "cmd",
    "terminal": "wt",
    "powershell": "powershell",
    "file explorer": "explorer",
    "explorer": "explorer",
    "files": "explorer",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "task manager": "taskmgr",
    "control panel": "control",
    "settings": "ms-settings:",
    "camera": "microsoft.windows.camera:",
    "spotify": "spotify:",
    "android studio": "studio64",
}


class Actions:
    """Real side effects on the user's machine."""

    def __init__(self) -> None:
        self.is_windows = platform.system() == "Windows"

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def play_youtube(self, query: str) -> bool:
        """Open the top YouTube result so it starts playing. Falls back to the search page."""
        search = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        video_id = first_youtube_video(search)
        self.open_url(f"https://www.youtube.com/watch?v={video_id}" if video_id else search)
        return video_id is not None

    def open_app(self, name: str) -> bool:
        """Launch an app by its spoken name. Returns False if we couldn't find it."""
        command = WINDOWS_APPS.get(name, name)
        try:
            if self.is_windows:
                # `start` resolves App Paths and protocol handlers like ms-settings:.
                subprocess.Popen(["cmd", "/c", "start", "", command], shell=False)
                return True
            exe = shutil.which(command)
            if exe:
                subprocess.Popen([exe])
                return True
        except OSError:
            pass
        return False

    def lock_screen(self) -> bool:
        if not self.is_windows:
            return False
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return True

    def schedule(self, seconds: float, callback: Callable[[], None]) -> None:
        timer = threading.Timer(seconds, callback)
        timer.daemon = True
        timer.start()

    def system_status(self) -> dict[str, float] | None:
        try:
            import psutil
        except ImportError:
            return None
        status: dict[str, float] = {
            "cpu": psutil.cpu_percent(interval=0.5),
            "memory": psutil.virtual_memory().percent,
        }
        battery = psutil.sensors_battery()
        if battery is not None:
            status["battery"] = battery.percent
            status["plugged"] = float(bool(battery.power_plugged))
        return status


def first_youtube_video(search_url: str, timeout: float = 4) -> str | None:
    request = urllib.request.Request(
        search_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "en"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            page = response.read().decode("utf-8", "ignore")
    except OSError:
        return None
    return parse_first_video_id(page)


def parse_first_video_id(page: str) -> str | None:
    match = re.search(r'"videoId":"([\w-]{11})"', page) or re.search(r"/watch\?v=([\w-]{11})", page)
    return match.group(1) if match else None
