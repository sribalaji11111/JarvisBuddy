from datetime import date

from jarvisbuddy.memory import DAILY_QUESTIONS, Memory


def say(a, text):
    return a.respond(text).text


def test_learns_from_what_you_say(jarvis):
    say(jarvis, "my favorite color is blue")
    say(jarvis, "I love biryani")
    say(jarvis, "remember that my sister's name is Priya")
    assert jarvis.memory.facts == [
        "Sri's favorite color is blue",
        "Sri loves biryani",
        "Sri's sister's name is priya",
    ]
    assert "Sri loves biryani" in say(jarvis, "what do you know about me")


def test_memory_survives_restart(jarvis):
    say(jarvis, "my name is balaji")
    say(jarvis, "i like cricket")
    again = Memory(jarvis.memory.path)
    assert again.name == "Balaji"
    assert again.facts == ["Balaji likes cricket"]
    assert say(jarvis, "hello").count("Balaji") == 1


def test_forget(jarvis):
    say(jarvis, "i like cricket")
    assert say(jarvis, "forget about cricket") == "Poof! Forgotten."
    assert jarvis.memory.facts == []


def test_one_new_question_per_day(tmp_path):
    m = Memory(tmp_path / "m.json")
    q1 = m.daily_question(date(2026, 10, 5))
    assert q1 == DAILY_QUESTIONS[0]
    assert m.daily_question(date(2026, 10, 5)) is None  # only once a day
    m.answer(q1, "dosa", "Sri")
    assert m.daily_question(date(2026, 10, 6)) == DAILY_QUESTIONS[1]


def test_greeting_asks_question_of_the_day(jarvis):
    jarvis.memory.data["last_question_day"] = None
    jarvis.greet()
    assert jarvis.spoken[0].endswith("Question of the day: what's your favorite food?")
    assert say(jarvis, "my favourite food is masala dosa") == "Ooh, masala dosa! Saved to my memory."
    assert "Sri's favorite food is masala dosa" in jarvis.memory.facts
    assert "food" in jarvis.memory.data["answered"]


def test_question_of_the_day_can_be_ignored(jarvis):
    jarvis.memory.data["last_question_day"] = None
    jarvis.greet()
    assert say(jarvis, "what time is it") == "It's 2:30 PM."
    assert jarvis.memory.data["answered"] == []


def test_profile_mentions_habits(jarvis):
    say(jarvis, "open chrome")
    say(jarvis, "play believer")
    say(jarvis, "i like cricket")
    profile = jarvis.memory.profile("Sri")
    assert "Sri likes cricket" in profile
    assert "often opens: chrome" in profile
    assert "often plays: believer" in profile
