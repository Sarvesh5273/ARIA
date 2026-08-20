"""Tests for Module 7 — Audio Pipeline.

Locked spec: .kiro/specs/audio-pipeline/{requirements,design,tasks}.md.

Plain pytest, NO hypothesis (matches Modules 1–6 style). These prove the
PHILOSOPHY contracts of the Audio Pipeline, not just behavior:

  * F4 / BARGE-IN → ZERO INTERNAL EFFECT (tripwire): stop_playback() leaves PAD
    byte-identical, never CALLS a PAD mutator, and never even READS PAD — the
    ONLY effect is playback.stop(). No graph/state/appraisal collaborator exists
    to mutate. (Addendum §5; project-rules.md PAD-purity)
  * PAD → PROSODY is a READ applied at TTS-generation time, varying the TTS
    parameters in the v4 Layer 5 DIRECTIONS when PAD changes — and NEVER writing
    PAD. (v4 Layer 5; project-rules.md "presentation read of substrate")
  * STT PRODUCES TRANSCRIBED TEXT OUT (input chain wake→verify→VAD→STT); the
    pipeline transcribes, it does NOT appraise. (Build Plan Module 7 Outputs)
  * CLOUD-TTS FAILURE FALLS BACK TO KOKORO (cloud primary, local fallback).
    (v4 "Graceful Degradation"; no provider hardcoded — Rule 6)
  * SATISFIES the Daemon's AudioPipelinePort — structurally (isinstance) AND
    end-to-end (the REAL AriaDaemon drives all four port methods through it).

Structural proofs (source scans) back the tripwire: the module never imports a
write-capable module and the PAD-write CALL never appears in it.
"""

import inspect
from typing import Optional

import pytest

import daemon.audio_pipeline as ap_mod
from daemon.audio_pipeline import (
    AudioPipeline,
    AudioSegment,
    Prosody,
    RingBuffer,
    TTSUnavailable,
    map_pad_to_prosody,
    RECONSIDERATION_SOUND_KEY,
    SPEAKER_THRESHOLD,
    VAD_THRESHOLD,
    VAD_CHUNK_SIZE,
    RING_BUFFER_SECONDS,
    SAMPLE_RATE_HZ,
    CHANNELS,
    BARGE_IN_WINDOW_SECONDS,
)
from daemon.aria_daemon import AudioPipelinePort
from daemon.pad_engine import PADEngine, PADSnapshot, PADDelta, Valence, PAD_BASELINE

# Reuse the canonical REAL-daemon wiring for the end-to-end contract test. Both
# files live in tests/ (pytest prepends it to sys.path); importing only runs
# test_daemon's module-level defs — it does NOT re-collect its tests.
from test_daemon import make_daemon, T0


# ===========================================================================
# Fakes for the INJECTED backends (Rule 6). Deterministic; record calls.
# ===========================================================================
class StubPAD:
    """Read-only PAD source (satisfies PADReader). Returns a settable snapshot;
    counts reads so we can prove a stop never reads PAD. Has NO mutator — the
    prosody seam is structurally read-only."""
    def __init__(self, pleasure=0.55, arousal=0.45, dominance=0.58):
        self._snap = PADSnapshot(pleasure=pleasure, arousal=arousal, dominance=dominance)
        self.reads = 0

    def set(self, pleasure, arousal, dominance):
        self._snap = PADSnapshot(pleasure=pleasure, arousal=arousal, dominance=dominance)

    def get_current_pad(self) -> PADSnapshot:
        self.reads += 1
        return self._snap


class SpyPAD(PADEngine):
    """The REAL PADEngine, instrumented to count PAD reads AND PAD-mutator calls
    — a live tripwire proving stop_playback() touches PAD in NO way."""
    def __init__(self):
        super().__init__()
        self.reads = 0
        self.writes = 0

    def get_current_pad(self) -> PADSnapshot:
        self.reads += 1
        return super().get_current_pad()

    def apply_appraisal_delta(self, delta) -> None:
        self.writes += 1
        return super().apply_appraisal_delta(delta)


