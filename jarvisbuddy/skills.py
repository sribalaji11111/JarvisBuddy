"""Built-in commands. Each skill matches a spoken phrase and returns what Jarvis should say."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from urllib.parse import quote_plus

from .actions import WINDOWS_APPS, Actions
from .config import Config

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
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in",
    "wikipedia": "https://www.wikipedia.org",
}

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I would tell you a UDP joke, but you might not get it.",
    "There are 10 kinds of people: those who understand binary and those who don't.",
    "Why did the developer go broke? Because he used up all his cache.",
    "A SQL query walks into a bar, walks up to two tables and asks: can I join you?",
]


@dataclass
class Reply:
    text: str
    end_session: bool = False


@dataclass
class Context:
    config: Config
    actions: Actions
    speak: Callable[[str], None]
    now: Callable[[], datetime] = datetime.now


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
    text = re.sub(r"[^\w\s.:'-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    # Politeness doesn't change the command.
    text = re.sub(r"^(please |can you |could you |would you |will you )+", "", text)
    text = re.sub(r" please$", "", text)
    return text


def handle(text: str, ctx: Context) -> Reply | None:
    """Run the first matching skill, or return None so the AI brain can answer."""
    cleaned = normalize(text)
    for pattern, fn in _SKILLS:
        match = pattern.fullmatch(cleaned)
        if match:
            return fn(match, ctx)
    return None


# --- conversation -----------------------------------------------------------


@skill(r"(goodbye|bye|exit|quit|stop|go to sleep|sleep|shut up|that's all)( jarvis)?")
def goodbye(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(f"Goodbye {ctx.config.user_name}. Call me when you need me.", end_session=True)


@skill(r"(hi|hello|hey|good (morning|afternoon|evening))( there)?( jarvis)?")
def greet(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(greeting(ctx))


def greeting(ctx: Context) -> str:
    hour = ctx.now().hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    return f"Good {part} {ctx.config.user_name}. How can I help?"


@skill(r"how are you( doing)?( today)?")
def how_are_you(m: re.Match[str], ctx: Context) -> Reply:
    return Reply("All systems running smoothly. Thanks for asking!")


@skill(r"(what is|what's) your name|who are you")
def who_are_you(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(f"I'm {ctx.config.assistant_name}, your desktop assistant.")


@skill(r"(what can you do|help|what are your (skills|commands))")
def help_skill(m: re.Match[str], ctx: Context) -> Reply:
    extra = " Ask me anything else and I'll think it through." if ctx.config.ai_enabled else ""
    return Reply(
        "I can open apps and websites, search Google or YouTube, tell the time and date, "
        "set timers, take notes, check your system, lock your PC and tell jokes." + extra
    )


@skill(r"(tell me )?(a )?joke|make me laugh|say something funny")
def joke(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(random.choice(JOKES))


# --- time -------------------------------------------------------------------


@skill(r"(what time is it|what's the time|what is the time|tell me the time|time)( now)?")
def time_skill(m: re.Match[str], ctx: Context) -> Reply:
    return Reply(f"It's {ctx.now().strftime('%I:%M %p').lstrip('0')}.")


@skill(r"(what's|what is) (the |today's )?date( today)?|what day is (it|today)|today's date|date")
def date_skill(m: re.Match[str], ctx: Context) -> Reply:
    now = ctx.now()
    return Reply(f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}.")


_UNITS = {"second": 1, "minute": 60, "hour": 3600}


@skill(r"(set (a |an )?)?timer (for )?(?P<n>\d+) (?P<unit>second|minute|hour)s?",
       r"remind me in (?P<n>\d+) (?P<unit>second|minute|hour)s?( to (?P<what>.+))?")
def timer(m: re.Match[str], ctx: Context) -> Reply:
    n, unit = int(m["n"]), m["unit"]
    what = m.groupdict().get("what")
    label = f"{n} {unit}{'s' if n != 1 else ''}"
    message = f"Reminder: {what}." if what else f"Your {label} timer is done."
    ctx.actions.schedule(n * _UNITS[unit], lambda: ctx.speak(message))
    return Reply(f"Okay, I'll let you know in {label}.")


# --- web --------------------------------------------------------------------


@skill(r"(search )?youtube (for )?(?P<q>.+)",
       r"play (?P<q>.+?) on youtube",
       r"search (for )?(?P<q>.+?) on youtube")
def youtube(m: re.Match[str], ctx: Context) -> Reply:
    q = m["q"]
    ctx.actions.open_url(f"https://www.youtube.com/results?search_query={quote_plus(q)}")
    return Reply(f"Here's {q} on YouTube.")


@skill(r"(search|google|look up)( google)?( for)? (?P<q>.+)")
def google(m: re.Match[str], ctx: Context) -> Reply:
    q = m["q"]
    ctx.actions.open_url(f"https://www.google.com/search?q={quote_plus(q)}")
    return Reply(f"Searching Google for {q}.")


# --- apps and sites ---------------------------------------------------------


@skill(r"(open|launch|start|run) (?P<target>.+)")
def open_thing(m: re.Match[str], ctx: Context) -> Reply:
    target = re.sub(r"^(the |my )", "", m["target"]).removesuffix(" app")
    if target in WEBSITES:
        ctx.actions.open_url(WEBSITES[target])
        return Reply(f"Opening {target}.")
    if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", target):
        url = target if target.startswith("http") else f"https://{target}"
        ctx.actions.open_url(url)
        return Reply(f"Opening {target}.")
    if ctx.actions.open_app(target):
        return Reply(f"Opening {target}.")
    return Reply(f"Sorry, I couldn't find an app called {target}.")


@skill(r"lock (my |the )?(computer|pc|laptop|screen)")
def lock(m: re.Match[str], ctx: Context) -> Reply:
    if ctx.actions.lock_screen():
        return Reply("Locking your computer.")
    return Reply("I can only lock the screen on Windows.")


@skill(r"(system|computer|pc) (status|info|health)|battery( status| level)?|how('s| is) my (pc|computer|system)")
def system(m: re.Match[str], ctx: Context) -> Reply:
    status = ctx.actions.system_status()
    if status is None:
        return Reply("I need the psutil package to check your system. Run pip install psutil.")
    text = f"CPU is at {status['cpu']:.0f} percent and memory at {status['memory']:.0f} percent."
    if "battery" in status:
        charging = "and charging" if status["plugged"] else "on battery"
        text += f" Battery is {status['battery']:.0f} percent, {charging}."
    return Reply(text)


# --- notes ------------------------------------------------------------------


@skill(r"(take a note|make a note|note down|write down|remember( that)?)( that)? (?P<note>.+)")
def take_note(m: re.Match[str], ctx: Context) -> Reply:
    path = ctx.config.notes_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ctx.now():%Y-%m-%d %H:%M}  {m['note']}\n")
    return Reply("Got it, I've noted that down.")


@skill(r"(read|show|what are) (me )?my notes|what did i (ask you to remember|note)")
def read_notes(m: re.Match[str], ctx: Context) -> Reply:
    path = ctx.config.notes_file
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    if not lines:
        return Reply("You don't have any notes yet.")
    recent = [line.split("  ", 1)[-1] for line in lines[-5:]]
    return Reply("Your latest notes: " + ". ".join(recent) + ".")
