"""Tests — Module 2: Needs System (daemon/needs_system.py).

Locked spec: .kiro/specs/needs-system/{requirements,design,tasks}.md.

Plain pytest, NO hypothesis (matches Modules 1/3/5 style). Proves the
philosophy contracts, not just behavior:

  * The four needs are STRICTLY CATEGORICAL — each is a NeedState enum, there
    is no numeric score/percentage/level on any need, and evaluating the same
    in-window graph at different times yields the SAME category (no gradation
    by "how much of the window elapsed" — the percentage test). (Req 7, 12)
  * A need flips satisfied -> un-satisfied PURELY because evidence ages out of
    its recency window as an injected clock advances — nothing is subtracted,
    the graph is untouched, and the evaluator holds no mutable need state.
    (Req 11)
  * Energy is SUBSTRATE: EMA decay under load, drift-to-baseline recovery on
    idle, bounded, banded at the in-spec 30/20 thresholds — and it NEVER
    writes PAD (structural absence + a live tripwire + real-PAD-unchanged).
    (Req 3, 4, 5, 6)
  * No need ever calls a PAD mutator. (Req 6, 13)
  * The evaluator DELEGATES to the real graph_manager evidence queries (a
    call-count spy proves it, and each of the four needs flips on real
    evidence built through the real graph write methods). (Req 8)
  * The output IS the exact soul_filter.NeedStates, consumed unchanged by the
    real SoulFilter. (Req 14)

No hypothesis: "property" checks use representative hand-picked inputs.
Placeholder tuning constants (k_load / k_rest) are NOT pinned to a value by
these tests — only their locked qualitative properties are asserted
(monotonicity, two-constants-no-valence, bounds), per the module's
build-time-placeholder discipline.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

import daemon.needs_system as ns_mod
from daemon.needs_system import (
    NeedsSystem,
    EnergyTracker,
    NeedsEvaluator,
    EnergyBand,
    ENERGY_BASELINE,
    ENERGY_MIN,
    K_LOAD,
    K_REST,
    _ema_step,
)
from daemon.soul_filter import (
    NeedState,
    NeedStates,
    ENERGY_LOW,
    ENERGY_CRITICAL,
    SoulFilter,
    FiveFieldInstruction,
)
from daemon.graph_manager import (
    MemoryGraph,
    PoignancyCategory,
    UncertaintyType,
    UncertaintyStatus,
    WINDOW_CONNECTION,
    WINDOW_GROWTH,
    WINDOW_PURPOSE,
    WINDOW_CONTINUITY,
)
from daemon.pad_engine import PADEngine, PADSnapshot

# Appraisal + soul-filter builders (for the contract-consumption test).
from daemon.appraisal_chain import (
    AppraisalResult,
    SocialSignals,
    GoalRelevance,
    Attribution,
)
from daemon.pad_engine import PADDelta, Valence


T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# Test doubles / builders
# ===========================================================================
class FakeEmbedding:
    """Deterministic encoder-only embedding (the shared EmbeddingModel). Not a
    generator — just enough for graph writes that store an embedding."""

    def __init__(self, table=None):
        self.table = dict(table or {})

    def embed(self, text):
        if text in self.table:
            return list(self.table[text])
        v = [0.0] * 8
        for ch in text:
            v[ord(ch) % 8] += 1.0
        return v


class FakeLLM:
    """Module 9 LLMClient contract — returns a benign candidate. Only needed to
    construct a real SoulFilter for the contract-consumption test."""

    def generate(self, instruction, user_message, session_context="", transport=None):
        return "I hear you. I'm here."


class EvidenceSpyGraph:
    """Wraps a REAL MemoryGraph and counts calls to the four evidence queries,
    forwarding each to the real implementation. Proves the evaluator DELEGATES
    to graph_manager's queries rather than reimplementing them (Req 8.2)."""

    def __init__(self, real):
        self._real = real
        self.calls = {"connection": 0, "growth": 0, "purpose": 0, "continuity": 0}

    def connection_evidence(self, now=None):
        self.calls["connection"] += 1
        return self._real.connection_evidence(now=now)

    def growth_evidence(self, now=None):
        self.calls["growth"] += 1
        return self._real.growth_evidence(now=now)

    def purpose_evidence(self, now=None):
        self.calls["purpose"] += 1
        return self._real.purpose_evidence(now=now)

    def continuity_evidence(self, self_entity_id, now=None):
        self.calls["continuity"] += 1
        return self._real.continuity_evidence(self_entity_id, now=now)