class FakeCapture:
    """Microphone capture backend. Returns a canned segment each read()."""
    def __init__(self, segment: AudioSegment):
        self.segment = segment
        self.reads = 0

    def read(self) -> AudioSegment:
        self.reads += 1
        return self.segment


class FakeWake:
    """Wake-word backend. `awake` controls whether the wake word is detected."""
    def __init__(self, awake=True):
        self.awake = awake
        self.calls = 0

    def detect(self, audio) -> bool:
        self.calls += 1
        return self.awake


class FakeSpeaker:
    """Speaker-verification backend. Returns a fixed cosine similarity."""
    def __init__(self, score=0.9):
        self.score = score
        self.calls = 0

    def similarity(self, audio) -> float:
        self.calls += 1
        return self.score


class FakeVAD:
    """VAD backend. A chunk is speech iff ANY of its samples is non-zero
    (silence = all zeros). Lets tests build utterances with leading/trailing
    silence and prove trimming."""
    def __init__(self):
        self.calls = 0

    def speech_probability(self, chunk) -> float:
        self.calls += 1
        return 1.0 if any(s != 0.0 for s in chunk.samples) else 0.0


class FakeSTT:
    """Whisper STT backend. Returns a canned transcript and records the audio it
    was handed (so we can assert VAD trimming)."""
    def __init__(self, transcript="hey aria, i shipped it today"):
        self.transcript = transcript
        self.received: Optional[AudioSegment] = None

    def transcribe(self, audio) -> str:
        self.received = audio
        return self.transcript


class FakeTTS:
    """A TTS backend. Records (text, prosody) per call and returns tagged WAV
    bytes. If `fail` is set, raises to exercise the fallback path."""
    def __init__(self, name, fail: Optional[BaseException] = None):
        self.name = name
        self.fail = fail
        self.calls = []  # list of (text, Prosody)

    def synthesize(self, text: str, prosody: Prosody) -> bytes:
        self.calls.append((text, prosody))
        if self.fail is not None:
            raise self.fail
        return b"WAV:" + self.name.encode() + b":" + text.encode()


class FakePlayback:
    """Audio output backend. Records everything so the tripwire can prove a stop
    does nothing but stop, and the contract test can prove speak() played."""
    def __init__(self):
        self.played = []          # WAV bytes passed to play()
        self.play_cached_keys = []  # keys passed to play_cached()
        self.stops = 0

    def play(self, wav) -> None:
        self.played.append(wav)

    def play_cached(self, key) -> None:
        self.play_cached_keys.append(key)

    def stop(self) -> None:
        self.stops += 1


# ===========================================================================
# Builders.
# ===========================================================================
def seg(samples):
    return AudioSegment(tuple(float(s) for s in samples), SAMPLE_RATE_HZ, CHANNELS)


def _speech_segment(n=VAD_CHUNK_SIZE):
    """A pure-speech segment (all-ones) of one chunk."""
    return seg([1.0] * n)


def make_pipeline(
    *,
    pad_source=None,
    capture_segment=None,
    awake=True,
    speaker_score=0.9,
    transcript="hey aria, i shipped it today",
    primary_fail=None,
    fallback_fail=None,
    playback=None,
):
    pad_source = pad_source if pad_source is not None else StubPAD()
    capture_segment = capture_segment if capture_segment is not None else _speech_segment()
    primary = FakeTTS("cloud", fail=primary_fail)
    fallback = FakeTTS("kokoro", fail=fallback_fail)
    playback = playback if playback is not None else FakePlayback()
    pipe = AudioPipeline(
        pad_source=pad_source,
        capture=FakeCapture(capture_segment),
        wake_word=FakeWake(awake=awake),
        speaker_verification=FakeSpeaker(score=speaker_score),
        vad=FakeVAD(),
        stt=FakeSTT(transcript=transcript),
        tts_primary=primary,
        tts_fallback=fallback,
        playback=playback,
    )
    # expose the fakes for assertions
    pipe._t_primary = primary
    pipe._t_fallback = fallback
    pipe._t_playback = playback
    return pipe


