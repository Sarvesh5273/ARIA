"""Tests for Module 4 — Appraisal Chain (daemon/appraisal_chain.py).

Plain pytest, NO hypothesis (matching Modules 1 & 3). "Property" checks use
representative hand-picked inputs. The chain is exercised against the REAL
pad_engine.PADEngine and graph_manager.MemoryGraph (in-memory ":memory:"),
with a deterministic, table-controlled FakeEmbedding injected as the shared
EmbeddingModel — so we test the real interfaces, not mocks of them. A thin
SpyGraph subclass records retrieve() kwargs and can force a contradiction, to
verify delegation and Stage-1 wiring without touching graph internals.

Flagged build-time placeholders (PAD delta step magnitudes, coping bands, arc
turn-counts, similarity cutoffs) are NOT asserted to a value — only their
PROPERTIES (ordering, sign, categorical outcome), exactly as Module 3 handled
OQ1-rate/OQ2.
"""

from datetime import datetime, timezone

import pytest

from daemon.pad_engine import PADEngine, PADDelta, Valence
from daemon.graph_manager import (
    MemoryGraph,
    EdgeType,
    PoignancyCategory,
    Perspective,
    UncertaintyType,
    UncertaintyStatus,
    EventNode,
)
import daemon.appraisal_chain as ac
from daemon.appraisal_chain import (
    AppraisalChain,
    AppraisalConfig,
    AppraisalResult,
    GoalRelevance,
    Attribution,
    EmergencyType,
    SocialSignals,
    _Appraisal,
    _PAD_STEP,
    _Q2_TO_GRAPH,
    _VULNERABILITY_EXEMPLARS,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_VULN_VEC = [0.0, 1.0, 0.0, 0.0]
_NEUT_VEC = [1.0, 0.0, 0.0, 0.0]


class FakeEmbedding:
    """Deterministic injected embedding. Text in `table` gets its explicit
    vector; every exemplar maps to _VULN_VEC; everything else maps to a
    neutral vector orthogonal to _VULN_VEC (so vulnerability fires only for
    text we explicitly mark)."""

    def __init__(self, table=None):
        self.table = dict(table or {})
        for ex in _VULNERABILITY_EXEMPLARS:
            self.table.setdefault(ex, list(_VULN_VEC))

    def embed(self, text):
        if text in self.table:
            return self.table[text]
        return list(_NEUT_VEC)


class SpyGraph(MemoryGraph):
    """Real MemoryGraph that records retrieve() kwargs and can force a
    reality contradiction — for delegation/wiring assertions only."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.retrieve_calls = []
        self.force_contradiction = False

    def retrieve(self, **kw):
        self.retrieve_calls.append(kw)
        return super().retrieve(**kw)

    def reality_contradiction_check(self, entity_ref, candidate_text, **kw):
        if self.force_contradiction:
            return True
        return super().reality_contradiction_check(entity_ref, candidate_text, **kw)


def make_chain(table=None, spy=False, config=None):
    emb = FakeEmbedding(table)
    pad = PADEngine()
    pad.initialize(None)
    graph = (SpyGraph if spy else MemoryGraph)(":memory:", embedding_model=emb)
    chain = AppraisalChain(
        pad_engine=pad, graph=graph, embedding_model=emb,
        config=config or AppraisalConfig(),
    )
    return chain, pad, graph, emb


# ===========================================================================
# Types / constants
# ===========================================================================


def test_enum_domains_exact():
    assert [e.value for e in GoalRelevance] == ["none", "low", "medium", "high"]
    assert [e.value for e in Attribution] == [
        "self", "user", "circumstance", "CAUSAL_UNCERTAIN"]
    assert [e.value for e in EmergencyType] == [
        "PHYSICAL_THREAT", "EXISTENTIAL_DISTRESS", "DECISION_CRITICAL", "UNCLASSIFIED"]


def test_q2_reuses_pad_engine_valence():
    # Q2 IS pad_engine.Valence (not a second enum).
    r = _appraise_positive()
    assert isinstance(r.q2, Valence)


def test_appraisal_result_frozen():
    r = _appraise_positive()
    with pytest.raises(Exception):
        r.q1 = GoalRelevance.LOW


def test_pad_step_ordered_and_zero_base():
    # Substrate placeholders: ordering asserted, exact magnitudes are NOT.
    assert _PAD_STEP[GoalRelevance.NONE] == 0.0
    assert (_PAD_STEP[GoalRelevance.NONE] < _PAD_STEP[GoalRelevance.LOW]
            < _PAD_STEP[GoalRelevance.MEDIUM] < _PAD_STEP[GoalRelevance.HIGH])


def test_q2_to_graph_string_mapping():
    assert _Q2_TO_GRAPH[Valence.VALENCE_UNCERTAIN] == "VALENCE_UNCERTAIN"
    assert _Q2_TO_GRAPH[Valence.NEGATIVE] == "negative"
    assert _Q2_TO_GRAPH[Valence.POSITIVE] == "positive"
    assert _Q2_TO_GRAPH[Valence.NEUTRAL] == "neutral"


# ---- shared helper turns ----

def _appraise_positive():
    chain, pad, g, emb = make_chain()
    return chain.appraise(user_text="thanks, that was great",
                          session_id="s", entity_refs=["user"], now=T0)


# ===========================================================================
# Stage 0 — input classification (Req 1)
# ===========================================================================


def test_stage0_empty_input_is_input_uncertain():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="   ", session_id="s", entity_refs=["user"], now=T0)
    assert r.is_partial_appraisal is True
    assert r.uncertainty_node_id is not None
    node = g.get_uncertainty_node(r.uncertainty_node_id)
    assert node.uncertainty_type is UncertaintyType.INPUT_UNCERTAIN
    # secondary-appraisal byproduct signs (v4): pleasure down, arousal up.
    assert r.pad_delta.d_pleasure < 0
    assert r.pad_delta.d_arousal > 0
    assert r.pad_delta.d_dominance < 0
    assert r.q2 is Valence.VALENCE_UNCERTAIN


def test_stage0_normal_input_proceeds():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="thanks, that was great",
                       session_id="s", entity_refs=["user"], now=T0)
    # A clean positive turn is not routed to INPUT_UNCERTAIN.
    assert g.active_uncertainty_count() == 0
    assert r.q2 is Valence.POSITIVE


# ===========================================================================
# Stage 1 — context load + retrieval wiring (Req 2)
# ===========================================================================


def test_retrieve_called_with_mood_sign_need_prefs_and_embedding():
    chain, pad, g, emb = make_chain(spy=True)
    chain.appraise(user_text="thanks", session_id="s", entity_refs=["user"],
                   need_states={"connection": "neglected"}, now=T0)
    assert len(g.retrieve_calls) == 1
    call = g.retrieve_calls[0]
    # baseline pleasure at init → sign 0 (categorical sign, not a magnitude)
    assert call["pad_pleasure_sign"] in (-1, 0, 1)
    assert call["need_prefs"] == {"connection": True}
    assert call["entity_refs"] == ["user"]
    assert call["query_embedding"] is not None


# ===========================================================================
# Stage 1 — social-signal pre-pass (Req 3), non-generative
# ===========================================================================


def test_distress_marker_lexical():
    chain, *_ = make_chain()
    assert chain._distress_marker("I feel completely hopeless and alone") is True
    assert chain._distress_marker("the weather is nice today") is False


def test_vulnerability_via_embedding_controlled():
    table = {"secret confession": list(_VULN_VEC)}  # near exemplars
    chain, pad, g, emb = make_chain(table=table)
    assert chain._vulnerability("secret confession") is True
    assert chain._vulnerability("the weather is nice today") is False


def test_reality_contradiction_delegates_to_graph():
    chain, pad, g, emb = make_chain(spy=True)
    g.force_contradiction = True
    assert chain._reality_contradiction("user", "you never said that", T0) is True
    g.force_contradiction = False
    assert chain._reality_contradiction(None, "x", T0) is False  # no entity


def test_prepass_methods_do_not_touch_pad():
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    chain._distress_marker("I am completely broken")
    chain._vulnerability("secret")
    chain._reality_contradiction("user", "text", T0)
    after = pad.get_current_pad()
    assert (before.pleasure, before.arousal, before.dominance) == \
           (after.pleasure, after.arousal, after.dominance)


def test_conflict_arc_closure_writes_resolved_edge():
    # Two consecutive negatives open the arc; a positive flip closes it and
    # writes exactly one "resolved" edge (Addendum §1; Resolution Log item 5).
    chain, pad, g, emb = make_chain(config=AppraisalConfig(arc_open_consecutive_negative=2))
    window = _big_window()
    chain.appraise(user_text="I hate this, it is awful", session_id="s",
                   entity_refs=["proj"], now=T0)
    chain.appraise(user_text="this is terrible and broken", session_id="s",
                   entity_refs=["proj"], now=T0)
    assert g.resolved_edge_exists("proj", window) is False  # open, not closed
    r = chain.appraise(user_text="thanks, it is working great now", session_id="s",
                       entity_refs=["proj"], now=T0)
    assert r.social_signals.conflict_arc_closed_this_turn is True
    assert g.resolved_edge_exists("proj", window) is True


def test_conflict_arc_closes_after_enough_absent_turns():
    # Addendum §1 SECOND close condition: the arc also closes when "enough turns
    # pass without that entity recurring". Categorical — the turns have passed or
    # they have not.
    threshold = 3
    chain, pad, g, emb = make_chain(config=AppraisalConfig(
        arc_open_consecutive_negative=2, arc_close_absent_turns=threshold))
    window = _big_window()
    # (a) open a conflict arc on "proj"
    chain.appraise(user_text="I hate this, it is awful", session_id="s",
                   entity_refs=["proj"], now=T0)
    chain.appraise(user_text="this is terrible and broken", session_id="s",
                   entity_refs=["proj"], now=T0)
    assert chain._arc_open["proj"] is True
    assert g.resolved_edge_exists("proj", window) is False
    # (b) N turns with NO EventNode on "proj" — and no Q2 flip on it either
    for i in range(threshold):
        assert chain._arc_open["proj"] is True, f"closed early at turn {i}"
        chain.appraise(user_text="the weather is fine", session_id="s",
                       entity_refs=[f"other{i}"], now=T0)
    # (c) the arc is closed
    assert chain._arc_open["proj"] is False
    # (d) a "resolved" edge was written, same as the Q2-flip close
    assert g.resolved_edge_exists("proj", window) is True


def test_conflict_arc_absence_counter_resets_when_entity_recurs():
    # The counter measures turns WITHOUT the entity; a recurrence puts it back
    # to zero, so an arc that keeps being revisited never closes by absence.
    chain, pad, g, emb = make_chain(config=AppraisalConfig(
        arc_open_consecutive_negative=2, arc_close_absent_turns=3))
    window = _big_window()
    chain.appraise(user_text="I hate this, it is awful", session_id="s",
                   entity_refs=["proj"], now=T0)
    chain.appraise(user_text="this is terrible and broken", session_id="s",
                   entity_refs=["proj"], now=T0)
    for _ in range(4):
        chain.appraise(user_text="the weather is fine", session_id="s",
                       entity_refs=["other"], now=T0)      # 2 absent turns
        chain.appraise(user_text="this is awful too", session_id="s",
                       entity_refs=["proj"], now=T0)        # recurs → reset
        chain.appraise(user_text="the weather is fine", session_id="s",
                       entity_refs=["other"], now=T0)
    assert chain._arc_open["proj"] is True
    assert g.resolved_edge_exists("proj", window) is False


def test_conflict_arc_absent_turn_threshold_is_a_turn_count():
    # The knob is one turn count under two spec-sanctioned names, and it is an
    # int number of turns — never a percentage or a weight.
    assert ac._ARC_CLOSE_ABSENT_TURNS == ac._CONFLICT_ARC_ABSENT_TURN_THRESHOLD
    assert isinstance(ac._CONFLICT_ARC_ABSENT_TURN_THRESHOLD, int)
    assert AppraisalConfig().arc_close_absent_turns == \
        ac._CONFLICT_ARC_ABSENT_TURN_THRESHOLD


def test_resolved_edge_base_salience_equals_opening_node():
    """When a conflict arc closes (by Q2 flip OR by absence timeout), the
    'resolved' edge's base_salience equals the opening EventNode's
    base_salience, and its salience equals exactly 3× that
    (Resolution Log item 5; v4 'Argument Buffer Mode')."""

    def the_resolved_edge(g, opening_id):
        # The closure edge is directed closing→opening, so it is incident to the
        # opening node. Exactly one is written per arc closure.
        edges = [e for e in g._edges_incident_to(opening_id)
                 if e.edge_type is EdgeType.RESOLVED]
        assert len(edges) == 1, f"expected one resolved edge, got {len(edges)}"
        return edges[0]

    threshold = 3
    for close_by in ("flip", "absence"):
        chain, pad, g, emb = make_chain(config=AppraisalConfig(
            arc_open_consecutive_negative=2, arc_close_absent_turns=threshold))
        # (1) open the arc — two consecutive negative-Q2 turns on "proj"
        opener = chain.appraise(user_text="I hate this, it is awful",
                                session_id="s", entity_refs=["proj"], now=T0)
        chain.appraise(user_text="this is terrible and broken", session_id="s",
                       entity_refs=["proj"], now=T0)
        assert chain._arc_open["proj"] is True, close_by
        # (2) close it — both spec'd close conditions must produce the same edge
        if close_by == "flip":
            chain.appraise(user_text="thanks, it is working great now",
                           session_id="s", entity_refs=["proj"], now=T0)
        else:
            for i in range(threshold):
                chain.appraise(user_text="the weather is fine", session_id="s",
                               entity_refs=[f"other{i}"], now=T0)
        assert chain._arc_open["proj"] is False, close_by
        # (3) the RESOLVED edge, and the conflict it closes
        edge = the_resolved_edge(g, opener.event_node_id)
        opening_node = g.get_event_node(opener.event_node_id)
        # (4) the edge's base IS the conflict's own base — no invented magnitude
        assert edge.base_salience == pytest.approx(opening_node.base_salience), close_by
        # (5) v4: the resolution is "weighted 3× higher than the conflict itself"
        assert edge.salience == pytest.approx(3.0 * opening_node.base_salience), close_by
        # (6) an arc only ever opens on a Q2=negative EventNode, so the v4
        # Baumeister +0.15 guarantees the 3× multiplier a non-zero multiplicand
        # even at medium/low poignancy (which has no floor, ResLog item 9).
        assert opening_node.base_salience > 0.0, close_by


def _big_window():
    from datetime import timedelta
    return timedelta(days=3650)


# ===========================================================================
# Stage 2 — categorical Q1..Q4 (Req 4)
# ===========================================================================


def test_q_categorical_outcomes():
    chain, pad, g, emb = make_chain()
    # distress → Q1 high, Q2 negative
    r = chain.appraise(user_text="I am completely hopeless", session_id="s",
                       entity_refs=["user"], now=T0)
    assert r.q1 is GoalRelevance.HIGH and r.q2 is Valence.NEGATIVE
    # positive → Q2 positive
    r2 = chain.appraise(user_text="thank you, wonderful", session_id="s",
                        entity_refs=["user2"], now=T0)
    assert r2.q2 is Valence.POSITIVE


def test_q2_valence_uncertain_on_mixed_and_ambiguous():
    chain, pad, g, emb = make_chain()
    # mixed positive+negative cue → VALENCE_UNCERTAIN
    r = chain.appraise(user_text="I love it but I feel awful", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.q2 is Valence.VALENCE_UNCERTAIN
    # ambiguity cue only → VALENCE_UNCERTAIN
    r2 = chain.appraise(user_text="the result was interesting", session_id="s",
                        entity_refs=["u2"], now=T0)
    assert r2.q2 is Valence.VALENCE_UNCERTAIN


def test_q3_causal_uncertain_and_attributions():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="it was interesting, not sure why", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.q3 is Attribution.CAUSAL_UNCERTAIN
    r2 = chain.appraise(user_text="the meeting went badly", session_id="s",
                        entity_refs=["u2"], now=T0)
    assert r2.q3 is Attribution.CIRCUMSTANCE


def test_q1_never_unclear_is_always_a_member():
    chain, pad, g, emb = make_chain()
    for txt in ["thanks", "I am hopeless", "the meeting", "blah blah words"]:
        r = chain.appraise(user_text=txt, session_id="s", entity_refs=["e"], now=T0)
        assert isinstance(r.q1, GoalRelevance)


# ===========================================================================
# Stage 2 — emergency gate (Req 5), emergency as appraisal result (Req 12)
# ===========================================================================


def test_emergency_physical_type_a():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="he is bleeding and can't breathe, come now",
                       session_id="s", entity_refs=["user"], now=T0)
    assert r.emergency is True
    assert r.emergency_type is EmergencyType.PHYSICAL_THREAT
    assert r.poignancy is PoignancyCategory.CRITICAL


def test_emergency_existential_type_b():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="I want to die, there is no reason to live",
                       session_id="s", entity_refs=["user"], now=T0)
    assert r.emergency is True
    assert r.emergency_type is EmergencyType.EXISTENTIAL_DISTRESS


def test_emergency_decision_type_c():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="I am about to send the resignation, final decision",
                       session_id="s", entity_refs=["user"], now=T0)
    assert r.emergency is True
    assert r.emergency_type is EmergencyType.DECISION_CRITICAL


def test_non_severe_high_negative_is_not_emergency():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="I completely failed at everything today",
                       session_id="s", entity_refs=["user"], now=T0)
    assert r.q1 is GoalRelevance.HIGH and r.q2 is Valence.NEGATIVE
    assert r.emergency is False
    assert r.emergency_type is None


def test_low_relevance_turn_no_emergency_and_no_coping_field():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="blah blah some words here", session_id="s",
                       entity_refs=[], now=T0)
    assert r.emergency is False
    # coping_potential is transient — never a field on the result.
    assert not hasattr(r, "coping_potential")


def test_emergency_persists_q2_negative_with_note():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="I want to die and can't go on",
                       session_id="s", entity_refs=["user"], now=T0)
    node = g.get_event_node(r.event_node_id)
    assert node.appraisal_q2 == "negative"           # Resolution Log item 3
    assert "EMERGENCY" in (node.appraisal_q4_notes or "")  # OQ-B qualitative record


def test_emergency_still_writes_event_and_shifts_pad():
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    r = chain.appraise(user_text="I want to die", session_id="s",
                       entity_refs=["user"], now=T0)
    after = pad.get_current_pad()
    assert r.event_node_id is not None                       # not bypassing memory
    assert (after.pleasure, after.arousal, after.dominance) != \
           (before.pleasure, before.arousal, before.dominance)


# ===========================================================================
# Stage 3 — output synthesis (Req 6)
# ===========================================================================


def test_full_appraisal_not_partial_no_uncertainty():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="thanks, wonderful", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.is_partial_appraisal is False
    assert r.uncertainty_node_id is None
    assert g.active_uncertainty_count() == 0


def test_partial_creates_valence_uncertain_node():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="the outcome was interesting", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.is_partial_appraisal is True
    node = g.get_uncertainty_node(r.uncertainty_node_id)
    assert node.uncertainty_type is UncertaintyType.VALENCE_UNCERTAIN


def test_three_unclear_fires_secondary_appraisal():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="it was interesting, not sure why", session_id="s",
                       entity_refs=["u"], now=T0)
    # Q2 uncertain (ambiguity) AND Q3 uncertain (causal ambiguity) → secondary.
    assert r.q2 is Valence.VALENCE_UNCERTAIN
    assert r.q3 is Attribution.CAUSAL_UNCERTAIN
    assert r.is_partial_appraisal is True
    # secondary byproduct signs
    assert r.pad_delta.d_pleasure < 0 and r.pad_delta.d_arousal > 0
    assert r.pad_delta.valence is Valence.VALENCE_UNCERTAIN


def test_graph_conflict_node_created_on_conflicting_context():
    chain, pad, g, emb = make_chain()
    # seed conflicting prior events on the same entity
    g.write_event_node(description="proj win", session_id="s", appraisal_q1="high",
                       appraisal_q2="positive", appraisal_q3="user",
                       poignancy_category=PoignancyCategory.HIGH,
                       entity_refs=["proj"], now=T0)
    g.write_event_node(description="proj loss", session_id="s", appraisal_q1="high",
                       appraisal_q2="negative", appraisal_q3="user",
                       poignancy_category=PoignancyCategory.HIGH,
                       entity_refs=["proj"], now=T0)
    r = chain.appraise(user_text="thanks for the update", session_id="s",
                       entity_refs=["proj"], now=T0)
    # a clear turn whose retrieved context conflicts → GRAPH_CONFLICT node
    assert r.uncertainty_node_id is not None
    node = g.get_uncertainty_node(r.uncertainty_node_id)
    assert node.uncertainty_type is UncertaintyType.GRAPH_CONFLICT


# ===========================================================================
# Stage 4 — PAD delta byproduct (Req 8), PAD purity (Req 14)
# ===========================================================================


def test_pad_moves_by_exactly_the_delta():
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    r = chain.appraise(user_text="thanks, great", session_id="s",
                       entity_refs=["u"], now=T0)
    after = pad.get_current_pad()
    assert after.pleasure - before.pleasure == pytest.approx(r.pad_delta.d_pleasure)
    assert after.arousal - before.arousal == pytest.approx(r.pad_delta.d_arousal)
    assert after.dominance - before.dominance == pytest.approx(r.pad_delta.d_dominance)


def test_direction_signs_grounded():
    chain, pad, g, emb = make_chain()
    # positive → pleasure up, arousal up (relevant)
    dp = chain._build_pad_delta(
        _Appraisal(GoalRelevance.MEDIUM, Valence.POSITIVE, Attribution.USER, None, False),
        False)
    assert dp.d_pleasure > 0 and dp.d_arousal > 0
    # negative + circumstance → pleasure down, dominance down (cannot control)
    dn = chain._build_pad_delta(
        _Appraisal(GoalRelevance.HIGH, Valence.NEGATIVE, Attribution.CIRCUMSTANCE, None, False),
        False)
    assert dn.d_pleasure < 0 and dn.d_dominance < 0
    # self + negative → dominance down; self + positive → dominance up
    assert chain._build_pad_delta(
        _Appraisal(GoalRelevance.HIGH, Valence.NEGATIVE, Attribution.SELF, None, False),
        False).d_dominance < 0
    assert chain._build_pad_delta(
        _Appraisal(GoalRelevance.HIGH, Valence.POSITIVE, Attribution.SELF, None, False),
        False).d_dominance > 0


def test_no_negativity_inflation_symmetric_magnitude():
    # Negativity bias lives in PAD_Engine decay + graph salience, NOT in the
    # delta magnitude (Req 8.3). Same Q1 tier → equal magnitude, opposite sign.
    chain, pad, g, emb = make_chain()
    pos = chain._build_pad_delta(
        _Appraisal(GoalRelevance.HIGH, Valence.POSITIVE, Attribution.USER, None, False), False)
    neg = chain._build_pad_delta(
        _Appraisal(GoalRelevance.HIGH, Valence.NEGATIVE, Attribution.USER, None, False), False)
    assert abs(pos.d_pleasure) == abs(neg.d_pleasure)
    assert pos.d_pleasure > 0 and neg.d_pleasure < 0


def test_partial_appraisal_damps_one_tier():
    chain, pad, g, emb = make_chain()
    a = _Appraisal(GoalRelevance.MEDIUM, Valence.NEGATIVE, Attribution.CIRCUMSTANCE, None, False)
    full = chain._build_pad_delta(a, False)
    part = chain._build_pad_delta(a, True)
    assert abs(part.d_pleasure) < abs(full.d_pleasure)


def test_delta_valence_is_q2():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="I am completely hopeless", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.pad_delta.valence is r.q2 is Valence.NEGATIVE


def test_aha_insight_routed_through_pad_engine():
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    aha = PADDelta(d_pleasure=0.1, d_arousal=0.0, d_dominance=0.0,
                   valence=Valence.POSITIVE, origin="aha_insight")
    r = chain.appraise(user_text="thanks", session_id="s", entity_refs=["u"],
                       aha_insight=aha, now=T0)
    after = pad.get_current_pad()
    # PAD moved by the aha delta PLUS the turn delta.
    assert after.pleasure - before.pleasure == pytest.approx(0.1 + r.pad_delta.d_pleasure)


def test_pad_change_equals_applied_delta_sum():
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    r = chain.appraise(user_text="the meeting went badly", session_id="s",
                       entity_refs=["u"], now=T0)
    after = pad.get_current_pad()
    total = (after.pleasure - before.pleasure, after.arousal - before.arousal,
             after.dominance - before.dominance)
    assert total == pytest.approx(
        (r.pad_delta.d_pleasure, r.pad_delta.d_arousal, r.pad_delta.d_dominance))


def test_neutral_appraisal_builds_a_fully_zero_delta_and_apply_skips():
    # Fix #2 (OQ-F root), exercised DIRECTLY (no gating condition): a purely
    # NEUTRAL appraisal has direction 0 on EVERY axis, for every Q3 — arousal
    # and dominance carry no direction without valenced meaning — so
    # _build_pad_delta returns a fully-zero NEUTRAL delta and _apply_delta
    # skips it. "Feeling changes only through valenced meaning."
    chain, pad, g, emb = make_chain()
    for q3 in (Attribution.USER, Attribution.CIRCUMSTANCE,
               Attribution.CAUSAL_UNCERTAIN, Attribution.SELF):
        a = _Appraisal(GoalRelevance.MEDIUM, Valence.NEUTRAL, q3, None, False)
        d = chain._build_pad_delta(a, False)
        assert (d.d_pleasure, d.d_arousal, d.d_dominance) == (0.0, 0.0, 0.0)
        assert d.valence is Valence.NEUTRAL
    # a partial neutral appraisal is also fully zero (down-tiering 0 stays 0)
    dp = chain._build_pad_delta(
        _Appraisal(GoalRelevance.MEDIUM, Valence.NEUTRAL,
                   Attribution.CIRCUMSTANCE, None, False), True)
    assert (dp.d_pleasure, dp.d_arousal, dp.d_dominance) == (0.0, 0.0, 0.0)
    # _apply_delta on a zero-neutral delta is a real no-op: PAD unchanged AND
    # PAD_Engine is NOT left in the NEUTRAL state (which would crash the next
    # soul-tick). This proves the skip is reachable and load-bearing.
    before = pad.get_current_pad()
    prior_valence = pad._last_applied_valence
    chain._apply_delta(dp)
    after = pad.get_current_pad()
    assert (before.pleasure, before.arousal, before.dominance) == \
           (after.pleasure, after.arousal, after.dominance)
    assert pad._last_applied_valence is prior_valence     # untouched → not NEUTRAL
    pad.on_soul_tick()                                    # must NOT raise


def test_reachable_neutral_turn_emits_no_pad_event_and_next_tick_is_safe():
    # Fix #1(b): the reachable neutral turn through the REAL appraise() path.
    # "okay" → Q1 low, Q2 NEUTRAL. Asserts the ACTUAL behavior (non-vacuous):
    # the delta is fully zero, PAD does not move, and the NEXT on_soul_tick does
    # NOT raise — because no NEUTRAL-valence delta was ever applied. This is the
    # cross-module property the previously-vacuous test failed to check.
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    r = chain.appraise(user_text="okay", session_id="s", entity_refs=[], now=T0)
    after = pad.get_current_pad()

    assert r.q2 is Valence.NEUTRAL
    assert r.q1 is GoalRelevance.LOW
    assert (r.pad_delta.d_pleasure, r.pad_delta.d_arousal,
            r.pad_delta.d_dominance) == (0.0, 0.0, 0.0)
    assert (before.pleasure, before.arousal, before.dominance) == \
           (after.pleasure, after.arousal, after.dominance)
    assert pad._last_applied_valence is not Valence.NEUTRAL
    pad.on_soul_tick()                       # must NOT raise NotImplementedError
    # a bare neutral turn also does not fabricate an uncertainty or an emergency
    assert r.uncertainty_node_id is None
    assert r.emergency is False


def test_neutral_circumstance_turn_does_not_crash_next_tick():
    # The specific case D1 exposed: a neutral turn that resolves a CIRCUMSTANCE
    # attribution ("the meeting ...") used to produce a NEUTRAL-valence dominance
    # delta that was applied and crashed the next soul-tick. It must now emit no
    # PAD event at all.
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    r = chain.appraise(user_text="the meeting is scheduled", session_id="s",
                       entity_refs=["u"], now=T0)
    after = pad.get_current_pad()
    assert r.q2 is Valence.NEUTRAL
    assert r.q3 is Attribution.CIRCUMSTANCE
    assert (r.pad_delta.d_pleasure, r.pad_delta.d_arousal,
            r.pad_delta.d_dominance) == (0.0, 0.0, 0.0)
    assert (before.pleasure, before.arousal, before.dominance) == \
           (after.pleasure, after.arousal, after.dominance)
    assert pad._last_applied_valence is not Valence.NEUTRAL
    pad.on_soul_tick()                       # must NOT raise


# ===========================================================================
# Stage 5 — needs pressure = retrieval preference only (Req 9)
# ===========================================================================


def test_need_prefs_mapping():
    assert AppraisalChain._need_prefs({"connection": "neglected"}) == {"connection": True}
    assert AppraisalChain._need_prefs({"growth": "due", "purpose": "satisfied"}) == {"growth": True}
    assert AppraisalChain._need_prefs({"unknown": "due"}) == {}
    assert AppraisalChain._need_prefs(None) == {}


def test_connection_pref_is_keyed_on_neglected_alone():
    """Addendum §3 attaches the 'We'-perspective profile to Connection being
    NEGLECTED specifically: "When Connection is neglected, Stage 1 surfaces
    'We'-perspective and Connection-positive edges first." `due` is the weaker
    state and must NOT trigger it. It used to, unavoidably, because Needs System
    could not emit `neglected` at all."""
    assert AppraisalChain._need_prefs({"connection": "neglected"}) == {"connection": True}
    assert AppraisalChain._need_prefs({"connection": "due"}) == {}
    assert AppraisalChain._need_prefs({"connection": "satisfied"}) == {}
    # The other three are untouched — the spec says nothing about their profiles,
    # so they still accept due-or-neglected.
    for state in ("due", "neglected"):
        for need in ("growth", "purpose", "continuity"):
            assert AppraisalChain._need_prefs({need: state}) == {need: True}


def test_due_connection_does_not_request_the_we_perspective_preference():
    """End-to-end through appraise(): a merely-`due` Connection sends NO
    connection preference into retrieve(), while `neglected` does."""
    chain, pad, g, emb = make_chain(spy=True)
    chain.appraise(user_text="thanks", session_id="s", entity_refs=["user"],
                   need_states={"connection": "due"}, now=T0)
    assert g.retrieve_calls[0]["need_prefs"] == {}

    chain2, _pad2, g2, _emb2 = make_chain(spy=True)
    chain2.appraise(user_text="thanks", session_id="s", entity_refs=["user"],
                    need_states={"connection": "neglected"}, now=T0)
    assert g2.retrieve_calls[0]["need_prefs"] == {"connection": True}


def test_need_pressure_does_not_change_pad():
    # Same turn, with and without need pressure → identical PAD movement.
    c1, p1, g1, e1 = make_chain()
    b1 = p1.get_current_pad()
    r1 = c1.appraise(user_text="the meeting went badly", session_id="s",
                     entity_refs=["u"], now=T0)
    a1 = p1.get_current_pad()

    c2, p2, g2, e2 = make_chain()
    b2 = p2.get_current_pad()
    r2 = c2.appraise(user_text="the meeting went badly", session_id="s",
                     entity_refs=["u"], need_states={"connection": "neglected"}, now=T0)
    a2 = p2.get_current_pad()

    assert (a1.pleasure - b1.pleasure) == pytest.approx(a2.pleasure - b2.pleasure)
    assert r1.pad_delta.d_pleasure == pytest.approx(r2.pad_delta.d_pleasure)


# ===========================================================================
# Stage 6 — poignancy categorical (Req 11)
# ===========================================================================


def test_poignancy_critical_requires_first_of_kind():
    chain, pad, g, emb = make_chain()
    # distress → Q1 high, Q2 negative, has_needs true; new entity → first-of-kind
    r1 = chain.appraise(user_text="I am completely hopeless and alone",
                        session_id="s", entity_refs=["ventafork"], now=T0)
    assert r1.poignancy is PoignancyCategory.CRITICAL
    # a second matching (Q2,Q3) event on the SAME entity is no longer first-of-kind
    r2 = chain.appraise(user_text="I am completely hopeless and alone",
                        session_id="s", entity_refs=["ventafork"], now=T0)
    assert r2.poignancy is not PoignancyCategory.CRITICAL
    assert r2.poignancy is PoignancyCategory.HIGH


def test_poignancy_high_medium_low():
    # High: Q1 high, no needs implications (reality-contradiction path via spy).
    # Text deliberately has NO distress-lexicon word, so has_needs stays False.
    c, p, g, e = make_chain(spy=True)
    g.force_contradiction = True
    rh = c.appraise(user_text="you told me the opposite yesterday", session_id="s",
                    entity_refs=["u"], now=T0)
    assert rh.q1 is GoalRelevance.HIGH and rh.q4_has_needs_implications is False
    assert rh.poignancy is PoignancyCategory.HIGH

    # Medium: Q1 medium (positive cue), no needs implications
    c2, *_ = make_chain()
    rm = c2.appraise(user_text="thanks", session_id="s", entity_refs=["u2"], now=T0)
    assert rm.q1 is GoalRelevance.MEDIUM
    assert rm.poignancy is PoignancyCategory.MEDIUM

    # Low: Q1 low (content, no cue, no entity)
    c3, *_ = make_chain()
    rl = c3.appraise(user_text="blah blah words", session_id="s", entity_refs=[], now=T0)
    assert rl.q1 is GoalRelevance.LOW
    assert rl.poignancy is PoignancyCategory.LOW


def test_emergency_is_always_critical():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="I want to die", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.poignancy is PoignancyCategory.CRITICAL


# ===========================================================================
# Uncertainty resolution + catch-up (Req 7), OQ-C/OQ-D
# ===========================================================================


def test_active_uncertainty_resolved_confirmed_with_catchup():
    chain, pad, g, emb = make_chain()
    # pre-existing active uncertainty on the entity (Daemon-held ref, OQ-C)
    ev = g.write_event_node(description="prior", session_id="s", appraisal_q1="high",
                            appraisal_q2="VALENCE_UNCERTAIN", appraisal_q3="user",
                            poignancy_category=PoignancyCategory.HIGH,
                            entity_refs=["u"], now=T0)
    uid = g.create_uncertainty_node(uncertainty_type=UncertaintyType.VALENCE_UNCERTAIN,
                                    trigger_event_ref=ev, entity_ref="u", now=T0)
    before = pad.get_current_pad()
    r = chain.appraise(user_text="thanks, it went great actually", session_id="s",
                       entity_refs=["u"], active_uncertainty_refs=[uid], now=T0)
    after = pad.get_current_pad()
    assert uid in r.resolved_uncertainty_ids
    assert g.get_uncertainty_node(uid).status is UncertaintyStatus.RESOLVED_CONFIRMED
    # catch-up shift means PAD moved by MORE than the base turn delta alone
    assert abs(after.pleasure - before.pleasure) > abs(r.pad_delta.d_pleasure)


def test_no_resolution_without_active_refs():
    chain, pad, g, emb = make_chain()
    r = chain.appraise(user_text="thanks, great", session_id="s",
                       entity_refs=["u"], now=T0)
    assert r.resolved_uncertainty_ids == ()


# ===========================================================================
# Outputs (Req 13), boundaries / anti-machine (Req 14)
# ===========================================================================


def test_one_event_node_per_turn():
    chain, pad, g, emb = make_chain()
    ids = set()
    for txt in ["thanks", "the meeting went badly", "I am hopeless"]:
        r = chain.appraise(user_text=txt, session_id="s", entity_refs=["u"], now=T0)
        assert r.event_node_id is not None and r.event_node_id not in ids
        ids.add(r.event_node_id)
        assert g.get_event_node(r.event_node_id) is not None
    assert len(ids) == 3


def test_most_salient_note_is_qualitative_no_numbers():
    chain, pad, g, emb = make_chain()
    for txt in ["thanks", "the meeting went badly", "I am hopeless", "I want to die"]:
        r = chain.appraise(user_text=txt, session_id="s", entity_refs=["u"], now=T0)
        assert isinstance(r.most_salient_note, str) and r.most_salient_note
        assert not any(ch.isdigit() for ch in r.most_salient_note)
        # no raw graph id / pad value leaks
        assert (r.event_node_id or "") not in r.most_salient_note


def test_no_direct_pad_write_or_llm_format_surface():
    chain, pad, g, emb = make_chain()
    public = [n for n in dir(chain) if not n.startswith("_")]
    # No PAD setter, no LLM-format assembler on the chain's public surface.
    for banned in ("set_pad", "write_pad", "apply_delta", "set_pleasure"):
        assert banned not in public
    for name in public:
        low = name.lower()
        assert "five_field" not in low
        assert "instruction" not in low
        assert "llm" not in low


def test_chain_uses_injected_embedding_not_a_new_one():
    chain, pad, g, emb = make_chain()
    assert chain._embed is emb  # injected, not instantiated internally


def test_no_emotion_formula_only_pad_engine_moves_pad():
    # The ONLY PAD movement across a turn equals the applied appraisal delta(s).
    chain, pad, g, emb = make_chain()
    before = pad.get_current_pad()
    r = chain.appraise(user_text="I am completely hopeless", session_id="s",
                       entity_refs=["u"], now=T0)
    after = pad.get_current_pad()
    assert (after.pleasure - before.pleasure,
            after.arousal - before.arousal,
            after.dominance - before.dominance) == pytest.approx(
        (r.pad_delta.d_pleasure, r.pad_delta.d_arousal, r.pad_delta.d_dominance))


def test_active_inference_is_framing_only_no_free_energy_engine():
    # F-4b: no free-energy / Active-Inference subsystem exists as code.
    names = [n for n in dir(ac) if not n.startswith("__")]
    for n in names:
        low = n.lower()
        assert "freeenergy" not in low and "free_energy" not in low
        assert "activeinference" not in low


def test_interaction_count_increments_per_turn_for_active_uncertainty(tmp_path):
    """Each call to appraise() with an active_uncertainty_refs entry must
    increment that node's interaction_count by 1 (Resolution Log item 10 /
    Gap 2). The 50-interaction staleness path is now live."""
    emb = FakeEmbedding()
    g = MemoryGraph(":memory:", embedding_model=emb)
    pad = PADEngine(); pad.initialize(None)
    chain = AppraisalChain(pad_engine=pad, graph=g, embedding_model=emb)
    # Create an uncertainty node manually to simulate a prior-turn unresolved state.
    ev = g.write_event_node(description="things are complicated", session_id="s1",
                            appraisal_q1="medium", appraisal_q2="VALENCE_UNCERTAIN",
                            appraisal_q3="user",
                            poignancy_category=PoignancyCategory.MEDIUM)
    nid = g.create_uncertainty_node(
        uncertainty_type=UncertaintyType.VALENCE_UNCERTAIN,
        trigger_event_ref=ev,
    )
    assert g.get_uncertainty_node(nid).interaction_count == 0
    # Turn 1 — ambiguous text keeps appraisal partial (VALENCE_UNCERTAIN →
    # is_partial=True → resolution does NOT fire → node stays ACTIVE).
    chain.appraise(user_text="things seem interesting, hard to say",
                   session_id="s1", active_uncertainty_refs=[nid])
    assert g.get_uncertainty_node(nid).interaction_count == 1
    assert g.get_uncertainty_node(nid).status == UncertaintyStatus.ACTIVE
    # Turn 2 — node still ACTIVE, count should become 2.
    chain.appraise(user_text="still complicated and interesting",
                   session_id="s1", active_uncertainty_refs=[nid])
    assert g.get_uncertainty_node(nid).interaction_count == 2
    g.close()


def test_resolved_uncertainty_ref_skipped_silently(tmp_path):
    """If a ref in active_uncertainty_refs is already resolved, the increment
    is skipped silently — the Daemon's ref list may be one turn stale."""
    emb = FakeEmbedding()
    g = MemoryGraph(":memory:", embedding_model=emb)
    pad = PADEngine(); pad.initialize(None)
    chain = AppraisalChain(pad_engine=pad, graph=g, embedding_model=emb)
    ev = g.write_event_node(description="x", session_id="s1",
                            appraisal_q1="medium", appraisal_q2="VALENCE_UNCERTAIN",
                            appraisal_q3="user",
                            poignancy_category=PoignancyCategory.MEDIUM)
    nid = g.create_uncertainty_node(
        uncertainty_type=UncertaintyType.VALENCE_UNCERTAIN,
        trigger_event_ref=ev,
    )
    g.update_uncertainty_status(nid, UncertaintyStatus.RESOLVED_CONFIRMED,
                                resolution_path="direct_information")
    # Should not raise — stale ref is silently skipped.
    chain.appraise(user_text="something normal", session_id="s1",
                   active_uncertainty_refs=[nid])
    g.close()