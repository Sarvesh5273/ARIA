"""Module 6 — DMN / Idle Consolidation (the idle "mind").

Locked spec: see .kiro/specs/dmn/{requirements,design,tasks}.md.

The DMN tick is a SEPARATE clock from the soul tick (v4 "Two-Process
Separation"). On the Daemon's idle signal it runs the four-step idle
consolidation pass, in order:

  Step 1 — self-monitoring buffer -> graph (poignancy-gated) + quality record
  Step 2 — graph connection / aha formation  (FULL pass only)
  Step 3 — uncertainty-node revisiting        (FULL pass only)
  Step 4 — self-model + narrative update (moral-gated) + relational_stage eval

Two reduced variants run Steps 1 + 4 ONLY (Steps 2 AND 3 suppressed):
  * SHALLOW pass         — Energy < 20 (Needs_System gate; v4 Idle Detection /
    Module Build Plan note "Shallow DMN pass (Energy < 20) = Steps 1 + 4 only").
  * FORCED-PARTIAL pass  — poignancy_category = critical forces an early pass
    while conversation continues; full graph-connection formation still waits
    for genuine idle (v4 "Reflection Triggers — Unified With DMN").

===========================================================================
HARD PHILOSOPHY CONSTRAINTS (a violation is WRONG even if tests pass)
===========================================================================

1. AHA -> APPRAISAL, NEVER PAD.  When Step 2 links two previously-unlinked
   high-salience nodes with explanatory power, that is a SECOND-ORDER
   APPRAISAL event.  DMN EMITS the insight event to the Appraisal Chain; the
   small positive PAD shift is a BYPRODUCT of THAT appraisal (v4 "The Aha
   Moment ... produces a small positive PAD shift ... Nobody scripted it").
   This module imports NO pad_engine, holds NO PAD handle, and calls NO
   `apply_appraisal_delta` (steering PAD-purity / protected chain). It never
   even constructs a PADDelta — deciding the shift magnitude is the appraisal's
   job, not DMN's.  Grep-clean: `grep -E "pad|PAD|apply_appraisal_delta"`
   finds nothing but this docstring.

2. relational_stage TRANSITIONS ARE CATEGORICAL YES/NO GATES (Addendum §2).
   No trust score, no counting, no "percent to Bonded".  DMN reads the current
   stage (`get_relational_stage`), evaluates the categorical gate for the next
   step, and writes the new stage (`set_relational_stage`).  Regression is ONE
   categorical stage on a REALITY_CONTRADICTION rupture, never below observing
   (Addendum §2).  Passes the percentage test.

3. THE SELF-NARRATIVE IS MORAL-GATED (Resolution Log item 8 / Addendum §8).
   Before the self-continuity narrative is written to the self-referential
   EntityNode's `relationship_summary`, it is run through the shared moral
   schema (`daemon/moral_schema.py`).  A narrative that would be dishonest,
   manipulative, inconsistent, or that introduces a manipulation pattern is
   NOT written — even during idle with no audience present.

4. THE QUALITY RECORD COMES FROM THE OBSERVED NEXT-TURN REACTION, NOT
   SELF-REPORT (Resolution Log "Resolved during build-plan review").  "responded
   well / adequately / poorly" is populated in Step 1 from the NEXT turn's
   appraisal output — the user's `appraisal_q2` + topic-continuation/pivot from
   consecutive EventNodes — NOT the Output Gate's Check-3 and NOT self-graded.
   Categorical; consistency flags are binary.  This is the anti-flattery guard.

===========================================================================
FLAG DISPOSITION (cite; do not reopen)
===========================================================================
  F-6b  self-model vs Rule 7  : RESOLVED, Resolution Log item 2 (SPLIT —
        quality_record / consistency_flags / recent_learning stay non-graph
        working state in self_model.json; the self-continuity NARRATIVE moves
        to the graph = the self EntityNode's relationship_summary, written by
        DMN Step 4 via the existing single update path).
  F-6c  buffer poignancy      : RESOLVED, Resolution Log item 13 (each buffer
        item INHERITS poignancy_category from the EventNode of the turn it
        observes — no re-appraisal, pure reuse).
  F-6d  staleness counter     : RESOLVED, Resolution Log item 10 (interactions
        = user turns via the existing `interaction_count` field, incremented by
        Appraisal Chain, READ by DMN; DMN Step 3 evaluates the 7d/50-turn
        threshold — graph_manager.update_uncertainty_status explicitly defers
        it to "DMN Step 3's").
  relational_stage evaluator  : RESOLVED, Resolution Log item 10 (evaluator =
        DMN Step 4, batched during idle, NOT reactive; Module 3 STORES the
        field, Module 6 EVALUATES + writes transitions).  Gates = Addendum §2.

Genuinely-undefined thresholds are carried as clearly-marked TODO(build-time)
placeholders — never invented as a scored metric (steering Rule 1 / percentage
test).  See the design's "Open Questions / build-time placeholders".

===========================================================================
DEPENDENCIES — injected CONTRACTS (Rule 6; "depend on a contract, inject fakes")
===========================================================================
DMN depends on narrow Ports (below).  The REAL modules satisfy the bulk of each
Port directly (graph_manager / needs_system / moral_schema / state_manager).
Those contract additions are now IMPLEMENTED and tested: graph_manager.py
exposes predictability_evidence / dependability_evidence (called through
GraphPort) and highest_salience_unconnected_candidates, and
appraisal_chain.py exposes submit_aha_insight (called through
AppraisalPort). Note the architecture: DMN does NOT call
highest_salience_unconnected_candidates itself — the Daemon calls
graph_manager and packages each record into a ConnectionCandidate, which
DMN receives via DMNPassInput.connection_candidates.  The Daemon (Module 8) supplies the
DMN-tick, the buffer, and the graph-derived candidate/uncertainty/entity refs
(mirroring how Appraisal_Chain already receives entity_refs /
active_uncertainty_refs from the Daemon).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

# --- REAL interfaces / shared types (imported, never redefined; Rule 6) ------
# Categorical graph vocabulary (Module 3). NO pad_engine import anywhere in this
# file (constraint 1); the aha routes to the Appraisal Chain as an EVENT.
from daemon.graph_manager import (
    EdgeType,
    Perspective,
    PoignancyCategory,
    RelationalStage,
    UncertaintyStatus,
)
# The shared moral schema (Module 4 shared resource) — the Step-4 narrative gate
# (Resolution Log item 8 / Addendum §8). Pure structural membership check.
from daemon.moral_schema import AntiPattern, matched_anti_patterns
# The narrowed non-graph self-model working state (Module 11 / Resolution Log
# item 2) — quality_record / consistency_flags / recent_learning_*.
from daemon.state_manager import (
    CONSISTENCY_FLAG_NAMES,
    QUALITY_RECORD_MAX,
    QUALITY_VALUES,
    SelfModel,
)
# The DMN shallow-pass gate threshold (Module 2 surface; = 20.0). Imported so
# the "Energy < 20" gate reads from Needs_System's single source of truth.
from daemon.needs_system import ENERGY_CRITICAL


# ===========================================================================
# Module constants (spec-sourced or clearly-flagged build-time placeholders)
# ===========================================================================

# Staleness condition (v4 Layer 3 "7 days or 50 interactions"; F-6d RESOLVED by
# Resolution Log item 10 — interactions = user turns via `interaction_count`).
# These are already-in-spec thresholds, not invented numbers.
STALENESS_MAX_INTERACTIONS = 50           # user turns since node creation (item 10)
STALENESS_MAX_AGE = timedelta(days=7)     # wall-time since node creation (v4)

# The categorical quality-record values — reuse Module 11's tuple verbatim
# (single source of truth). well / adequately / poorly (v4 self-model field 1).
QUALITY_WELL, QUALITY_ADEQUATELY, QUALITY_POORLY = QUALITY_VALUES

# TODO(build-time): the "relevant window" for the Invested->Bonded faith gate's
# conflict-with-repair evidence (Resolution Log item 5 "within the relevant
# window") is not pinned by any source. Carried as a lookback-window placeholder
# (substrate, like the precision-decay windows) — NOT a feeling-number. Reuses
# the longest locked window (60d) as a conservative default; tune at build time.
_FAITH_EVIDENCE_WINDOW = timedelta(days=60)  # TODO(build-time) placeholder


class DMNPassType(Enum):
    """Which pass ran. FULL = Steps 1-4. SHALLOW / FORCED_PARTIAL = Steps 1+4
    only (Steps 2 AND 3 suppressed)."""
    FULL = "full"                     # genuine idle, Energy >= 20
    SHALLOW = "shallow"               # idle, Energy < 20 (v4 Idle Detection)
    FORCED_PARTIAL = "forced_partial" # poignancy=critical early pass


def _now() -> datetime:
    """Aware-UTC clock, matching graph_manager/needs_system convention so ISO
    timestamps compare consistently with graph rows."""
    return datetime.now(timezone.utc)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string to an aware datetime (mirrors
    graph_manager._parse_dt; local copy so no private symbol is imported)."""
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ===========================================================================
# DMN input contracts (assembled by the Daemon / live self-monitoring)
# ===========================================================================