# ===========================================================================
# 1) INPUT CHAIN — STT produces transcribed text OUT; gates; VAD trimming.
#    (Build Plan Module 7 Outputs; v4 "The Daemon — Audio Flow")
# ===========================================================================
def test_capture_turn_transcribes_text_out():
    """wake→verify→VAD→Whisper STT → transcribed text OUT (to the Daemon)."""
    pipe = make_pipeline(transcript="hey aria, i finally shipped it today")
    text = pipe.capture_turn()
    assert text == "hey aria, i finally shipped it today"


def test_capture_turn_returns_none_when_not_woken():
    """No wake word → nothing transcribes (the STT never even runs)."""
    pipe = make_pipeline(awake=False)
    assert pipe.capture_turn() is None


def test_capture_turn_rejects_unverified_speaker():
    """Cosine below the 0.75 gate → dropped, not transcribed (v4)."""
    pipe = make_pipeline(speaker_score=0.5)
    assert pipe.capture_turn() is None


def test_capture_turn_accepts_speaker_at_exactly_threshold():
    """Cosine == 0.75 passes (gate is >=)."""
    pipe = make_pipeline(speaker_score=SPEAKER_THRESHOLD)
    assert pipe.capture_turn() == "hey aria, i shipped it today"


def test_capture_turn_returns_none_on_silence():
    """VAD finds no speech (all-zero samples) → None (no utterance)."""
    silent = seg([0.0] * (VAD_CHUNK_SIZE * 3))
    pipe = make_pipeline(capture_segment=silent)
    assert pipe.capture_turn() is None


def test_vad_trims_nonspeech_boundaries():
    """VAD trims leading/trailing silence: Whisper receives only speech chunks
    (v4: chunk 512, threshold 0.5)."""
    # [silence chunk][speech chunk][silence chunk]
    samples = ([0.0] * VAD_CHUNK_SIZE) + ([1.0] * VAD_CHUNK_SIZE) + ([0.0] * VAD_CHUNK_SIZE)
    pipe = make_pipeline(capture_segment=seg(samples))
    text = pipe.capture_turn()
    assert text == "hey aria, i shipped it today"
    # STT got exactly ONE chunk of speech — boundaries trimmed.
    assert len(pipe._stt.received) == VAD_CHUNK_SIZE
    assert all(s == 1.0 for s in pipe._stt.received.samples)


def test_capture_turn_does_not_appraise_or_judge():
    """The pipeline only transcribes — it holds no appraisal/graph collaborator
    and returns the raw STT string (constraint 3). Proven structurally too."""
    pipe = make_pipeline(transcript="i think the startup might be failing")
    out = pipe.capture_turn()
    # Returned verbatim — no interpretation, scoring, or judgement applied.
    assert out == "i think the startup might be failing"


# ===========================================================================
# 2) v4 CITED CONSTANTS (Rule 4 "no invented numbers").
# ===========================================================================
def test_v4_cited_constants():
    assert SPEAKER_THRESHOLD == 0.75          # v4 constants table
    assert VAD_THRESHOLD == 0.5               # v4 constants table
    assert VAD_CHUNK_SIZE == 512              # v4 constants table
    assert RING_BUFFER_SECONDS == 20          # v4 constants table
    assert SAMPLE_RATE_HZ == 16_000           # v4 audio flow (16 kHz)
    assert CHANNELS == 1                       # v4 audio flow (mono)
    assert BARGE_IN_WINDOW_SECONDS == 0.75    # v4 (window owned by aria_daemon.py)


# ===========================================================================
# 3) RING BUFFER — 20s rolling pre-roll (v4).
# ===========================================================================
def test_ring_buffer_capacity_is_20s_at_16khz():
    pipe = make_pipeline()
    assert pipe._ring.capacity_samples == RING_BUFFER_SECONDS * SAMPLE_RATE_HZ == 320_000


def test_ring_buffer_evicts_oldest_beyond_capacity():
    rb = RingBuffer(capacity_samples=5, sample_rate=SAMPLE_RATE_HZ)
    rb.append(seg([1, 2, 3, 4]))
    rb.append(seg([5, 6, 7]))  # total 7 → keep last 5
    assert rb.snapshot().samples == (3.0, 4.0, 5.0, 6.0, 7.0)


