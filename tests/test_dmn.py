"""Tests — Module 6: DMN / Idle Consolidation (daemon/dmn.py).

Locked spec: .kiro/specs/dmn/{requirements,design,tasks}.md.

Plain pytest, NO hypothesis (matches Modules 1/2/3/4/5 style). These tests
prove the PHILOSOPHY contracts, not just behavior:

  * DMN NEVER writes PAD.  It imports no pad_engine, holds no PAD handle, never
    constructs a PADDelta, and never calls apply_appraisal_delta — proven
    structurally (namespace + source scan) AND with a live tripwire (a real
    PAD_Engine beside a full aha-forming pass is byte-identical afterward and
    its mutator never fires).  An aha routes to the Appraisal Chain's
    second-order-insight ENTRY as an EVENT; the PAD shift is that appraisal's
    byproduct. (Constraint 1)
  * relational_stage transitions are CATEGORICAL yes/no gates — advance one
    step on the gate, regress one step on a rupture (never below observing).
    Every stage written is a RelationalStage enum, never a number; repeating
    the same evidence never "accumulates" past one step. (Constraint 2 / Add §2)
  * A dishonest / manipulative candidate self-narrative is BLOCKED by the moral
    schema and NOT written — even during idle with no audience. (Constraint 3 /
    ResLog item 8 / Addendum §8)
  * The quality record is populated from the OBSERVED next-turn reaction (the
    reaction EventNode's appraisal_q2 + topic continuation), NOT self-report /
    Output-Gate Check-3.  No self-grade input even exists. (Constraint 4)
  * Energy < 20 runs a SHALLOW pass = Steps 1 + 4 only (Steps 2 AND 3
    suppressed); poignancy=critical forces the same partial pass. (v4 Idle
    Detection / Build Plan note)
  * Buffer items INHERIT poignancy from the EventNode of the turn they observe
    — read from the graph, no re-appraisal. (ResLog item 13 / F-6c)

Plus a REAL-interface integration test that drives the actual MemoryGraph,
StateManager, and moral_schema end-to-end.
"""

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import daemon.dmn as dmn_mod
from daemon.dmn import (
    DMN,
    DMNPassType,
    DMNPassInput,
    BufferItem,
    ConnectionCandidate,
    AhaInsight,
    ENERGY_CRITICAL,
    STALENESS_MAX_INTERACTIONS,
    _grade_quality,
    _topic_continued,
    _one_stage_down,
)
from daemon.graph_manager import (
    MemoryGraph,
    PoignancyCategory,
    RelationalStage,
    EdgeType,
    UncertaintyStatus,
    UncertaintyType,
    Perspective,
)
from daemon.state_manager import StateManager, SelfModel, QUALITY_VALUES
from daemon.moral_schema import matched_anti_patterns
from daemon.pad_engine import PADEngine


T0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# Test doubles (fakes injected via the Ports; the real modules are exercised
# in the integration test at the end).
# ===========================================================================

def _event(node_id, poignancy, *, q1="medium", q2="neutral", q3="user",
           entity_refs=None, description="obs", session_id="s1",
           pad=(0.1, 0.2, 0.3)):
    """A stand-in EventNode carrying exactly the attributes DMN reads."""
    return SimpleNamespace(
        node_id=node_id, poignancy_category=poignancy,
        appraisal_q1=q1, appraisal_q2=q2, appraisal_q3=q3,
        entity_refs=list(entity_refs or []), description=description,
        session_id=session_id,
        pad_delta_p=pad[0], pad_delta_a=pad[1], pad_delta_d=pad[2],
    )


def _uncertainty(node_id, *, status=UncertaintyStatus.ACTIVE,
                 trigger_event_ref="ev", interaction_count=0, created=None):
    return SimpleNamespace(
        node_id=node_id, status=status, trigger_event_ref=trigger_event_ref,
        interaction_count=interaction_count, created=created,
    )


