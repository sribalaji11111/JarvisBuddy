# JarvisBuddy

A cute, fully personal robot buddy for your Windows laptop. JarvisBuddy has an animated EVE-style face,
talks in a high sing-song robot voice, controls your whole laptop by voice through a set of laptop tools
(also available over MCP), and learns a little more about you every day.

![Jarvis's faces: neutral, happy, laughing, love, wink, surprised, sad, angry, confused, thinking, sleepy, excited](docs/faces.png)

Say **"Hey Jarvis"**, wait for **"Yes?"**, then talk. Or say it all at once: *"Hey Jarvis, play Believer."*

## Quick start (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"**.
2. Download or clone this repo.
3. Double-click **`run.bat`**. The first run installs everything and creates a `.env` settings file.
4. Optional but recommended: open `.env` and paste your Anthropic API key after `ANTHROPIC_API_KEY=`.
   With it, Jarvis can chat about anything and learns from your conversations. Every built-in command works without it.

Prefer the terminal?

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m jarvisbuddy             :: face + voice
python -m jarvisbuddy --text      :: type instead of talking
```

Options: `--text` (keyboard chat), `--mute` (don't speak), `--no-face` (no window), `--fullscreen` (face fills the
screen, Esc to leave), `--no-wake-word` (every phrase is a command), `--check` (see what's set up),
`--learn` (learn from today's chats), `--mcp-server` (offer the laptop tools to other apps).

After Jarvis answers, keep talking for 10 seconds without saying "Hey Jarvis" again.

## What you can say

| Ask | Example |
|---|---|
| Play songs | "play Believer", "play the song Shape of You", "play some music" (plays your most-played song) |
| Pick a song | "search songs by Arijit Singh", then "play number 2" |
| Music controls | "pause", "next song", "previous", "volume up", "set volume to 40", "mute" |
| Screen | "brightness 70", "take a screenshot", "type hello world" |
| Close and power (asks first) | "close notepad", "shut down", "restart", "cancel shutdown" |
| Weather | "what's the weather in Chennai" |
| Open apps | "open notepad", "launch VS Code", "open calculator", "open task manager" |
| Open websites | "open YouTube", "open gmail", "open github.com" |
| Search | "search for python tutorials", "search YouTube for cats" |
| Send email | "send an email to mom saying I'll be home by 7", or just "send an email" and answer the questions |
| Contacts | "save contact mom as mom at gmail dot com" |
| Time and date | "what time is it", "what's the date today" |
| Timers | "set a timer for 5 minutes", "remind me in 1 hour to call mom" |
| Notes | "take a note buy milk", "read my notes" |
| Your laptop | "battery", "system status", "lock my laptop" |
| Teach Jarvis | "my favorite food is dosa", "I love cricket", "remember that my sister is Priya", "call me Balaji" |
| Ask Jarvis | "what do you know about me", "forget about cricket" |
| Fun | "tell me a joke", "sing a song", "how are you", or click the face |
| Anything else | "explain black holes simply", or any laptop task (see below) |
| Daily learning | "learn from today" |
| Stop | "goodbye", "go to sleep" |

## Full laptop control (Claude + tools + MCP)

The quick commands above run instantly and offline. Anything else goes to Claude, which can control the laptop
with 35 tools, so you can ask in your own words:

- "Close Chrome and open my Downloads folder"
- "What's using all my memory?"
- "Make a folder called Project on the desktop and move report.pdf from Downloads into it"
- "Copy the text on my clipboard into a new note file"
- "Switch to the VS Code window and press ctrl+s"
- "Is my Wi-Fi connected?" (runs a PowerShell command, after asking)
- "Email Priya that the meeting moved to 5"

| Tool group | Tools |
|---|---|
| Apps and windows | open_app, close_app*, list_running_apps, list_windows, focus_window, window_action, press_keys, type_text, clipboard |
| Web and media | open_website, web_search, play_youtube, media_control |
| Sound, screen, power | set_volume, set_brightness, screenshot, lock_screen, power*, cancel_shutdown, system_status, weather |
| Files | list_folder, find_files, open_path, read_text_file, write_text_file*, create_folder, move_file*, delete_file* (to the Recycle Bin) |
| You | send_email*, save_contact, remember, set_timer, take_note |
| Anything else | run_command* (PowerShell) |

**\* Risky tools always ask you out loud first** ("Should I delete old.zip?"). Only a clear yes goes ahead;
anything else, or silence, cancels it.

### Use Jarvis's tools from other apps (MCP server)

Jarvis's laptop tools are also an MCP server, so Claude Desktop, Claude Code or any MCP app can control your laptop
through Jarvis. In Claude Desktop, open Settings > Developer > Edit Config and add:

```json
{
  "mcpServers": {
    "jarvisbuddy": {
      "command": "C:\\Users\\YOU\\JarvisBuddy\\.venv\\Scripts\\python.exe",
      "args": ["-m", "jarvisbuddy.mcp_server"],
      "cwd": "C:\\Users\\YOU\\JarvisBuddy"
    }
  }
}
```

Risky tools pop up a Yes/No box on your laptop before running, even when called from another app.

### Give Jarvis more tools (MCP client)

Jarvis can also use tools from other MCP servers. Create `%USERPROFILE%\.jarvisbuddy\mcp_servers.json` in the
same format as Claude Desktop, for example:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\YOU\\Documents"]
    }
  }
}
```

Jarvis connects to them at start-up and asks before using any tool the server doesn't mark as read-only.

### Email always asks first

Jarvis reads the email back ("Here's your email to mom: I'll be home by 7. Should I send it?") and only sends
if you say yes. Anything else, or silence, cancels it. Set up Gmail in `.env` with an
[app password](https://myaccount.google.com/apppasswords) (not your normal password).

### How Jarvis learns about you

- **Question of the day:** the first time you start Jarvis each day, it asks one new question (favorite food, music, hobbies...).
- **Things you say:** "my favorite color is blue" or "I love biryani" are saved right away.
- **Conversations:** with an API key, Jarvis quietly picks up facts from what you tell it.
- **Habits:** it notices the apps you open and the songs you play.
- **Daily diary:** say "learn from today" (or double-click `schedule_daily_learning.bat` once to do it every night at
  11 pm). Jarvis reads the day's chats, saves new facts, writes a diary page in `.jarvisbuddy\diary`, and adds the
  chats to `.jarvisbuddy\dataset.jsonl`, which you could later use to fine-tune your own model.
- **Personality:** edit `personality.md` any day to shape who Jarvis is.

Everything is saved on your laptop in `%USERPROFILE%\.jarvisbuddy\memory.json`. Jarvis uses it to make answers personal.

### Voice and face

- For an even cuter voice, set `JARVIS_VOICE_ENGINE=neural`: a child-like Microsoft neural voice, pitched up and
  bouncing sentence to sentence. It needs internet and falls back to the Windows voice when offline.
- The default voice uses Windows' built-in voices with pitch changes every couple of words, so it bounces like a cartoon robot.
  Try `JARVIS_VOICE_STYLE=robot` for a flat high robot, or pick another voice with `JARVIS_VOICE`.
- The face blinks, glances around, bounces while talking, makes a face to match each answer, and pulls silly
  expressions when you leave it alone. It falls asleep after 90 seconds of quiet.

### Speed

Built-in commands answer instantly and offline. Claude answers stream in and Jarvis starts speaking after the
first sentence. Set `JARVIS_FAST_MODE=1` for Claude's faster output mode (about twice the cost per answer).

## Settings (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | (empty) | Lets Jarvis chat about anything and learn from conversations |
| `JARVIS_USER_NAME` | `Sri` | What Jarvis calls you |
| `JARVIS_NAME` | `Jarvis` | Assistant name, also the wake word |
| `JARVIS_VOICE_ENGINE` | `windows` | `windows` (instant, offline) or `neural` (cuter, online) |
| `JARVIS_VOICE_STYLE` | `singsong` | `singsong`, `robot` or `normal` |
| `JARVIS_VOICE` | `Zira` | Windows voice to use |
| `JARVIS_VOICE_RATE` | `2` | Speaking speed, -10 to 10 |
| `JARVIS_SPEECH_LANGUAGE` | `en-IN` | Accent for speech recognition |
| `JARVIS_EMAIL_ADDRESS` / `JARVIS_EMAIL_APP_PASSWORD` | (empty) | Gmail account for sending email |
| `JARVIS_FAST_MODE` | `0` | Faster Claude answers at a higher price |
| `JARVIS_FOLLOW_UP_SECONDS` | `10` | Keep listening after a reply without the wake word |
| `JARVIS_MCP_CONFIRM` | `1` | Yes/No pop-up for risky tools called through the MCP server |
| `JARVIS_DATA_DIR` | `~/.jarvisbuddy` | Where memory and notes are stored |
| `JARVIS_CLAUDE_MODEL` | `claude-opus-5-5` | Claude model for open questions |

## Troubleshooting

- **PyAudio fails to install:** run `pip install pipwin && pipwin install pyaudio`, or use `--text` mode.
- **Jarvis doesn't hear you:** check the microphone in Windows Sound settings. Speech recognition uses Google's free online service, so you need internet.
- **Voice sounds wrong or is missing:** check which voices you have in Settings > Time & language > Speech, and set `JARVIS_VOICE` to one of them.
- **A song opens the search page instead of playing:** YouTube changed its page layout; Jarvis falls back to the search results.

## Adding your own commands

Quick offline commands live in `jarvisbuddy/skills.py`; tools for Claude and MCP live in
`jarvisbuddy/tools.py` (add a function with the `@tool` decorator, and `risky=True` if it needs a yes).
To add a quick command, add a function with the `@skill` decorator, a regex for the phrase,
and the face to make:

```python
@skill(r"open my project folder")
def project_folder(m, ctx):
    ctx.actions.open_app(r"C:\Users\you\projects")
    return Reply("Opening your projects.", mood="happy")
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Tests use fakes for the microphone, speaker, apps, email and Claude, so they run anywhere. One test starts the
real MCP server and connects to it.
