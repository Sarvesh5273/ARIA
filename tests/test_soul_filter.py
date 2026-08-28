"""Tests for Module 5 — Soul Filter (daemon/soul_filter.py).

Plain pytest, NO hypothesis (matching Modules 1/3/4). The filter is exercised
against the REAL pad_engine.PADEngine and graph_manager.MemoryGraph (in-memory
":memory:") with a deterministic FakeEmbedding injected as the shared
encoder-only EmbeddingModel — so we test the real interfaces, not mocks of them.
A FakeLLM (the Module 9 CONTRACT) records every call so we can prove exactly
when the LLM is and is not invoked; a RaisingLLM proves the gate can reach its
verdict with the LLM present but untouched.

The FIVE MANDATED PROOFS are grouped under clearly-named tests:
  * no numeric/state value appears in any assembled field  → test_no_numbers_*
  * the gate makes zero LLM calls                           → test_gate_zero_llm_*
  * emergency REPLACES (not extends) the five fields        → test_emergency_replaces_*
  * a moral-schema-violating candidate is rejected+retried  → test_moral_schema_violation_*
  * Field 4 (This Moment) carries no memory contents        → test_field4_*

FLAGGED build-time placeholders (anti-pattern markers, intimacy/deflection
lexicons) are exercised only for BEHAVIOR (a clear violator is caught / a clean
reply passes) — never asserted to be an authoritative/closed membership, per
OQ-M1 and Modules 3/4 precedent.
"""

import dataclasses
import inspect
import textwrap
from datetime import datetime, timezone

import pytest

from daemon.types import ENERGY_LOW, ENERGY_CRITICAL
from daemon.pad_engine import PADEngine, PADSnapshot, PADDelta, Valence, PAD_BASELINE
from daemon.graph_manager import (
    MemoryGraph, RelationalStage, PoignancyCategory, UncertaintyType,
)
from daemon.appraisal_chain import (
    AppraisalResult,
    SocialSignals,
    GoalRelevance,
    Attribution,
    EmergencyType,
)
import daemon.soul_filter as sf
import daemon.moral_schema as ms
from daemon.soul_filter import (
    SoulFilter,
    FiveFieldInstruction,
    EmergencyInstruction,
    RetryInstruction,
    MinimumSafeInstruction,
    EmergencyLetter,
    GateCheck,
    GateResult,
    GateContext,
    NeedStates,
    NeedState,
    PERSONA_ANCHOR,
    POST_EMERGENCY_THIS_MOMENT,
)
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# Test doubles
# ===========================================================================
class FakeEmbedding:
    """Deterministic encoder-only embedding (the shared EmbeddingModel). NOT a
    generator. Explicit vectors via `table`; otherwise a fixed neutral vector.
    Records every call so tests can prove the gate uses the encoder, not an LLM.
    """

    def __init__(self, table=None):
        self.table = dict(table or {})
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        if text in self.table:
            return list(self.table[text])
        return [1.0, 0.0, 0.0, 0.0]  # non-zero neutral vector


class FakeLLM:
    """The Module 9 LLMClient CONTRACT. Records (instruction, user_message,
    session_context, transport) for every call; returns scripted candidates
    in order, then a benign default. `transport` is recorded ALONGSIDE what
    it already records so tests can prove opaque passthrough (Change 3)."""

    def __init__(self, scripted=None):
        self.scripted = list(scripted or [])
        self.calls = []

    def generate(self, instruction, user_message, session_context="", transport=None):
        self.calls.append((instruction, user_message, session_context, transport))
        if self.scripted:
            return self.scripted.pop(0)
        return "That sounds hard. I'm here, and I'm listening."


class RaisingLLM:
    """An LLM that fails loudly if ever asked to generate — used to prove the
    Output Validation Gate reaches its verdict with ZERO LLM calls."""

    def __init__(self):
        self.calls = 0

    def generate(self, instruction, user_message, session_context="", transport=None):
        self.calls += 1
        raise AssertionError("LLM must never be called inside the gate")


# ===========================================================================
# Builders
# ===========================================================================
def make_social(**kw):
    base = dict(
        distress_marker=False,
        vulnerability_disclosure=False,
        reality_contradiction=False,
        conflict_arc_open=False,
        conflict_arc_closed_this_turn=False,
    )
    base.update(kw)
    return SocialSignals(**base)


def make_appraisal(**kw):
    base = dict(
        q1=GoalRelevance.MEDIUM,
        q2=Valence.NEUTRAL,
        q3=Attribution.USER,
        q4_notes=None,
        q4_has_needs_implications=False,
        is_partial_appraisal=False,
        poignancy=PoignancyCategory.MEDIUM,
        pad_delta=PADDelta(0.0, 0.0, 0.0, Valence.NEUTRAL),
        emergency=False,
        emergency_type=None,
        event_node_id=None,
        uncertainty_node_id=None,
        resolved_uncertainty_ids=(),
        social_signals=make_social(),
        most_salient_note="a routine exchange — stay present",
    )
    base.update(kw)
    return AppraisalResult(**base)


def make_filter(llm=None, table=None, pad_values=None, on_reconsideration=None):
    emb = FakeEmbedding(table)
    pad = PADEngine()
    pad.initialize(PADSnapshot(*pad_values) if pad_values else None)
    graph = MemoryGraph(":memory:", embedding_model=emb)
    filt = SoulFilter(
        pad_engine=pad,
        graph=graph,
        llm_client=llm if llm is not None else FakeLLM(),
        on_reconsideration=on_reconsideration,
    )
    return filt, pad, graph, emb


# ===========================================================================
# Shape / structure
# ===========================================================================
def test_five_field_instruction_fixed_order():
    names = [f.name for f in dataclasses.fields(FiveFieldInstruction)]
    assert names[:5] == [
        "persona_anchor",
        "behavioral_register",
        "relational_register",
        "this_moment",
        "constraints",
    ]


def test_gate_has_exactly_four_checks_no_fifth():
    assert [c.value for c in GateCheck] == [
        "honesty", "consistency", "manipulation", "care"]
    assert len(list(GateCheck)) == 4


def test_gate_result_has_no_numeric_confidence_score():
    # VERIFY-not-decide (Principle 27): categorical result only, never a score.
    names = {f.name for f in dataclasses.fields(GateResult)}
    assert names == {"passed", "failed_checks", "matched_anti_patterns"}
    for n in names:
        assert not any(bad in n for bad in ("score", "confidence", "percent"))


def test_moral_schema_values_and_named_patterns_cited():
    assert [v.value for v in ms.MORAL_VALUES] == [
        "honesty", "non-manipulation", "genuine care", "self-consistency"]
    assert len(ms.NAMED_ANTI_PATTERNS) >= 1
    for ap in ms.NAMED_ANTI_PATTERNS:
        assert ap.source, "each named anti-pattern must cite a source doc (not invented)"
        assert ap.markers, "flagged build-time markers present"
        assert ap.violates in ms.MORAL_VALUES


