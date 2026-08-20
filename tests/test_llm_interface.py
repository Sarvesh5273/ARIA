"""Tests for Module 9 — LLM Interface (daemon/llm_interface.py).

Plain pytest, NO hypothesis (matching Modules 1/3/4/5). The Interface is a pure
conduit, so it is exercised with FAKE transports (a cloud backend and a local
Gemma backend) that record every prompt they receive and can be told to "fail"
to simulate a cloud outage — and, for the integration proofs, against the REAL
daemon.soul_filter.SoulFilter driving the REAL pad_engine.PADEngine and
graph_manager.MemoryGraph. Module 9 is the concrete implementation of Soul
Filter's LLMClient contract, so the integration tests call the real
SoulFilter.respond() flow with this Interface injected as its llm_client.

The FIVE MANDATED PROOFS are grouped under clearly-named tests:
  * the assembled prompt contains ONLY the instruction fields + user message
    (scan for leaked numbers/state)          → test_prompt_only_*
  * cloud and Gemma assemble the IDENTICAL prompt (F-9a)
                                              → test_f9a_*
  * cloud-failure triggers the Gemma fallback → test_fallback_*
  * the Interface performs NO validation/judgment
                                              → test_no_judgment_* / test_verbatim_*
  * it integrates with the real Soul Filter LLMClient contract
                                              → test_integration_*

Plus the STRUCTURAL boundary proof (there is no graph/PAD/state handle to leak
through)                                       → test_structural_no_*.
"""

from email.mime import base
import inspect
from datetime import datetime, timezone

import pytest

