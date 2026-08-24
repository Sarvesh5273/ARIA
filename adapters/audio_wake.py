"""Concrete `WakeWordBackend` — v4: "Porcupine ~2 MB, or hotkey fallback".

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.WakeWordBackend`:

    def detect(self, audio: AudioSegment) -> bool

TWO IMPLEMENTATIONS, BECAUSE v4 NAMES TWO
-----------------------------------------
    PorcupineWakeWord   the keyword spotter (v4's primary)
    HotkeyWakeWord      v4's own named "hotkey fallback"

Nothing else is offered. In particular there is no "always awake" variant: the
wake-word gate is the first thing between a live microphone and a transcription,
and a backend that always returns True would turn the whole pipeline into an
open mic. If that is ever wanted it should be a deliberate decision at the wiring
layer, visible in the startup output, not an adapter someone picks by accident.

WHAT `detect` IS ASKED, AND THE ONE SUBTLETY
--------------------------------------------
`AudioPipeline.capture_turn()` calls `detect(buffered)` with the WHOLE 20-second
ring-buffer snapshot, not just the newest frame. So the honest question is "does
this window contain the wake word", and a stateful detector must not re-fire on
the same utterance every cycle just because it is still inside the window.

`PorcupineWakeWord` handles that itself: Porcupine consumes fixed-length frames
and returns the index of a detection, and this adapter tracks how far into the
buffer it has already consumed — so a wake word is reported ONCE and the same
audio does not wake her repeatedly while it ages out of the ring.

THE FRAME-LENGTH GUARD IS THE POINT OF THIS ADAPTER
---------------------------------------------------
Porcupine requires exactly `frame_length` samples per call at exactly its own
`sample_rate`, as int16. Hand it the wrong size and it raises; hand it the wrong
rate and it silently detects nothing, which is the worse failure because it looks
like a wake word that just never works. So the rate is checked against the
pipeline's cited 16 kHz at construction and refused loudly if they disagree.

FLOAT -> INT16 IS A FORMAT CONVERSION, NOT A JUDGMENT
-----------------------------------------------------
The pipeline's `AudioSegment.samples` are floats in [-1, 1] (what PortAudio's
float32 mode gives); Porcupine and Silero both want int16 PCM. Scaling by 32767
and clamping is the standard, lossless-in-intent mapping between the two
representations — and it is shared from `audio_pcm.py` rather than copied into
each backend, so three adapters cannot drift on it.

NO KEYWORD IS INVENTED. Porcupine needs a keyword path or a built-in keyword
name and this adapter requires the caller to name one. "Aria" is not a Porcupine
built-in, so a real deployment needs a trained `.ppn` — and guessing a substitute
built-in ("computer", "jarvis") would pick her name on the operator's behalf.
"""

from __future__ import annotations

import threading
from typing import Optional, Sequence

from daemon.audio_pipeline import SAMPLE_RATE_HZ, AudioSegment

from adapters._provider import AudioBackendUnavailable, module_available, require_module
from adapters.audio_pcm import to_int16

_PORCUPINE = "pvporcupine"
_INSTALL = "pip install pvporcupine   (needs a free access key from Picovoice)"


