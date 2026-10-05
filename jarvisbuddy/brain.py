"""Answers anything the built-in skills don't cover, using Claude."""

from __future__ import annotations

from typing import Any

from .config import Config

MAX_TURNS = 20  # keep the last N exchanges so memory doesn't grow forever


class Brain:
    def __init__(self, config: Config, client: Any | None = None) -> None:
        self.config = config
        self.history: list[dict[str, Any]] = []
        self._client = client

    @property
    def available(self) -> bool:
        return self._client is not None or self.config.ai_enabled

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def _system_prompt(self) -> str:
        return (
            f"You are {self.config.assistant_name}, a friendly voice assistant running on "
            f"{self.config.user_name}'s Windows PC. Your replies are read aloud by text-to-speech, "
            "so answer in one to three short conversational sentences of plain text: no markdown, "
            "lists, code blocks or emoji. If a question needs a long answer, give the key point "
            "and offer to go deeper."
        )

    def ask(self, text: str) -> str:
        if not self.available:
            return (
                "I don't know that one yet. Add your Anthropic API key to the .env file "
                "and I'll be able to answer questions like this."
            )

        import anthropic

        messages = self.history + [{"role": "user", "content": text}]
        try:
            response = self._get_client().beta.messages.create(
                model=self.config.claude_model,
                # Spoken answers are deliberately short.
                max_tokens=1024,
                system=self._system_prompt(),
                messages=messages,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            return "My API key was rejected. Please check ANTHROPIC_API_KEY in your .env file."
        except anthropic.RateLimitError:
            return "I'm getting too many requests right now. Try again in a moment."
        except anthropic.APIStatusError as e:
            return f"Claude returned an error, status {e.status_code}. Try again in a moment."
        except anthropic.APIConnectionError:
            return "I can't reach the internet right now."

        if response.stop_reason == "refusal":
            return "Sorry, I can't help with that one."

        answer = " ".join(b.text for b in response.content if b.type == "text").strip()
        # Keep the full content so thinking and fallback blocks are replayed unchanged.
        self.history = messages + [{"role": "assistant", "content": response.content}]
        if len(self.history) > MAX_TURNS * 2:
            self.history = self.history[-MAX_TURNS * 2 :]
        return answer or "Hmm, I don't have an answer for that."