# ===========================================================================
# 4) PAD → PROSODY — read of substrate, v4 Layer 5 DIRECTIONS, never a write.
# ===========================================================================
def test_prosody_pleasure_increases_noise_scale():
    """Pleasure → noise_scale: higher pleasure = warmer/more resonant (v4)."""
    low = map_pad_to_prosody(PADSnapshot(0.2, 0.5, 0.5))
    high = map_pad_to_prosody(PADSnapshot(0.8, 0.5, 0.5))
    assert high.noise_scale > low.noise_scale


def test_prosody_arousal_is_inverse_on_length_scale():
    """Arousal → length_scale INVERSE: higher arousal = faster = shorter
    length_scale (v4)."""
    low = map_pad_to_prosody(PADSnapshot(0.5, 0.2, 0.5))
    high = map_pad_to_prosody(PADSnapshot(0.5, 0.8, 0.5))
    assert high.length_scale < low.length_scale


def test_prosody_dominance_lowers_pitch_shift():
    """Dominance → pitch_shift: higher dominance = lower, more grounded (v4)."""
    low = map_pad_to_prosody(PADSnapshot(0.5, 0.5, 0.2))
    high = map_pad_to_prosody(PADSnapshot(0.5, 0.5, 0.8))
    assert high.pitch_shift < low.pitch_shift


def test_prosody_is_a_pure_function_of_pad():
    """Same PAD → same prosody; no hidden state, no feeling computed."""
    p = PADSnapshot(0.6, 0.4, 0.7)
    assert map_pad_to_prosody(p) == map_pad_to_prosody(p)


def test_speak_reads_pad_at_generation_time_and_varies_prosody():
    """speak() reads the LIVE PAD at generation time (v4 Layer 5). When PAD
    changes, the prosody handed to the TTS backend changes in the v4 directions
    — proving a generation-time READ (not a cached/constant value)."""
    pad = StubPAD(pleasure=0.3, arousal=0.3, dominance=0.3)
    pipe = make_pipeline(pad_source=pad)

    pipe.speak("hello")
    p_low = pipe._t_primary.calls[-1][1]

    pad.set(pleasure=0.9, arousal=0.9, dominance=0.9)  # PAD moved (by the substrate)
    pipe.speak("hello again")
    p_high = pipe._t_primary.calls[-1][1]

    assert p_high.noise_scale > p_low.noise_scale       # pleasure ↑ → warmer
    assert p_high.length_scale < p_low.length_scale     # arousal ↑ → faster (inverse)
    assert p_high.pitch_shift < p_low.pitch_shift       # dominance ↑ → lower/grounded
    assert pad.reads >= 2                                 # PAD was READ each speak


def test_speak_never_writes_pad_tripwire():
    """The output chain reads PAD but NEVER writes it (project-rules.md
    PAD-purity). Proven against the REAL PADEngine mutator."""
    pad = SpyPAD()
    pad.initialize(PAD_BASELINE, Valence.POSITIVE)
    pad.apply_appraisal_delta(PADDelta(0.1, 0.05, 0.02, valence=Valence.POSITIVE))
    writes_after_setup = pad.writes
    before = pad.get_current_pad()

    pipe = make_pipeline(pad_source=pad)
    pipe.speak("a")
    pipe.speak("b")
    pipe.speak("c")

    assert pad.get_current_pad() == before          # PAD unchanged by speaking
    assert pad.writes == writes_after_setup          # no PAD mutator call from speak()