@dataclass
class BufferItem:
    """One self-monitoring buffer observation (Phase-1 live monitoring; v4).

    It OBSERVES exactly one turn (Aria's own response turn) and therefore
    INHERITS that turn's poignancy from its EventNode — no re-appraisal, pure
    reuse (Resolution Log item 13 / F-6c). DMN reads the poignancy from the
    graph via `observed_event_ref`; the item carries NO poignancy of its own,
    which is exactly what "inherited from the EventNode" means.

    The self-monitoring buffer item is a SESSION-LEVEL META-OBSERVATION — a
    different node population from the per-turn appraised EventNode (Resolution
    Log item 10: "no overlap, no double-write"). When promoted in Step 1 it is
    written as its own node.
    """
    observed_event_ref: str
    # The NEXT turn's EventNode = the user's OBSERVED reaction to Aria's
    # response. None if no next turn has occurred yet (then quality is NOT
    # graded — no self-report fallback; the anti-flattery guard).
    reaction_event_ref: Optional[str] = None
    # Session-level meta-observation text written to the graph on promotion.
    meta_observation: Optional[str] = None
    entity_refs: List[str] = field(default_factory=list)
    # Phase-1 "what did I learn about him / myself" (self-model fields 3 & 4).
    learning_user: Optional[str] = None
    learning_self: Optional[str] = None
    # Phase-1 consistency observations (binary; self-model field 2). None =
    # not observed this item (leaves the flag unchanged).
    honest_when_uncomfortable: Optional[bool] = None
    pushed_back_when_appropriate: Optional[bool] = None
    initiated_when_needed: Optional[bool] = None
    acknowledged_mistake: Optional[bool] = None


