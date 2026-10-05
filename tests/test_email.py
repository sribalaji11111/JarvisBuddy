import pytest

from jarvisbuddy.mailer import spoken_to_email, subject_from


def say(a, text):
    return a.respond(text).text


@pytest.mark.parametrize("spoken,address", [
    ("sri at gmail dot com", "sri@gmail.com"),
    ("sri dot balaji at gmail dot com", "sri.balaji@gmail.com"),
    ("john underscore doe at the rate yahoo dot co dot in", "john_doe@yahoo.co.in"),
    ("mom@gmail.com", "mom@gmail.com"),
    ("mom", None),
])
def test_spoken_to_email(spoken, address):
    assert spoken_to_email(spoken) == address


def test_subject():
    assert subject_from("running late, see you at 6") == "Running late, see you at 6"
    assert subject_from("one two three four five six seven eight") == "One two three four five six seven..."


def test_email_in_one_go_waits_for_yes(jarvis):
    jarvis.memory.save_contact("mom", "mom@example.com")
    assert say(jarvis, "send an email to mom saying I'll be home by 7") == (
        "Here's your email to mom: I'll be home by 7. Should I send it?"
    )
    assert jarvis.ctx.mailer.sent == []  # nothing sent before the yes
    assert say(jarvis, "yes send it") == "Whoosh! Email sent to mom."
    assert jarvis.ctx.mailer.sent == [("mom@example.com", "I'll be home by 7", "I'll be home by 7")]


def test_email_step_by_step(jarvis):
    assert say(jarvis, "send an email") == "Sure! Who should I send it to?"
    assert "don't have an email address for bob" in say(jarvis, "bob")
    assert say(jarvis, "bob at gmail dot com") == "What should the email say?"
    assert "Should I send it?" in say(jarvis, "the party is on saturday")
    say(jarvis, "yes")
    assert jarvis.ctx.mailer.sent[0][0] == "bob@gmail.com"
    assert jarvis.ctx.mailer.sent[0][2] == "The party is on saturday"


@pytest.mark.parametrize("answer", ["no", "wait", "change it", "cancel", "what time is it"])
def test_anything_but_yes_cancels(jarvis, answer):
    say(jarvis, "send email to test at example dot com saying hi")
    assert say(jarvis, answer) == "Okay, I won't send it."
    assert jarvis.ctx.mailer.sent == []
    assert jarvis.ctx.pending is None


def test_voice_mode_drops_confirmation_on_silence(jarvis):
    heard = iter(["jarvis send email to a at b dot com saying hello", None, "jarvis goodbye"])

    class FakeListener:
        def listen(self, timeout=None):
            return next(heard)

    jarvis.run_voice(FakeListener())
    assert jarvis.ctx.mailer.sent == []
    assert jarvis.spoken[-1].startswith("Bye bye")


def test_email_not_configured(jarvis):
    jarvis.ctx.mailer.ready = False
    assert "isn't set up" in say(jarvis, "send an email to mom saying hi")


def test_save_contact(jarvis):
    assert say(jarvis, "save contact priya as priya at gmail dot com") == "Saved priya as priya@gmail.com."
    assert jarvis.memory.contact("Priya") == "priya@gmail.com"
