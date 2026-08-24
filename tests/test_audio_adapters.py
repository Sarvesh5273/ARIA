"""The seven audio backends — contract conformance and the constraints that bind.

WHAT IS AND IS NOT PROVED HERE
------------------------------
Hermetic. No provider is installed in this suite's environment, so nothing here
loads torch, ONNX Runtime, Whisper, Porcupine or PortAudio. What that leaves is
still the part worth pinning:

  * every adapter satisfies its Protocol STRUCTURALLY (`isinstance`, which the
    pipeline itself relies on);
  * the format conversions are exact, because four backends share them and a
    quiet difference in one would just make that stage deafer than the others;
  * the constraints that a passing implementation could still violate — F4 writes
    nothing, the cited thresholds are NOT applied inside the swappable component,
    TTS text is passed verbatim, an absent input backend refuses rather than
    returning a plausible neutral value.

The macOS `say` + `afplay` path IS exercised for real when those binaries exist,
because that is the one provider present on the dev machine — and an output chain
nobody has heard is not an output chain. Those tests skip elsewhere.

WHAT IS NOT TESTED, STATED PLAINLY: no microphone, no wake word, no voiceprint, no
transcription. Those need hardware and weights, and a test that faked them would be
asserting that the fake works.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import time
import wave

import pytest

from daemon.aria_daemon import AudioPipelinePort
from daemon.audio_pipeline import (
    CHANNELS,
    SAMPLE_RATE_HZ,
    SPEAKER_THRESHOLD,
    VAD_CHUNK_SIZE,
    VAD_THRESHOLD,
    AudioPipeline,
    AudioSegment,
    CaptureBackend,
    PlaybackBackend,
    Prosody,
    STTBackend,
    SpeakerVerificationBackend,
    TTSBackend,
    TTSUnavailable,
    VADBackend,
    WakeWordBackend,
    map_pad_to_prosody,
)
from daemon.pad_engine import PADEngine, PADSnapshot

from adapters import audio_stack
from adapters._provider import (
    AudioBackendUnavailable,
    binary_available,
    module_available,
    require_binary,
    require_module,
)
from adapters.audio_pcm import (
    INT16_MAX,
    INT16_MIN,
    from_int16_bytes,
    to_int16,
    to_int16_bytes,
    to_wav_bytes,
    wav_bytes_to_samples,
)
from adapters.audio_playback import CommandLinePlayback
from adapters.audio_tts import (
    SAY_DEFAULT_WPM,
    SystemSayTTS,
    _has_format_markers,
    _speed_from,
    _wpm_from,
)
from adapters.audio_wake import HotkeyWakeWord

HAS_SAY = binary_available("say") is not None
HAS_PLAYER = any(binary_available(p) for p in ("afplay", "pw-play", "aplay", "ffplay"))

needs_say = pytest.mark.skipif(not HAS_SAY, reason="macOS `say` not present")
needs_player = pytest.mark.skipif(not HAS_PLAYER, reason="no audio player on PATH")

NEUTRAL = Prosody(noise_scale=1.0, length_scale=1.0, pitch_shift=0.0)


# ===========================================================================
# Lazy provider loading — the property that keeps the suite hermetic.
# ===========================================================================

def test_every_audio_adapter_imports_without_any_provider_installed():
    """The whole point of lazy imports. If any of these grew a module-scope
    `import torch`, this fails on a bare machine — which is where a bring-up asks
    what is available in the first place."""
    import importlib
    for name in (
        "audio_capture", "audio_wake", "audio_speaker", "audio_vad",
        "audio_stt", "audio_tts", "audio_playback", "audio_stack", "audio_pcm",
    ):
        importlib.import_module(f"adapters.{name}")


def test_daemon_still_imports_nothing_from_adapters():
    """The dependency arrow points one way, and audio is where it would most
    plausibly get reversed — Module 7 names seven providers."""
    import pathlib
    for path in pathlib.Path("daemon").glob("*.py"):
        assert "import adapters" not in path.read_text()
        assert "from adapters" not in path.read_text()


def test_missing_provider_names_the_install_line():
    with pytest.raises(AudioBackendUnavailable, match="pip install nope"):
        require_module(
            "definitely_not_installed_xyz", purpose="testing",
            install="pip install nope",
        )


def test_missing_binary_names_the_install_line():
    with pytest.raises(AudioBackendUnavailable, match="brew install nope"):
        require_binary(
            "definitely-not-a-binary-xyz", purpose="testing",
            install="brew install nope",
        )


def test_availability_questions_never_raise():
    assert module_available("definitely_not_installed_xyz") is False
    assert binary_available("definitely-not-a-binary-xyz") is None


def test_backend_unavailable_is_not_a_tts_unavailable():
    """Two different facts. `TTSUnavailable` is the signal the pipeline catches to
    degrade cloud -> local; a missing dependency is a configuration error no
    fallback fixes, and dressing it as the former would make a broken install look
    like graceful degradation."""
    assert not issubclass(AudioBackendUnavailable, TTSUnavailable)
    assert not issubclass(TTSUnavailable, AudioBackendUnavailable)


# ===========================================================================
# PCM conversion — shared by four backends, so exactness matters.
# ===========================================================================

def test_full_scale_does_not_overflow_in_either_direction():
    """The reason the scale is 32767 and not 32768: at 32768 a legitimate +1.0
    wraps to -32768, a full-scale sign flip that is audible and that reads to an
    energy-based spotter as a transient."""
    assert to_int16([1.0])[0] == INT16_MAX
    assert to_int16([-1.0])[0] == -INT16_MAX
    assert to_int16([0.0])[0] == 0


def test_out_of_range_input_clamps_rather_than_wraps():
    assert to_int16([2.5])[0] == INT16_MAX
    assert to_int16([-2.5])[0] == INT16_MIN


def test_int16_round_trip_is_stable_to_one_step():
    original = (0.0, 0.25, -0.25, 0.5, -1.0, 1.0, 0.001)
    restored = from_int16_bytes(to_int16_bytes(original))
    assert len(restored) == len(original)
    for before, after in zip(original, restored):
        assert abs(before - after) < 1e-4


def test_wav_round_trip_preserves_rate_channels_and_samples():
    samples = tuple(i / 1000.0 for i in range(-500, 500))
    wav = to_wav_bytes(samples, sample_rate=SAMPLE_RATE_HZ, channels=CHANNELS)
    restored, rate, channels = wav_bytes_to_samples(wav)
    assert rate == SAMPLE_RATE_HZ
    assert channels == CHANNELS
    assert len(restored) == len(samples)


def test_wav_bytes_are_a_real_container_the_stdlib_can_read():
    wav = to_wav_bytes((0.1, -0.1) * 100, sample_rate=SAMPLE_RATE_HZ)
    with wave.open(io.BytesIO(wav)) as handle:
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == SAMPLE_RATE_HZ


def test_non_16bit_wav_is_refused_rather_than_misread():
    """Reading a 32-bit float WAV as int16 produces noise, and noise that PLAYS is
    harder to diagnose than a refusal."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(SAMPLE_RATE_HZ)
        handle.writeframes(b"\x00" * 10)
    with pytest.raises(ValueError, match="16-bit"):
        wav_bytes_to_samples(buffer.getvalue())


