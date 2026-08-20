"""Tests for Module 10 — Visual Layer.

Locked spec: .kiro/specs/visual-layer/{requirements,design,tasks}.md.

Plain pytest, NO hypothesis (matches Modules 1–7 style). These prove the
PHILOSOPHY contracts of the Visual Layer, not just behavior:

  * PAD → ZONE is a CATEGORICAL READ (tripwire): map_pad_to_zone returns one of
    the eight discrete v4 zones by boolean threshold membership — never a
    score/percentage — varies with PAD, is a pure function, and computing/
    displaying a zone NEVER writes PAD (byte-identical against the REAL
    PADEngine; the mutator is never called). (project-rules.md substrate-vs-
    feeling + percentage test; v4 "Representation Layer")
  * TALKING vs IDLE VARIANT follows speaking-state, promptly, WITHOUT changing
    the zone and WITHOUT resetting the 8 s zone gate. (v4 "Speaking State")
  * 8-SECOND MINIMUM-BEFORE-SWITCH holds: a zone is held < 8 s, switches ≥ 8 s
    (8.0 s boundary switches), first zone is immediate. (v4 "Transition Logic";
    v4 constants table "Video zone stability | 8 seconds min before switch")
  * CLOUD FAILURE shows the inward/waiting DEGRADATION loop, overriding PAD,
    promptly (ungated), resuming on restore — no fabricated content. (v4
    "Graceful degradation video state")
  * RUNS INDEPENDENTLY of language generation: refresh() needs only the PAD seam
    + window; the module imports NO LLM/SoulFilter/Appraisal. (v4 "runs locally,
    independently, in parallel with language generation")
  * SATISFIES a clean VisualLayerPort the Daemon can drive — structurally
    (isinstance) AND end-to-end (the REAL AriaDaemon drives speaking-state
    through its EXISTING speak() boundary while the Visual Layer reads the REAL
    PADEngine).

Structural proofs (AST import scan + source scan) back the tripwire: the module
imports only the read-only PADSnapshot type, no write-capable module, and no GUI
toolkit; and the PAD-write CALL never appears in it.
"""

import ast
import inspect
from datetime import timedelta

import pytest

import daemon.visual_layer as vl_mod
from daemon.visual_layer import (
    VisualLayer,
    VisualLayerPort,
    VideoWindow,
    PADReader,
    Zone,
    SpeakingState,
    ZoneLoop,
    map_pad_to_zone,
    PAD_ZONES,
    ZONE_STABILITY_SECONDS,
)
from daemon.pad_engine import PADEngine, PADSnapshot, PADDelta, Valence
from daemon.aria_daemon import AudioPipelinePort

# Reuse the canonical REAL-daemon wiring for the end-to-end contract test (same
# pattern the audio-pipeline tests use). Importing only runs test_daemon's
# module-level defs — it does NOT re-collect its tests.
from test_daemon import make_daemon, T0


# ===========================================================================
# Fakes for the INJECTED collaborators (Rule 6). Deterministic; record calls.
# ===========================================================================
class FakeWindow:
    """The injected VideoWindow (a ZonePlayer). Records every ZoneLoop it is
    asked to play, in order — so tests can prove which loop is shown, the
    de-dup (driven only on change), and the 8 s stability."""
    def __init__(self):
        self.loops = []

    def play_loop(self, loop: ZoneLoop) -> None:
        self.loops.append(loop)

    @property
    def last(self):
        return self.loops[-1] if self.loops else None