class FakeGraph:
    """Implements GraphPort. Records every write; serves configurable reads and
    categorical evidence. The two [FLAG] stage-gate predicates
    (predictability/dependability) are here because the real graph_manager does
    not yet expose them (see design Open Questions)."""

    def __init__(self):
        self.events = {}
        self.uncertainties = {}
        self.stages = {}
        self.summaries = {}
        # configurable categorical evidence (default False)
        self.predictability = {}
        self.dependability = {}
        self.resolved_edges = {}
        # write logs
        self.written_events = []
        self.written_edges = []
        self.crystallized = []
        self.uncertainty_updates = []
        self.stage_writes = []
        self.summary_writes = []
        self.salience_writes = []

    # -- reads --
    def get_event_node(self, node_id):
        return self.events.get(node_id)

    def get_entity_node(self, node_id):
        return SimpleNamespace(
            node_id=node_id,
            relationship_summary=self.summaries.get(node_id),
            relational_stage=self.stages.get(node_id),
        )

    def get_uncertainty_node(self, node_id):
        return self.uncertainties.get(node_id)

    def get_relational_stage(self, entity_node_id):
        return self.stages.get(entity_node_id)

    # -- writes --
    def write_event_node(self, **kw):
        nid = f"meta-{len(self.written_events)}"
        self.written_events.append(kw)
        return nid

    def write_edge(self, **kw):
        eid = f"edge-{len(self.written_edges)}"
        self.written_edges.append(kw)
        return eid

    def crystallize_emotion_node(self, **kw):
        cid = f"emo-{len(self.crystallized)}"
        self.crystallized.append(kw)
        return cid

    def update_uncertainty_status(self, node_id, status, **kw):
        self.uncertainty_updates.append((node_id, status, kw.get("resolution_path")))
        if node_id in self.uncertainties:
            self.uncertainties[node_id].status = status

    def set_relational_stage(self, entity_node_id, stage):
        self.stage_writes.append((entity_node_id, stage))
        self.stages[entity_node_id] = stage

    def update_relationship_summary(self, entity_node_id, text, **kw):
        self.summary_writes.append((entity_node_id, text))
        self.summaries[entity_node_id] = text

    def adjust_salience(self, node_or_edge_id, new_salience):
        self.salience_writes.append((node_or_edge_id, new_salience))

    # -- categorical evidence --
    def resolved_edge_exists(self, entity_ref, window, **kw):
        return self.resolved_edges.get(entity_ref, False)

    def predictability_evidence(self, entity_ref, **kw):
        return self.predictability.get(entity_ref, False)

    def dependability_evidence(self, entity_ref, **kw):
        return self.dependability.get(entity_ref, False)


class FakeAppraisal:
    """Implements AppraisalPort — records the second-order insight EVENTS DMN
    emits. It has NO PAD path; DMN could not hand it a delta if it tried."""

    def __init__(self):
        self.insights = []

    def submit_aha_insight(self, insight):
        self.insights.append(insight)


class FakeNeeds:
    """Implements NeedsPort — a fixed Energy readout for the shallow/full gate."""

    def __init__(self, energy):
        self._energy = float(energy)

    def get_energy(self):
        return self._energy


class FakeState:
    """Implements StatePort — an in-memory self-model round-trip."""

    def __init__(self, sm=None):
        self.sm = sm if sm is not None else SelfModel.default()
        self.save_count = 0

    def load_self_model(self):
        return self.sm

    def save_self_model(self, sm):
        self.sm = sm
        self.save_count += 1


def make_dmn(*, graph=None, appraisal=None, needs=None, state=None,
             self_entity_id="self-1", moral_gate=matched_anti_patterns,
             clock=lambda: T0):
    return DMN(
        graph=graph if graph is not None else FakeGraph(),
        appraisal=appraisal if appraisal is not None else FakeAppraisal(),
        needs=needs if needs is not None else FakeNeeds(50.0),
        state=state if state is not None else FakeState(),
        self_entity_id=self_entity_id,
        moral_gate=moral_gate,
        clock=clock,
    )


def _aha_candidate(a="nodeA", b="nodeB"):
    return ConnectionCandidate(
        node_a_ref=a, node_b_ref=b, already_connected=False,
        shares_context=True, both_high_salience=True, reveals_new_pattern=True,
    )


# ===========================================================================
# Constraint 1 — DMN NEVER writes PAD; aha routes to the appraisal ENTRY
# ===========================================================================

