"""Tests — Module 8: Daemon / Soul Tick (daemon/aria_daemon.py).

Locked spec: .kiro/specs/daemon/{requirements,design,tasks}.md.

Plain pytest, NO hypothesis (matches Modules 1–6 style). These tests prove the
PHILOSOPHY contracts of the ORCHESTRATOR, not just behavior:

  * TWO SEPARATE CLOCKS. soul_tick drives PAD decay + Energy and NEVER runs a
    DMN pass; dmn_tick runs a DMN pass and NEVER decays PAD. Driven
    independently; neither triggers the other. (constraint 2 / v4 Two-Process)
  * INITIALIZE ONCE. PADEngine.initialize() is called exactly once at startup
    (proven with a counting engine) and a second startup() is GUARDED (raises).
    (constraint 4c / HANDOFF_NOTES)
  * CONSISTENCY_FLAGS CLEARED each session on startup, and the clear persists;
    the quality record is left intact. (constraint 4b / HANDOFF_NOTES)
  * last_applied_valence ROUND-TRIPS on save AND on shutdown: saved as its
    string and restored into a fresh PADEngine via initialize(restored_valence).
    (constraint 4a / HANDOFF_NOTES)
  * F4 / BARGE-IN → ZERO internal effect (tripwire): PAD, Energy, graph, and the
    persisted state files are byte-identical afterward; the PAD mutator is never
    called; the ONLY effect is Audio.stop_playback(). (constraint 3 / Addendum §5)
  * INITIATIVE keys on the categorical `due` state (no number), fires ONCE, does
    NOT nag, and enters at soul_filter directly — skipping wake/STT/appraisal.
    (constraint 5 / Addendum §7 / v4 Layer 2)
  * A FULL inbound turn routes Audio(fake)→Appraisal→SoulFilter→LLM(fake)→gate
    →TTS(fake) end-to-end with the REAL modules.
  * The Daemon COMPUTES NO FEELING: `apply_appraisal_delta` never appears in its
    source (no PAD write anywhere), and PAD only ever moves via the modules.

Plus tests for the additive DMN-contract-gap closures (each with its own test):
appraisal_chain.submit_aha_insight; graph_manager.predictability_evidence /
dependability_evidence / highest_salience_unconnected_candidates — including a
DMN pass wired to the REAL graph predicates.
"""

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import daemon.aria_daemon as daemon_mod
from daemon.aria_daemon import (
    AriaDaemon,
    ThinkingSound,
    select_thinking_sound,
    build_initiative_appraisal,
    pad_state_to_snapshot,
    valence_from_str,
    valence_to_str,
    read_pad_last_valence,
    need_states_to_mapping,
)
from daemon.pad_engine import PADEngine, PADSnapshot, PADDelta, Valence, PAD_BASELINE
from daemon.state_manager import StateManager, PADState, SelfModel, CONSISTENCY_FLAG_NAMES
from daemon.needs_system import NeedsSystem, ENERGY_CRITICAL
from daemon.types import ENERGY_LOW
from daemon.graph_manager import MemoryGraph, PoignancyCategory, RelationalStage, EdgeType
from daemon.appraisal_chain import AppraisalChain
from daemon.soul_filter import SoulFilter, NeedState, NeedStates
from daemon.llm_interface import LLMInterface
from daemon.dmn import DMN, DMNPassInput
from daemon.backend_router import BackendRouter
from daemon.aria_daemon import DaemonState


T0 = datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc)
_BENIGN_REPLY = "That's genuinely good to hear. Shipping something real is hard, and you did it."


# ===========================================================================
# Fakes for the NOT-YET-BUILT modules (Audio Pipeline = Module 7) and the LLM
# backend transports. The core Aria modules (PAD, Needs, Graph, Appraisal,
# Soul_Filter, LLM Interface, DMN, State_Manager) are the REAL ones.
# ===========================================================================

class FakeEmbedding:
    """Injected embedding model (Addendum §1) — deterministic, non-generative.
    A token-hash bag-of-words over a wide vector so UNRELATED sentences are
    genuinely dissimilar (low cosine) — the char-frequency toy used elsewhere is
    too coarse and would false-trigger VULNERABILITY_DISCLOSURE on ordinary
    text. Deterministic (stable token hash), so tests are reproducible."""
    DIM = 128

    @staticmethod
    def _tok_hash(tok: str) -> int:
        h = 0
        for ch in tok:
            h = (h * 131 + ord(ch)) % 1_000_003
        return h

    def embed(self, text):
        v = [0.0] * self.DIM
        for tok in (text or "").lower().split():
            v[self._tok_hash(tok) % self.DIM] += 1.0
        return v


class FakeAudio:
    """Implements AudioPipelinePort (Module 7 contract). Records every call so
    tests can assert TTS, thinking sounds, and — critically — that F4/barge-in
    do nothing but stop playback."""
    def __init__(self):
        self.spoken = []
        self.stops = 0
        self.thinking_sounds = []
        self.reconsiderations = 0

    def speak(self, text): self.spoken.append(text)
    def stop_playback(self): self.stops += 1
    def play_thinking_sound(self, sound): self.thinking_sounds.append(sound)
    def play_reconsideration_sound(self): self.reconsiderations += 1


class FakeCloud:
    """Cloud ModelTransport (LLM Interface backend / BackendRouter's "groq").
    Records prompts; returns a canned, gate-safe reply. `healthy` +
    `is_healthy()` let tests drive BackendRouter's health-probe chain (Change
    1's test doubles use the same shape)."""
    def __init__(self, reply=_BENIGN_REPLY, healthy=True):
        self.reply = reply
        self.prompts = []
        self.healthy = healthy

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.reply

    def is_healthy(self):
        return self.healthy


class FakeLocal:
    """Local (Gemma) LocalModelTransport — also BackendRouter's "gemma" tier.
    Must satisfy the protocol (is_loaded/load/unload/generate) plus the
    optional HealthProbe (`is_healthy`) and a `load_calls` counter so tests
    can prove `ensure_local_loaded()`'s idempotence (Track A)."""
    def __init__(self, healthy=True, reply="local reply"):
        self._loaded = False
        self.prompts = []
        self.healthy = healthy
        self.reply = reply
        self.load_calls = 0
        self.unload_calls = 0

    @property
    def is_loaded(self): return self._loaded

    def load(self):
        self._loaded = True
        self.load_calls += 1

    def unload(self):
        self._loaded = False
        self.unload_calls += 1

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.reply

    def is_healthy(self):
        return self.healthy


class SpyDMN:
    """Records DMN invocations WITHOUT side effects. Used to prove the soul tick
    never runs a DMN pass and the DMN tick does. Returns a minimal result whose
    only field the Daemon reads is `buffer_consumed`."""
    def __init__(self):
        self.idle_calls = 0
        self.forced_calls = 0
        self._self_entity_id = None

    def set_self_entity_id(self, entity_id):
        self._self_entity_id = entity_id

    def run_idle_pass(self, pass_input):
        self.idle_calls += 1
        return SimpleNamespace(buffer_consumed=[])

    def run_forced_partial_pass(self, pass_input):
        self.forced_calls += 1
        return SimpleNamespace(buffer_consumed=[])


