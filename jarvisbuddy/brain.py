"""Answers anything the built-in skills don't cover, using Claude.

Replies stream in and are spoken sentence by sentence, so Jarvis starts talking almost
immediately instead of waiting for the whole answer."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

from .config import Config
from .memory import Memory

MAX_TURNS = 20  # keep the last N exchanges so the conversation doesn't grow forever
MOOD_TAG = re.compile(r"^\s*\[(\w+)\]\s*")
SENTENCE_END = re.compile(r"(.+?[.!?])(\s+|$)", re.S)

FAST_MODE_BETA = "fast-mode-2026-02-01"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class Answer:
    text: str
    mood: str = "happy"
    spoken: bool = False


class Brain:
    def __init__(self, config: Config, memory: Memory | None = None, client: Any | None = None,
                 moods: tuple[str, ...] = ("happy",)) -> None:
        self.config = config
        self.memory = memory
        self.moods = moods
        self.history: list[dict[str, Any]] = []
        self._client = client
        self._fast = config.fast_mode

    @property
    def available(self) -> bool:
        return self._client is not None or self.config.ai_enabled

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def _name(self) -> str:
        return (self.memory.name if self.memory else None) or self.config.user_name

    def system_prompt(self) -> str:
        name = self._name()
        prompt = (
            f"You are {self.config.assistant_name}, a tiny, cute, cheerful robot who lives on {name}'s "
            "Windows laptop, a bit like EVE from WALL-E with a comedian's timing. Your replies are "
            "spoken aloud in a high sing-song robot voice, so: answer in one to three short sentences, "
            "plain words only (no markdown, lists, emoji or code), put the answer first, and add a "
            "playful or funny touch when it fits. For long topics, give the key point and offer more.\n\n"
            f"Start every reply with one face tag in square brackets that matches how you feel, chosen "
            f"from: {', '.join(self.moods)}. Example: [laugh] Because light attracts bugs!"
        )
        profile = self.memory.profile(name) if self.memory else ""
        if profile:
            prompt += (
                f"\n\nWhat you've learned about {name} so far. Use it naturally to be personal, "
                f"but don't recite it:\n{profile}"
            )
        return prompt

    def _request(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = dict(
            model=self.config.claude_model,
            max_tokens=1024,  # spoken answers are deliberately short
            system=self.system_prompt(),
            messages=messages,
            output_config={"effort": "low"},  # quick, chatty answers
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if self._fast:
            kwargs["betas"] = [FALLBACK_BETA, FAST_MODE_BETA]
            kwargs["speed"] = "fast"
        return kwargs

    def ask(self, text: str, on_sentence: Callable[[str, str], None] | None = None) -> Answer:
        """Answer `text`. If `on_sentence` is given, each sentence is passed to it (with the
        mood) as soon as it arrives, and the returned Answer is marked as already spoken."""
        if not self.available:
            return Answer(
                "Ooh, I don't know that one yet! Add your Anthropic API key to the .env file "
                "and I'll be able to answer questions like this.",
                mood="confused",
            )
        import anthropic

        messages = self.history + [{"role": "user", "content": text}]
        try:
            return self._stream(messages, on_sentence)
        except anthropic.BadRequestError as e:
            if not self._fast:
                return Answer(f"Claude didn't accept that request: {e.message}", "confused")
            self._fast = False  # fast mode not available on this account; use normal speed
            return self.ask(text, on_sentence)
        except anthropic.AuthenticationError:
            return Answer("My API key was rejected. Please check ANTHROPIC_API_KEY in the .env file.", "sad")
        except anthropic.RateLimitError:
            return Answer("Whoa, too many questions at once! Try again in a moment.", "confused")
        except anthropic.APIStatusError as e:
            return Answer(f"Claude had a hiccup, error {e.status_code}. Try again in a moment.", "sad")
        except anthropic.APIConnectionError:
            return Answer("I can't reach the internet right now.", "sad")

    def _stream(self, messages: list[dict[str, Any]], on_sentence: Callable[[str, str], None] | None) -> Answer:
        mood: str | None = None
        buffer = ""
        spoken: list[str] = []

        def emit(sentence: str) -> None:
            sentence = sentence.strip()
            if sentence:
                spoken.append(sentence)
                if on_sentence:
                    on_sentence(sentence, mood or "happy")

        with self._get_client().beta.messages.stream(**self._request(messages)) as stream:
            for chunk in stream.text_stream:
                buffer += chunk
                if mood is None:
                    # Wait until the [mood] tag is complete before speaking anything.
                    if buffer.lstrip().startswith("[") and "]" not in buffer and len(buffer) < 20:
                        continue
                    tag = MOOD_TAG.match(buffer)
                    mood = tag.group(1).lower() if tag and tag.group(1).lower() in self.moods else "happy"
                    if tag:
                        buffer = buffer[tag.end():]
                while match := SENTENCE_END.match(buffer):
                    if not match.group(2):  # sentence might continue (e.g. "3." of "3.5")
                        break
                    emit(match.group(1))
                    buffer = buffer[match.end():]
            final = stream.get_final_message()

        if final.stop_reason == "refusal":
            return Answer("Sorry, I can't help with that one.", "sad", spoken=False)

        if mood is None:  # very short reply that never finished its tag check
            tag = MOOD_TAG.match(buffer)
            mood = tag.group(1).lower() if tag and tag.group(1).lower() in self.moods else "happy"
            buffer = buffer[tag.end():] if tag else buffer
        emit(buffer)

        # Keep the full content so thinking and fallback blocks are replayed unchanged.
        self.history = messages + [{"role": "assistant", "content": final.content}]
        if len(self.history) > MAX_TURNS * 2:
            self.history = self.history[-MAX_TURNS * 2 :]
        text = " ".join(spoken) or "Hmm, I don't have an answer for that."
        return Answer(text, mood, spoken=bool(spoken) and on_sentence is not None)

    # --- learning ------------------------------------------------------------

    def learn_in_background(self, text: str) -> None:
        """Pick up personal facts from what the user said, without slowing down the reply."""
        if not (self.available and self.memory) or not re.search(r"\b(i|i'm|my|me|mine|we|our)\b", text, re.I):
            return
        threading.Thread(target=self._learn, args=(text,), daemon=True).start()

    def _learn(self, text: str) -> None:
        name = self._name()
        try:
            response = self._get_client().messages.create(
                model=self.config.claude_model,
                max_tokens=300,
                output_config={"effort": "low"},
                system=(
                    f"Extract lasting personal facts about {name} (preferences, people, plans, routines, "
                    f"background) from what {name} just said to their voice assistant. Write each as a "
                    f"short third-person sentence starting with '{name}', one per line. Skip questions, "
                    "commands and passing moods. If there is nothing worth remembering, reply NONE."
                ),
                messages=[{"role": "user", "content": text}],
            )
        except Exception:
            return  # learning is best-effort
        out = " ".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "refusal" or not out or out.upper().startswith("NONE"):
            return
        for line in out.splitlines():
            line = line.strip(" -•\t")
            if line and line.upper() != "NONE":
                self.memory.add_fact(line)
