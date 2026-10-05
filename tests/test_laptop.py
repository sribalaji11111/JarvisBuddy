import pytest

from jarvisbuddy import learn


def say(a, text):
    return a.respond(text).text


@pytest.mark.parametrize("phrase,key", [
    ("pause", "play_pause"), ("stop the music", "play_pause"), ("resume", "play_pause"),
    ("next song", "next"), ("skip", "next"), ("previous song", "previous"),
    ("volume up", "volume_up"), ("quieter", "volume_down"), ("mute", "mute"),
])
def test_media_keys(jarvis, phrase, key):
    say(jarvis, phrase)
    assert jarvis.actions.keys[0][0] == key


def test_search_songs_then_play_number(jarvis):
    assert say(jarvis, "play number 2").startswith("Search for songs first")
    reply = say(jarvis, "search songs by arijit singh")
    assert reply.startswith("I found 1: arijit singh song 1. 2: arijit singh song 2")
    assert say(jarvis, "play number two") == "Playing arijit singh song 2!"
    assert jarvis.actions.urls == ["https://youtu.be/2"]


def test_volume_brightness_screenshot_type(jarvis):
    assert say(jarvis, "set volume to 40") == "Volume 40 percent."
    assert jarvis.actions.volume == 40
    assert say(jarvis, "brightness 70") == "Brightness 70 percent."
    assert "Screenshot saved" in say(jarvis, "take a screenshot")
    say(jarvis, "type hello world")
    assert jarvis.actions.typed == "hello world"


def test_weather(jarvis):
    assert say(jarvis, "what's the weather in chennai") == "Weather in chennai: Sunny, 31°C, wind 10km/h."
    assert say(jarvis, "weather").startswith("Weather: Sunny")


def test_close_app_asks_first(jarvis):
    assert say(jarvis, "close notepad") == "Close notepad? Unsaved work may be lost."
    assert not hasattr(jarvis.actions, "closed")
    assert say(jarvis, "yes") == "Closed notepad."
    assert jarvis.actions.closed == "notepad"


def test_shutdown_asks_first_and_can_be_cancelled(jarvis):
    assert say(jarvis, "shut down the laptop") == "Shut down the laptop?"
    assert say(jarvis, "no") == "Okay, cancelled."
    assert not hasattr(jarvis.actions, "shut")
    say(jarvis, "restart")
    say(jarvis, "yes")
    assert jarvis.actions.shut == "restart"
    say(jarvis, "cancel shutdown")
    assert jarvis.actions.shut is None


def test_conversations_are_logged_and_learned_daily(jarvis):
    jarvis.handle("hello")
    jarvis.handle("what time is it")
    messages = jarvis.memory.day_messages(jarvis.ctx.now().date().today())
    assert ("user", "what time is it") in messages and ("assistant", "It's 2:30 PM.") in messages

    jarvis.brain.extract_facts = lambda text, source: ["Sri says hello a lot"]
    jarvis.brain.available = True
    result = learn.daily(jarvis.memory, jarvis.brain, "Sri", "Jarvis")
    assert result.startswith("I learned 1 new thing")
    data = jarvis.memory.path.parent
    assert "Sri says hello a lot" in (data / "diary").glob("*.md").__next__().read_text()
    assert '"content": "what time is it"' in (data / "dataset.jsonl").read_text()


def test_follow_up_without_wake_word(jarvis):
    heard = iter(["jarvis what time is it", "tell me a joke", None, "random chatter", "jarvis bye"])

    class FakeListener:
        def listen(self, timeout=None):
            return next(heard)

    jarvis.run_voice(FakeListener())
    assert jarvis.spoken[1] == "It's 2:30 PM."
    assert len(jarvis.spoken) == 4  # greeting, time, joke (no wake word needed), bye; chatter ignored


def test_wake_word_aliases(jarvis):
    from jarvisbuddy.assistant import strip_wake_word

    assert strip_wake_word("javis open notepad", jarvis.config.wake_words) == "open notepad"
