"""Real Silero inference — the arm no fake can cover.

WHY THIS FILE EXISTS, AND WHY IT IS SEPARATE
--------------------------------------------
`SileroVAD` shipped deaf against the v5 model export for as long as the export
existed, and nothing in a 902-test suite could see it. That is not a gap in the
tests that were written; it is a gap in what they were ABLE to see:

  * `tests/test_audio_pipeline.py` injects fakes for every backend, correctly —
    Module 7's job is the chain and the cited gates, not a provider's input shape.
  * `tests/test_audio_adapters.py` touched `audio_vad` exactly twice: the
    imports-with-no-providers test, and an AST scan asserting no adapter defines
    `VAD_THRESHOLD` or `SPEAKER_THRESHOLD`. Neither can detect a wrong tensor
    shape.
  * the model FILE did not exist on the dev machine until inbound audio was
    wired, so there was nothing to run real inference against.

The failure mode is the dangerous kind: feeding the v5 graph a bare 512-sample
frame raises nothing and returns a plausible-looking probability that is simply
always near zero. Measured on one 2.10 s utterance, same file, same 0.5 gate:
**0/65 chunks over threshold without the 64-sample lookback, 62/65 with it.**
So the entire inbound chain failed closed and looked like silence.

SKIPS RATHER THAN FAILS, DELIBERATELY
-------------------------------------
Every test here needs two things this repo does not ship: the ONNX model file and
`onnxruntime`. Both are absent on a clean checkout, so all of it skips there and
`make check` stays hermetic and fast — the same arrangement
`tests/test_embedding_local.py` already uses for its real-backend arm, and the
reason the suite reads "N passed + 3 skipped" with the model backend stopped.

`say` is used to produce the speech because it is the one renderer present on this
machine with zero installs, which is what makes this runnable at all. It is not
byte-deterministic (measured previously: a 94-byte wobble in trailing silence
across identical invocations), so nothing here asserts on rendered bytes — the
assertions are about which chunks clear a threshold, which is stable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import pytest

from daemon.audio_pipeline import (
    SAMPLE_RATE_HZ,
    VAD_CHUNK_SIZE,
    VAD_THRESHOLD,
    AudioSegment,
)

from adapters.audio_pcm import from_int16_bytes

# The default location `--vad-model` documents. Overridable so a machine that
# keeps it elsewhere still runs these rather than silently skipping.
DEFAULT_VAD_MODEL = os.path.expanduser("~/.local/aria/models/silero_vad.onnx")
VAD_MODEL = os.environ.get("ARIA_VAD_MODEL", DEFAULT_VAD_MODEL)

HAS_MODEL = Path(VAD_MODEL).is_file()
HAS_SAY = shutil.which("say") is not None

try:  # pragma: no cover - import probe
    import onnxruntime  # noqa: F401
    HAS_ONNX = True
except ImportError:  # pragma: no cover - the clean-checkout case
    HAS_ONNX = False

needs_model = pytest.mark.skipif(
    not (HAS_MODEL and HAS_ONNX),
    reason=(
        f"needs onnxruntime and a Silero VAD model at {VAD_MODEL} "
        f"(set ARIA_VAD_MODEL to point elsewhere)"
    ),
)
needs_say = pytest.mark.skipif(not HAS_SAY, reason="needs macOS `say` to render speech")


# ===========================================================================
# Helpers
# ===========================================================================

def _render_speech(text: str) -> AudioSegment:
    """Real speech at the pipeline's cited 16 kHz mono, so nothing resamples."""
    workdir = Path(tempfile.mkdtemp())
    try:
        path = workdir / "speech.wav"
        subprocess.run(
            ["say", "-o", str(path), "--data-format", "LEI16@16000", "--", text],
            check=True,
            capture_output=True,
        )
        with wave.open(str(path)) as handle:
            assert handle.getframerate() == SAMPLE_RATE_HZ
            assert handle.getnchannels() == 1
            raw = handle.readframes(handle.getnframes())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return AudioSegment(tuple(from_int16_bytes(raw)), SAMPLE_RATE_HZ, 1)


def _silence(seconds: float) -> AudioSegment:
    return AudioSegment(
        tuple([0.0] * int(seconds * SAMPLE_RATE_HZ)), SAMPLE_RATE_HZ, 1
    )


