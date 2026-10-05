"""An offline brain that runs on your own laptop with Ollama (free and private).

Install Ollama from https://ollama.com, then `python -m jarvisbuddy --setup` downloads the
model. Jarvis uses Claude when an API key is set and Ollama otherwise (see JARVIS_BRAIN)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from .brain import MOOD_TAG, SENTENCE_END, Answer, Brain

MAX_TOOL_ROUNDS = 6


class SentenceStream:
    """Turns streamed text into spoken sentences, reading the [mood] tag at the start."""

    def __init__(self, moods: tuple[str, ...], on_sentence: Callable[[str, str], None] | None,
                 state: dict[str, Any]) -> None:
        self.moods, self.on_sentence, self.state = moods, on_sentence, state
        self.buffer = ""
        self.tag_checked = False

    def _check_tag(self) -> None:
        tag = MOOD_TAG.match(self.buffer)
        mood = tag.group(1).lower() if tag else None
        if self.state.get("mood") is None:
            self.state["mood"] = mood if mood in self.moods else "happy"
        if tag:
            self.buffer = self.buffer[tag.end():]

    def _emit(self, sentence: str) -> None:
        sentence = sentence.strip()
        if sentence:
            self.state.setdefault("spoken", []).append(sentence)
            if self.on_sentence:
                self.on_sentence(sentence, self.state["mood"] or "happy")

    def feed(self, chunk: str) -> None:
        self.buffer += chunk
        if not self.tag_checked:
            if self.buffer.lstrip().startswith("[") and "]" not in self.buffer and len(self.buffer) < 20:
                return
            self._check_tag()
            self.tag_checked = True
        while match := SENTENCE_END.match(self.buffer):
            if not match.group(2):
                break
            self._emit(match.group(1))
            self.buffer = self.buffer[match.end():]

    def finish(self) -> None:
        if not self.tag_checked:
            self._check_tag()
        self._emit(self.buffer)
        self.buffer = ""


class OllamaBrain(Brain):
    def __init__(self, *args: Any, url: str = "http://localhost:11434", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.url = url.rstrip("/")
        self.use_tools = True

    @property
    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=1.5):
                return True
        except OSError:
            return False

    def _post(self, path: str, body: dict[str, Any], timeout: float = 120):
        request = urllib.request.Request(f"{self.url}{path}", json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
        return urllib.request.urlopen(request, timeout=timeout)

    def _tool_schemas(self) -> list[dict[str, Any]]:
        if self.tools is None or not self.use_tools:
            return []
        return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["input_schema"]}}
                for t in self.tools.schemas()]

    def _chat(self, messages: list[dict[str, Any]], stream: SentenceStream) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.ollama_model,
            "messages": [{"role": "system", "content": self.system_prompt()}] + messages,
            "stream": True,
            "keep_alive": "30m",  # keep the model in memory so answers start fast
            "options": {"temperature": 0.7, "num_predict": 300},
        }
        if tools := self._tool_schemas():
            body["tools"] = tools
        content, calls = "", []
        try:
            response = self._post("/api/chat", body)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "tools" in body:  # this model can't use tools; chat without them
                self.use_tools = False
                return self._chat(messages, stream)
            raise
        with response:
            for line in response:
                if not line.strip():
                    continue
                part = json.loads(line)
                message = part.get("message", {})
                if piece := message.get("content"):
                    content += piece
                    stream.feed(piece)
                calls += message.get("tool_calls") or []
                if part.get("done"):
                    break
        stream.finish()
        return {"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})}

    def ask(self, text: str, on_sentence: Callable[[str, str], None] | None = None) -> Answer:
        if not self.available:
            return Answer("My offline brain isn't running. Start Ollama, or add an Anthropic API key.", "sleepy")
        state: dict[str, Any] = {"mood": None, "spoken": []}
        convo = self.history + [{"role": "user", "content": text}]
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                reply = self._chat(convo, SentenceStream(self.moods, on_sentence, state))
                convo.append(reply)
                if not reply.get("tool_calls") or self.tools is None:
                    break
                for call in reply["tool_calls"]:
                    fn = call.get("function", {})
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        args = json.loads(args or "{}")
                    output, _ = self.tools.run(fn.get("name", ""), args)
                    convo.append({"role": "tool", "content": output, "tool_name": fn.get("name", "")})
        except (OSError, ValueError) as e:
            return Answer(f"My offline brain had a hiccup: {e}", "sad")
        starts = [i for i, m in enumerate(convo) if m["role"] == "user"]
        self.history = convo[starts[-12]:] if len(starts) > 12 else convo
        spoken = state["spoken"]
        return Answer(" ".join(spoken) or "Done!", state["mood"] or "happy",
                      spoken=bool(spoken) and on_sentence is not None)

    def extract_facts(self, text: str, source: str) -> list[str]:
        name = self._name()
        prompt = (f"Here is {source}:\n\n{text}\n\nList lasting personal facts about {name} (likes, people, "
                  f"work, plans, habits), one per line starting with '- {name}'. If none, answer NONE.")
        try:
            with self._post("/api/generate", {"model": self.config.ollama_model, "prompt": prompt,
                                               "stream": False}, timeout=300) as r:
                out = json.load(r).get("response", "")
        except (OSError, ValueError):
            return []
        return [m.strip() for m in re.findall(r"^\s*-\s*(.+)$", out, re.M) if len(m.strip()) > 3][:15]


def make_brain(config, memory, moods, tools=None) -> Brain:
    """Claude when an API key is set (or JARVIS_BRAIN=claude), otherwise Ollama."""
    choice = config.brain
    if choice == "ollama" or (choice == "auto" and not config.ai_enabled):
        local = OllamaBrain(config, memory, moods=moods, tools=tools, url=config.ollama_url)
        if choice == "ollama" or local.available:
            return local
    brain = Brain(config, memory, moods=moods, tools=tools)
    if choice == "auto":  # fall back to the offline brain when there's no internet
        brain.backup = OllamaBrain(config, memory, moods=moods, tools=tools, url=config.ollama_url)
    return brain