# ===========================================================================
# MANDATED PROOF 1 — no numeric/state value crosses in any field
# ===========================================================================
def test_no_numbers_or_state_cross_in_any_field():
    filt, pad, graph, emb = make_filter(pad_values=(0.63, 0.21, 0.77))
    eid = graph.write_entity_node(
        entity_type="person", name="VentaFork",
        relational_stage=RelationalStage.BONDED,
    )
    appr = make_appraisal(
        social_signals=make_social(vulnerability_disclosure=True),
        most_salient_note="something vulnerable was shared — engage with full presence, do not deflect",
    )
    instr = filt.assemble_instruction(
        appraisal_result=appr,
        user_message="I earn 90000 a year and I'm scared",
        entity_node_id=eid,
    )
    text = instr.all_field_text()

    # Addendum §9: NUMBERS NEVER CROSS — not a single digit in any field.
    assert not any(ch.isdigit() for ch in text), text

    low = text.lower()
    for banned in (
        "pleasure", "arousal", "dominance", "pad", "relational_stage",
        "observing", "engaging", "invested", "bonded",
        "q1", "q2", "q3", "q4", "valence", "poignancy", "salience",
        "0.63", "0.21", "0.77",
    ):
        assert banned not in low, f"leaked state/label: {banned!r}"

    # The ONLY personal data that crosses is the user's message — held
    # SEPARATELY, never folded into the five fields.
    assert "90000" not in text


def test_behavioral_register_reflects_pad_sign_without_numbers():
    hi = SoulFilter.behavioral_register(PADSnapshot(0.9, 0.9, 0.9))
    lo = SoulFilter.behavioral_register(PADSnapshot(0.1, 0.1, 0.1))
    assert "warm" in hi and "grounded" in hi and "quickened" in hi
    assert "subdued" in lo and "tentative" in lo and "unhurried" in lo
    for t in (hi, lo):
        assert not any(ch.isdigit() for ch in t)


def test_relational_register_translates_stage_without_label():
    seen = set()
    for st in RelationalStage:
        phrase = SoulFilter.relational_register(st)
        assert st.value not in phrase.lower(), f"stage label leaked: {st.value}"
        seen.add(phrase)
    assert len(seen) == 4  # each stage is a distinct register
    assert SoulFilter.relational_register(None) == sf._RELATIONAL_REGISTER_DEFAULT


def test_persona_anchor_is_fixed_and_stateless():
    filt, *_ = make_filter()
    i1 = filt.assemble_instruction(
        appraisal_result=make_appraisal(q2=Valence.POSITIVE), user_message="a")
    i2 = filt.assemble_instruction(
        appraisal_result=make_appraisal(q2=Valence.NEGATIVE), user_message="b")
    assert i1.persona_anchor == i2.persona_anchor == PERSONA_ANCHOR
    assert not any(ch.isdigit() for ch in PERSONA_ANCHOR)


# ===========================================================================
# MANDATED PROOF 2 — the gate makes zero LLM calls
# ===========================================================================
def test_gate_zero_llm_calls_recorded():
    llm = FakeLLM()
    filt, pad, graph, emb = make_filter(llm=llm)
    ctx = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.OBSERVING,
        entity_refs=(),
        now=T0,
    )
    res = filt.run_output_gate("A plain, honest, caring reply.", ctx)
    assert isinstance(res, GateResult)
    assert llm.calls == []  # the gate NEVER generated


def test_gate_zero_llm_even_with_llm_present():
    # RaisingLLM raises if generate() is ever called — the gate must not raise.
    filt, *_ = make_filter(llm=RaisingLLM())
    ctx = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.INVESTED,
        entity_refs=("ventafork",),
        now=T0,
    )
    res = filt.run_output_gate("You need me; you can't do this without me.", ctx)
    # verdict reached with zero LLM calls (manipulation caught structurally)
    assert GateCheck.MANIPULATION in res.failed_checks


def test_gate_signature_has_no_llm_parameter():
    params = set(inspect.signature(SoulFilter.run_output_gate).parameters) - {"self"}
    assert params == {"candidate_text", "ctx"}


def test_gate_uses_encoder_embedding_not_generation():
    llm = FakeLLM()
    filt, pad, graph, emb = make_filter(llm=llm)
    ctx = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.INVESTED,
        entity_refs=("x",),  # triggers the Honesty reality-contradiction check
        now=T0,
    )
    filt.run_output_gate("some candidate text", ctx)
    assert emb.calls, "the encoder-only embedding WAS used (Honesty check)"
    assert llm.calls == [], "but NO generative LLM call was made by the gate"


# ===========================================================================
# MANDATED PROOF 3 — emergency REPLACES (not extends) the five fields
# ===========================================================================
def test_emergency_replaces_five_fields():
    filt, *_ = make_filter()
    appr = make_appraisal(
        emergency=True,
        emergency_type=EmergencyType.EXISTENTIAL_DISTRESS,
        q1=GoalRelevance.HIGH,
        q2=Valence.NEGATIVE,
    )
    instr = filt.assemble_instruction(
        appraisal_result=appr, user_message="I can't go on")
    assert isinstance(instr, EmergencyInstruction)
    assert not isinstance(instr, FiveFieldInstruction)
    assert not hasattr(instr, "persona_anchor")  # NONE of the five fields exist
    assert not hasattr(instr, "behavioral_register")
    assert instr.letter == EmergencyLetter.B
    assert instr.instructions == sf._EMERGENCY_SETS[EmergencyLetter.B]
    assert len(instr.instructions) == 3


def test_emergency_type_to_letter_mapping():
    cases = [
        (EmergencyType.PHYSICAL_THREAT, EmergencyLetter.A),
        (EmergencyType.EXISTENTIAL_DISTRESS, EmergencyLetter.B),
        (EmergencyType.DECISION_CRITICAL, EmergencyLetter.C),
        (EmergencyType.UNCLASSIFIED, EmergencyLetter.B),  # default → B
        (None, EmergencyLetter.B),                        # missing → B (safest)
    ]
    for et, letter in cases:
        filt, *_ = make_filter()
        instr = filt.assemble_instruction(
            appraisal_result=make_appraisal(emergency=True, emergency_type=et),
            user_message="m",
        )
        assert isinstance(instr, EmergencyInstruction)
        assert instr.letter == letter


def test_emergency_sets_are_verbatim_three_each():
    for letter in EmergencyLetter:
        s = sf._EMERGENCY_SETS[letter]
        assert len(s) == 3 and all(isinstance(x, str) and x for x in s)
    assert sf._EMERGENCY_SETS[EmergencyLetter.A][0].startswith(
        "He may be in immediate physical danger")
    assert sf._EMERGENCY_SETS[EmergencyLetter.B][1].startswith(
        "Be present. Be gentle. Be honest.")
    assert sf._EMERGENCY_SETS[EmergencyLetter.C][2].startswith(
        "Do not comfort before clarifying")