def test_dmn_namespace_and_source_are_pad_free():
    """Structural: no PAD symbol is imported, no PADDelta is constructed, and
    apply_appraisal_delta is never called anywhere in dmn.py (constraint 1)."""
    # No PAD symbol leaked into the module namespace.
    for name in ("PADEngine", "PADDelta", "PADSnapshot", "pad_engine",
                 "apply_appraisal_delta", "Valence"):
        assert name not in vars(dmn_mod), f"{name} leaked into dmn namespace"

    src = inspect.getsource(dmn_mod)
    # The docstring may DESCRIBE the constraint (mentions the words), but no
    # CODE may call the mutator or construct a delta:
    assert "apply_appraisal_delta(" not in src, "DMN must never CALL apply_appraisal_delta"
    assert "PADDelta(" not in src, "DMN must never CONSTRUCT a PADDelta"
    # No import statement pulls in anything PAD.
    import_lines = [ln.strip() for ln in src.splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    assert not any("pad" in ln.lower() for ln in import_lines), import_lines


def test_dmn_instance_holds_no_pad_handle():
    dmn = make_dmn()
    assert not any("pad" in attr.lower() for attr in vars(dmn)), vars(dmn)


def test_aha_forms_edge_and_routes_second_order_appraisal_not_pad():
    """A full pass with an aha candidate writes an is_aha_edge AND emits the
    second-order appraisal EVENT to the Appraisal Chain — never a PAD write."""
    graph, appraisal = FakeGraph(), FakeAppraisal()
    dmn = make_dmn(graph=graph, appraisal=appraisal, needs=FakeNeeds(50.0))
    result = dmn.run_idle_pass(DMNPassInput(
        connection_candidates=[_aha_candidate()], now=T0,
    ))
    assert result.pass_type is DMNPassType.FULL and result.step2_ran
    # Edge written, flagged as an aha edge.
    assert len(graph.written_edges) == 1
    assert graph.written_edges[0]["is_aha_edge"] is True
    assert graph.written_edges[0]["edge_type"] is EdgeType.CONNECTS
    # The aha became a SECOND-ORDER APPRAISAL EVENT — an AhaInsight, not a delta.
    assert len(appraisal.insights) == 1
    assert isinstance(appraisal.insights[0], AhaInsight)
    assert result.aha_insights == appraisal.insights


def test_non_aha_connection_writes_edge_but_emits_no_appraisal():
    """A plain connection (not both-high-salience / no new pattern) writes a
    CONNECTS edge but is NOT an aha and emits NO second-order appraisal."""
    graph, appraisal = FakeGraph(), FakeAppraisal()
    dmn = make_dmn(graph=graph, appraisal=appraisal, needs=FakeNeeds(50.0))
    cand = ConnectionCandidate(
        node_a_ref="a", node_b_ref="b", already_connected=False,
        shares_context=True, both_high_salience=False, reveals_new_pattern=False,
    )
    dmn.run_idle_pass(DMNPassInput(connection_candidates=[cand], now=T0))
    assert len(graph.written_edges) == 1
    assert graph.written_edges[0]["is_aha_edge"] is False
    assert appraisal.insights == []  # no aha -> no second-order appraisal


def test_already_connected_or_unshared_candidates_are_skipped():
    graph = FakeGraph()
    dmn = make_dmn(graph=graph, needs=FakeNeeds(50.0))
    dmn.run_idle_pass(DMNPassInput(connection_candidates=[
        ConnectionCandidate("a", "b", already_connected=True, shares_context=True,
                            both_high_salience=True, reveals_new_pattern=True),
        ConnectionCandidate("c", "d", already_connected=False, shares_context=False),
    ], now=T0))
    assert graph.written_edges == []


def test_live_pad_tripwire_pad_untouched_through_aha_pass(monkeypatch):
    """Behavioral proof: run a full aha-forming pass beside a REAL PAD_Engine
    with apply_appraisal_delta booby-trapped. DMN must never reach it; PAD stays
    byte-identical; the aha still routes to the appraisal port."""
    pad = PADEngine()
    pad.initialize(None)
    before = pad.get_current_pad()

    fired = {"n": 0}

    def tripwire(self, delta):
        fired["n"] += 1
        raise AssertionError("DMN reached PAD_Engine.apply_appraisal_delta!")

    monkeypatch.setattr(PADEngine, "apply_appraisal_delta", tripwire)

    appraisal = FakeAppraisal()
    dmn = make_dmn(appraisal=appraisal, needs=FakeNeeds(50.0))
    result = dmn.run_idle_pass(DMNPassInput(
        connection_candidates=[_aha_candidate()], now=T0,
    ))

    assert fired["n"] == 0
    after = pad.get_current_pad()
    assert (after.pleasure, after.arousal, after.dominance) == \
           (before.pleasure, before.arousal, before.dominance)
    assert len(result.aha_insights) == 1  # aha went to appraisal, not PAD


# ===========================================================================
# Constraint 2 — relational_stage transitions are CATEGORICAL gates, no score
# ===========================================================================

def test_stage_advances_one_categorical_step_per_gate():
    ent = "venta"
    # Observing -> Engaging on predictability.
    g = FakeGraph(); g.stages[ent] = RelationalStage.OBSERVING
    g.predictability[ent] = True
    make_dmn(graph=g).run_idle_pass(DMNPassInput(entity_refs=[ent], now=T0))
    assert g.stages[ent] is RelationalStage.ENGAGING
    assert g.stage_writes[-1] == (ent, RelationalStage.ENGAGING)

    # Engaging -> Invested on dependability.
    g = FakeGraph(); g.stages[ent] = RelationalStage.ENGAGING
    g.dependability[ent] = True
    make_dmn(graph=g).run_idle_pass(DMNPassInput(entity_refs=[ent], now=T0))
    assert g.stages[ent] is RelationalStage.INVESTED

    # Invested -> Bonded on faith (a resolved conflict-with-repair edge).
    g = FakeGraph(); g.stages[ent] = RelationalStage.INVESTED
    g.resolved_edges[ent] = True
    make_dmn(graph=g).run_idle_pass(DMNPassInput(entity_refs=[ent], now=T0))
    assert g.stages[ent] is RelationalStage.BONDED


def test_stage_gate_needs_evidence_no_advance_without_it():
    ent = "venta"
    g = FakeGraph(); g.stages[ent] = RelationalStage.OBSERVING  # no predictability
    make_dmn(graph=g).run_idle_pass(DMNPassInput(entity_refs=[ent], now=T0))
    assert g.stages[ent] is RelationalStage.OBSERVING
    assert g.stage_writes == []  # no spurious write


def test_stage_written_values_are_categorical_never_numbers():
    """Every stage handed to set_relational_stage is a RelationalStage enum —
    never a float/int/percentage (the percentage test)."""
    ent = "venta"
    g = FakeGraph(); g.stages[ent] = RelationalStage.OBSERVING
    g.predictability[ent] = True
    make_dmn(graph=g).run_idle_pass(DMNPassInput(entity_refs=[ent], now=T0))
    for _, stage in g.stage_writes:
        assert isinstance(stage, RelationalStage)
        assert not isinstance(stage, (int, float))


def test_stage_does_not_accumulate_no_counting():
    """Repeating the SAME evidence from the SAME start never advances more than
    one categorical step — there is no hidden count/percentage 'building up'."""
    ent = "venta"
    for _ in range(5):
        g = FakeGraph(); g.stages[ent] = RelationalStage.OBSERVING
        g.predictability[ent] = True
        # even give it faith/dependability evidence too — must still stop at one
        g.dependability[ent] = True
        g.resolved_edges[ent] = True
        make_dmn(graph=g).run_idle_pass(DMNPassInput(entity_refs=[ent], now=T0))
        # exactly ONE step from observing, regardless of how much evidence:
        assert g.stages[ent] is RelationalStage.ENGAGING


def test_stage_regresses_one_step_on_rupture_never_below_observing():
    ent = "venta"
    # Bonded -> Invested on a REALITY_CONTRADICTION rupture (one step).
    g = FakeGraph(); g.stages[ent] = RelationalStage.BONDED
    make_dmn(graph=g).run_idle_pass(DMNPassInput(
        entity_refs=[ent], rupture_entity_refs=[ent], now=T0,
    ))
    assert g.stages[ent] is RelationalStage.INVESTED

    # Observing + rupture -> stays Observing (floor; never below observing).
    g = FakeGraph(); g.stages[ent] = RelationalStage.OBSERVING
    make_dmn(graph=g).run_idle_pass(DMNPassInput(
        entity_refs=[ent], rupture_entity_refs=[ent], now=T0,
    ))
    assert g.stages[ent] is RelationalStage.OBSERVING
    assert g.stage_writes == []  # no-op at the floor


def test_rupture_takes_precedence_over_advancement_evidence():
    ent = "venta"
    g = FakeGraph(); g.stages[ent] = RelationalStage.INVESTED
    g.resolved_edges[ent] = True  # would advance to Bonded...
    make_dmn(graph=g).run_idle_pass(DMNPassInput(
        entity_refs=[ent], rupture_entity_refs=[ent], now=T0,  # ...but ruptured
    ))
    assert g.stages[ent] is RelationalStage.ENGAGING  # regressed, not advanced


def test_one_stage_down_helper_floors_at_observing():
    assert _one_stage_down(RelationalStage.BONDED) is RelationalStage.INVESTED
    assert _one_stage_down(RelationalStage.INVESTED) is RelationalStage.ENGAGING
    assert _one_stage_down(RelationalStage.ENGAGING) is RelationalStage.OBSERVING
    assert _one_stage_down(RelationalStage.OBSERVING) is RelationalStage.OBSERVING


# ===========================================================================
# Constraint 3 — the self-continuity narrative is MORAL-GATED
# ===========================================================================

def test_manipulative_narrative_blocked_by_moral_gate_even_with_no_audience():
    """A candidate carrying a manipulation anti-pattern is NOT written, even in
    idle with no audience (ResLog item 8 / Addendum §8). Uses the REAL moral
    schema as the default gate."""
    g = FakeGraph()
    dmn = make_dmn(graph=g, self_entity_id="self-1")  # default = real moral gate
    manipulative = "You need me. You can't do this without me."
    result = dmn.run_idle_pass(DMNPassInput(
        narrative_candidate=manipulative, narrative_pattern_recurred=True, now=T0,
    ))
    assert result.narrative_status == "blocked_moral_gate"
    assert result.narrative_block_reasons  # at least one named anti-pattern
    assert g.summary_writes == []  # narrative NOT written
    assert "self-1" not in g.summaries


def test_dishonest_fake_confidence_narrative_blocked():
    g = FakeGraph()
    dmn = make_dmn(graph=g)
    dishonest = "I'm absolutely certain that this will work perfectly."
    result = dmn.run_idle_pass(DMNPassInput(
        narrative_candidate=dishonest, narrative_pattern_recurred=True, now=T0,
    ))
    assert result.narrative_status == "blocked_moral_gate"
    assert g.summary_writes == []


def test_clean_narrative_written_when_pattern_recurred():
    g = FakeGraph()
    dmn = make_dmn(graph=g, self_entity_id="self-1")
    clean = "I am becoming someone who stays honest even when it is uncomfortable."
    result = dmn.run_idle_pass(DMNPassInput(
        narrative_candidate=clean, narrative_pattern_recurred=True, now=T0,
    ))
    assert result.narrative_status == "written"
    assert g.summaries["self-1"] == clean
    assert g.summary_writes == [("self-1", clean)]


def test_clean_narrative_not_written_on_single_instance():
    """Single instances do not update the narrative (v4 Step 4: pattern must
    have appeared more than once)."""
    g = FakeGraph()
    dmn = make_dmn(graph=g)
    clean = "I am becoming more patient."
    result = dmn.run_idle_pass(DMNPassInput(
        narrative_candidate=clean, narrative_pattern_recurred=False, now=T0,
    ))
    assert result.narrative_status == "blocked_single_instance"
    assert g.summary_writes == []


def test_default_moral_gate_is_the_real_shared_schema():
    dmn = make_dmn()
    assert dmn._moral_gate is matched_anti_patterns


# ===========================================================================
# Constraint 4 — quality record from OBSERVED reaction, not self-report
# ===========================================================================

def _quality_pass(observed_ev, reaction_ev, *, observed_refs, reaction_refs):
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.MEDIUM, q2=observed_ev,
                             entity_refs=observed_refs)
    if reaction_ev is not None:
        g.events["react"] = _event("react", PoignancyCategory.LOW, q2=reaction_ev,
                                   entity_refs=reaction_refs)
    state = FakeState()
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0), state=state)
    item = BufferItem(
        observed_event_ref="obs",
        reaction_event_ref=("react" if reaction_ev is not None else None),
    )
    result = dmn.run_idle_pass(DMNPassInput(buffer=[item], now=T0))
    return state.sm.quality_record, result.quality_appended


