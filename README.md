# JarvisBuddy

A "Hey Jarvis" voice assistant for your Windows PC, written in Python.
Say **"Hey Jarvis"**, wait for **"Yes?"**, then give a command. Or say it in one go: *"Hey Jarvis, open notepad."*

## Quick start (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"**.
2. Download or clone this repo.
3. Double-click **`run.bat`**. The first run installs everything into a `.venv` folder and creates a `.env` file.
4. Optional: open `.env` and paste your Anthropic API key after `ANTHROPIC_API_KEY=` so Jarvis can answer any question. Built-in commands work without it.

Prefer the terminal?

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m jarvisbuddy            :: voice mode
python -m jarvisbuddy --text     :: type instead of talking
```

Options: `--text` (keyboard chat), `--mute` (print replies, don't speak), `--no-wake-word` (every phrase is a command).

## What you can say

| Ask | Example |
|---|---|
| Open apps | "open notepad", "launch VS Code", "open calculator", "open task manager" |
| Open websites | "open YouTube", "open gmail", "open github.com" |
| Search | "search for python tutorials", "google weather in Chennai" |
| YouTube | "play lofi music on YouTube", "search YouTube for cats" |
| Time and date | "what time is it", "what's the date today" |
| Timers and reminders | "set a timer for 5 minutes", "remind me in 1 hour to call mom" |
| Notes | "take a note buy milk", "remember that the meeting is at 5", "read my notes" |
| Your PC | "system status", "battery", "lock my computer" |
| Fun | "tell me a joke", "how are you" |
| Anything else | "explain black holes simply" (answered by Claude when an API key is set) |
| Stop | "goodbye", "go to sleep" |

## Settings (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | (empty) | Lets Jarvis answer open questions with Claude |
| `JARVIS_USER_NAME` | `Sri` | What Jarvis calls you |
| `JARVIS_NAME` | `Jarvis` | Assistant name, also the wake word |
| `JARVIS_VOICE_RATE` | `180` | Speaking speed |
| `JARVIS_NOTES_FILE` | `~/jarvisbuddy_notes.txt` | Where notes are saved |
| `JARVIS_CLAUDE_MODEL` | `claude-opus-5-5` | Claude model for open questions |

## Troubleshooting

- **PyAudio fails to install:** run `pip install pipwin && pipwin install pyaudio`, or use `--text` mode.
- **Jarvis doesn't hear you:** check the microphone in Windows Sound settings. Speech recognition uses Google's free online service, so you need internet.
- **No voice:** Jarvis uses the built-in Windows voices (SAPI). Replies are still printed if speech isn't available.

## Adding your own commands

Commands live in `jarvisbuddy/skills.py`. Add a function with the `@skill` decorator and a regex for the phrase:

```python
@skill(r"open my project folder")
def project_folder(m, ctx):
    ctx.actions.open_app(r"C:\Users\you\projects")
    return Reply("Opening your projects.")
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Tests use fakes for the microphone, speaker, apps and Claude, so they run anywhere.
