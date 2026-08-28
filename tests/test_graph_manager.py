"""Unit tests for daemon/graph_manager.py — Module 3 (Memory Graph).

Covers tasks.md Tasks 2–22: enums, node/edge dataclasses, SQLite schema +
init guard, write_event_node + salience floors, adjust_salience + base
immutability, lazy precision decay (transitions/resistance-vs-base_salience/
multi-step), uncertainty lifecycle (max-5 cap + protected + staleness),
edges (connection/aha/tension + resolved 3×), emotion crystallization
(critical-only), relationship_summary single path, relational_stage
accept-only, embedding similarity, retrieve (mood-congruence + need-preference
+ size + touch), qualifying-evidence queries, is_first_of_kind /
resolved_edge_exists / reality_contradiction_check, and boundary API-surface
guarantees.

Flagged Open Questions are deliberately NOT pinned to a value by these tests
(retrieval precedence OQ4, habituation rate OQ1, decay-threshold semantics OQ5
beyond total-elapsed) — per design.md, tests must not silently encode an
un-approved resolution. Medium/low base_salience is no longer among them: ResLog
item 9 says "no floor" outright, and the tests now assert exactly that.

No hypothesis dependency: "property" checks use representative hand-picked
inputs, matching Module 1's plain-pytest style.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

import daemon.graph_manager as gm
from daemon.graph_manager import (
    EdgeType,
    Edge,
    EmotionNode,
    EntityNode,
    EventNode,
    MemoryGraph,
    NodeType,
    Perspective,
    PoignancyCategory,
    Precision,
    RelationalStage,
    UncertaintyNode,
    UncertaintyStatus,
    UncertaintyType,
    NEGATIVE_SALIENCE_BONUS,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class FakeEmbedding:
    """Deterministic injected embedding model. Explicit vectors via `table`;
    otherwise a simple char-bucket vector."""

    def __init__(self, table=None):
        self.table = table or {}

    def embed(self, text):
        if text in self.table:
            return self.table[text]
        v = [0.0] * 8
        for ch in text:
            v[ord(ch) % 8] += 1.0
        return v


def make_graph(table=None):
    return MemoryGraph(":memory:", embedding_model=FakeEmbedding(table))


def add_event(mg, **kw):
    defaults = dict(
        description="d", session_id="s", appraisal_q1="high",
        appraisal_q2="neutral", appraisal_q3="user",
        poignancy_category=PoignancyCategory.MEDIUM, now=T0,
    )
    defaults.update(kw)
    return mg.write_event_node(**defaults)


# ===========================================================================
# Task 2 — enums
# ===========================================================================


def test_enum_members_exact():
    assert [e.value for e in NodeType] == ["event", "entity", "emotion", "uncertainty"]
    assert [e.value for e in Precision] == ["vivid", "present", "softened", "faded"]
    assert [e.value for e in PoignancyCategory] == ["critical", "high", "medium", "low"]
    assert [e.value for e in Perspective] == ["I-Now", "User-Now", "We"]
    assert [e.value for e in RelationalStage] == [
        "observing", "engaging", "invested", "bonded"]
    assert [e.value for e in UncertaintyType] == [
        "INPUT_UNCERTAIN", "VALENCE_UNCERTAIN", "CAUSAL_UNCERTAIN", "GRAPH_CONFLICT"]
    assert [e.value for e in UncertaintyStatus] == [
        "ACTIVE", "RESOLVED_CONFIRMED", "RESOLVED_INFERRED", "ABANDONED"]
    assert [e.value for e in EdgeType] == [
        "triggered", "caused", "relates_to", "resolved",
        "contradicts", "connects", "crystallized_into"]


def test_no_trust_score_enum_anywhere():
    # trust_score is removed (Addendum §2) — RelationalStage replaces it.
    all_values = []
    for enum in (NodeType, Precision, PoignancyCategory, Perspective,
                 RelationalStage, UncertaintyType, UncertaintyStatus, EdgeType):
        all_values += [e.value for e in enum]
    assert not any("trust" in v.lower() for v in all_values)


# ===========================================================================
# Task 3 — dataclasses
# ===========================================================================


def test_entity_node_has_relational_stage_no_trust_score():
    fields = EntityNode.__dataclass_fields__
    assert "relational_stage" in fields
    assert "trust_score" not in fields


def test_node_type_defaults():
    assert EventNode.__dataclass_fields__["node_type"].default == NodeType.EVENT
    assert EntityNode.__dataclass_fields__["node_type"].default == NodeType.ENTITY


# ===========================================================================
# Task 4 — SQLite schema round-trip + column checks
# ===========================================================================


def test_entity_schema_columns():
    mg = make_graph()
    cols = [r[1] for r in mg._conn.execute("PRAGMA table_info(entity_nodes)")]
    assert "relational_stage" in cols
    assert "trust_score" not in cols


def test_event_node_roundtrip():
    mg = make_graph()
    nid = add_event(mg, description="hello", appraisal_q2="negative",
                    poignancy_category=PoignancyCategory.HIGH,
                    entity_refs=["e1", "e2"])
    n = mg.get_event_node(nid)
    assert n.description == "hello"
    assert n.appraisal_q2 == "negative"
    assert n.poignancy_category == PoignancyCategory.HIGH
    assert n.entity_refs == ["e1", "e2"]
    assert n.precision == Precision.VIVID


def test_edge_roundtrip_all_fields():
    mg = make_graph()
    eid = mg.write_edge(from_node="a", to_node="b", edge_type=EdgeType.CONNECTS,
                        valence=0.5, arousal=0.2, dominance=0.1,
                        base_salience=0.4, is_aha_edge=True,
                        perspective=Perspective.WE, now=T0)
    e = mg.get_edge(eid)
    assert e.edge_type == EdgeType.CONNECTS
    assert e.is_aha_edge is True
    assert e.perspective == Perspective.WE
    assert e.valence == 0.5


# ===========================================================================
# Task 5 — pre-init guard
# ===========================================================================


def test_pre_init_guard_raises():
    mg = make_graph()
    mg._ready = False  # simulate un-wired store
    with pytest.raises(RuntimeError):
        mg.get_relational_stage("x")
    with pytest.raises(RuntimeError):
        mg.retrieve(pad_pleasure_sign=1)


# ===========================================================================
# Task 6 — base_salience floors
# ===========================================================================


def test_base_salience_critical_floor():
    mg = make_graph()
    n = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.CRITICAL,
                                    appraisal_q2="neutral"))
    assert n.base_salience >= 0.85
    assert n.salience == n.base_salience  # initial salience == base


def test_base_salience_high_floor():
    mg = make_graph()
    n = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.HIGH,
                                    appraisal_q2="neutral"))
    assert n.base_salience >= 0.55
    assert n.base_salience < 0.85  # high floor, not critical


def test_negative_bonus_stacks_on_floor():
    mg = make_graph()
    pos = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.HIGH,
                                      appraisal_q2="positive"))
    neg = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.HIGH,
                                      appraisal_q2="negative"))
    assert neg.base_salience == pytest.approx(pos.base_salience + NEGATIVE_SALIENCE_BONUS)
    assert neg.base_salience == pytest.approx(0.55 + 0.15)


def test_medium_low_have_no_base_salience_floor():
    # Resolution Log item 9: "Medium/Low → no floor, decays/discards as already
    # locked." No floor means no floor — not a placeholder magnitude. Both tiers
    # start at 0.0 for a non-negative event.
    mg = make_graph()
    med = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.MEDIUM,
                                      appraisal_q2="neutral"))
    low = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.LOW,
                                      appraisal_q2="neutral"))
    assert med.base_salience == pytest.approx(0.0)
    assert low.base_salience == pytest.approx(0.0)
    assert med.salience == pytest.approx(0.0)  # initial salience == base
    # No floor constant survives for medium/low.
    assert not hasattr(gm, "_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER")
    assert PoignancyCategory.MEDIUM not in gm.POIGNANCY_SALIENCE_FLOOR
    assert PoignancyCategory.LOW not in gm.POIGNANCY_SALIENCE_FLOOR


def test_negative_bonus_stacks_on_absent_medium_low_floor():
    # Item 9: the +0.15 bonus stacks "on top of whichever floor applies" — for
    # medium/low the floor is nothing, so the bonus is the whole base.
    mg = make_graph()
    med_neg = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.MEDIUM,
                                         appraisal_q2="negative"))
    low_neg = mg.get_event_node(add_event(mg, poignancy_category=PoignancyCategory.LOW,
                                         appraisal_q2="negative"))
    assert med_neg.base_salience == pytest.approx(NEGATIVE_SALIENCE_BONUS)
    assert low_neg.base_salience == pytest.approx(NEGATIVE_SALIENCE_BONUS)


def test_medium_low_decay_naturally_while_critical_high_resist():
    # The behavioural consequence of "no floor": medium/low nodes walk the full
    # forgetting path on the same elapsed time that critical/high resist.
    mg = make_graph()
    med = add_event(mg, poignancy_category=PoignancyCategory.MEDIUM)
    low = add_event(mg, poignancy_category=PoignancyCategory.LOW)
    crit = add_event(mg, poignancy_category=PoignancyCategory.CRITICAL)
    high = add_event(mg, poignancy_category=PoignancyCategory.HIGH)
    later = T0 + timedelta(days=65)
    for nid in (med, low, crit, high):
        mg._touch_event_node(mg.get_event_node(nid), later)
    # no floor → decays/discards: all the way to faded
    assert mg.get_event_node(med).precision == Precision.FADED
    assert mg.get_event_node(low).precision == Precision.FADED
    # floors hold: critical stays word-for-word, high settles at the gist
    assert mg.get_event_node(crit).precision == Precision.VIVID
    assert mg.get_event_node(high).precision == Precision.PRESENT
    # a medium node decays sooner than the high node's resisted stopping point
    med2 = add_event(mg, poignancy_category=PoignancyCategory.MEDIUM)
    high2 = add_event(mg, poignancy_category=PoignancyCategory.HIGH)
    mid = T0 + timedelta(days=20)
    mg._touch_event_node(mg.get_event_node(med2), mid)
    mg._touch_event_node(mg.get_event_node(high2), mid)
    assert mg.get_event_node(med2).precision == Precision.SOFTENED
    assert mg.get_event_node(high2).precision == Precision.PRESENT


# ===========================================================================
# Task 7 — adjust_salience + base immutability
# ===========================================================================


def test_adjust_salience_leaves_base_unchanged():
    mg = make_graph()
    nid = add_event(mg, poignancy_category=PoignancyCategory.CRITICAL)
    base_before = mg.get_event_node(nid).base_salience
    mg.adjust_salience(nid, 0.1)
    mg.adjust_salience(nid, 0.9)
    after = mg.get_event_node(nid)
    assert after.salience == pytest.approx(0.9)
    assert after.base_salience == pytest.approx(base_before)  # never decays


def test_adjust_salience_on_edge():
    mg = make_graph()
    eid = mg.write_edge(from_node="a", to_node="b", edge_type=EdgeType.CONNECTS,
                        base_salience=0.4, now=T0)
    mg.adjust_salience(eid, 0.2)
    assert mg.get_edge(eid).salience == pytest.approx(0.2)
    assert mg.get_edge(eid).base_salience == pytest.approx(0.4)


# ===========================================================================
# Task 8 — lazy precision decay (pure logic + touch integration)
# ===========================================================================


def test_precision_critical_never_leaves_vivid():
    mg = make_graph()
    # base 0.85 > 0.8 → vivid→present resisted, even after a huge gap
    assert mg._target_precision(Precision.VIVID, timedelta(days=365), 0.85) == Precision.VIVID


def test_precision_high_settles_at_present():
    mg = make_graph()
    # 0.55: vivid→present allowed (not >0.8), present→softened resisted (>0.5)
    assert mg._target_precision(Precision.VIVID, timedelta(hours=100), 0.55) == Precision.PRESENT
    assert mg._target_precision(Precision.VIVID, timedelta(days=30), 0.55) == Precision.PRESENT


def test_precision_low_multistep_catchup():
    mg = make_graph()
    # base 0.2: after 65d untouched → vivid→present→softened→faded in one pass
    assert mg._target_precision(Precision.VIVID, timedelta(days=65), 0.2) == Precision.FADED
    # 20d → softened (present→softened at 14d ok; softened→faded 60d not met)
    assert mg._target_precision(Precision.VIVID, timedelta(days=20), 0.2) == Precision.SOFTENED


def test_precision_no_advance_before_threshold():
    mg = make_graph()
    assert mg._target_precision(Precision.VIVID, timedelta(hours=1), 0.2) == Precision.VIVID


def test_precision_never_regresses():
    mg = make_graph()
    # starting SOFTENED, small elapsed → stays softened (never back to vivid)
    assert mg._target_precision(Precision.SOFTENED, timedelta(hours=1), 0.2) == Precision.SOFTENED


def test_touch_resets_timer_and_frequent_retrieval_stays_vivid():
    mg = make_graph()
    nid = add_event(mg, poignancy_category=PoignancyCategory.LOW)
    n = mg.get_event_node(nid)
    # retrieved 1h after creation → still vivid; timer resets
    mg._touch_event_node(n, T0 + timedelta(hours=1))
    n2 = mg.get_event_node(nid)
    assert n2.precision == Precision.VIVID
    assert n2.access_count == 1
    assert gm._parse_dt(n2.last_accessed) == T0 + timedelta(hours=1)


def test_faded_node_not_deleted():
    mg = make_graph()
    nid = add_event(mg, poignancy_category=PoignancyCategory.LOW)
    n = mg.get_event_node(nid)
    mg._touch_event_node(n, T0 + timedelta(days=100))  # would fade
    n2 = mg.get_event_node(nid)
    assert n2 is not None  # never deleted (Req 4.5)
    assert n2.precision == Precision.FADED


# ===========================================================================
# Task 9 — uncertainty cap
# ===========================================================================


def _mk_unc(mg, utype, created):
    return mg.create_uncertainty_node(
        uncertainty_type=utype, trigger_event_ref="ev", created=created, now=created)


def test_uncertainty_cap_evicts_oldest_graph_conflict():
    mg = make_graph()
    ids = []
    # 5 GRAPH_CONFLICT nodes, oldest first
    for i in range(5):
        ids.append(_mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0 + timedelta(minutes=i)))
    assert mg.active_uncertainty_count() == 5
    # 6th creation → oldest GRAPH_CONFLICT abandoned
    _mk_unc(mg, UncertaintyType.CAUSAL_UNCERTAIN, T0 + timedelta(minutes=10))
    assert mg.active_uncertainty_count() == 5
    assert mg.get_uncertainty_node(ids[0]).status == UncertaintyStatus.ABANDONED


def test_uncertainty_cap_never_abandons_protected():
    mg = make_graph()
    prot = _mk_unc(mg, UncertaintyType.INPUT_UNCERTAIN, T0)
    _mk_unc(mg, UncertaintyType.VALENCE_UNCERTAIN, T0 + timedelta(minutes=1))
    gc = [_mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0 + timedelta(minutes=2 + i))
          for i in range(3)]
    # now 5 active (2 protected + 3 GC); 6th → evict oldest GC, protected safe
    _mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0 + timedelta(minutes=20))
    assert mg.get_uncertainty_node(prot).status == UncertaintyStatus.ACTIVE
    assert mg.get_uncertainty_node(gc[0]).status == UncertaintyStatus.ABANDONED


def test_uncertainty_protected_flag_set():
    mg = make_graph()
    p = mg.get_uncertainty_node(_mk_unc(mg, UncertaintyType.VALENCE_UNCERTAIN, T0))
    assert p.is_protected is True
    c = mg.get_uncertainty_node(_mk_unc(mg, UncertaintyType.CAUSAL_UNCERTAIN, T0))
    assert c.is_protected is False


def _fill_to_capacity_with_no_evictable(mg):
    """Five active nodes, none of them GRAPH_CONFLICT, so nothing may be evicted."""
    _mk_unc(mg, UncertaintyType.INPUT_UNCERTAIN, T0)
    _mk_unc(mg, UncertaintyType.VALENCE_UNCERTAIN, T0 + timedelta(minutes=1))
    for i in range(3):
        _mk_unc(mg, UncertaintyType.CAUSAL_UNCERTAIN, T0 + timedelta(minutes=2 + i))


def test_uncertainty_ceiling_declines_the_new_node_instead_of_raising():
    """2026-08-26 architect ruling. This used to raise `RuntimeError`, which
    killed the turn — a traceback mid-conversation because she was already holding
    five things. Now no node forms and the turn proceeds.

    This is what the code itself had flagged as probably right: "a new uncertainty
    simply does not FORM when she is already at her limit — a real cognitive
    ceiling — rather than raising"."""
    mg = make_graph()
    _fill_to_capacity_with_no_evictable(mg)
    result = _mk_unc(mg, UncertaintyType.CAUSAL_UNCERTAIN, T0 + timedelta(minutes=30))
    assert result is None