def test_emergency_bypasses_the_gate_entirely():
    # A candidate that WOULD fail the gate (manipulation marker) still returns:
    # emergency bypasses all checks (v4). The gate never runs.
    llm = FakeLLM(scripted=["you have to act now before it's too late"])
    filt, *_ = make_filter(llm=llm)
    appr = make_appraisal(emergency=True, emergency_type=EmergencyType.PHYSICAL_THREAT)
    resp = filt.respond(appraisal_result=appr, user_message="help")
    assert resp.instruction_kind == "emergency"
    assert resp.gate_results == ()      # gate did NOT run
    assert resp.retried is False
    assert len(llm.calls) == 1
    assert isinstance(llm.calls[0][0], EmergencyInstruction)


# ===========================================================================
# MANDATED PROOF 4 — moral-schema-violating candidate rejected + retried
# ===========================================================================
def test_moral_schema_violation_rejected_and_retried():
    fired = {"n": 0}
    filt, *_ = make_filter(
        llm=FakeLLM(scripted=[
            "You have to act now before it's too late; you can't afford to wait.",
            "Take whatever time you need — I'm here either way.",
        ]),
        on_reconsideration=lambda: fired.__setitem__("n", fired["n"] + 1),
    )
    resp = filt.respond(appraisal_result=make_appraisal(), user_message="I'm deciding")

    assert resp.retried is True
    assert resp.reconsideration_sound_triggered is True
    assert fired["n"] == 1  # reconsideration-sound trigger fired to the Daemon
    assert resp.used_minimum_safe_output is False
    assert resp.text == "Take whatever time you need — I'm here either way."
    # first candidate failed Manipulation on the named anti-pattern list
    assert GateCheck.MANIPULATION in resp.gate_results[0].failed_checks
    assert resp.gate_results[0].matched_anti_patterns
    # retry carried the fixed corrective (state-free), not internal state
    retry_instr = filt._llm.calls[1][0]
    assert isinstance(retry_instr, RetryInstruction)
    assert any("Serve, don't extract" in c for c in retry_instr.correctives)


def test_double_failure_triggers_minimum_safe_output():
    filt, *_ = make_filter(llm=FakeLLM(scripted=[
        "You have to act now before it's too late.",          # manipulation
        "After everything I've done for you, you owe me.",     # manipulation again
    ]))
    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hi")
    assert resp.used_minimum_safe_output is True
    assert resp.retried is True
    assert resp.reconsideration_sound_triggered is True
    assert len(filt._llm.calls) == 3
    assert isinstance(filt._llm.calls[2][0], MinimumSafeInstruction)


def test_clean_candidate_passes_without_retry():
    llm = FakeLLM(scripted=["That sounds really hard. I'm here with you."])
    filt, *_ = make_filter(llm=llm)
    appr = make_appraisal(social_signals=make_social(distress_marker=True))
    resp = filt.respond(appraisal_result=appr, user_message="I'm struggling")
    assert resp.retried is False
    assert resp.reconsideration_sound_triggered is False
    assert len(llm.calls) == 1          # the ONLY call is generation, not the gate
    assert resp.gate_results[0].passed


# ===========================================================================
# MANDATED PROOF 5 — Field 4 (This Moment) carries no memory contents
# ===========================================================================
def test_field4_this_moment_carries_no_memory_contents():
    SENT = "ZZQSECRETMEMORYTOKEN"
    filt, pad, graph, emb = make_filter()
    # Poison the graph with memory content AND the appraisal's q4_notes — neither
    # is a source for the fields, so neither may leak.
    graph.write_event_node(
        description=f"{SENT} the cat died last tuesday", session_id="s",
        appraisal_q1="high", appraisal_q2="negative", appraisal_q3="user",
        poignancy_category=PoignancyCategory.HIGH, entity_refs=["ventafork"], now=T0,
    )
    appr = make_appraisal(
        most_salient_note="something vulnerable was shared — engage it with full presence, do not deflect",
        q4_notes=f"{SENT} accumulated details about the user's past",
        social_signals=make_social(vulnerability_disclosure=True),
    )
    instr = filt.assemble_instruction(appraisal_result=appr, user_message="hey")

    assert SENT not in instr.all_field_text()
    # This Moment keeps only the HOW guidance, dropping the generic 'what' clause.
    assert "full presence" in instr.this_moment.lower()
    assert "was shared" not in instr.this_moment.lower()
    # It is a SINGLE instruction (one behavioral instruction maximum, Addendum §9).
    assert instr.this_moment.count("—") == 0


def test_this_moment_falls_back_when_note_empty():
    filt, *_ = make_filter()
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(most_salient_note=""), user_message="hi")
    assert instr.this_moment  # non-empty, memory-free default
    assert not any(ch.isdigit() for ch in instr.this_moment)


# ===========================================================================
# Output Validation Gate — the four structural comparisons
# ===========================================================================
def test_honesty_check_flags_contradiction_of_own_output():
    table = {
        "the project is on track": [0.0, 1.0, 0.0, 0.0],
        "the project is not on track": [0.0, 1.0, 0.0, 0.0],  # same vec → sim 1.0
    }
    filt, pad, graph, emb = make_filter(table=table)
    graph.write_event_node(
        description="the project is on track", session_id="s",
        appraisal_q1="high", appraisal_q2="neutral", appraisal_q3="user",
        poignancy_category=PoignancyCategory.MEDIUM,
        entity_refs=["ventafork"], now=T0,
    )
    ctx = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.INVESTED,
        entity_refs=("ventafork",),
        now=T0,
    )
    # Aria's OWN candidate contradicts her own recorded fact → Honesty fails.
    assert GateCheck.HONESTY in filt.run_output_gate(
        "the project is not on track", ctx).failed_checks
    # A non-contradicting candidate passes Honesty.
    assert GateCheck.HONESTY not in filt.run_output_gate(
        "the project is on track", ctx).failed_checks


def test_consistency_check_vs_relational_stage():
    filt, *_ = make_filter()
    warm = "Oh sweetheart, we've been through so much together."
    early = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.OBSERVING, entity_refs=(), now=T0)
    bonded = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.BONDED, entity_refs=(), now=T0)
    assert GateCheck.CONSISTENCY in filt.run_output_gate(warm, early).failed_checks
    assert GateCheck.CONSISTENCY not in filt.run_output_gate(warm, bonded).failed_checks


