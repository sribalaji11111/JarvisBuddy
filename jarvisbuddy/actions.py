"""Things Jarvis can do to your computer. Kept behind one class so tests can swap in a fake."""

from __future__ import annotations

import ctypes
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote, quote_plus, urlencode

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
    "whatsapp": "whatsapp:",
    "snipping tool": "snippingtool",
    "clock": "ms-clock:",
    "calendar": "outlookcal:",
}

# Spoken name -> process to close.
PROCESSES: dict[str, str] = {
    "notepad": "notepad.exe", "calculator": "CalculatorApp.exe", "calc": "CalculatorApp.exe",
    "paint": "mspaint.exe", "chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe",
    "microsoft edge": "msedge.exe", "firefox": "firefox.exe", "vs code": "Code.exe", "vscode": "Code.exe",
    "visual studio code": "Code.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE", "outlook": "OUTLOOK.EXE", "spotify": "Spotify.exe",
    "task manager": "Taskmgr.exe", "android studio": "studio64.exe",
}

# Windows virtual-key codes for media keys (work with YouTube, Spotify and most players).
MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1,
              "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}


class Actions:
    """Real side effects on the user's machine."""

    def __init__(self) -> None:
        self.is_windows = platform.system() == "Windows"

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def play_youtube(self, query: str) -> bool:
        """Open the top YouTube result so it starts playing. Falls back to the search page."""
        results = self.youtube_results(query, 1)
        if results:
            self.open_url(results[0][1])
            return True
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

    def youtube_results(self, query: str, n: int = 5) -> list[tuple[str, str]]:
        """Top YouTube results as (title, url), using yt-dlp. Empty if yt-dlp isn't installed."""
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            return []
        try:
            with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True,
                            "no_warnings": True}) as ydl:
                info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
        except Exception:
            return []
        return [(e.get("title") or query, f"https://www.youtube.com/watch?v={e['id']}")
                for e in info.get("entries") or [] if e.get("id")]

    def media_key(self, key: str, times: int = 1) -> bool:
        if not self.is_windows:
            return False
        for _ in range(times):
            ctypes.windll.user32.keybd_event(MEDIA_KEYS[key], 0, 0, 0)
            ctypes.windll.user32.keybd_event(MEDIA_KEYS[key], 0, 2, 0)
        return True

    def set_volume(self, level: int) -> bool:
        level = max(0, min(100, level))
        try:
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            device = AudioUtilities.GetSpeakers()
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            cast(interface, POINTER(IAudioEndpointVolume)).SetMasterVolumeLevelScalar(level / 100, None)
            return True
        except Exception:
            # Without pycaw: go to zero, then up in 2% steps.
            return self.media_key("volume_down", 50) and self.media_key("volume_up", level // 2)

    def set_brightness(self, level: int) -> bool:
        try:
            import screen_brightness_control as sbc

            sbc.set_brightness(max(0, min(100, level)))
            return True
        except Exception:
            return False

    def screenshot(self) -> Path | None:
        folder = Path.home() / "Pictures" / "JarvisBuddy"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("screenshot-%Y%m%d-%H%M%S.png")
        try:
            from PIL import ImageGrab

            ImageGrab.grab().save(path)
            return path
        except Exception:
            return None

    def type_text(self, text: str) -> bool:
        try:
            import pyautogui
        except ImportError:
            return False
        time.sleep(0.5)  # let the user's window take focus back
        pyautogui.write(text, interval=0.02)
        return True

    def close_app(self, name: str) -> bool:
        if not self.is_windows:
            return False
        process = PROCESSES.get(name, name if name.endswith(".exe") else f"{name}.exe")
        result = subprocess.run(["taskkill", "/im", process], capture_output=True, text=True)
        return result.returncode == 0

    def shutdown(self, restart: bool = False) -> bool:
        if not self.is_windows:
            return False
        subprocess.run(["shutdown", "/r" if restart else "/s", "/t", "60"])
        return True

    def cancel_shutdown(self) -> bool:
        if not self.is_windows:
            return False
        subprocess.run(["shutdown", "/a"], capture_output=True)
        return True

    def weather(self, city: str = "") -> str | None:
        url = f"https://wttr.in/{quote(city)}?format=%C,+%t,+wind+%w"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "curl"})
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.read().decode("utf-8").strip().replace("+", "")
        except OSError:
            return None

    def mail_draft(self, to: str, subject: str, body: str) -> None:
        """Open a ready-to-send draft in the default mail app."""
        self.open_url(f"mailto:{to}?" + urlencode({"subject": subject, "body": body}, quote_via=quote))

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