def test_the_ceiling_is_not_an_eviction_policy():
    """The load-bearing half. The architect explicitly refused
    eviction-of-a-protected-node, so the ceiling must decline the NEW question and
    leave everything she is already carrying untouched. Quietly discarding one of
    those is the invention that was rejected."""
    mg = make_graph()
    _fill_to_capacity_with_no_evictable(mg)
    before = {r["node_id"] for r in mg._active_uncertainty_rows()}

    _mk_unc(mg, UncertaintyType.CAUSAL_UNCERTAIN, T0 + timedelta(minutes=30))

    after = {r["node_id"] for r in mg._active_uncertainty_rows()}
    assert after == before          # nothing evicted, nothing added
    assert len(after) == 5          # v4 line 1313's max is unchanged


def test_at_uncertainty_capacity_reports_without_consuming():
    """The signal behind the at-capacity behaviour. DERIVED from current rows, so
    asking twice gives the same answer — a stored flag would be read once and then
    destroy the condition it reported."""
    mg = make_graph()
    assert mg.at_uncertainty_capacity() is False
    _fill_to_capacity_with_no_evictable(mg)
    assert mg.at_uncertainty_capacity() is True
    assert mg.at_uncertainty_capacity() is True


def test_not_at_capacity_when_something_is_evictable():
    """Non-vacuous: five active nodes alone is not the ceiling. The ceiling is five
    AND nothing evictable — a GRAPH_CONFLICT node can still be taken, so a sixth
    question is holdable."""
    mg = make_graph()
    for i in range(5):
        _mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0 + timedelta(minutes=i))
    assert mg.at_uncertainty_capacity() is False
    assert _mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0 + timedelta(minutes=30))