class CountingPAD(PADEngine):
    """Real PADEngine that counts initialize() calls and records the
    restored_valence passed — to prove initialize() runs exactly once with the
    restored valence."""
    def __init__(self):
        super().__init__()
        self.init_calls = 0
        self.init_valences = []

    def initialize(self, restored, restored_valence=None):
        self.init_calls += 1
        self.init_valences.append(restored_valence)
        return super().initialize(restored, restored_valence)


class TripwirePAD(PADEngine):
    """Real PADEngine that counts apply_appraisal_delta calls — a live tripwire
    proving F4/barge-in cause NO PAD write."""
    def __init__(self):
        super().__init__()
        self.delta_calls = 0

    def apply_appraisal_delta(self, delta):
        self.delta_calls += 1
        return super().apply_appraisal_delta(delta)


# ---------------------------------------------------------------------------
# Test-only helpers.
# ---------------------------------------------------------------------------

def _count_events(graph):
    return graph._conn.execute("SELECT COUNT(*) FROM event_nodes").fetchone()[0]


def _dir_snapshot(path):
    return {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()}


def make_daemon(
    tmp_path,
    *,
    pad=None,
    dmn=None,
    audio=None,
    state=None,
    graph=None,
    needs=None,
    self_entity_id=None,
    primary_entity_id=None,
    cloud_reply=_BENIGN_REPLY,
    clock=None,
    backend_router=None,
    local=None,
    proposal_timeout=None,
):
    """Build an AriaDaemon wired to the REAL core modules + fakes for the unbuilt
    Audio Pipeline and the LLM transports. Returns a namespace of every part so
    tests can inspect/drive them.

    `backend_router` (Track A, optional): pass a real BackendRouter built over
    `local` (gemma tier) / `cloud` (groq tier) — or leave both at their
    defaults and pass `backend_router=True` to have this helper build one for
    you over the SAME cloud/local fakes already wired into LLMInterface, so
    router-driven selection and the LLM Interface's fallback share one
    transport identity."""
    emb = FakeEmbedding()
    graph = graph or MemoryGraph(":memory:", embedding_model=emb)
    pad = pad if pad is not None else PADEngine()
    needs = needs or NeedsSystem(graph, self_entity_id=self_entity_id)
    appraisal = AppraisalChain(pad_engine=pad, graph=graph, embedding_model=emb)
    cloud = FakeCloud(cloud_reply)
    local = local if local is not None else FakeLocal()
    llm = LLMInterface(cloud_transport=cloud, local_transport=local)
    audio = audio or FakeAudio()
    soul = SoulFilter(pad_engine=pad, graph=graph, llm_client=llm,
                      on_reconsideration=audio.play_reconsideration_sound)
    state = state or StateManager(state_dir=tmp_path)
    dmn = dmn or DMN(graph=graph, appraisal=appraisal, needs=needs, state=state,
                     self_entity_id=self_entity_id)
    clock = clock or (lambda: T0)

    router = None
    azure = None
    if backend_router is True:
        # Build a real BackendRouter over the SAME local/cloud fakes used by
        # LLMInterface's internal chain, and a THIRD fake for azure (tier_2) —
        # router-selected "gemma"/"groq" transports are then object-identical
        # to what LLMInterface would otherwise pick internally.
        azure = FakeCloud("azure reply")
        router = BackendRouter(
            gemma_transport=local, groq_transport=cloud, azure_transport=azure,
            clock=clock,
        )
    elif backend_router is not None:
        router = backend_router

    daemon_kwargs = dict(
        pad_engine=pad, needs_system=needs, graph=graph, appraisal_chain=appraisal,
        soul_filter=soul, dmn=dmn, state_manager=state, audio=audio,
        primary_entity_id=primary_entity_id, self_entity_id=self_entity_id, clock=clock,
        backend_router=router,
    )
    if proposal_timeout is not None:
        daemon_kwargs["proposal_timeout"] = proposal_timeout
    d = AriaDaemon(**daemon_kwargs)
    return SimpleNamespace(
        daemon=d, pad=pad, needs=needs, graph=graph, appraisal=appraisal, soul=soul,
        llm=llm, cloud=cloud, local=local, audio=audio, dmn=dmn, state=state, emb=emb,
        backend_router=router, azure=azure,
    )


# ===========================================================================
# 1) TWO SEPARATE CLOCKS, driven independently (constraint 2 / v4 Two-Process).
# ===========================================================================

def test_soul_tick_decays_pad_and_never_runs_dmn(tmp_path):
    spy = SpyDMN()
    ctx = make_daemon(tmp_path, dmn=spy)
    d = ctx.daemon
    d.startup()
    # Move PAD off baseline with a REAL appraisal delta so decay is observable
    # and a real valence is set (test-side action; the Daemon writes no PAD).
    ctx.pad.apply_appraisal_delta(PADDelta(0.1, 0.0, 0.0, valence=Valence.POSITIVE))
    p_before = ctx.pad.get_current_pad().pleasure

    d.soul_tick(now=T0)
    d.soul_tick(now=T0)
    d.soul_tick(now=T0)

    # PAD decayed toward baseline — the soul tick drove Module 1's decay.
    assert ctx.pad.get_current_pad().pleasure < p_before
    # ...and the soul tick NEVER ran a DMN pass (separate clock).
    assert spy.idle_calls == 0 and spy.forced_calls == 0
    assert d.soul_tick_count == 3 and d.dmn_tick_count == 0


def test_dmn_tick_runs_pass_and_never_touches_pad(tmp_path):
    spy = SpyDMN()
    ctx = make_daemon(tmp_path, dmn=spy)
    d = ctx.daemon
    d.startup()
    ctx.pad.apply_appraisal_delta(PADDelta(0.1, 0.0, 0.0, valence=Valence.POSITIVE))
    pad_before = ctx.pad.get_current_pad()

    # Genuinely idle (no voice for > 8 min, no pending output) → DMN pass runs.
    result = d.dmn_tick(now=T0 + timedelta(minutes=9))

    assert result is not None
    assert spy.idle_calls == 1
    # The DMN tick did NOT decay PAD (separate clock — maintenance vs dream).
    assert ctx.pad.get_current_pad() == pad_before
    assert d.dmn_tick_count == 1 and d.soul_tick_count == 0


def test_dmn_tick_does_nothing_when_not_idle(tmp_path):
    spy = SpyDMN()
    ctx = make_daemon(tmp_path, dmn=spy)
    d = ctx.daemon
    d.startup()
    # Only 2 minutes since boot (< 8 min) → not idle → no pass.
    assert d.dmn_tick(now=T0 + timedelta(minutes=2)) is None
    assert spy.idle_calls == 0


def test_scheduler_drives_both_clocks_on_independent_intervals(tmp_path):
    spy = SpyDMN()
    ctx = make_daemon(tmp_path, dmn=spy)
    d = ctx.daemon
    d.startup()
    # soul interval 3s, dmn interval 30s (defaults). At +3s only the soul clock
    # is due; at +31s both are due — two clocks on their OWN schedules.
    assert d.run_scheduler_step(now=T0 + timedelta(seconds=3)) == ["soul"]
    assert d.run_scheduler_step(now=T0 + timedelta(seconds=31)) == ["soul", "dmn"]
    assert d.soul_tick_count == 2
    assert d.dmn_tick_count == 1  # the dmn CLOCK fired once (pass gated on idle)


# ===========================================================================
# 2) initialize() called EXACTLY ONCE, second startup GUARDED (constraint 4c).
# ===========================================================================