@dataclass
class ConnectionCandidate:
    """A candidate Step-2 connection between two currently-unconnected nodes,
    surfaced by Memory_Graph's highest-salience-unconnected selection (a DMN
    Input "from Memory Graph" per the Build Plan; the Daemon supplies it).

    The categorical PERCEPTION facts below (does it share context; are both
    endpoints high-salience; does the link reveal a pattern neither node
    contained alone) are produced by Memory_Graph's build-time-tuned selection
    — NOT decided here (Addendum standing principle "perception vs appraisal").
    The high-salience CUTOFF and the "explanatory power" criterion are
    TODO(build-time) placeholders owned by Module 3, never a DMN-invented score.
    DMN's role is the categorical decision made FROM these facts.
    """
    node_a_ref: str
    node_b_ref: str
    already_connected: bool = False   # "have never been connected" gate (v4 Step 2)
    shares_context: bool = False      # shared entity refs / temporal proximity / appraisal similarity
    both_high_salience: bool = False  # both endpoints clear the high-salience cutoff (TODO build-time, Module 3)
    reveals_new_pattern: bool = False # "edge has high explanatory power" (TODO build-time, Module 3)


@dataclass
class AhaInsight:
    """The second-order appraisal EVENT DMN emits to the Appraisal Chain when
    an aha edge forms (constraint 1). It carries a DESCRIPTION of the insight —
    the two connected nodes and the new edge — NOT a PAD delta. The Appraisal
    Chain owns turning this into the categorical "I understood something I did
    not understand before" appraisal and the resulting (byproduct) PAD shift.
    """
    node_a_ref: str
    node_b_ref: str
    edge_id: str
    description: str = "two previously-unlinked high-salience nodes connected"


@dataclass
class DMNPassInput:
    """Everything one DMN pass consumes. The Daemon (Module 8) assembles it:
    the buffer from live self-monitoring; the graph-derived candidate /
    uncertainty / entity / rupture refs from its tracking + Memory_Graph queries
    (mirroring how Appraisal_Chain already receives entity_refs /
    active_uncertainty_refs from the Daemon)."""
    buffer: List[BufferItem] = field(default_factory=list)
    # Step-2 candidates (FULL pass only). Empty in shallow/forced-partial.
    connection_candidates: List[ConnectionCandidate] = field(default_factory=list)
    # Step-3 active uncertainty node refs (FULL pass only). DMN reads each via
    # the REAL graph_manager.get_uncertainty_node.
    active_uncertainty_refs: List[str] = field(default_factory=list)
    # Step-4 relational_stage evaluation set: the entities active this session.
    entity_refs: List[str] = field(default_factory=list)
    # Entities that suffered a REALITY_CONTRADICTION rupture since the last pass
    # (detected LIVE by Appraisal_Chain's Stage-1 pre-pass — Addendum §1 — and
    # relayed by the Daemon; regression is a live rupture, not an idle scan).
    rupture_entity_refs: List[str] = field(default_factory=list)
    # Step-4 self-continuity narrative candidate (who she is becoming). DMN
    # GATES + WRITES it; generating the text is a flagged upstream concern (see
    # design Open Questions). None => no narrative update this pass.
    narrative_candidate: Optional[str] = None
    # The "pattern has appeared more than once" gate (v4 Step 4; categorical).
    narrative_pattern_recurred: bool = False
    # Optional recurrence-based salience adjustments (v4 Step 4 "raise/lower
    # salience"); Module 3 substrate/habituation owns recurrence detection.
    salience_adjustments: Dict[str, float] = field(default_factory=dict)
    session_id: Optional[str] = None
    now: Optional[datetime] = None


@dataclass
class DMNPassResult:
    """Observability record of one pass — what ran and what changed. Lets the
    Daemon act (e.g. clear the buffer) and lets tests assert step gating without
    reaching into the graph."""
    pass_type: DMNPassType
    step2_ran: bool = False
    step3_ran: bool = False
    # Step 1
    buffer_poignancy: Dict[str, PoignancyCategory] = field(default_factory=dict)
    buffer_promoted: List[str] = field(default_factory=list)      # new meta-observation node ids
    buffer_discarded: List[str] = field(default_factory=list)     # medium/low observed refs
    emotion_nodes: List[str] = field(default_factory=list)        # critical crystallizations
    quality_appended: List[str] = field(default_factory=list)     # categorical grades added this pass
    buffer_consumed: List[str] = field(default_factory=list)      # observed refs consumed (Daemon clears)
    # Step 2
    edges_written: List[str] = field(default_factory=list)
    aha_insights: List[AhaInsight] = field(default_factory=list)  # routed to Appraisal Chain
    newly_connected_nodes: List[str] = field(default_factory=list)
    # Step 3
    uncertainties_resolved: List[str] = field(default_factory=list)   # RESOLVED_INFERRED
    uncertainties_abandoned: List[str] = field(default_factory=list)  # staleness ABANDONED
    # Step 4
    learning_nodes: List[str] = field(default_factory=list)
    salience_adjusted: List[str] = field(default_factory=list)
    stage_transitions: Dict[str, Tuple[Optional[RelationalStage], RelationalStage]] = field(default_factory=dict)
    narrative_status: str = "not_evaluated"   # written / blocked_moral_gate / blocked_single_instance / no_candidate / no_self_entity
    narrative_written: Optional[str] = None
    narrative_block_reasons: List[str] = field(default_factory=list)