class StubPAD:
    """Read-only PAD source (satisfies PADReader). Returns a settable snapshot;
    counts reads. Has NO mutator — the presentation seam is structurally
    read-only."""
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
    — a live tripwire proving the Visual Layer touches PAD in NO writing way."""
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

    def on_soul_tick(self) -> None:
        self.writes += 1
        return super().on_soul_tick()


def _visual(pad=None, window=None, **kw):
    return VisualLayer(
        pad_source=pad or StubPAD(),
        window=window or FakeWindow(),
        clock=kw.pop("clock", lambda: T0),
        **kw,
    )


# ===========================================================================
# 1) CATEGORICAL PAD → zone selection, varying with PAD (Req 3).
# ===========================================================================

def test_map_pad_to_zone_returns_a_discrete_zone_not_a_number():
    z = map_pad_to_zone(PADSnapshot(0.55, 0.45, 0.58))
    assert isinstance(z, Zone)
    # A discrete category, never a score/percentage/number in disguise.
    assert not isinstance(z, (int, float))


def test_map_pad_to_zone_covers_all_eight_zones_and_varies_with_pad():
    # Representative PADs for each v4 zone (boundaries CITED to v4's table).
    cases = {
        Zone.NEUTRAL_IDLE: (0.55, 0.45, 0.58),   # ~baseline (default)
        Zone.ENGAGED:      (0.65, 0.65, 0.65),   # P/A/D 0.6+
        Zone.WARM:         (0.75, 0.40, 0.50),   # P 0.7+, calm
        Zone.THINKING:     (0.50, 0.75, 0.50),   # A 0.7+
        Zone.CONCERNED:    (0.20, 0.50, 0.40),   # P 0.3-
        Zone.PLAYFUL:      (0.80, 0.70, 0.80),   # P 0.7+ A 0.6+ D 0.7+
        Zone.LOW_TIRED:    (0.30, 0.20, 0.30),   # P 0.4- A 0.3- D 0.4-
        Zone.FIRM:         (0.50, 0.50, 0.85),   # D 0.8+
    }
    seen = set()
    for expected, (p, a, d) in cases.items():
        z = map_pad_to_zone(PADSnapshot(p, a, d))
        assert z is expected, f"PAD {(p, a, d)} → {z}, expected {expected}"
        seen.add(z)
    # Selection VARIES with PAD: all eight distinct PAD-zones are reachable.
    assert seen == set(PAD_ZONES)
    assert len(PAD_ZONES) == 8


def test_map_pad_to_zone_is_pure_and_deterministic():
    pad = PADSnapshot(0.8, 0.7, 0.8)
    assert map_pad_to_zone(pad) is map_pad_to_zone(pad) is Zone.PLAYFUL
    base = PADSnapshot(0.55, 0.45, 0.58)
    assert map_pad_to_zone(base) is Zone.NEUTRAL_IDLE  # baseline → default zone


def test_inward_waiting_is_not_one_of_the_eight_pad_zones():
    # The degradation state is distinct from the PAD-mapped catalog (v4).
    assert Zone.INWARD_WAITING not in PAD_ZONES


# ===========================================================================
# 2) TALKING vs IDLE variant follows speaking-state (Req 4).
# ===========================================================================

def test_talking_vs_idle_variant_follows_speaking_state():
    window = FakeWindow()
    visual = _visual(pad=StubPAD(0.65, 0.65, 0.65), window=window)  # ENGAGED
    loop = visual.refresh(now=T0)
    assert loop.zone is Zone.ENGAGED and loop.variant is SpeakingState.IDLE
    assert loop.loop_id == "engaged_idle"

    visual.set_speaking(True)  # Aria speaks → talking variant of the SAME zone
    assert visual.current_loop.zone is Zone.ENGAGED
    assert visual.current_loop.variant is SpeakingState.TALKING
    assert visual.current_loop.loop_id == "engaged_talking"

    visual.set_speaking(False)  # back to idle
    assert visual.current_loop.variant is SpeakingState.IDLE


def test_variant_flip_is_ungated_and_does_not_reset_zone_timer():
    window = FakeWindow()
    pad = StubPAD(0.55, 0.45, 0.58)               # NEUTRAL_IDLE
    visual = _visual(pad=pad, window=window)
    visual.refresh(now=T0)                          # establish NEUTRAL_IDLE
    pad.set(0.80, 0.70, 0.80)                       # candidate is now PLAYFUL

    # Speaking toggles WITHIN the 8 s window — prompt, ungated, zone unchanged.
    visual.set_speaking(True)
    assert visual.current_loop.zone is Zone.NEUTRAL_IDLE       # zone NOT changed
    assert visual.current_loop.variant is SpeakingState.TALKING
    visual.set_speaking(False)
    assert visual.current_loop.variant is SpeakingState.IDLE

    # The variant flips did NOT reset the zone-stability timer: at 8 s the zone
    # switch is still permitted.
    loop8 = visual.refresh(now=T0 + timedelta(seconds=8))
    assert loop8.zone is Zone.PLAYFUL


def test_speaking_set_before_first_zone_is_applied_on_first_refresh():
    window = FakeWindow()
    visual = _visual(pad=StubPAD(0.65, 0.65, 0.65), window=window)
    visual.set_speaking(True)                       # no zone yet → stored only
    assert visual.current_loop is None
    assert window.loops == []
    loop = visual.refresh(now=T0)                   # first zone applies talking
    assert loop.zone is Zone.ENGAGED and loop.variant is SpeakingState.TALKING


# ===========================================================================
# 3) 8-SECOND minimum-before-switch (Req 5; v4 constants table).
# ===========================================================================

def test_stability_constant_is_v4_eight_seconds():
    assert ZONE_STABILITY_SECONDS == 8


def test_first_zone_is_displayed_immediately():
    window = FakeWindow()
    visual = _visual(pad=StubPAD(0.80, 0.70, 0.80), window=window)  # PLAYFUL
    loop = visual.refresh(now=T0)
    assert loop.zone is Zone.PLAYFUL         # immediate, no prior zone to hold
    assert len(window.loops) == 1


def test_zone_held_below_8s_then_switches_at_8s():
    window = FakeWindow()
    pad = StubPAD(0.55, 0.45, 0.58)          # NEUTRAL_IDLE
    visual = _visual(pad=pad, window=window)
    assert visual.refresh(now=T0).zone is Zone.NEUTRAL_IDLE

    pad.set(0.80, 0.70, 0.80)                # PAD jumps into PLAYFUL

    # < 8 s: HOLD the current zone (prevents flickering, v4).
    assert visual.refresh(now=T0 + timedelta(seconds=5)).zone is Zone.NEUTRAL_IDLE
    assert visual.refresh(now=T0 + timedelta(seconds=7.999)).zone is Zone.NEUTRAL_IDLE

    # ≥ 8 s: SWITCH (the 8.0 s boundary permits it — the gate is ≥).
    assert visual.refresh(now=T0 + timedelta(seconds=8)).zone is Zone.PLAYFUL


def test_switch_resets_the_stability_timer():
    window = FakeWindow()
    pad = StubPAD(0.55, 0.45, 0.58)
    visual = _visual(pad=pad, window=window)
    visual.refresh(now=T0)                                    # NEUTRAL_IDLE @ t0
    pad.set(0.80, 0.70, 0.80)
    assert visual.refresh(now=T0 + timedelta(seconds=8)).zone is Zone.PLAYFUL  # switch @ +8

    # Now a third candidate appears; the timer restarted at +8, so a switch is
    # blocked until +16 (8 s after the last switch).
    pad.set(0.20, 0.50, 0.40)                                 # CONCERNED candidate
    assert visual.refresh(now=T0 + timedelta(seconds=15)).zone is Zone.PLAYFUL  # held
    assert visual.refresh(now=T0 + timedelta(seconds=16)).zone is Zone.CONCERNED  # switched


def test_same_candidate_zone_is_never_a_switch():
    window = FakeWindow()
    pad = StubPAD(0.65, 0.65, 0.65)          # ENGAGED
    visual = _visual(pad=pad, window=window)
    visual.refresh(now=T0)
    # PAD wobbles but stays inside ENGAGED — no switch, no re-render.
    pad.set(0.62, 0.61, 0.66)
    visual.refresh(now=T0 + timedelta(seconds=20))
    assert visual.current_zone is Zone.ENGAGED
    assert len(window.loops) == 1            # de-duped (same loop)


def test_stability_window_is_injectable():
    window = FakeWindow()
    pad = StubPAD(0.55, 0.45, 0.58)
    visual = _visual(pad=pad, window=window, stability_seconds=2)
    visual.refresh(now=T0)
    pad.set(0.80, 0.70, 0.80)
    assert visual.refresh(now=T0 + timedelta(seconds=1)).zone is Zone.NEUTRAL_IDLE  # < 2s
    assert visual.refresh(now=T0 + timedelta(seconds=2)).zone is Zone.PLAYFUL       # ≥ 2s


# ===========================================================================
# 4) GRACEFUL DEGRADATION — inward/waiting loop on cloud failure (Req 6).
# ===========================================================================

def test_cloud_failure_shows_inward_waiting_overriding_pad():
    window = FakeWindow()
    pad = StubPAD(0.80, 0.70, 0.80)          # PLAYFUL signature
    visual = _visual(pad=pad, window=window)
    visual.refresh(now=T0)
    assert visual.current_loop.zone is Zone.PLAYFUL

    # Cloud fails → inward/waiting overrides PAD, PROMPTLY (within the 8 s window
    # of the just-established zone → proves degradation is ungated).
    visual.set_cloud_available(False)
    assert visual.current_loop.zone is Zone.INWARD_WAITING
    assert visual.current_loop.loop_id == "inward_waiting"

    # A refresh while degraded stays inward/waiting REGARDLESS of PAD.
    pad.set(0.55, 0.45, 0.58)
    assert visual.refresh(now=T0).zone is Zone.INWARD_WAITING


def test_degradation_loop_has_no_talking_variant():
    window = FakeWindow()
    visual = _visual(pad=StubPAD(0.80, 0.70, 0.80), window=window)
    visual.refresh(now=T0)
    visual.set_cloud_available(False)
    # Even if speaking-state flips, the withdrawn loop stays a single loop.
    visual.set_speaking(True)
    assert visual.current_loop.zone is Zone.INWARD_WAITING
    assert visual.current_loop.variant is SpeakingState.IDLE
    assert visual.current_loop.loop_id == "inward_waiting"


def test_degradation_before_any_zone_still_shows_inward_waiting():
    visual = _visual(pad=StubPAD(0.80, 0.70, 0.80), window=FakeWindow())
    visual.set_cloud_available(False)        # before any refresh
    assert visual.current_loop is not None
    assert visual.current_loop.zone is Zone.INWARD_WAITING


def test_cloud_restore_resumes_pad_driven_zone():
    window = FakeWindow()
    pad = StubPAD(0.80, 0.70, 0.80)
    visual = _visual(pad=pad, window=window)
    visual.refresh(now=T0)
    visual.set_cloud_available(False)
    assert visual.is_degraded is True
    assert visual.current_loop.zone is Zone.INWARD_WAITING

    # Restore → resume PAD-driven zones, no announcement (v4).
    visual.set_cloud_available(True)
    assert visual.is_degraded is False
    later = visual.refresh(now=T0 + timedelta(seconds=30))
    assert later.zone is not Zone.INWARD_WAITING
    assert later.zone in PAD_ZONES


# ===========================================================================
# 5) RUNS INDEPENDENTLY / in parallel with language generation (Req 8).
# ===========================================================================

def test_refresh_depends_only_on_pad_seam_and_window():
    # No LLM/SoulFilter/Appraisal collaborator exists; the loop runs with no turn.
    pad = StubPAD(0.55, 0.45, 0.58)
    window = FakeWindow()
    visual = _visual(pad=pad, window=window)
    for _ in range(5):
        loop = visual.refresh()              # uses the injected clock (→ T0)
        assert loop.zone in PAD_ZONES
    assert pad.reads >= 5                     # it read PAD each non-degraded tick
    assert len(window.loops) == 1            # nothing changed → de-duped


# ===========================================================================
# 6) PAD-PURITY / never writes PAD (tripwire) + structural proofs (Req 2).
# ===========================================================================

def test_visual_layer_never_writes_pad_tripwire():
    spy = SpyPAD()
    spy.initialize(None)                                  # baseline
    # Move PAD to a non-default zone via the REAL write path, THEN reset the
    # counters so we count ONLY what the Visual Layer does.
    spy.apply_appraisal_delta(PADDelta(0.30, 0.30, 0.30, valence=Valence.POSITIVE))
    before = spy.get_current_pad()                        # PLAYFUL-region
    assert map_pad_to_zone(before) is Zone.PLAYFUL
    spy.reads = 0
    spy.writes = 0

    window = FakeWindow()
    visual = VisualLayer(pad_source=spy, window=window, clock=lambda: T0)
    # Exercise every path: refreshes across time, speaking toggles, degrade+restore.
    for i in range(6):
        visual.refresh(now=T0 + timedelta(seconds=i * 9))
        visual.set_speaking(i % 2 == 0)
    visual.set_cloud_available(False)
    visual.refresh(now=T0)
    visual.set_cloud_available(True)
    visual.refresh(now=T0 + timedelta(seconds=100))
    after = spy.get_current_pad()

    # It READ PAD (a presentation read of substrate) ...
    assert spy.reads >= 2
    # ... but NEVER wrote it — no mutator call, PAD byte-identical.
    assert spy.writes == 0
    assert before == after


def _imported_module_names(module):
    tree = ast.parse(inspect.getsource(module))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_module_imports_no_write_capable_or_gui_module():
    mods = _imported_module_names(vl_mod)
    forbidden = {
        "daemon.graph_manager", "daemon.appraisal_chain", "daemon.needs_system",
        "daemon.state_manager", "daemon.aria_daemon", "daemon.soul_filter",
        "daemon.llm_interface",
    }
    assert not (mods & forbidden), f"forbidden imports present: {mods & forbidden}"
    # The ONLY daemon symbol imported is the read-only PAD type.
    daemon_imports = {m for m in mods if m and m.startswith("daemon")}
    assert daemon_imports == {"daemon.pad_engine"}
    # No GUI/video toolkit is imported (it is injected behind VideoWindow).
    assert not any(m.startswith("PyQt6") for m in mods)
    assert "mpv" not in mods


def test_module_never_calls_a_pad_mutator_in_source():
    src = inspect.getsource(vl_mod)
    # The CALL forms (dot + paren) must never appear — the docstring's bare
    # mentions of the names do not match these.
    for call in (".apply_appraisal_delta(", ".on_soul_tick(", ".initialize("):
        assert call not in src, f"visual_layer must not call {call}"


# ===========================================================================
# 7) CONTRACT — VisualLayerPort + injected Protocols + REAL-Daemon end-to-end.
# ===========================================================================

def test_satisfies_visual_layer_port_and_fakes_satisfy_protocols():
    visual = _visual()
    assert isinstance(visual, VisualLayerPort)
    assert isinstance(StubPAD(), PADReader)
    assert isinstance(FakeWindow(), VideoWindow)


def test_zoneloop_id_and_inward_waiting_normalization():
    assert ZoneLoop(Zone.ENGAGED, SpeakingState.TALKING).loop_id == "engaged_talking"
    assert ZoneLoop(Zone.NEUTRAL_IDLE).loop_id == "neutral_idle_idle"
    # INWARD_WAITING collapses to a single (IDLE) loop.
    z = ZoneLoop(Zone.INWARD_WAITING, SpeakingState.TALKING)
    assert z.variant is SpeakingState.IDLE
    assert z.loop_id == "inward_waiting"


class VisualSpeakingBridge:
    """Top-of-tree WIRING (OQ-2): implements the Daemon's AudioPipelinePort by
    forwarding the Daemon's EXISTING speak() boundary to the Visual Layer's
    speaking-state contract. The Daemon is UNCHANGED — this bridge lives at the
    wiring layer, exactly as the audio-pipeline's streaming driver loop (OQ-1)
    does for capture."""
    def __init__(self, visual: VisualLayer):
        self._visual = visual
        self.saw_talking = False
        self.talking_loop = None
        self.spoken = []

    def speak(self, text):
        self._visual.set_speaking(True)          # Daemon output-pending → talking
        self.saw_talking = True
        self.talking_loop = self._visual.current_loop
        self.spoken.append(text)
        self._visual.set_speaking(False)         # speak() returned → idle

    def stop_playback(self):
        pass

    def play_thinking_sound(self, sound):
        pass

    def play_reconsideration_sound(self):
        pass


def test_real_daemon_drives_speaking_state_and_visual_reads_real_pad(tmp_path):
    pad = PADEngine()
    window = FakeWindow()
    visual = VisualLayer(pad_source=pad, window=window, clock=lambda: T0)
    bridge = VisualSpeakingBridge(visual)
    # The bridge is a valid AudioPipelinePort the REAL Daemon can drive.
    assert isinstance(bridge, AudioPipelinePort)

    ctx = make_daemon(tmp_path, pad=pad, audio=bridge)
    d = ctx.daemon
    d.startup()                                  # initializes the REAL PADEngine

    # Establish an initial zone (idle) by reading the REAL engine's PAD.
    first = visual.refresh(now=T0)
    assert isinstance(first.zone, Zone) and first.variant is SpeakingState.IDLE

    # Drive a real turn: the Daemon calls bridge.speak() between its output-
    # pending True/False boundary → the Visual Layer goes talking then idle,
    # with NO modification to the Daemon.
    d.route_inbound_turn(
        user_text="thanks, that really helped",
        session_id="s1", entity_refs=(), entity_node_id=None, now=T0,
    )

    # The Daemon's speak() boundary drove the speaking-state contract.
    assert bridge.saw_talking is True
    assert bridge.talking_loop is not None
    assert bridge.talking_loop.variant is SpeakingState.TALKING
    # ...and it returned to the idle variant after speaking.
    assert visual.current_loop.variant is SpeakingState.IDLE

    # The Visual Layer reads PAD from the REAL PADEngine (post-turn zone valid).
    assert visual.refresh(now=T0).zone in PAD_ZONES
    ctx.graph.close()