def test_pad_initialize_called_exactly_once_and_second_startup_guarded(tmp_path):
    pad = CountingPAD()
    ctx = make_daemon(tmp_path, pad=pad)
    d = ctx.daemon
    d.startup()
    assert pad.init_calls == 1              # initialize() ran exactly once
    assert d.started is True
    # A second startup() is GUARDED (initialize() is NOT idempotent, HANDOFF).
    with pytest.raises(RuntimeError, match="exactly once"):
        d.startup()
    assert pad.init_calls == 1              # still once — guard fired before init


def test_startup_passes_restored_valence_to_initialize(tmp_path):
    # Persist a valence, then a fresh daemon must pass it to initialize().
    state = StateManager(state_dir=tmp_path)
    state.save_all(PADState(0.62, 0.40, 0.71), 55.0, SelfModel.default(), "negative")
    pad = CountingPAD()
    ctx = make_daemon(tmp_path, pad=pad, state=state)
    ctx.daemon.startup()
    # initialize() received the restored valence converted from the string.
    assert pad.init_valences == [Valence.NEGATIVE]


# ===========================================================================
# 3) consistency_flags CLEARED on startup, and the clear persists (constraint 4b).
# ===========================================================================

def test_consistency_flags_cleared_on_startup(tmp_path):
    state = StateManager(state_dir=tmp_path)
    # Previous session left ALL flags True + a quality record.
    seeded = SelfModel(
        quality_record=["responded_well", "adequately"],
        consistency_flags={n: True for n in CONSISTENCY_FLAG_NAMES},
        recent_learning_user="ships when scared",
    )
    state.save_self_model(seeded)

    ctx = make_daemon(tmp_path, state=state)
    ctx.daemon.startup()

    reloaded = state.load_self_model()
    # Flags reset each session (HANDOFF): all False now, and it PERSISTED.
    assert all(v is False for v in reloaded.consistency_flags.values())
    assert set(reloaded.consistency_flags.keys()) == set(CONSISTENCY_FLAG_NAMES)
    # The rest of the self-model is untouched (only flags reset).
    assert reloaded.quality_record == ["responded_well", "adequately"]
    assert reloaded.recent_learning_user == "ships when scared"


# ===========================================================================
# 4) last_applied_valence ROUND-TRIPS on save + shutdown (constraint 4a).
# ===========================================================================

def test_last_applied_valence_round_trips_on_shutdown_then_restart(tmp_path):
    state = StateManager(state_dir=tmp_path)
    ctx1 = make_daemon(tmp_path, state=state)
    ctx1.daemon.startup()
    # A real appraisal delta sets PAD off-baseline AND the last-applied valence.
    ctx1.pad.apply_appraisal_delta(PADDelta(0.10, 0.0, 0.0, valence=Valence.POSITIVE))

    ctx1.daemon.shutdown()   # HANDOFF: save PAD + Energy + last_applied_valence

    # Persisted as the opaque string.
    assert state.load_last_applied_valence() == "positive"
    saved_pad = state.load_pad()
    assert abs(saved_pad.pleasure - 0.65) < 1e-9

    # A fresh process (new PADEngine) restores it via initialize(restored_valence).
    state2 = StateManager(state_dir=tmp_path)
    pad2 = PADEngine()
    ctx2 = make_daemon(tmp_path, pad=pad2, state=state2)
    ctx2.daemon.startup()
    assert read_pad_last_valence(pad2) is Valence.POSITIVE       # valence restored
    assert abs(pad2.get_current_pad().pleasure - 0.65) < 1e-9    # PAD restored too


def test_last_applied_valence_round_trips_on_periodic_save(tmp_path):
    state = StateManager(state_dir=tmp_path)
    ctx = make_daemon(tmp_path, state=state)
    ctx.daemon.startup()
    ctx.pad.apply_appraisal_delta(PADDelta(-0.05, 0.0, 0.0, valence=Valence.NEGATIVE))
    ctx.daemon.save_periodic()   # same round-trip on the periodic cadence
    assert state.load_last_applied_valence() == "negative"


def test_valence_wiring_helpers_round_trip():
    # The wiring helpers the HANDOFF names: string <-> Valence, both directions.
    for v in Valence:
        assert valence_from_str(valence_to_str(v)) is v
    assert valence_from_str(None) is None
    assert valence_from_str("not_a_valence") is None
    # PADState -> PADSnapshot conversion helper.
    snap = pad_state_to_snapshot(PADState(0.1, 0.2, 0.3))
    assert (snap.pleasure, snap.arousal, snap.dominance) == (0.1, 0.2, 0.3)


# ===========================================================================
# 5) F4 / BARGE-IN → ZERO internal effect (constraint 3 / Addendum §5).
# ===========================================================================

def test_f4_and_barge_in_have_zero_internal_effect_tripwire(tmp_path):
    pad = TripwirePAD()
    state = StateManager(state_dir=tmp_path)
    ctx = make_daemon(tmp_path, pad=pad, state=state)
    d = ctx.daemon
    d.startup()

    # Arrange non-trivial internal state: PAD off-baseline, a graph node, Energy.
    pad.apply_appraisal_delta(PADDelta(0.1, 0.05, 0.0, valence=Valence.POSITIVE))
    ctx.graph.write_event_node(
        description="something happened", session_id="s1", appraisal_q1="high",
        appraisal_q2="positive", appraisal_q3="user",
        poignancy_category=PoignancyCategory.HIGH, now=T0,
    )
    d.soul_tick(now=T0)  # let Energy move once so we can prove F4 doesn't touch it

    # Snapshot EVERYTHING that could be an "internal effect".
    pad_before = pad.get_current_pad()
    energy_before = ctx.needs.get_energy()
    events_before = _count_events(ctx.graph)
    edges_before = ctx.graph._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    files_before = _dir_snapshot(tmp_path)
    delta_calls_before = pad.delta_calls

    # THE INTERRUPTS.
    d.on_f4_interrupt()
    d.on_barge_in()

    # ZERO internal effect: nothing moved.
    assert pad.get_current_pad() == pad_before            # no PAD change
    assert pad.delta_calls == delta_calls_before          # PAD mutator NEVER called
    assert ctx.needs.get_energy() == energy_before        # no Energy change
    assert _count_events(ctx.graph) == events_before      # no graph write
    assert ctx.graph._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == edges_before
    assert _dir_snapshot(tmp_path) == files_before        # no persisted-state write
    # The ONLY effect: audio stopped (once per interrupt).
    assert ctx.audio.stops == 2


def test_daemon_source_never_writes_pad():
    """Structural proof the Daemon computes NO feeling: the PAD-write CALL
    `.apply_appraisal_delta(` never appears anywhere in the Daemon's source —
    F4, barge-in, initiative, and turn routing all move PAD only THROUGH the
    modules (constraint 1). (The name appears in docstrings that EXPLAIN the
    philosophy; what must be absent is the call.)"""
    src = inspect.getsource(daemon_mod)
    assert ".apply_appraisal_delta(" not in src


def test_f4_and_barge_in_are_pure_audio_stops():
    """Each interrupt's body is a single Audio.stop_playback() — no path to PAD,
    appraisal, graph, needs, or state (Addendum §5)."""
    for fn in (AriaDaemon.on_f4_interrupt, AriaDaemon.on_barge_in):
        body = inspect.getsource(fn)
        assert "stop_playback" in body
        for forbidden in ("apply_appraisal_delta", "appraise", "write_event_node",
                          "write_edge", "save_", "on_soul_tick"):
            assert forbidden not in body, (fn.__name__, forbidden)


