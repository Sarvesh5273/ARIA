"""The inbound chain end to end: real audio in, real transcript out.

WHAT THIS COVERS THAT NOTHING ELSE DOES
---------------------------------------
`tests/test_audio_pipeline.py` proves the chain's LOGIC with fakes.
`tests/test_audio_endpoint.py` proves the endpointer's state machine with a
scripted VAD. Neither runs a real utterance through real Silero and real Whisper,
and the VAD lookback defect is the standing proof that a chain can be green at
every unit boundary and still be deaf end to end.

So this file assembles what `voice_main.py` assembles — endpointer, queued capture,
real VAD, real Whisper, the real `AudioPipeline` with its cited gates — feeds it
rendered speech, and asserts words come out.

Skips without `onnxruntime`, the VAD model or `say`, so `make check` stays hermetic.
Nothing here needs a microphone, a model backend, Ollama, or a graph.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import pytest

from daemon.audio_pipeline import SAMPLE_RATE_HZ, AudioPipeline, AudioSegment
from daemon.pad_engine import PADEngine

from adapters.audio_endpoint import Endpointer, QueuedCapture
from adapters.audio_pcm import from_int16_bytes
from adapters.audio_wake import HotkeyWakeWord

VAD_MODEL = os.environ.get(
    "ARIA_VAD_MODEL", os.path.expanduser("~/.local/aria/models/silero_vad.onnx")
)
HAS_SAY = shutil.which("say") is not None

try:  # pragma: no cover - import probe
    import onnxruntime  # noqa: F401
    import faster_whisper  # noqa: F401
    HAS_PROVIDERS = True
except ImportError:  # pragma: no cover - clean checkout
    HAS_PROVIDERS = False

pytestmark = pytest.mark.skipif(
    not (HAS_PROVIDERS and HAS_SAY and Path(VAD_MODEL).is_file()),
    reason=(
        "needs onnxruntime + faster-whisper + macOS `say` + a Silero VAD model "
        f"at {VAD_MODEL}"
    ),
)

PHRASE = "i finally shipped it today and it actually works"


# ===========================================================================
# Assembly — mirrors voice_main.VoiceWiring._build_audio, minus the soul layer.
# ===========================================================================

def _render(text: str) -> AudioSegment:
    workdir = Path(tempfile.mkdtemp())
    try:
        path = workdir / "speech.wav"
        subprocess.run(
            ["say", "-o", str(path), "--data-format", "LEI16@16000", "--", text],
            check=True,
            capture_output=True,
        )
        with wave.open(str(path)) as handle:
            raw = handle.readframes(handle.getnframes())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return AudioSegment(tuple(from_int16_bytes(raw)), SAMPLE_RATE_HZ, 1)


def _silence(seconds: float) -> AudioSegment:
    return AudioSegment(
        tuple([0.0] * int(seconds * SAMPLE_RATE_HZ)), SAMPLE_RATE_HZ, 1
    )


class _Refuses:
    """Occupies the slots this test does not exercise. Raises if touched, so a
    chain that reaches the wrong backend fails loudly instead of passing."""
    def similarity(self, audio):
        raise AssertionError("speaker backend should not be reached here")
    def synthesize(self, text, prosody):
        raise AssertionError("TTS should not be reached by the inbound chain")
    def play(self, wav):
        raise AssertionError("playback should not be reached by the inbound chain")
    def play_cached(self, key):
        raise AssertionError("playback should not be reached by the inbound chain")
    def stop(self):
        raise AssertionError("playback should not be reached by the inbound chain")


class _AlwaysThisSpeaker:
    """Stands in for `voice_main.DeferredSpeakerVerification` so the cited 0.75
    gate is exercised rather than bypassed — the pipeline still applies it."""
    def similarity(self, audio) -> float:
        return 1.0


def _build(speaker=None):
    from adapters.audio_stt import FasterWhisperSTT
    from adapters.audio_vad import SileroVAD

    pad = PADEngine()
    pad.initialize(None)
    capture = QueuedCapture()
    wake = HotkeyWakeWord()
    pipeline = AudioPipeline(
        pad_source=pad,
        capture=capture,
        wake_word=wake,
        speaker_verification=speaker if speaker is not None else _AlwaysThisSpeaker(),
        vad=SileroVAD(model_path=VAD_MODEL),
        stt=FasterWhisperSTT(model_size="base"),
        tts_primary=_Refuses(),
        tts_fallback=_Refuses(),
        playback=_Refuses(),
    )
    endpointer = Endpointer(vad=SileroVAD(model_path=VAD_MODEL))
    return pipeline, capture, wake, endpointer


def _drive(pipeline, capture, wake, endpointer, audio: AudioSegment):
    """What `run_voice_loop` does for one turn, minus the Daemon.

    Feeds audio in ragged blocks on purpose — PortAudio never aligns to the VAD
    window, and a loop that only worked on aligned input would pass here and fail
    against a device.
    """
    utterance = None
    step = 1024
    for start in range(0, len(audio.samples), step):
        block = AudioSegment(
            audio.samples[start:start + step], SAMPLE_RATE_HZ, 1
        )
        utterance = endpointer.feed(block)
        if utterance is not None:
            break
    if utterance is None:
        # Trailing quiet closes it, exactly as a real pause would.
        utterance = endpointer.feed(_silence(2.0))
    assert utterance is not None, "the endpointer never closed the utterance"

    pipeline._ring.clear()
    wake.trigger()
    capture.push(utterance)
    return pipeline.capture_turn()


# ===========================================================================
# The end-to-end claim.
# ===========================================================================

def test_real_speech_becomes_real_text():
    """The whole inbound chain over real audio.

    This is the test the VAD lookback defect would have failed: `_trim_to_speech`
    returned None for every utterance, so `capture_turn()` returned before Whisper
    and this would have been None rather than words.

    Asserted on CONTENT WORDS rather than an exact string. `say`'s synthetic voice
    is not what Whisper was trained on and mis-hears some words (measured: "hey
    aria" came back as "Here RIO"), and `say` is not byte-deterministic across
    invocations. Pinning an exact transcript would make this a test of one voice on
    one machine. What must hold is that speech becomes words, in order.
    """
    pipeline, capture, wake, endpointer = _build()
    text = _drive(pipeline, capture, wake, endpointer, _render(PHRASE))

    assert text, "the inbound chain produced no text for real speech"
    lowered = text.lower()
    found = [word for word in ("shipped", "today", "works") if word in lowered]
    assert len(found) >= 2, (
        f"transcript {text!r} shares too little with {PHRASE!r} — the chain "
        f"produced text but not this utterance's text"
    )


def test_silence_produces_no_turn_and_never_reaches_whisper():
    """The other direction, and it is the one that protects the graph.

    Whisper invents text for near-silence (subtitle boilerplate, "thank you"). The
    cited VAD trim is what stops that becoming an appraised EventNode she never
    heard, so this asserts the gate holds over REAL silence and a real model.
    """
    pipeline, capture, wake, endpointer = _build()
    pipeline._ring.clear()
    wake.trigger()
    capture.push(_silence(3.0))
    assert pipeline.capture_turn() is None


def test_the_wake_gate_still_blocks_a_full_utterance():
    """No trigger, no transcription — even with a complete utterance waiting. The
    wake word is the only thing between a live microphone and a transcription, so
    this asserts the endpointer did not route around it."""
    pipeline, capture, wake, endpointer = _build()
    pipeline._ring.clear()
    capture.push(_render("this should never be transcribed"))
    assert pipeline.capture_turn() is None, "transcribed without being addressed"


def test_the_cited_speaker_gate_still_rejects_a_stranger():
    """`DeferredSpeakerVerification` passes everyone, but the GATE it passes is
    still the pipeline's. A backend below 0.75 must still be refused — that is what
    makes the deferral a substituted backend rather than a removed threshold."""
    class Stranger:
        def similarity(self, audio) -> float:
            return 0.74      # just under v4's cited 0.75

    pipeline, capture, wake, endpointer = _build(speaker=Stranger())
    pipeline._ring.clear()
    wake.trigger()
    capture.push(_render(PHRASE))
    assert pipeline.capture_turn() is None


def test_two_utterances_in_a_row_do_not_bleed_into_each_other():
    """The reason the ring is cleared between turns.

    `capture_turn()` trims THE WHOLE RING, so without a clear the second turn would
    re-transcribe the first utterance alongside the new one — she would hear the
    previous sentence again, appraise it again, and write a second EventNode for
    something said once.
    """
    pipeline, capture, wake, endpointer = _build()
    first = _drive(pipeline, capture, wake, endpointer, _render("the deploy failed"))
    second = _drive(pipeline, capture, wake, endpointer, _render("but the tests pass"))

    assert first and second
    assert "deploy" not in second.lower(), (
        f"the first utterance bled into the second: {second!r}"
    )
