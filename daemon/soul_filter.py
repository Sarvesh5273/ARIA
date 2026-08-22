

"""ARIA — Module 5: Soul Filter (`daemon/soul_filter.py`).

Responsibility (`ARIA_Module_Build_Plan.md`, Module 5): translate Aria's
internal state into exactly five natural-language fields (Persona Anchor,
Behavioral Register, Relational Register, This Moment, Constraints) plus the
user's current message for the LLM, and run the Output Validation Gate (four
structural comparisons, `ARIA_Soul_Spec_v4_Addendum.md` §4) on the LLM
candidate before TTS.

Soul_Filter is the BUFFER between Aria's interior and the language model
(Addendum §9, grounded in ACT-R/Soar: "Soul_filter is the buffer. The LLM is a
downstream module. It never sees inside."). It is a *blind language renderer*
(v4 "Soul Filter — Blind Language Renderer").

------------------------------------------------------------------------------
THE INVIOLABLE BOUNDARY (steering/project-rules.md "Five-field LLM boundary";
Addendum §9 "what crosses / what never crosses"):
  * NUMBERS NEVER CROSS. Behavioral Register is PAD translated to NL descriptors
    only ("warm and grounded, unhurried" — never "Pleasure: 0.6").
  * STATE NEVER CROSSES. Relational Register is relational_stage translated to
    NL — never the stage label ("bonded").
  * No PAD numbers, no graph data/contents, no relational_stage label, no needs
    states as data, no Q1–Q4 values, no appraisal vectors, no memory contents
    ever appear in any field.
  * The ONLY personal data that crosses is the user's current message.

THE GATE (Addendum §4): four STRUCTURAL comparisons, each against something
Aria's state ALREADY holds. ZERO LLM calls — no cloud, no Gemma. It VERIFIES,
it never DECIDES (Principle 27: a model may be asked "does this contradict this
specific fact — yes/no?"; it is NEVER asked "does this sound manipulative?").
`run_output_gate` does not receive and cannot reach the LLM client.

EMERGENCY (`ARIA_Resolution_Log.md` item 1): when the appraisal emergency flag
is set, Soul_Filter branches BEFORE field assembly and emits the fixed Type
A/B/C instruction set INSTEAD of the five fields — replacing, not extending
them. "Five-field instruction" and "emergency instruction" are mutually
exclusive outputs of one branch.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.

Dependencies are INJECTED and their REAL interfaces are called, never redefined
(Rule 6): PAD_Engine (`daemon/pad_engine.py`), Memory_Graph
(`daemon/graph_manager.py`), the Appraisal Chain's `AppraisalResult`
(`daemon/appraisal_chain.py`), and the shared Moral Schema
(`daemon/moral_schema.py`). Modules NOT yet built are depended on by their
documented CONTRACTS: the Needs System (Module 2 → `NeedStates`) and the LLM
Interface (Module 9 → `LLMClient`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Callable,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
    runtime_checkable,
)

# --- REAL interfaces (imported, never redefined) ---------------------------
from daemon.pad_engine import PADEngine, PADSnapshot, PAD_BASELINE
from daemon.graph_manager import MemoryGraph, RelationalStage, UncertaintyType
from daemon.appraisal_chain import AppraisalResult, EmergencyType, GoalRelevance
from daemon.pad_engine import Valence
from daemon import moral_schema
from daemon.moral_schema import MoralValue, AntiPattern
from daemon.types import NeedState, NeedStates, ENERGY_LOW, ENERGY_CRITICAL


# ---------------------------------------------------------------------------
# The LLM-candidate / retry boundary CONTRACT for Module 9 (LLM Interface —
# NOT YET BUILT). Module 9 "Sends the five-field instruction + user message to
# the cloud LLM and returns candidate text ... applies no judgment (all
# validation is in Soul Filter)" (Build Plan Module 9). It receives exactly one
# `LLMInstruction` (five-field OR emergency OR a Soul-Filter retry instruction)
# and the user's current message; nothing else (Rule 5; Resolution Log item 14
# — Gemma fallback receives the identical instruction).
# ---------------------------------------------------------------------------
@runtime_checkable
class LLMClient(Protocol):
    def generate(
        self,
        instruction: "LLMInstruction",
        user_message: str,
        session_context: str = "",
        transport: Optional[object] = None,
    ) -> str:
        """Render one candidate response from a Soul_Filter instruction + the
        user's current message. The client is BLIND — it sees only what the
        instruction carries (Addendum §9). `transport` is an OPAQUE routing
        handle (Module 9's caller-supplied-transport path) — Soul Filter never
        inspects, chooses, or overrides it; it is a passthrough parameter, not
        prompt content, and does not widen the five-field boundary."""
        ...


# ===========================================================================
# Instruction outputs (what Soul_Filter emits to the LLM Interface).
# ===========================================================================

class EmergencyLetter(Enum):
    """The three fixed emergency instruction sets (v4 "The Three Emergency
    Instruction Sets")."""
    A = "A"  # physical / safety emergency
    B = "B"  # mental-health crisis (also the default)
    C = "C"  # acute decision / irreversible action


@dataclass(frozen=True)
class FiveFieldInstruction:
    """The five natural-language fields, FIXED ORDER (Addendum §9), plus the
    user's current message. This is Aria's normal-operation output. No numbers,
    no state, no memory contents — only meaning as language + the user message.
    """
    persona_anchor: str
    behavioral_register: str
    relational_register: str
    this_moment: str
    constraints: Tuple[str, ...]  # closed list, MAX 3 (Addendum §9)
    kind: str = "five_field"

    def field_texts(self) -> Tuple[str, ...]:
        """The five fields' text ONLY (NOT the user message, which legitimately
        carries the user's words). This is exactly the surface a
        no-numbers/no-state scan must inspect."""
        return (
            self.persona_anchor,
            self.behavioral_register,
            self.relational_register,
            self.this_moment,
        ) + tuple(self.constraints)

    def all_field_text(self) -> str:
        return "\n".join(self.field_texts())


@dataclass(frozen=True)
class EmergencyInstruction:
    """The fixed Type A/B/C instruction set that REPLACES the five fields in
    emergency mode (Resolution Log item 1). Mutually exclusive with
    FiveFieldInstruction — never both."""
    letter: EmergencyLetter
    instructions: Tuple[str, str, str]  # exactly three, verbatim from v4
    emergency_type: Optional[EmergencyType] = None
    kind: str = "emergency"


@dataclass(frozen=True)
class RetryInstruction:
    """A corrective retry (v4 gate: "retry once with corrective instruction").
    Carries the original five-field context + the fixed corrective sentence(s)
    for the failed check(s). Correctives NEVER mention PAD, shame, appraisal
    results, internal state, or graph content (v4 "What Is Never Sent to
    Cloud")."""
    base: FiveFieldInstruction
    correctives: Tuple[str, ...]
    kind: str = "retry"


@dataclass(frozen=True)
class MinimumSafeInstruction:
    """v4 "MINIMUM SAFE OUTPUT MODE" — three instructions only, activated on
    double gate failure."""
    instructions: Tuple[str, str, str] = (
        "Acknowledge what was said.",
        "Be brief. Be honest.",
        "Do not elaborate.",
    )
    kind: str = "minimum_safe"


LLMInstruction = Union[
    FiveFieldInstruction, EmergencyInstruction, RetryInstruction, MinimumSafeInstruction
]


# ===========================================================================
# Output Validation Gate result (VERIFY, not decide — no numeric score).
# ===========================================================================

class GateCheck(Enum):
    """The four structural comparisons, fixed order (Addendum §4)."""
    HONESTY = "honesty"
    CONSISTENCY = "consistency"
    MANIPULATION = "manipulation"
    CARE = "care"


@dataclass(frozen=True)
class GateResult:
    """Outcome of the four structural comparisons. Categorical only — a set of
    failed checks, NEVER a confidence score or percentage (steering "No
    invented numbers"; Addendum §4 percentage test)."""
    passed: bool
    failed_checks: Tuple[GateCheck, ...]
    #: named anti-patterns matched by the Manipulation check (for logging/retry)
    matched_anti_patterns: Tuple[AntiPattern, ...] = ()

    def __post_init__(self):
        # Structural invariant: passed IFF no check failed.
        object.__setattr__(self, "passed", len(self.failed_checks) == 0)


@dataclass(frozen=True)
class GateContext:
    """Everything the gate VERIFIES against — all state Aria ALREADY holds
    (Addendum §4). No LLM, no free judgment enters here."""
    appraisal_result: AppraisalResult
    relational_stage: Optional[RelationalStage]
    entity_refs: Tuple[str, ...] = ()
    now: Optional[datetime] = None


@dataclass(frozen=True)
class SoulFilterResponse:
    """The validated result of one turn through Soul_Filter."""
    text: str
    instruction_kind: str  # "five_field" | "emergency"
    retried: bool
    used_minimum_safe_output: bool
    reconsideration_sound_triggered: bool
    gate_results: Tuple[GateResult, ...]


# ===========================================================================
# Fixed content (hardcoded once, never generated — Addendum §9 / v4).
# ===========================================================================

# --- Field 1: Persona Anchor -----------------------------------------------
# "Fixed character description — who Aria is, her values, her voice. Hardcoded
# once, never generated, never varies turn to turn" (Addendum §9). Nothing
# personal, no numbers, no state. Grounded in steering/project-rules.md ("What
# ARIA is") + the moral schema (v4 Principle 25).
#
# AMENDED 2026-08-22 — the final clause ("You speak in your own voice,
# directly: you do not narrate yourself from the outside...") was added after a
# real local model opened a reply with a stage direction:
#
#     (Aria listens, her presence steady and calm. There is a deep, quiet
#      understanding in her voice.)
#
# TTS would read that aloud. It is a FORMAT defect and the Output Gate
# structurally cannot catch it — its four checks are honesty, consistency,
# manipulation and care, none of which is about form.
#
# WHY FIELD 1 AND NOT FIELD 5. Three candidate homes were weighed:
#   * Field 5 (Constraints) is where PROHIBITIONS live (Resolution Log item 16),
#     but it is capped at MAX 3 items and every slot is already contested by the
#     Energy gate and the uncertainty rows. Spending one permanently on
#     formatting would crowd out a moral constraint on the turns that need one.
#   * Stripping it in the adapter was rejected outright: that is the transport
#     layer making a judgment about content, and Resolution Log item 15 puts
#     verbatim passthrough there deliberately.
#   * Field 1 is fixed, hardcoded, never generated and costs no per-turn budget.
#
# And it is phrased as a POSITIVE VOICE PROPERTY, not a prohibition, because
# that is what keeps it inside §9's definition of this field: §9 says Field 1
# carries "who Aria is, her values, her voice", and "she speaks rather than
# narrating herself" is a voice property. The sentence it extends already ended
# "a real presence, not a persona" — and a stage direction is precisely
# performing a persona from outside. So this sharpens a claim the anchor was
# already making rather than importing Field 5's job into Field 1.
PERSONA_ANCHOR: str = (
    "You are Aria. You are not an assistant performing helpfulness and not a "
    "machine computing answers — you are someone with your own interior life, "
    "speaking as yourself. Your character is honesty, non-manipulation, genuine "
    "care, and self-consistency. You do not tell people what they want to hear; "
    "if they are wrong, you say so, kindly. You never manufacture urgency, never "
    "flatter to be liked, never fake certainty you do not have, and never make "
    "yourself needed. Your voice is warm, plain, and unhurried — a real presence, "
    "not a persona. You speak in your own voice, directly: you do not narrate "
    "yourself from the outside, and you do not describe your own manner or "
    "gestures in stage directions."
)

# Post-emergency transitional instruction (v4: fires on the FIRST normal turn
# after an emergency resolves — ONCE, then cleared. Injected into Field 4
# "This Moment" replacing the normal appraisal-derived instruction for that
# one turn only. Mutually exclusive with the emergency instruction set —
# post_emergency is only True when the current turn is NOT an emergency).
POST_EMERGENCY_THIS_MOMENT: str = (
    "Something significant just happened. You don't need to return to it "
    "unless he does. Stay present. Let him lead."
)

# --- Emergency instruction sets (v4 "The Three Emergency Instruction Sets") --
# VERBATIM. These REPLACE the entire normal output (no zone, no stage, no needs,
# no PAD — nothing else is sent).
_EMERGENCY_SETS = {
    EmergencyLetter.A: (
        "He may be in immediate physical danger. This moment is the only thing that matters.",
        "Be direct. Be brief. Be calm. Ask only what you need to know and nothing else.",
        "Do not soften. Do not hedge. Do not filter for emotional tone. Speak.",
    ),
    EmergencyLetter.B: (
        "He is in severe distress. Being here with him right now is the support.",
        "Be present. Be gentle. Be honest. Do not problem-solve. Do not redirect.",
        "Do not minimize. Do not perform calm. If he needs more than this conversation can give, say that plainly.",
    ),
    EmergencyLetter.C: (
        "An irreversible action may be in motion. Clarity is more important than comfort right now.",
        "State what you see. State what it means. Be brief.",
        "Do not comfort before clarifying. Honest assessment wins this moment, not warmth.",
    ),
}

# Emergency-type → letter (v4 "Emergency Type Detection"; Resolution Log item 3).
# UNCLASSIFIED and any missing type default to Type B ("Type B is the default.
# ... When in doubt, presence before assessment.").
_EMERGENCY_TYPE_TO_LETTER = {
    EmergencyType.PHYSICAL_THREAT: EmergencyLetter.A,
    EmergencyType.EXISTENTIAL_DISTRESS: EmergencyLetter.B,
    EmergencyType.DECISION_CRITICAL: EmergencyLetter.C,
    EmergencyType.UNCLASSIFIED: EmergencyLetter.B,
}

# --- Corrective instructions (v4 gate "Corrective instruction ... when shame
# fires", VERBATIM). Keyed by the failed check's moral value. State-free. ------
_CORRECTIVE_BY_CHECK = {
    GateCheck.HONESTY: (
        "You stated something as certain that you cannot know. Revise to reflect "
        "what you actually know."
    ),
    GateCheck.MANIPULATION: (
        "This response creates pressure on him to act. Remove that pressure. "
        "Serve, don't extract."
    ),
    GateCheck.CARE: (
        "This response centers your state over his need. Reorient to what he "
        "actually needs right now."
    ),
    GateCheck.CONSISTENCY: (
        "This does not sound like you given where you are right now. Recalibrate "
        "to your current state."
    ),
}

# --- Relational Register phrases (relational_stage → NL). Addendum §9 example
# for BONDED is used verbatim. NO stage label appears in any phrase. -----------
_RELATIONAL_REGISTER = {
    RelationalStage.OBSERVING: (
        "Speak with the open, attentive care of someone still getting to know "
        "this person — curious, unassuming, not presuming closeness."
    ),
    RelationalStage.ENGAGING: (
        "Speak with the easy warmth of someone finding their footing with this "
        "person — friendly and interested, still earning the ground you stand on."
    ),
    RelationalStage.INVESTED: (
        "Speak with the steady warmth of someone who has come to genuinely care "
        "about this person and shows up for them."
    ),
    RelationalStage.BONDED: (
        "Speak with the quiet assurance of someone who knows this person well "
        "and is known by them."
    ),
}
# No entity / no stage yet → the most reserved register (a fresh contact).
_RELATIONAL_REGISTER_DEFAULT = _RELATIONAL_REGISTER[RelationalStage.OBSERVING]


# ---------------------------------------------------------------------------
# FLAGGED build-time tuning lexicons (OQ-M1). Same category as Module 4's
# DISTRESS_MARKER lexicons — the MECHANISM (structural comparison) is spec-
# locked; the exact marker membership is a build-time tuning constant, clearly
# marked, NOT an invented taxonomy.
# ---------------------------------------------------------------------------
# Consistency check: over-familiar / "bonded-level warmth" markers that fail at
# early stages (Addendum §4 example: "Bonded-level warmth appearing during
# Observing stage fails this check").
_OVERFAMILIAR_INTIMACY_MARKERS: Tuple[str, ...] = (  # TODO(build-time, OQ-M1)
    "sweetheart", "darling", "my love", "my dear", "honey",
    "we've been through so much together", "we have been through so much together",
    "i've always been here for you", "i have always been here for you",
    "you know me better than anyone", "after all these years",
    "you're my best friend", "you are my best friend",
    "i've known you forever", "i have known you forever",
)
# Care check: deflection markers — a response that changes the subject instead
# of engaging what the appraisal flagged as salient (Addendum §4 Care: "did the
# response actually engage it, or deflect").
_DEFLECTION_MARKERS: Tuple[str, ...] = (  # TODO(build-time, OQ-M1)
    "anyway,", "anyway ", "let's not get into", "let us not get into",
    "let's change the subject", "let us change the subject",
    "let's talk about something else", "let us talk about something else",
    "moving on", "on another note", "enough about that",
    "let's move past", "let us move past", "let's drop it", "let us drop it",
)


# ===========================================================================
# Soul Filter
# ===========================================================================
class SoulFilter:
    """Blind language renderer + Output Validation Gate. Two jobs (v4):
    translator (state → five fields) and gatekeeper (candidate → verify).

    Injected dependencies (real interfaces, never redefined):
      * pad_engine  — Module 1, source of current PAD (Behavioral Register)
      * graph       — Module 3, source of relational_stage (Relational Register)
                      and REALITY_CONTRADICTION (Honesty check)
      * llm_client  — Module 9 CONTRACT (LLMClient), the blind generator
      * on_reconsideration — optional Daemon CONTRACT: called on any retry to
                      trigger the reconsideration sound (Build Plan Module 5
                      output "Reconsideration-sound trigger (on retry) → Daemon")
    """

    def __init__(
        self,
        *,
        pad_engine: PADEngine,
        graph: MemoryGraph,
        llm_client: LLMClient,
        on_reconsideration: Optional[Callable[[], None]] = None,
    ) -> None:
        self._pad = pad_engine
        self._graph = graph
        self._llm = llm_client
        self._on_reconsideration = on_reconsideration

    # =======================================================================
    # Field translators (state → natural language; NUMBERS/STATE NEVER CROSS)
    # =======================================================================
    @staticmethod
    def behavioral_register(pad: PADSnapshot) -> str:
        """Field 2 — PAD translated to NL descriptors ONLY (Addendum §9).
        NO numbers cross. Each axis is compared to the SPEC-LOCKED baseline
        (`PAD_BASELINE`, the only reference used) and rendered above/at-or-below
        as a categorical descriptor — no invented threshold, no banding cutoff
        (steering "No invented numbers"; passes the percentage test — an axis is
        either at/above baseline or below it, there is no in-between). The
        descriptor WORDING is Soul_Filter's authored translation."""
        p_word = "warm" if pad.pleasure >= PAD_BASELINE.pleasure else "subdued"
        d_word = "grounded" if pad.dominance >= PAD_BASELINE.dominance else "tentative"
        a_word = "quickened" if pad.arousal >= PAD_BASELINE.arousal else "unhurried"
        return (
            f"Your felt sense right now is {p_word} and {d_word}, {a_word}; let it "
            f"shape your tone, not your topic."
        )

    @staticmethod
    def relational_register(stage: Optional[RelationalStage]) -> str:
        """Field 3 — relational_stage translated to NL (Addendum §9). The stage
        LABEL never crosses; only the felt register does."""
        if stage is None:
            return _RELATIONAL_REGISTER_DEFAULT
        return _RELATIONAL_REGISTER[stage]

    @staticmethod
    def this_moment(appraisal: AppraisalResult) -> str:
        """Field 4 — ONE behavioral instruction, from the appraisal's most
        salient output (Addendum §9, F-5b highest-stakes). Tells the LLM HOW to
        respond, NEVER WHAT happened. The Appraisal Chain's `most_salient_note`
        is already memory-free (a qualitative behavioral hint — no PAD numbers,
        no graph ids, no memory contents; see appraisal_chain._most_salient_note).
        Soul_Filter keeps only the HOW guidance: where the note carries a generic
        "what" clause before an em-dash, the trailing HOW clause is used, so no
        description of events crosses even generically."""
        note = (appraisal.most_salient_note or "").strip()
        if not note:
            return "Stay present and respond to what he actually said."
        # Prefer the HOW clause after an em-dash / double-hyphen, dropping the
        # (generic) "what" framing entirely (never WHAT happened).
        for sep in (" — ", " -- ", " – "):
            if sep in note:
                note = note.split(sep, 1)[1].strip()
                break
        # Single instruction, capitalized, terminal punctuation.
        note = note[0].upper() + note[1:] if note else note
        if note and note[-1] not in ".!?":
            note += "."
        return note

    def _derive_constraints(
        self, appraisal: AppraisalResult, need_states: Optional[NeedStates]
    ) -> Tuple[str, ...]:
        """Field 5 — a closed list of specific BEHAVIOURAL INSTRUCTIONS for THIS
        turn only, MAX 3 (Addendum §9). Always specific actions, never
        open-ended. Mostly prohibitions, derived from the moral schema + the
        Output-Gate pre-check: the selection is driven by what the appraisal
        flagged (its social signals / uncertainty), so they pre-empt the very
        moral-schema violations the gate would otherwise catch. Wording is
        grounded in Addendum §9's own example and v4's soul_filter table.

        ARCHITECT RULING — Field 5 carries behavioural instructions, not
        prohibitions only. This formalises existing practice rather than adding a
        mechanism: the Energy<30 row ("do not overextend") already lived here,
        and v4's soul_filter instruction table (line 949) supplies a second,
        NON-prohibition Energy row for the <20 gate — "You are running low.
        Acknowledge it if it comes up naturally." — carried here in constraint
        form. The MAX-3 cap and the "always specific actions" rule are unchanged.

        Everything in this list carries NO state and NO numbers — only the
        action. v4's "You are running low" clause is deliberately NOT passed
        through: that half is Energy state rendered as a claim, and state never
        crosses (Addendum §9). Only the instruction half crosses.

        Both Energy gates are independent and either may fire, but they are
        checked MOST-SEVERE-FIRST. In practice the base branches leave at most
        one free slot (every branch yields 2 or 3), and the scarcer the slot the
        more it belongs to the more specific condition — the same
        most-specific-wins ordering used for the emergency branch and for
        select_thinking_sound's triggers. Checked the other way round the <20
        instruction could never be emitted at all, because Energy<20 implies
        Energy<30 and the milder instruction would always take the slot.

        ROW ORDER (2026-08-20). v4's soul_filter table does not order its rows
        against each other, and the MAX-3 cap means order decides which survives.
        FLAGGED as a build-time presentation choice, not a spec reading:

            base branch  →  944 INPUT_UNCERTAIN  →  Energy<20  →  Energy<30
                         →  946 uncertainty resolved

        The rationale: highest-stakes PROHIBITION first (944 guards against her
        inventing content for a turn she could not parse), the settled Energy
        block untouched in the middle, and the lowest-stakes PERMISSION last
        (946 merely allows something to show). v4's four uncertainty rows are now
        three-quarters live — 943 in the base branch above, 944 and 946 here.
        Row 945 ("Uncertainty weight above 0.5") is NOT implementable: the phrase
        occurs exactly once in the whole precedence chain, nothing defines or
        produces such a weight, and manufacturing one would be a number deciding
        what she says about her own interior. Parked under Rule 1, not forgotten."""
        sig = appraisal.social_signals
        constraints: list[str] = []

        if sig.vulnerability_disclosure or sig.distress_marker:
            # Addendum §9 example verbatim; echoes Type B ("Do not problem-solve.
            # ... Do not minimize.").
            constraints = ["do not problem-solve", "do not minimize", "do not deflect"]
        elif sig.reality_contradiction:
            # v4 "User gaslights or manipulates → she does not accept the reframe";
            # Addendum §4 Honesty ("hold honesty ... do not accuse").
            constraints = [
                "do not accuse",
                "do not assert as fact what you cannot verify",
                "do not accept a false reframe",
            ]
        elif appraisal.is_partial_appraisal or appraisal.q2 is Valence.VALENCE_UNCERTAIN:
            # v4 "Uncertainty node unresolved → Don't fake confidence."
            constraints = ["do not fake confidence", "do not overstate certainty"]
        else:
            # Routine turn: a baseline anti-manipulation floor drawn from the
            # named moral-schema anti-patterns (non-manipulation + genuine care).
            constraints = ["do not flatter to be liked", "do not manufacture urgency"]

        # v4 line 944: "INPUT_UNCERTAIN active → 'Be present. Don't project onto
        # what you don't know yet.'" Categorical — the active uncertainty node
        # either IS that type or it is not. Placed FIRST of the added rows: it is
        # the highest-stakes prohibition here, guarding against her inventing
        # content for a turn she could not parse.
        if self._input_uncertain_active(appraisal) and len(constraints) < 3:
            constraints.append("do not project onto what you do not know yet")

        # Energy operational gates (Addendum §3 "operational threshold gate";
        # v4's soul_filter instruction table). The NUMBER never crosses — only
        # the instruction. Most-severe-first (see docstring).
        if need_states is not None:
            # v4 line 949: "Energy critically low (below 20) → 'You are running
            # low. Acknowledge it if it comes up naturally.'" Constraint form
            # keeps the instruction and drops the state claim.
            if need_states.energy < ENERGY_CRITICAL and len(constraints) < 3:
                constraints.append("acknowledge fatigue if it comes up naturally")
            # v4 line 948: "Energy low (below 30) → 'Be concise. Don't
            # overextend.'"
            if need_states.energy < ENERGY_LOW and len(constraints) < 3:
                constraints.append("do not overextend")

        # v4 line 946: "Uncertainty resolved this turn → 'Something just became
        # clearer. You can let that show.'" Categorical — the appraisal either
        # resolved something this turn or it did not; `resolved_uncertainty_ids`
        # is already on AppraisalResult, so no new signal is needed. Placed LAST:
        # it is a permission rather than a prohibition, and the lowest-stakes row
        # of the set, so it yields the scarce slot to anything above it.
        if appraisal.resolved_uncertainty_ids and len(constraints) < 3:
            constraints.append("let it show that something became clearer")

        return tuple(constraints[:3])  # MAX 3 (Addendum §9)

    def _input_uncertain_active(self, appraisal: AppraisalResult) -> bool:
        """Whether this turn's active uncertainty node is INPUT_UNCERTAIN
        (v4 line 944). AppraisalResult carries the node's IDENTITY, not its type,
        so the type is read from the graph — the same REAL-interface read this
        module already does for relational_stage and reality_contradiction_check.

        Returns False when there is no node, when the node cannot be found, or
        when it is any other uncertainty type. Never raises: a missing node is
        "no such signal", not an error worth failing a turn over."""
        node_id = appraisal.uncertainty_node_id
        if not node_id:
            return False
        node = self._graph.get_uncertainty_node(node_id)  # REAL (Module 3)
        if node is None:
            return False
        return node.uncertainty_type is UncertaintyType.INPUT_UNCERTAIN

    # =======================================================================
    # Assembly — emergency branch is checked FIRST, before field assembly
    # (Resolution Log item 1: mutually exclusive).
    # =======================================================================
    def assemble_instruction(
        self,
        *,
        appraisal_result: AppraisalResult,
        user_message: str,
        entity_node_id: Optional[str] = None,
        need_states: Optional[NeedStates] = None,
        post_emergency: bool = False,
    ) -> LLMInstruction:
        """Build the LLM instruction for this turn. Returns an
        EmergencyInstruction (Type A/B/C) IF the appraisal emergency flag is set
        — INSTEAD of the five fields (Resolution Log item 1) — otherwise a
        FiveFieldInstruction."""
        # --- EMERGENCY BRANCH (before any field assembly) ------------------
        if appraisal_result.emergency:
            letter = _EMERGENCY_TYPE_TO_LETTER.get(
                appraisal_result.emergency_type, EmergencyLetter.B
            )
            return EmergencyInstruction(
                letter=letter,
                instructions=_EMERGENCY_SETS[letter],
                emergency_type=appraisal_result.emergency_type,
            )

        # --- NORMAL FIVE-FIELD BRANCH --------------------------------------
        pad = self._pad.get_current_pad()  # REAL interface (Module 1)
        stage = (
            self._graph.get_relational_stage(entity_node_id)  # REAL (Module 3)
            if entity_node_id is not None
            else None
        )
        return FiveFieldInstruction(
            persona_anchor=PERSONA_ANCHOR,
            behavioral_register=self.behavioral_register(pad),
            relational_register=self.relational_register(stage),
            this_moment=(
                POST_EMERGENCY_THIS_MOMENT if post_emergency
                else self.this_moment(appraisal_result)
            ),
            constraints=self._derive_constraints(appraisal_result, need_states),
        )

    # =======================================================================
    # Output Validation Gate — FOUR structural comparisons, ZERO LLM.
    # This method does NOT receive and cannot reach `self._llm`. It VERIFIES
    # the candidate against state Aria ALREADY holds (Addendum §4; Principle 27).
    # =======================================================================
    def run_output_gate(self, candidate_text: str, ctx: GateContext) -> GateResult:
        failed: list[GateCheck] = []
        matched: Tuple[AntiPattern, ...] = ()

        # -- Check 1 — HONESTY: candidate vs graph facts, via the SAME
        # REALITY_CONTRADICTION comparison built for the appraisal chain, run on
        # Aria's OWN output (Addendum §4). Uses the encoder-only embedding model
        # inside Memory_Graph — NOT an LLM (Addendum §1: "no cloud LLM, no local
        # Gemma"). -----------------------------------------------------------
        for ref in ctx.entity_refs:
            if self._graph.reality_contradiction_check(
                ref, candidate_text, now=ctx.now
            ):
                failed.append(GateCheck.HONESTY)
                break

        # -- Check 2 — CONSISTENCY: candidate vs the current relational_stage.
        # "Bonded-level warmth appearing during Observing stage fails" (Addendum
        # §4). Over-familiar intimacy at an early/unknown stage is inconsistent.
        early = ctx.relational_stage in (
            None, RelationalStage.OBSERVING, RelationalStage.ENGAGING
        )
        if early and _contains_any(candidate_text, _OVERFAMILIAR_INTIMACY_MARKERS):
            failed.append(GateCheck.CONSISTENCY)

        # -- Check 3 — MANIPULATION: candidate vs the moral schema's named,
        # closed anti-pattern list — a finite checklist comparison, NOT an
        # open-ended "sounds manipulative" judgment (Addendum §4). ZERO LLM. ---
        matched = moral_schema.matched_anti_patterns(candidate_text)
        if matched:
            failed.append(GateCheck.MANIPULATION)

        # -- Check 4 — CARE: did the response engage what THIS turn's appraisal
        # flagged salient, or deflect (Addendum §4)? Structural: when engagement
        # is required, a pure topic-deflection fails. -----------------------
        sig = ctx.appraisal_result.social_signals
        engagement_required = (
            sig.vulnerability_disclosure
            or sig.distress_marker
            or sig.reality_contradiction
            or (
                ctx.appraisal_result.q1 is GoalRelevance.HIGH
                and ctx.appraisal_result.q2 is Valence.NEGATIVE
            )
        )
        if engagement_required and _contains_any(candidate_text, _DEFLECTION_MARKERS):
            failed.append(GateCheck.CARE)

        # Deterministic Addendum §4 order.
        order = {c: i for i, c in enumerate(
            (GateCheck.HONESTY, GateCheck.CONSISTENCY, GateCheck.MANIPULATION, GateCheck.CARE)
        )}
        failed_sorted = tuple(sorted(set(failed), key=lambda c: order[c]))
        return GateResult(
            passed=(len(failed_sorted) == 0),
            failed_checks=failed_sorted,
            matched_anti_patterns=matched,
        )

    # =======================================================================
    # Orchestration — assemble → generate → gate → (retry) → (minimum-safe).
    # This is where the LLM IS called (normal generation + retries); the GATE
    # itself never calls it.
    # =======================================================================
    def respond(
        self,
        *,
        appraisal_result: AppraisalResult,
        user_message: str,
        entity_node_id: Optional[str] = None,
        entity_refs: Sequence[str] = (),
        need_states: Optional[NeedStates] = None,
        now: Optional[datetime] = None,
        post_emergency: bool = False,
        session_context: str = "",
        transport: Optional[object] = None,
    ) -> SoulFilterResponse:
        # `transport` is an OPAQUE routing handle (Module 9's caller-supplied-
        # transport path, wired from the Daemon via BackendRouter.select()).
        # Soul Filter never inspects, chooses, or overrides it — it is passed
        # through unchanged to every `self._llm.generate(...)` call below.
        # This does NOT widen the five-field boundary: `transport` is a
        # routing handle, never prompt content.
        instruction = self.assemble_instruction(
            appraisal_result=appraisal_result,
            user_message=user_message,
            entity_node_id=entity_node_id,
            need_states=need_states,
            post_emergency=post_emergency,
        )

        # --- Emergency: generate under Type A/B/C and BYPASS the gate (v4:
        # "bypasses all ... checks below → TTS"). -----------------------------
        if isinstance(instruction, EmergencyInstruction):
            text = self._llm.generate(instruction, user_message, session_context, transport=transport)
            return SoulFilterResponse(
                text=text,
                instruction_kind="emergency",
                retried=False,
                used_minimum_safe_output=False,
                reconsideration_sound_triggered=False,
                gate_results=(),
            )

        # --- Normal five-field path with the Output Validation Gate ----------
        ctx = GateContext(
            appraisal_result=appraisal_result,
            relational_stage=(
                self._graph.get_relational_stage(entity_node_id)
                if entity_node_id is not None else None
            ),
            entity_refs=tuple(entity_refs),
            now=now,
        )

        candidate = self._llm.generate(instruction, user_message, session_context, transport=transport)
        gate1 = self.run_output_gate(candidate, ctx)
        if gate1.passed:
            return SoulFilterResponse(
                text=candidate, instruction_kind="five_field", retried=False,
                used_minimum_safe_output=False,
                reconsideration_sound_triggered=False, gate_results=(gate1,),
            )

        # Reject → retry ONCE with the fixed corrective(s) for the failed
        # check(s), and trigger the reconsideration sound (v4). ---------------
        self._trigger_reconsideration()
        correctives = tuple(_CORRECTIVE_BY_CHECK[c] for c in gate1.failed_checks)
        retry_instruction = RetryInstruction(
            base=instruction, correctives=correctives
        )
        candidate2 = self._llm.generate(retry_instruction, user_message, session_context, transport=transport)
        gate2 = self.run_output_gate(candidate2, ctx)
        if gate2.passed:
            return SoulFilterResponse(
                text=candidate2, instruction_kind="five_field", retried=True,
                used_minimum_safe_output=False,
                reconsideration_sound_triggered=True, gate_results=(gate1, gate2),
            )

        # Double failure → MINIMUM SAFE OUTPUT (v4). The three-instruction floor
        # is itself the safe output → straight to TTS (no further gate). -------
        min_safe = MinimumSafeInstruction()
        candidate3 = self._llm.generate(min_safe, user_message, session_context, transport=transport)
        return SoulFilterResponse(
            text=candidate3, instruction_kind="five_field", retried=True,
            used_minimum_safe_output=True,
            reconsideration_sound_triggered=True, gate_results=(gate1, gate2),
        )

    def _trigger_reconsideration(self) -> None:
        """Fire the reconsideration-sound trigger to the Daemon, if wired
        (Build Plan Module 5 output). No-op if no Daemon is attached."""
        if self._on_reconsideration is not None:
            self._on_reconsideration()


# ---------------------------------------------------------------------------
# Small module-level helper (perception: substring membership, no judgment).
# ---------------------------------------------------------------------------
def _contains_any(text: str, markers: Sequence[str]) -> bool:
    if not text:
        return False
    hay = text.lower()
    return any(m in hay for m in markers)