def make_graph(table=None):
    return MemoryGraph(":memory:", embedding_model=FakeEmbedding(table))


def add_connection_evidence(mg, at=T0):
    """Relatedness: an EventNode scored Q1 medium-or-above (Addendum §3).
    Q2 neutral so it does NOT also count as Purpose evidence."""
    return mg.write_event_node(
        description="a real exchange", session_id="s",
        appraisal_q1="medium", appraisal_q2="neutral", appraisal_q3="user",
        poignancy_category=PoignancyCategory.MEDIUM, timestamp=at,
    )


def add_growth_evidence(mg, at=T0):
    """Competence: an UncertaintyNode actually RESOLVED (Addendum §3). The
    trigger event is Q1 low / Q2 neutral so it is neither Connection nor
    Purpose evidence."""
    ev = mg.write_event_node(
        description="a question", session_id="s",
        appraisal_q1="low", appraisal_q2="neutral", appraisal_q3="user",
        poignancy_category=PoignancyCategory.LOW, timestamp=at,
    )
    u = mg.create_uncertainty_node(
        uncertainty_type=UncertaintyType.INPUT_UNCERTAIN,
        trigger_event_ref=ev, created=at,
    )
    mg.update_uncertainty_status(u, UncertaintyStatus.RESOLVED_CONFIRMED, resolved=at)
    return u


def add_purpose_evidence(mg, at=T0):
    """Beneficence: a positive-valence EventNode (the graph's current stand-in
    query, TODO(OQ6-M2)). Q1 none so it is not also Connection evidence."""
    return mg.write_event_node(
        description="thanks, that helped", session_id="s",
        appraisal_q1="none", appraisal_q2="positive", appraisal_q3="user",
        poignancy_category=PoignancyCategory.LOW, timestamp=at,
    )


def add_continuity_evidence(mg, at=T0):
    """Narrative coherence: the self-referential EntityNode's narrative extended
    within window (Addendum §3; Resolution Log item 2). Returns the self id."""
    self_id = mg.write_entity_node(entity_type="person", name="Aria")
    mg.update_relationship_summary(self_id, "We have kept building together.", now=at)
    return self_id


def make_social(**kw):
    base = dict(
        distress_marker=False, vulnerability_disclosure=False,
        reality_contradiction=False, conflict_arc_open=False,
        conflict_arc_closed_this_turn=False,
    )
    base.update(kw)
    return SocialSignals(**base)


def make_appraisal(**kw):
    """A routine (non-emergency, no-signal) appraisal — the branch that yields
    two base constraints, leaving room for the Energy '<30' constraint to be
    appended, so the contract test can observe it."""
    base = dict(
        q1=GoalRelevance.MEDIUM, q2=Valence.NEUTRAL, q3=Attribution.USER,
        q4_notes=None, q4_has_needs_implications=False,
        is_partial_appraisal=False, poignancy=PoignancyCategory.MEDIUM,
        pad_delta=PADDelta(0.0, 0.0, 0.0, Valence.NEUTRAL),
        emergency=False, emergency_type=None, event_node_id=None,
        uncertainty_node_id=None, resolved_uncertainty_ids=(),
        social_signals=make_social(),
        most_salient_note="a routine exchange — stay present",
    )
    base.update(kw)
    return AppraisalResult(**base)


def make_soul_filter():
    pad = PADEngine()
    pad.initialize(None)
    graph = make_graph()
    return SoulFilter(pad_engine=pad, graph=graph, llm_client=FakeLLM())


def fixed_clock(t):
    return lambda: t


# ===========================================================================
# Group A — The four needs are STRICTLY CATEGORICAL, never a number (Req 7, 12)
# ===========================================================================
def test_needstates_shape_only_energy_is_numeric():
    """The contract has exactly the four categorical need fields + one numeric
    field (energy). No numeric per-need field exists (Req 7.2, 7.3)."""
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(NeedStates)}
    assert set(fields) == {"connection", "growth", "purpose", "continuity", "energy"}
    # Energy is the ONLY float; the four needs are NeedState (a category).
    assert fields["energy"].type in (float, "float")


def test_produced_needs_are_categorical_enums_not_numbers():
    mg = make_graph()
    ns = NeedsSystem(mg, clock=fixed_clock(T0))
    ns.initialize()
    states = ns.get_need_states()
    for need in (states.connection, states.growth, states.purpose, states.continuity):
        assert isinstance(need, NeedState)
        # A category is NOT a number (bool is an int subclass — exclude too).
        assert not isinstance(need, (int, float, bool))
    # Energy is the one sanctioned number.
    assert isinstance(states.energy, float)