# ===========================================================================
# Task 10 — update_uncertainty_status
# ===========================================================================


def test_resolution_stores_catchup_fields():
    mg = make_graph()
    uid = _mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0)
    mg.update_uncertainty_status(
        uid, UncertaintyStatus.RESOLVED_CONFIRMED,
        resolution_path="direct_information",
        catch_up_delta_p=-0.1, catch_up_magnitude_factor=0.50, now=T0)
    n = mg.get_uncertainty_node(uid)
    assert n.status == UncertaintyStatus.RESOLVED_CONFIRMED
    assert n.catch_up_delta_p == pytest.approx(-0.1)
    assert n.catch_up_magnitude_factor == pytest.approx(0.50)
    assert n.resolved is not None


def test_no_auto_abandon_on_staleness():
    # Memory Graph does NOT evaluate the 7d/50-interaction threshold (Req 3.3).
    mg = make_graph()
    uid = mg.create_uncertainty_node(
        uncertainty_type=UncertaintyType.GRAPH_CONFLICT, trigger_event_ref="e",
        interaction_count=999, created=T0 - timedelta(days=30), now=T0)
    # stays ACTIVE despite being "stale" — only an explicit write abandons it
    assert mg.get_uncertainty_node(uid).status == UncertaintyStatus.ACTIVE
    mg.update_uncertainty_status(uid, UncertaintyStatus.ABANDONED,
                                 resolution_path="staleness", now=T0)
    assert mg.get_uncertainty_node(uid).status == UncertaintyStatus.ABANDONED