# ===========================================================================
# Wake word — the hotkey fallback is v4's own, and it is one-shot.
# ===========================================================================

def test_hotkey_wake_word_satisfies_the_protocol():
    assert isinstance(HotkeyWakeWord(), WakeWordBackend)


def test_hotkey_is_one_shot_so_one_press_does_not_leave_the_mic_open():
    """A latched flag would keep every later cycle awake — the open-mic failure the
    wake-word gate exists to prevent."""
    wake = HotkeyWakeWord()
    empty = AudioSegment()
    assert wake.detect(empty) is False
    wake.trigger()
    assert wake.detect(empty) is True
    assert wake.detect(empty) is False


def test_no_always_awake_backend_is_offered():
    """Deliberate absence. The wake-word gate is the only thing between a live
    microphone and a transcription, so an 'always True' adapter must not be
    something a wiring layer can pick by accident."""
    import adapters.audio_wake as module
    exported = [n for n in dir(module) if n.endswith("WakeWord")]
    assert sorted(exported) == ["HotkeyWakeWord", "PorcupineWakeWord"]


# ===========================================================================
# TTS — verbatim text, and the prosody dimensions that reach nothing.
# ===========================================================================

@needs_say
def test_say_backend_satisfies_the_tts_protocol():
    assert isinstance(SystemSayTTS(), TTSBackend)


@needs_say
def test_say_renders_a_real_readable_wav():
    wav = SystemSayTTS().synthesize("testing one two", NEUTRAL)
    with wave.open(io.BytesIO(wav)) as handle:
        assert handle.getsampwidth() == 2
        assert handle.getnchannels() == 1
        assert handle.getnframes() > 0