# ===========================================================================
# 6) INITIATIVE: keys on `due`, fires once, no nag, enters at soul_filter.
# ===========================================================================

def test_highest_pressure_need_is_categorical_keyed_on_due_no_number():
    # All satisfied → no pressure → no need selected.
    assert AriaDaemon._select_highest_pressure_need(NeedStates()) is None
    # `due` is the categorical state that triggers (not a number).
    assert AriaDaemon._select_highest_pressure_need(
        NeedStates(connection=NeedState.DUE)) == "connection"
    # Canonical-order tie-break among simultaneously-due needs (F-8b).
    assert AriaDaemon._select_highest_pressure_need(
        NeedStates(connection=NeedState.SATISFIED, growth=NeedState.DUE)) == "growth"
    # `neglected` also triggers defensively (though Needs System never emits it).
    assert AriaDaemon._select_highest_pressure_need(
        NeedStates(connection=NeedState.NEGLECTED)) == "connection"


def test_initiative_fires_once_no_nag_and_enters_at_soul_filter(tmp_path):
    # Fresh graph → NO qualifying evidence for any need → all needs `due`.
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    d.startup()
    events_before = _count_events(ctx.graph)

    # First soul tick: initiative fires ONCE for the highest-pressure due need.
    d.soul_tick(now=T0)
    assert d.initiative_count == 1
    assert ctx.audio.spoken                        # Aria spoke (TTS)
    assert len(ctx.cloud.prompts) == 1             # entered soul_filter → LLM invoked
    # Entered at soul_filter DIRECTLY, skipping wake/STT/appraisal → NO EventNode
    # was written (appraisal is the only thing that writes events in this flow).
    assert _count_events(ctx.graph) == events_before
    spoken_after_first = len(ctx.audio.spoken)

    # Second soul tick: the SAME need is still due but already expressed → NO NAG.
    d.soul_tick(now=T0)
    assert d.initiative_count == 1
    assert len(ctx.audio.spoken) == spoken_after_first


def test_initiative_does_not_fire_when_no_need_is_due(tmp_path):
    # Force all needs SATISFIED by injecting a needs stub the Daemon reads.
    class AllSatisfiedNeeds:
        def initialize(self, restored=None): pass
        def get_energy(self): return 100.0
        def on_soul_tick(self): pass
        def on_idle_recovery(self): pass
        def get_need_states(self, now=None): return NeedStates()  # all satisfied
        def set_self_entity_id(self, entity_id): pass
    ctx = make_daemon(tmp_path, needs=AllSatisfiedNeeds())
    d = ctx.daemon
    d.startup()
    d.soul_tick(now=T0)
    assert d.initiative_count == 0     # nothing due → no reach-out
    assert ctx.audio.spoken == []


def test_initiative_relatches_after_need_is_satisfied_again(tmp_path):
    """The no-nag latch resets when the need is satisfied again, so a LATER drop
    can express once more (v4: 'expresses a need exactly once when it drops')."""
    class ToggleNeeds:
        def __init__(self): self.state = NeedState.DUE
        def initialize(self, restored=None): pass
        def get_energy(self): return 100.0
        def on_soul_tick(self): pass
        def on_idle_recovery(self): pass
        def get_need_states(self, now=None):
            return NeedStates(connection=self.state)
        def set_self_entity_id(self, entity_id): pass
    needs = ToggleNeeds()
    ctx = make_daemon(tmp_path, needs=needs)
    d = ctx.daemon
    d.startup()
    d.soul_tick(now=T0)
    assert d.initiative_count == 1          # due → fires once
    d.soul_tick(now=T0)
    assert d.initiative_count == 1          # still due → no nag
    needs.state = NeedState.SATISFIED
    d.soul_tick(now=T0)                     # satisfied → latch resets, no fire
    assert d.initiative_count == 1
    needs.state = NeedState.DUE
    d.soul_tick(now=T0)                     # due again → fires once more
    assert d.initiative_count == 2


# ===========================================================================
# 7) FULL inbound turn end-to-end with the REAL modules.
#    Audio(fake) → Appraisal → SoulFilter → LLM(fake) → gate → TTS(fake)
# ===========================================================================

def test_full_inbound_turn_routes_end_to_end_with_real_modules(tmp_path):
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    d.startup()
    venta = ctx.graph.write_entity_node(
        entity_type="person", name="Venta", relational_stage=RelationalStage.OBSERVING)
    pleasure_before = ctx.pad.get_current_pad().pleasure
    events_before = _count_events(ctx.graph)

    resp = d.route_inbound_turn(
        user_text="I finally shipped the release and I'm proud of it",
        session_id="s1", entity_refs=[venta], entity_node_id=venta, now=T0,
    )

    # Audio(fake): a pre-cached thinking sound played, then TTS spoke the text.
    assert ctx.audio.thinking_sounds == [ThinkingSound.CONTEMPLATION.value]
    assert ctx.audio.spoken == [resp.text]
    # Appraisal(real): the meaning step ran → exactly one new EventNode.
    assert _count_events(ctx.graph) == events_before + 1
    # SoulFilter(real) → LLM Interface(real) → fake cloud transport was invoked.
    assert len(ctx.cloud.prompts) == 1
    # The five-field boundary held through the REAL LLM Interface.
    assert "You are Aria" in ctx.cloud.prompts[0].instruction_text
    # gate(real) passed → a validated five-field response, no retry.
    assert resp.instruction_kind == "five_field"
    assert resp.text == _BENIGN_REPLY and resp.retried is False
    # PAD moved — via APPRAISAL (a positive turn → pleasure up), not the Daemon.
    assert ctx.pad.get_current_pad().pleasure > pleasure_before
    ctx.graph.close()


def test_turn_routing_never_computes_feeling_itself(tmp_path):
    """PAD moves during a turn ONLY through the appraisal chain's delta (via
    PAD_Engine). Proven with a tripwire engine: the ONLY apply_appraisal_delta
    calls during a turn originate inside appraisal, and the count matches a bare
    appraise() call — the Daemon adds none of its own."""
    pad = TripwirePAD()
    ctx = make_daemon(tmp_path, pad=pad)
    d = ctx.daemon
    d.startup()
    calls_before = pad.delta_calls
    d.route_inbound_turn(user_text="thanks, that really helped", session_id="s1",
                         entity_refs=(), entity_node_id=None, now=T0)
    # A positive turn applied exactly one appraisal delta (the Stage-4 byproduct)
    # — and it came through PAD_Engine, the only write path; the Daemon added 0.
    assert pad.delta_calls == calls_before + 1
    ctx.graph.close()


def test_critical_turn_triggers_forced_partial_dmn_pass_separate_clock(tmp_path):
    """A critical-poignancy turn forces an EARLY DMN partial pass (v4 reflection
    trigger) — a DMN-clock event, NOT a soul tick, and it does not decay PAD."""
    spy = SpyDMN()
    ctx = make_daemon(tmp_path, dmn=spy)
    d = ctx.daemon
    d.startup()
    venta = ctx.graph.write_entity_node(entity_type="person", name="V",
                                        relational_stage=RelationalStage.INVESTED)
    # An emergency/critical turn → poignancy critical → forced partial pass.
    d.route_inbound_turn(user_text="I want to die, I can't go on", session_id="s1",
                         entity_refs=[venta], entity_node_id=venta, now=T0)
    assert spy.forced_calls == 1     # forced-partial pass ran (DMN clock)
    assert spy.idle_calls == 0       # NOT an idle pass
    assert d.soul_tick_count == 0    # and it was NOT a soul tick (separate clock)
    ctx.graph.close()


