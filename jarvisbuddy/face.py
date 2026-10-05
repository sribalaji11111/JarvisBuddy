"""The animated EVE-style face: glowing blue eyes on a black visor that blink, glance around,
bounce while talking, and pull funny expressions. Built on tkinter, which ships with Python."""

from __future__ import annotations

import math
import queue
import random
import time
import tkinter as tk
from typing import Callable

W, H = 520, 440
BG = "#0b0f17"
SHELL = "#eef2f6"
VISOR = "#000000"
BLUE = ("#06223a", "#0b4a78", "#1f8fd6", "#47cfff", "#b9f1ff")  # glow, outer to core
PINK = ("#3a0b24", "#7a1750", "#d6338c", "#ff6fb5", "#ffd0e8")
RED = ("#3a0b0b", "#781616", "#d62f2f", "#ff5c5c", "#ffd0d0")

# How long a reaction face stays up after Jarvis finishes talking.
HOLD_SECONDS = 2.5


class Face:
    """Call the public methods from any thread; they're queued onto the UI thread."""

    def __init__(self, title: str = "JarvisBuddy", on_poke: Callable[[], None] | None = None,
                 on_close: Callable[[], None] | None = None, fullscreen: bool = False) -> None:
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.geometry(f"{W}x{H}")
        self.root.minsize(360, 320)
        if fullscreen:
            self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.root.bind("<F11>", lambda e: self.root.attributes(
            "-fullscreen", not self.root.attributes("-fullscreen")))
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", lambda e: on_poke and on_poke())
        self.root.protocol("WM_DELETE_WINDOW", lambda: (on_close and on_close(), self.root.destroy()))

        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.mood = "neutral"
        self.mood_until = 0.0
        self.speaking = False
        self.status = ""
        self.caption = ""
        self.t0 = time.monotonic()
        self.last_activity = self.t0
        self.next_blink = self.t0 + 2
        self.blink_start = 0.0
        self.look = [0.0, 0.0]
        self.look_target = [0.0, 0.0]
        self.next_glance = self.t0 + 3
        self.next_antic = self.t0 + 25

    # --- thread-safe API ---------------------------------------------------------

    def set_mood(self, mood: str, hold: float = HOLD_SECONDS) -> None:
        self._events.put(("mood", (mood, hold)))

    def set_status(self, text: str) -> None:
        self._events.put(("status", text))

    def set_caption(self, text: str) -> None:
        self._events.put(("caption", text))

    def set_speaking(self, speaking: bool) -> None:
        self._events.put(("speaking", speaking))

    def close(self) -> None:
        self._events.put(("close", None))

    def run(self) -> None:
        self._tick()
        self.root.mainloop()

    # --- animation loop ----------------------------------------------------------

    def _tick(self) -> None:
        now = time.monotonic()
        while not self._events.empty():
            kind, value = self._events.get()
            self.last_activity = now
            if kind == "mood":
                mood, hold = value  # type: ignore[misc]
                self.mood, self.mood_until = mood, now + hold
            elif kind == "status":
                self.status = str(value)
            elif kind == "caption":
                self.caption = str(value)
            elif kind == "speaking":
                self.speaking = bool(value)
                if not self.speaking:
                    self.mood_until = now + HOLD_SECONDS
            elif kind == "close":
                self.root.destroy()
                return
        self._idle_behaviour(now)
        self._draw(now)
        self.root.after(33, self._tick)

    def _idle_behaviour(self, now: float) -> None:
        if now >= self.next_blink:
            self.blink_start = now
            self.next_blink = now + random.uniform(2.5, 6) if random.random() > 0.2 else now + 0.35
        if now >= self.next_glance:
            self.look_target = [random.uniform(-1, 1), random.uniform(-0.6, 0.6)] if random.random() < 0.6 else [0, 0]
            self.next_glance = now + random.uniform(2, 6)
        self.look[0] += (self.look_target[0] - self.look[0]) * 0.15
        self.look[1] += (self.look_target[1] - self.look[1]) * 0.15

        if not self.speaking and now > self.mood_until and self.mood not in ("neutral", "sleepy", "thinking"):
            self.mood = "neutral"
        idle = now - self.last_activity
        if idle > 90 and not self.speaking:
            self.mood = "sleepy"
        elif now >= self.next_antic and idle > 15 and not self.speaking:
            # A little comedy while nobody's talking to us.
            self.mood = random.choice(["wink", "surprised", "confused", "laugh", "love", "excited"])
            self.mood_until = now + 1.6
            self.next_antic = now + random.uniform(20, 45)

    # --- drawing ------------------------------------------------------------------

    def _draw(self, now: float) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width() or W, c.winfo_height() or H
        s = min(w / W, h / H)
        cx, cy = w / 2, h * 0.46
        t = now - self.t0

        # EVE's white egg head with a black visor.
        c.create_oval(cx - 220 * s, cy - 190 * s, cx + 220 * s, cy + 175 * s, fill=SHELL, outline="#c9d2dc", width=3)
        c.create_oval(cx - 185 * s, cy - 120 * s, cx + 185 * s, cy + 110 * s, fill=VISOR, outline="#1d2633", width=4)

        mood = self.mood
        bob = math.sin(t * 2.0) * 3 * s  # gentle floating
        if self.speaking:
            bob += abs(math.sin(t * 9)) * -6 * s  # bounce while talking
        if mood == "laugh":
            bob += math.sin(t * 22) * 5 * s
        if mood == "excited":
            bob += math.sin(t * 14) * 4 * s
        lx = self.look[0] * 18 * s
        ly = self.look[1] * 12 * s + bob
        if mood == "thinking":
            lx, ly = 22 * s, -22 * s + bob

        blink = 1.0
        dt = now - self.blink_start
        if dt < 0.16 and mood not in ("happy", "laugh", "love", "sleepy"):
            blink = max(0.08, abs(dt - 0.08) / 0.08)

        gap = 72 * s
        for side in (-1, 1):
            self._eye(cx + side * gap + lx, cy + ly - 4 * s, side, mood, blink, s, t)

        if self.speaking:
            self._voice_bars(cx, cy + 70 * s, s, t)
        if mood == "thinking":
            dots = "." * (1 + int(t * 3) % 3)
            c.create_text(cx + 110 * s, cy + 60 * s, text=dots, fill=BLUE[3], font=("Segoe UI", int(28 * s), "bold"))
        if mood == "sleepy":
            for i in range(3):
                phase = (t * 0.6 + i / 3) % 1
                c.create_text(cx + (110 + i * 18) * s, cy - (40 + phase * 70) * s, text="z",
                              fill=BLUE[3], font=("Segoe UI", int((14 + i * 5) * s), "bold"))

        if self.status:
            c.create_text(16, 14, anchor="nw", text=self.status, fill="#7fa8c9", font=("Segoe UI", 11))
        if self.caption:
            c.create_text(cx, h - 30 * s, text=self.caption, width=w - 40, fill="#dfe9f3",
                          font=("Segoe UI", max(10, int(13 * s))), justify="center")

    def _eye(self, x: float, y: float, side: int, mood: str, blink: float, s: float, t: float) -> None:
        c = self.canvas
        ew, eh = 46 * s, 30 * s
        colors = BLUE
        if mood == "angry":
            colors = RED
        if mood in ("love",):
            colors = PINK

        if mood == "wink" and side == 1:
            self._arc(x, y, ew, eh, colors, s)
            return
        if mood in ("happy", "laugh"):
            self._arc(x, y, ew, eh, colors, s)
            if mood == "laugh" and side == 1:
                # happy tear
                ty = y + eh + (t * 40 % 30) * s
                c.create_oval(x + ew * 0.7, ty, x + ew * 0.7 + 8 * s, ty + 12 * s, fill=BLUE[3], outline="")
            return
        if mood == "love":
            pulse = 1 + 0.12 * math.sin(t * 8)
            self._heart(x, y, 34 * s * pulse, colors)
            return
        if mood == "sleepy":
            eh *= 0.18
        if mood == "surprised":
            ew, eh = 40 * s, 40 * s
        if mood == "excited":
            ew, eh = 44 * s, 38 * s
        if mood == "confused" and side == -1:
            ew, eh = ew * 0.65, eh * 0.65

        eh *= blink
        for i, color in enumerate(colors[:3]):
            pad = (3 - i) * 7 * s
            c.create_oval(x - ew - pad, y - eh - pad, x + ew + pad, y + eh + pad, fill=color, outline="")
        c.create_oval(x - ew, y - eh, x + ew, y + eh, fill=colors[3], outline="")
        c.create_oval(x - ew * 0.55, y - eh * 0.55, x + ew * 0.55, y + eh * 0.55, fill=colors[4], outline="")

        if mood == "excited" and blink > 0.5:
            c.create_oval(x - ew * 0.5, y - eh * 0.6, x - ew * 0.15, y - eh * 0.25, fill="white", outline="")
        # Eyelids made of visor-black polygons give sad/angry/confused shapes.
        if mood == "sad":
            outer = x + side * (ew + 30 * s)
            c.create_polygon(outer, y - eh - 30 * s, outer, y - eh * 0.1, x - side * (ew + 30 * s), y - eh - 30 * s,
                             fill=VISOR, outline="")
        elif mood == "angry":
            inner = x - side * (ew + 30 * s)
            c.create_polygon(inner, y - eh - 30 * s, inner, y - eh * 0.05, x + side * (ew + 30 * s), y - eh - 30 * s,
                             fill=VISOR, outline="")
        elif mood == "confused" and side == 1:
            c.create_polygon(x - ew - 30 * s, y - eh - 20 * s, x + ew + 30 * s, y - eh - 20 * s,
                             x + ew + 30 * s, y - eh * 0.4, x - ew - 30 * s, y - eh * 0.1, fill=VISOR, outline="")

    def _arc(self, x: float, y: float, ew: float, eh: float, colors: tuple[str, ...], s: float) -> None:
        for width, color in ((22, colors[1]), (16, colors[2]), (10, colors[3])):
            self.canvas.create_arc(x - ew, y - eh, x + ew, y + eh * 1.6, start=15, extent=150,
                                   style="arc", outline=color, width=width * s)

    def _heart(self, x: float, y: float, r: float, colors: tuple[str, ...]) -> None:
        pts = []
        for i in range(40):
            a = i / 40 * 2 * math.pi
            hx = 16 * math.sin(a) ** 3
            hy = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
            pts += [x + hx * r / 16, y - hy * r / 16]
        self.canvas.create_polygon(pts, fill=colors[3], outline=colors[2], width=4, smooth=True)

    def _voice_bars(self, cx: float, y: float, s: float, t: float) -> None:
        for i in range(-3, 4):
            amp = (abs(math.sin(t * 11 + i * 1.3)) * 0.8 + 0.2) * 16 * s
            x = cx + i * 12 * s
            self.canvas.create_rectangle(x - 3 * s, y - amp, x + 3 * s, y + amp, fill=BLUE[3], outline="")