# ===========================================================================
# 5) F4 / BARGE-IN → ZERO INTERNAL EFFECT (tripwire) — Addendum §5.
# ===========================================================================
def test_stop_playback_has_zero_internal_effect_tripwire():
    """F4 and pause-based barge-in are the SAME shape (Addendum §5): audio stop
    ONLY. stop_playback() leaves PAD byte-identical, NEVER calls a PAD mutator,
    and NEVER even READS PAD — the sole effect is playback.stop()."""
    pad = SpyPAD()
    pad.initialize(PAD_BASELINE, Valence.POSITIVE)
    # Arrange non-trivial PAD so any accidental change would be visible.
    pad.apply_appraisal_delta(PADDelta(0.12, 0.07, 0.03, valence=Valence.POSITIVE))

    playback = FakePlayback()
    pipe = make_pipeline(pad_source=pad, playback=playback)

    before = pad.get_current_pad()          # explicit read (increments reads)
    reads_at_stop_start = pad.reads
    writes_at_stop_start = pad.writes

    pipe.stop_playback()   # F4
    pipe.stop_playback()   # pause-based barge-in (same shape)

    # ZERO internal effect:
    assert pad.reads == reads_at_stop_start          # stop NEVER read PAD
    assert pad.writes == writes_at_stop_start         # stop NEVER wrote PAD
    after = pad.get_current_pad()
    assert after == before                            # PAD byte-identical
    # The ONLY effect: audio stopped, once per interrupt.
    assert playback.stops == 2
    # And a stop plays/synthesizes nothing.
    assert playback.played == []
    assert pipe._t_primary.calls == [] and pipe._t_fallback.calls == []


def test_stop_playback_source_is_pure_audio_stop():
    """stop_playback()'s body is a single playback stop — no path to PAD,
    appraisal, graph, needs, or state (Addendum §5)."""
    body = inspect.getsource(AudioPipeline.stop_playback)
    assert "self._playback.stop()" in body
    for forbidden in (
        "apply_appraisal_delta", "appraise", "write_event_node", "write_edge",
        "get_current_pad", "save_", "_pad", "_stt", "_vad", "_wake",
    ):
        assert forbidden not in body, forbidden


def test_module_never_imports_write_capable_modules():
    """Structural proof of no path to a PAD write / appraisal / graph / state:
    the module imports ONLY the read-only PADSnapshot type from pad_engine, and
    NONE of the write-capable modules; the PAD-write CALL never appears."""
    src = inspect.getsource(ap_mod)
    # the sole daemon import is the read-only PAD type
    assert "from daemon.pad_engine import PADSnapshot" in src
    for forbidden_import in (
        "from daemon.aria_daemon", "import aria_daemon",
        "from daemon.graph_manager", "import graph_manager",
        "from daemon.appraisal_chain", "import appraisal_chain",
        "from daemon.needs_system", "import needs_system",
        "from daemon.state_manager", "import state_manager",
    ):
        assert forbidden_import not in src, forbidden_import
    # the PAD-write CALL and other state-mutating CALLS never appear
    for forbidden_call in (
        ".apply_appraisal_delta(", ".appraise(", ".write_event_node(", ".write_edge(",
    ):
        assert forbidden_call not in src, forbidden_call


# ===========================================================================
# 6) TTS FALLBACK — cloud primary, Kokoro fallback (v4 Graceful Degradation).
# ===========================================================================
def test_speak_uses_cloud_primary_when_available():
    pipe = make_pipeline()
    pipe.speak("hello")
    assert len(pipe._t_primary.calls) == 1        # cloud used
    assert pipe._t_fallback.calls == []            # fallback NOT used
    assert pipe._t_playback.played == [b"WAV:cloud:hello"]
    assert pipe._last_fell_back is False


def test_cloud_tts_failure_falls_back_to_kokoro():
    """Cloud primary raises → Kokoro local fallback renders (v4). No provider is
    hardcoded — both are injected."""
    pipe = make_pipeline(primary_fail=TTSUnavailable("cloud down"))
    pipe.speak("hello")
    assert len(pipe._t_primary.calls) == 1         # cloud attempted
    assert len(pipe._t_fallback.calls) == 1        # Kokoro fell back
    assert pipe._t_playback.played == [b"WAV:kokoro:hello"]
    assert pipe._last_fell_back is True


