"""Shared PCM format conversion for the audio adapters. One copy, deliberately.

WHY THIS IS ITS OWN MODULE
--------------------------
Four backends need the same conversion: the pipeline's `AudioSegment.samples` are
floats in [-1, 1] (PortAudio's float32 mode), while Porcupine, Silero VAD, Silero
speaker verification and Whisper all want int16 PCM or a bytes buffer of it.

Four copies of "multiply by 32767 and clamp" is four places for an off-by-one, a
missing clamp, or a different rounding rule to appear — and a subtly different
clamp in ONE backend is close to untraceable, because it does not raise. It just
makes that stage slightly deafer than the others.

The same reasoning as `transport_cloud` importing `split_prompt` from
`transport_ollama` instead of copying it: when a property has to hold across two
call sites, one implementation is how it keeps holding.

THE SCALE IS 32767, NOT 32768
-----------------------------
Multiplying by 32768 makes a legitimate sample of exactly +1.0 overflow to
-32768, which is a full-scale sign flip: an audible click, and for a spotter that
looks at frame energy, a spurious transient. Using 32767 and clamping to
[-32768, 32767] cannot overflow in either direction.

NOTHING HERE IS A JUDGMENT ABOUT THE SIGNAL. No gain, no normalisation, no
filtering, no dithering. Only a representation change — which is why it can be
shared without any backend inheriting another's opinion.
"""

from __future__ import annotations

import array
import io
import struct
import wave
from typing import Sequence

#: Full-scale for signed 16-bit PCM. See the module docstring for why not 32768.
INT16_SCALE = 32767
INT16_MIN = -32768
INT16_MAX = 32767


def to_int16(samples: Sequence[float]) -> "array.array":
    """Float samples in [-1, 1] -> signed 16-bit PCM.

    Returns an `array('h')`, which is what the Picovoice and Silero Python APIs
    accept directly and which needs no numpy. Out-of-range input is CLAMPED
    rather than wrapped: a sample above 1.0 is a signal that was already too hot,
    and clipping it is the conventional answer, while wrapping it inverts the
    waveform.
    """
    out = array.array("h", bytes(2 * len(samples)))
    for index, value in enumerate(samples):
        scaled = int(value * INT16_SCALE)
        if scaled > INT16_MAX:
            scaled = INT16_MAX
        elif scaled < INT16_MIN:
            scaled = INT16_MIN
        out[index] = scaled
    return out


def to_int16_bytes(samples: Sequence[float]) -> bytes:
    """The same conversion as raw little-endian bytes, for APIs that want a
    buffer (ONNX Runtime inputs, `wave` frames, an HTTP body)."""
    return to_int16(samples).tobytes()


def from_int16_bytes(payload: bytes) -> Sequence[float]:
    """The inverse: little-endian int16 PCM -> floats in [-1, 1].

    Divides by `INT16_SCALE`, so a round trip through `to_int16` is stable to
    within one quantisation step. Used when a provider hands back PCM.
    """
    count = len(payload) // 2
    values = struct.unpack(f"<{count}h", payload[:count * 2])
    return tuple(v / INT16_SCALE for v in values)


def to_wav_bytes(
    samples: Sequence[float], *, sample_rate: int, channels: int = 1
) -> bytes:
    """Wrap float samples in a WAV container (16-bit PCM).

    `TTSBackend.synthesize` returns "rendered audio bytes (WAV)" and
    `PlaybackBackend.play` takes a WAV, so WAV is the currency of the output
    chain. This exists for the inbound direction too: an STT provider that takes
    a file path or a file-like object needs a real container, and writing one with
    the stdlib `wave` module keeps that from being a reason to add a dependency.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(to_int16_bytes(samples))
    return buffer.getvalue()


def wav_bytes_to_samples(wav: bytes) -> tuple:
    """Read a 16-bit PCM WAV back to `(samples, sample_rate, channels)`.

    Raises `ValueError` on a width this cannot read rather than guessing — a
    32-bit float WAV silently misread as int16 produces noise, and noise that
    plays is harder to diagnose than a refusal.
    """
    with wave.open(io.BytesIO(wav), "rb") as handle:
        width = handle.getsampwidth()
        if width != 2:
            raise ValueError(
                f"expected 16-bit PCM WAV, got {width * 8}-bit. Reading it as "
                f"int16 anyway would produce noise rather than an error."
            )
        frames = handle.readframes(handle.getnframes())
        return (
            from_int16_bytes(frames),
            handle.getframerate(),
            handle.getnchannels(),
        )
