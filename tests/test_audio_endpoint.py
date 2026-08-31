"""Endpointer + QueuedCapture — the wiring layer's two voice-host pieces.

Hermetic: a scripted fake VAD, no model file, no provider, no microphone. The real
Silero arm lives in `tests/test_audio_vad_real_model.py` and skips without the
model; this file is about the state machine and the Protocol conformance, which are
exactly the parts a real model would obscure rather than prove.
"""

from __future__ import annotations

import pytest

from daemon.audio_pipeline import (
    CaptureBackend,
    RING_BUFFER_SECONDS,
    SAMPLE_RATE_HZ,
    VAD_CHUNK_SIZE,
    VAD_THRESHOLD,
    AudioSegment,
)

from adapters.audio_endpoint import (
    DEFAULT_HANGOVER_SECONDS,
    DEFAULT_MIN_SPEECH_SECONDS,
    MAX_UTTERANCE_SECONDS,
    Endpointer,
    QueuedCapture,
)


# ===========================================================================
# Fakes
# ===========================================================================

class ScriptedVAD:
    """Returns a probability per window from a script. Records resets.

    Loud/quiet rather than numbers at the call site: the tests are about the state
    machine, and a caller writing 0.9/0.1 everywhere reads as though the endpointer
    cared about the magnitude, which it does not — it only compares to the
    pipeline's threshold.
    """

    LOUD = 0.99
    QUIET = 0.01

    def __init__(self, script=()) -> None:
        self.script = list(script)
        self.calls = 0
        self.resets = 0

    def speech_probability(self, chunk) -> float:
        assert len(chunk.samples) == VAD_CHUNK_SIZE, (
            "the endpointer must only score whole windows — a partial one is "
            "carried, never padded"
        )
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return self.QUIET


class StatelessVAD:
    """No `reset` at all — the shape of a stateless backend."""
    def speech_probability(self, chunk) -> float:
        return ScriptedVAD.QUIET


def seg(n_samples: int, *, rate: int = SAMPLE_RATE_HZ) -> AudioSegment:
    return AudioSegment(tuple([0.05] * n_samples), rate, 1)


def windows(n: int) -> AudioSegment:
    """`n` whole VAD windows of audio."""
    return seg(n * VAD_CHUNK_SIZE)


def make(vad=None, **kwargs) -> Endpointer:
    return Endpointer(vad=vad if vad is not None else ScriptedVAD(), **kwargs)


def hangover_windows(hangover: float = DEFAULT_HANGOVER_SECONDS) -> int:
    """How many quiet windows it takes to close an utterance."""
    return int(hangover * SAMPLE_RATE_HZ) // VAD_CHUNK_SIZE + 1


# ===========================================================================
# It is not a gate — the structural claims.
# ===========================================================================

