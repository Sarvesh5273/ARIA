"""The Visual Layer's window adapter and the bridge that drives it.

WHAT IS LOAD-BEARING HERE
-------------------------
1. `test_the_daemon_is_not_modified_to_carry_a_visual_handle` — the whole reason
   the bridge exists. `AriaDaemon` takes no visual parameter, and Module 10's own
   flag disposition calls this wiring "top-of-tree BUILD-TIME wiring, not this
   module's concern." The alternative was editing an approved module's public
   constructor to wire a leaf.

2. `test_speaking_signal_is_lowered_even_when_tts_raises` — a TTS failure must not
   leave her mouth frozen open for the rest of the session. The observed empty-text
   crash is exactly the shape that would have done it.

3. `test_the_llm_routing_readout_is_not_used_as_the_degradation_trigger` — the
   readout Module 10 names must not be wired. `serving_from_local` said "cloud is
   currently down" while returning `local.is_loaded`, which Track A made
   permanently True, so wiring it would park her face in INWARD_WAITING forever.
   `last_route` replaced it and tells the truth, and the guard STAYS: under a
   local-primary design "no cloud" is the resting state, so the deeper question
   (v4's degradation state assumes cloud-primary) is flagged, not resolved. Both
   names are asserted absent.

PyQt6 and libmpv are absent in this environment, so `MpvVideoWindow` is exercised
only for what does not need them: the loop catalogue, the key derivation, and the
availability questions. `LoggingVideoWindow` carries the behavioural tests, which
is what it is for.
"""

from __future__ import annotations

import inspect

import pytest

from daemon.aria_daemon import AriaDaemon, AudioPipelinePort
from daemon.pad_engine import PADEngine, PADSnapshot
from daemon.visual_layer import (
    PAD_ZONES,
    ZONE_STABILITY_SECONDS,
    SpeakingState,
    VideoWindow,
    VisualLayer,
    VisualLayerPort,
    Zone,
    ZoneLoop,
    map_pad_to_zone,
)

from adapters import visual_window
from adapters._provider import AudioBackendUnavailable
from adapters.audio_noop import NoOpAudioPipeline
from adapters.visual_bridge import CloudAvailabilityReporter, SpeakingSignalAudio
from adapters.visual_window import (
    LoggingVideoWindow,
    MpvVideoWindow,
    expected_loop_ids,
    missing_loop_files,
    resolve_loop_files,
)


class _RaisingAudio:
    """An `AudioPipelinePort` whose `speak` fails — the case that matters."""

    def __init__(self) -> None:
        self.stops = 0

    def speak(self, text: str) -> None:
        raise RuntimeError("TTS exploded")

    def stop_playback(self) -> None:
        self.stops += 1

    def play_thinking_sound(self, sound: str) -> None:
        pass

    def play_reconsideration_sound(self) -> None:
        pass


def _layer(window=None, clock=None):
    pad = PADEngine()
    pad.initialize(None)
    window = window or LoggingVideoWindow()
    kwargs = {"pad_source": pad, "window": window}
    if clock is not None:
        kwargs["clock"] = clock
    return VisualLayer(**kwargs), window, pad


# ===========================================================================
# Conformance.
# ===========================================================================

def test_logging_window_satisfies_the_video_window_protocol():
    assert isinstance(LoggingVideoWindow(), VideoWindow)


def test_visual_layer_accepts_the_adapter_and_exposes_its_port():
    layer, _window, _pad = _layer()
    assert isinstance(layer, VisualLayerPort)


def test_the_adapters_import_without_pyqt6_or_libmpv():
    """Same lazy-provider property as the audio adapters: a bring-up must be able
    to ASK what is available on a machine that has neither."""
    import importlib
    importlib.import_module("adapters.visual_window")
    importlib.import_module("adapters.visual_bridge")


def test_visual_layer_still_imports_no_gui_toolkit():
    """Module 10 constraint 6: PyQt6/libmpv are NEVER imported there, and the
    adapter existing is precisely what keeps that true.

    Checked over the IMPORTS by AST rather than by grepping the file, because
    `visual_layer.py` mentions "PyQt6 frameless" and libmpv repeatedly in prose —
    it is describing the window it drives. A text search cannot tell a description
    from an import.
    """
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("daemon/visual_layer.py").read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    for forbidden in ("PyQt6", "mpv", "adapters"):
        assert not any(
            m == forbidden or m.startswith(f"{forbidden}.") for m in modules
        ), f"{forbidden} reached daemon/visual_layer.py: {sorted(modules)}"
    # Positively: the ONLY daemon import is the read-only PAD type.
    assert {m for m in modules if m.startswith("daemon")} == {"daemon.pad_engine"}