# ===========================================================================
# 8) Thinking-sound selection (Layer 5): categorical, in-spec triggers.
# ===========================================================================

def test_thinking_sound_selection_is_categorical():
    base = PAD_BASELINE  # (0.55, 0.45, 0.58)
    # content triggers (v4 exact words)
    assert select_thinking_sound("this is a problem", base) is ThinkingSound.CONCERN
    assert select_thinking_sound("that was unexpected", base) is ThinkingSound.SURPRISE
    # PAD-mood triggers (v4 exact thresholds)
    playful = PADSnapshot(pleasure=0.6, arousal=0.5, dominance=0.7)  # D>0.6 & P>0.5
    assert select_thinking_sound("okay", playful) is ThinkingSound.PLAYFULNESS
    warm = PADSnapshot(pleasure=0.8, arousal=0.5, dominance=0.5)     # P>0.7 (not playful)
    assert select_thinking_sound("okay", warm) is ThinkingSound.WARMTH
    # default: neutral question/statement at baseline PAD
    assert select_thinking_sound("what time is it", base) is ThinkingSound.CONTEMPLATION
    # contentless input → no sound
    assert select_thinking_sound("", base) is None


def test_initiative_appraisal_is_inert_for_pad():
    """The initiative appraisal the Daemon builds carries an INERT PAD delta
    (all zero, NEUTRAL) — a data placeholder Soul_Filter never applies."""
    appr = build_initiative_appraisal("reach out once, gently")
    assert appr.pad_delta.d_pleasure == 0.0
    assert appr.pad_delta.d_arousal == 0.0
    assert appr.pad_delta.d_dominance == 0.0
    assert appr.emergency is False
    assert appr.most_salient_note == "reach out once, gently"


# ===========================================================================
# 9) ADDITIVE DMN-contract-gap closures (each with its own test).
# ===========================================================================

def test_appraisal_submit_aha_insight_applies_positive_pad_byproduct(tmp_path):
    """DMN emits an aha EVENT (duck-typed); the Appraisal Chain turns it into a
    small POSITIVE PAD shift as the appraisal's BYPRODUCT, via PAD_Engine — DMN
    never builds or writes PAD (constraint 1 / v4 'The Aha Moment')."""
    emb = FakeEmbedding()
    g = MemoryGraph(":memory:", embedding_model=emb)
    pad = PADEngine(); pad.initialize(None)   # baseline
    appraisal = AppraisalChain(pad_engine=pad, graph=g, embedding_model=emb)
    before = pad.get_current_pad()
    insight = SimpleNamespace(node_a_ref="a", node_b_ref="b", edge_id="e",
                              description="two previously-unlinked nodes connected")
    appraisal.submit_aha_insight(insight)   # the DMN AppraisalPort entry
    after = pad.get_current_pad()
    assert after.pleasure > before.pleasure           # small positive byproduct
    assert after.dominance > before.dominance         # a step of competence
    assert read_pad_last_valence(pad) is Valence.POSITIVE
    g.close()


def test_graph_predictability_evidence_is_recurrence(tmp_path):
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    e = g.write_entity_node(entity_type="person", name="V")

    def ev(desc, session="s1", q2="positive"):
        return g.write_event_node(description=desc, session_id=session,
                                  appraisal_q1="medium", appraisal_q2=q2,
                                  appraisal_q3="user",
                                  poignancy_category=PoignancyCategory.MEDIUM,
                                  entity_refs=[e], now=T0)
    ev("first")
    assert g.predictability_evidence(e) is False       # one occurrence — not recurred
    ev("second")
    assert g.predictability_evidence(e) is True         # same profile recurred (>1)

    # A different profile alone does NOT count as recurrence of a specific one.
    g2e = g.write_entity_node(entity_type="person", name="W")
    g.write_event_node(description="x", session_id="s1", appraisal_q1="medium",
                       appraisal_q2="positive", appraisal_q3="user",
                       poignancy_category=PoignancyCategory.MEDIUM,
                       entity_refs=[g2e], now=T0)
    g.write_event_node(description="y", session_id="s1", appraisal_q1="medium",
                       appraisal_q2="negative", appraisal_q3="circumstance",
                       poignancy_category=PoignancyCategory.MEDIUM,
                       entity_refs=[g2e], now=T0)
    assert g.predictability_evidence(g2e) is False      # two DIFFERENT profiles
    g.close()


def test_graph_dependability_evidence_needs_distinct_situations(tmp_path):
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    e = g.write_entity_node(entity_type="person", name="V")

    def ev(session):
        return g.write_event_node(description="p", session_id=session,
                                  appraisal_q1="medium", appraisal_q2="positive",
                                  appraisal_q3="user",
                                  poignancy_category=PoignancyCategory.MEDIUM,
                                  entity_refs=[e], now=T0)
    ev("s1"); ev("s1")
    assert g.predictability_evidence(e) is True         # recurred...
    assert g.dependability_evidence(e) is False          # ...but only one situation
    ev("s2")
    assert g.dependability_evidence(e) is True           # generalizes across situations
    g.close()


def test_graph_highest_salience_unconnected_candidates(tmp_path):
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    e = g.write_entity_node(entity_type="person", name="V")
    a = g.write_event_node(description="alpha", session_id="s1", appraisal_q1="high",
                           appraisal_q2="positive", appraisal_q3="user",
                           poignancy_category=PoignancyCategory.HIGH,
                           entity_refs=[e], now=T0)
    b = g.write_event_node(description="beta", session_id="s2", appraisal_q1="high",
                           appraisal_q2="positive", appraisal_q3="user",
                           poignancy_category=PoignancyCategory.HIGH,
                           entity_refs=[e], now=T0)
    cands = g.highest_salience_unconnected_candidates()
    pair = [c for c in cands if {c["node_a_ref"], c["node_b_ref"]} == {a, b}]
    assert pair, "the two high-salience unconnected events should be a candidate"
    rec = pair[0]
    assert rec["already_connected"] is False
    assert rec["shares_context"] is True         # share entity e
    assert rec["both_high_salience"] is True
    assert rec["reveals_new_pattern"] is True     # shared entity ACROSS sessions

    # Connect them → they are no longer an unconnected candidate.
    g.write_edge(from_node=a, to_node=b, edge_type=EdgeType.CONNECTS, now=T0)
    cands2 = g.highest_salience_unconnected_candidates()
    assert not [c for c in cands2 if {c["node_a_ref"], c["node_b_ref"]} == {a, b}]
    g.close()


def test_low_salience_nodes_are_not_candidates(tmp_path):
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    e = g.write_entity_node(entity_type="person", name="V")
    # LOW poignancy → salience 0.15 < 0.55 cutoff → never a candidate.
    for d in ("m1", "m2"):
        g.write_event_node(description=d, session_id="s1", appraisal_q1="low",
                           appraisal_q2="neutral", appraisal_q3="user",
                           poignancy_category=PoignancyCategory.LOW,
                           entity_refs=[e], now=T0)
    assert g.highest_salience_unconnected_candidates() == []
    g.close()