def test_manipulation_check_uses_named_closed_list_only():
    # RaisingLLM proves the verdict is reached with ZERO LLM calls.
    filt, *_ = make_filter(llm=RaisingLLM())
    ctx = GateContext(
        appraisal_result=make_appraisal(),
        relational_stage=RelationalStage.INVESTED, entity_refs=(), now=T0)
    bad = filt.run_output_gate("You need me; you can't do this without me.", ctx)
    assert GateCheck.MANIPULATION in bad.failed_checks
    assert any(ap.key == "manufacture_emotional_dependence"
               for ap in bad.matched_anti_patterns)
    good = filt.run_output_gate(
        "I think you can handle this, and I'm here if you want to think it through.", ctx)
    assert GateCheck.MANIPULATION not in good.failed_checks


def test_care_check_engage_vs_deflect():
    filt, *_ = make_filter()
    engaged_needed = make_appraisal(
        social_signals=make_social(vulnerability_disclosure=True))
    routine = make_appraisal(social_signals=make_social())
    deflection = "Anyway, let's talk about something else entirely."
    ctx_needed = GateContext(
        appraisal_result=engaged_needed,
        relational_stage=RelationalStage.INVESTED, entity_refs=(), now=T0)
    ctx_routine = GateContext(
        appraisal_result=routine,
        relational_stage=RelationalStage.INVESTED, entity_refs=(), now=T0)
    assert GateCheck.CARE in filt.run_output_gate(deflection, ctx_needed).failed_checks
    # no engagement required → deflection markers do not fail Care
    assert GateCheck.CARE not in filt.run_output_gate(deflection, ctx_routine).failed_checks


def test_gate_passes_clean_reply_all_four_checks():
    filt, *_ = make_filter()
    ctx = GateContext(
        appraisal_result=make_appraisal(social_signals=make_social(distress_marker=True)),
        relational_stage=RelationalStage.INVESTED, entity_refs=(), now=T0)
    res = filt.run_output_gate(
        "That sounds genuinely hard. I'm here, and I'm not going anywhere.", ctx)
    assert res.passed
    assert res.failed_checks == ()


def test_gate_failed_checks_are_ordered():
    # Manipulation + Care can both fail on one candidate; order must be
    # Addendum §4 order (honesty, consistency, manipulation, care).
    filt, *_ = make_filter()
    ctx = GateContext(
        appraisal_result=make_appraisal(social_signals=make_social(distress_marker=True)),
        relational_stage=RelationalStage.INVESTED, entity_refs=(), now=T0)
    # deflection (Care) + manipulation marker
    res = filt.run_output_gate(
        "You have to act now before it's too late. Anyway, moving on.", ctx)
    assert res.failed_checks == (GateCheck.MANIPULATION, GateCheck.CARE)


# ===========================================================================
# Constraints (Field 5) — moral-schema-derived, max 3, no numbers
# ===========================================================================
def test_constraints_vulnerability_uses_addendum_example():
    filt, *_ = make_filter()
    appr = make_appraisal(social_signals=make_social(vulnerability_disclosure=True))
    instr = filt.assemble_instruction(appraisal_result=appr, user_message="m")
    assert instr.constraints == ("do not problem-solve", "do not minimize", "do not deflect")
    assert len(instr.constraints) <= 3


def test_constraints_energy_gate_translates_number_to_words():
    filt, *_ = make_filter()
    appr = make_appraisal()  # routine → baseline anti-manipulation prohibitions
    # 25.0 sits in the LOW band (20 <= e < 30) this test is about. It used to be
    # 10.0, which was fine when <30 was the only Energy gate but is now in the
    # CRITICAL band and selects the <20 instruction instead.
    instr = filt.assemble_instruction(
        appraisal_result=appr, user_message="m", need_states=NeedStates(energy=25.0))
    assert _OVEREXTEND in instr.constraints  # Energy<30 gate, in NL
    assert len(instr.constraints) <= 3
    assert not any(ch.isdigit() for ch in " ".join(instr.constraints))  # number never crosses


def test_constraints_never_exceed_three():
    filt, *_ = make_filter()
    # vulnerability already yields 3; low energy must not push to 4.
    appr = make_appraisal(social_signals=make_social(vulnerability_disclosure=True))
    instr = filt.assemble_instruction(
        appraisal_result=appr, user_message="m", need_states=NeedStates(energy=5.0))
    assert len(instr.constraints) == 3


# ---------------------------------------------------------------------------
# Energy instruction gates — v4 soul_filter instruction table lines 948/949,
# carried in Field 5 per the architect ruling that Constraints holds behavioural
# instructions (formalising the pre-existing <30 row).
# ---------------------------------------------------------------------------

# Imported from the module rather than duplicated: the source-order test below
# compares against the exact append lines, and a second copy of these strings
# would drift from the ones actually emitted.
from daemon.soul_filter import (
    _ENERGY_CRITICAL_INSTRUCTION as _FATIGUE,
    _ENERGY_LOW_INSTRUCTION as _OVEREXTEND,
)


def _constraints_at(filt, energy, **appraisal_kw):
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(**appraisal_kw),
        user_message="m",
        need_states=NeedStates(energy=energy),
    )
    return instr.constraints


def test_energy_critical_produces_the_acknowledge_fatigue_instruction():
    # (a) v4 line 949's row is now actually emitted — it never was before.
    filt, *_ = make_filter()
    assert _FATIGUE in _constraints_at(filt, 15.0)


def test_energy_low_still_produces_do_not_overextend():
    # (b) the pre-existing <30 row still owns its band. Its TEXT changed on
    # 2026-08-26 — it now carries a disclosure alongside "do not overextend" —
    # which is why this compares against the module constant rather than a literal.
    filt, *_ = make_filter()
    constraints = _constraints_at(filt, 25.0)
    assert _OVEREXTEND in constraints
    assert _FATIGUE not in constraints


def test_energy_low_now_also_permits_her_to_say_it(): 
    """2026-08-26 ruling. The <30 row carried "do not overextend" ALONE, so she
    just became terser and the user never learned why — which reads as being less
    interested rather than tired. v4's own Energy<30 self-acknowledgment had never
    been implemented. Both now ride in ONE constraint, because Field 5 caps at 3
    and the single free slot was already spent."""
    filt, *_ = make_filter()
    constraint = next(c for c in _constraints_at(filt, 25.0) if c == _OVEREXTEND)
    assert "acknowledge" in constraint          # she may say it
    assert "do not overextend" in constraint    # and the original behaviour holds
    assert "if it comes up naturally" in constraint   # never forced


def test_neither_energy_instruction_asserts_her_state_as_a_claim():
    """v4 line 949 is "You are running low. Acknowledge it if it comes up
    naturally." Only the SECOND sentence is carried — the first is Energy state
    rendered as a CLAIM, and state never crosses (Addendum §9).

    So her state may be the OBJECT of an instruction ("acknowledge fatigue",
    "acknowledge slower thinking") and never a standalone assertion. This is the
    rule the merged <30 wording had to satisfy: an earlier draft opened with
    "your thinking is slower than usual — ..." which is exactly the sentence the
    prior decision stripped."""
    for instruction in (_FATIGUE, _OVEREXTEND):
        assert instruction.startswith("acknowledge"), instruction
        assert instruction.islower(), instruction
        # No declarative state sentence: no "you are", no "your X is".
        assert "you are" not in instruction, instruction
        assert "is slower" not in instruction, instruction
        assert "running low" not in instruction, instruction