def test_endpointer_defines_neither_cited_threshold():
    """`AudioPipeline` owns the 0.5 and 0.75 comparisons. The endpointer READS the
    VAD threshold from the module that owns it, so it cannot drift into a second
    gate. Asserted on the parse tree, not the text: the module docstring discusses
    both numbers at length in order to say it applies neither, and a substring
    search cannot tell an explanation from a use."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("adapters/audio_endpoint.py").read_text())
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "VAD_THRESHOLD" not in assigned
    assert "SPEAKER_THRESHOLD" not in assigned


def test_endpointer_uses_the_pipelines_own_threshold_and_window():
    endpointer = make()
    assert endpointer._threshold == VAD_THRESHOLD
    assert endpointer._chunk == VAD_CHUNK_SIZE


def test_the_utterance_ceiling_is_derived_from_v4s_ring_not_chosen():
    """An utterance longer than the ring cannot be represented downstream, so the
    cap is the cited 20 seconds rather than a new number."""
    assert MAX_UTTERANCE_SECONDS == RING_BUFFER_SECONDS == 20


def test_returned_audio_is_untrimmed_so_the_pipeline_still_owns_the_trim():
    """The whole point of handing over raw audio: trimming here would move the
    cited gate out of Module 7, and would also be able to delete the moment the
    wake word was spoken."""
    quiet = hangover_windows()
    # Enough loud windows to clear the min-speech floor, then enough quiet ones to
    # close. Derived from the constants rather than hardcoded, so retuning either
    # flag cannot silently make this test vacuous.
    loud = int(DEFAULT_MIN_SPEECH_SECONDS * SAMPLE_RATE_HZ) // VAD_CHUNK_SIZE + 2
    vad = ScriptedVAD([ScriptedVAD.LOUD] * loud + [ScriptedVAD.QUIET] * (quiet + 5))
    endpointer = make(vad)
    fed = 0
    utterance = None
    while utterance is None and fed < loud + quiet + 5:
        utterance = endpointer.feed(windows(1))
        fed += 1
    assert utterance is not None
    # Every sample fed is returned — silence included.
    assert len(utterance) == fed * VAD_CHUNK_SIZE


# ===========================================================================
# The state machine.
# ===========================================================================

def test_silence_alone_never_produces_an_utterance():
    endpointer = make(ScriptedVAD())          # always quiet
    for _ in range(200):
        assert endpointer.feed(windows(1)) is None
    assert endpointer.utterances == 0


def test_speech_then_hangover_closes_the_utterance():
    quiet = hangover_windows()
    vad = ScriptedVAD([ScriptedVAD.LOUD] * 10 + [ScriptedVAD.QUIET] * (quiet + 5))
    endpointer = make(vad)

    for _ in range(10):
        assert endpointer.feed(windows(1)) is None, "closed while he was talking"
    assert endpointer.in_speech

    utterance = None
    for _ in range(quiet + 5):
        utterance = endpointer.feed(windows(1))
        if utterance is not None:
            break
    assert utterance is not None
    assert endpointer.last_end_reason == "silence"
    assert endpointer.utterances == 1
    assert not endpointer.in_speech


def test_a_pause_shorter_than_the_hangover_does_not_split_the_utterance():
    """"so... the thing is" must arrive as ONE turn. Splitting mid-sentence would
    appraise half a thought and write it to the graph as a whole one."""
    quiet = hangover_windows()
    vad = ScriptedVAD(
        [ScriptedVAD.LOUD] * 5
        + [ScriptedVAD.QUIET] * (quiet - 2)      # a real pause, but not the end
        + [ScriptedVAD.LOUD] * 5
        + [ScriptedVAD.QUIET] * (quiet + 5)
    )
    endpointer = make(vad)
    closes = 0
    for _ in range(5 + (quiet - 2) + 5):
        if endpointer.feed(windows(1)) is not None:
            closes += 1
    assert closes == 0, "the mid-sentence pause ended the turn"


def test_a_burst_shorter_than_the_floor_is_ignored():
    """A door closing clears the 0.5 gate for a window or two. Without the floor
    each click costs a Whisper call and returns either nothing or an invention."""
    endpointer = make(ScriptedVAD([ScriptedVAD.LOUD] + [ScriptedVAD.QUIET] * 200))
    for _ in range(150):
        assert endpointer.feed(windows(1)) is None
    assert endpointer.utterances == 0
    assert not endpointer.in_speech


def test_two_short_bursts_far_apart_do_not_add_up_to_an_utterance():
    """The non-obvious half of the floor: speech credit has to DECAY, or two
    unrelated clicks a minute apart eventually cross it together."""
    quiet = hangover_windows()
    script = (
        [ScriptedVAD.LOUD]
        + [ScriptedVAD.QUIET] * (quiet + 2)
        + [ScriptedVAD.LOUD]
        + [ScriptedVAD.QUIET] * (quiet + 2)
    )
    endpointer = make(ScriptedVAD(script))
    for _ in range(len(script)):
        assert endpointer.feed(windows(1)) is None
    assert endpointer.utterances == 0


def test_min_speech_floor_is_actually_reached_by_real_speech():
    """Non-vacuous counterpart: the floor must not be so high that ordinary speech
    fails to start an utterance."""
    needed = int(DEFAULT_MIN_SPEECH_SECONDS * SAMPLE_RATE_HZ) // VAD_CHUNK_SIZE + 1
    assert needed < 20, "the floor is implausibly long for a spoken word"
    endpointer = make(ScriptedVAD([ScriptedVAD.LOUD] * needed))
    for _ in range(needed):
        endpointer.feed(windows(1))
    assert endpointer.in_speech


def test_an_overlong_utterance_is_cut_at_the_ring_capacity():
    """Cutting hands over what the ring can hold. Letting the buffer roll instead
    would drop the START of a long utterance, which is the half carrying the wake
    word."""
    endpointer = make(ScriptedVAD([ScriptedVAD.LOUD] * 10_000))
    utterance = None
    for _ in range(10_000):
        utterance = endpointer.feed(windows(1))
        if utterance is not None:
            break
    assert utterance is not None
    assert endpointer.last_end_reason == "max_length"
    assert len(utterance) <= int(MAX_UTTERANCE_SECONDS * SAMPLE_RATE_HZ) + VAD_CHUNK_SIZE


def test_idle_buffer_stays_bounded_so_an_overnight_host_does_not_grow():
    endpointer = make(ScriptedVAD())
    for _ in range(3_000):
        endpointer.feed(windows(1))
    assert endpointer.buffered_seconds <= MAX_UTTERANCE_SECONDS + 1


# ===========================================================================
# Windowing — no padding, and no dropped samples.
# ===========================================================================

def test_partial_windows_are_carried_not_padded():
    """Zero-padding a partial window hands the model an invented tail. At 32 ms per
    window that would happen on most calls, so the invention would be continuous.
    `ScriptedVAD` asserts the window size on every call."""
    endpointer = make(vad := ScriptedVAD())
    endpointer.feed(seg(VAD_CHUNK_SIZE // 2))
    assert vad.calls == 0, "scored a half window"
    endpointer.feed(seg(VAD_CHUNK_SIZE // 2))
    assert vad.calls == 1, "the carried halves did not combine into one window"


def test_no_samples_are_lost_across_ragged_feeds():
    """Audio arrives in whatever blocks PortAudio chose, never aligned to 512."""
    endpointer = make(ScriptedVAD([ScriptedVAD.LOUD] * 500))
    total = 0
    for size in (100, 7, 999, 1, 512, 3000):
        endpointer.feed(seg(size))
        total += size
    assert len(endpointer._buffer) == total


def test_an_empty_segment_is_a_no_op():
    endpointer = make(vad := ScriptedVAD())
    assert endpointer.feed(AudioSegment((), SAMPLE_RATE_HZ, 1)) is None
    assert vad.calls == 0


def test_a_rate_mismatch_is_refused_rather_than_resampled():
    """Same reasoning as the STT adapter: a wrong rate also breaks the 512-sample
    window and the wake-word engine, and resampling would hide the cause."""
    endpointer = make()
    with pytest.raises(ValueError, match="16000"):
        endpointer.feed(seg(VAD_CHUNK_SIZE, rate=44_100))


# ===========================================================================
# Recurrent-state hygiene (ResLog 29C's rule, applied at this layer too).
# ===========================================================================

def test_vad_is_reset_at_construction_and_after_every_utterance():
    quiet = hangover_windows()
    vad = ScriptedVAD([ScriptedVAD.LOUD] * 10 + [ScriptedVAD.QUIET] * (quiet + 5))
    endpointer = make(vad)
    assert vad.resets == 0, "ScriptedVAD has no reset(); see the stateless test"

    class Resettable(ScriptedVAD):
        def reset(self):
            self.resets += 1

    vad = Resettable([ScriptedVAD.LOUD] * 10 + [ScriptedVAD.QUIET] * (quiet + 5))
    endpointer = make(vad)
    assert vad.resets == 1, "not reset at construction"
    for _ in range(10 + quiet + 5):
        if endpointer.feed(windows(1)) is not None:
            break
    assert vad.resets == 2, "not reset after the utterance closed"


def test_a_stateless_vad_needs_no_reset_method():
    """A capability probe, matching `AudioPipeline._reset_vad`. A backend with
    nothing to reset must not have to pretend otherwise."""
    endpointer = Endpointer(vad=StatelessVAD())
    assert endpointer.feed(windows(1)) is None


# ===========================================================================
# QueuedCapture
# ===========================================================================

def test_queued_capture_satisfies_the_capture_protocol():
    """This is what lets `capture_turn()` run unmodified over a pushed utterance."""
    assert isinstance(QueuedCapture(), CaptureBackend)


def test_queued_capture_drains_on_read():
    """`read()`'s contract is "audio since the last call" — the reason exactly one
    consumer may hold a capture backend."""
    capture = QueuedCapture()
    capture.push(seg(100))
    assert len(capture.read()) == 100
    assert len(capture.read()) == 0


def test_queued_capture_returns_empty_when_nothing_was_pushed():
    """`capture_turn` handles an empty read through the ordinary wake-word gate,
    so this needs no special case downstream."""
    assert len(QueuedCapture().read()) == 0


def test_queued_capture_never_drops_what_was_pushed():
    """Deliberately not a ring. `SoundDeviceCapture` bounds its queue because old
    DEVICE audio is worth less than a bounded process; here the producer is a host
    handing over one finished utterance, and dropping any of it loses real speech."""
    capture = QueuedCapture()
    big = int(MAX_UTTERANCE_SECONDS * SAMPLE_RATE_HZ) * 2
    capture.push(seg(big))
    assert len(capture.read()) == big


def test_queued_capture_refuses_a_rate_mismatch():
    with pytest.raises(ValueError, match="16000"):
        QueuedCapture().push(seg(10, rate=8_000))
