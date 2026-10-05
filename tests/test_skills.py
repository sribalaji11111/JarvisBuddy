from datetime import datetime

import pytest

from jarvisbuddy import skills
from jarvisbuddy.assistant import Assistant, strip_wake_word
from jarvisbuddy.config import Config


class FakeActions:
    def __init__(self):
        self.urls, self.apps, self.timers, self.locked = [], [], [], False

    def open_url(self, url):
        self.urls.append(url)

    def open_app(self, name):
        self.apps.append(name)
        return name != "nonexistentthing"

    def lock_screen(self):
        self.locked = True
        return True

    def schedule(self, seconds, callback):
        self.timers.append((seconds, callback))

    def system_status(self):
        return {"cpu": 12.3, "memory": 45.6, "battery": 80.0, "plugged": 1.0}


class FakeBrain:
    def __init__(self):
        self.asked = []

    def ask(self, text):
        self.asked.append(text)
        return "brain answer"


@pytest.fixture
def jarvis(tmp_path):
    config = Config(notes_file=tmp_path / "notes.txt")
    spoken = []
    a = Assistant(config, speak=spoken.append, actions=FakeActions(), brain=FakeBrain())
    a.ctx.now = lambda: datetime(2026, 10, 5, 14, 30)
    a.spoken = spoken
    return a


def say(a, text):
    return a.respond(text).text


def test_time_and_date(jarvis):
    assert say(jarvis, "what time is it") == "It's 2:30 PM."
    assert say(jarvis, "What's the date today?") == "Today is Monday, 5 October 2026."


def test_greeting_uses_name_and_time_of_day(jarvis):
    assert say(jarvis, "hello") == "Good afternoon Sri. How can I help?"


@pytest.mark.parametrize("phrase,app", [
    ("open notepad", "notepad"),
    ("please open the calculator", "calculator"),
    ("launch VS Code", "vs code"),
    ("start chrome app", "chrome"),
])
def test_open_apps(jarvis, phrase, app):
    assert say(jarvis, phrase) == f"Opening {app}."
    assert jarvis.actions.apps == [app]


def test_unknown_app(jarvis):
    assert "couldn't find" in say(jarvis, "open nonexistentthing")


def test_open_websites(jarvis):
    say(jarvis, "open youtube")
    say(jarvis, "open example.com")
    assert jarvis.actions.urls == ["https://www.youtube.com", "https://example.com"]
    assert jarvis.actions.apps == []


@pytest.mark.parametrize("phrase,url", [
    ("search for python tutorials", "https://www.google.com/search?q=python+tutorials"),
    ("google weather in chennai", "https://www.google.com/search?q=weather+in+chennai"),
    ("play lofi music on youtube", "https://www.youtube.com/results?search_query=lofi+music"),
    ("search youtube for cats", "https://www.youtube.com/results?search_query=cats"),
    ("search for cats on youtube", "https://www.youtube.com/results?search_query=cats"),
])
def test_web_search(jarvis, phrase, url):
    say(jarvis, phrase)
    assert jarvis.actions.urls == [url]


def test_timer_speaks_when_done(jarvis):
    assert say(jarvis, "set a timer for 5 minutes") == "Okay, I'll let you know in 5 minutes."
    seconds, callback = jarvis.actions.timers[0]
    assert seconds == 300
    callback()
    assert jarvis.spoken == ["Your 5 minutes timer is done."]


def test_reminder(jarvis):
    say(jarvis, "remind me in 1 hour to call mom")
    seconds, callback = jarvis.actions.timers[0]
    callback()
    assert seconds == 3600 and jarvis.spoken == ["Reminder: call mom."]


def test_notes_round_trip(jarvis):
    assert say(jarvis, "read my notes") == "You don't have any notes yet."
    say(jarvis, "take a note buy milk")
    say(jarvis, "remember that the meeting is at 5")
    assert say(jarvis, "read my notes") == "Your latest notes: buy milk. the meeting is at 5."


def test_system_and_lock(jarvis):
    assert say(jarvis, "battery") == (
        "CPU is at 12 percent and memory at 46 percent. Battery is 80 percent, and charging."
    )
    say(jarvis, "lock my computer")
    assert jarvis.actions.locked


def test_goodbye_ends_session(jarvis):
    assert jarvis.respond("goodbye").end_session
    assert not jarvis.respond("hello").end_session


def test_unknown_questions_go_to_the_brain(jarvis):
    assert say(jarvis, "who won the world cup in 2022?") == "brain answer"
    assert jarvis.brain.asked == ["who won the world cup in 2022?"]
    # Commands never reach the brain.
    say(jarvis, "open notepad")
    assert len(jarvis.brain.asked) == 1


@pytest.mark.parametrize("heard,expected", [
    ("hey jarvis open notepad", "open notepad"),
    ("Jarvis, what time is it", "what time is it"),
    ("jarvis", ""),
    ("ok so Hey Jarvis tell me a joke", "tell me a joke"),
    ("open notepad", None),
    ("jarvisbuddy rocks", None),
])
def test_strip_wake_word(heard, expected):
    assert strip_wake_word(heard, ("jarvis", "hey jarvis")) == expected


def test_text_mode_loop(jarvis):
    inputs = iter(["what's your name", "", "bye"])
    jarvis.run_text(read=lambda prompt: next(inputs))
    assert jarvis.spoken == [
        "Good afternoon Sri. How can I help?",
        "I'm Jarvis, your desktop assistant.",
        "Goodbye Sri. Call me when you need me.",
    ]


def test_voice_loop_with_wake_word(jarvis):
    heard = iter(["random chatter", "hey jarvis", "what time is it", "jarvis goodbye"])

    class FakeListener:
        def listen(self, timeout=None):
            return next(heard)

    jarvis.run_voice(FakeListener())
    assert jarvis.spoken[1:] == ["Yes?", "It's 2:30 PM.", "Goodbye Sri. Call me when you need me."]