@needs_say
def test_empty_text_renders_silence_and_is_counted_not_raised():
    """This test previously asserted the opposite, and the opposite crashed her.

    Raising `TTSUnavailable` on empty text was the first answer. Observed
    consequence: `_synthesize_with_fallback` caught the primary's failure, tried the
    fallback, the fallback raised for the same reason (the INPUT, not the provider),
    and the exception propagated out of `speak()` -> `_route_initiative` ->
    `soul_tick()`. A no-content turn became a crashed soul tick.

    `TTSUnavailable` was also the wrong signal: it means "try the other renderer",
    and no renderer can help with empty input.

    So nothing to say produces no sound, and the counter is the visibility — the
    alternative to a crash must not be a silence nobody can see.
    """
    backend = SystemSayTTS()
    wav = backend.synthesize("   ", NEUTRAL)
    assert backend.empty_text_requests == 1
    # A REAL, playable WAV with no frames — not empty bytes, which playback rejects.
    with wave.open(io.BytesIO(wav)) as handle:
        assert handle.getnframes() == 0
    assert len(wav) > 0


@needs_say
@needs_player
def test_an_empty_reply_does_not_crash_the_output_chain():
    """The end-to-end form of the same claim, through the real pipeline: the path
    that actually broke was `speak("")`, not `synthesize("")`."""
    pad = PADEngine()
    pad.initialize(None)
    pipeline = audio_stack.build_output_only(pad_source=pad, env={})
    try:
        pipeline.speak("")
        assert pipeline._tts_primary.empty_text_requests == 1
    finally:
        pipeline._playback.close()


@needs_say
def test_text_beginning_with_a_hyphen_is_not_parsed_as_a_flag():
    """`--` before the text. A reply that opens with a dash is ordinary prose, and
    an argv injection here would fail the turn."""
    wav = SystemSayTTS().synthesize("-- actually, no", NEUTRAL)
    assert len(wav) > 0


def test_arousal_maps_to_speed_in_v4s_inverse_direction():
    """v4 Layer 5: higher arousal = faster speech, encoded upstream as a SHORTER
    length_scale. Speed is its reciprocal, so this is a unit conversion and the
    locked direction survives it."""
    calm = map_pad_to_prosody(PADSnapshot(pleasure=0.5, arousal=0.2, dominance=0.5))
    alert = map_pad_to_prosody(PADSnapshot(pleasure=0.5, arousal=0.9, dominance=0.5))
    assert alert.length_scale < calm.length_scale
    assert _speed_from(alert) > _speed_from(calm)
    assert _wpm_from(alert, base_wpm=SAY_DEFAULT_WPM) > _wpm_from(
        calm, base_wpm=SAY_DEFAULT_WPM
    )


def test_non_positive_length_scale_does_not_divide_by_zero():
    assert _speed_from(Prosody(1.0, 0.0, 0.0)) == 1.0
    assert _speed_from(Prosody(1.0, -1.0, 0.0)) == 1.0


@needs_say
def test_two_of_v4s_three_prosody_dimensions_reach_nothing():
    """The honest finding, pinned so it cannot quietly stop being true in either
    direction. No available provider has a timbre or pitch control, and mapping
    Pleasure/Dominance onto unrelated knobs (ElevenLabs `stability`, `style`) was
    REJECTED — it would make PAD appear to reach the voice while doing something
    else. If a backend gains real controls, this test should be updated
    deliberately."""
    backend = SystemSayTTS()
    assert backend.unmapped_prosody == [
        "noise_scale (Pleasure)", "pitch_shift (Dominance)",
    ]


# ===========================================================================
# The format-guard row. Records, never strips.
# ===========================================================================

@pytest.mark.parametrize("text", [
    # The shape actually observed and recorded in the tracker.
    "(Aria listens, her presence steady and calm.)",
    # The same narration followed by real prose on the same line — the mixed case,
    # which a whole-line-only pattern would miss.
    "(Aria listens, her presence steady.) Just the words.",
    "## Heading",
    "- a bullet",
    "1. a numbered item",
    "<think>hmm</think>",
    "**bold**",
])
def test_format_markers_are_detected(text):
    assert _has_format_markers(text) is True