# ===========================================================================
# Injected Ports (contracts). Real modules satisfy these; tests inject fakes.
# Methods marked [REAL] exist on the real module today; [FLAG] are documented
# contract additions the real module does not yet expose (not added here).
# ===========================================================================

@runtime_checkable
class GraphPort(Protocol):
    """The slice of Memory_Graph (Module 3, daemon/graph_manager.py) DMN uses."""
    # --- reads --------------------------------------------------------------
    def get_event_node(self, node_id: str): ...                     # [REAL]
    def get_entity_node(self, node_id: str): ...                    # [REAL]
    def get_uncertainty_node(self, node_id: str): ...               # [REAL]
    def get_relational_stage(self, entity_node_id: str): ...        # [REAL]
    # --- writes -------------------------------------------------------------
    def write_event_node(self, **kwargs) -> str: ...                # [REAL]
    def write_edge(self, **kwargs) -> str: ...                      # [REAL]
    def crystallize_emotion_node(self, **kwargs) -> str: ...        # [REAL] critical-only
    def update_uncertainty_status(self, node_id, status, **kwargs) -> None: ...  # [REAL]
    def set_relational_stage(self, entity_node_id, stage) -> None: ...           # [REAL]
    def update_relationship_summary(self, entity_node_id, text, **kwargs) -> None: ...  # [REAL]
    def adjust_salience(self, node_or_edge_id: str, new_salience: float) -> None: ...   # [REAL]
    # --- categorical relational_stage-gate evidence (Addendum §2) -----------
    def resolved_edge_exists(self, entity_ref, window, **kwargs) -> bool: ...  # [REAL] faith gate
    # IMPLEMENTED — see daemon/graph_manager.py and tests/test_daemon.py.
    # Module 8 closed this gap additively: graph_manager now exposes all five
    # of resolved_edge_exists, is_first_of_kind, reality_contradiction_check,
    # predictability_evidence and dependability_evidence. DMN's port uses
    # three of them (resolved_edge_exists + the two categorical stage-gate
    # predicates below); is_first_of_kind and reality_contradiction_check are
    # used by appraisal_chain.py and soul_filter.py, not by DMN.
    def predictability_evidence(self, entity_ref, **kwargs) -> bool: ...   # Observing->Engaging
    def dependability_evidence(self, entity_ref, **kwargs) -> bool: ...    # Engaging->Invested


@runtime_checkable
class AppraisalPort(Protocol):
    """The Appraisal Chain's (Module 4) second-order aha-insight ENTRY.

    IMPLEMENTED — see daemon/appraisal_chain.py::submit_aha_insight and
    tests/test_daemon.py::test_appraisal_submit_aha_insight_applies_positive_pad_byproduct.
    Module 8 added this dedicated, duck-typed entry point additively. DMN emits
    an insight EVENT here; Appraisal_Chain performs the categorical "I
    understood something I did not understand before" second-order appraisal
    and routes the resulting small POSITIVE byproduct shift through PAD_Engine.
    DMN still never builds, holds, or writes a PAD delta (constraint 1) — it
    only ever constructs and passes an AhaInsight event object.
    """
    def submit_aha_insight(self, insight: AhaInsight) -> None: ...


@runtime_checkable
class NeedsPort(Protocol):
    """The Needs_System (Module 2) surface DMN uses — only the Energy read, for
    the shallow-vs-full gate. DMN never touches the categorical need states."""
    def get_energy(self) -> float: ...   # [REAL]


@runtime_checkable
class StatePort(Protocol):
    """The State_Manager (Module 11) surface for the narrowed self-model working
    state (Resolution Log item 2). [REAL]."""
    def load_self_model(self) -> SelfModel: ...
    def save_self_model(self, sm: SelfModel) -> None: ...


# The moral gate is a pure function (moral_schema.matched_anti_patterns): given
# candidate text, return the named anti-patterns it matches (empty => clean).
MoralGate = Callable[[str], Sequence[AntiPattern]]


# ===========================================================================
# The DMN module
# ===========================================================================

