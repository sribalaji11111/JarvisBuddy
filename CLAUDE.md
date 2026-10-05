# JarvisBuddy developer guide

A Windows voice assistant in Python: EVE-style face, sing-song voice, quick offline commands,
Claude (or offline Ollama) with laptop tools, MCP server and client, and memory that grows daily.
Sri develops it a little every day; `ROADMAP.md` lists the next ideas.

## Run and check

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # all tests use fakes: no mic, speaker, browser, email or API needed
ruff check jarvisbuddy tests # lint (ruff check --fix fixes most things)
python -m jarvisbuddy --text --mute --no-face   # quick manual try in the terminal
python -m jarvisbuddy --check                   # which optional pieces are installed
```

CI (`.github/workflows/tests.yml`) runs ruff and pytest on Ubuntu and Windows for every push.

## How a request flows

1. `voice.py` hears it (Whisper offline, or Google) and `assistant.py` strips the wake word.
2. `skills.py` tries the quick regex commands (instant, offline). Each returns a `Reply` with a `mood` for the face.
3. Otherwise `brain.py` (Claude) or `local_brain.py` (Ollama) answers, streaming sentence by sentence,
   and may call laptop tools from `tools.py` through `ToolRunner`.
4. `assistant.say()` speaks (`voice.py`) and updates the face (`face.py`).
5. `memory.py` logs the chat, facts and habits; `learn.py` turns a day of chats into facts and a diary.

## Where to add things

| To add | Do this |
|---|---|
| A quick voice command | `@skill(r"regex")` function in `skills.py`, return `Reply(text, mood=...)`. Order matters: first match wins. |
| A laptop ability for Claude and MCP | `@tool(...)` function inside `build_tools()` in `tools.py`. Set `risky=True` and `confirm="..."` if it is hard to undo. |
| An OS action used by both | a method on `Actions` in `actions.py`, and the same method on `FakeActions` in `tests/conftest.py` |
| A face expression | add the mood to `MOODS` in `skills.py` and draw it in `Face._eye()` in `face.py` |
| A setting | a field on `Config` in `config.py`, read in `from_env()`, documented in `.env.example` and README |

Every new skill or tool gets a test (see `tests/test_skills.py`, `tests/test_tools.py`).

## Rules

- Anything hard to undo (email, deleting/moving/overwriting files, closing apps, shutdown, commands)
  must ask the user first and only proceed on a clear yes. Silence is a no.
- Keep spoken replies short and plain (no markdown): they are read aloud.
- Optional libraries are imported inside functions so Jarvis still starts without them; `--check` lists them.
- Never commit `.env` or anything from `~/.jarvisbuddy` (memory, diary, conversations).