# ===========================================================================
# The loop catalogue — v4 names 16 files plus one.
# ===========================================================================

def test_expected_loop_ids_are_the_seventeen_v4_implies():
    ids = expected_loop_ids()
    assert len(ids) == len(PAD_ZONES) * 2 + 1 == 17
    assert len(set(ids)) == 17
    assert "inward_waiting" in ids
    assert "engaged_talking" in ids
    assert "neutral_idle_idle" in ids


def test_loop_ids_are_derived_from_zoneloop_not_written_out():
    """So a change to `ZoneLoop.loop_id` cannot leave the catalogue stale."""
    for zone in PAD_ZONES:
        for variant in (SpeakingState.IDLE, SpeakingState.TALKING):
            assert ZoneLoop(zone, variant).loop_id in expected_loop_ids()


def test_inward_waiting_has_a_single_variant():
    """v4 names it in the singular — "an inward/waiting loop" — and `ZoneLoop`
    normalises the variant at construction."""
    assert ZoneLoop(Zone.INWARD_WAITING, SpeakingState.TALKING).loop_id == (
        "inward_waiting"
    )


def test_resolve_and_missing_loop_files(tmp_path):
    (tmp_path / "neutral_idle_idle.mp4").write_bytes(b"")
    (tmp_path / "inward_waiting.mov").write_bytes(b"")
    found = resolve_loop_files(str(tmp_path))
    assert set(found) == {"neutral_idle_idle", "inward_waiting"}
    missing = missing_loop_files(str(tmp_path))
    assert len(missing) == 15
    assert "engaged_talking" in missing


def test_window_refuses_an_empty_loop_directory(tmp_path):
    with pytest.raises(AudioBackendUnavailable, match="no video loops"):
        MpvVideoWindow(loop_dir=str(tmp_path))


def test_availability_and_preflight_never_raise():
    assert isinstance(visual_window.available(), bool)
    assert isinstance(visual_window.preflight_report(), str)
    assert isinstance(visual_window.preflight_report("/definitely/not/here"), str)


# ===========================================================================
# The zone machinery, driven for real through the logging window.
# ===========================================================================

def test_every_pad_zone_can_be_reached_and_signalled():
    """The categorical mapping, end to end through the adapter. Each PAD reading
    is chosen to satisfy exactly one v4 signature under the module's documented
    precedence."""
    probes = {
        Zone.LOW_TIRED: PADSnapshot(pleasure=0.2, arousal=0.2, dominance=0.3),
        Zone.CONCERNED: PADSnapshot(pleasure=0.2, arousal=0.9, dominance=0.9),
        Zone.PLAYFUL: PADSnapshot(pleasure=0.8, arousal=0.65, dominance=0.75),
        Zone.FIRM: PADSnapshot(pleasure=0.5, arousal=0.5, dominance=0.9),
        Zone.THINKING: PADSnapshot(pleasure=0.5, arousal=0.8, dominance=0.5),
        Zone.ENGAGED: PADSnapshot(pleasure=0.65, arousal=0.65, dominance=0.65),
        Zone.WARM: PADSnapshot(pleasure=0.75, arousal=0.4, dominance=0.5),
        Zone.NEUTRAL_IDLE: PADSnapshot(pleasure=0.55, arousal=0.45, dominance=0.58),
    }
    for expected, pad in probes.items():
        assert map_pad_to_zone(pad) is expected, expected


def test_variant_change_is_signalled_promptly_and_is_not_zone_gated():
    """Module 10: a talking<->idle change alters only the VARIANT and "is NOT
    subject to the 8 s zone gate". The mouth has to track the voice."""
    layer, window, _pad = _layer()
    layer.refresh()
    first = window.current_loop_id
    layer.set_speaking(True)
    assert window.current_loop_id.endswith("_talking")
    layer.set_speaking(False)
    assert window.current_loop_id == first


def test_degradation_override_is_signalled_immediately():
    layer, window, _pad = _layer()
    layer.refresh()
    layer.set_cloud_available(False)
    assert window.current_loop_id == "inward_waiting"
    assert layer.is_degraded is True
    layer.set_cloud_available(True)
    assert window.current_loop_id != "inward_waiting"
    assert layer.is_degraded is False