# ===========================================================================
# Gap 1 — Post-emergency re-entry instruction: flag tracking (v4 locked spec)
# ===========================================================================

def test_emergency_turn_sets_last_turn_was_emergency_flag(tmp_path):
    """An emergency turn must set `_last_turn_was_emergency = True` so the
    NEXT normal turn knows to inject the post-emergency instruction (v4)."""
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    d.startup()
    venta = ctx.graph.write_entity_node(
        entity_type="person", name="V",
        relational_stage=RelationalStage.OBSERVING,
    )
    d.route_inbound_turn(
        user_text="I want to die, I can't go on",
        session_id="s1", entity_refs=[venta], entity_node_id=venta, now=T0,
    )
    assert d._last_turn_was_emergency is True
    ctx.graph.close()


def test_post_emergency_fires_on_first_normal_turn_then_flag_resets(tmp_path):
    """After an emergency turn, the FIRST normal turn must receive
    post_emergency=True (Field 4 becomes POST_EMERGENCY_THIS_MOMENT) and the
    flag must reset to False — so it fires exactly ONCE (v4)."""
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    d.startup()
    venta = ctx.graph.write_entity_node(
        entity_type="person", name="V",
        relational_stage=RelationalStage.OBSERVING,
    )
    # Turn 1 — emergency
    d.route_inbound_turn(
        user_text="I want to die, I can't go on",
        session_id="s1", entity_refs=[venta], entity_node_id=venta, now=T0,
    )
    assert d._last_turn_was_emergency is True

    # Turn 2 — normal (post-emergency)
    d.route_inbound_turn(
        user_text="I think I'm okay now",
        session_id="s1", entity_refs=[venta], entity_node_id=venta, now=T0,
    )
    # Flag resets after the normal turn consumed it.
    assert d._last_turn_was_emergency is False
    # The second prompt to the LLM carried the post-emergency instruction in
    # Field 4 — proven by the locked text appearing in instruction_text.
    assert "Something significant just happened" in ctx.cloud.prompts[1].instruction_text
    ctx.graph.close()


def test_consecutive_emergencies_do_not_trigger_post_emergency(tmp_path):
    """Two consecutive emergency turns: the flag is True after turn 1, still
    True after turn 2 (not consumed), and the post-emergency text never appears
    in either prompt — `post_emergency_this_turn = True and not True = False`."""
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    d.startup()
    venta = ctx.graph.write_entity_node(
        entity_type="person", name="V",
        relational_stage=RelationalStage.OBSERVING,
    )
    # Turn 1 — emergency
    d.route_inbound_turn(
        user_text="I want to die, I can't go on",
        session_id="s1", entity_refs=[venta], entity_node_id=venta, now=T0,
    )
    assert d._last_turn_was_emergency is True

    # Turn 2 — also emergency
    d.route_inbound_turn(
        user_text="I still want to die",
        session_id="s1", entity_refs=[venta], entity_node_id=venta, now=T0,
    )
    # Flag stays True — second turn was also emergency, not a normal turn.
    assert d._last_turn_was_emergency is True
    # Post-emergency text never appeared in either prompt.
    for prompt in ctx.cloud.prompts:
        assert "Something significant just happened" not in prompt.instruction_text
    ctx.graph.close()


def test_dmn_advances_stage_via_the_real_graph_predicate(tmp_path):
    """The closure works with the REAL modules: DMN calls the REAL
    predictability_evidence (no wrapper) and advances Observing → Engaging."""
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    state = StateManager(state_dir=tmp_path)
    e = g.write_entity_node(entity_type="person", name="V",
                            relational_stage=RelationalStage.OBSERVING)
    for _ in range(2):   # same profile twice → real predictability_evidence True
        g.write_event_node(description="p", session_id="s1", appraisal_q1="medium",
                           appraisal_q2="positive", appraisal_q3="user",
                           poignancy_category=PoignancyCategory.MEDIUM,
                           entity_refs=[e], now=T0)
    assert g.predictability_evidence(e) is True
    dmn = DMN(
        graph=g,
        appraisal=SimpleNamespace(submit_aha_insight=lambda i: None),
        needs=SimpleNamespace(get_energy=lambda: 50.0),
        state=state, self_entity_id=None, clock=lambda: T0,
    )
    dmn.run_idle_pass(DMNPassInput(entity_refs=[e], now=T0))
    assert g.get_relational_stage(e) is RelationalStage.ENGAGING
    g.close()

# ===========================================================================
# Gap 3 — self_entity_id created at startup (self-referential EntityNode)
# ===========================================================================

def test_startup_creates_self_entity_node_on_first_run(tmp_path):
    """On first startup with no persisted self_entity_id, the Daemon must
    create a self-referential EntityNode (entity_type='concept', name='aria')
    in the graph and persist its id to state."""
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    assert ctx.state.load_self_entity_id() is None  # nothing persisted yet
    d.startup()
    # After startup: id is set, persisted, and the node exists in the graph.
    assert d._self_entity_id is not None
    assert ctx.state.load_self_entity_id() == d._self_entity_id
    node = ctx.graph.get_entity_node(d._self_entity_id)
    assert node is not None
    assert node.entity_type == "concept"
    assert node.name == "aria"


def test_startup_restores_self_entity_id_on_restart(tmp_path):
    """On restart, the Daemon must restore the persisted self_entity_id rather
    than creating a new node — preserving narrative continuity across sessions."""
    state = StateManager(state_dir=tmp_path)
    emb = FakeEmbedding()
    graph = MemoryGraph(":memory:", embedding_model=emb)

    # First startup — creates the node.
    ctx1 = make_daemon(tmp_path, state=state, graph=graph)
    ctx1.daemon.startup()
    first_id = ctx1.daemon._self_entity_id
    assert first_id is not None

    # Simulate restart: new Daemon, same graph and state.
    ctx2 = make_daemon(tmp_path, state=state, graph=graph)
    ctx2.daemon.startup()
    second_id = ctx2.daemon._self_entity_id

    # Same id — no new node created.
    assert second_id == first_id
    # Only one "aria" entity node in the graph.
    rows = graph._conn.execute(
        "SELECT COUNT(*) FROM entity_nodes WHERE name = 'aria'"
    ).fetchone()[0]
    assert rows == 1
    graph.close()


def test_self_entity_id_propagated_to_needs_and_dmn(tmp_path):
    """After startup(), NeedsSystem and DMN must both have _self_entity_id
    set to the same id the Daemon resolved — so Continuity evidence and
    self-narrative updates can fire correctly."""
    ctx = make_daemon(tmp_path)
    d = ctx.daemon
    d.startup()
    assert d._self_entity_id is not None
    # Both modules expose a read-only property; mutation is only via the
    # public setter called by the Daemon during startup().
    assert ctx.needs.self_entity_id == d._self_entity_id
    assert ctx.dmn.self_entity_id == d._self_entity_id


# ===========================================================================
# 10) Track A — BackendRouter wired into the conversation loop.
#
# These prove: no router injected -> unchanged behaviour (backward compat);
# Gemma loads at startup and stays resident; a tier-2 query defers into a
# proposal (no EventNode, no LLM call) rather than answering immediately;
# the three proposal-response paths (affirmative / negative / unrecognized)
# all set the expected override and replay the ORIGINAL deferred query
# (not the yes/no reply) through the full pipeline exactly once; the
# timeout path is reachable from soul_tick with NO direct PAD write; a
# backend meta-command bypasses appraisal/Soul Filter/the LLM entirely; and
# F4 during a pending proposal does not answer it.
# ===========================================================================

