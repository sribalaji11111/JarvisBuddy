from types import SimpleNamespace

import anthropic
import httpx

from jarvisbuddy.brain import Brain
from jarvisbuddy.config import Config
from jarvisbuddy.memory import Memory
from jarvisbuddy.skills import MOODS


class FakeStream:
    def __init__(self, chunks, stop_reason):
        self.text_stream = iter(chunks)
        self.final = SimpleNamespace(stop_reason=stop_reason,
                                     content=[SimpleNamespace(type="text", text="".join(chunks))])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.final


class FakeMessages:
    def __init__(self, chunks, stop_reason="end_turn", error=None):
        self.chunks, self.stop_reason, self.error, self.calls = chunks, stop_reason, error, []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.error and len(self.calls) == 1:
            raise self.error
        return FakeStream(self.chunks, self.stop_reason)


def make_brain(chunks, tmp_path, config=None, **kw):
    api = FakeMessages(chunks, **kw)
    client = SimpleNamespace(beta=SimpleNamespace(messages=api))
    memory = Memory(tmp_path / "m.json")
    return Brain(config or Config(), memory, client=client, moods=MOODS), api


def test_streams_sentence_by_sentence_with_mood(tmp_path):
    brain, api = make_brain(["[la", "ugh] Because light ", "attracts bugs! Pi is 3.", "14, by the way."], tmp_path)
    heard = []
    answer = brain.ask("why dark mode?", on_sentence=lambda s, m: heard.append((s, m)))
    assert heard == [("Because light attracts bugs!", "laugh"), ("Pi is 3.14, by the way.", "laugh")]
    assert answer.spoken and answer.mood == "laugh"
    assert answer.text == "Because light attracts bugs! Pi is 3.14, by the way."


def test_request_shape_and_history(tmp_path):
    brain, api = make_brain(["[happy] Paris."], tmp_path)
    brain.memory.add_fact("Sri loves dosa")
    brain.ask("capital of france?")
    brain.ask("and germany?")
    call = api.calls[1]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "low"}
    assert call["fallbacks"] == "default"
    assert "speed" not in call
    assert [m["role"] for m in call["messages"]] == ["user", "assistant", "user"]
    assert "Sri loves dosa" in call["system"] and "laugh" in call["system"]


def test_unknown_mood_tag_and_no_tag(tmp_path):
    brain, _ = make_brain(["[grumpy] Fine."], tmp_path)
    assert brain.ask("hi").mood == "happy"
    brain, _ = make_brain(["Hello there."], tmp_path)
    answer = brain.ask("hi")
    assert (answer.text, answer.mood) == ("Hello there.", "happy")


def test_refusal(tmp_path):
    brain, _ = make_brain([], tmp_path, stop_reason="refusal")
    assert brain.ask("something").text == "Sorry, I can't help with that one."
    assert brain.history == []


def test_fast_mode_falls_back_when_rejected(tmp_path):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.BadRequestError("no fast mode", response=httpx.Response(400, request=request), body=None)
    brain, api = make_brain(["[happy] Hi."], tmp_path, config=Config(fast_mode=True), error=error)
    assert brain.ask("hi").text == "Hi."
    assert api.calls[0]["speed"] == "fast" and "fast-mode-2026-02-01" in api.calls[0]["betas"]
    assert "speed" not in api.calls[1]


def test_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "API key" in Brain(Config()).ask("hello?").text


def test_learns_facts_in_background(tmp_path):
    brain, _ = make_brain([], tmp_path)
    facts = "Sri has a dog named Bruno\nSri works at TCS"
    created = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=facts)])
    brain._client.messages = SimpleNamespace(create=lambda **kw: created)
    brain._learn("my dog Bruno hates my job at TCS")
    assert brain.memory.facts == ["Sri has a dog named Bruno", "Sri works at TCS"]


def test_learning_skips_plain_questions(tmp_path):
    brain, _ = make_brain([], tmp_path)
    brain._client.messages = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(AssertionError))
    brain.learn_in_background("what is the capital of peru")  # no "I"/"my": no API call