# ===========================================================================
# Tasks 11–12 — edges
# ===========================================================================


def test_tension_pair_edges():
    mg = make_graph()
    e1 = mg.write_edge(from_node="a", to_node="b", edge_type=EdgeType.RELATES_TO,
                       is_tension_pair=True, now=T0)
    e2 = mg.write_edge(from_node="a", to_node="c", edge_type=EdgeType.RELATES_TO,
                       is_tension_pair=True, tension_partner_edge=e1, now=T0)
    assert mg.get_edge(e2).is_tension_pair is True
    assert mg.get_edge(e2).tension_partner_edge == e1


def test_resolved_edge_3x_salience():
    mg = make_graph()
    plain = mg.write_edge(from_node="close", to_node="open",
                          edge_type=EdgeType.RELATES_TO, base_salience=0.3, now=T0)
    resolved = mg.write_edge(from_node="close", to_node="open",
                             edge_type=EdgeType.RESOLVED, base_salience=0.3, now=T0)
    assert mg.get_edge(resolved).salience == pytest.approx(3.0 * 0.3)
    assert mg.get_edge(plain).salience == pytest.approx(0.3)
    # base_salience itself is unchanged (only the fluctuating salience is 3×)
    assert mg.get_edge(resolved).base_salience == pytest.approx(0.3)


# ===========================================================================
# Task 13 — emotion crystallization (critical-only)
# ===========================================================================


def test_emotion_crystallizes_at_critical():
    mg = make_graph()
    eid = mg.crystallize_emotion_node(emotion_label="grief", pad_p=0.1, pad_a=0.8,
                                      pad_d=0.2, trigger_event_ref="ev", now=T0)
    assert mg.get_emotion_node(eid).poignancy_category == PoignancyCategory.CRITICAL


def test_emotion_rejects_non_critical():
    mg = make_graph()
    with pytest.raises(ValueError):
        mg.crystallize_emotion_node(emotion_label="mild", pad_p=0.5, pad_a=0.4,
                                    pad_d=0.5, trigger_event_ref="ev",
                                    poignancy_category=PoignancyCategory.HIGH, now=T0)


# ===========================================================================
# Task 14 — relationship_summary single path (incl. self-referential node)
# ===========================================================================


def test_relationship_summary_single_path_incl_self():
    mg = make_graph()
    self_id = mg.write_entity_node(entity_type="person", name="Aria", now=T0)
    other_id = mg.write_entity_node(entity_type="person", name="User", now=T0)
    # same method for both — no self-model-specific method exists
    mg.update_relationship_summary(self_id, "who I am becoming")
    mg.update_relationship_summary(other_id, "context about user")
    assert mg.get_entity_node(self_id).relationship_summary == "who I am becoming"
    assert mg.get_entity_node(other_id).relationship_summary == "context about user"
    assert not hasattr(mg, "write_self_model")
    assert not hasattr(mg, "update_self_model")


# ===========================================================================
# Task 15 — relational_stage accept-only
# ===========================================================================


def test_relational_stage_set_get_roundtrip():
    mg = make_graph()
    eid = mg.write_entity_node(entity_type="person", name="User", now=T0)
    assert mg.get_relational_stage(eid) is None
    mg.set_relational_stage(eid, RelationalStage.INVESTED)
    assert mg.get_relational_stage(eid) == RelationalStage.INVESTED
    # one-step regression accepted (DMN decides; graph just persists)
    mg.set_relational_stage(eid, RelationalStage.ENGAGING)
    assert mg.get_relational_stage(eid) == RelationalStage.ENGAGING


def test_no_gate_evaluation_method():
    # Memory Graph stores the field; DMN evaluates transitions (Req 7.5).
    method_names = [m for m in dir(MemoryGraph) if not m.startswith("_")]
    for banned in ("evaluate_relational_stage", "advance_relational_stage",
                   "evaluate_gate", "compute_relational_stage"):
        assert banned not in method_names


# ===========================================================================
# Task 16 — embedding similarity ranking
# ===========================================================================


def test_similarity_rank_orders_by_cosine():
    tbl = {
        "near": [1.0, 0.0, 0.0, 0, 0, 0, 0, 0],
        "far": [0.0, 1.0, 0.0, 0, 0, 0, 0, 0],
        "query": [0.9, 0.1, 0.0, 0, 0, 0, 0, 0],
    }
    mg = make_graph(tbl)
    near_id = add_event(mg, description="near")
    far_id = add_event(mg, description="far")
    ranked = mg._similarity_rank(tbl["query"])
    assert ranked[0][0] == near_id
    assert ranked[-1][0] == far_id


# ===========================================================================
# Tasks 17–18 — retrieve (mood-congruence, size, touch)
# ===========================================================================


