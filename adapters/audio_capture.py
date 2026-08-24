"""Concrete `CaptureBackend` — the microphone. v4: sounddevice, 16 kHz mono.

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.CaptureBackend`, a one-method Protocol:

    def read(self) -> AudioSegment

`AudioPipeline.capture_turn()` calls `read()` once per cycle and appends the
result to the 20-second ring buffer (v4 constants table). So `read()` returns the
audio captured SINCE THE LAST CALL, not a fresh recording of fixed length — the
pipeline owns the rolling window, this owns the device.

FORMAT IS NOT NEGOTIABLE HERE
-----------------------------
`SAMPLE_RATE_HZ = 16_000` and `CHANNELS = 1` are CITED v4 values, and they are
imported from the module that owns them rather than restated. Whisper expects 16
kHz mono, and Silero's VAD chunk size of 512 samples is defined at 16 kHz — a
capture at 44.1 kHz would still "work" in the sense that nothing raises, while
making every downstream chunk boundary mean something different. So the stream is
opened at the pipeline's declared rate and `read()` returns segments tagged with
it; a device that cannot provide it fails at construction.

WHY A CALLBACK AND A QUEUE, NOT A BLOCKING READ
-----------------------------------------------
`capture_turn()` is called from the same thread that then runs wake-word,
verification, VAD and Whisper. A blocking `sounddevice.rec()` would make capture
and processing alternate, so audio arriving during transcription would simply be
lost — and the 20-second pre-roll exists precisely so that the wake word AND the
utterance that follows it are both retained.

`sounddevice.InputStream` with a callback fixes that: PortAudio's own thread
appends to a bounded `deque`, and `read()` drains it. The callback does no work
beyond the append, because it runs under a real-time constraint.

THE BOUND IS A RING, AND DROPPING IS CORRECT
--------------------------------------------
`_queue` is a `deque(maxlen=...)` so a caller that stops calling `read()` cannot
grow memory without limit; the oldest audio is discarded. That is the same
decision `RingBuffer` already makes one layer up, for the same reason: old audio
is worth less than a bounded process. The default holds a few seconds — longer
than the pipeline's own 20 s window would be pointless, since the ring re-buffers
whatever this hands over.

NOTHING IS DECIDED HERE. No VAD, no gain control, no resampling, no noise
suppression. Those would be judgments about the signal, and every gate that acts
on the signal is already a named stage of the pipeline with its own cited
threshold. This is a device read.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Sequence

from daemon.audio_pipeline import CHANNELS, SAMPLE_RATE_HZ, AudioSegment

from adapters._provider import AudioBackendUnavailable, module_available, require_module

#: How much audio the callback may hold before the oldest is dropped. Device
#: plumbing, not a soul number — the pipeline's own 20 s ring buffer is the
#: window that has a spec behind it (v4 constants table).
DEFAULT_QUEUE_SECONDS = 5.0        # TODO(build-time): capture queue depth

#: PortAudio callback block size. Left to the library by default (0 = "you
#: choose"), because a fixed block here would interact with the 512-sample VAD
#: chunking for no stated reason.
DEFAULT_BLOCKSIZE = 0

_SOUNDDEVICE = "sounddevice"
_INSTALL = "pip install sounddevice   (needs PortAudio: brew install portaudio)"


class SoundDeviceCapture:
    """`CaptureBackend` backed by PortAudio via `sounddevice` (v4's named tool).

    Holds a device handle, a bounded queue and the format. No soul state.
    """

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE_HZ,
        channels: int = CHANNELS,
        device: Optional[object] = None,
        queue_seconds: float = DEFAULT_QUEUE_SECONDS,
        blocksize: int = DEFAULT_BLOCKSIZE,
    ) -> None:
        self._sd = require_module(
            _SOUNDDEVICE, purpose="microphone capture", install=_INSTALL
        )
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device
        self._blocksize = blocksize
        self._queue: Deque[float] = deque(
            maxlen=max(1, int(queue_seconds * sample_rate))
        )
        self._stream = None
        self.overflows = 0          # observability only
        self.samples_read = 0

    # -- lifecycle ----------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        """Open the input stream. Idempotent.

        Raises `AudioBackendUnavailable` if the device cannot be opened at the
        pipeline's declared format — better than silently capturing at whatever
        the device preferred, which would move every downstream chunk boundary.
        """
        if self._stream is not None:
            return
        try:
            self._stream = self._sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                device=self._device,
                blocksize=self._blocksize,
                dtype="float32",
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as exc:  # provider raises its own family of errors
            self._stream = None
            raise AudioBackendUnavailable(
                f"could not open the microphone at {self._sample_rate} Hz / "
                f"{self._channels}ch (v4's capture format): {exc}"
            ) from exc

    def stop(self) -> None:
        """Close the stream and drop buffered audio. Idempotent."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            finally:
                self._queue.clear()

    def __enter__(self) -> "SoundDeviceCapture":
        self.start()
        return self

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False

    # -- CaptureBackend -----------------------------------------------------

    def read(self) -> AudioSegment:
        """Drain everything captured since the last call.

        Returns an EMPTY segment when nothing arrived — silence is a legitimate
        answer, and `AudioPipeline.capture_turn` handles it through the ordinary
        wake-word gate rather than needing a special case. Opens the stream on
        first use so a caller that never calls `start()` still works.
        """
        if self._stream is None:
            self.start()
        samples = tuple(self._queue)
        self._queue.clear()
        self.samples_read += len(samples)
        return AudioSegment(
            samples=samples,
            sample_rate=self._sample_rate,
            channels=self._channels,
        )

    # -- PortAudio callback -------------------------------------------------

    def _on_audio(self, indata, frames, time_info, status) -> None:
        """Runs on PortAudio's thread under a real-time constraint.

        Does exactly one thing: flatten and append. No filtering, no logging, no
        allocation beyond the extend — work here causes dropouts, and a dropout
        is data the wake word never sees.
        """
        if status:
            self.overflows += 1
        if self._channels == 1:
            self._queue.extend(float(frame[0]) for frame in indata)
        else:
            # Mix to mono by frame average. v4 captures mono; this only exists so
            # a multi-channel device is usable at all, and it is arithmetic on the
            # signal rather than a judgment about it.
            self._queue.extend(
                sum(float(x) for x in frame) / len(frame) for frame in indata
            )


def available() -> bool:
    """Is the capture provider importable? The non-raising preflight question."""
    return module_available(_SOUNDDEVICE)


def install_hint() -> str:
    return _INSTALL


def list_devices() -> Sequence[str]:
    """Input devices, for a bring-up that needs to pick one. Returns `[]` when the
    provider is absent rather than raising — this is diagnostic output."""
    if not available():
        return []
    sd = require_module(_SOUNDDEVICE, purpose="device listing", install=_INSTALL)
    names = []
    for index, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0:
            names.append(f"{index}: {info.get('name', '?')}")
    return names