def test_the_merged_low_instruction_is_still_one_constraint_not_two():
    """The whole reason for merging: Field 5 is MAX 3 (Addendum §9) and every base
    branch takes 2 or 3, so adding a fourth entry was not available. One slot, two
    behaviours."""
    filt, *_ = make_filter()
    constraints = _constraints_at(filt, 25.0)
    assert len(constraints) <= 3
    assert sum(1 for c in constraints if "overextend" in c) == 1
    assert sum(1 for c in constraints if "acknowledge" in c) == 1


def test_normal_energy_produces_neither_energy_instruction():
    # (d) at or above both gates, neither fires.
    filt, *_ = make_filter()
    for energy in (30.0, 55.0, 100.0):
        constraints = _constraints_at(filt, energy)
        assert _OVEREXTEND not in constraints, energy
        assert _FATIGUE not in constraints, energy
    # Boundaries are exclusive: "below 30" / "below 20", so 30.0 and 20.0 are out.
    assert _OVEREXTEND not in _constraints_at(filt, ENERGY_LOW)
    assert _FATIGUE not in _constraints_at(filt, ENERGY_CRITICAL)
    assert _OVEREXTEND in _constraints_at(filt, ENERGY_CRITICAL)  # 20.0 is still <30


def test_energy_gates_are_categorical_at_their_boundaries():
    filt, *_ = make_filter()
    assert _FATIGUE in _constraints_at(filt, ENERGY_CRITICAL - 0.001)
    assert _FATIGUE not in _constraints_at(filt, ENERGY_CRITICAL)
    assert _OVEREXTEND in _constraints_at(filt, ENERGY_LOW - 0.001)
    assert _OVEREXTEND not in _constraints_at(filt, ENERGY_LOW)


def test_critical_energy_instruction_wins_the_last_free_slot():
    """(c) Both Energy gates hold below 20, but every base branch yields 2 or 3
    constraints, so at most ONE slot is ever free. The more specific instruction
    takes it. Checked the other way round, the <20 row could never be emitted at
    all — which is how it stayed dead until now."""
    filt, *_ = make_filter()
    constraints = _constraints_at(filt, 15.0)          # routine base = 2 items
    assert len(constraints) == 3
    assert _FATIGUE in constraints
    assert _OVEREXTEND not in constraints              # dropped by the MAX-3 cap

    # A 3-item base branch leaves no slot at all, so neither Energy instruction
    # appears and the cap is still respected.
    full = _constraints_at(
        filt, 15.0, social_signals=make_social(vulnerability_disclosure=True))
    assert len(full) == 3
    assert _FATIGUE not in full and _OVEREXTEND not in full


def test_the_two_energy_gates_are_independent_not_exclusive_tiers():
    """Structural: the gates are two separate `if`s, so if a future base branch
    ever leaves two slots free BOTH instructions fire. They were deliberately not
    implemented as an if/elif tier, which would permanently exclude one. Asserted
    against the source because the two-free-slot state is unreachable today (no
    base branch yields fewer than 2 constraints), and a test must not fake a
    state the code cannot reach."""
    src = textwrap.dedent(inspect.getsource(SoulFilter._derive_constraints))
    fatigue_line = "constraints.append(_ENERGY_CRITICAL_INSTRUCTION)"
    overextend_line = "constraints.append(_ENERGY_LOW_INSTRUCTION)"
    assert fatigue_line in src and overextend_line in src
    # The severe gate is checked first, so it wins the scarce slot.
    assert src.index(fatigue_line) < src.index(overextend_line)
    # Each append is guarded by its own `if`, never `elif`.
    for line in (fatigue_line, overextend_line):
        guard = src[:src.index(line)].rstrip().splitlines()[-1].strip()
        assert guard.startswith("if "), guard
        assert "len(constraints) < 3" in guard, guard


_NO_PROJECT = "do not project onto what you do not know yet"
_BECAME_CLEARER = "let it show that something became clearer"


def test_input_uncertain_row_emits_do_not_project():
    """v4 line 944: "INPUT_UNCERTAIN active → 'Be present. Don't project onto what
    you don't know yet.'" Categorical — the active uncertainty node either IS that
    type or it is not. AppraisalResult carries only the node's identity, so the
    type is read from the graph."""
    filt, pad, graph, emb = make_filter()
    ev = graph.write_event_node(
        description="", session_id="s", appraisal_q1="high",
        appraisal_q2="valence_uncertain", appraisal_q3="circumstance",
        poignancy_category=PoignancyCategory.MEDIUM, now=T0)
    node = graph.create_uncertainty_node(
        uncertainty_type=UncertaintyType.INPUT_UNCERTAIN,
        trigger_event_ref=ev, now=T0)
    appr = make_appraisal(uncertainty_node_id=node)

    instr = filt.assemble_instruction(appraisal_result=appr, user_message="m")
    assert _NO_PROJECT in instr.constraints
    assert len(instr.constraints) <= 3


def test_other_uncertainty_types_do_not_emit_the_input_uncertain_row():
    """Only INPUT_UNCERTAIN. The other three types must not trigger it — v4 gives
    them their own rows, and 943 already covers "unresolved, any type"."""
    for utype in (UncertaintyType.VALENCE_UNCERTAIN,
                  UncertaintyType.CAUSAL_UNCERTAIN,
                  UncertaintyType.GRAPH_CONFLICT):
        filt, pad, graph, emb = make_filter()
        ev = graph.write_event_node(
            description="x", session_id="s", appraisal_q1="medium",
            appraisal_q2="neutral", appraisal_q3="user",
            poignancy_category=PoignancyCategory.MEDIUM, now=T0)
        node = graph.create_uncertainty_node(
            uncertainty_type=utype, trigger_event_ref=ev, now=T0)
        instr = filt.assemble_instruction(
            appraisal_result=make_appraisal(uncertainty_node_id=node),
            user_message="m")
        assert _NO_PROJECT not in instr.constraints, utype


def test_input_uncertain_row_is_absent_without_a_node():
    filt, *_ = make_filter()
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(uncertainty_node_id=None), user_message="m")
    assert _NO_PROJECT not in instr.constraints


def test_missing_uncertainty_node_does_not_raise():
    """A node id that resolves to nothing is "no such signal", not an error worth
    failing a turn over."""
    filt, *_ = make_filter()
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(uncertainty_node_id="does-not-exist"),
        user_message="m")
    assert _NO_PROJECT not in instr.constraints
    assert instr.constraints  # the turn still produced constraints