def test_daemon_without_router_behaves_exactly_as_before(tmp_path):
    """No BackendRouter injected -> a normal turn routes end-to-end exactly as
    it did before Track A (existing internal cloud-first LLM Interface path),
    and the turn-routing state stays NORMAL throughout. Backward compat
    (Part 4i: "Every existing AriaDaemon construction... must keep working")."""
    ctx = make_daemon(tmp_path)  # backend_router defaults to None
    d = ctx.daemon
    d.startup()
    assert d.state is DaemonState.NORMAL
    assert d.proposal_pending is False
    assert d.pending_query is None
    events_before = _count_events(ctx.graph)

    resp = d.route_inbound_turn(
        user_text="I finally shipped the release and I'm proud of it", now=T0,
    )

    assert d.state is DaemonState.NORMAL
    assert d.proposal_pending is False
    assert resp.text == _BENIGN_REPLY
    assert len(ctx.cloud.prompts) == 1    # unchanged internal cloud-first path
    assert ctx.local.prompts == []
    assert _count_events(ctx.graph) == events_before + 1


def test_gemma_loaded_at_startup_and_stays_resident(tmp_path):
    """startup() calls ensure_local_loaded(); the local fake is loaded; a
    subsequent normal turn does NOT unload it (Part 4c / 4i)."""
    local = FakeLocal()  # starts unloaded
    ctx = make_daemon(tmp_path, local=local, backend_router=True)
    d = ctx.daemon
    assert local.is_loaded is False

    d.startup()
    assert local.is_loaded is True
    assert local.load_calls == 1

    d.route_inbound_turn(user_text="how are you", now=T0)

    assert local.is_loaded is True     # still resident
    assert local.unload_calls == 0     # never unloaded
    assert len(local.prompts) == 1     # Gemma (default voice) served this turn
    assert ctx.cloud.prompts == []     # groq was not needed


def test_tier2_query_triggers_proposal_and_defers_appraisal(tmp_path):
    """A tier-2-keyword query -> state becomes PROPOSING_CLOUD, the proposal
    text was spoken, NO EventNode was written, and the LLM was never called
    (Part 4e — appraisal is deferred to the replay, not lost)."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()
    events_before = _count_events(ctx.graph)

    resp = d.route_inbound_turn(user_text="debug this traceback", now=T0)

    assert d.state is DaemonState.PROPOSING_CLOUD
    assert d.proposal_pending is True
    assert d.pending_query == "debug this traceback"
    assert resp.text == daemon_mod._PROPOSAL_PROMPT
    assert ctx.audio.spoken == [daemon_mod._PROPOSAL_PROMPT]
    assert _count_events(ctx.graph) == events_before   # no EventNode written
    assert ctx.cloud.prompts == [] and ctx.local.prompts == [] and ctx.azure.prompts == []


def test_affirmative_response_sets_tier2_override_and_replays(tmp_path):
    """From PROPOSING_CLOUD, "yes please" -> override "tier_2", state back to
    NORMAL, exactly ONE EventNode written (the replayed pending query, not
    the "yes"), and the LLM called once (via the azure transport, per the
    new override)."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()
    events_before = _count_events(ctx.graph)

    d.route_inbound_turn(user_text="debug this traceback", now=T0)
    assert d.proposal_pending is True

    resp = d.route_inbound_turn(user_text="yes please", now=T0)

    assert ctx.backend_router.get_override() == "tier_2"
    assert d.state is DaemonState.NORMAL
    assert d.proposal_pending is False
    assert _count_events(ctx.graph) == events_before + 1   # only the replay
    assert len(ctx.azure.prompts) == 1
    assert ctx.azure.prompts[0].user_message == "debug this traceback"
    assert resp.text == "azure reply"


def test_negative_response_sets_tier0_override_and_replays(tmp_path):
    """Same shape with "no thanks" -> override "tier_0", replay happened
    (via the gemma/local transport, per the new override)."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()
    events_before = _count_events(ctx.graph)

    d.route_inbound_turn(user_text="debug this traceback", now=T0)
    assert d.proposal_pending is True

    resp = d.route_inbound_turn(user_text="no thanks", now=T0)

    assert ctx.backend_router.get_override() == "tier_0"
    assert d.state is DaemonState.NORMAL
    assert _count_events(ctx.graph) == events_before + 1
    assert len(ctx.local.prompts) == 1
    assert ctx.local.prompts[0].user_message == "debug this traceback"


def test_unrecognized_response_defaults_to_negative_and_still_replays(tmp_path):
    """"hmm maybe" matches neither lexicon -> override defaults to "tier_0"
    (FLAG 2 in HANDOFF_NOTES.md) and the pending query is still answered —
    nothing is dropped."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()
    events_before = _count_events(ctx.graph)

    d.route_inbound_turn(user_text="debug this traceback", now=T0)
    assert d.proposal_pending is True

    resp = d.route_inbound_turn(user_text="hmm maybe", now=T0)

    assert ctx.backend_router.get_override() == "tier_0"      # FLAG 2 default
    assert d.state is DaemonState.NORMAL
    assert _count_events(ctx.graph) == events_before + 1      # still answered
    assert len(ctx.local.prompts) == 1


def test_proposal_times_out_on_soul_tick_and_auto_answers_with_gemma(tmp_path):
    """Enter PROPOSING_CLOUD, advance the clock past the timeout, call
    soul_tick -> the timeout reply was spoken, state is NORMAL, the pending
    query was replayed, and the transport handed to Soul Filter was the
    local (gemma) fake (Part 4g)."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()

    d.route_inbound_turn(user_text="debug this traceback", now=T0)
    assert d.proposal_pending is True

    d.soul_tick(now=T0 + timedelta(seconds=daemon_mod.PROPOSAL_TIMEOUT_SECONDS + 1))

    assert daemon_mod._PROPOSAL_TIMEOUT_REPLY in ctx.audio.spoken
    assert d.state is DaemonState.NORMAL
    assert d.proposal_pending is False
    assert ctx.backend_router.get_override() == "tier_0"
    assert any(p.user_message == "debug this traceback" for p in ctx.local.prompts)


def test_timeout_writes_no_pad_directly(tmp_path):
    """Tripwire, mirroring the existing F4 tripwire: the Daemon adds NO
    apply_appraisal_delta call of its own on timeout — the only delta applied
    across the whole soul_tick call is the one the appraisal chain produces
    as the byproduct of appraising the REPLAYED query (matching the count a
    bare normal turn's appraisal already proves, in
    test_turn_routing_never_computes_feeling_itself).

    Uses an emotionally-charged tier-2 query (NEGATIVE valence, HIGH
    relevance) rather than a neutral one — a purely neutral appraisal emits
    a fully-zero delta that is never applied at all (see
    AppraisalChain._apply_delta), which would make a "+1" assertion here
    pass for the wrong reason (0 == 0, not "the replay's own byproduct")."""
    pad = TripwirePAD()
    local = FakeLocal()
    ctx = make_daemon(tmp_path, pad=pad, local=local, backend_router=True)
    d = ctx.daemon
    d.startup()

    query = "there is an error here and it is terrible"
    d.route_inbound_turn(user_text=query, now=T0)
    assert d.proposal_pending is True
    delta_calls_before = pad.delta_calls

    d.soul_tick(now=T0 + timedelta(seconds=daemon_mod.PROPOSAL_TIMEOUT_SECONDS + 1))

    # Exactly one delta call for the entire tick: the replayed appraisal's own
    # Stage-4 byproduct. The Daemon (timeout handling + initiative, if it also
    # fired this tick) contributes none — initiative's appraisal carries an
    # INERT delta Soul_Filter never applies (see build_initiative_appraisal).
    assert pad.delta_calls == delta_calls_before + 1


def test_backend_meta_command_sets_override_and_bypasses_pipeline(tmp_path):
    """"use cloud" -> override "tier_2", no EventNode written, LLM never
    called, state still NORMAL (Part 4d STEP 3)."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()
    events_before = _count_events(ctx.graph)

    resp = d.route_inbound_turn(user_text="use cloud", now=T0)

    assert ctx.backend_router.get_override() == "tier_2"
    assert _count_events(ctx.graph) == events_before
    assert ctx.cloud.prompts == [] and ctx.local.prompts == [] and ctx.azure.prompts == []
    assert d.state is DaemonState.NORMAL
    assert ctx.audio.spoken == [resp.text]