@pytest.mark.parametrize("text", [
    # VERBATIM from the real model. These are what she actually produced.
    "[I lean forward just a fraction, settling into the space between us. "
    "My gaze is steady, not searching, just held.]",
    "[I pause, letting the silence stretch out just a moment longer than "
    "necessary. My hands rest where they are, quiet.]",
    "[My posture doesn't change. I simply hold the silence.]",
    "[I remain still.] I hear the quiet in that statement.",
    "*leans forward slightly*",
])
def test_square_bracket_and_asterisk_narration_are_detected(text):
    """REGRESSION, and the most important test in this file.

    The detector originally matched only ROUND brackets, because that was the
    shape recorded in the tracker. `tools/measure_format_markers.py` then reported
    0/16 markers on deliberately adversarial bait, which read as Field 1's
    anti-narration clause holding.

    It was not holding. Printing the replies showed four of eight opening with
    SQUARE-bracket stage directions — the strings above, verbatim. The detector's
    false negative had inverted the measurement, and "prompt-level mitigation is
    sufficient" was one step from being recorded in the Resolution Log as a
    measured finding.

    Re-measured with the hole closed: 8/16, and 12/16 on a warm session.
    """
    assert _has_format_markers(text) is True


@pytest.mark.parametrize("text", [
    "That sounds hard. I am glad you told me.",
    "It costs 5 dollars (roughly) which is fine.",
    "I do not know yet - I would rather say so.",
    # Mid-sentence square brackets are not narration either. Widening the
    # detector must not have cost the precision that makes the signal useful.
    "You said the config lives in app[0] which I could not find.",
])
def test_ordinary_prose_is_not_flagged(text):
    assert _has_format_markers(text) is False


def test_narration_with_no_marker_at_all_is_a_known_gap():
    """Recorded rather than papered over, because it bounds what this detector
    can honestly claim.

    Measured on the same run: "I am sitting still. My attention is focused
    entirely on the words you are saying." is a stage direction in plain prose.
    No lexical pattern catches it without judging content, so the detector does
    not — and this test exists so nobody mistakes a recorder for a guard.
    """
    prose_narration = (
        "I am sitting still. My attention is focused entirely on the words you "
        "are saying. There is a quietness here, a sense of waiting."
    )
    assert _has_format_markers(prose_narration) is False


@needs_say
def test_a_stage_direction_is_recorded_and_still_spoken_verbatim():
    """The tracker's needs-ruling row, made observable rather than resolved.
    'Strip it in the adapter' was rejected: that is the transport judging content,
    and Resolution Log item 15 puts verbatim passthrough here deliberately. So the
    marker is RECORDED and the audio is still produced from the full text."""
    backend = SystemSayTTS()
    plain = backend.synthesize("Just the words.", NEUTRAL)
    assert backend.last_text_had_format_markers is False

    staged = backend.synthesize(
        "(Aria listens, her presence steady.) Just the words.", NEUTRAL
    )
    assert backend.last_text_had_format_markers is True
    # Longer audio, because the stage direction was spoken too. That is the
    # defect the ruling has to settle — this asserts it is still present.
    assert len(staged) > len(plain)


def test_no_adapter_exposes_a_strip_or_sanitize_helper():
    """Asserted as an ABSENCE, because this is the kind of thing someone adds later
    meaning well. The fix for the format defect does not live at this layer."""
    import adapters.audio_tts as module
    names = [n.lower() for n in dir(module)]
    for forbidden in ("strip", "sanitize", "sanitise", "clean", "normalize"):
        assert not any(forbidden in name for name in names), forbidden


# ===========================================================================
# Playback — and F4's one and only mechanism.
# ===========================================================================

@needs_player
def test_playback_satisfies_the_protocol():
    playback = CommandLinePlayback()
    try:
        assert isinstance(playback, PlaybackBackend)
    finally:
        playback.close()


@needs_player
def test_stop_actually_stops_a_playing_clip():
    """F4 has to interrupt, not queue behind a buffer. A separately-scheduled
    process is what makes that possible from the calling thread."""
    playback = CommandLinePlayback()
    try:
        long_tone = to_wav_bytes((0.05, -0.05) * 40_000, sample_rate=SAMPLE_RATE_HZ)
        playback.play(long_tone)
        assert playback.is_playing is True
        playback.stop()
        time.sleep(0.2)
        assert playback.is_playing is False
    finally:
        playback.close()