def test_needstate_values_are_labels_not_numbers():
    for member in NeedState:
        assert isinstance(member.value, str)
    assert {m.value for m in NeedState} == {"satisfied", "due", "neglected"}


def test_evaluator_only_ever_returns_satisfied_or_due_never_a_number():
    """Every per-need evaluation returns a NeedState in {SATISFIED, DUE} — never
    a number, and never NEGLECTED (the flagged OQ-1 decision)."""
    mg = make_graph()
    add_connection_evidence(mg)
    add_growth_evidence(mg)
    add_purpose_evidence(mg)
    self_id = add_continuity_evidence(mg)
    ev = NeedsEvaluator(mg, self_entity_id=self_id)
    # Sample many times, in-window and long after (aged out).
    for now in (T0 + timedelta(hours=1), T0 + timedelta(days=365)):
        for state in ev.evaluate_all(now).values():
            assert isinstance(state, NeedState)
            assert state in (NeedState.SATISFIED, NeedState.DUE)
            assert state is not NeedState.NEGLECTED


def test_no_gradation_within_window_passes_percentage_test():
    """Two different times, both inside the 72h window, give the IDENTICAL
    category — there is no 'percent of the way there'. (Req 12.3, percentage
    test.)"""
    mg = make_graph()
    add_connection_evidence(mg, at=T0)
    ev = NeedsEvaluator(mg)
    early = ev.evaluate_connection(T0 + timedelta(hours=1))
    late_but_in_window = ev.evaluate_connection(T0 + timedelta(hours=70))
    assert early is NeedState.SATISFIED
    assert late_but_in_window is NeedState.SATISFIED
    assert early is late_but_in_window  # no in-between state


def test_needs_system_exposes_no_numeric_need_accessor():
    """No public surface returns a per-need number/score/level/pressure. The
    only numeric accessor is Energy (Req 7.2, 7.3)."""
    banned = ("score", "pressure", "percent", "level", "fraction", "intensity")
    for cls in (NeedsSystem, NeedsEvaluator):
        for name in dir(cls):
            low = name.lower()
            if low.startswith("__"):
                continue
            assert not any(b in low for b in banned), (
                f"{cls.__name__}.{name} smells like a numeric need measure"
            )


# ===========================================================================
# Group B — States revert on their own as evidence ages out (Req 11)
# ===========================================================================
def test_connection_flips_satisfied_to_due_purely_by_clock():
    """The core philosophy proof: identical graph, only `now` advances past the
    72h window -> satisfied becomes due. Nothing is subtracted."""
    mg = make_graph()
    add_connection_evidence(mg, at=T0)
    ns = NeedsSystem(mg)
    ns.initialize()

    inside = ns.get_need_states(now=T0 + timedelta(hours=71))
    outside = ns.get_need_states(now=T0 + timedelta(hours=73))

    assert inside.connection is NeedState.SATISFIED
    assert outside.connection is NeedState.DUE


def test_revert_is_time_only_graph_and_state_untouched():
    """After the flip, the evidence row is STILL in the graph (the query with a
    huge window still finds it) — proving nothing was deleted/subtracted; only
    the window relationship changed. And the evaluator holds no mutable need
    state."""
    mg = make_graph()
    add_connection_evidence(mg, at=T0)
    ev = NeedsEvaluator(mg)

    assert ev.evaluate_connection(T0 + timedelta(hours=1)) is NeedState.SATISFIED
    assert ev.evaluate_connection(T0 + timedelta(days=30)) is NeedState.DUE

    # Evidence still physically present (window widened proves it wasn't removed).
    assert mg.connection_evidence(
        now=T0 + timedelta(days=30), window=timedelta(days=365)
    ) is True

    # Evaluator is stateless: only injected deps, no per-need value stored.
    assert set(vars(ev)) == {"_graph", "_self_entity_id"}


def test_each_need_uses_its_own_window():
    """Connection (72h) and Growth (14d) age out on different schedules —
    demonstrating the per-need window mapping (Resolution Log item 7)."""
    mg = make_graph()
    add_connection_evidence(mg, at=T0)
    add_growth_evidence(mg, at=T0)
    ev = NeedsEvaluator(mg)

    # 8 days later: Connection (72h) has aged out; Growth (14d) has not.
    now = T0 + timedelta(days=8)
    assert ev.evaluate_connection(now) is NeedState.DUE
    assert ev.evaluate_growth(now) is NeedState.SATISFIED

    # 20 days later: both aged out.
    now = T0 + timedelta(days=20)
    assert ev.evaluate_connection(now) is NeedState.DUE
    assert ev.evaluate_growth(now) is NeedState.DUE