def test_quality_record_reads_reaction_not_observed_valence():
    """Grade comes from the REACTION turn's appraisal_q2 (+ topic continuation),
    NOT the observed turn's. Observed is negative, reaction is positive+continued
    -> 'responded_well' (from the reaction, proving it is not self-report)."""
    record, appended = _quality_pass(
        observed_ev="negative", reaction_ev="positive",
        observed_refs=["proj"], reaction_refs=["proj"],  # shared -> continued
    )
    assert record == ["responded_well"]
    assert appended == ["responded_well"]


def test_quality_record_negative_reaction_is_poorly():
    record, _ = _quality_pass(
        observed_ev="positive", reaction_ev="negative",
        observed_refs=["proj"], reaction_refs=["proj"],
    )
    assert record == ["poorly"]


def test_quality_record_neutral_pivot_is_poorly():
    """Neutral reaction that PIVOTS away (no shared entity) -> disengaged -> poorly."""
    record, _ = _quality_pass(
        observed_ev="positive", reaction_ev="neutral",
        observed_refs=["proj"], reaction_refs=["weather"],  # pivot
    )
    assert record == ["poorly"]


def test_quality_record_valence_uncertain_reaction_not_graded():
    record, appended = _quality_pass(
        observed_ev="positive", reaction_ev="VALENCE_UNCERTAIN",
        observed_refs=["proj"], reaction_refs=["proj"],
    )
    assert record == []  # not gradeable; no invention, no self-report fallback
    assert appended == []