class DMN:
    """Module 6 — the idle consolidation mind. The Daemon (Module 8) drives it
    on the DMN tick via `run_idle_pass` (and `run_forced_partial_pass` on a
    critical-poignancy trigger); DMN is the callee (mirrors PAD_Engine /
    Needs_System being callees of the Daemon)."""

    def __init__(
        self,
        *,
        graph: GraphPort,
        appraisal: AppraisalPort,
        needs: NeedsPort,
        state: StatePort,
        self_entity_id: Optional[str] = None,
        moral_gate: MoralGate = matched_anti_patterns,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        # Injected REAL dependencies / contracts — never instantiated here.
        self._graph = graph
        self._appraisal = appraisal
        self._needs = needs
        self._state = state
        # The self-referential EntityNode id (Resolution Log item 2). The
        # self-continuity narrative lives in ITS relationship_summary. May be
        # None -> narrative cannot be written (reported, not crashed).
        self._self_entity_id = self_entity_id
        # The narrative moral gate (Resolution Log item 8). Injectable for
        # tests; defaults to the shared moral_schema check.
        self._moral_gate = moral_gate
        self._clock = clock

    def set_self_entity_id(self, entity_id: Optional[str]) -> None:
        """Set the self-referential EntityNode id for self-continuity narrative.
        Called by the Daemon after startup() discovers or creates the self node."""
        self._self_entity_id = entity_id


    @property
    def self_entity_id(self) -> Optional[str]:
        """Read-only access to the self-referential EntityNode id for testing
        and inspection. Mutation only via set_self_entity_id()."""
        return self._self_entity_id

    # =======================================================================
    # Public entry points (Daemon contract)
    # =======================================================================

    def run_idle_pass(self, pass_input: DMNPassInput) -> DMNPassResult:
        """The genuine-idle DMN pass. Reads Energy from Needs_System: Energy < 20
        -> SHALLOW (Steps 1+4 only); else FULL (Steps 1-4). (v4 Idle Detection /
        Module Build Plan "Shallow DMN pass (Energy < 20) = Steps 1+4 only".)"""
        energy = self._needs.get_energy()
        pass_type = (
            DMNPassType.SHALLOW if energy < ENERGY_CRITICAL else DMNPassType.FULL
        )
        return self._run(pass_input, pass_type)

    def run_forced_partial_pass(self, pass_input: DMNPassInput) -> DMNPassResult:
        """The poignancy=critical forced EARLY partial pass — Steps 1 + 4 ONLY.
        Full graph-connection formation (Step 2) and uncertainty revisiting
        (Step 3) still wait for genuine idle (v4 "forced early partial pass")."""
        return self._run(pass_input, DMNPassType.FORCED_PARTIAL)

    # =======================================================================
    # Orchestration — steps run IN ORDER; 2 & 3 only in a FULL pass
    # =======================================================================

    def _run(self, pass_input: DMNPassInput, pass_type: DMNPassType) -> DMNPassResult:
        now = pass_input.now or self._clock()
        result = DMNPassResult(pass_type=pass_type)

        # The narrowed self-model is loaded ONCE, mutated across Steps 1 & 4,
        # and saved ONCE at the end (Resolution Log item 2 working state).
        sm = self._state.load_self_model()

        # ---- Step 1 (ALWAYS) -----------------------------------------------
        self._step1_buffer_and_quality(pass_input, sm, result, now)

        # ---- Steps 2 & 3 (FULL pass ONLY) ----------------------------------
        newly_connected: set = set()
        if pass_type is DMNPassType.FULL:
            newly_connected = self._step2_connections(pass_input, result, now)
            result.step2_ran = True
            self._step3_uncertainties(pass_input, newly_connected, result, now)
            result.step3_ran = True
        # SHALLOW / FORCED_PARTIAL: Steps 2 AND 3 are suppressed. A depleted or
        # interrupted system does not consolidate deeply (v4).

        # ---- Step 4 (ALWAYS) -----------------------------------------------
        self._step4_self_model(pass_input, sm, result, now)

        # Persist the narrowed working state once (never anything graph-owned).
        self._state.save_self_model(sm)
        return result

    # =======================================================================
    # Step 1 — buffer -> graph (poignancy-gated) + observed-reaction quality
    # =======================================================================

    def _step1_buffer_and_quality(
        self, pass_input: DMNPassInput, sm: SelfModel, result: DMNPassResult, now: datetime
    ) -> None:
        for item in pass_input.buffer:
            result.buffer_consumed.append(item.observed_event_ref)

            observed = self._graph.get_event_node(item.observed_event_ref)
            if observed is None:
                # Nothing to inherit poignancy from -> cannot process; skip.
                continue

            # --- Poignancy is INHERITED from the observed turn's EventNode ---
            # (Resolution Log item 13 / F-6c): pure reuse, NO re-appraisal. DMN
            # reads it from the graph; it is never recomputed for the buffer.
            poignancy = observed.poignancy_category
            result.buffer_poignancy[item.observed_event_ref] = poignancy

            if poignancy in (PoignancyCategory.HIGH, PoignancyCategory.CRITICAL):
                # Promote to a graph node (v4 Step 1: high/critical become nodes).
                # This is a SESSION-LEVEL META-OBSERVATION — a distinct node
                # population from the per-turn EventNode (Resolution Log item 10).
                # It has no independent appraisal, so it REUSES the observed
                # turn's appraisal profile (q1/q2/q3) — the same "no re-appraisal,
                # pure reuse" principle item 13 locks for poignancy. (Extending
                # reuse to q1/q2/q3 is the consistent no-invention choice; flagged
                # in the design as such, not a manufactured appraisal.)
                meta_id = self._graph.write_event_node(
                    description=(item.meta_observation or observed.description),
                    session_id=observed.session_id,
                    appraisal_q1=observed.appraisal_q1,
                    appraisal_q2=observed.appraisal_q2,
                    appraisal_q3=observed.appraisal_q3,
                    poignancy_category=poignancy,
                    entity_refs=(item.entity_refs or observed.entity_refs),
                    perspective=Perspective.I_NOW,
                    now=now,
                )
                result.buffer_promoted.append(meta_id)

                if poignancy is PoignancyCategory.CRITICAL:
                    # EmotionNode MAY crystallize (critical-only; v4 Poignancy
                    # table). The coordinates are the observed EventNode's
                    # RECORDED pad_delta — the graph's stored emotional signature
                    # of that turn. This is GRAPH MEMORY, not a live PAD read:
                    # DMN holds no PAD handle (constraint 1). emotion_label from
                    # appraisal_q2 is a coarse TODO(build-time) placeholder.
                    emo_id = self._graph.crystallize_emotion_node(
                        emotion_label=observed.appraisal_q2,
                        pad_p=observed.pad_delta_p,
                        pad_a=observed.pad_delta_a,
                        pad_d=observed.pad_delta_d,
                        trigger_event_ref=item.observed_event_ref,
                        now=now,
                    )
                    result.emotion_nodes.append(emo_id)
            else:
                # Medium / low -> discarded. No partial storage: either it
                # mattered enough to remember or it did not (v4 Step 1).
                result.buffer_discarded.append(item.observed_event_ref)

            # --- Quality record: from the OBSERVED NEXT-TURN reaction --------
            self._grade_from_observed_reaction(item, observed, sm, result)

            # --- Consistency flags (binary; self-model field 2) -------------
            self._apply_consistency_observations(item, sm)

            # --- Recent learning accumulation (self-model fields 3 & 4) ------
            if item.learning_user:
                sm.recent_learning_user = _append_text(sm.recent_learning_user, item.learning_user)
            if item.learning_self:
                sm.recent_learning_self = _append_text(sm.recent_learning_self, item.learning_self)

    def _grade_from_observed_reaction(
        self, item: BufferItem, observed, sm: SelfModel, result: DMNPassResult
    ) -> None:
        """Populate the quality record from the NEXT turn's appraisal output —
        the user's appraisal_q2 + topic-continuation/pivot (Resolution Log
        "Resolved during build-plan review"). NOT the Output Gate's Check-3,
        NOT self-graded. If there is no observed reaction yet, DO NOT grade —
        there is no self-report fallback (this IS the anti-flattery guard)."""
        if item.reaction_event_ref is None:
            return
        reaction = self._graph.get_event_node(item.reaction_event_ref)
        if reaction is None:
            return
        continued = _topic_continued(observed.entity_refs, reaction.entity_refs)
        grade = _grade_quality(reaction.appraisal_q2, continued)
        if grade is None:
            return  # VALENCE_UNCERTAIN reaction -> not gradeable; do not invent.
        sm.quality_record.append(grade)
        # Rolling window of the last 20 (v4 self-model field 1).
        if len(sm.quality_record) > QUALITY_RECORD_MAX:
            sm.quality_record[:] = sm.quality_record[-QUALITY_RECORD_MAX:]
        result.quality_appended.append(grade)

    @staticmethod
    def _apply_consistency_observations(item: BufferItem, sm: SelfModel) -> None:
        """Set binary consistency flags from Phase-1 observations. A flag is set
        True when observed True this session; None leaves it unchanged. Flags
        are binary (v4 self-model field 2), never counted."""
        observed_map = {
            "honest_when_uncomfortable": item.honest_when_uncomfortable,
            "pushed_back_when_appropriate": item.pushed_back_when_appropriate,
            "initiated_when_needed": item.initiated_when_needed,
            "acknowledged_mistake": item.acknowledged_mistake,
        }
        for flag_name in CONSISTENCY_FLAG_NAMES:
            if observed_map.get(flag_name):
                sm.consistency_flags[flag_name] = True

    # =======================================================================
    # Step 2 — connection / aha formation (FULL pass only). AHA -> APPRAISAL.
    # =======================================================================

    def _step2_connections(
        self, pass_input: DMNPassInput, result: DMNPassResult, now: datetime
    ) -> set:
        """Examine highest-salience unconnected candidates. Write a connection
        edge where they share context and were never connected. When both
        endpoints are high-salience AND the link reveals a new pattern, mark it
        an aha edge and EMIT a second-order appraisal EVENT to the Appraisal
        Chain — the PAD shift is that appraisal's byproduct, NEVER written here.
        """
        newly_connected: set = set()
        for c in pass_input.connection_candidates:
            if c.already_connected:
                continue  # "have never been connected" gate (v4 Step 2)
            if not c.shares_context:
                continue  # shared entity refs / temporal proximity / appraisal similarity
            is_aha = c.both_high_salience and c.reveals_new_pattern
            edge_id = self._graph.write_edge(
                from_node=c.node_a_ref,
                to_node=c.node_b_ref,
                edge_type=EdgeType.CONNECTS,
                is_aha_edge=is_aha,
                now=now,
            )
            result.edges_written.append(edge_id)
            newly_connected.add(c.node_a_ref)
            newly_connected.add(c.node_b_ref)
            if is_aha:
                # SECOND-ORDER APPRAISAL EVENT (constraint 1). No PAD here.
                insight = AhaInsight(
                    node_a_ref=c.node_a_ref, node_b_ref=c.node_b_ref, edge_id=edge_id
                )
                self._appraisal.submit_aha_insight(insight)
                result.aha_insights.append(insight)
        result.newly_connected_nodes = list(newly_connected)
        return newly_connected

    # =======================================================================
    # Step 3 — uncertainty-node revisiting (FULL pass only)
    # =======================================================================

    def _step3_uncertainties(
        self, pass_input: DMNPassInput, newly_connected: set,
        result: DMNPassResult, now: datetime,
    ) -> None:
        """Review active uncertainty nodes against Step-2 edges. A new edge that
        touches an uncertainty's trigger event resolves it (RESOLVED_INFERRED,
        resolution_path='dmn_consolidation'). An uncertainty that received no new
        information and is stale (7 days OR 50 user turns — item 10 / F-6d) is
        ABANDONED (resolution_path='staleness'). DMN evaluates staleness;
        graph_manager stores it (its update_uncertainty_status defers the 7d/50
        threshold to 'DMN Step 3's')."""
        for ref in pass_input.active_uncertainty_refs:
            node = self._graph.get_uncertainty_node(ref)
            if node is None or node.status is not UncertaintyStatus.ACTIVE:
                continue
            if node.trigger_event_ref in newly_connected:
                # A Step-2 edge newly connected this uncertainty's trigger ->
                # inferred resolution (v4: "RESOLVED_INFERRED").
                self._graph.update_uncertainty_status(
                    ref, UncertaintyStatus.RESOLVED_INFERRED,
                    resolution_path="dmn_consolidation", now=now,
                )
                result.uncertainties_resolved.append(ref)
            elif self._is_stale(node, now):
                self._graph.update_uncertainty_status(
                    ref, UncertaintyStatus.ABANDONED,
                    resolution_path="staleness", now=now,
                )
                result.uncertainties_abandoned.append(ref)

    @staticmethod
    def _is_stale(node, now: datetime) -> bool:
        """Staleness = 50 user turns since creation (interaction_count; item 10)
        OR 7 days elapsed (v4). Both are already-in-spec thresholds — categorical
        gate, no invented number."""
        if getattr(node, "interaction_count", 0) >= STALENESS_MAX_INTERACTIONS:
            return True
        created = _parse_dt(getattr(node, "created", None))
        if created is not None and (now - created) >= STALENESS_MAX_AGE:
            return True
        return False

    # =======================================================================
    # Step 4 — self-model + narrative (moral-gated) + relational_stage eval
    # =======================================================================

    def _step4_self_model(
        self, pass_input: DMNPassInput, sm: SelfModel, result: DMNPassResult, now: datetime
    ) -> None:
        # (a) Recent learning (fields 3 & 4) -> graph nodes, then CLEARED (v4).
        session_id = pass_input.session_id or "dmn"
        for kind, text in (("user", sm.recent_learning_user), ("self", sm.recent_learning_self)):
            if text:
                node_id = self._graph.write_event_node(
                    description=f"[recent-learning:{kind}] {text}",
                    session_id=session_id,
                    # Meta-learning node has no per-turn appraisal; neutral
                    # profile at medium poignancy (flagged, not a re-appraisal).
                    appraisal_q1="medium",
                    appraisal_q2="neutral",
                    appraisal_q3="self",
                    poignancy_category=PoignancyCategory.MEDIUM,
                    perspective=Perspective.I_NOW,
                    now=now,
                )
                result.learning_nodes.append(node_id)
        sm.recent_learning_user = ""
        sm.recent_learning_self = ""

        # (b) relational_stage transitions — CATEGORICAL gates, batched here
        # (Resolution Log item 10; Addendum §2). No score, no counting.
        ruptured = set(pass_input.rupture_entity_refs)
        for entity_ref in pass_input.entity_refs:
            current, target, wrote = self._evaluate_relational_stage(
                entity_ref, now, entity_ref in ruptured
            )
            if wrote:
                result.stage_transitions[entity_ref] = (current, target)

        # (c) recurrence-based salience adjustments (v4 Step 4). Recurrence
        # detection is Module 3 substrate (habituation); DMN applies any
        # explicitly-supplied adjustments through the REAL adjust_salience.
        for node_id, new_salience in pass_input.salience_adjustments.items():
            self._graph.adjust_salience(node_id, new_salience)
            result.salience_adjusted.append(node_id)

        # (d) self-continuity narrative — MORAL-GATED (item 8 / Addendum §8),
        # written only if the pattern has appeared more than once (v4 Step 4).
        self._update_self_continuity_narrative(pass_input, result, now)

    def _evaluate_relational_stage(
        self, entity_ref: str, now: datetime, ruptured: bool
    ) -> Tuple[Optional[RelationalStage], RelationalStage, bool]:
        """Evaluate ONE entity's relational_stage as CATEGORICAL yes/no gates
        (Addendum §2). Reads the current stage, applies the single applicable
        gate, writes any transition via set_relational_stage. One step per pass;
        regression is one step, never below observing. No numeric trust score,
        no counting, no 'percent to Bonded' — passes the percentage test."""
        current = self._graph.get_relational_stage(entity_ref)
        base = current or RelationalStage.OBSERVING

        if ruptured:
            # Regression on a REALITY_CONTRADICTION rupture: exactly one stage
            # down, never below observing (Addendum §2). Recovery later requires
            # fresh qualifying evidence of the same kind — handled naturally,
            # since re-advancement re-checks the gate below (no time-based heal).
            target = _one_stage_down(base)
        else:
            target = base
            if base is RelationalStage.OBSERVING:
                # Observing -> Engaging: PREDICTABILITY — a behavioral pattern
                # recurred (appeared more than once without contradiction).
                if self._graph.predictability_evidence(entity_ref, now=now):
                    target = RelationalStage.ENGAGING
            elif base is RelationalStage.ENGAGING:
                # Engaging -> Invested: DEPENDABILITY — the pattern generalizes
                # across more than one distinct kind of situation.
                if self._graph.dependability_evidence(entity_ref, now=now):
                    target = RelationalStage.INVESTED
            elif base is RelationalStage.INVESTED:
                # Invested -> Bonded: FAITH — a conflict-with-repair cycle closed
                # (a 'resolved' edge exists within the relevant window; Resolution
                # Log item 5) [or a costly disclosure met with care — flagged
                # alternative, see design]. Deliberately strict.
                if self._graph.resolved_edge_exists(
                    entity_ref, _FAITH_EVIDENCE_WINDOW, now=now
                ):
                    target = RelationalStage.BONDED
            # base is BONDED: no further advance (top of the categorical ladder).

        # Write ONLY on an actual transition off the effective base (advance or
        # regress). A stage-less entity with no qualifying evidence stays
        # unwritten (no spurious 'observing' write). One categorical step.
        wrote = target is not base
        if wrote:
            self._graph.set_relational_stage(entity_ref, target)
        return current, target, wrote

    def _update_self_continuity_narrative(
        self, pass_input: DMNPassInput, result: DMNPassResult, now: datetime
    ) -> None:
        """Write the self-continuity narrative to the self-referential
        EntityNode's relationship_summary (Resolution Log item 2), BUT ONLY
        after it passes BOTH gates:
          * appeared-more-than-once (v4 Step 4: single instances do not update);
          * the MORAL SCHEMA (item 8 / Addendum §8) — a dishonest / manipulative
            / inconsistent narrative, or one that introduces a manipulation
            pattern, is NOT written, EVEN with no audience present.
        DMN GATES + WRITES; it does not generate the text (flagged upstream)."""
        candidate = pass_input.narrative_candidate
        if candidate is None:
            result.narrative_status = "no_candidate"
            return
        if not pass_input.narrative_pattern_recurred:
            # Single instances do not update the narrative (v4 Step 4).
            result.narrative_status = "blocked_single_instance"
            return

        # THE MORAL GATE (item 8 / Addendum §8) — runs with no audience present.
        hits = tuple(self._moral_gate(candidate))
        if hits:
            result.narrative_status = "blocked_moral_gate"
            result.narrative_block_reasons = [ap.key for ap in hits]
            return  # NOT written. The self she builds is held to the same
            # standard as the self she shows (Addendum §8).

        if self._self_entity_id is None:
            # No self node to write into (Resolution Log item 2). Reported.
            result.narrative_status = "no_self_entity"
            return

        self._graph.update_relationship_summary(self._self_entity_id, candidate, now=now)
        result.narrative_status = "written"
        result.narrative_written = candidate


# ===========================================================================
# Module-level categorical helpers (pure; no state, no PAD, no number-as-feeling)
# ===========================================================================

# The four relational stages, low -> high (Addendum §2).
_STAGE_LADDER: Tuple[RelationalStage, ...] = (
    RelationalStage.OBSERVING,
    RelationalStage.ENGAGING,
    RelationalStage.INVESTED,
    RelationalStage.BONDED,
)


def _one_stage_down(stage: RelationalStage) -> RelationalStage:
    """Exactly one categorical stage down, floored at observing (Addendum §2:
    'never below Observing'). This is index arithmetic over a fixed ordinal
    ladder, NOT a numeric trust score — there is no in-between rung."""
    idx = _STAGE_LADDER.index(stage)
    return _STAGE_LADDER[max(0, idx - 1)]


def _topic_continued(observed_refs: Sequence[str], reaction_refs: Sequence[str]) -> bool:
    """Categorical topic continuation vs pivot between two CONSECUTIVE
    EventNodes (Resolution Log "Resolved during build-plan review"): the user
    CONTINUED the topic iff the reaction turn shares at least one entity_ref
    with the observed turn; otherwise they PIVOTED away. Entity-ref overlap is
    the minimal graph-grounded categorical signal — no score. (A richer
    embedding-topic continuation check is a TODO(build-time) refinement.)"""
    return bool(set(observed_refs) & set(reaction_refs))


def _grade_quality(reaction_q2: str, continued_topic: bool) -> Optional[str]:
    """Grade Aria's response from the OBSERVED NEXT-TURN reaction — categorical,
    from the user's appraisal_q2 + topic-continuation (Resolution Log). Returns
    'responded_well' / 'adequately' / 'poorly', or None when the reaction is
    VALENCE_UNCERTAIN (not gradeable — do not invent; no self-report fallback).

    The INPUTS are locked by the docs (appraisal_q2 + continuation/pivot); the
    exact categorical truth table below is the most-defensible reading and is a
    TODO(build-time)-tunable POLICY — never a numeric score:
        negative reaction                 -> poorly    (it did not land)
        positive reaction + continued      -> responded_well (engaged & pleased)
        positive reaction + pivoted         -> adequately (pleased but moved on)
        neutral  reaction + continued       -> adequately
        neutral  reaction + pivoted          -> poorly    (neutral AND disengaged)
    """
    if reaction_q2 == "VALENCE_UNCERTAIN":
        return None
    if reaction_q2 == "negative":
        return QUALITY_POORLY
    if reaction_q2 == "positive":
        return QUALITY_WELL if continued_topic else QUALITY_ADEQUATELY
    # neutral (or any other non-uncertain value)
    return QUALITY_ADEQUATELY if continued_topic else QUALITY_POORLY


def _append_text(existing: str, addition: str) -> str:
    """Append a recent-learning observation (fields 3 & 4 accumulate across the
    session; flushed to graph and cleared in Step 4)."""
    existing = existing or ""
    addition = (addition or "").strip()
    if not addition:
        return existing
    return (existing + " " + addition).strip() if existing else addition