def test_continuity_window_and_missing_self_node():
    mg = make_graph()
    self_id = add_continuity_evidence(mg, at=T0)
    ev = NeedsEvaluator(mg, self_entity_id=self_id)
    assert ev.evaluate_continuity(T0 + timedelta(days=59)) is NeedState.SATISFIED
    assert ev.evaluate_continuity(T0 + timedelta(days=61)) is NeedState.DUE

    # No self entity id -> no narrative to find -> due (OQ-2), no crash.
    ev_no_self = NeedsEvaluator(mg, self_entity_id=None)
    assert ev_no_self.evaluate_continuity(T0) is NeedState.DUE


def test_windows_match_resolution_log_item_7():
    """Guard that the reused windows are exactly the locked values (F-2c /
    Resolution Log item 7), owned by graph_manager."""
    assert WINDOW_CONNECTION == timedelta(hours=72)
    assert WINDOW_GROWTH == timedelta(days=14)
    assert WINDOW_PURPOSE == timedelta(days=14)
    assert WINDOW_CONTINUITY == timedelta(days=60)


# ===========================================================================
# Group C — Energy is SUBSTRATE: decay / recovery / bounds / bands (Req 3,4,5)
# ===========================================================================
def test_energy_initializes_to_baseline():
    e = EnergyTracker()
    e.initialize()
    assert e.get_energy() == ENERGY_BASELINE == 100.0


def test_energy_initializes_from_valid_restore():
    e = EnergyTracker()
    e.initialize(42.5)
    assert e.get_energy() == 42.5


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"),
                                  float("-inf"), -1.0, 100.1, True, "50"])
def test_energy_invalid_restore_falls_back_to_baseline(bad):
    e = EnergyTracker()
    e.initialize(bad)
    assert e.get_energy() == ENERGY_BASELINE


def test_energy_decays_monotonically_under_load_toward_empty():
    e = EnergyTracker()
    e.initialize()
    prev = e.get_energy()
    for _ in range(50):
        e.on_soul_tick()
        cur = e.get_energy()
        assert cur < prev          # strictly decreasing under load
        assert cur >= ENERGY_MIN   # never below empty
        prev = cur
    # After sustained load it is well down the battery.
    assert e.get_energy() < 30.0


def test_energy_recovers_monotonically_on_idle_toward_full():
    e = EnergyTracker()
    e.initialize(10.0)
    prev = e.get_energy()
    for _ in range(50):
        e.on_idle_recovery()
        cur = e.get_energy()
        assert cur > prev              # strictly increasing while idle
        assert cur <= ENERGY_BASELINE  # never above full
        prev = cur
    assert e.get_energy() > 50.0


def test_energy_never_overshoots_either_bound():
    # From near-empty, load ticks never go below empty.
    e = EnergyTracker()
    e.initialize(0.001)
    for _ in range(100):
        e.on_soul_tick()
        assert e.get_energy() >= ENERGY_MIN
    # From near-full, idle ticks never exceed full.
    e2 = EnergyTracker()
    e2.initialize(99.999)
    for _ in range(100):
        e2.on_idle_recovery()
        assert e2.get_energy() <= ENERGY_BASELINE


@pytest.mark.parametrize("energy,expected", [
    (100.0, EnergyBand.NORMAL),
    (30.0, EnergyBand.NORMAL),     # >= 30
    (29.999, EnergyBand.LOW),      # below 30
    (20.0, EnergyBand.LOW),        # >= 20
    (19.999, EnergyBand.CRITICAL), # below 20
    (0.0, EnergyBand.CRITICAL),
])
def test_energy_band_uses_in_spec_thresholds(energy, expected):
    e = EnergyTracker()
    e.initialize(energy)
    assert e.energy_band() == expected
    # Bands trace to the in-spec soul_filter thresholds, single source of truth.
    assert ENERGY_LOW == 30.0 and ENERGY_CRITICAL == 20.0