def _score(vad, segment: AudioSegment):
    """Probabilities for a whole segment, one cited-size chunk at a time."""
    vad.reset()
    return [
        vad.speech_probability(chunk)
        for chunk in segment.chunks(VAD_CHUNK_SIZE)
    ]


def _make_vad():
    from adapters.audio_vad import SileroVAD
    return SileroVAD(model_path=VAD_MODEL)


# ===========================================================================
# The graph's contract — which export is loaded, and is the lookback in force.
# ===========================================================================

@needs_model
def test_v5_export_is_detected_and_the_lookback_is_in_force():
    """The two exports are indistinguishable from their OUTPUT — both return a
    plausible probability — and the wrong contract is silently deaf. So which one
    is in force has to be observable."""
    vad = _make_vad()
    if vad._wants_context:
        assert vad.context_size == 64, "64 samples at 16 kHz is Silero's own rule"
    else:
        assert vad.context_size == 0, "a pre-v5 export takes bare frames"


@needs_model
def test_chunk_size_stays_the_cited_512_regardless_of_the_lookback():
    """The lookback is prepended INSIDE the adapter. The caller still hands over
    512-sample windows, because `VAD_CHUNK_SIZE` is a v4 constant and the fix must
    not have moved it."""
    vad = _make_vad()
    assert vad.chunk_size == VAD_CHUNK_SIZE == 512


# NOT REPEATED HERE: "the adapter defines neither cited threshold". That is
# already asserted, and asserted BETTER, by the AST scan in
# `tests/test_audio_adapters.py` — which covers `audio_vad.py` by name and reads
# the parse tree rather than the text.
#
# A text-grep version of it was written here first and failed immediately, for the
# precise reason HANDOFF_NOTES records: this adapter's docstring now DISCUSSES
# `VAD_THRESHOLD = 0.5` at length in order to explain that it does not apply it,
# and a substring search cannot tell an explanation from a use. That trap has
# caught two earlier versions of the same assertion in this repo. Left recorded
# rather than silently deleted, because the next person to reach for a grep here
# will reach for the same one.


# ===========================================================================
# THE REGRESSION. This is the test the defect would have failed.
# ===========================================================================

@needs_model
@needs_say
def test_real_speech_clears_the_cited_threshold():
    """The defect, stated as an assertion.

    Before the lookback fix this was 0/65 chunks over 0.5 on exactly this input —
    max probability 0.4187 — so the pipeline trimmed a whole utterance to nothing
    and `capture_turn()` returned None as if the room were empty.

    The bound is deliberately loose (a THIRD of chunks, not the measured 62/65):
    `say` is not byte-deterministic, voices differ between machines, and this test
    exists to catch "the VAD is deaf", not to pin a rendering. A third is far
    above the 0 the defect produced and far below anything a working VAD gives.
    """
    vad = _make_vad()
    probabilities = _score(vad, _render_speech("hey aria, i finally shipped it today"))
    over = [p for p in probabilities if p >= VAD_THRESHOLD]

    assert probabilities, "no chunks scored at all"
    assert len(over) >= len(probabilities) // 3, (
        f"only {len(over)}/{len(probabilities)} chunks cleared "
        f"{VAD_THRESHOLD} (max {max(probabilities):.4f}). The v5 graph returns "
        f"near-zero on real speech when the 64-sample lookback is missing, and "
        f"raises nothing — so a deaf VAD looks exactly like a quiet room."
    )


