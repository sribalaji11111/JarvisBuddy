from types import SimpleNamespace

from jarvisbuddy.brain import Brain
from jarvisbuddy.config import Config


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def make_brain(stop_reason="end_turn", text="Paris is the capital of France."):
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    messages = FakeMessages(SimpleNamespace(stop_reason=stop_reason, content=content))
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return Brain(Config(), client=client), messages


def test_answers_and_keeps_history():
    brain, api = make_brain()
    assert brain.ask("capital of france?") == "Paris is the capital of France."
    brain.ask("and germany?")
    second = api.calls[1]
    assert second["model"] == "claude-opus-5-5"
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert "read aloud" in second["system"]


def test_refusal():
    brain, _ = make_brain(stop_reason="refusal", text="")
    assert brain.ask("something") == "Sorry, I can't help with that one."
    assert brain.history == []


def test_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "API key" in Brain(Config()).ask("hello?")