def test_energy_two_constants_no_valence():
    """Resolution Log item 6: exactly TWO constants (k_load, k_rest), no
    valence -> the tick methods take no valence argument."""
    assert isinstance(K_LOAD, float) and 0.0 < K_LOAD < 1.0
    assert isinstance(K_REST, float) and 0.0 < K_REST < 1.0
    for m in (EnergyTracker.on_soul_tick, EnergyTracker.on_idle_recovery):
        params = [p for p in inspect.signature(m).parameters if p != "self"]
        assert params == []  # no valence / no coefficient argument


def test_ema_step_is_the_standard_pad_form():
    # new = k*target + (1-k)*current — the same EMA form PAD uses.
    assert _ema_step(100.0, 0.0, 0.5) == 50.0
    assert _ema_step(0.0, 100.0, 0.25) == 25.0
    assert _ema_step(50.0, 50.0, 0.9) == 50.0  # already at target -> no move


def test_pre_initialize_guard():
    for call in (
        lambda t: t.get_energy(),
        lambda t: t.on_soul_tick(),
        lambda t: t.on_idle_recovery(),
        lambda t: t.energy_band(),
    ):
        with pytest.raises(RuntimeError):
            call(EnergyTracker())
    # The facade guards get_need_states too (it reads Energy).
    ns = NeedsSystem(make_graph())
    with pytest.raises(RuntimeError):
        ns.get_need_states(now=T0)