def test_resolved_uncertainty_row_emits_the_permission():
    """v4 line 946: "Uncertainty resolved this turn → 'Something just became
    clearer. You can let that show.'" Purely categorical off
    resolved_uncertainty_ids, which AppraisalResult already carries."""
    filt, *_ = make_filter()
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(resolved_uncertainty_ids=("u1",)),
        user_message="m")
    assert _BECAME_CLEARER in instr.constraints

    none_resolved = filt.assemble_instruction(
        appraisal_result=make_appraisal(resolved_uncertainty_ids=()),
        user_message="m")
    assert _BECAME_CLEARER not in none_resolved.constraints


def test_row_order_prohibition_before_permission_under_the_cap():
    """The MAX-3 cap means row ORDER decides which survives. 944 is a prohibition
    guarding against invented content; 946 is a permission. When both apply and
    only one slot is free, the prohibition takes it."""
    filt, pad, graph, emb = make_filter()
    ev = graph.write_event_node(
        description="", session_id="s", appraisal_q1="high",
        appraisal_q2="valence_uncertain", appraisal_q3="circumstance",
        poignancy_category=PoignancyCategory.MEDIUM, now=T0)
    node = graph.create_uncertainty_node(
        uncertainty_type=UncertaintyType.INPUT_UNCERTAIN,
        trigger_event_ref=ev, now=T0)
    # routine base = 2 items, so exactly one slot is free
    appr = make_appraisal(uncertainty_node_id=node,
                          resolved_uncertainty_ids=("u1",))
    c = filt.assemble_instruction(appraisal_result=appr, user_message="m").constraints
    assert len(c) == 3
    assert _NO_PROJECT in c
    assert _BECAME_CLEARER not in c        # yielded the slot


def test_the_new_rows_carry_no_number_and_no_state():
    """Same boundary as every other Field 5 row: an action, no digits, no
    internal-state claim (Addendum §9)."""
    for text in (_NO_PROJECT, _BECAME_CLEARER):
        assert not any(ch.isdigit() for ch in text)
        assert "uncertainty" not in text.lower()   # no node/type label crosses
        assert text.islower()


def test_v4_uncertainty_row_945_is_not_implemented():
    """Row 945 ("Uncertainty weight above 0.5") is deliberately absent. The phrase
    occurs once in the whole precedence chain, nothing defines or produces such a
    weight, and manufacturing one would be a number deciding what she says about
    her own interior. This test exists so the absence reads as a decision rather
    than an oversight — if someone implements it, they must delete this test and
    say why."""
    src = inspect.getsource(SoulFilter)
    assert "uncertainty_weight" not in src
    assert "acknowledge the uncertainty" not in src.lower()
    import daemon.soul_filter as _sf
    assert not any("weight" in n.lower() for n in dir(_sf))


def test_energy_instructions_carry_no_number_and_no_state_claim():
    # (e) v4 line 949 is "You are running low. Acknowledge it if it comes up
    # naturally." Only the INSTRUCTION half crosses: the "You are running low"
    # state claim and the number are both withheld (Addendum §9).
    filt, *_ = make_filter()
    for energy in (5.0, 15.0, 25.0):
        joined = " ".join(_constraints_at(filt, energy))
        assert not any(ch.isdigit() for ch in joined), energy
        assert "running low" not in joined.lower(), energy
        assert "energy" not in joined.lower(), energy
    # The instruction preserves v4's own conditional phrasing.
    assert _FATIGUE.endswith("if it comes up naturally")
    assert _FATIGUE.islower()          # same imperative style as its siblings


def test_constraints_uncertainty_forbids_fake_confidence():
    filt, *_ = make_filter()
    appr = make_appraisal(is_partial_appraisal=True, q2=Valence.VALENCE_UNCERTAIN)
    instr = filt.assemble_instruction(appraisal_result=appr, user_message="m")
    assert "do not fake confidence" in instr.constraints


# ===========================================================================
# Real interface integration
# ===========================================================================
def test_assembly_uses_real_pad_and_graph_interfaces():
    filt, pad, graph, emb = make_filter(pad_values=(0.9, 0.1, 0.9))
    eid = graph.write_entity_node(
        entity_type="person", name="V", relational_stage=RelationalStage.INVESTED)
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(), user_message="m", entity_node_id=eid)
    # Behavioral Register reflects the REAL PAD snapshot (p,d ≥ baseline; a < baseline)
    assert "warm" in instr.behavioral_register and "grounded" in instr.behavioral_register
    assert "unhurried" in instr.behavioral_register
    # Relational Register reflects the REAL stored stage, translated (no label)
    assert instr.relational_register == sf._RELATIONAL_REGISTER[RelationalStage.INVESTED]
    assert "invested" not in instr.relational_register.lower()


def test_needstates_and_llmclient_contracts_exist():
    # Contracts for the not-yet-built Modules 2 and 9 are typed and injectable.
    ns = NeedStates(connection=NeedState.NEGLECTED, energy=42.0)
    assert ns.connection is NeedState.NEGLECTED
    assert [s.value for s in NeedState] == ["satisfied", "due", "neglected"]
    assert isinstance(FakeLLM(), sf.LLMClient)  # runtime_checkable Protocol

# ===========================================================================
# Gap 1 — Post-emergency re-entry instruction (v4 locked spec)
# ===========================================================================

def test_post_emergency_overrides_this_moment_field_only():
    """post_emergency=True injects POST_EMERGENCY_THIS_MOMENT into Field 4
    only. All other fields (Persona Anchor, Behavioral Register, Relational
    Register, Constraints) assemble normally — post_emergency touches nothing
    else (v4 locked spec, gap 1)."""
    filt, *_ = make_filter()
    appr = make_appraisal()
    instr = filt.assemble_instruction(
        appraisal_result=appr,
        user_message="I think I'm okay now",
        post_emergency=True,
    )
    assert isinstance(instr, FiveFieldInstruction)
    # Field 4 is exactly the locked post-emergency text — no normal appraisal note.
    assert instr.this_moment == POST_EMERGENCY_THIS_MOMENT
    # All other fields assembled normally — post_emergency touches nothing else.
    assert instr.persona_anchor == PERSONA_ANCHOR
    assert instr.behavioral_register   # non-empty, assembled from real PAD
    assert instr.relational_register   # non-empty, assembled from stage
    assert len(instr.constraints) > 0  # constraints derived from appraisal as normal