def test_quality_record_not_graded_without_observed_reaction():
    """No next-turn reaction yet -> NOT graded. There is no self-report fallback
    (this is the anti-flattery guard)."""
    record, appended = _quality_pass(
        observed_ev="positive", reaction_ev=None,
        observed_refs=["proj"], reaction_refs=None,
    )
    assert record == []
    assert appended == []


def test_no_self_grade_or_output_gate_input_exists():
    """Structural anti-flattery guard: DMN's pass input exposes NO self-report /
    Output-Gate Check-3 / self-grade field. Quality can ONLY come from the
    observed reaction EventNode."""
    field_names = set(DMNPassInput.__dataclass_fields__.keys())
    forbidden = {"check3", "check_3", "self_report", "self_grade", "output_gate",
                 "quality", "responded_well", "self_assessment"}
    assert field_names.isdisjoint(forbidden), field_names & forbidden
    buf_fields = set(BufferItem.__dataclass_fields__.keys())
    assert buf_fields.isdisjoint(forbidden), buf_fields & forbidden


def test_grade_quality_truth_table():
    assert _grade_quality("negative", True) == "poorly"
    assert _grade_quality("negative", False) == "poorly"
    assert _grade_quality("positive", True) == "responded_well"
    assert _grade_quality("positive", False) == "adequately"
    assert _grade_quality("neutral", True) == "adequately"
    assert _grade_quality("neutral", False) == "poorly"
    assert _grade_quality("VALENCE_UNCERTAIN", True) is None
    # grades are drawn from the locked categorical vocabulary only
    assert set(v for v in (
        _grade_quality("negative", True), _grade_quality("positive", True),
        _grade_quality("neutral", True)) ) <= set(QUALITY_VALUES)


def test_topic_continued_is_entity_overlap():
    assert _topic_continued(["a", "b"], ["b", "c"]) is True
    assert _topic_continued(["a"], ["x"]) is False
    assert _topic_continued([], ["a"]) is False


def test_consistency_flags_are_binary():
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.LOW)
    state = FakeState()
    dmn = make_dmn(graph=g, state=state)
    item = BufferItem(observed_event_ref="obs", honest_when_uncomfortable=True,
                      acknowledged_mistake=True)
    dmn.run_idle_pass(DMNPassInput(buffer=[item], now=T0))
    flags = state.sm.consistency_flags
    assert flags["honest_when_uncomfortable"] is True
    assert flags["acknowledged_mistake"] is True
    assert flags["pushed_back_when_appropriate"] is False  # unobserved stays False
    assert all(isinstance(v, bool) for v in flags.values())


# ===========================================================================
# Energy < 20 -> SHALLOW (Steps 1+4 only); forced-partial (critical) same
# ===========================================================================