# ===========================================================================
# Group D — Energy never writes PAD; needs never call a PAD mutator (Req 6,13)
# ===========================================================================
def test_needs_system_source_has_no_pad_dependency():
    """Structural guarantee: no PAD import, no PAD reference, no PAD mutator
    call anywhere in the module (Req 6.1)."""
    src = inspect.getsource(ns_mod)
    assert "apply_appraisal_delta" not in src
    assert "PADEngine" not in src   # no-underscore class name never appears
    assert "PADDelta" not in src
    # No import statement references pad.
    import_lines = [
        ln for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    assert not any("pad" in ln.lower() for ln in import_lines)
    # No PAD symbol leaked into the module namespace.
    assert not hasattr(ns_mod, "PADEngine")
    assert not hasattr(ns_mod, "PADDelta")


def test_no_class_takes_a_pad_parameter():
    for cls in (NeedsSystem, EnergyTracker, NeedsEvaluator):
        for _, member in inspect.getmembers(cls, predicate=inspect.isfunction):
            for pname in inspect.signature(member).parameters:
                assert "pad" not in pname.lower()


def test_full_cycle_leaves_a_real_pad_engine_untouched():
    """Needs_System has no handle to PAD, so exercising it cannot change PAD."""
    pad = PADEngine()
    pad.initialize(None)
    before = pad.get_current_pad()

    mg = make_graph()
    add_connection_evidence(mg)
    ns = NeedsSystem(mg, clock=fixed_clock(T0))
    ns.initialize()
    for _ in range(20):
        ns.on_soul_tick()
    for _ in range(20):
        ns.on_idle_recovery()
    ns.get_need_states()

    after = pad.get_current_pad()
    assert (before.pleasure, before.arousal, before.dominance) == (
        after.pleasure, after.arousal, after.dominance
    )


def test_pad_mutator_tripwire_never_fires(monkeypatch):
    """Arm the ONLY PAD mutator to explode; run the whole Needs_System cycle;
    it must never fire (needs never pull PAD; Energy never writes PAD)."""
    def boom(self, *a, **k):
        raise AssertionError("Needs_System must never call a PAD mutator")

    monkeypatch.setattr(PADEngine, "apply_appraisal_delta", boom)

    mg = make_graph()
    self_id = add_continuity_evidence(mg)
    ns = NeedsSystem(mg, self_entity_id=self_id, clock=fixed_clock(T0))
    ns.initialize()
    for _ in range(15):
        ns.on_soul_tick()
    for _ in range(15):
        ns.on_idle_recovery()
    # Full evaluation + output — none of this may touch PAD.
    states = ns.get_need_states()
    assert isinstance(states, NeedStates)  # completed without the tripwire firing


# ===========================================================================
# Group E — Real graph_manager evidence integration (Req 8)
# ===========================================================================
def test_evaluator_delegates_to_real_graph_queries():
    """A call-count spy proves the evaluator CALLS graph_manager's four evidence
    queries once each (delegation, not reimplementation — Req 8.2)."""
    real = make_graph()
    self_id = add_continuity_evidence(real)
    spy = EvidenceSpyGraph(real)
    ev = NeedsEvaluator(spy, self_entity_id=self_id)
    ev.evaluate_all(T0)
    assert spy.calls == {"connection": 1, "growth": 1, "purpose": 1, "continuity": 1}


def test_each_need_satisfied_only_with_its_own_real_evidence():
    """Build each need's evidence through the REAL graph write methods; only
    that need becomes satisfied (isolation), proving the correct query wiring."""
    # Connection only.
    mg = make_graph()
    add_connection_evidence(mg)
    s = NeedsEvaluator(mg).evaluate_all(T0 + timedelta(hours=1))
    assert s["connection"] is NeedState.SATISFIED
    assert s["growth"] is NeedState.DUE
    assert s["purpose"] is NeedState.DUE
    assert s["continuity"] is NeedState.DUE

    # Growth only.
    mg = make_graph()
    add_growth_evidence(mg)
    s = NeedsEvaluator(mg).evaluate_all(T0 + timedelta(days=1))
    assert s["growth"] is NeedState.SATISFIED
    assert s["connection"] is NeedState.DUE

    # Purpose only.
    mg = make_graph()
    add_purpose_evidence(mg)
    s = NeedsEvaluator(mg).evaluate_all(T0 + timedelta(days=1))
    assert s["purpose"] is NeedState.SATISFIED
    assert s["connection"] is NeedState.DUE


def test_all_four_satisfied_with_full_evidence():
    mg = make_graph()
    add_connection_evidence(mg, at=T0)
    add_growth_evidence(mg, at=T0)
    add_purpose_evidence(mg, at=T0)
    self_id = add_continuity_evidence(mg, at=T0)
    ns = NeedsSystem(mg, self_entity_id=self_id, clock=fixed_clock(T0 + timedelta(hours=1)))
    ns.initialize()
    st = ns.get_need_states()
    assert st.connection is NeedState.SATISFIED
    assert st.growth is NeedState.SATISFIED
    assert st.purpose is NeedState.SATISFIED
    assert st.continuity is NeedState.SATISFIED


def test_empty_graph_all_due():
    mg = make_graph()
    ns = NeedsSystem(mg, clock=fixed_clock(T0))
    ns.initialize()
    st = ns.get_need_states()
    for need in (st.connection, st.growth, st.purpose, st.continuity):
        assert need is NeedState.DUE


# ===========================================================================
# Group F — Soul Filter consumes the produced NeedStates unchanged (Req 14)
# ===========================================================================
def test_output_is_exactly_soul_filter_needstates_type():
    mg = make_graph()
    ns = NeedsSystem(mg, clock=fixed_clock(T0))
    ns.initialize()
    st = ns.get_need_states()
    # Not merely duck-typed: the SAME class soul_filter imports/consumes.
    assert type(st) is NeedStates
    assert isinstance(st, NeedStates)


def test_soul_filter_derive_constraints_reads_produced_energy():
    """The exact consumption path in soul_filter (`_derive_constraints` reads
    need_states.energy < ENERGY_LOW) works on the produced object unchanged."""
    filt = make_soul_filter()
    appraisal = make_appraisal()
    mg = make_graph()

    # Low Energy (< 30) -> 'do not overextend' appended.
    ns_low = NeedsSystem(mg, clock=fixed_clock(T0))
    ns_low.initialize(25.0)
    low = ns_low.get_need_states()
    c_low = filt._derive_constraints(appraisal, low)
    assert "do not overextend" in c_low

    # Normal Energy (>= 30) -> no energy constraint.
    ns_hi = NeedsSystem(mg, clock=fixed_clock(T0))
    ns_hi.initialize(100.0)
    hi = ns_hi.get_need_states()
    c_hi = filt._derive_constraints(appraisal, hi)
    assert "do not overextend" not in c_hi


def test_soul_filter_assemble_instruction_consumes_produced_needstates():
    """Full five-field assembly consumes the produced NeedStates unchanged and
    the Energy gate flows through to Constraints (Req 14.2)."""
    filt = make_soul_filter()
    appraisal = make_appraisal()
    mg = make_graph()
    ns = NeedsSystem(mg, clock=fixed_clock(T0))
    ns.initialize(18.0)  # critical energy
    states = ns.get_need_states()

    instr = filt.assemble_instruction(
        appraisal_result=appraisal,
        user_message="how are you?",
        entity_node_id=None,
        need_states=states,
    )
    assert isinstance(instr, FiveFieldInstruction)
    assert "do not overextend" in instr.constraints
    # The Energy NUMBER never crosses into the fields (only the prohibition).
    assert "18" not in instr.all_field_text()
    assert "energy" not in instr.all_field_text().lower()