def test_retrieve_caps_at_five():
    mg = make_graph()
    for i in range(8):
        add_event(mg, description=f"n{i}", entity_refs=["E"])
    results = mg.retrieve(pad_pleasure_sign=1, entity_refs=["E"], now=T0)
    assert len(results) <= 5


def test_retrieve_mood_congruence_orders_matching_sign_first():
    tbl = {"q": [1.0, 0, 0, 0, 0, 0, 0, 0], "anchor": [1.0, 0, 0, 0, 0, 0, 0, 0]}
    mg = make_graph(tbl)
    a = add_event(mg, description="anchor", appraisal_q2="neutral", entity_refs=["E"])
    # edges incident to the anchor node with known valence signs
    mg.write_edge(from_node=a, to_node="x", edge_type=EdgeType.CONNECTS,
                  valence=0.7, now=T0)   # + matches pleasure sign +1
    mg.write_edge(from_node=a, to_node="y", edge_type=EdgeType.CONNECTS,
                  valence=0.6, now=T0)   # +
    mg.write_edge(from_node=a, to_node="z", edge_type=EdgeType.CONNECTS,
                  valence=-0.8, now=T0)  # - opposite
    results = mg.retrieve(pad_pleasure_sign=1, query_embedding=tbl["q"], now=T0)
    edges = [r for r in results if isinstance(r, Edge)]
    signs = [(1 if e.valence > 0 else -1) for e in edges]
    # all matching-sign (+) edges appear before the opposite (-) edge
    assert signs, "expected edges in results"
    last_pos = max((i for i, s in enumerate(signs) if s == 1), default=-1)
    first_neg = next((i for i, s in enumerate(signs) if s == -1), len(signs))
    assert last_pos < first_neg


def test_retrieve_touches_returned_nodes():
    tbl = {"q": [1.0, 0, 0, 0, 0, 0, 0, 0], "anchor": [1.0, 0, 0, 0, 0, 0, 0, 0]}
    mg = make_graph(tbl)
    a = add_event(mg, description="anchor")
    later = T0 + timedelta(hours=2)
    mg.retrieve(pad_pleasure_sign=0, query_embedding=tbl["q"], now=later)
    n = mg.get_event_node(a)
    assert n.access_count == 1
    assert gm._parse_dt(n.last_accessed) == later


def test_retrieve_no_coefficient_is_hard_partition():
    # Req 6.5 / OQ4: mood-congruence is a PREFERENCE, not a weighted score.
    # With equal-similarity edges (all incident to the same anchor node),
    # valence-sign must act as a HARD PARTITION — every matching-sign edge
    # precedes every non-matching one, even when created interleaved. A numeric
    # coefficient blend would not guarantee a clean partition.
    tbl = {"q": [1.0, 0, 0, 0, 0, 0, 0, 0], "anchor": [1.0, 0, 0, 0, 0, 0, 0, 0]}
    mg = make_graph(tbl)
    a = add_event(mg, description="anchor", appraisal_q2="neutral")
    interleaved = [0.5, -0.5, 0.4, -0.4, 0.3, -0.3]  # +,-,+,-,+,- at creation
    for i, v in enumerate(interleaved):
        mg.write_edge(from_node=a, to_node=f"n{i}", edge_type=EdgeType.CONNECTS,
                      valence=v, now=T0)
    results = mg.retrieve(pad_pleasure_sign=1, query_embedding=tbl["q"], now=T0)
    signs = [(1 if e.valence > 0 else -1) for e in results if isinstance(e, Edge)]
    assert 1 in signs and -1 in signs
    # strict partition: no negative appears before any positive
    assert signs == sorted(signs, reverse=True)


# ===========================================================================
# Task 19 — qualifying-evidence queries (structural; no need state)
# ===========================================================================


def test_connection_evidence_window():
    mg = make_graph()
    add_event(mg, appraisal_q1="high", timestamp=T0 - timedelta(hours=1))
    assert mg.connection_evidence(now=T0) is True
    mg2 = make_graph()
    add_event(mg2, appraisal_q1="high", timestamp=T0 - timedelta(hours=100))
    assert mg2.connection_evidence(now=T0) is False  # outside 72h
    mg3 = make_graph()
    add_event(mg3, appraisal_q1="low", timestamp=T0 - timedelta(hours=1))
    assert mg3.connection_evidence(now=T0) is False  # q1 below medium


def test_growth_evidence_window():
    mg = make_graph()
    uid = _mk_unc(mg, UncertaintyType.GRAPH_CONFLICT, T0 - timedelta(days=1))
    mg.update_uncertainty_status(uid, UncertaintyStatus.RESOLVED_INFERRED,
                                 resolved=T0 - timedelta(hours=2), now=T0)
    assert mg.growth_evidence(now=T0) is True
    # abandoned does not count as growth
    mg2 = make_graph()
    uid2 = _mk_unc(mg2, UncertaintyType.GRAPH_CONFLICT, T0 - timedelta(days=1))
    mg2.update_uncertainty_status(uid2, UncertaintyStatus.ABANDONED,
                                  resolved=T0 - timedelta(hours=2), now=T0)
    assert mg2.growth_evidence(now=T0) is False


def test_purpose_evidence_half_a_explicit_positive_feedback_about_her():
    """OQ6 resolved 2026-08-26, Addendum §3 half (a). `q3='self'` is ARIA as the
    cause: Q3's self-cues are second-person ("you helped", "because of you") and
    `_dominance_dir` reads SELF+POSITIVE as "agency affirmed"."""
    mg = make_graph()
    add_event(mg, appraisal_q1="none", appraisal_q2="positive",
              appraisal_q3="self", timestamp=T0 - timedelta(days=1))
    assert mg.purpose_evidence(now=T0) is True


def test_purpose_no_longer_satisfied_by_any_positive_turn():
    """THE DEFECT THIS CLOSED, pinned. The old stand-in was "any positive-valence
    EventNode in-window", so one cheerful remark met Purpose — a need meaning "she
    had a positive effect on his life" instead meant "the fortnight contained a
    good moment". False positives are the quiet failure: Purpose read healthy, so
    it never shaped retrieval and never raised an initiative."""
    mg = make_graph()
    add_event(mg, appraisal_q1="none", appraisal_q2="positive",
              appraisal_q3="user", timestamp=T0 - timedelta(days=1))
    assert mg.purpose_evidence(now=T0) is False