def test_f4_during_proposal_does_not_answer_it(tmp_path):
    """Enter PROPOSING_CLOUD, call on_f4_interrupt() -> audio stopped once,
    state is STILL PROPOSING_CLOUD, pending query unchanged, no override set.
    A stop button is not an answer to a question (Part 4i)."""
    ctx = make_daemon(tmp_path, backend_router=True)
    d = ctx.daemon
    d.startup()

    d.route_inbound_turn(user_text="debug this traceback", now=T0)
    assert d.proposal_pending is True
    stops_before = ctx.audio.stops

    d.on_f4_interrupt()

    assert ctx.audio.stops == stops_before + 1
    assert d.state is DaemonState.PROPOSING_CLOUD
    assert d.pending_query == "debug this traceback"
    assert ctx.backend_router.get_override() is None


# ===========================================================================
# Energy < 30 -> cognitive-load modifier (Addendum §3 operational threshold
# gate; v4 mechanism table "Cognitive load effect | Appraisal modifier |
# Stage 2 appraisal + DMN depth check").
# ===========================================================================

def _record_appraisal_calls(appraisal):
    """Wrap the REAL AppraisalChain's two entry points on the instance the
    Daemon holds, recording call ORDER. Instance attributes shadow the class
    methods, so the Daemon sees the wrappers while the real behaviour still
    runs underneath — nothing is stubbed out."""
    calls = []
    real_submit = appraisal.submit_cognitive_load
    real_appraise = appraisal.appraise

    def recording_submit(load_state):
        calls.append(f"submit_cognitive_load:{load_state}")
        return real_submit(load_state)

    def recording_appraise(**kwargs):
        calls.append("appraise")
        return real_appraise(**kwargs)

    appraisal.submit_cognitive_load = recording_submit
    appraisal.appraise = recording_appraise
    return calls


def _daemon_with_energy(tmp_path, energy):
    """A Daemon whose live Energy is `energy`, set through the REAL restore
    path: StateManager persists it, startup() hands it to NeedsSystem."""
    state = StateManager(state_dir=tmp_path)
    state.save_energy(energy)
    ctx = make_daemon(tmp_path, state=state)
    ctx.daemon.startup()
    assert ctx.needs.get_energy() == pytest.approx(energy)
    return ctx


def test_low_energy_submits_heavy_cognitive_load_before_appraise(tmp_path):
    # Energy below the in-spec 30 gate routes through the EXISTING
    # submit_cognitive_load entry point, BEFORE the appraisal runs.
    ctx = _daemon_with_energy(tmp_path, 25.0)
    assert ctx.needs.get_energy() < ENERGY_LOW
    calls = _record_appraisal_calls(ctx.appraisal)

    ctx.daemon.route_inbound_turn(user_text="how are you", now=T0)

    assert calls == ["submit_cognitive_load:heavy", "appraise"]


def test_normal_energy_submits_no_cognitive_load(tmp_path):
    ctx = _daemon_with_energy(tmp_path, 80.0)
    calls = _record_appraisal_calls(ctx.appraisal)

    ctx.daemon.route_inbound_turn(user_text="how are you", now=T0)

    assert calls == ["appraise"]


def test_energy_gate_is_categorical_at_the_in_spec_boundary(tmp_path):
    # "Below 30" — 30.0 itself is NOT below. The gate either holds or it does
    # not; there is no partial load state.
    at_gate = _daemon_with_energy(tmp_path / "at", ENERGY_LOW)
    calls_at = _record_appraisal_calls(at_gate.appraisal)
    at_gate.daemon.route_inbound_turn(user_text="how are you", now=T0)
    assert calls_at == ["appraise"]

    below = _daemon_with_energy(tmp_path / "below", ENERGY_LOW - 0.001)
    calls_below = _record_appraisal_calls(below.appraisal)
    below.daemon.route_inbound_turn(user_text="how are you", now=T0)
    assert calls_below == ["submit_cognitive_load:heavy", "appraise"]


def test_low_energy_skips_no_appraisal_stage(tmp_path):
    """The load modifier is additive — it must not shorten the chain. At low
    Energy a turn still runs Stage 0-6: an EventNode is written, PAD moves as
    the appraisal's byproduct, and the response still clears the Output Gate."""
    ctx = _daemon_with_energy(tmp_path, 25.0)
    events_before = _count_events(ctx.graph)
    pad_before = ctx.pad.get_current_pad()

    response = ctx.daemon.route_inbound_turn(
        user_text="I shipped the thing and it works", now=T0)

    assert _count_events(ctx.graph) > events_before      # Stage 6 ran
    assert ctx.pad.get_current_pad() != pad_before        # Stage 4 ran
    assert response.text                                  # gate passed


def test_low_energy_still_detects_an_emergency(tmp_path):
    """The load modifier must NOT touch the emergency gate or the Stage-1
    vulnerability pre-pass. A tired ARIA still detects a crisis."""
    ctx = _daemon_with_energy(tmp_path, 25.0)

    ctx.daemon.route_inbound_turn(
        user_text="I can't go on, I want to die", now=T0)

    assert ctx.daemon._last_turn_was_emergency is True


def test_energy_number_never_reaches_the_appraisal_chain(tmp_path):
    """Only the CATEGORICAL load state crosses. The Appraisal Chain holds no
    Energy handle and appraise() is passed no Energy value."""
    ctx = _daemon_with_energy(tmp_path, 25.0)
    seen = {}
    real_appraise = ctx.appraisal.appraise

    def capturing_appraise(**kwargs):
        seen.update(kwargs)
        return real_appraise(**kwargs)

    ctx.appraisal.appraise = capturing_appraise
    ctx.daemon.route_inbound_turn(user_text="how are you", now=T0)

    assert "energy" not in seen
    assert not any("energy" in str(k).lower() for k in seen)
    # need_states crosses as categorical strings only, never a number.
    assert all(isinstance(v, str) for v in seen["need_states"].values())
    # And the chain itself holds no needs/state handle to read Energy from.
    held = set(vars(ctx.appraisal))
    assert not any("energy" in n.lower() or "needs" in n.lower() for n in held), held
