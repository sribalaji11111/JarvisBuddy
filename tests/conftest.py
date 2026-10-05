from datetime import datetime

import pytest

from jarvisbuddy.assistant import Assistant
from jarvisbuddy.brain import Answer
from jarvisbuddy.config import Config
from jarvisbuddy.memory import Memory


class FakeActions:
    def __init__(self):
        self.urls, self.apps, self.songs, self.timers, self.locked = [], [], [], [], False

    def open_url(self, url):
        self.urls.append(url)

    def play_youtube(self, query):
        self.songs.append(query)
        return True

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
        self.asked, self.learned = [], []

    def ask(self, text, on_sentence=None):
        self.asked.append(text)
        if on_sentence:
            on_sentence("Brain answer one.", "laugh")
            on_sentence("Brain answer two.", "laugh")
            return Answer("Brain answer one. Brain answer two.", "laugh", spoken=True)
        return Answer("Brain answer.", "laugh")

    def learn_in_background(self, text):
        self.learned.append(text)


class FakeMailer:
    ready = True

    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))


class FakeUI:
    def __init__(self):
        self.moods, self.captions, self.statuses = [], [], []

    def set_mood(self, mood):
        self.moods.append(mood)

    def set_status(self, text):
        self.statuses.append(text)

    def set_caption(self, text):
        self.captions.append(text)

    def set_speaking(self, speaking):
        pass


@pytest.fixture
def jarvis(tmp_path):
    config = Config(data_dir=tmp_path)
    spoken = []
    memory = Memory(config.memory_file)
    memory.data["last_question_day"] = "2026-10-05"  # no daily question unless a test wants one
    a = Assistant(config, speak=spoken.append, ui=FakeUI(), actions=FakeActions(), memory=memory,
                  brain=FakeBrain(), mailer=FakeMailer())
    a.ctx.now = lambda: datetime(2026, 10, 5, 14, 30)
    a.spoken = spoken
    return a