def test_identical_loops_are_not_re_signalled_every_tick():
    """Module 10 de-dups, so the window is driven only on change. Asserted through
    the adapter because it is the adapter that would otherwise be told to restart
    the same video repeatedly."""
    layer, window, _pad = _layer()
    for _ in range(5):
        layer.refresh()
    assert len(window.loops) == 1


# ===========================================================================
# The bridge — signals taken from where Module 10 says they live.
# ===========================================================================

def test_bridge_satisfies_the_audio_pipeline_port():
    """So it drops into the same Daemon slot as the no-op or the real pipeline."""
    layer, _window, _pad = _layer()
    bridge = SpeakingSignalAudio(audio=NoOpAudioPipeline(), visual=layer)
    assert isinstance(bridge, AudioPipelinePort)


def test_the_daemon_is_not_modified_to_carry_a_visual_handle():
    """The claim the whole bridge exists to make. If a `visual` parameter ever
    appears on `AriaDaemon.__init__`, that is a change to an approved module's
    public constructor and wants a ruling — not a passing test."""
    parameters = set(inspect.signature(AriaDaemon.__init__).parameters)
    assert "visual" not in parameters
    assert "visual_layer" not in parameters
    assert "window" not in parameters


def test_speak_raises_then_lowers_the_talking_variant():
    layer, window, _pad = _layer()
    layer.refresh()
    audio = NoOpAudioPipeline()
    bridge = SpeakingSignalAudio(audio=audio, visual=layer)

    bridge.speak("hello")

    assert audio.spoken == ["hello"]
    assert bridge.speaking_transitions == [True, False]
    # Ends idle: she finished talking.
    assert window.current_loop_id.endswith("_idle")
    # And the talking variant really was signalled in between.
    assert any(loop_id.endswith("_talking") for loop_id in window.loop_ids)


def test_speaking_signal_is_lowered_even_when_tts_raises():
    """`finally` is load-bearing. Without it a TTS failure freezes her mouth open
    for the rest of the session while the zone machinery keeps running."""
    layer, window, _pad = _layer()
    layer.refresh()
    bridge = SpeakingSignalAudio(audio=_RaisingAudio(), visual=layer)

    with pytest.raises(RuntimeError, match="TTS exploded"):
        bridge.speak("hello")

    assert bridge.speaking_transitions == [True, False]
    assert window.current_loop_id.endswith("_idle")


def test_barge_in_stops_the_audio_and_closes_her_mouth():
    """F4 stays audio-only in the Addendum §5 sense — no PAD, no appraisal, no
    graph write. A variant signal is none of those; leaving the talking loop
    playing after a stop would show her still speaking."""
    layer, window, _pad = _layer()
    layer.refresh()
    audio = NoOpAudioPipeline()
    bridge = SpeakingSignalAudio(audio=audio, visual=layer)

    layer.set_speaking(True)
    bridge.stop_playback()

    assert audio.stops == 1
    assert window.current_loop_id.endswith("_idle")


def test_thinking_sounds_do_not_raise_the_talking_variant():
    """A thinking sound plays while she is NOT talking (v4 Layer 5 covers the pause
    before generation), so moving her mouth over a breath would be wrong."""
    layer, window, _pad = _layer()
    layer.refresh()
    idle = window.current_loop_id
    audio = NoOpAudioPipeline()
    bridge = SpeakingSignalAudio(audio=audio, visual=layer)

    bridge.play_thinking_sound("soft")
    bridge.play_reconsideration_sound()

    assert audio.thinking_sounds == ["soft"]
    assert audio.reconsiderations == 1
    assert bridge.speaking_transitions == []
    assert window.current_loop_id == idle


def test_bridge_exposes_the_wrapped_port_so_diagnostics_still_reach_it():
    audio = NoOpAudioPipeline()
    layer, _window, _pad = _layer()
    assert SpeakingSignalAudio(audio=audio, visual=layer).wrapped is audio


def test_the_decorator_hides_the_pipelines_internals_which_is_why_wrapped_exists():
    """REGRESSION. `report_startup` and `Wiring.close` both reach for the
    pipeline's `_tts_primary` / `_playback`, and with the visual layer on they were
    reaching into the DECORATOR — which has neither.

    Observed: the startup line read "SPEAKING — NoneType -> ?" exactly when the
    visual layer was enabled, i.e. exactly when someone was checking it. Worse, the
    same reach in `close()` would have left a playback subprocess and its temp WAVs
    behind.

    So the trap is pinned from both sides: the attribute is genuinely absent on the
    decorator, and `wrapped` is genuinely the way through.
    """
    class _Pipeline(NoOpAudioPipeline):
        def __init__(self) -> None:
            super().__init__()
            self._tts_primary = object()
            self._playback = object()

    pipeline = _Pipeline()
    layer, _window, _pad = _layer()
    bridge = SpeakingSignalAudio(audio=pipeline, visual=layer)

    assert getattr(bridge, "_tts_primary", None) is None
    assert getattr(bridge, "_playback", None) is None
    port = getattr(bridge, "wrapped", bridge)
    assert port._tts_primary is pipeline._tts_primary
    assert port._playback is pipeline._playback
    # And the same expression is correct when there is no decorator at all, which
    # is what lets both call sites use one form.
    assert getattr(pipeline, "wrapped", pipeline) is pipeline