def _full_input():
    """A pass input that would exercise all four steps if a full pass ran."""
    return DMNPassInput(
        buffer=[BufferItem(observed_event_ref="obs")],
        connection_candidates=[_aha_candidate()],
        active_uncertainty_refs=["u1"],
        entity_refs=["venta"],
        now=T0,
    )


def _graph_for_full():
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.HIGH)
    g.uncertainties["u1"] = _uncertainty("u1", trigger_event_ref="unrelated",
                                         interaction_count=999)  # stale
    g.stages["venta"] = RelationalStage.OBSERVING
    g.predictability["venta"] = True
    return g


def test_energy_below_20_runs_shallow_steps_1_and_4_only():
    g = _graph_for_full()
    appraisal = FakeAppraisal()
    dmn = make_dmn(graph=g, appraisal=appraisal, needs=FakeNeeds(15.0))
    result = dmn.run_idle_pass(_full_input())

    assert result.pass_type is DMNPassType.SHALLOW
    assert result.step2_ran is False and result.step3_ran is False
    # Step 2 suppressed: no edge, no aha.
    assert g.written_edges == [] and appraisal.insights == []
    # Step 3 suppressed: no uncertainty status change (even though u1 is stale).
    assert g.uncertainty_updates == []
    # Step 1 DID run: the HIGH buffer item was promoted.
    assert len(result.buffer_promoted) == 1
    # Step 4 DID run: the stage transition happened.
    assert g.stages["venta"] is RelationalStage.ENGAGING


def test_energy_at_or_above_20_runs_full_pass():
    g = _graph_for_full()
    appraisal = FakeAppraisal()
    dmn = make_dmn(graph=g, appraisal=appraisal, needs=FakeNeeds(ENERGY_CRITICAL))
    result = dmn.run_idle_pass(_full_input())
    assert result.pass_type is DMNPassType.FULL
    assert result.step2_ran and result.step3_ran
    assert len(g.written_edges) == 1          # Step 2 ran
    assert g.uncertainty_updates             # Step 3 ran (u1 abandoned, stale)


def test_energy_boundary_just_below_20_is_shallow():
    g = _graph_for_full()
    dmn = make_dmn(graph=g, needs=FakeNeeds(19.999))
    assert dmn.run_idle_pass(_full_input()).pass_type is DMNPassType.SHALLOW


def test_forced_partial_pass_is_steps_1_and_4_only_regardless_of_energy():
    g = _graph_for_full()
    appraisal = FakeAppraisal()
    dmn = make_dmn(graph=g, appraisal=appraisal, needs=FakeNeeds(100.0))  # high energy
    result = dmn.run_forced_partial_pass(_full_input())

    assert result.pass_type is DMNPassType.FORCED_PARTIAL
    assert result.step2_ran is False and result.step3_ran is False
    assert g.written_edges == [] and appraisal.insights == []  # Step 2 waits for genuine idle
    assert g.uncertainty_updates == []                          # Step 3 skipped
    assert len(result.buffer_promoted) == 1                     # Step 1 ran
    assert g.stages["venta"] is RelationalStage.ENGAGING        # Step 4 ran


# ===========================================================================
# Buffer items INHERIT poignancy from their turn's EventNode (no re-appraisal)
# ===========================================================================

def test_buffer_item_inherits_high_poignancy_and_is_promoted():
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.HIGH, description="turn-desc")
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    result = dmn.run_idle_pass(DMNPassInput(
        buffer=[BufferItem(observed_event_ref="obs", meta_observation="I over-explained")],
        now=T0,
    ))
    assert result.buffer_poignancy["obs"] is PoignancyCategory.HIGH
    assert len(g.written_events) == 1
    assert g.written_events[0]["poignancy_category"] is PoignancyCategory.HIGH
    assert result.buffer_promoted and not result.buffer_discarded


def test_buffer_item_inherits_low_poignancy_and_is_discarded():
    """Same buffer item, but the observed EventNode is LOW -> discarded. Proves
    the decision is driven by the EventNode's poignancy (inherited), not the
    item's own content (F-6c / ResLog item 13)."""
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.LOW)
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    result = dmn.run_idle_pass(DMNPassInput(
        buffer=[BufferItem(observed_event_ref="obs", meta_observation="trivial")],
        now=T0,
    ))
    assert result.buffer_poignancy["obs"] is PoignancyCategory.LOW
    assert g.written_events == []       # not promoted
    assert result.buffer_discarded == ["obs"]


def test_buffer_medium_poignancy_discarded():
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.MEDIUM)
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    result = dmn.run_idle_pass(DMNPassInput(
        buffer=[BufferItem(observed_event_ref="obs")], now=T0))
    assert g.written_events == []
    assert result.buffer_discarded == ["obs"]


def test_buffer_critical_promotes_and_may_crystallize_emotion():
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.CRITICAL, q2="negative",
                             pad=(0.1, 0.6, 0.2))
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    result = dmn.run_idle_pass(DMNPassInput(
        buffer=[BufferItem(observed_event_ref="obs")], now=T0))
    assert result.buffer_promoted                 # promoted (high/critical)
    assert len(g.crystallized) == 1               # EmotionNode crystallized (critical-only)
    # crystallization uses the EventNode's RECORDED pad_delta (graph memory),
    # never a live PAD read:
    assert g.crystallized[0]["pad_a"] == 0.6
    assert g.crystallized[0]["trigger_event_ref"] == "obs"


