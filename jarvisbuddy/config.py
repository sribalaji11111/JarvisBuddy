"""Settings, read from environment variables (or a .env file next to the project)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so users don't need an extra package. Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    user_name: str = "Sri"
    assistant_name: str = "Jarvis"
    wake_words: tuple[str, ...] = ("jarvis", "hey jarvis", "javis", "jervis", "jarvish", "jarwis")
    follow_up_seconds: float = 10  # keep listening this long after a reply, no wake word needed
    data_dir: Path = field(default_factory=lambda: Path.home() / ".jarvisbuddy")

    # Voice engine: "windows" (built-in, instant, offline) or "neural" (cuter, needs internet).
    voice_engine: str = "windows"
    # Voice: "singsong" (cute, bouncy), "robot" (flat and high) or "normal".
    voice_style: str = "singsong"
    voice_name: str = "Zira"  # any installed Windows voice; Zira is the high US female voice
    voice_rate: int = 2  # SAPI speed, -10 (slow) to 10 (fast)

    speech_language: str = "en-IN"  # accent for speech recognition, e.g. en-US, en-GB

    claude_model: str = "claude-opus-5-5"
    fast_mode: bool = False

    email_address: str = ""
    email_password: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465

    @property
    def notes_file(self) -> Path:
        return self.data_dir / "notes.txt"

    @property
    def personality_file(self) -> Path:
        override = os.environ.get("JARVIS_PERSONALITY_FILE")
        return Path(override).expanduser() if override else Path(__file__).resolve().parent.parent / "personality.md"

    @property
    def memory_file(self) -> Path:
        return self.data_dir / "memory.json"

    @property
    def ai_enabled(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_address and self.email_password)

    @classmethod
    def from_env(cls, dotenv: Path | None = None) -> "Config":
        _load_dotenv(dotenv or Path.cwd() / ".env")
        env = os.environ.get
        cfg = cls()
        cfg.user_name = env("JARVIS_USER_NAME") or cfg.user_name
        cfg.assistant_name = env("JARVIS_NAME") or cfg.assistant_name
        name = cfg.assistant_name.lower()
        if name != "jarvis":
            cfg.wake_words = (name, f"hey {name}")
        if follow := env("JARVIS_FOLLOW_UP_SECONDS"):
            cfg.follow_up_seconds = float(follow)
        if data_dir := env("JARVIS_DATA_DIR"):
            cfg.data_dir = Path(data_dir).expanduser()
        cfg.voice_engine = (env("JARVIS_VOICE_ENGINE") or cfg.voice_engine).lower()
        cfg.voice_style = (env("JARVIS_VOICE_STYLE") or cfg.voice_style).lower()
        cfg.voice_name = env("JARVIS_VOICE") or cfg.voice_name
        if rate := env("JARVIS_VOICE_RATE"):
            cfg.voice_rate = int(rate)
        cfg.speech_language = env("JARVIS_SPEECH_LANGUAGE") or cfg.speech_language
        cfg.claude_model = env("JARVIS_CLAUDE_MODEL") or cfg.claude_model
        cfg.fast_mode = _flag("JARVIS_FAST_MODE")
        cfg.email_address = env("JARVIS_EMAIL_ADDRESS", "")
        cfg.email_password = env("JARVIS_EMAIL_APP_PASSWORD", "").replace(" ", "")
        cfg.smtp_host = env("JARVIS_SMTP_HOST") or cfg.smtp_host
        if port := env("JARVIS_SMTP_PORT"):
            cfg.smtp_port = int(port)
        return cfg