def test_cloud_failure_of_any_kind_falls_back():
    """Graceful degradation covers arbitrary cloud/network failures, not just
    TTSUnavailable (the whole reason the fallback exists)."""
    pipe = make_pipeline(primary_fail=ConnectionError("network"))
    pipe.speak("hi")
    assert len(pipe._t_fallback.calls) == 1
    assert pipe._t_playback.played == [b"WAV:kokoro:hi"]


def test_fallback_receives_the_same_prosody_as_primary():
    """The Kokoro fallback renders with the SAME PAD-derived prosody the cloud
    would have used (one PAD read per speak)."""
    pad = StubPAD(pleasure=0.8, arousal=0.7, dominance=0.3)
    pipe = make_pipeline(pad_source=pad, primary_fail=TTSUnavailable("x"))
    pipe.speak("hello")
    used = pipe._t_fallback.calls[-1][1]
    assert used == map_pad_to_prosody(PADSnapshot(0.8, 0.7, 0.3))


def test_both_backends_failing_propagates():
    """If Kokoro ALSO fails, there is nothing left to try — the error
    propagates (not swallowed)."""
    pipe = make_pipeline(
        primary_fail=TTSUnavailable("cloud"),
        fallback_fail=TTSUnavailable("kokoro too"),
    )
    with pytest.raises(TTSUnavailable):
        pipe.speak("hello")


# ===========================================================================
# 7) THINKING / RECONSIDERATION SOUNDS (v4 Layer 5) — play pre-cached clips.
# ===========================================================================
def test_play_thinking_sound_plays_cached_clip():
    pipe = make_pipeline()
    pipe.play_thinking_sound("hmm")
    assert pipe._t_playback.play_cached_keys == ["hmm"]
    assert pipe._t_playback.played == []           # a cached clip, not synthesis


def test_play_reconsideration_sound_plays_cached_clip():
    pipe = make_pipeline()
    pipe.play_reconsideration_sound()
    assert pipe._t_playback.play_cached_keys == [RECONSIDERATION_SOUND_KEY]


# ===========================================================================
# 8) SATISFIES the Daemon's AudioPipelinePort (Module 8 contract).
# ===========================================================================
def test_satisfies_audio_pipeline_port_isinstance():
    """Structural conformance to the runtime_checkable Protocol the Daemon
    depends on."""
    pipe = make_pipeline()
    assert isinstance(pipe, AudioPipelinePort)


def test_audio_pipeline_has_every_port_method_with_matching_signature():
    port_methods = {
        "speak": ["text"],
        "stop_playback": [],
        "play_thinking_sound": ["sound"],
        "play_reconsideration_sound": [],
    }
    for name, params in port_methods.items():
        assert hasattr(AudioPipeline, name), name
        sig = inspect.signature(getattr(AudioPipeline, name))
        # drop `self`
        got = [p for p in sig.parameters if p != "self"]
        assert got == params, (name, got, params)


def test_real_daemon_drives_all_four_port_methods_end_to_end(tmp_path):
    """The REAL AriaDaemon (Module 8) uses this pipeline UNCHANGED through the
    documented AudioPipelinePort: routing a turn drives speak (TTS) + a thinking
    sound; a retry drives the reconsideration sound; F4 and barge-in drive
    stop_playback. The pipeline reads the SAME PADEngine the daemon runs."""
    pad = PADEngine()
    playback = FakePlayback()
    pipe = make_pipeline(pad_source=pad, playback=playback)

    ctx = make_daemon(tmp_path, audio=pipe, pad=pad)
    d = ctx.daemon
    d.startup()

    resp = d.route_inbound_turn(user_text="Hey Aria, I finally shipped it today.", now=T0)
    assert resp.text                                   # Soul_Filter produced text
    assert playback.played, "route_inbound_turn drove pipeline.speak() → TTS play"
    assert playback.play_cached_keys, "route_inbound_turn drove play_thinking_sound()"

    d.on_reconsideration()
    assert RECONSIDERATION_SOUND_KEY in playback.play_cached_keys

    stops_before = playback.stops
    d.on_f4_interrupt()      # F4 → stop only
    d.on_barge_in()          # barge-in → stop only
    assert playback.stops == stops_before + 2