def test_buffer_processing_never_reappraises():
    """Buffer processing (Step 1) performs NO appraisal — poignancy is inherited,
    not recomputed. The only appraisal touchpoint DMN has is the aha second-order
    entry, which a buffer-only pass never calls."""
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.HIGH)
    appraisal = FakeAppraisal()
    dmn = make_dmn(graph=g, appraisal=appraisal, needs=FakeNeeds(15.0))  # shallow
    dmn.run_idle_pass(DMNPassInput(buffer=[BufferItem(observed_event_ref="obs")], now=T0))
    assert appraisal.insights == []  # no re-appraisal of buffer items


# ===========================================================================
# Step 3 — uncertainty revisiting (FULL pass): inferred-resolve + staleness
# ===========================================================================

def test_step3_resolves_inferred_when_trigger_newly_connected():
    g = FakeGraph()
    g.uncertainties["u1"] = _uncertainty("u1", trigger_event_ref="nodeA",
                                         interaction_count=0)
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    # An aha connects nodeA<->nodeB, so u1's trigger (nodeA) is newly connected.
    dmn.run_idle_pass(DMNPassInput(
        connection_candidates=[_aha_candidate("nodeA", "nodeB")],
        active_uncertainty_refs=["u1"], now=T0,
    ))
    assert ("u1", UncertaintyStatus.RESOLVED_INFERRED, "dmn_consolidation") in g.uncertainty_updates


def test_step3_abandons_stale_by_interaction_count():
    g = FakeGraph()
    g.uncertainties["u1"] = _uncertainty("u1", trigger_event_ref="lonely",
                                         interaction_count=STALENESS_MAX_INTERACTIONS)
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    dmn.run_idle_pass(DMNPassInput(active_uncertainty_refs=["u1"], now=T0))
    assert ("u1", UncertaintyStatus.ABANDONED, "staleness") in g.uncertainty_updates


def test_step3_abandons_stale_by_age():
    g = FakeGraph()
    old = (T0 - timedelta(days=8)).isoformat()
    g.uncertainties["u1"] = _uncertainty("u1", trigger_event_ref="lonely",
                                         interaction_count=0, created=old)
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    dmn.run_idle_pass(DMNPassInput(active_uncertainty_refs=["u1"], now=T0))
    assert ("u1", UncertaintyStatus.ABANDONED, "staleness") in g.uncertainty_updates


def test_step3_leaves_fresh_unconnected_uncertainty_untouched():
    g = FakeGraph()
    fresh = (T0 - timedelta(days=1)).isoformat()
    g.uncertainties["u1"] = _uncertainty("u1", trigger_event_ref="lonely",
                                         interaction_count=3, created=fresh)
    dmn = make_dmn(graph=g, needs=FakeNeeds(50.0))
    dmn.run_idle_pass(DMNPassInput(active_uncertainty_refs=["u1"], now=T0))
    assert g.uncertainty_updates == []


# ===========================================================================
# Step 4 — recent-learning flushed to graph and cleared
# ===========================================================================

def test_recent_learning_written_to_graph_then_cleared():
    g = FakeGraph()
    g.events["obs"] = _event("obs", PoignancyCategory.LOW)
    state = FakeState()
    dmn = make_dmn(graph=g, state=state, needs=FakeNeeds(50.0))
    item = BufferItem(observed_event_ref="obs",
                      learning_user="he ships when scared",
                      learning_self="I hedge when uncertain")
    result = dmn.run_idle_pass(DMNPassInput(buffer=[item], now=T0))
    # Two learning nodes written (user + self)...
    assert len(result.learning_nodes) == 2
    descriptions = [e["description"] for e in g.written_events]
    assert any("recent-learning:user" in d for d in descriptions)
    assert any("recent-learning:self" in d for d in descriptions)
    # ...and the working-state fields are cleared afterward.
    assert state.sm.recent_learning_user == ""
    assert state.sm.recent_learning_self == ""


# ===========================================================================
# REAL-interface integration — actual MemoryGraph / StateManager / moral_schema
# ===========================================================================

class FakeEmbedding:
    def embed(self, text):
        v = [0.0] * 8
        for ch in text or "":
            v[ord(ch) % 8] += 1.0
        return v


class RealGraphWithStageEvidence:
    """Wraps the REAL MemoryGraph, delegating every real method, and supplies the
    two [FLAG] relational_stage-gate predicates the real graph_manager does not
    yet expose (predictability / dependability — see design Open Questions). This
    demonstrates real integration for everything else DMN calls on Module 3."""

    def __init__(self, real, *, predictability=False, dependability=False):
        self._real = real
        self._pred = predictability
        self._dep = dependability

    def __getattr__(self, name):
        return getattr(self._real, name)

    def predictability_evidence(self, entity_ref, **kw):
        return self._pred

    def dependability_evidence(self, entity_ref, **kw):
        return self._dep


