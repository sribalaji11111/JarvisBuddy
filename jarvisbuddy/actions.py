"""Things Jarvis can do to your computer. Kept behind one class so tests can swap in a fake."""

from __future__ import annotations

import platform
import shutil
import subprocess
import threading
import webbrowser
from typing import Callable

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
