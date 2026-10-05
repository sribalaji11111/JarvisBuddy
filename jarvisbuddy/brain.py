"""Answers anything the built-in skills don't cover, using Claude.

Replies stream in and are spoken sentence by sentence, so Jarvis starts talking almost
immediately instead of waiting for the whole answer."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import Config
from .memory import Memory

MAX_TURNS = 20  # keep the last N exchanges so the conversation doesn't grow forever
MAX_TOOL_ROUNDS = 10  # tool calls Claude may chain for one request
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
                 moods: tuple[str, ...] = ("happy",), tools: Any | None = None) -> None:
        self.config = config
        self.tools = tools  # a ToolRunner: lets Claude control the laptop
        self.memory = memory
        self.moods = moods
        self.history: list[dict[str, Any]] = []
        self._client = client
        self._fast = config.fast_mode
        self.backup: Brain | None = None  # used when Claude can't be reached (set by make_brain)

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
        if self.tools is not None:
            prompt += (
                f"\n\nYou can control {name}'s laptop with your tools: apps, windows, keyboard, files, "
                "volume, media, power, email and PowerShell. When asked to do something, do it with the "
                "tools instead of explaining how. Before calling tools, say one very short line like "
                "'On it!'. After acting, confirm in a few words. Risky tools automatically ask the user "
                "out loud for a yes first, so don't ask for permission yourself; if the user says no, "
                "just accept it. Never guess email addresses."
            )
        personality = self.config.personality_file
        if personality.is_file():
            prompt += f"\n\nYour personality, written by {name}:\n" + personality.read_text(encoding="utf-8").strip()
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
            messages=list(messages),
            output_config={"effort": "low"},  # quick, chatty answers
            betas=[FALLBACK_BETA],
            fallbacks="default",
            cache_control={"type": "ephemeral"},  # tools + system prompt are reused every turn
        )
        if self.tools is not None:
            kwargs["tools"] = self.tools.schemas()
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
            if self.backup is not None and self.backup.available:
                return self.backup.ask(text, on_sentence)
            return Answer("I can't reach the internet right now.", "sad")

    def _stream(self, messages: list[dict[str, Any]], on_sentence: Callable[[str, str], None] | None) -> Answer:
        state: dict[str, Any] = {"mood": None, "spoken": []}
        convo = list(messages)
        for _ in range(MAX_TOOL_ROUNDS):
            final = self._stream_round(convo, on_sentence, state)
            if final.stop_reason == "refusal":
                return Answer("Sorry, I can't help with that one.", "sad", spoken=False)
            # Keep the full content so thinking, fallback and tool blocks are replayed unchanged.
            convo.append({"role": "assistant", "content": final.content})
            calls = [b for b in final.content if b.type == "tool_use"]
            if final.stop_reason != "tool_use" or not calls or self.tools is None:
                break
            results = []
            for call in calls:
                output, is_error = self.tools.run(call.name, dict(call.input or {}))
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": output, "is_error": is_error})
            convo.append({"role": "user", "content": results})

        self.history = self._trim(convo)
        spoken = state["spoken"]
        text = " ".join(spoken) or "Done!"
        return Answer(text, state["mood"] or "happy", spoken=bool(spoken) and on_sentence is not None)

    def _stream_round(self, convo: list[dict[str, Any]], on_sentence: Callable[[str, str], None] | None,
                      state: dict[str, Any]) -> Any:
        buffer = ""
        tag_checked = False

        def emit(sentence: str) -> None:
            sentence = sentence.strip()
            if sentence:
                state["spoken"].append(sentence)
                if on_sentence:
                    on_sentence(sentence, state["mood"] or "happy")

        def check_tag() -> None:
            nonlocal buffer
            tag = MOOD_TAG.match(buffer)
            mood = tag.group(1).lower() if tag else None
            if state["mood"] is None:
                state["mood"] = mood if mood in self.moods else "happy"
            if tag:
                buffer = buffer[tag.end():]

        with self._get_client().beta.messages.stream(**self._request(convo)) as stream:
            for chunk in stream.text_stream:
                buffer += chunk
                if not tag_checked:
                    # Wait until a [mood] tag is complete before speaking anything.
                    if buffer.lstrip().startswith("[") and "]" not in buffer and len(buffer) < 20:
                        continue
                    check_tag()
                    tag_checked = True
                while match := SENTENCE_END.match(buffer):
                    if not match.group(2):  # sentence might continue (e.g. "3." of "3.5")
                        break
                    emit(match.group(1))
                    buffer = buffer[match.end():]
            final = stream.get_final_message()
        if final.stop_reason != "refusal":
            if not tag_checked:
                check_tag()
            emit(buffer)
        return final

    @staticmethod
    def _trim(convo: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the last MAX_TURNS requests, cutting only where a new request starts so a tool
        call is never separated from its result."""
        starts = [i for i, m in enumerate(convo) if m["role"] == "user" and isinstance(m["content"], str)]
        return convo[starts[-MAX_TURNS]:] if len(starts) > MAX_TURNS else convo

    # --- learning ------------------------------------------------------------

    def learn_in_background(self, text: str) -> None:
        """Pick up personal facts from what the user said, without slowing down the reply."""
        if not (self.available and self.memory) or not re.search(r"\b(i|i'm|my|me|mine|we|our)\b", text, re.I):
            return
        threading.Thread(target=self._learn, args=(text,), daemon=True).start()

    def _learn(self, text: str) -> None:
        for fact in self.extract_facts(text, f"what {self._name()} just said to their voice assistant"):
            self.memory.add_fact(fact)

    def extract_facts(self, text: str, source: str) -> list[str]:
        """Lasting personal facts found in `text`, as short third-person sentences."""
        if not self.available:
            return []
        name = self._name()
        try:
            response = self._get_client().messages.create(
                model=self.config.claude_model,
                max_tokens=600,
                output_config={"effort": "low"},
                system=(
                    f"Extract lasting personal facts about {name} (preferences, people, work, plans, "
                    f"routines, background) from {source}. Write each as a short third-person sentence "
                    f"starting with '{name}', one per line. Skip questions, commands and passing moods. "
                    "If there is nothing worth remembering, reply NONE."
                ),
                messages=[{"role": "user", "content": text}],
            )
        except Exception:
            return []  # learning is best-effort
        out = " ".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "refusal" or not out or out.upper().startswith("NONE"):
            return []
        facts = [line.strip(" -•\t") for line in out.splitlines()]
        return [f for f in facts if f and f.upper() != "NONE"][:15]
