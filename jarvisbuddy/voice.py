"""Speaking and listening.

The voice is a high, bouncy, sing-song robot: on Windows we drive the built-in SAPI voices
directly with pitch markup, which is instant and works offline. Elsewhere we fall back to
pyttsx3, and if no voice works at all, replies are just printed."""

from __future__ import annotations

import re
import threading
from typing import Any
from xml.sax.saxutils import escape

# Pitch per phrase chunk (SAPI absmiddle, -10..10). Cycling through these makes the voice bounce.
SINGSONG_PITCHES = (7, 10, 6, 10, 8, 4, 9)
ROBOT_PITCH = 10
SAPI_IS_XML = 8


def voice_markup(text: str, style: str = "singsong", rate: int = 2) -> str:
    """SAPI XML for `text`. Sing-song raises and lowers pitch every couple of words and
    rises at the end of questions, like a cute cartoon robot."""
    rate = max(-10, min(10, rate))
    if style == "normal":
        return f'<rate absspeed="{rate}">{escape(text)}</rate>'
    if style == "robot":
        return f'<rate absspeed="{rate}"><pitch absmiddle="{ROBOT_PITCH}">{escape(text)}</pitch></rate>'

    parts: list[str] = []
    i = 0
    for sentence in re.findall(r"[^.!?]+[.!?]*", text):
        words = sentence.split()
        if not words:
            continue
        question = sentence.rstrip().endswith("?")
        chunks = [words[j:j + 2] for j in range(0, len(words), 2)]
        for k, chunk in enumerate(chunks):
            pitch = SINGSONG_PITCHES[i % len(SINGSONG_PITCHES)]
            if question and k == len(chunks) - 1:
                pitch = 10
            i += 1
            parts.append(f'<pitch absmiddle="{pitch}">{escape(" ".join(chunk))}</pitch>')
    return f'<rate absspeed="{rate}">{" ".join(parts)}</rate>'


class Speaker:
    def __init__(self, style: str = "singsong", voice_name: str = "Zira", rate: int = 2,
                 enabled: bool = True) -> None:
        self.style = style
        self.voice_name = voice_name
        self.rate = rate
        self.enabled = enabled
        self._lock = threading.Lock()  # one voice at a time (timers can speak from other threads)
        self._local = threading.local()
        self._backend = "print"
        if not enabled:
            return
        try:
            self._sapi_voice()
            self._backend = "sapi"
            return
        except Exception:
            pass
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", 190 + rate * 10)
            for voice in engine.getProperty("voices"):
                if voice_name.lower() in voice.name.lower() or "female" in str(voice.gender).lower():
                    engine.setProperty("voice", voice.id)
                    break
            self._pyttsx3 = engine
            self._backend = "pyttsx3"
        except Exception as e:  # missing package, no audio device, no voices...
            print(f"(Voice output unavailable: {e}. Replies will be printed only.)")

    def _sapi_voice(self) -> Any:
        """A SAPI voice for the current thread (COM objects can't be shared across threads)."""
        voice = getattr(self._local, "voice", None)
        if voice is None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            for token in voice.GetVoices():
                if self.voice_name.lower() in token.GetDescription().lower():
                    voice.Voice = token
                    break
            self._local.voice = voice
        return voice

    def say(self, text: str) -> None:
        with self._lock:
            if self._backend == "sapi":
                self._sapi_voice().Speak(voice_markup(text, self.style, self.rate), SAPI_IS_XML)
            elif self._backend == "pyttsx3":
                self._pyttsx3.say(text)
                self._pyttsx3.runAndWait()


class Listener:
    """Microphone input through Google's free speech recognition."""

    def __init__(self, language: str = "en-IN") -> None:
        import speech_recognition as sr

        self.language = language
        self._sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        # Stop listening sooner after you finish talking, so replies feel instant.
        self.recognizer.pause_threshold = 0.6
        self.recognizer.non_speaking_duration = 0.4
        self.microphone = sr.Microphone()
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

    def listen(self, timeout: float | None = None, phrase_limit: float = 12) -> str | None:
        """Return what was said, or None on silence or if it couldn't be understood."""
        sr = self._sr
        with self.microphone as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return None
        try:
            return self.recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"(Speech service error: {e})")
            return None
