"""Speaking and listening. Both degrade gracefully so Jarvis still works as a text chat."""

from __future__ import annotations

from typing import Any


class Speaker:
    def __init__(self, rate: int = 180, enabled: bool = True) -> None:
        self._engine: Any = None
        if not enabled:
            return
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
        except Exception as e:  # missing package, no audio device, no SAPI voice...
            print(f"(Voice output unavailable: {e}. Replies will be printed only.)")

    def say(self, text: str, name: str = "Jarvis") -> None:
        print(f"{name}: {text}")
        if self._engine is not None:
            self._engine.say(text)
            self._engine.runAndWait()


class Listener:
    """Microphone input through Google's free speech recognition."""

    def __init__(self) -> None:
        import speech_recognition as sr

        self._sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.microphone = sr.Microphone()
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

    def listen(self, timeout: float | None = None, phrase_limit: float = 10) -> str | None:
        """Return what was said, or None on silence or if it couldn't be understood."""
        sr = self._sr
        with self.microphone as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return None
        try:
            return self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"(Speech service error: {e})")
            return None