def test_purpose_evidence_half_b_follow_through_across_sessions():
    """Half (b): an in-window turn returning to a SUBSTANTIVE topic from an
    EARLIER session. Entity-ref overlap is DMN's existing categorical
    topic-continuation test; `q1 in (medium, high)` is `connection_evidence`'s
    existing substantiveness signal."""
    mg = make_graph()
    thesis = mg.write_entity_node(entity_type="concept", name="thesis")
    add_event(mg, session_id="s1", appraisal_q1="high", appraisal_q2="neutral",
              entity_refs=[thesis], timestamp=T0 - timedelta(days=6))
    add_event(mg, session_id="s2", appraisal_q1="low", appraisal_q2="neutral",
              entity_refs=[thesis], timestamp=T0 - timedelta(days=1))
    assert mg.purpose_evidence(now=T0) is True


def test_purpose_follow_through_needs_a_LATER_session_not_the_same_one():
    """The session boundary is what makes it FOLLOW-through rather than
    still-talking-about-it: returning to a subject in a later session is the
    return; mentioning it twice in one sitting is one conversation."""
    mg = make_graph()
    thesis = mg.write_entity_node(entity_type="concept", name="thesis")
    add_event(mg, session_id="s1", appraisal_q1="high", appraisal_q2="neutral",
              entity_refs=[thesis], timestamp=T0 - timedelta(days=1, hours=2))
    add_event(mg, session_id="s1", appraisal_q1="low", appraisal_q2="neutral",
              entity_refs=[thesis], timestamp=T0 - timedelta(days=1))
    assert mg.purpose_evidence(now=T0) is False


def test_purpose_follow_through_needs_the_earlier_turn_to_be_substantive():
    """§3 says "something SUBSTANTIVE Aria helped with". A low-relevance earlier
    mention is not something she helped with."""
    mg = make_graph()
    thesis = mg.write_entity_node(entity_type="concept", name="thesis")
    add_event(mg, session_id="s1", appraisal_q1="low", appraisal_q2="neutral",
              entity_refs=[thesis], timestamp=T0 - timedelta(days=6))
    add_event(mg, session_id="s2", appraisal_q1="low", appraisal_q2="neutral",
              entity_refs=[thesis], timestamp=T0 - timedelta(days=1))
    assert mg.purpose_evidence(now=T0) is False


def test_purpose_evidence_respects_the_locked_window():
    """WINDOW_PURPOSE (14d, item 7) is untouched — only the predicate changed."""
    mg = make_graph()
    add_event(mg, appraisal_q1="none", appraisal_q2="positive",
              appraisal_q3="self", timestamp=T0 - timedelta(days=20))
    assert mg.purpose_evidence(now=T0) is False
    assert mg.purpose_evidence(now=T0, window=timedelta(days=30)) is True


def test_continuity_evidence_measures_extension_recency_not_age():
    # Guards D1: continuity must key off WHEN the narrative was extended, not
    # entity creation age. Entity created 90d ago, narrative extended NOW.
    mg = make_graph()
    old_self = mg.write_entity_node(entity_type="person", name="Aria",
                                    now=T0 - timedelta(days=90))
    mg.update_relationship_summary(old_self, "extended narrative", now=T0)
    assert mg.continuity_evidence(old_self, now=T0) is True  # recent extension
    # Entity also 90d old, but narrative last extended 90d ago → gapped.
    mg2 = make_graph()
    stale_self = mg2.write_entity_node(entity_type="person", name="Aria",
                                       now=T0 - timedelta(days=90))
    mg2.update_relationship_summary(stale_self, "old narrative",
                                    now=T0 - timedelta(days=90))
    assert mg2.continuity_evidence(stale_self, now=T0) is False  # outside 60d


# ===========================================================================
# Task 20 — is_first_of_kind + resolved_edge_exists
# ===========================================================================


def test_is_first_of_kind_by_appraisal_profile():
    # Addendum §6: first-of-kind = no prior event with this (Q2 quadrant × Q3
    # attribution) profile already references this entity.
    mg = make_graph()
    # no events yet → first-of-kind for any profile
    assert mg.is_first_of_kind("ent1", "negative", "user") is True
    # a negative×user event on ent1 now exists
    add_event(mg, appraisal_q2="negative", appraisal_q3="user", entity_refs=["ent1"])
    assert mg.is_first_of_kind("ent1", "negative", "user") is False  # same profile
    # a DIFFERENT profile on the same entity is still first-of-kind
    assert mg.is_first_of_kind("ent1", "positive", "user") is True
    assert mg.is_first_of_kind("ent1", "negative", "self") is True
    # same profile but a DIFFERENT entity is still first-of-kind
    assert mg.is_first_of_kind("ent2", "negative", "user") is True


def test_resolved_edge_exists_within_window():
    mg = make_graph()
    ev = add_event(mg, description="conflict", entity_refs=["ent1"])
    assert mg.resolved_edge_exists("ent1", timedelta(days=14), now=T0) is False
    mg.write_edge(from_node=ev, to_node="opening", edge_type=EdgeType.RESOLVED,
                  base_salience=0.3, now=T0 - timedelta(days=1))
    assert mg.resolved_edge_exists("ent1", timedelta(days=14), now=T0) is True
    # outside window
    assert mg.resolved_edge_exists("ent1", timedelta(hours=1), now=T0) is False


# ===========================================================================
# Task 21 — reality_contradiction_check (structural only)
# ===========================================================================


def test_reality_contradiction_detects_negation_polarity_flip():
    # same topic embedding, differing negation polarity → contradiction
    tbl = {
        "The deadline is Friday": [1.0, 0, 0, 0, 0, 0, 0, 0],
        "The deadline is not Friday": [1.0, 0, 0, 0, 0, 0, 0, 0],
    }
    mg = make_graph(tbl)
    add_event(mg, description="The deadline is Friday", entity_refs=["proj"],
              timestamp=T0 - timedelta(hours=1))
    assert mg.reality_contradiction_check(
        "proj", "The deadline is not Friday", now=T0) is True


def test_reality_contradiction_false_on_agreement():
    tbl = {
        "The deadline is Friday": [1.0, 0, 0, 0, 0, 0, 0, 0],
        "The deadline is Friday too": [1.0, 0, 0, 0, 0, 0, 0, 0],
    }
    mg = make_graph(tbl)
    add_event(mg, description="The deadline is Friday", entity_refs=["proj"],
              timestamp=T0 - timedelta(hours=1))
    assert mg.reality_contradiction_check(
        "proj", "The deadline is Friday too", now=T0) is False