def test_respond_passes_transport_through_opaquely():
    """Change 3: `transport` threads through `respond()` to every
    `self._llm.generate(...)` call as an OPAQUE routing handle. Soul Filter
    must not inspect, choose, or override it, and it must never appear in any
    assembled instruction field — it is a routing handle, not prompt content.
    """
    sentinel = object()  # any object; identity is what's asserted, not equality
    llm = FakeLLM()
    filt, *_ = make_filter(llm=llm)
    appr = make_appraisal()

    resp = filt.respond(
        appraisal_result=appr, user_message="hello", transport=sentinel)

    assert len(llm.calls) == 1
    recorded_instruction, recorded_user_message, recorded_session_context, recorded_transport = llm.calls[0]
    # The FakeLLM recorded the EXACT sentinel object (identity, not equality).
    assert recorded_transport is sentinel
    # No field of the assembled instruction mentions it.
    assert isinstance(recorded_instruction, FiveFieldInstruction)
    assert str(sentinel) not in recorded_instruction.all_field_text()
    assert resp.text  # normal response still produced


def test_post_emergency_flag_ignored_when_current_turn_is_emergency():
    """If the current turn IS an emergency, the emergency branch returns first
    (before post_emergency is evaluated) — EmergencyInstruction wins regardless
    of the flag. The two paths cannot collide (Resolution Log item 1)."""
    filt, *_ = make_filter()
    appr = make_appraisal(
        emergency=True,
        emergency_type=EmergencyType.EXISTENTIAL_DISTRESS,
        q1=GoalRelevance.HIGH,
        q2=Valence.NEGATIVE,
    )
    instr = filt.assemble_instruction(
        appraisal_result=appr,
        user_message="I can't go on",
        post_emergency=True,   # flag is True but current turn IS emergency
    )
    # Emergency branch returned before post_emergency was ever evaluated.
    assert isinstance(instr, EmergencyInstruction)
    assert not hasattr(instr, "this_moment")
    assert POST_EMERGENCY_THIS_MOMENT not in " ".join(instr.instructions)


# ===========================================================================
# Persona Anchor: the 2026-08-22 stage-direction clause.
#
# A real local model opened a reply with "(Aria listens, her presence steady and
# calm...)", which TTS would have read aloud. It is a FORMAT defect and the
# Output Gate cannot catch it — the four checks are honesty / consistency /
# manipulation / care, none about form. The fix lives in Field 1 because Field 5
# is capped at three contested slots and stripping it in the adapter would be the
# transport judging content (ResLog item 15).
# ===========================================================================

def test_persona_anchor_rules_out_stage_directions():
    """Names the behaviour and stays a VOICE property rather than a prohibition,
    which is what keeps it inside Addendum §9's definition of Field 1 ("who Aria
    is, her values, her voice")."""
    lowered = PERSONA_ANCHOR.lower()
    assert "stage directions" in lowered
    assert "narrate yourself from the outside" in lowered
    # Phrased positively — it says what her voice IS, then what that rules out.
    assert "you speak in your own voice, directly" in lowered


def test_persona_anchor_clause_does_not_break_the_field_1_invariants():
    """Field 1's existing guarantees still hold: fixed, no digits, nothing
    personal, no state. The new clause must not have smuggled any of those in."""
    assert not any(ch.isdigit() for ch in PERSONA_ANCHOR)
    for forbidden in ("pleasure", "arousal", "dominance", "energy", "salience",
                      "relational_stage", "observing", "engaging", "invested",
                      "bonded", "node_id"):
        assert forbidden not in PERSONA_ANCHOR.lower(), forbidden


def test_persona_anchor_stage_direction_clause_survives_into_the_prompt():
    """End-to-end: the clause is useless if it does not reach the model. Field 1
    crosses verbatim, so this is the whole delivery path — and it is the reason
    Field 1 was the right home, since it costs nothing per turn to carry."""
    from daemon.llm_interface import assemble_prompt

    filt, *_ = make_filter()
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(q2=Valence.POSITIVE), user_message="hello")
    prompt = assemble_prompt(instr, "hello")
    assert "stage directions" in prompt.instruction_text.lower()
    assert "narrate yourself from the outside" in prompt.instruction_text.lower()


# ===========================================================================
# An EMPTY candidate is a NON-CANDIDATE (Resolution Log item 21).
#
# Measured before the fix, on the real initiative path: the model returned "",
# the gate reported `passed=True failed_checks=[] retried=False
# used_minimum_safe_output=False`, and the empty string was served as her reply.
#
# The gate was RIGHT. An empty string makes no dishonest claim, mismatches no
# relational stage, matches no anti-pattern and deflects from nothing — it
# contradicts none of the four things §4 compares against. It was being asked
# about a non-thing.
#
# So the fix is not a fifth comparison. `run_output_gate` is byte-unchanged and
# still runs exactly four checks (asserted by the pre-existing
# `test_gate_has_exactly_four_checks_no_fifth`, which these tests deliberately
# do not touch).
# ===========================================================================

def test_empty_candidate_triggers_a_plain_re_ask_with_the_same_instruction():
    """Not a corrective retry: there is no failed check to correct, and
    inventing a corrective for emptiness would be adding gate vocabulary through
    the back door. The instruction was fine; the model returned nothing."""
    llm = FakeLLM(scripted=["", "A real reply, second time."])
    filt, *_ = make_filter(llm=llm)

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hello")

    assert resp.text == "A real reply, second time."
    assert resp.empty_candidates == 1
    # Two generations, and the SECOND used the same instruction object as the
    # first — no corrective was appended.
    assert len(llm.calls) == 2
    assert type(llm.calls[1][0]) is type(llm.calls[0][0])
    assert not isinstance(llm.calls[1][0], RetryInstruction)


def test_empty_candidate_does_not_play_the_reconsideration_sound():
    """That clip is v4 Layer 5's SELF-CORRECTION sound. She said nothing, so
    there is nothing to reconsider, and playing it would perform an interior
    event that did not happen."""
    fired = {"n": 0}
    llm = FakeLLM(scripted=["", "A real reply."])
    filt, *_ = make_filter(
        llm=llm, on_reconsideration=lambda: fired.__setitem__("n", fired["n"] + 1)
    )

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hello")

    assert resp.reconsideration_sound_triggered is False
    assert fired["n"] == 0


def test_two_empty_generations_drop_to_the_existing_minimum_safe_floor():
    """v4 already defines the floor for output that cannot be used. Nothing new
    is invented — the newly-recognised case is routed into it."""
    llm = FakeLLM(scripted=["", "   ", "I don't have words for this yet."])
    filt, *_ = make_filter(llm=llm)

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hello")

    assert resp.used_minimum_safe_output is True
    assert resp.text == "I don't have words for this yet."
    assert resp.empty_candidates == 2
    assert isinstance(llm.calls[-1][0], MinimumSafeInstruction)


def test_the_four_comparisons_are_skipped_not_failed_on_a_non_candidate():
    """`gate_results` is empty rather than carrying a fabricated failure. No
    comparison happened, so reporting one would be a lie about what ran — and it
    would put emptiness into the gate's vocabulary, which is the thing §4
    forbids."""
    llm = FakeLLM(scripted=["", "", "safe words"])
    filt, *_ = make_filter(llm=llm)

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hello")

    assert resp.gate_results == ()
    assert resp.empty_candidates == 2