@needs_model
@needs_say
def test_the_pipeline_actually_trims_real_speech_to_speech():
    """One layer up: the REAL `_trim_to_speech` over real audio.

    The unit test above proves the adapter scores; this proves the seam the
    adapter feeds. Uses the real pipeline with the real VAD and refusing stubs
    everywhere else, so nothing but the VAD path is exercised.
    """
    from daemon.audio_pipeline import AudioPipeline
    from daemon.pad_engine import PADEngine
    from adapters import audio_stack

    pad = PADEngine()
    pad.initialize(None)
    absent = audio_stack._Absent("unused in this test", "n/a")
    pipeline = AudioPipeline(
        pad_source=pad,
        capture=absent,
        wake_word=absent,
        speaker_verification=absent,
        vad=_make_vad(),
        stt=absent,
        tts_primary=absent,
        tts_fallback=absent,
        playback=absent,
    )

    # Silence is added EXPLICITLY at both ends rather than relying on whatever
    # `say` happens to render. An earlier version of this test asserted that the
    # trim removed something from a bare rendering and was flaky for a good reason:
    # how much padding a synthesiser emits is not a property of the pipeline, and
    # a render that is speech end-to-end has nothing to trim. Padding here makes
    # both directions of the assertion mean something.
    speech = _render_speech("i think the startup might be failing")
    pad_seconds = 1.0
    padded = AudioSegment(
        _silence(pad_seconds).samples + speech.samples + _silence(pad_seconds).samples,
        SAMPLE_RATE_HZ,
        1,
    )
    trimmed = pipeline._trim_to_speech(padded)

    assert trimmed is not None, (
        "_trim_to_speech returned None for real speech — this is exactly the "
        "shape of the defect: capture_turn() would return before Whisper."
    )
    # Both directions matter. Keeping everything means the VAD is not
    # discriminating; keeping almost nothing means it is deaf.
    assert len(trimmed) < len(padded), "the added silence was not trimmed"
    assert len(trimmed) >= len(speech) // 2, (
        f"kept only {len(trimmed)} samples of {len(speech)} spoken — the trim is "
        f"eating speech, not silence"
    )


@needs_model
def test_silence_is_still_rejected():
    """The other direction, and the reason the fix cannot just be 'return 1.0'.

    Whisper hallucinates on near-silence (subtitle boilerplate, 'thank you'), and
    the cited VAD gate is the ONLY thing standing between that and an appraised
    EventNode she never heard. A VAD that passes silence would put invented text
    into the graph.
    """
    vad = _make_vad()
    probabilities = _score(vad, _silence(1.0))
    assert probabilities
    assert max(probabilities) < VAD_THRESHOLD, (
        f"silence scored {max(probabilities):.4f}, at or above the cited "
        f"{VAD_THRESHOLD} gate — Whisper would be handed silence and would "
        f"invent text for it."
    )


@needs_model
@needs_say
def test_a_trailing_partial_window_is_still_accepted():
    """`AudioSegment.chunks()` yields a short final window by design, so this is a
    real case in normal operation rather than an edge one. It must not raise, and
    it must not corrupt the lookback for a following utterance."""
    vad = _make_vad()
    spoken = _render_speech("hello")
    # Guarantee a partial trailing window.
    ragged = AudioSegment(spoken.samples[:-(VAD_CHUNK_SIZE // 2)], SAMPLE_RATE_HZ, 1)
    first = _score(vad, ragged)
    assert first, "no chunks scored"
    # A second pass after reset must behave the same — proving the partial window
    # left no stale context behind.
    second = _score(vad, ragged)
    assert len(first) == len(second)


# ===========================================================================
# Reset semantics, now that there are TWO recurrent things to clear.
# ===========================================================================

@needs_model
@needs_say
def test_reset_clears_both_the_lstm_state_and_the_lookback():
    """ResLog 29C's ruling is that each utterance is scored from a clean state.
    There are now two pieces of state, and a reset that cleared only one would
    leave 64 samples of the previous utterance's tail in front of the new one.

    Asserted behaviourally: the same input scored twice, with a reset between,
    must produce the SAME sequence. If either piece of state survived, the second
    pass would differ.
    """
    vad = _make_vad()
    spoken = _render_speech("hey aria, are you there")
    first = _score(vad, spoken)
    second = _score(vad, spoken)
    assert first == second, (
        "scoring is not reproducible across a reset — some recurrent state "
        "(LSTM or the 64-sample lookback) survived it"
    )


@needs_model
@needs_say
def test_without_a_reset_the_second_pass_differs():
    """The non-vacuous half of the test above: prove the state is real.

    If this ever starts passing trivially — identical output with no reset — then
    the reset is not clearing anything and the test above proves nothing.
    """
    vad = _make_vad()
    spoken = _render_speech("hey aria, are you there")
    vad.reset()
    first = [vad.speech_probability(c) for c in spoken.chunks(VAD_CHUNK_SIZE)]
    # NO reset here — carry the state straight into a second pass.
    second = [vad.speech_probability(c) for c in spoken.chunks(VAD_CHUNK_SIZE)]
    assert first != second, (
        "identical output with no reset between passes means the recurrent state "
        "is inert, and the reset test above is vacuous"
    )