# ===========================================================================
# Task 22 — boundary API-surface guarantees (Req 13, 7.6)
# ===========================================================================


def test_no_pad_or_llm_surface():
    public = [m for m in dir(MemoryGraph) if not m.startswith("_")]
    for m in public:
        low = m.lower()
        assert "pad" not in low, f"{m} looks like a PAD surface"
        assert "pleasure" not in low and "arousal" not in low and "dominance" not in low
        assert "llm" not in low and "prompt" not in low and "gemma" not in low


def test_no_relationship_depth_column_anywhere():
    # Req 7.6 / Resolution Log item 10: relationship_depth is superseded and
    # must never be a storage-layer concern of the graph. (The module docstring
    # legitimately *mentions* the name to document the boundary, so we check the
    # actual schema, not the source text.)
    mg = make_graph()
    for t in ("event_nodes", "entity_nodes", "emotion_nodes",
              "uncertainty_nodes", "edges", "node_embeddings"):
        cols = [r[1] for r in mg._conn.execute(f"PRAGMA table_info({t})")]
        assert "relationship_depth" not in cols
    # and no public method is named for it
    assert not any("relationship_depth" in m for m in dir(MemoryGraph))


def test_reads_are_detached_copies():
    mg = make_graph()
    nid = add_event(mg, poignancy_category=PoignancyCategory.CRITICAL)
    n1 = mg.get_event_node(nid)
    n1.salience = 999.0  # mutate the returned copy
    n2 = mg.get_event_node(nid)
    assert n2.salience != 999.0  # live state unaffected


# ===========================================================================
# Guards added after independent code audit (base-vs-salience, purpose window,
# emotion decay, retrieve edge-dedup)
# ===========================================================================


def test_precision_resistance_uses_base_salience_not_fluctuating():
    # Guards Resolution Log item 9: a critical node whose FLUCTUATING salience
    # has been driven low must STILL resist decay — resistance is checked
    # against base_salience, never the fluctuating salience. This would FAIL if
    # _evaluate_precision regressed to using node.salience.
    mg = make_graph()
    nid = add_event(mg, poignancy_category=PoignancyCategory.CRITICAL)  # base 0.85
    mg.adjust_salience(nid, 0.05)  # fluctuating salience now far below 0.8
    n = mg.get_event_node(nid)
    mg._touch_event_node(n, T0 + timedelta(days=365))
    assert mg.get_event_node(nid).precision == Precision.VIVID  # base 0.85 resists


def test_purpose_evidence_out_of_window_and_negative():
    # positive event OUTSIDE the 14d window → no evidence
    mg = make_graph()
    add_event(mg, appraisal_q2="positive", timestamp=T0 - timedelta(days=30))
    assert mg.purpose_evidence(now=T0) is False
    # only a negative event in-window → no evidence
    mg2 = make_graph()
    add_event(mg2, appraisal_q2="negative", timestamp=T0 - timedelta(days=1))
    assert mg2.purpose_evidence(now=T0) is False


def test_emotion_node_stays_vivid():
    # EmotionNodes are ALWAYS critical → resist vivid→present indefinitely
    # (Resolution Log item 9). There is deliberately no decay path; precision
    # stays VIVID. Documents the intended behavior (auditor D4).
    mg = make_graph()
    eid = mg.crystallize_emotion_node(emotion_label="grief", pad_p=0.1, pad_a=0.8,
                                      pad_d=0.2, trigger_event_ref="ev", now=T0)
    assert mg.get_emotion_node(eid).precision == Precision.VIVID


def test_retrieve_no_duplicate_edge_between_two_candidate_nodes():
    # Guards D2: an edge whose BOTH endpoints are candidate event nodes must
    # appear ONCE in results, not twice.
    tbl = {"q": [1.0, 0, 0, 0, 0, 0, 0, 0],
           "a": [1.0, 0, 0, 0, 0, 0, 0, 0],
           "b": [0.99, 0, 0, 0, 0, 0, 0, 0]}
    mg = make_graph(tbl)
    a = add_event(mg, description="a")
    b = add_event(mg, description="b")
    eid = mg.write_edge(from_node=a, to_node=b, edge_type=EdgeType.RESOLVED,
                        base_salience=0.3, now=T0)
    results = mg.retrieve(pad_pleasure_sign=0, query_embedding=tbl["q"], now=T0)
    edge_ids = [r.edge_id for r in results if isinstance(r, Edge)]
    assert edge_ids.count(eid) == 1


# ===========================================================================
# Architect resolutions (2026-07-05): OQ4 precedence + OQ1 habituation trigger
# ===========================================================================


def test_retrieve_mood_primary_over_need():
    # OQ4 (architect): mood-congruence PRIMARY, need-preference SECONDARY. When
    # they disagree, MOOD wins. Negative mood (sign -1): the mood-congruent
    # (negative-valence, non-need) edge must come BEFORE the need-relevant
    # (We-perspective, positive-valence, mood-incongruent) edge.
    tbl = {"q": [1.0, 0, 0, 0, 0, 0, 0, 0], "anchor": [1.0, 0, 0, 0, 0, 0, 0, 0]}
    mg = make_graph(tbl)
    a = add_event(mg, description="anchor", appraisal_q2="neutral")
    mood_edge = mg.write_edge(from_node=a, to_node="m", edge_type=EdgeType.CONNECTS,
                              valence=-0.5, perspective=Perspective.I_NOW, now=T0)
    need_edge = mg.write_edge(from_node=a, to_node="n", edge_type=EdgeType.CONNECTS,
                              valence=0.5, perspective=Perspective.WE, now=T0)
    results = mg.retrieve(pad_pleasure_sign=-1, need_prefs={"connection": True},
                          query_embedding=tbl["q"], now=T0)
    edge_ids = [r.edge_id for r in results if isinstance(r, Edge)]
    assert edge_ids.index(mood_edge) < edge_ids.index(need_edge)  # mood primary