def test_bridge_holds_no_soul_handle():
    parameters = set(inspect.signature(SpeakingSignalAudio.__init__).parameters)
    assert parameters == {"self", "audio", "visual"}


# ===========================================================================
# Cloud availability — and the readout that must not be used.
# ===========================================================================

def test_cloud_reporter_drives_the_degradation_loop_from_turn_outcomes():
    layer, window, _pad = _layer()
    layer.refresh()
    reporter = CloudAvailabilityReporter(visual=layer)

    reporter.report_turn_failed()
    assert window.current_loop_id == "inward_waiting"
    assert layer.is_degraded is True

    reporter.report_turn_served()
    assert window.current_loop_id != "inward_waiting"
    assert layer.is_degraded is False


def test_cloud_reporter_is_edge_triggered():
    """So a caller can report every turn without tracking state — which is what
    makes it safe to drop into a REPL's success and failure paths unconditionally."""
    layer, window, _pad = _layer()
    layer.refresh()
    reporter = CloudAvailabilityReporter(visual=layer)
    for _ in range(4):
        reporter.report_turn_served()
    assert reporter.transitions == [True]
    for _ in range(4):
        reporter.report_turn_failed()
    assert reporter.transitions == [True, False]


def test_the_llm_routing_readout_is_not_used_as_the_degradation_trigger():
    """Module 10's docstring names the LLM Interface's readout, and it must NOT
    be wired — even now that the readout tells the truth.

    The old `serving_from_local` was disqualified because it LIED: it returned
    `local.is_loaded`, which Track A made permanently True, so
    `set_cloud_available(not serving_from_local)` would have parked her face in
    INWARD_WAITING for the entire session. `last_route` fixes the lie.

    The wiring still does not follow, and that is the point of keeping this
    guard. Under a local-primary design "no cloud" is the ordinary resting state
    rather than degradation, so whether it should drive a withdrawn face AT ALL
    is the question the tracker row still holds open. Until that is ruled on,
    the trigger stays `LLMUnavailableError` — "nothing could answer this turn" —
    which is well-defined under either design.

    Both names are asserted absent: the new one so the open question is not
    quietly closed by wiring it, and the old one so it cannot come back.
    """
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("adapters/visual_bridge.py").read_text())
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "serving_from_local" not in attributes
    assert "last_route" not in attributes


def test_a_resident_local_model_no_longer_reads_as_cloud_failure():
    """The regression pin for the row this fixed, stated as the fact it turns on.

    A loaded local transport with nothing wrong anywhere used to make the readout
    say "cloud is currently down". It no longer can, because residency is not
    consulted: nothing has been served yet, so the honest answer is `no_turn_yet`.
    """
    from daemon.llm_interface import LLMInterface, ROUTE_NO_TURN_YET

    class _Loaded:
        is_loaded = True

        def generate(self, prompt):    # pragma: no cover - not called
            raise AssertionError

        def load(self):    # pragma: no cover
            pass

        def unload(self):  # pragma: no cover
            pass

    interface = LLMInterface(cloud_transport=_Loaded(), local_transport=_Loaded())
    assert interface.last_route == ROUTE_NO_TURN_YET


# ===========================================================================
# The stability gate is Module 10's, and the window must not duplicate it.
# ===========================================================================

def test_the_eight_second_gate_stays_in_module_10():
    """Two different mechanisms at two layers: Module 10 decides whether a zone
    CHANGE is allowed (v4's anti-flicker rule); the window decides when an allowed
    change is RENDERED (v4's no-jarring-cuts rule). The adapter must not hold a
    copy of the first."""
    import ast
    import pathlib

    source = pathlib.Path("adapters/visual_window.py").read_text()
    tree = ast.parse(source)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "ZONE_STABILITY_SECONDS" not in imported
    assert ZONE_STABILITY_SECONDS == 8
