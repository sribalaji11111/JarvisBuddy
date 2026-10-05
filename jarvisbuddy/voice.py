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


# Cute neural voice: a child-like Microsoft voice, pitched up, alternating pitch each sentence.
NEURAL_VOICE = "en-US-AnaNeural"
NEURAL_PITCHES = ("+25Hz", "+40Hz", "+30Hz", "+45Hz")


def neural_settings(text: str, style: str = "singsong") -> list[tuple[str, str]]:
    """(sentence, pitch) pairs for the neural voice."""
    sentences = [s.strip() for s in re.findall(r"[^.!?]+[.!?]*", text) if s.strip()] or [text]
    if style != "singsong":
        return [(" ".join(sentences), NEURAL_PITCHES[0])]
    return [(sentence, NEURAL_PITCHES[i % len(NEURAL_PITCHES)]) for i, sentence in enumerate(sentences)]


class NeuralSpeaker:
    """Microsoft's online neural voices through edge-tts: much cuter and smoother than the
    built-in voices, but needs internet. Falls back to `fallback` when it can't connect."""

    def __init__(self, fallback: Speaker, voice: str = NEURAL_VOICE, style: str = "singsong") -> None:
        import edge_tts  # noqa: F401  (fail early if missing)
        import pygame

        pygame.mixer.init()
        self.fallback = fallback
        self.voice = voice
        self.style = style
        self._lock = threading.Lock()

    def _fetch(self, text: str, pitch: str) -> bytes:
        import asyncio

        import edge_tts

        async def go() -> bytes:
            data = bytearray()
            async for chunk in edge_tts.Communicate(text, self.voice, rate="+8%", pitch=pitch).stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
            return bytes(data)

        return asyncio.run(asyncio.wait_for(go(), timeout=8))

    def say(self, text: str) -> None:
        import io

        import pygame

        with self._lock:
            try:
                clips = [self._fetch(sentence, pitch) for sentence, pitch in neural_settings(text, self.style)]
            except Exception:
                self.fallback.say(text)
                return
            for clip in clips:
                sound = pygame.mixer.Sound(file=io.BytesIO(clip))
                channel = sound.play()
                while channel.get_busy():
                    pygame.time.wait(20)


def make_speaker(engine: str, style: str, voice_name: str, rate: int, enabled: bool = True):
    windows = Speaker(style, voice_name, rate, enabled=enabled)
    if enabled and engine == "neural":
        try:
            return NeuralSpeaker(windows, style=style)
        except Exception as e:
            print(f"(Cute neural voice unavailable: {e}. Using the Windows voice.)")
    return windows


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


class WhisperListener:
    """Offline speech recognition with faster-whisper: no internet needed, and usually quicker
    than the online service. The model downloads once (about 140 MB for base.en)."""

    RATE = 16000
    BLOCK = 480  # 30 ms

    def __init__(self, model: str = "base.en", silence_seconds: float = 0.6) -> None:
        import queue

        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel

        self._np = np
        self.model = WhisperModel(model, device="cpu", compute_type="int8")
        self.silence_seconds = silence_seconds
        self._queue: queue.Queue = queue.Queue()
        self._noise = 0.01
        self._stream = sd.InputStream(samplerate=self.RATE, channels=1, dtype="float32", blocksize=self.BLOCK,
                                      callback=lambda data, *_: self._queue.put(data[:, 0].copy()))
        self._stream.start()

    def listen(self, timeout: float | None = None, phrase_limit: float = 12) -> str | None:
        import queue
        import time

        np = self._np
        while not self._queue.empty():  # drop anything heard while Jarvis was talking
            self._queue.get_nowait()
        speech, started, silent_for, t0 = [], None, 0.0, time.monotonic()
        while True:
            try:
                block = self._queue.get(timeout=0.5)
            except queue.Empty:
                block = None
            if timeout and started is None and time.monotonic() - t0 > timeout:
                return None
            if block is None:
                continue
            level = float(np.sqrt(np.mean(block ** 2)))
            loud = level > max(0.012, self._noise * 3)
            if started is None:
                self._noise = 0.98 * self._noise + 0.02 * level  # learn the room's background noise
                if loud:
                    started, speech, silent_for = time.monotonic(), [block], 0.0
                continue
            speech.append(block)
            silent_for = 0.0 if loud else silent_for + self.BLOCK / self.RATE
            if silent_for >= self.silence_seconds or len(speech) * self.BLOCK / self.RATE > phrase_limit:
                break
        audio = np.concatenate(speech)
        if len(audio) < self.RATE * 0.35:
            return None
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        return text or None


def make_listener(engine: str, language: str, whisper_model: str):
    """Offline Whisper when available (or asked for), otherwise Google's online recognizer."""
    if engine in ("auto", "whisper"):
        try:
            return WhisperListener(whisper_model)
        except Exception as e:
            if engine == "whisper":
                raise
            print(f"(Offline speech recognition unavailable: {e}. Using Google's online service.)")
    return Listener(language)