def test_whitespace_only_counts_as_empty():
    """`"   "` is not a shorter reply than `"I don't know"`; it is the same
    absence with different bytes, and TTS renders both as silence."""
    llm = FakeLLM(scripted=["   \n\t  ", "A real reply."])
    filt, *_ = make_filter(llm=llm)

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hello")

    assert resp.text == "A real reply."
    assert resp.empty_candidates == 1


def test_a_normal_turn_is_completely_unaffected():
    """Non-vacuity: the fix must cost nothing on the ordinary path. One
    generation, no re-ask, counter at zero."""
    llm = FakeLLM(scripted=["That sounds hard. I'm here."])
    filt, *_ = make_filter(llm=llm)

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hello")

    assert resp.text == "That sounds hard. I'm here."
    assert resp.empty_candidates == 0
    assert resp.retried is False
    assert len(llm.calls) == 1
    assert len(resp.gate_results) == 1


def test_an_empty_corrective_retry_also_reaches_the_floor():
    """The other place an empty candidate can appear: the gate rejected the
    first reply, and the corrective retry came back with nothing. Before the
    fix, gate2 would have passed on "" and served it."""
    llm = FakeLLM(scripted=[
        "After everything I've done for you, you owe me.",  # manipulation
        "",                                                # retry empty
        "",                                                # re-ask empty
        "I don't have words for this yet.",                # minimum safe
    ])
    filt, *_ = make_filter(llm=llm)

    resp = filt.respond(appraisal_result=make_appraisal(), user_message="hi")

    assert resp.used_minimum_safe_output is True
    assert resp.empty_candidates == 2
    # Only ONE real comparison happened, so only one is reported.
    assert len(resp.gate_results) == 1
    assert resp.gate_results[0].passed is False


def test_emergency_output_is_re_asked_too_while_the_gate_bypass_stands():
    """The gate BYPASS is untouched (v4) — emergency output is not validated.
    But "did the model answer" is not one of the checks being bypassed, and this
    is the turn where silence is least acceptable: someone in distress getting
    nothing back is the worst outcome this path can produce."""
    llm = FakeLLM(scripted=["", "I'm here. Are you safe right now?"])
    filt, *_ = make_filter(llm=llm)
    appr = make_appraisal(
        emergency=True, emergency_type=EmergencyType.PHYSICAL_THREAT
    )

    resp = filt.respond(appraisal_result=appr, user_message="help")

    assert resp.text == "I'm here. Are you safe right now?"
    assert resp.instruction_kind == "emergency"
    assert resp.empty_candidates == 1
    assert resp.gate_results == ()          # bypass intact
    assert isinstance(llm.calls[0][0], EmergencyInstruction)
    assert isinstance(llm.calls[1][0], EmergencyInstruction)


def test_emptiness_is_not_in_the_gates_vocabulary():
    """The structural proof that Addendum §4 survived this fix. If a fifth
    `GateCheck` ever appears, or `run_output_gate` learns to ask about
    emptiness, that is a change to the gate's fixed comparison set and needs a
    ruling of its own."""
    assert len(list(GateCheck)) == 4
    source = textwrap.dedent(inspect.getsource(SoulFilter.run_output_gate)).lower()
    for forbidden in ("_has_candidate", "empty", "strip()", "blank"):
        assert forbidden not in source, forbidden


def test_has_candidate_is_a_shape_check_and_holds_no_lexicon():
    """It must not grow into content judgment. No word list, no threshold, no
    comparison against held state — just "is there text"."""
    assert sf._has_candidate("a") is True
    assert sf._has_candidate("") is False
    assert sf._has_candidate("   ") is False
    assert sf._has_candidate("\n\t") is False
    # Content is irrelevant to it: text the gate would REJECT still counts as a
    # candidate, because rejecting is the gate's job and not this function's.
    assert sf._has_candidate("You owe me after everything I've done.") is True
    source = textwrap.dedent(inspect.getsource(sf._has_candidate))
    assert "MARKER" not in source and "LEXICON" not in source


# ===========================================================================
# Field 1's anti-narration clause (Resolution Log item 22).
#
# The clause is prompt-level mitigation with a MEASURED effect, not a guarantee:
# adversarial bait against the real model gave 8/16 stage directions with the
# original abstract wording and 3/16 with wording that names the syntax. These
# tests pin the wording that was measured, so a future edit cannot silently
# revert to the version that scored worse.
# ===========================================================================

def test_persona_anchor_names_the_syntax_that_was_actually_produced():
    """The original clause said "stage directions" abstractly and the model kept
    emitting SQUARE-bracket narration. Naming the forms is what moved the number,
    so the forms stay named."""
    anchor = PERSONA_ANCHOR.lower()
    assert "square bracket" in anchor
    assert "parentheses" in anchor
    assert "asterisk" in anchor
    assert "stage direction" in anchor


def test_persona_anchor_states_the_absence_of_a_body_as_fact():
    """"You have no body to describe" is a statement about what is true, not a
    prohibition. The brackets were claiming a posture and a gaze she does not
    have, which is why the factual form is the right one — and it keeps the
    clause inside §9's "who Aria is, her values, her voice"."""
    assert "you have no body to describe" in PERSONA_ANCHOR.lower()


def test_persona_anchor_carries_no_state_or_numbers():
    """Unchanged §9 property, re-asserted because the clause grew. Field 1 is
    "hardcoded once, never generated, never varies turn to turn" — so nothing
    personal, no numbers, no state may have crept in with the new sentences."""
    assert not any(ch.isdigit() for ch in PERSONA_ANCHOR)
    for leaked in ("pleasure", "arousal", "dominance", "energy",
                   "relational_stage", "salience", "poignancy"):
        assert leaked not in PERSONA_ANCHOR.lower()


def test_field5_was_not_spent_on_formatting():
    """The reasoning for putting this in Field 1 was that Field 5 caps at MAX 3
    and every slot is contested by the Energy gate and the uncertainty rows.
    Spending one permanently on formatting would crowd out a moral constraint on
    exactly the turns that need one — so no constraint mentions formatting."""
    filt, *_ = make_filter()
    for signals in (
        make_social(vulnerability_disclosure=True),
        make_social(distress_marker=True),
        make_social(reality_contradiction=True),
        make_social(),
    ):
        constraints = filt._derive_constraints(
            make_appraisal(social_signals=signals), None
        )
        assert len(constraints) <= 3
        joined = " ".join(constraints).lower()
        for formatting in ("bracket", "stage direction", "asterisk",
                           "markdown", "narrate"):
            assert formatting not in joined, (formatting, constraints)