def test_we_perspective_surfacing_fires_only_for_the_connection_pref():
    """Addendum §3: "When Connection is neglected, Stage 1 surfaces
    'We'-perspective and Connection-positive edges first." prefs["connection"]
    now MEANS neglected (set by appraisal_chain._need_prefs for that state
    alone), so the reordering must happen with the key present and not happen
    without it — a merely-`due` Connection sends no key at all.

    Mood is held NEUTRAL (sign 0) so need-preference is the only active
    reordering and the effect is unambiguous."""
    tbl = {"q": [1.0, 0, 0, 0, 0, 0, 0, 0], "anchor": [1.0, 0, 0, 0, 0, 0, 0, 0]}

    def build():
        mg = make_graph(tbl)
        a = add_event(mg, description="anchor", appraisal_q2="neutral")
        plain = mg.write_edge(from_node=a, to_node="p", edge_type=EdgeType.CONNECTS,
                              valence=0.0, perspective=Perspective.I_NOW, now=T0)
        we = mg.write_edge(from_node=a, to_node="w", edge_type=EdgeType.CONNECTS,
                           valence=0.5, perspective=Perspective.WE, now=T0)
        return mg, plain, we

    # NEGLECTED -> the key is present -> the We edge is surfaced first.
    mg, plain, we = build()
    ids = [r.edge_id for r in mg.retrieve(
        pad_pleasure_sign=0, need_prefs={"connection": True},
        query_embedding=tbl["q"], now=T0) if isinstance(r, Edge)]
    assert ids.index(we) < ids.index(plain)

    # DUE -> _need_prefs emits {} -> no reordering; insertion order stands.
    mg2, plain2, we2 = build()
    ids2 = [r.edge_id for r in mg2.retrieve(
        pad_pleasure_sign=0, need_prefs={},
        query_embedding=tbl["q"], now=T0) if isinstance(r, Edge)]
    assert ids2.index(plain2) < ids2.index(we2)

    # Same for no need_prefs at all (all needs satisfied).
    mg3, plain3, we3 = build()
    ids3 = [r.edge_id for r in mg3.retrieve(
        pad_pleasure_sign=0, query_embedding=tbl["q"], now=T0)
        if isinstance(r, Edge)]
    assert ids3.index(plain3) < ids3.index(we3)


def test_habituation_repeated_similar_firing_decrements_salience():
    # OQ1 (architect trigger shape): a firing "without variation" (context
    # embedding-similar to recent firings of the same edge) decrements salience.
    mg = make_graph()
    eid = mg.write_edge(from_node="a", to_node="b", edge_type=EdgeType.CONNECTS,
                        base_salience=0.5, now=T0)
    ctx = [1.0, 0, 0, 0, 0, 0, 0, 0]
    assert mg.register_edge_firing(eid, ctx, now=T0) is False  # first firing: no prior
    assert mg.get_edge(eid).salience == pytest.approx(0.5)
    assert mg.register_edge_firing(eid, ctx, now=T0 + timedelta(minutes=1)) is True
    assert mg.get_edge(eid).salience < 0.5  # habituated (decremented)
    assert mg.get_edge(eid).firing_count == 2


def test_habituation_varied_firing_no_decrement():
    mg = make_graph()
    eid = mg.write_edge(from_node="a", to_node="b", edge_type=EdgeType.CONNECTS,
                        base_salience=0.5, now=T0)
    mg.register_edge_firing(eid, [1.0, 0, 0, 0, 0, 0, 0, 0], now=T0)
    # a dissimilar retrieval context → NOT "without variation" → no decrement
    applied = mg.register_edge_firing(eid, [0, 1.0, 0, 0, 0, 0, 0, 0],
                                      now=T0 + timedelta(minutes=1))
    assert applied is False
    assert mg.get_edge(eid).salience == pytest.approx(0.5)


def test_habituation_touches_only_salience_never_base_or_valence():
    # GUARD (architect): habituation adjusts edge salience ONLY.
    mg = make_graph()
    eid = mg.write_edge(from_node="a", to_node="b", edge_type=EdgeType.CONNECTS,
                        valence=0.7, base_salience=0.5, now=T0)
    ctx = [1.0, 0, 0, 0, 0, 0, 0, 0]
    mg.register_edge_firing(eid, ctx, now=T0)
    mg.register_edge_firing(eid, ctx, now=T0 + timedelta(minutes=1))
    e = mg.get_edge(eid)
    assert e.salience < 0.5          # salience changed
    assert e.base_salience == pytest.approx(0.5)  # base_salience untouched
    assert e.valence == pytest.approx(0.7)        # valence (appraisal) untouched

def test_increment_uncertainty_interaction_count_increments_each_call():
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    ev = g.write_event_node(description="x", session_id="s1",
                            appraisal_q1="medium", appraisal_q2="neutral",
                            appraisal_q3="user",
                            poignancy_category=PoignancyCategory.MEDIUM, now=T0)
    nid = g.create_uncertainty_node(
        uncertainty_type=UncertaintyType.VALENCE_UNCERTAIN,
        trigger_event_ref=ev, now=T0,
    )
    assert g.get_uncertainty_node(nid).interaction_count == 0
    g.increment_uncertainty_interaction_count(nid)
    assert g.get_uncertainty_node(nid).interaction_count == 1
    g.increment_uncertainty_interaction_count(nid)
    g.increment_uncertainty_interaction_count(nid)
    assert g.get_uncertainty_node(nid).interaction_count == 3
    g.close()


def test_increment_raises_for_resolved_or_absent_node():
    g = MemoryGraph(":memory:", embedding_model=FakeEmbedding())
    ev = g.write_event_node(description="x", session_id="s1",
                            appraisal_q1="medium", appraisal_q2="neutral",
                            appraisal_q3="user",
                            poignancy_category=PoignancyCategory.MEDIUM, now=T0)
    nid = g.create_uncertainty_node(
        uncertainty_type=UncertaintyType.VALENCE_UNCERTAIN,
        trigger_event_ref=ev, now=T0,
    )
    g.update_uncertainty_status(nid, UncertaintyStatus.RESOLVED_CONFIRMED,
                                resolution_path="direct_information", now=T0)
    # Resolved node raises — it is no longer ACTIVE.
    with pytest.raises(KeyError):
        g.increment_uncertainty_interaction_count(nid)
    # Non-existent node also raises.
    with pytest.raises(KeyError):
        g.increment_uncertainty_interaction_count("does-not-exist")
    g.close()
