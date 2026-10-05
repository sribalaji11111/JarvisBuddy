import pytest

from jarvisbuddy.assistant import strip_wake_word


def say(a, text):
    return a.respond(text).text


def test_time_and_date(jarvis):
    assert say(jarvis, "what time is it") == "It's 2:30 PM."
    assert say(jarvis, "What's the date today?") == "Today is Monday, 5 October 2026."


def test_replies_carry_a_face(jarvis):
    assert jarvis.respond("tell me a joke").mood == "laugh"
    assert jarvis.respond("goodbye").mood == "sleepy"
    assert jarvis.respond("open nonexistentthing").mood == "confused"


@pytest.mark.parametrize("phrase,app", [
    ("open notepad", "notepad"),
    ("please open the calculator", "calculator"),
    ("launch VS Code", "vs code"),
    ("start chrome app", "chrome"),
])
def test_open_apps(jarvis, phrase, app):
    assert say(jarvis, phrase) == f"Opening {app}."
    assert jarvis.actions.apps == [app]
    assert jarvis.memory.favorite_apps() == [app]


def test_unknown_app(jarvis):
    assert "couldn't find" in say(jarvis, "open nonexistentthing")


def test_open_websites(jarvis):
    say(jarvis, "open youtube")
    say(jarvis, "open example.com")
    assert jarvis.actions.urls == ["https://www.youtube.com", "https://example.com"]
    assert jarvis.actions.apps == []


@pytest.mark.parametrize("phrase,song", [
    ("play believer", "believer"),
    ("play the song shape of you on youtube", "shape of you"),
    ("play arijit singh songs", "arijit singh songs"),
    ("youtube lofi beats", "lofi beats"),
])
def test_play_songs(jarvis, phrase, song):
    assert say(jarvis, phrase).startswith(f"Playing {song}")
    assert jarvis.actions.songs == [song]


def test_play_music_uses_favorite_song(jarvis):
    for _ in range(2):
        say(jarvis, "play believer")
    say(jarvis, "play some music")
    assert jarvis.actions.songs[-1] == "believer"


@pytest.mark.parametrize("phrase,url", [
    ("search for python tutorials", "https://www.google.com/search?q=python+tutorials"),
    ("google weather in chennai", "https://www.google.com/search?q=weather+in+chennai"),
    ("search youtube for cats", "https://www.youtube.com/results?search_query=cats"),
    ("search for cats on youtube", "https://www.youtube.com/results?search_query=cats"),
])
def test_web_search(jarvis, phrase, url):
    say(jarvis, phrase)
    assert jarvis.actions.urls == [url]


def test_timer_speaks_when_done(jarvis):
    assert say(jarvis, "set a timer for 5 minutes") == "Okay! I'll let you know in 5 minutes."
    seconds, callback = jarvis.actions.timers[0]
    assert seconds == 300
    callback()
    assert jarvis.spoken == ["Ding ding! Your 5 minutes timer is done."]
    assert jarvis.ui.moods[-1] == "surprised"


def test_reminder(jarvis):
    say(jarvis, "remind me in 1 hour to call mom")
    seconds, callback = jarvis.actions.timers[0]
    callback()
    assert seconds == 3600 and jarvis.spoken == ["Ding ding! Reminder: call mom."]


def test_notes_round_trip(jarvis):
    assert say(jarvis, "read my notes") == "You don't have any notes yet."
    say(jarvis, "take a note buy milk")
    say(jarvis, "note down the meeting is at 5")
    assert say(jarvis, "read my notes") == "Your latest notes: buy milk. the meeting is at 5."


def test_system_and_lock(jarvis):
    assert say(jarvis, "battery") == (
        "CPU is at 12 percent and memory at 46 percent. Battery is 80 percent, and charging."
    )
    say(jarvis, "lock my laptop")
    assert jarvis.actions.locked


def test_goodbye_ends_session(jarvis):
    assert jarvis.respond("goodbye").end_session
    assert not jarvis.respond("hello").end_session


def test_unknown_questions_stream_from_the_brain(jarvis):
    reply = jarvis.handle("why is the sky blue?")
    assert reply.spoken and reply.mood == "laugh"
    assert jarvis.spoken == ["Brain answer one.", "Brain answer two."]  # spoken once, as it streamed
    assert jarvis.ui.moods[:2] == ["thinking", "laugh"]
    assert jarvis.brain.learned == ["why is the sky blue?"]
    # Commands never reach the brain.
    say(jarvis, "open notepad")
    assert jarvis.brain.asked == ["why is the sky blue?"]


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
        "Good afternoon Sri! How can I help?",
        "I'm Jarvis, your tiny robot buddy!",
        "Bye bye Sri! Call me when you need me.",
    ]


def test_voice_loop_with_wake_word(jarvis):
    heard = iter(["random chatter", "hey jarvis", "what time is it", "jarvis goodbye"])

    class FakeListener:
        def listen(self, timeout=None):
            return next(heard)

    jarvis.run_voice(FakeListener())
    assert jarvis.spoken[1:] == ["Yes?", "It's 2:30 PM.", "Bye bye Sri! Call me when you need me."]
