"""What Jarvis knows about you. Saved as JSON so it survives restarts and grows every day."""

from __future__ import annotations

import json
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class DailyQuestion:
    id: str
    question: str
    fact: str  # "{name}" and "{answer}" are filled in


# One new question a day, so Jarvis gets to know you a little more each time.
DAILY_QUESTIONS = [
    DailyQuestion("food", "what's your favorite food?", "{name}'s favorite food is {answer}"),
    DailyQuestion("music", "what kind of music do you like?", "{name} likes {answer} music"),
    DailyQuestion("song", "what's a song you never get tired of?", "{name}'s favorite song is {answer}"),
    DailyQuestion("hobby", "what do you like to do for fun?", "For fun, {name} likes {answer}"),
    DailyQuestion("work", "what do you do, work or studies?", "{name} does {answer}"),
    DailyQuestion("color", "what's your favorite color?", "{name}'s favorite color is {answer}"),
    DailyQuestion("movie", "what's your favorite movie?", "{name}'s favorite movie is {answer}"),
    DailyQuestion("goal", "what's one goal you're working on?", "{name} is working toward {answer}"),
    DailyQuestion("city", "which city do you live in?", "{name} lives in {answer}"),
    DailyQuestion("birthday", "when is your birthday?", "{name}'s birthday is {answer}"),
    DailyQuestion("drink", "tea or coffee?", "{name} prefers {answer}"),
    DailyQuestion("sport", "do you follow any sport or team?", "{name} follows {answer}"),
    DailyQuestion("game", "what's your favorite game?", "{name}'s favorite game is {answer}"),
    DailyQuestion("pet", "do you have a pet, or want one?", "About pets, {name} said: {answer}"),
    DailyQuestion("wake", "what time do you usually wake up?", "{name} usually wakes up at {answer}"),
]


class Memory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.data: dict = {
            "facts": [],
            "contacts": {},
            "answered": [],
            "last_question_day": None,
            "apps": {},
            "songs": [],
            "days_used": [],
        }
        if path.is_file():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass  # a corrupt file shouldn't stop Jarvis from starting

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)

    # --- facts ---------------------------------------------------------------

    @property
    def facts(self) -> list[str]:
        return [f["text"] for f in self.data["facts"]]

    def add_fact(self, text: str, today: date | None = None) -> bool:
        text = text.strip().rstrip(".")
        if not text or text.lower() in (f.lower() for f in self.facts):
            return False
        self.data["facts"].append({"text": text, "day": str(today or date.today())})
        self.save()
        return True

    def forget(self, phrase: str) -> int:
        before = len(self.data["facts"])
        self.data["facts"] = [f for f in self.data["facts"] if phrase.lower() not in f["text"].lower()]
        removed = before - len(self.data["facts"])
        if removed:
            self.save()
        return removed

    @property
    def name(self) -> str | None:
        return self.data.get("name")

    def set_name(self, name: str) -> None:
        self.data["name"] = name
        self.save()

    # --- contacts ------------------------------------------------------------

    def contact(self, name: str) -> str | None:
        return self.data["contacts"].get(name.lower().strip())

    def save_contact(self, name: str, email: str) -> None:
        self.data["contacts"][name.lower().strip()] = email
        self.save()

    # --- habits --------------------------------------------------------------

    def record_app(self, name: str) -> None:
        self.data["apps"][name] = self.data["apps"].get(name, 0) + 1
        self.save()

    def record_song(self, song: str) -> None:
        self.data["songs"] = (self.data["songs"] + [song])[-50:]
        self.save()

    def favorite_apps(self, n: int = 3) -> list[str]:
        return [a for a, _ in Counter(self.data["apps"]).most_common(n)]

    def favorite_songs(self, n: int = 3) -> list[str]:
        return [s for s, _ in Counter(self.data["songs"]).most_common(n)]

    def mark_day(self, today: date) -> bool:
        """Record that Jarvis ran today. Returns True on the first run of the day."""
        day = str(today)
        if day in self.data["days_used"]:
            return False
        self.data["days_used"] = (self.data["days_used"] + [day])[-400:]
        self.save()
        return True

    # --- daily question ------------------------------------------------------

    def daily_question(self, today: date) -> DailyQuestion | None:
        if self.data.get("last_question_day") == str(today):
            return None
        for q in DAILY_QUESTIONS:
            if q.id not in self.data["answered"]:
                self.data["last_question_day"] = str(today)
                self.save()
                return q
        return None

    def answer(self, q: DailyQuestion, answer: str, name: str) -> str:
        fact = q.fact.format(name=name, answer=answer.strip().rstrip("."))
        self.data["answered"].append(q.id)
        self.add_fact(fact)
        return fact

    # --- summary for Claude --------------------------------------------------

    def profile(self, name: str) -> str:
        lines = [f"- {f}" for f in self.facts[-60:]]
        if apps := self.favorite_apps():
            lines.append(f"- {name} often opens: {', '.join(apps)}")
        if songs := self.favorite_songs():
            lines.append(f"- {name} often plays: {', '.join(songs)}")
        if days := len(self.data["days_used"]):
            lines.append(f"- You have chatted with {name} on {days} different days")
        return "\n".join(lines)