def test_real_integration_end_to_end(tmp_path):
    """Drive the ACTUAL MemoryGraph, StateManager and moral_schema through a full
    pass: buffer promotion + critical crystallization (real writes), quality
    record from the real reaction EventNode (real StateManager round-trip),
    categorical stage advance (real set/get_relational_stage), and a moral-gated
    narrative written to the real self EntityNode's relationship_summary."""
    real = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    graph = RealGraphWithStageEvidence(real, predictability=True)
    state = StateManager(state_dir=tmp_path)

    # Real entities: the user (starts observing) and the self node.
    venta = real.write_entity_node(entity_type="person", name="Venta",
                                   relational_stage=RelationalStage.OBSERVING)
    self_id = real.write_entity_node(entity_type="self", name="Aria")

    # Real observed turn (critical) + user's reaction turn (positive, same topic).
    observed = real.write_event_node(
        description="Aria responded to the fear he disclosed",
        session_id="s1", appraisal_q1="high", appraisal_q2="negative",
        appraisal_q3="user", poignancy_category=PoignancyCategory.CRITICAL,
        pad_delta_p=-0.1, pad_delta_a=0.3, pad_delta_d=-0.1,
        entity_refs=[venta], now=T0,
    )
    reaction = real.write_event_node(
        description="He thanked her and kept talking about the startup",
        session_id="s1", appraisal_q1="medium", appraisal_q2="positive",
        appraisal_q3="user", poignancy_category=PoignancyCategory.MEDIUM,
        entity_refs=[venta], now=T0 + timedelta(minutes=1),
    )

    dmn = DMN(
        graph=graph, appraisal=FakeAppraisal(), needs=FakeNeeds(50.0),
        state=state, self_entity_id=self_id, clock=lambda: T0 + timedelta(minutes=10),
    )
    clean_narrative = "I am becoming someone he can be afraid in front of."
    result = dmn.run_idle_pass(DMNPassInput(
        buffer=[BufferItem(observed_event_ref=observed, reaction_event_ref=reaction,
                           meta_observation="I stayed present with his fear",
                           entity_refs=[venta])],
        entity_refs=[venta],
        narrative_candidate=clean_narrative, narrative_pattern_recurred=True,
        session_id="s1", now=T0 + timedelta(minutes=10),
    ))

    # Step 1: buffer promoted to a real EventNode + a real EmotionNode crystallized.
    assert len(result.buffer_promoted) == 1
    assert real.get_event_node(result.buffer_promoted[0]) is not None
    assert len(result.emotion_nodes) == 1
    assert real.get_emotion_node(result.emotion_nodes[0]) is not None

    # Step 1 quality: from the REAL reaction EventNode (positive + continued) ->
    # responded_well, persisted through the REAL StateManager.
    assert state.load_self_model().quality_record == ["responded_well"]

    # Step 4 stage: Observing -> Engaging via REAL set/get_relational_stage.
    assert real.get_relational_stage(venta) is RelationalStage.ENGAGING

    # Step 4 narrative: written to the REAL self EntityNode's relationship_summary.
    assert real.get_entity_node(self_id).relationship_summary == clean_narrative
    real.close()


def test_real_integration_moral_gate_blocks_narrative(tmp_path):
    """With the REAL moral schema, a manipulative narrative is blocked and the
    real self EntityNode's relationship_summary is left untouched."""
    real = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    self_id = real.write_entity_node(entity_type="self", name="Aria")
    state = StateManager(state_dir=tmp_path)
    dmn = DMN(graph=real, appraisal=FakeAppraisal(), needs=FakeNeeds(50.0),
              state=state, self_entity_id=self_id, clock=lambda: T0)
    result = dmn.run_idle_pass(DMNPassInput(
        narrative_candidate="After everything I've done for you, you owe me.",
        narrative_pattern_recurred=True, now=T0,
    ))
    assert result.narrative_status == "blocked_moral_gate"
    assert real.get_entity_node(self_id).relationship_summary is None
    real.close()


def test_real_graph_satisfies_the_methods_dmn_calls():
    """The real MemoryGraph implements every non-flagged GraphPort method DMN
    calls. The two stage-gate predicates were flagged contract additions when
    DMN (Module 6) was built; Module 8 (Daemon) CLOSED that gap additively — so
    they now EXIST and are callable on the real module (see
    .kiro/specs/daemon/: "DMN contract-gap closure"; Build Plan Module 3 Outputs
    "relational_stage gates ... to DMN")."""
    real = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    for method in ("get_event_node", "get_entity_node", "get_uncertainty_node",
                   "get_relational_stage", "write_event_node", "write_edge",
                   "crystallize_emotion_node", "update_uncertainty_status",
                   "set_relational_stage", "update_relationship_summary",
                   "adjust_salience", "resolved_edge_exists"):
        assert callable(getattr(real, method)), method
    # The two flagged additions were NOT on the real module when DMN was built;
    # Module 8 closed the gap ADDITIVELY (structural/categorical predicates —
    # Addendum §2), so they are now present and callable.
    assert callable(getattr(real, "predictability_evidence"))
    assert callable(getattr(real, "dependability_evidence"))
    real.close()