@needs_player
def test_a_new_play_stops_the_previous_one():
    """Two players talking over each other is never wanted, and it would make
    `stop()` ambiguous about which process F4 meant."""
    playback = CommandLinePlayback()
    try:
        tone = to_wav_bytes((0.05, -0.05) * 40_000, sample_rate=SAMPLE_RATE_HZ)
        playback.play(tone)
        first = playback._process
        playback.play(tone)
        assert playback._process is not first
        assert first.poll() is not None
    finally:
        playback.close()


@needs_player
def test_stop_is_safe_when_nothing_is_playing():
    playback = CommandLinePlayback()
    try:
        playback.stop()
        playback.stop()
        assert playback.stops == 2
    finally:
        playback.close()


@needs_player
def test_missing_cached_clip_is_a_recorded_noop_not_an_exception():
    """The caller is on the pre-generation path of an otherwise-fine turn. Raising
    would cost her the answer over a missing comfort noise."""
    playback = CommandLinePlayback()
    try:
        playback.play_cached("no_such_clip")
        assert playback.missing_clips == ["no_such_clip"]
    finally:
        playback.close()


@needs_player
def test_registering_a_missing_clip_file_fails_at_wiring_time():
    playback = CommandLinePlayback()
    try:
        with pytest.raises(AudioBackendUnavailable, match="not found"):
            playback.register_clip("thinking", "/definitely/not/here.wav")
    finally:
        playback.close()


@needs_player
def test_empty_wav_is_refused():
    playback = CommandLinePlayback()
    try:
        with pytest.raises(ValueError, match="empty WAV"):
            playback.play(b"")
    finally:
        playback.close()


def test_playback_holds_no_soul_handle_at_all():
    """F4's zero-internal-effect guarantee (Addendum §5) is structural here: there
    is no constructor parameter through which a PAD, graph, appraisal or state
    handle could arrive, so `stop()` cannot reach one."""
    import inspect
    signature = inspect.signature(CommandLinePlayback.__init__)
    assert set(signature.parameters) == {
        "self", "player", "cached_clips", "clip_dir",
    }


