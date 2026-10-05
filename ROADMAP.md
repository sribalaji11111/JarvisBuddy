# Roadmap: one small upgrade a day

Pick the next unchecked item, make a branch, build it with a test, run `pytest` and `ruff`, and merge.
Add your own ideas anywhere.

## Week 1: feel more alive
- [ ] Day 1: Move the face's voice bars and bounce in time with the real audio loudness
- [ ] Day 2: Offline wake word with openWakeWord, so "Hey Jarvis" works without sending audio anywhere
- [ ] Day 3: Remember timers and reminders across restarts (save them in memory.json)
- [ ] Day 4: Morning briefing on the first start of the day: weather, battery, reminders, a fun fact
- [ ] Day 5: Windows toast notifications for reminders when the face window is hidden
- [ ] Day 6: More face moods: dizzy, cool sunglasses, party; pick them from joke and song replies
- [ ] Day 7: Tray icon with Show face / Mute / Quit

## Week 2: control more of the laptop
- [ ] Day 8: Spotify control (play a playlist by name) with the Spotify Web API
- [ ] Day 9: Wi-Fi and Bluetooth on/off tools (risky: ask first)
- [ ] Day 10: Read and summarise the selected text or the clipboard
- [ ] Day 11: Calendar: today's events from Google Calendar or Outlook
- [ ] Day 12: WhatsApp Web message to a contact (always ask first)
- [ ] Day 13: "Clean my Downloads": group old files into folders (show the plan, ask first)
- [ ] Day 14: App usage report: which apps you used most today

## Week 3: smarter brain
- [ ] Day 15: Let Jarvis see the screen: screenshot + Claude vision for "what's on my screen?"
- [ ] Day 16: Webcam glance: notice when you come back and greet you
- [ ] Day 17: Tamil and Hindi replies (speech recognition language + a matching voice)
- [ ] Day 18: Rank memory facts by relevance to the question instead of sending all of them
- [ ] Day 19: Weekly memory review: "here's what I learned about you this week"
- [ ] Day 20: Try `qwen2.5:7b` in Ollama and compare tool use with llama3.2
- [ ] Day 21: Fine-tune a small model on `~/.jarvisbuddy/dataset.jsonl` (Colab + LoRA) and load it in Ollama

## Week 4: polish
- [ ] Day 22: Settings window instead of editing .env
- [ ] Day 23: Start Jarvis automatically when Windows starts
- [ ] Day 24: Package as a single .exe with PyInstaller
- [ ] Day 25: Sound effects for listening and thinking
- [ ] Day 26: Interrupt Jarvis by talking while it speaks
- [ ] Day 27: Conversation history window
- [ ] Day 28: Backup and restore memory
