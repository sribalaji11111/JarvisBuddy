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


@dataclass
class Config:
    user_name: str = "Sri"
    assistant_name: str = "Jarvis"
    wake_words: tuple[str, ...] = ("jarvis", "hey jarvis")
    notes_file: Path = field(default_factory=lambda: Path.home() / "jarvisbuddy_notes.txt")
    claude_model: str = "claude-opus-5-5"
    voice_rate: int = 180

    @property
    def ai_enabled(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @classmethod
    def from_env(cls, dotenv: Path | None = None) -> "Config":
        _load_dotenv(dotenv or Path.cwd() / ".env")
        cfg = cls()
        cfg.user_name = os.environ.get("JARVIS_USER_NAME", cfg.user_name)
        cfg.assistant_name = os.environ.get("JARVIS_NAME", cfg.assistant_name)
        name = cfg.assistant_name.lower()
        cfg.wake_words = (name, f"hey {name}")
        if notes := os.environ.get("JARVIS_NOTES_FILE"):
            cfg.notes_file = Path(notes).expanduser()
        cfg.claude_model = os.environ.get("JARVIS_CLAUDE_MODEL", cfg.claude_model)
        if rate := os.environ.get("JARVIS_VOICE_RATE"):
            cfg.voice_rate = int(rate)
        return cfg