def test_stop_body_is_only_process_termination():
    """Scans the CODE of `stop()`, docstring excluded.

    The docstring necessarily names PAD, appraisal and the graph — it exists to say
    the method touches none of them — so a naive source grep matches its own
    explanation and proves nothing. Parsing and dropping the docstring is the
    difference between checking the constraint and checking the comment.

    `AudioPipeline.stop_playback()` is one call into this, and Addendum §5 removes
    v4's F4 PAD-effect row entirely.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(CommandLinePlayback.stop)))
    function = tree.body[0]
    body = function.body
    if (
        isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    code = "\n".join(ast.unparse(node) for node in body).lower()

    assert code, "stop() has no body outside its docstring"
    for forbidden in (
        "pad", "appraise", "graph", "salience", "energy", "need", "save", "write",
    ):
        assert forbidden not in code, f"{forbidden!r} reachable from stop(): {code}"
    # And positively: what it DOES is terminate a process.
    assert "_terminate" in code


# ===========================================================================
# The stack — preflight, and what an absent input backend must do.
# ===========================================================================

def test_preflight_reports_all_seven_backends_and_never_raises():
    rows = audio_stack.preflight()
    assert len(rows) == 7
    assert {r.name for r in rows} == {
        "capture", "wake", "speaker", "vad", "stt", "tts", "playback",
    }
    assert isinstance(audio_stack.preflight_report(), str)


def test_preflight_names_an_install_line_for_every_missing_backend():
    for status in audio_stack.preflight():
        if not status.present:
            assert status.hint


def test_absent_input_backend_refuses_rather_than_returning_a_neutral_value():
    """The dangerous alternative, spelled out: a capture returning silence, a VAD
    returning 0.0 and a speaker check returning 1.0 all look like ordinary
    operation, and `capture_turn()` would return None as if nobody had spoken."""
    absent = audio_stack._Absent("capture", "pip install something")
    for call in (
        lambda: absent.read(),
        lambda: absent.detect(AudioSegment()),
        lambda: absent.similarity(AudioSegment()),
        lambda: absent.speech_probability(AudioSegment()),
        lambda: absent.transcribe(AudioSegment()),
    ):
        with pytest.raises(AudioBackendUnavailable, match="not a stub"):
            call()


def test_absent_stubs_still_satisfy_the_protocols_structurally():
    """They have to, or `AudioPipeline` could not be constructed with them — which
    is what makes an output-only pipeline possible at all."""
    absent = audio_stack._Absent("x", "y")
    assert isinstance(absent, CaptureBackend)
    assert isinstance(absent, WakeWordBackend)
    assert isinstance(absent, SpeakerVerificationBackend)
    assert isinstance(absent, VADBackend)
    assert isinstance(absent, STTBackend)


@needs_say
@needs_player
def test_output_only_pipeline_satisfies_the_daemons_port():
    """The claim that matters for wiring: a pipeline with a real output chain and
    absent input backends is a drop-in for `NoOpAudioPipeline`."""
    pad = PADEngine()
    pad.initialize(None)
    pipeline = audio_stack.build_output_only(pad_source=pad, env={})
    try:
        assert isinstance(pipeline, AudioPipeline)
        assert isinstance(pipeline, AudioPipelinePort)
    finally:
        pipeline._playback.close()


@needs_say
@needs_player
def test_the_whole_output_chain_leaves_pad_byte_identical():
    """Prosody is a presentation READ of substrate. The seam exposes only
    `get_current_pad()`, so a write is not expressible — this checks the value
    really is untouched across synthesis and playback."""
    pad = PADEngine()
    pad.initialize(None)
    before = pad.get_current_pad()
    pipeline = audio_stack.build_output_only(pad_source=pad, env={})
    try:
        pipeline.speak("A short line.")
        pipeline.stop_playback()
        pipeline.play_reconsideration_sound()
    finally:
        pipeline._playback.close()
    assert pad.get_current_pad() == before


@needs_say
def test_unkeyed_cloud_tts_puts_the_local_renderer_in_both_slots():
    """Deliberate, not lazy: `AudioPipeline` requires both slots, and a single
    renderer failing twice is honest — it does not pretend a second provider was
    tried."""
    primary, fallback = audio_stack.build_tts_pair(env={})
    assert primary is fallback


def test_build_full_refuses_without_a_voiceprint_and_says_why():
    """Without one the real backend returns -1.0 for everyone and no turn passes
    the 0.75 gate — she would appear to have stopped listening rather than to be
    misconfigured. So it is refused, with that consequence named."""
    pad = PADEngine()
    pad.initialize(None)
    with pytest.raises(AudioBackendUnavailable, match="voiceprint"):
        audio_stack.build_full(
            pad_source=pad,
            vad_model_path="/tmp/whatever.onnx",
            speaker_model_path="/tmp/whatever.pt",
            voiceprint_path=None,
        )


def test_build_full_refuses_without_a_vad_model_and_downloads_nothing():
    pad = PADEngine()
    pad.initialize(None)
    with pytest.raises(AudioBackendUnavailable, match="VAD model"):
        audio_stack.build_full(pad_source=pad, vad_model_path=None)


# ===========================================================================
# The cited thresholds stay in the pipeline, not in the swappable backends.
# ===========================================================================

def test_no_adapter_imports_a_cited_pipeline_threshold():
    """`SPEAKER_THRESHOLD = 0.75` and `VAD_THRESHOLD = 0.5` are CITED v4 values and
    `AudioPipeline` owns both comparisons. A backend applying one would put a spec'd
    number inside a hot-swappable component, so swapping the component would
    silently move the gate.

    Checked by AST over the IMPORTS, not by grepping the file: these adapters
    discuss the thresholds in their docstrings precisely to explain that they do not
    apply them, and a text search cannot tell an explanation from a use. What
    matters is whether the symbol is in scope to be compared against.
    """
    import ast
    import pathlib

    for name in ("audio_vad.py", "audio_speaker.py", "audio_capture.py",
                 "audio_stt.py", "audio_wake.py"):
        tree = ast.parse((pathlib.Path("adapters") / name).read_text())
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "SPEAKER_THRESHOLD" not in imported, name
        assert "VAD_THRESHOLD" not in imported, name
        # The chunk SIZE is different in kind and legitimately imported: it is the
        # window shape the model was exported for, not a decision about the signal.
        assigned = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert "SPEAKER_THRESHOLD" not in assigned, name
        assert "VAD_THRESHOLD" not in assigned, name


def test_the_pipeline_still_owns_both_gates():
    """The other half of the same claim — asserted against the module that should
    have them, so the test above cannot pass by the constants having moved."""
    import inspect
    source = inspect.getsource(AudioPipeline)
    assert "_speaker_threshold" in source
    assert "_vad_threshold" in source
    assert SPEAKER_THRESHOLD == 0.75
    assert VAD_THRESHOLD == 0.5
    assert VAD_CHUNK_SIZE == 512
