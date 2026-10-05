"""Daily learning: say "learn from today", run `python -m jarvisbuddy --learn`, or schedule it
nightly with schedule_daily_learning.bat. Each run:

  1. reads today's conversations,
  2. saves the new facts it learned about you to memory (needs an API key),
  3. writes a diary page to ~/.jarvisbuddy/diary/<date>.md,
  4. adds today's question-and-answer pairs to ~/.jarvisbuddy/dataset.jsonl, in the chat
     format used for fine-tuning, in case you ever want to train your own model.
"""

from __future__ import annotations

import json
from datetime import date

from .brain import Brain
from .memory import Memory


def daily(memory: Memory, brain: Brain, name: str, assistant_name: str, day: date | None = None) -> str:
    day = day or date.today()
    messages = memory.day_messages(day)
    if not messages:
        return "We haven't talked today, so there's nothing new to learn yet."

    transcript = "\n".join(f"{name if role == 'user' else assistant_name}: {text}" for role, text in messages)
    learned = [f for f in brain.extract_facts(transcript, f"today's conversation with {name}") if memory.add_fact(f)]

    data_dir = memory.path.parent
    diary = data_dir / "diary"
    diary.mkdir(parents=True, exist_ok=True)
    (diary / f"{day}.md").write_text(
        f"# {day}\n\n## What I learned about {name}\n"
        + ("\n".join(f"- {f}" for f in learned) or "- nothing new")
        + f"\n\n## Conversation\n{transcript}\n",
        encoding="utf-8",
    )

    pairs = [(messages[i][1], messages[i + 1][1]) for i in range(len(messages) - 1)
             if messages[i][0] == "user" and messages[i + 1][0] == "assistant"]
    with (data_dir / "dataset.jsonl").open("a", encoding="utf-8") as f:
        for question, answer in pairs:
            f.write(json.dumps({"messages": [{"role": "user", "content": question},
                                             {"role": "assistant", "content": answer}]},
                               ensure_ascii=False) + "\n")

    things = "thing" if len(learned) == 1 else "things"
    note = "" if brain.available else " Add an API key so I can pick out facts too."
    return f"I learned {len(learned)} new {things} about you today and wrote it in my diary.{note}"