class PorcupineWakeWord:
    """`WakeWordBackend` backed by Picovoice Porcupine (v4's named tool, ~2 MB).

    Holds the provider handle, the consumed-sample cursor and a lock. No soul
    state, no PAD, no graph.
    """

    def __init__(
        self,
        *,
        access_key: str,
        keyword_paths: Optional[Sequence[str]] = None,
        keywords: Optional[Sequence[str]] = None,
        sensitivities: Optional[Sequence[float]] = None,
        expected_sample_rate: int = SAMPLE_RATE_HZ,
    ) -> None:
        if not keyword_paths and not keywords:
            raise AudioBackendUnavailable(
                "wake word needs either keyword_paths (a trained .ppn for her "
                "name) or keywords (a Porcupine built-in). Neither was given, "
                "and picking a built-in here would choose her wake word for you."
            )
        provider = require_module(
            _PORCUPINE, purpose="wake-word detection", install=_INSTALL
        )
        try:
            self._porcupine = provider.create(
                access_key=access_key,
                keyword_paths=list(keyword_paths) if keyword_paths else None,
                keywords=list(keywords) if keywords else None,
                sensitivities=list(sensitivities) if sensitivities else None,
            )
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not initialise the wake-word engine: {exc}"
            ) from exc

        self._frame_length = int(self._porcupine.frame_length)
        engine_rate = int(self._porcupine.sample_rate)
        if engine_rate != expected_sample_rate:
            # Refuse rather than resample. A rate mismatch here does not raise on
            # its own — it just never detects, which reads as "the wake word is
            # broken" and is very hard to trace back to a number.
            self.close()
            raise AudioBackendUnavailable(
                f"wake-word engine runs at {engine_rate} Hz but the pipeline "
                f"captures at {expected_sample_rate} Hz (v4's cited format). "
                f"A silent mismatch would detect nothing."
            )
        self._rate = engine_rate
        self._consumed = 0
        self._lock = threading.Lock()
        self.detections = 0        # observability only

    @property
    def frame_length(self) -> int:
        return self._frame_length

    @property
    def sample_rate(self) -> int:
        return self._rate

    # -- WakeWordBackend ----------------------------------------------------

    def detect(self, audio: AudioSegment) -> bool:
        """Has the wake word appeared in the audio not yet examined?

        The pipeline passes the whole ring-buffer snapshot every cycle, so this
        consumes only the NEW tail and remembers how far it got. That is what
        stops one spoken wake word from waking her on every cycle for the twenty
        seconds it remains in the buffer.

        The cursor is reset when the buffer appears to have shrunk or been
        cleared (a snapshot shorter than what we already consumed), because the
        ring dropping old samples means our index no longer refers to the same
        audio.
        """
        pcm = to_int16(audio.samples)
        with self._lock:
            if len(pcm) < self._consumed:
                self._consumed = 0
            found = False
            cursor = self._consumed
            while cursor + self._frame_length <= len(pcm):
                frame = pcm[cursor:cursor + self._frame_length]
                cursor += self._frame_length
                if self._porcupine.process(frame) >= 0:
                    found = True
                    self.detections += 1
                    # Keep consuming so the cursor lands past the detection; a
                    # detection mid-buffer must not be re-reported next cycle.
            self._consumed = cursor
            return found

    def reset(self) -> None:
        """Forget the consumed cursor — for a caller that clears the ring buffer
        and wants the next snapshot examined from the start."""
        with self._lock:
            self._consumed = 0

    def close(self) -> None:
        engine, self._porcupine = getattr(self, "_porcupine", None), None
        if engine is not None:
            try:
                engine.delete()
            except Exception:  # pragma: no cover - provider teardown
                pass


class HotkeyWakeWord:
    """v4's own named alternative: the "hotkey fallback".

    Not a detector at all — it reports whether something OUTSIDE this process
    signalled that she was addressed. `trigger()` is called by whatever owns the
    key binding (a REPL keypress, a global hotkey daemon, a GUI button); `detect`
    consumes the signal and returns it.

    ONE-SHOT ON PURPOSE. `detect` clears the flag, so one press wakes her once.
    A latched flag would keep every subsequent cycle awake, which is the open-mic
    failure the wake-word gate exists to prevent.

    Needs no provider, so it is the honest fallback on a machine with no
    Picovoice key — and unlike a stub it does not weaken the gate: nothing is
    transcribed unless a human actually pressed something.
    """

    def __init__(self) -> None:
        self._triggered = False
        self._lock = threading.Lock()
        self.detections = 0

    def trigger(self) -> None:
        """Signal "she was addressed". Safe to call from another thread."""
        with self._lock:
            self._triggered = True

    def detect(self, audio: AudioSegment) -> bool:
        """Consume the pending trigger, if any. The audio is not examined — that
        is the whole nature of a hotkey fallback, and pretending to look at the
        signal would be worse than being clear that it does not."""
        with self._lock:
            fired, self._triggered = self._triggered, False
        if fired:
            self.detections += 1
        return fired


def available() -> bool:
    return module_available(_PORCUPINE)


def install_hint() -> str:
    return _INSTALL
