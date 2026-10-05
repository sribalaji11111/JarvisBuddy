"""Built-in commands. Each skill matches a spoken phrase and returns what Jarvis should say,
plus the face Jarvis should make while saying it. These run instantly, with no internet."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote_plus

from .actions import Actions
from .config import Config
from .mailer import Mailer, spoken_to_email, subject_from
from .memory import DailyQuestion, Memory

# Faces the EVE display knows how to make. Claude picks from these too.
MOODS = (
    "neutral", "happy", "laugh", "love", "wink", "surprised",
    "sad", "angry", "confused", "thinking", "sleepy", "excited",
)

WEBSITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "claude": "https://claude.ai",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in",
    "wikipedia": "https://www.wikipedia.org",
}

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "I would tell you a UDP joke, but you might not get it.",
    "There are 10 kinds of people: those who understand binary and those who don't.",
    "Why did the developer go broke? Because he used up all his cache!",
    "A SQL query walks into a bar, walks up to two tables and asks: can I join you?",
    "I tried to catch some fog earlier. I mist.",
    "Why was the robot so tired? It had a hard drive!",
    "What do you call a robot who always takes the long way around? R2 Detour!",
    "I'm reading a book about anti-gravity. I can't put it down!",
    "Why did the computer go to the doctor? It had a virus. Don't worry, I'm vaccinated. Mostly.",
]

YES = re.compile(r"(?:(?:yes|yeah|yep|yup|sure|ok|okay|send it|send|go ahead|do it|confirm|correct|right|"
                 r"please|absolutely|of course|jarvis)\s*)+")


@dataclass
class Reply:
    text: str
    mood: str = "happy"
    end_session: bool = False
    spoken: bool = False  # True when the text was already spoken while streaming


PendingHandler = Callable[[str, "Context"], Reply]


@dataclass
class Context:
    config: Config
    actions: Actions
    memory: Memory
    speak: Callable[[str, str], None]
    mailer: Mailer | None = None
    brain: Any = None
    now: Callable[[], datetime] = datetime.now
    # When Jarvis asks a follow-up question, the next thing you say goes here first.
    pending: PendingHandler | None = None
    draft: dict = field(default_factory=dict)
    song_results: list[tuple[str, str]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.memory.name or self.config.user_name


Handler = Callable[[re.Match[str], Context], Reply]
_SKILLS: list[tuple[re.Pattern[str], Handler]] = []


def skill(*patterns: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        for pattern in patterns:
            _SKILLS.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn

    return register


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s.:'@+-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    # Politeness doesn't change the command.
    text = re.sub(r"^(ok |okay |hey |so )?(please |can you |could you |would you |will you )+", "", text)
    text = re.sub(r" please$", "", text)
    return text


def handle(text: str, ctx: Context) -> Reply | None:
    """Run the follow-up or first matching skill, or return None so Claude can answer."""
    if ctx.pending is not None:
        pending, ctx.pending = ctx.pending, None
        return pending(text, ctx)
    found = _match(normalize(text))
    return found[0](found[1], ctx) if found else None


def _match(cleaned: str) -> tuple[Handler, re.Match[str]] | None:
    for pattern, fn in _SKILLS:
        match = pattern.fullmatch(cleaned)
        if match:
            return fn, match
    return None


def greeting(ctx: Context) -> Reply:
    hour = ctx.now().hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    text = f"Good {part} {ctx.name}! How can I help?"
    if ctx.memory.mark_day(ctx.now().date()) and len(ctx.memory.data["days_used"]) > 1:
        text = f"Good {part} {ctx.name}! So happy to see you again!"
    q = ctx.memory.daily_question(ctx.now().date())
    if q:
        text += f" Question of the day: {q.question}"
        ctx.pending = _daily_answer(q)
    return Reply(text, mood="excited")


def _daily_answer(q: DailyQuestion) -> PendingHandler:
    def answered(text: str, ctx: Context) -> Reply:
        if normalize(text) in ("skip", "pass", "no", "not now", "never mind", "nevermind"):
            return Reply("No problem, I'll ask you something else another day.", mood="wink")
        found = _match(normalize(text))
        if found and found[0] not in _LEARNING_SKILLS:
            return found[0](found[1], ctx)  # they gave a command instead; ask again another day
        ctx.memory.answer(q, _clean_answer(text), ctx.name)
        return Reply(f"Ooh, {_clean_answer(text)}! Saved to my memory.", mood="love")

    return answered


def _clean_answer(text: str) -> str:
    t = normalize(text)
    t = re.sub(r"^(i think |well |um |uh |hmm )+", "", t)
    t = re.sub(r"^(my favou?rite \w+ is |i (really )?(like|love|prefer|do|follow|live in) |it's |it is |i'm a |i am a )", "", t)
    return t


def confirm(ctx: Context, question: str, action: Callable[[], Reply], mood: str = "thinking") -> Reply:
    """Ask a yes/no question; `action` runs only on a clear yes."""
    def answered(text: str, ctx: Context) -> Reply:
        if YES.fullmatch(normalize(text)):
            return action()
        return Reply("Okay, cancelled.", mood="neutral")

    ctx.pending = answered
    return Reply(question, mood=mood)


# --- conversation -----------------------------------------------------------


@skill(r"(goodbye|bye|bye bye|exit|quit|go to sleep|sleep|shut down jarvis|that's all|see you)( jarvis)?")
def goodbye(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(f"Bye bye {ctx.name}! Call me when you need me.", mood="sleepy", end_session=True)


@skill(r"(hi|hello|hey|yo|good (morning|afternoon|evening))( there)?( jarvis)?")
def greet(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(random.choice([f"Hello {ctx.name}!", f"Hi hi {ctx.name}!", f"Hey {ctx.name}! I missed you."]),
                 mood="happy")


@skill(r"how are you( doing)?( today)?|how's it going|what's up")
def how_are_you(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(random.choice([
        "All systems sparkly! Thanks for asking.",
        "Fantastic! My circuits are doing a happy dance.",
        "Great! Though I did dream about electric sheep again.",
    ]), mood="excited")


@skill(r"(what is|what's) your name|who are you")
def who_are_you(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(f"I'm {ctx.config.assistant_name}, your tiny robot buddy!", mood="wink")


@skill(r"(thanks|thank you|thank you so much|thanks a lot)( jarvis)?")
def thanks(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(random.choice(["You're welcome!", "Anytime!", "Happy to help, beep boop!"]), mood="love")


@skill(r"(i love you|you're (the best|awesome|cute|amazing)|good (job|bot|robot))( jarvis)?")
def compliment(m: re.Match[str], ctx: Context) -> Reply:
    return Reply("Aww, stop it! You're making my circuits blush.", mood="love")


@skill(r"(you're|you are) (stupid|dumb|useless|bad)|bad (bot|robot)")
def insult(m: re.Match[str], ctx: Context) -> Reply:
    return Reply("Hmph! I'm still learning, okay? Be nice to the robot.", mood="angry")


@skill(r"(what can you do|help|what are your (skills|commands))")
def help_skill(m: re.Match[str], ctx: Context) -> Reply:
    extra = " And you can ask me anything else!" if ctx.config.ai_enabled else ""
    return Reply(
        "I can play songs on YouTube, open apps and websites, search Google, send emails, "
        "tell the time, set timers, take notes, check your laptop, and tell terrible jokes. "
        "I also learn a little about you every day." + extra,
        mood="excited",
    )


@skill(r"(tell me )?(a |another )?joke|make me laugh|say something funny")
def joke(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(random.choice(JOKES), mood="laugh")


@skill(r"sing( me)?( a song)?( for me)?|sing something")
def sing(m: re.Match[str], ctx: Context) -> Reply:
    return Reply("La la la! Beep boop bee doo! I'm a tiny robot and I sing for you!", mood="excited")


# --- time -------------------------------------------------------------------


@skill(r"(what time is it|what's the time|what is the time|tell me the time|time)( now)?")
def time_skill(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(f"It's {ctx.now().strftime('%I:%M %p').lstrip('0')}.", mood="happy")


@skill(r"(what's|what is) (the |today's )?date( today)?|what day is (it|today)|today's date|date")
def date_skill(m: re.Match[str], ctx: Context) -> Reply:
    now = ctx.now()
    return Reply(f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}.", mood="happy")


_UNITS = {"second": 1, "minute": 60, "hour": 3600}


@skill(r"(set (a |an )?)?timer (for )?(?P<n>\d+) (?P<unit>second|minute|hour)s?",
       r"remind me in (?P<n>\d+) (?P<unit>second|minute|hour)s?( to (?P<what>.+))?")
def timer(m: re.Match[str], ctx: Context) -> Reply:
    n, unit = int(m["n"]), m["unit"]
    what = m.groupdict().get("what")
    label = f"{n} {unit}{'s' if n != 1 else ''}"
    message = f"Ding ding! Reminder: {what}." if what else f"Ding ding! Your {label} timer is done."
    ctx.actions.schedule(n * _UNITS[unit], lambda: ctx.speak(message, "surprised"))
    return Reply(f"Okay! I'll let you know in {label}.", mood="wink")


# --- music and web ----------------------------------------------------------

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


@skill(r"(pause|stop)( the)?( music| song| video)?|(resume|continue|unpause)( the)?( music| song| video)?")
def pause_resume(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.media_key("play_pause")
    return Reply("Okay!", mood="wink")


@skill(r"(next|skip)( song| track| video| one)?|play (the )?next( song)?")
def next_song(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.media_key("next")
    return Reply("Next one!", mood="excited")


@skill(r"(previous|go back|last)( song| track| video| one)?|play (the )?previous( song)?")
def previous_song(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.media_key("previous")
    return Reply("Going back!", mood="happy")


@skill(r"play (number |the )?(?P<n>[1-5]|one|two|three|four|five|first|second|third|fourth|fifth)( one| song)?")
def play_number(m: re.Match[str], ctx: Context) -> Reply:
    if not ctx.song_results:
        return Reply("Search for songs first, like 'search songs by Arijit Singh', then pick a number.",
                     mood="confused")
    n = int(m["n"]) if m["n"].isdigit() else _NUMBERS[m["n"]]
    if n > len(ctx.song_results):
        return Reply(f"Pick a number from 1 to {len(ctx.song_results)}.", mood="confused")
    title, url = ctx.song_results[n - 1]
    ctx.actions.open_url(url)
    ctx.memory.record_song(title)
    return Reply(f"Playing {title}!", mood="excited")


@skill(r"(search|find|show me)( for)? (songs?|music) (by |of |from )?(?P<q>.+)",
       r"(search|find|show me)( for)? (?P<q>.+?) songs")
def search_songs(m: re.Match[str], ctx: Context) -> Reply:
    q = m["q"]
    ctx.song_results = ctx.actions.youtube_results(q, 5)
    if not ctx.song_results:
        ctx.actions.open_url(f"https://www.youtube.com/results?search_query={quote_plus(q)}")
        return Reply(f"Here are YouTube results for {q}.", mood="happy")
    names = ". ".join(f"{i}: {title}" for i, (title, _) in enumerate(ctx.song_results[:3], 1))
    return Reply(f"I found {names}. Say play number one, two or three.", mood="excited")



@skill(r"search (youtube )?(for )?(?P<q>.+?) on youtube", r"search youtube (for )?(?P<q>.+)")
def youtube_search(m: re.Match[str], ctx: Context) -> Reply:
    q = m["q"]
    ctx.actions.open_url(f"https://www.youtube.com/results?search_query={quote_plus(q)}")
    return Reply(f"Here's {q} on YouTube.", mood="happy")


@skill(r"play (the )?(song |music |video )?(?P<q>.+?)( song)?( on youtube)?", r"youtube (?P<q>.+)")
def play(m: re.Match[str], ctx: Context) -> Reply:
    q = m["q"]
    if q in ("some music", "music", "a song", "something", "my song", "my favorite song", "my favourite song"):
        q = (ctx.memory.favorite_songs(1) or ["lofi hip hop"])[0]
    ctx.actions.play_youtube(q)
    ctx.memory.record_song(q)
    return Reply(f"Playing {q}! Time to dance.", mood="excited")


@skill(r"(search|google|look up)( google)?( for)? (?P<q>.+)")
def google(m: re.Match[str], ctx: Context) -> Reply:
    q = m["q"]
    ctx.actions.open_url(f"https://www.google.com/search?q={quote_plus(q)}")
    return Reply(f"Searching Google for {q}.", mood="thinking")


# --- apps and the laptop ----------------------------------------------------


@skill(r"(open|launch|start|run) (?P<target>.+)")
def open_thing(m: re.Match[str], ctx: Context) -> Reply:
    target = re.sub(r"^(the |my |up )", "", m["target"]).removesuffix(" app")
    if target in WEBSITES:
        ctx.actions.open_url(WEBSITES[target])
        return Reply(f"Opening {target}.", mood="happy")
    if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", target):
        url = target if target.startswith("http") else f"https://{target}"
        ctx.actions.open_url(url)
        return Reply(f"Opening {target}.", mood="happy")
    if ctx.actions.open_app(target):
        ctx.memory.record_app(target)
        return Reply(f"Opening {target}.", mood="happy")
    return Reply(f"Hmm, I couldn't find an app called {target}.", mood="confused")


@skill(r"lock (my |the )?(computer|pc|laptop|screen)")
def lock(m: re.Match[str], ctx: Context) -> Reply:
    if ctx.actions.lock_screen():
        return Reply("Locking your laptop. Nobody gets past me!", mood="wink")
    return Reply("I can only lock the screen on Windows.", mood="sad")


@skill(r"(set )?(the )?volume (to )?(?P<n>\d{1,3})( percent| %)?")
def volume_set(m: re.Match[str], ctx: Context) -> Reply:
    level = min(100, int(m["n"]))
    ctx.actions.set_volume(level)
    return Reply(f"Volume {level} percent.", mood="happy")


@skill(r"volume up|louder|(turn|crank) (it |the volume )?up|(increase|raise)( the)? volume")
def volume_up(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.media_key("volume_up", 5)
    return Reply("Louder!", mood="excited")


@skill(r"volume down|quieter|softer|turn (it |the volume )?down|(decrease|lower|reduce)( the)? volume")
def volume_down(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.media_key("volume_down", 5)
    return Reply("Shh, quieter.", mood="wink")


@skill(r"(mute|unmute)( the)?( sound| volume| audio| laptop)?")
def mute(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.media_key("mute")
    return Reply("Done.", mood="neutral")


@skill(r"(set )?(the )?brightness (to )?(?P<n>\d{1,3})( percent| %)?")
def brightness(m: re.Match[str], ctx: Context) -> Reply:
    level = min(100, int(m["n"]))
    if ctx.actions.set_brightness(level):
        return Reply(f"Brightness {level} percent.", mood="happy")
    return Reply("I can't change the brightness on this screen.", mood="sad")


@skill(r"(take a |take )?screen ?shot")
def screenshot(m: re.Match[str], ctx: Context) -> Reply:
    if ctx.actions.screenshot():
        return Reply("Cheese! Screenshot saved in your Pictures folder.", mood="wink")
    return Reply("I couldn't take a screenshot. I need the pillow package.", mood="sad")


@skill(r"type (?P<text>.+)")
def type_text(m: re.Match[str], ctx: Context) -> Reply:
    if ctx.actions.type_text(m["text"]):
        return Reply("Typed!", mood="happy")
    return Reply("Typing needs the pyautogui package.", mood="sad")


@skill(r"(what's |what is |how's |how is )?(the )?weather( like)?( (in|at|for) (?P<city>.+?))?( today| now| outside)?")
def weather(m: re.Match[str], ctx: Context) -> Reply:
    city = m["city"] or ""
    report = ctx.actions.weather(city)
    if report is None:
        return Reply("I couldn't reach the weather service.", mood="sad")
    return Reply(f"Weather{' in ' + city if city else ''}: {report}.", mood="happy")


@skill(r"(close|quit|exit|kill) (the |my )?(?P<app>.+?)( app)?")
def close_app(m: re.Match[str], ctx: Context) -> Reply:
    app = m["app"]

    def close() -> Reply:
        if ctx.actions.close_app(app):
            return Reply(f"Closed {app}.", mood="happy")
        return Reply(f"{app} doesn't seem to be open.", mood="confused")

    return confirm(ctx, f"Close {app}? Unsaved work may be lost.", close)


@skill(r"(?P<what>shut ?down|turn off|power off|restart|reboot)( the| my)?( laptop| computer| pc)?")
def shutdown(m: re.Match[str], ctx: Context) -> Reply:
    restart = m["what"] in ("restart", "reboot")
    word = "Restart" if restart else "Shut down"

    def go() -> Reply:
        if ctx.actions.shutdown(restart):
            return Reply(f"{word} in one minute. Say cancel shutdown to stop it.", mood="sleepy")
        return Reply("I can only do that on Windows.", mood="sad")

    return confirm(ctx, f"{word} the laptop?", go, mood="surprised")


@skill(r"(cancel|abort|stop)( the)? (shut ?down|restart|reboot)")
def cancel_shutdown(m: re.Match[str], ctx: Context) -> Reply:
    ctx.actions.cancel_shutdown()
    return Reply("Phew! Cancelled.", mood="happy")


@skill(r"(system|computer|pc|laptop) (status|info|health)|battery( status| level)?|how('s| is) my (pc|computer|system|laptop)")
def system(m: re.Match[str], ctx: Context) -> Reply:
    status = ctx.actions.system_status()
    if status is None:
        return Reply("I need the psutil package to check your laptop. Run pip install psutil.", mood="sad")
    text = f"CPU is at {status['cpu']:.0f} percent and memory at {status['memory']:.0f} percent."
    mood = "happy"
    if "battery" in status:
        charging = "and charging" if status["plugged"] else "on battery"
        text += f" Battery is {status['battery']:.0f} percent, {charging}."
        if status["battery"] < 20 and not status["plugged"]:
            text += " I'm getting hungry, please plug me in!"
            mood = "sad"
    return Reply(text, mood=mood)


# --- email (always confirms before sending) ---------------------------------

_MAIL = r"(send|write|compose|draft) (an |a )?(e-?mail|mail|message on email)"


@skill(_MAIL + r" to (?P<to>.+?) (saying|that says|telling (him|her|them)|that|message|with) (?P<body>.+)",
       _MAIL + r" to (?P<to>.+)",
       _MAIL)
def email(m: re.Match[str], ctx: Context) -> Reply:
    ctx.draft = {"to": None, "name": None, "body": m.groupdict().get("body")}
    who = m.groupdict().get("to")
    if not who:
        ctx.pending = _email_recipient
        return Reply("Sure! Who should I send it to?", mood="thinking")
    return _email_recipient(who, ctx)


def _email_recipient(text: str, ctx: Context) -> Reply:
    who = normalize(text)
    if who in ("cancel", "never mind", "nevermind", "stop"):
        return _cancel_email(ctx)
    address = ctx.memory.contact(who) or spoken_to_email(who)
    if address is None:
        ctx.pending = _email_recipient
        return Reply(
            f"I don't have an email address for {who}. Say the address, like name at gmail dot com.",
            mood="confused",
        )
    ctx.draft.update(to=address, name=who if ctx.memory.contact(who) else address)
    if not ctx.draft.get("body"):
        ctx.pending = _email_body
        return Reply("What should the email say?", mood="thinking")
    return _email_confirm_prompt(ctx)


def _email_body(text: str, ctx: Context) -> Reply:
    if normalize(text) in ("cancel", "never mind", "nevermind", "stop"):
        return _cancel_email(ctx)
    ctx.draft["body"] = text.strip()
    return _email_confirm_prompt(ctx)


def _email_confirm_prompt(ctx: Context) -> Reply:
    body = ctx.draft["body"]
    body = body[:1].upper() + body[1:]
    ctx.draft["body"] = body
    ctx.pending = _email_confirm
    return Reply(f"Here's your email to {ctx.draft['name']}: {body}. Should I send it?", mood="thinking")


def _email_confirm(text: str, ctx: Context) -> Reply:
    if not YES.fullmatch(normalize(text)):
        return _cancel_email(ctx)
    draft, ctx.draft = ctx.draft, {}
    if ctx.mailer is None or not ctx.mailer.ready:
        ctx.actions.mail_draft(draft["to"], subject_from(draft["body"]), draft["body"])
        return Reply("I opened it in your mail app. Press Send there!", mood="wink")
    try:
        ctx.mailer.send(draft["to"], subject_from(draft["body"]), draft["body"])
    except Exception as e:
        return Reply(f"Uh oh, the email didn't send. The mail server said: {e}", mood="sad")
    return Reply(f"Whoosh! Email sent to {draft['name']}.", mood="excited")


def _cancel_email(ctx: Context) -> Reply:
    ctx.draft = {}
    return Reply("Okay, I won't send it.", mood="neutral")


@skill(r"(save|add) (a )?(new )?contact (?P<name>[\w ]+?) (as|email|with email|is|at) (?P<email>.+)")
def save_contact(m: re.Match[str], ctx: Context) -> Reply:
    address = spoken_to_email(m["email"])
    if not address:
        return Reply(f"Hmm, {m['email']} doesn't sound like an email address.", mood="confused")
    ctx.memory.save_contact(m["name"], address)
    return Reply(f"Saved {m['name']} as {address}.", mood="happy")


# --- notes ------------------------------------------------------------------


@skill(r"(take a note|make a note|note down|write down|add a note)( that)? (?P<note>.+)")
def take_note(m: re.Match[str], ctx: Context) -> Reply:
    path = ctx.config.notes_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ctx.now():%Y-%m-%d %H:%M}  {m['note']}\n")
    return Reply("Got it, I've noted that down.", mood="happy")


@skill(r"(read|show|what are) (me )?my notes")
def read_notes(m: re.Match[str], ctx: Context) -> Reply:
    path = ctx.config.notes_file
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    if not lines:
        return Reply("You don't have any notes yet.", mood="neutral")
    recent = [line.split("  ", 1)[-1] for line in lines[-5:]]
    return Reply("Your latest notes: " + ". ".join(recent) + ".", mood="happy")


# --- learning about you -----------------------------------------------------


@skill(r"(my name is|call me) (?P<name>[\w ]{1,30})")
def set_name(m: re.Match[str], ctx: Context) -> Reply:
    name = m["name"].strip().title()
    ctx.memory.set_name(name)
    return Reply(f"Nice to meet you, {name}! I'll remember that.", mood="love")


@skill(r"remember( that)? (?P<fact>.+)")
def remember(m: re.Match[str], ctx: Context) -> Reply:
    fact = _first_to_third_person(m["fact"], ctx.name)
    ctx.memory.add_fact(fact)
    return Reply("Got it! Saved to my memory.", mood="love")


@skill(r"my (?P<thing>(favou?rite |best |least favou?rite )?[\w ]{2,30}?) (is|are) (?P<value>.+)")
def my_thing(m: re.Match[str], ctx: Context) -> Reply:
    ctx.memory.add_fact(f"{ctx.name}'s {m['thing']} is {m['value']}")
    return Reply(f"{m['value'].capitalize()}! Got it, I'll remember that.", mood="love")


@skill(r"i (really |totally )?(?P<verb>like|love|enjoy|hate|dislike|prefer|adore) (?P<value>.+)")
def i_like(m: re.Match[str], ctx: Context) -> Reply:
    verb = m["verb"]
    ctx.memory.add_fact(f"{ctx.name} {verb}s {m['value']}")
    if verb in ("hate", "dislike"):
        return Reply(f"Noted, no {m['value']} for you!", mood="wink")
    return Reply(f"Ooh, {m['value']}! I'll remember that.", mood="love")


@skill(r"what do you (know|remember) about me|who am i|tell me about (me|myself)")
def about_me(m: re.Match[str], ctx: Context) -> Reply:
    facts = ctx.memory.facts
    if not facts:
        return Reply("Not much yet! Tell me things like 'my favorite food is dosa' and I'll remember.",
                     mood="confused")
    picks = random.sample(facts, min(4, len(facts)))
    return Reply("Let's see. " + ". ".join(picks) + ". See? I pay attention!", mood="wink")


@skill(r"forget (that |about )?(?P<what>.+)")
def forget(m: re.Match[str], ctx: Context) -> Reply:
    removed = ctx.memory.forget(m["what"])
    if not removed:
        return Reply(f"I didn't have anything about {m['what']}.", mood="confused")
    return Reply("Poof! Forgotten.", mood="wink")


@skill(r"learn from today|train yourself|daily (training|learning)|study today|update your memory")
def learn_today(m: re.Match[str], ctx: Context) -> Reply:
    from . import learn

    return Reply(learn.daily(ctx.memory, ctx.brain, ctx.name, ctx.config.assistant_name, ctx.now().date()),
                 mood="excited")


def _first_to_third_person(text: str, name: str) -> str:
    swaps = {"i": name, "i'm": f"{name} is", "am": "is", "my": f"{name}'s", "me": name, "mine": f"{name}'s"}
    return " ".join(swaps.get(w, w) for w in text.split())


# Replies to the daily question that sound like "my favorite food is dosa" count as answers.
_LEARNING_SKILLS = {my_thing, i_like, remember, set_name}
