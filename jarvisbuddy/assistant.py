"""The main loop: wait for the wake word, hear a command, act on it, reply with voice and face."""

from __future__ import annotations

import random
import re
import time
from typing import Callable, Protocol

from . import skills
from .actions import Actions
from .brain import Brain
from .config import Config
from .mailer import Mailer
from .memory import Memory


class UI(Protocol):
    def set_mood(self, mood: str) -> None: ...
    def set_status(self, text: str) -> None: ...
    def set_caption(self, text: str) -> None: ...
    def set_speaking(self, speaking: bool) -> None: ...


class NoUI:
    def set_mood(self, mood: str) -> None: pass
    def set_status(self, text: str) -> None: pass
    def set_caption(self, text: str) -> None: pass
    def set_speaking(self, speaking: bool) -> None: pass


POKES = ["Hehe, that tickles!", "Hey! Boop!", "Beep beep! Personal space!", "Ooh, do it again!"]


def strip_wake_word(text: str, wake_words: tuple[str, ...]) -> str | None:
    """Return the command after the wake word, "" if only the wake word was said,
    or None if the wake word wasn't said at all."""
    lowered = text.lower()
    for word in sorted(wake_words, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(word)}\b[\s,.!?]*", lowered)
        if match:
            return text[match.end():].strip()
    return None


class Assistant:
    def __init__(
        self,
        config: Config,
        speak: Callable[[str], None],
        ui: UI | None = None,
        actions: Actions | None = None,
        memory: Memory | None = None,
        brain: Brain | None = None,
        mailer: Mailer | None = None,
    ) -> None:
        self.config = config
        self._speak = speak
        self.ui = ui or NoUI()
        self.actions = actions or Actions()
        self.memory = memory or Memory(config.memory_file)
        self.brain = brain or Brain(config, self.memory, moods=skills.MOODS)
        self.ctx = skills.Context(
            config=config, actions=self.actions, memory=self.memory, speak=self.say,
            mailer=mailer or Mailer(config), brain=self.brain,
        )

    def say(self, text: str, mood: str = "happy") -> None:
        print(f"{self.config.assistant_name}: {text}")
        self.ui.set_mood(mood)
        self.ui.set_caption(text)
        self.ui.set_speaking(True)
        try:
            self._speak(text)
        finally:
            self.ui.set_speaking(False)

    def respond(self, text: str) -> skills.Reply:
        reply = skills.handle(text, self.ctx)
        if reply is not None:
            return reply
        self.ui.set_status("Thinking...")
        self.ui.set_mood("thinking")
        answer = self.brain.ask(text, on_sentence=self.say)
        self.brain.learn_in_background(text)
        self.ui.set_status("")
        return skills.Reply(answer.text, mood=answer.mood, spoken=answer.spoken)

    def handle(self, text: str) -> skills.Reply:
        """Respond to `text` and say the reply (unless it was already spoken while streaming)."""
        self.ui.set_caption(f"You: {text}")
        self.memory.log("user", text)
        try:
            reply = self.respond(text)
        except Exception as e:  # a broken skill shouldn't crash Jarvis
            reply = skills.Reply(f"Oops, that didn't work: {e}", mood="sad")
        if not reply.spoken:
            self.say(reply.text, reply.mood)
        self.memory.log("assistant", reply.text)
        return reply

    def greet(self) -> None:
        reply = skills.greeting(self.ctx)
        self.say(reply.text, reply.mood)

    def poke(self) -> None:
        self.say(random.choice(POKES), "laugh")

    def run_text(self, read: Callable[[str], str] = input) -> None:
        """Keyboard chat. No wake word needed."""
        self.greet()
        while True:
            try:
                text = read("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text and self.handle(text).end_session:
                break

    def run_voice(self, listener, always_listen: bool = False) -> None:
        """Voice mode. Wake word, then the command. After each reply Jarvis keeps listening for
        a few seconds, so you can carry on without saying the wake word again; questions like
        "Should I send it?" are answered the same way."""
        self.greet()
        wake = self.config.wake_words
        idle_status = "Listening..." if always_listen else f'Say "{wake[1].title()}"'
        print(f"({idle_status}. Press Ctrl+C to quit.)")
        awake_until = time.monotonic() + self.config.follow_up_seconds if self.ctx.pending else 0.0
        while True:
            remaining = awake_until - time.monotonic()
            if remaining > 0 or self.ctx.pending is not None:
                self.ui.set_status("Listening for your answer..." if self.ctx.pending else "I'm listening...")
                heard = listener.listen(timeout=max(remaining, 4))
                if not heard:
                    self.ctx.pending = None  # don't let a stray "yes" later send an email
                    awake_until = 0.0
                    continue
                command = strip_wake_word(heard, wake) or heard
            else:
                self.ui.set_status(idle_status)
                heard = listener.listen()
                if not heard:
                    continue
                command = heard if always_listen else strip_wake_word(heard, wake)
                if command is None:
                    continue
                if not command:
                    self.say("Yes?", "excited")
                    awake_until = time.monotonic() + self.config.follow_up_seconds
                    continue
            print(f"You: {command}")
            if self.handle(command).end_session:
                break
            awake_until = time.monotonic() + self.config.follow_up_seconds