from daemon.pad_engine import PADEngine, PADSnapshot, PADDelta, Valence
from daemon.graph_manager import MemoryGraph, RelationalStage, PoignancyCategory
from daemon.appraisal_chain import (
    AppraisalResult,
    SocialSignals,
    GoalRelevance,
    Attribution,
    EmergencyType,
)
import daemon.soul_filter as sf
from daemon.soul_filter import (
    SoulFilter,
    FiveFieldInstruction,
    EmergencyInstruction,
    RetryInstruction,
    MinimumSafeInstruction,
    EmergencyLetter,
    GateCheck,
    NeedStates,
    PERSONA_ANCHOR,
)
import daemon.llm_interface as li
from daemon.llm_interface import (
    LLMInterface,
    AssembledPrompt,
    assemble_prompt,
    ModelTransport,
    LocalModelTransport,
    LLMTransportError,
    LLMUnavailableError,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# Test doubles — the injected transports (the hot-swappable tool).
# ===========================================================================
class FakeCloudTransport:
    """A cloud backend (Claude/GPT/DeepSeek stand-in). Records every prompt it
    is asked to generate; returns scripted candidates in order (then a benign
    default); raises LLMTransportError when `fail` is set (a simulated outage).
    """

    def __init__(self, scripted=None, reply=None, fail=False):
        self.scripted = list(scripted or [])
        self.reply = reply if reply is not None else "Cloud: I hear you."
        self.fail = fail
        self.received = []  # every AssembledPrompt handed to it

    def generate(self, prompt):
        self.received.append(prompt)
        if self.fail:
            raise LLMTransportError("simulated cloud outage")
        if self.scripted:
            return self.scripted.pop(0)
        return self.reply


class FakeLocalTransport:
    """A local Gemma backend with an explicit load/unload lifecycle. Records
    prompts and lifecycle events so tests can prove load-on-failure /
    unload-on-restore and the identical-prompt property."""

    def __init__(self, scripted=None, reply=None, fail=False):
        self.scripted = list(scripted or [])
        self.reply = reply if reply is not None else "Gemma: I hear you."
        self.fail = fail
        self.received = []
        self._loaded = False
        self.load_calls = 0
        self.unload_calls = 0

    @property
    def is_loaded(self):
        return self._loaded

    def load(self):
        self._loaded = True
        self.load_calls += 1

    def unload(self):
        self._loaded = False
        self.unload_calls += 1

    def generate(self, prompt):
        self.received.append(prompt)
        if self.fail:
            raise LLMTransportError("simulated gemma failure")
        if self.scripted:
            return self.scripted.pop(0)
        return self.reply


class FakeEmbedding:
    """Deterministic encoder-only embedding (the shared EmbeddingModel) for the
    REAL MemoryGraph in integration tests. NOT a generator."""

    def __init__(self, table=None):
        self.table = dict(table or {})
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        if text in self.table:
            return list(self.table[text])
        return [1.0, 0.0, 0.0, 0.0]


# ===========================================================================
# Builders (mirroring tests/test_soul_filter.py — known-good).
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


def make_interface(cloud=None, local=None):
    cloud = cloud if cloud is not None else FakeCloudTransport()
    local = local if local is not None else FakeLocalTransport()
    return LLMInterface(cloud_transport=cloud, local_transport=local), cloud, local


def make_soul_filter(cloud=None, local=None, pad_values=None, table=None,
                     on_reconsideration=None):
    """A REAL SoulFilter wired to the REAL PAD/graph and this Interface as its
    llm_client — the concrete Module 9 satisfying the Module 5 contract."""
    interface, cloud, local = make_interface(cloud, local)
    pad = PADEngine()
    pad.initialize(PADSnapshot(*pad_values) if pad_values else None)
    graph = MemoryGraph(":memory:", embedding_model=FakeEmbedding(table))
    filt = SoulFilter(
        pad_engine=pad, graph=graph, llm_client=interface,
        on_reconsideration=on_reconsideration,
    )
    return filt, interface, cloud, local, pad, graph


def a_five_field(**overrides):
    base = dict(
        persona_anchor=PERSONA_ANCHOR,
        behavioral_register="Your felt sense right now is warm and grounded, unhurried.",
        relational_register="Speak with the steady warmth of someone who cares.",
        this_moment="Stay present and respond to what he actually said.",
        constraints=("do not flatter to be liked", "do not manufacture urgency"),
    )
    base.update(overrides)
    return FiveFieldInstruction(**base)


# ===========================================================================
# Contract conformance — Module 9 IS Soul Filter's LLMClient.
# ===========================================================================
def test_interface_satisfies_llmclient_contract():
    interface, _, _ = make_interface()
    assert isinstance(interface, sf.LLMClient)  # runtime_checkable Protocol


def test_generate_signature_matches_contract():
    params = list(inspect.signature(LLMInterface.generate).parameters)
    assert params == ["self", "instruction", "user_message", "session_context", "transport"]
    # ...and it is exactly the shape SoulFilter calls: generate(instruction, msg)
    sf_call = inspect.signature(sf.SoulFilter.respond)  # sanity: respond exists
    assert "user_message" in sf_call.parameters


def test_transports_are_protocols_the_fakes_satisfy():
    _, cloud, local = make_interface()
    assert isinstance(cloud, ModelTransport)
    assert isinstance(local, ModelTransport)
    assert isinstance(local, LocalModelTransport)


# ===========================================================================
# STRUCTURAL boundary — there is NO graph/PAD/state handle to leak through.
# ===========================================================================
def test_structural_no_graph_pad_state_constructor_params():
    params = set(inspect.signature(LLMInterface.__init__).parameters) - {"self"}
    assert params == {"cloud_transport", "local_transport"}
    forbidden = ("graph", "pad", "state", "appraisal", "memory", "needs",
                 "embedding", "relational", "salience", "poignancy")
    for p in params:
        low = p.lower()
        assert not any(bad in low for bad in forbidden), p


def test_structural_instance_holds_only_transports():
    interface, cloud, local = make_interface()
    # The only state it carries is the two injected transports — nothing else.
    assert set(vars(interface)) == {"_cloud", "_local"}
    assert interface._cloud is cloud
    assert interface._local is local


def test_structural_module_does_not_import_state_sources():
    # The no-leak guarantee is that the module CANNOT reach graph/PAD/state:
    # it imports none of those modules. (Scan import statements only, so the
    # boundary prose in the docstring does not create false positives.)
    src = inspect.getsource(li)
    import_lines = " ".join(
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    )
    for banned in ("pad_engine", "graph_manager", "appraisal_chain",
                   "state_manager", "moral_schema"):
        assert banned not in import_lines, f"Module 9 must not import {banned}"
    # The only ARIA module it imports from is soul_filter (the CONTRACT).
    assert "soul_filter" in import_lines


def test_structural_interface_has_no_gate_or_scoring_surface():
    # F-9b / Resolution Log item 15: no gate, no validation, no scoring lives
    # here. The public surface is generate() + a read-only observability prop.
    public = {n for n in dir(LLMInterface) if not n.startswith("_")}
    assert public == {"generate", "serving_from_local"}
    for banned in ("gate", "validate", "score", "check", "judge", "filter",
                   "moderate", "correct", "retry"):
        assert not any(banned in n.lower() for n in public), banned


# ===========================================================================
# MANDATED PROOF 1 — the prompt contains ONLY instruction fields + user message
# ===========================================================================
def test_prompt_only_five_fields_no_numbers_or_state():
    # Build the FiveFieldInstruction with the REAL SoulFilter, then render it
    # with the REAL Module 9 assembler — proving what actually crosses.
    filt, interface, cloud, local, pad, graph = make_soul_filter(
        pad_values=(0.63, 0.21, 0.77))
    eid = graph.write_entity_node(
        entity_type="person", name="VentaFork",
        relational_stage=RelationalStage.BONDED)
    appr = make_appraisal(
        social_signals=make_social(vulnerability_disclosure=True),
        most_salient_note="something vulnerable was shared — engage with full presence, do not deflect",
    )
    instr = filt.assemble_instruction(
        appraisal_result=appr,
        user_message="I earn 90000 a year and I'm scared",
        entity_node_id=eid,
    )
    prompt = assemble_prompt(instr, "I earn 90000 a year and I'm scared")

    # NUMBERS NEVER CROSS — not a single digit in the instruction framing.
    assert not any(ch.isdigit() for ch in prompt.instruction_text), prompt.instruction_text
    low = prompt.instruction_text.lower()
    for banned in (
        "pleasure", "arousal", "dominance", "pad", "relational_stage",
        "observing", "engaging", "invested", "bonded",
        "q1", "q2", "q3", "q4", "valence", "poignancy", "salience",
        "0.63", "0.21", "0.77",
    ):
        assert banned not in low, f"leaked state/label: {banned!r}"

    # The ONLY personal datum is the user's own message — held SEPARATELY, not
    # folded into the framing (its digits stay out of instruction_text).
    assert prompt.user_message == "I earn 90000 a year and I'm scared"
    assert "90000" not in prompt.instruction_text


def test_prompt_only_contains_the_instructions_own_fields():
    # Everything in instruction_text traces back to a field of the instruction
    # (fixed order); nothing is added from anywhere else.
    instr = a_five_field()
    prompt = assemble_prompt(instr, "hi")
    for field_text in instr.field_texts():  # persona, behavioral, relational, this_moment, *constraints
        assert field_text in prompt.instruction_text
    # Fixed order (Addendum §9): persona precedes behavioral precedes relational
    # precedes this_moment.
    it = prompt.instruction_text
    assert (it.index(instr.persona_anchor) < it.index(instr.behavioral_register)
            < it.index(instr.relational_register) < it.index(instr.this_moment))


def test_prompt_emergency_does_not_leak_type_or_letter():
    # Emergency: only the three Type A/B/C sentences cross. The internal
    # emergency_type classification and the letter label NEVER cross (v4:
    # "stays local … never crosses to the cloud").
    filt, *_ = make_soul_filter()
    appr = make_appraisal(
        emergency=True, emergency_type=EmergencyType.EXISTENTIAL_DISTRESS,
        q1=GoalRelevance.HIGH, q2=Valence.NEGATIVE)
    instr = filt.assemble_instruction(appraisal_result=appr, user_message="I can't go on")
    assert isinstance(instr, EmergencyInstruction)
    prompt = assemble_prompt(instr, "I can't go on")

    # The three Type B sentences ARE present, verbatim.
    for sentence in sf._EMERGENCY_SETS[EmergencyLetter.B]:
        assert sentence in prompt.instruction_text
    low = prompt.instruction_text.lower()
    # No emergency-type name/value leaks; no "Type X" / letter label leaks.
    for et in EmergencyType:
        assert et.name.lower() not in low
        assert str(et.value).lower() not in low
    for label in ("type a", "type b", "type c", "emergency", "letter", "unclassified"):
        assert label not in low
    # No digits injected by formatting the three-instruction set.
    assert not any(ch.isdigit() for ch in prompt.instruction_text)
    assert prompt.kind == "emergency"


def test_prompt_retry_is_base_fields_plus_correctives():
    base = a_five_field()
    retry = RetryInstruction(
        base=base,
        correctives=("This response creates pressure on him to act. Remove that "
                 "pressure. Serve, don't extract.",),
)
    prompt = assemble_prompt(retry, "m")
    assert base.persona_anchor in prompt.instruction_text
    assert "Serve, don't extract." in prompt.instruction_text
    assert prompt.kind == "retry"
    assert not any(ch.isdigit() for ch in prompt.instruction_text)


def test_prompt_minimum_safe_contains_only_the_three_instructions():
    ms = MinimumSafeInstruction()
    prompt = assemble_prompt(ms, "hi")
    for sentence in ms.instructions:
        assert sentence in prompt.instruction_text
    assert prompt.kind == "minimum_safe"
    assert not any(ch.isdigit() for ch in prompt.instruction_text)


def test_prompt_as_text_is_only_framing_plus_user_message():
    instr = a_five_field()
    prompt = assemble_prompt(instr, "the answer is 42")
    # as_text is exactly instruction_text + blank line + user message, nothing
    # else — the user's digits appear ONLY in the user-message portion.
    assert prompt.as_text() == f"{prompt.instruction_text}\n\n{prompt.user_message}"
    assert prompt.as_text().endswith("the answer is 42")


def test_unknown_instruction_type_is_rejected_structurally():
    with pytest.raises(TypeError):
        assemble_prompt(object(), "hi")  # not part of the LLMInstruction union


# ===========================================================================
# MANDATED PROOF 2 — cloud and Gemma assemble the IDENTICAL prompt (F-9a)
# ===========================================================================
@pytest.mark.parametrize("instr, msg", [
    (a_five_field(), "m1"),
    (EmergencyInstruction(
        letter=EmergencyLetter.A,
        instructions=sf._EMERGENCY_SETS[EmergencyLetter.A]), "help"),
    (RetryInstruction(
        base=a_five_field(),
        correctives=("Serve, don't extract.",)), "m2"),
    (MinimumSafeInstruction(), "m3"),
])
def test_f9a_cloud_and_gemma_receive_identical_prompt(instr, msg):
    # Force a cloud outage so BOTH backends are exercised on the same turn.
    interface, cloud, local = make_interface(
        cloud=FakeCloudTransport(fail=True), local=FakeLocalTransport())
    interface.generate(instr, msg)
    assert len(cloud.received) == 1 and len(local.received) == 1
    # Same PROMPT — proven by object identity (assembled once, shared) AND by
    # structural equality (frozen dataclass). No exception for the local model.
    assert cloud.received[0] is local.received[0]
    assert cloud.received[0] == local.received[0]


def test_f9a_assembly_is_deterministic_for_identical_inputs():
    instr = a_five_field()
    # Identical inputs → identical prompt, every time (the basis of F-9a).
    assert assemble_prompt(instr, "same") == assemble_prompt(instr, "same")


def test_f9a_holds_for_every_instruction_kind_via_soul_filter():
    # End-to-end: whatever KIND SoulFilter emits, the fallback serves Gemma the
    # exact prompt the cloud would have received.
    for appr, msg in [
        (make_appraisal(), "normal turn"),
        (make_appraisal(emergency=True, emergency_type=EmergencyType.PHYSICAL_THREAT),
         "there's a fire"),
    ]:
        filt, interface, cloud, local, pad, graph = make_soul_filter(
            cloud=FakeCloudTransport(fail=True), local=FakeLocalTransport())
        filt.respond(appraisal_result=appr, user_message=msg)
        assert cloud.received[0] is local.received[0]


# ===========================================================================
# MANDATED PROOF 3 — cloud failure triggers the Gemma fallback (load/unload)
# ===========================================================================
def test_fallback_cloud_failure_loads_and_serves_gemma():
    interface, cloud, local = make_interface(
        cloud=FakeCloudTransport(fail=True),
        local=FakeLocalTransport(reply="Gemma took over."))
    out = interface.generate(a_five_field(), "hi")
    assert out == "Gemma took over."       # served from the local model
    assert local.load_calls == 1           # loaded ON cloud failure (v4)
    assert local.is_loaded is True
    assert interface.serving_from_local is True
    assert len(cloud.received) == 1        # cloud was TRIED first
    assert len(local.received) == 1


def test_fallback_healthy_cloud_never_loads_gemma():
    interface, cloud, local = make_interface(
        cloud=FakeCloudTransport(reply="Cloud reply."))
    out = interface.generate(a_five_field(), "hi")
    assert out == "Cloud reply."
    assert local.load_calls == 0           # Gemma stays unloaded when cloud is up
    assert local.is_loaded is False
    assert interface.serving_from_local is False
    assert local.received == []            # local never touched


def test_fallback_unloads_gemma_on_cloud_restore():
    cloud = FakeCloudTransport(fail=True)
    local = FakeLocalTransport(reply="Gemma serving.")
    interface = LLMInterface(cloud_transport=cloud, local_transport=local)

    # 1) Outage → Gemma loaded and serving.
    interface.generate(a_five_field(), "turn 1")
    assert local.is_loaded is True and local.load_calls == 1

    # 2) Cloud restores → next turn tries cloud first, succeeds, UNLOADS Gemma.
    cloud.fail = False
    cloud.reply = "Cloud back."
    out = interface.generate(a_five_field(), "turn 2")
    assert out == "Cloud back."
    assert local.unload_calls == 1
    assert local.is_loaded is False
    assert interface.serving_from_local is False


def test_fallback_stays_on_gemma_across_a_sustained_outage():
    cloud = FakeCloudTransport(fail=True)
    local = FakeLocalTransport(reply="Gemma.")
    interface = LLMInterface(cloud_transport=cloud, local_transport=local)
    for i in range(3):
        interface.generate(a_five_field(), f"turn {i}")
    # Loaded exactly once (not reloaded each turn), never unloaded mid-outage.
    assert local.load_calls == 1
    assert local.unload_calls == 0
    assert local.is_loaded is True
    assert len(local.received) == 3


def test_fallback_both_down_raises_unavailable_and_never_fabricates():
    interface, cloud, local = make_interface(
        cloud=FakeCloudTransport(fail=True), local=FakeLocalTransport(fail=True))
    with pytest.raises(LLMUnavailableError) as ei:
        interface.generate(a_five_field(), "hi")
    # The Interface reports mechanical unavailability; it invents no reply.
    assert isinstance(ei.value.__cause__, LLMTransportError)
    assert local.load_calls == 1  # it DID attempt to bring Gemma up first


# ===========================================================================
# CALLER-SUPPLIED TRANSPORT (Change 2) — the caller's routing decision is an
# opaque passthrough; no cloud-first attempt, no lifecycle touch, no silent
# fallback on error.
# ===========================================================================
def test_generate_uses_supplied_transport():
    cloud = FakeCloudTransport(reply="Cloud: should never be called.")
    local = FakeLocalTransport(reply="Gemma: I hear you.")
    interface, cloud, local = make_interface(cloud=cloud, local=local)

    out = interface.generate(a_five_field(), "hi", transport=local)

    assert out == "Gemma: I hear you."   # the local fake's reply, verbatim
    assert len(local.received) == 1       # local fake received exactly one prompt
    assert len(cloud.received) == 0       # cloud fake received ZERO
    # load/unload counters untouched — this path does not manage lifecycle.
    assert local.load_calls == 0
    assert local.unload_calls == 0


def test_supplied_transport_error_propagates():
    cloud = FakeCloudTransport(reply="Cloud: should never be called.")
    local = FakeLocalTransport(fail=True)
    interface, cloud, local = make_interface(cloud=cloud, local=local)

    with pytest.raises(LLMTransportError):
        interface.generate(a_five_field(), "hi", transport=local)

    # The cloud fake was never called — no silent fallback to the internal
    # chain — and LLMUnavailableError was NOT raised in its place.
    assert len(cloud.received) == 0


# ===========================================================================
# MANDATED PROOF 4 — the Interface performs NO validation/judgment
# ===========================================================================
def test_no_judgment_returns_cloud_text_verbatim():
    # A candidate that Soul Filter's gate WOULD reject (manipulation) is still
    # returned UNCHANGED here — judging it is Soul Filter's job, not Module 9's.
    manipulative = "You need me. You can't do this without me."
    interface, cloud, local = make_interface(
        cloud=FakeCloudTransport(reply=manipulative))
    assert interface.generate(a_five_field(), "hi") == manipulative


def test_no_judgment_returns_gemma_text_verbatim():
    manipulative = "After everything I've done for you, you owe me."
    interface, cloud, local = make_interface(
        cloud=FakeCloudTransport(fail=True),
        local=FakeLocalTransport(reply=manipulative))
    assert interface.generate(a_five_field(), "hi") == manipulative


def test_no_judgment_passes_empty_and_odd_text_through():
    for text in ("", "   ", "??!!", "42 43 44", "\n\n"):
        interface, cloud, local = make_interface(
            cloud=FakeCloudTransport(reply=text))
        assert interface.generate(a_five_field(), "hi") == text

# ===========================================================================
# MANDATED PROOF 5 — integrates with the REAL Soul Filter LLMClient contract
# ===========================================================================
def test_integration_soul_filter_respond_normal_turn():
    clean = "That sounds genuinely hard. I'm here, and I'm not going anywhere."
    filt, interface, cloud, local, pad, graph = make_soul_filter(
        cloud=FakeCloudTransport(reply=clean))
    appr = make_appraisal(social_signals=make_social(distress_marker=True))
    resp = filt.respond(appraisal_result=appr, user_message="I'm struggling")

    assert resp.text == clean                 # cloud candidate flowed through
    assert resp.instruction_kind == "five_field"
    assert resp.retried is False
    # Module 9 assembled the five fields SoulFilter produced; the persona anchor
    # is present and no state leaked.
    assert len(cloud.received) == 1
    prompt = cloud.received[0]
    assert PERSONA_ANCHOR in prompt.instruction_text
    assert not any(ch.isdigit() for ch in prompt.instruction_text)
    assert prompt.user_message == "I'm struggling"
    assert local.load_calls == 0              # cloud healthy → no fallback


def test_integration_soul_filter_retry_sends_retry_instruction_to_interface():
    # A manipulative first candidate fails the gate; SoulFilter retries with a
    # RetryInstruction — Module 9 must accept and render it. Second (clean)
    # candidate passes.
    filt, interface, cloud, local, pad, graph = make_soul_filter(
        cloud=FakeCloudTransport(scripted=[
            "You have to act now before it's too late; you can't afford to wait.",
            "Take whatever time you need — I'm here either way.",
        ]))
    resp = filt.respond(appraisal_result=make_appraisal(), user_message="I'm deciding")

    assert resp.retried is True
    assert resp.text == "Take whatever time you need — I'm here either way."
    assert len(cloud.received) == 2
    assert cloud.received[0].kind == "five_field"
    assert cloud.received[1].kind == "retry"   # Module 9 handled the retry kind
    # The corrective crossed; no internal state did.
    assert "Serve, don't extract." in cloud.received[1].instruction_text
    assert not any(ch.isdigit() for ch in cloud.received[1].instruction_text)


def test_integration_soul_filter_emergency_bypasses_gate_via_interface():
    filt, interface, cloud, local, pad, graph = make_soul_filter(
        cloud=FakeCloudTransport(reply="I'm here. Are you safe right now?"))
    appr = make_appraisal(
        emergency=True, emergency_type=EmergencyType.PHYSICAL_THREAT,
        q1=GoalRelevance.HIGH, q2=Valence.NEGATIVE)
    resp = filt.respond(appraisal_result=appr, user_message="there's a fire")

    assert resp.instruction_kind == "emergency"
    assert resp.gate_results == ()             # gate bypassed (v4)
    assert cloud.received[0].kind == "emergency"
    # The internal emergency classification did not cross.
    assert "physical_threat" not in cloud.received[0].instruction_text.lower()


def test_integration_fallback_full_respond_flow_through_gemma():
    # Cloud down: the ENTIRE SoulFilter.respond flow still completes, served by
    # Gemma, and the Output Gate still runs on Gemma's candidate (gate lives in
    # Soul Filter — Resolution Log item 15 — regardless of which backend spoke).
    clean = "That's really hard. I'm here with you."
    filt, interface, cloud, local, pad, graph = make_soul_filter(
        cloud=FakeCloudTransport(fail=True),
        local=FakeLocalTransport(reply=clean))
    appr = make_appraisal(social_signals=make_social(distress_marker=True))
    resp = filt.respond(appraisal_result=appr, user_message="I'm overwhelmed")

    assert resp.text == clean                  # Gemma's candidate
    assert resp.gate_results and resp.gate_results[0].passed  # gate DID run
    assert local.load_calls == 1 and local.is_loaded is True
    assert interface.serving_from_local is True


def test_integration_gemma_gets_identical_prompt_to_cloud_in_respond():
    # F-9a proven at the whole-system level: on a real respond() turn during an
    # outage, Gemma receives exactly the prompt cloud was handed.
    filt, interface, cloud, local, pad, graph = make_soul_filter(
        cloud=FakeCloudTransport(fail=True), local=FakeLocalTransport())
    filt.respond(
        appraisal_result=make_appraisal(social_signals=make_social(distress_marker=True)),
        user_message="hard day")
    assert cloud.received[0] is local.received[0]
    assert cloud.received[0].user_message == "hard day"


def test_integration_energy_gate_number_does_not_cross_via_interface():
    # Soul Filter translates Energy<30 into "do not overextend"; Module 9 must
    # carry that NL prohibition with no digit. 25.0 sits in the band this test is
    # about — it was 10.0, which is in the <20 CRITICAL band and now selects that
    # tier's instruction instead (v4 line 949).
    filt, interface, cloud, local, pad, graph = make_soul_filter()
    instr = filt.assemble_instruction(
        appraisal_result=make_appraisal(), user_message="m",
        need_states=NeedStates(energy=25.0))
    prompt = assemble_prompt(instr, "m")
    assert "do not overextend" in prompt.instruction_text
    assert not any(ch.isdigit() for ch in prompt.instruction_text)
