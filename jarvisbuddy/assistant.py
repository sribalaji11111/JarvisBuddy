"""The main loop: wait for the wake word, hear a command, act on it, reply."""

from __future__ import annotations

import re
from typing import Callable

from . import skills
from .actions import Actions
from .brain import Brain
from .config import Config


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
        actions: Actions | None = None,
        brain: Brain | None = None,
    ) -> None:
        self.config = config
        self.speak = speak
        self.actions = actions or Actions()
        self.brain = brain or Brain(config)
        self.ctx = skills.Context(config=config, actions=self.actions, speak=speak)

    def respond(self, text: str) -> skills.Reply:
        reply = skills.handle(text, self.ctx)
        if reply is None:
            reply = skills.Reply(self.brain.ask(text))
        return reply

    def greet(self) -> None:
        self.speak(skills.greeting(self.ctx))

    def run_text(self, read: Callable[[str], str] = input) -> None:
        """Keyboard chat. No wake word needed."""
        self.greet()
        while True:
            try:
                text = read("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            reply = self.respond(text)
            self.speak(reply.text)
            if reply.end_session:
                break

    def run_voice(self, listener, always_listen: bool = False) -> None:
        """Voice mode. Says "Yes?" after the wake word, then listens for the command."""
        self.greet()
        wake = self.config.wake_words
        if not always_listen:
            print(f'(Listening for "{wake[-1]}"... press Ctrl+C to quit.)')
        while True:
            heard = listener.listen()
            if not heard:
                continue
            print(f"You: {heard}")
            command: str | None = heard
            if not always_listen:
                command = strip_wake_word(heard, wake)
                if command is None:
                    continue
                if not command:
                    self.speak("Yes?")
                    command = listener.listen(timeout=6)
                    if not command:
                        continue
                    print(f"You: {command}")
            reply = self.respond(command)
            self.speak(reply.text)
            if reply.end_session:
                break
