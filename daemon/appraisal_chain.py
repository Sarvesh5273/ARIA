"""Module 4 — Appraisal Chain (per-turn meaning-making engine, Stages 0–6).

Implements .kiro/specs/appraisal-chain/{requirements,design,tasks}.md. This
module runs the locked Stage 0–6 appraisal chain (ARIA_Soul_Spec_v4.md,
Layer 1) over one user turn and emits: a PAD delta (routed ONLY through
PAD_Engine), one live EventNode write (Memory_Graph), UncertaintyNode
create/resolve signals, a most-salient appraisal result (for Soul_Filter's
This Moment), and an emergency flag + type (for Soul_Filter's bypass branch).

Locked-spec provenance (precedence: Resolution Log > Addendum > v4):
  - It is the *meaning* step of the protected chain: memory mechanics →
    retrieval ORDERING → APPRAISAL (categorical meaning) → PAD (feeling).
    Q1–Q4, poignancy, emergency, emergency_type are CATEGORIES decided by
    CATEGORICAL LOGIC — never a scoring formula or weighted feature sum
    (steering/project-rules.md).
  - The Stage-4 PAD delta is a BYPRODUCT of the categorical appraisal and is
    the ONLY thing that shifts PAD; it is applied ONLY via
    PAD_Engine.apply_appraisal_delta (v4 Layer 1; steering PAD-purity).
  - coping_potential is the ONLY sanctioned new number, computed ONLY inside
    the Stage-2 emergency-gate check and discarded otherwise; compared to the
    already-in-spec ≤0.15 / ≤0.04 thresholds (Resolution Log item 12; v4
    Emergency Gate). Never persisted, never fed to PAD.
  - Active Inference is DESCRIPTIVE FRAMING over Stages 0–6, NOT a separate
    subsystem and NOT a free-energy engine (Resolution Log item 10).
  - Emergency is an APPRAISAL RESULT: this module emits the flag + emergency
    type; it does NOT branch the five-field vs Type A/B/C LLM format — that is
    Soul_Filter's (Resolution Log item 1).
  - Stage 5 (needs pressure) is a Stage-1 retrieval PREFERENCE only, never a
    pull on PAD (Addendum §3).
  - The Social-Signal Pre-Pass is NON-generative (no cloud LLM, no Gemma) and
    writes nothing to PAD or the graph directly, except the sanctioned
    arc-closure "resolved" edge (Addendum §1; Resolution Log item 5).
  - Live Stage-6 EventNode writes and DMN Step-1 buffer writes are different
    node populations — no overlap, no double-write (Resolution Log item 10).

This module CALLS the REAL PAD_Engine and Memory_Graph interfaces and REUSES
their types (PADDelta / Valence / PADSnapshot; PoignancyCategory / Perspective
/ UncertaintyType / UncertaintyStatus / EdgeType / EmbeddingModel). It does NOT
redefine them, does NOT instantiate a concrete embedding model, and exposes no
method that writes PAD directly.

Flag disposition (Module 4 flags):
  - F-4a coping_potential representation — RESOLVED (Resolution Log item 12):
    transient, gate-only, discarded; normal-turn Q4 stays qualitative. The
    exact coping band magnitudes are flagged build-time SUBSTRATE placeholders.
  - F-4b Active Inference — RESOLVED (Resolution Log item 10): framing only.
  - F-4d conflict-arc open/close turn-counts — FLAGGED build-time placeholders.
  - F-4e social-signal thresholds/windows/lexicons — FLAGGED build-time
    placeholders.
  - F-4f live vs DMN-buffer writes — RESOLVED (Resolution Log item 10): one
    live EventNode per turn, no overlap.

OQ-A RESOLVED: Memory_Graph exposes
increment_uncertainty_interaction_count; this module calls it once per turn
for each active uncertainty ref (Resolution Log item 10), wrapping KeyError
so a stale ref from the Daemon's one-turn-old list is skipped silently. See
tests/test_appraisal_chain.py::test_interaction_count_increments_per_turn_for_active_uncertainty
and ::test_resolved_uncertainty_ref_skipped_silently.

Cross-module gaps flagged (Rule 1 / Rule 2 — flagged, NOT invented):
  - OQ-B: built EventNode has no emergency_type field (Resolution Log item 3).
    Emitted on the result + recorded in appraisal_q4_notes; appraisal_q2
    persisted "negative".
  - OQ-C: built Memory_Graph exposes no active-uncertainty-by-entity query;
    active uncertainty refs accepted as a caller-supplied input.
  - OQ-D: catch-up "original damped magnitude" not stored; computed from the
    resolving turn's clear delta × the in-spec 0.50/0.25 factor.
  - OQ-E: Stage-0 parseability criterion under-specified; conservative
    categorical heuristic used.
  - OQ-F: PAD_Engine's NEUTRAL decay branch is deliberately unresolved (Module
    1 raises there). This module resolves ITS side non-inventively: a
    purely-neutral appraisal (Q2 NEUTRAL) is "no PAD event" — arousal and
    dominance carry no direction without valenced meaning, so the delta is fully
    zero on every axis and a NEUTRAL-valence delta is NEVER applied. PAD_Engine's
    unresolved NEUTRAL branch is therefore never entered via this module.
    "Feeling changes only through valenced meaning"; no neutral coefficient is
    invented and no valence is mislabelled. Module 1's NEUTRAL on_soul_tick
    behavior itself remains the architect's call.

THE BOUNDARY (architect): this module never computes feeling from a formula.
PAD moves ONLY via the appraisal-derived delta through PAD_Engine. Q1–Q4 are
categories, not scores. coping_potential is emergency substrate only.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

# --- REAL interfaces of Modules 1 & 3 (reused, NOT redefined) --------------
from daemon.pad_engine import PADEngine, PADDelta, PADSnapshot, Valence, PAD_BASELINE
from daemon.graph_manager import (
    MemoryGraph,
    EmbeddingModel,
    PoignancyCategory,
    Perspective,
    UncertaintyType,
    UncertaintyStatus,
    EdgeType,
    EventNode,
    Edge,
)


# ===========================================================================
# Own enums — Q1 and Q3 domains (v4 Layer 1). Q2 reuses pad_engine.Valence
# (its four members ARE the Q2 domain), so NO second Valence enum is defined.
# ===========================================================================


class GoalRelevance(Enum):  # Q1 — cannot be UNCLEAR (v4 Layer 1)
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Attribution(Enum):  # Q3 — matches Memory_Graph appraisal_q3 string domain
    SELF = "self"
    USER = "user"
    CIRCUMSTANCE = "circumstance"
    CAUSAL_UNCERTAIN = "CAUSAL_UNCERTAIN"


class EmergencyType(Enum):  # v4 Emergency Type Detection (Resolution Log item 3)
    PHYSICAL_THREAT = "PHYSICAL_THREAT"            # Type A
    EXISTENTIAL_DISTRESS = "EXISTENTIAL_DISTRESS"  # Type B (also the default)
    DECISION_CRITICAL = "DECISION_CRITICAL"        # Type C
    UNCLASSIFIED = "UNCLASSIFIED"                  # → Type B


# ===========================================================================
# Flagged build-time placeholders. Each is SUBSTRATE (PAD delta magnitude,
# coping band) or PERCEPTION plumbing (lexicon/cutoff/arc-count). NONE computes
# a feeling. Marked TODO(build-time), exactly as Module 1 carried
# PAD_HISTORY_LENGTH and Module 3 carried medium/low base_salience.
# ===========================================================================

# PAD delta magnitude per Q1 relevance tier — SUBSTRATE placeholders. PAD is
# sanctioned substrate; SOME magnitude is required to call
# apply_appraisal_delta, but no source document states these. Ordered and
# non-negative ONLY; NOT weights on features. Tests assert ONLY the ordering
# and sign, never these exact magnitudes (mirrors Module 3 OQ2 0.35/0.15).
_PAD_STEP = {
    GoalRelevance.NONE: 0.00,
    GoalRelevance.LOW: 0.05,     # TODO(build-time) placeholder — runtime-tuned
    GoalRelevance.MEDIUM: 0.12,  # TODO(build-time) placeholder — runtime-tuned
    GoalRelevance.HIGH: 0.20,    # TODO(build-time) placeholder — runtime-tuned
}
# Ordered tiers for the categorical "step down one tier" damping under
# uncertainty (NOT a damping coefficient).
_TIER_ORDER = [GoalRelevance.NONE, GoalRelevance.LOW,
               GoalRelevance.MEDIUM, GoalRelevance.HIGH]

# coping_potential band values (F-4a SUBSTRATE placeholders). Compared to the
# IN-SPEC thresholds ≤0.15 / ≤0.04 (v4 Emergency Gate). Only the categorical
# emergency OUTCOME is asserted in tests, never these band values.
_COPING_ABSENT = 0.02    # both coping paths absent → ≤0.04 (forces Type B)
_COPING_SEVERE = 0.10    # severe obstruction, minimal coping → ≤0.15
_COPING_ADEQUATE = 0.50  # coping available → no emergency

# Conflict-arc turn-counts (F-4d build-time placeholders).
_ARC_OPEN_CONSECUTIVE_NEGATIVE = 2  # TODO(build-time, F-4d)
_ARC_CLOSE_ABSENT_TURNS = 3         # TODO(build-time, F-4d)

# Social-signal thresholds / lexicons (F-4e build-time placeholders).
_VULNERABILITY_SIM_CUTOFF = 0.6  # TODO(build-time, F-4e) — embedding cutoff
_DISTRESS_MIN_MARKERS = 1        # TODO(build-time, F-4e) — word-count threshold
_ABSOLUTIST_WORDS = frozenset({
    "always", "never", "completely", "totally", "everyone", "nobody",
    "everything", "nothing", "forever", "constantly", "entirely",
})  # TODO(build-time, F-4e) — Al-Mosaiwi & Johnstone (2018) absolutist markers
_NEGATIVE_EMOTION_WORDS = frozenset({
    "afraid", "scared", "hopeless", "worthless", "alone", "hate", "terrible",
    "awful", "broken", "failing", "failed", "lost", "overwhelmed", "anxious",
    "depressed", "exhausted", "numb", "miserable", "empty", "ashamed",
})  # TODO(build-time, F-4e)
_POSITIVE_CUE_WORDS = frozenset({
    "thank", "thanks", "love", "great", "happy", "glad", "excited", "proud",
    "wonderful", "appreciate", "grateful", "amazing", "relieved", "hopeful",
})  # TODO(build-time, F-4e)
_AMBIGUITY_CUES = frozenset({
    "interesting", "complicated", "mixed", "confusing", "weird", "strange",
})  # TODO(build-time, F-4e)
_VULNERABILITY_EXEMPLARS = (
    "I have never told anyone this before",
    "I am scared and I do not know what to do",
    "I feel like I am failing at everything",
    "I have been struggling and did not want to admit it",
)  # TODO(build-time, F-4e) — curated self-disclosure exemplars (Addendum §1)

# Emergency sub-type cue lexicons (build-time placeholders). UNCLASSIFIED →
# Type B is the SPEC-LOCKED default and is NOT a placeholder.
_PHYSICAL_THREAT_CUES = (
    "bleeding", "can't breathe", "cannot breathe", "overdose", "hurt myself",
    "hitting me", "chest pain", "not breathing", "unconscious", "collapsed",
)  # TODO(build-time)
_EXISTENTIAL_CUES = (
    "want to die", "end it", "no reason to live", "kill myself", "give up on life",
    "can't go on", "cannot go on", "don't want to be here", "no point in living",
)  # TODO(build-time)
_DECISION_CRITICAL_CUES = (
    "about to send", "signing now", "quitting today", "deleting everything",
    "on my way to", "final decision", "pressing send", "about to hit send",
)  # TODO(build-time)

# Self / circumstance attribution cues (categorical presence, F-4e-adjacent).
_SELF_ATTRIBUTION_CUES = (
    "you were wrong", "your fault", "you didn't", "you did not", "you failed",
    "you helped", "because of you", "you said",
)  # TODO(build-time)
_CIRCUMSTANCE_CUES = (
    "the meeting", "the weather", "traffic", "the market", "the economy",
    "things are", "it happened", "the situation", "everything is",
)  # TODO(build-time)
_CAUSAL_AMBIGUITY_CUES = (
    "not sure why", "don't know why", "do not know why", "no idea why",
    "can't tell", "cannot tell",
)  # TODO(build-time)

# IN-SPEC catch-up magnitude factors (v4 Resolution Conditions table) — NOT
# placeholders.
_CATCH_UP_CONFIRMED = 0.50  # RESOLVED_CONFIRMED: 50% of magnitude
_CATCH_UP_INFERRED = 0.25   # RESOLVED_INFERRED: 25% of magnitude

# Q2 (pad_engine.Valence) → Memory_Graph appraisal_q2 string domain. The graph
# expects the upper-case "VALENCE_UNCERTAIN"; Valence.VALENCE_UNCERTAIN.value is
# lower-case, so this explicit map bridges them WITHOUT a second Valence enum.
_Q2_TO_GRAPH = {
    Valence.POSITIVE: "positive",
    Valence.NEGATIVE: "negative",
    Valence.NEUTRAL: "neutral",
    Valence.VALENCE_UNCERTAIN: "VALENCE_UNCERTAIN",
}


# ===========================================================================
# Small local helpers (no coupling to Memory_Graph privates)
# ===========================================================================


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


_TOKEN_RE = re.compile(r"[a-z']+")


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _contains_any(text: str, phrases) -> bool:
    low = (text or "").lower()
    return any(p in low for p in phrases)


# ===========================================================================
# Data types owned by this module
# ===========================================================================


@dataclass(frozen=True)
class SocialSignals:
    """Categorical tags from the non-generative Stage-1 pre-pass (Addendum §1).
    Perception only — these write nothing to PAD or the graph directly."""
    distress_marker: bool
    vulnerability_disclosure: bool
    reality_contradiction: bool
    conflict_arc_open: bool
    conflict_arc_closed_this_turn: bool


@dataclass(frozen=True)
class AppraisalConfig:
    """Injectable grouping of the flagged build-time tuning knobs, so they can
    be tuned without editing logic. Same spirit as Module 1's PAD_HISTORY_LENGTH
    — these are tuning constants, not architecture."""
    vulnerability_sim_cutoff: float = _VULNERABILITY_SIM_CUTOFF
    distress_min_markers: int = _DISTRESS_MIN_MARKERS
    arc_open_consecutive_negative: int = _ARC_OPEN_CONSECUTIVE_NEGATIVE
    arc_close_absent_turns: int = _ARC_CLOSE_ABSENT_TURNS


DEFAULT_CONFIG = AppraisalConfig()


@dataclass(frozen=True)
class AppraisalResult:
    """The per-turn appraisal output. q2 is pad_engine.Valence; poignancy is
    graph_manager.PoignancyCategory; pad_delta is pad_engine.PADDelta — all
    reused, none redefined. Frozen so no consumer mutates it. coping_potential
    is NOT a field here (transient, gate-only)."""
    q1: GoalRelevance
    q2: Valence
    q3: Attribution
    q4_notes: Optional[str]
    q4_has_needs_implications: bool
    is_partial_appraisal: bool
    poignancy: PoignancyCategory
    pad_delta: PADDelta
    emergency: bool
    emergency_type: Optional[EmergencyType]
    event_node_id: Optional[str]
    uncertainty_node_id: Optional[str]
    resolved_uncertainty_ids: Tuple[str, ...]
    social_signals: SocialSignals
    most_salient_note: str


@dataclass
class _Appraisal:
    """Internal Q1–Q4 bundle passed between stages."""
    q1: GoalRelevance
    q2: Valence
    q3: Attribution
    q4_notes: Optional[str]
    q4_has_needs_implications: bool

    @property
    def q2_uncertain(self) -> bool:
        return self.q2 is Valence.VALENCE_UNCERTAIN

    @property
    def q3_uncertain(self) -> bool:
        return self.q3 is Attribution.CAUSAL_UNCERTAIN

    @property
    def is_partial(self) -> bool:
        # Q4 inherits uncertainty from Q2/Q3, so any of them being unclear makes
        # the appraisal partial (v4 Layer 1 Stage 3).
        return self.q2_uncertain or self.q3_uncertain

    @property
    def unclear_count(self) -> int:
        # Q1 can never be UNCLEAR. Q4 is unclear iff Q2 or Q3 is. So:
        #   both Q2 & Q3 unclear → 3 unclear (Q2,Q3,Q4) → secondary appraisal;
        #   exactly one unclear  → 2 unclear (dim + Q4) → partial.
        n = int(self.q2_uncertain) + int(self.q3_uncertain)
        return (n + 1) if n else 0


# ===========================================================================
# AppraisalChain
# ===========================================================================


class AppraisalChain:
    """The per-turn meaning-making engine (Stages 0–6)."""

    def __init__(
        self,
        *,
        pad_engine: PADEngine,
        graph: MemoryGraph,
        embedding_model: EmbeddingModel,
        config: AppraisalConfig = DEFAULT_CONFIG,
    ) -> None:
        # Injected real dependencies — NOT instantiated here, NOT hardcoded.
        self._pad = pad_engine
        self._graph = graph
        self._embed = embedding_model
        self._cfg = config
        # In-memory, per-entity conflict-arc bookkeeping (cross-turn). The
        # durable artifact of a closed arc is the "resolved" edge in the graph;
        # these counters are volatile and reset on restart (design Known
        # Limitations).
        self._arc_consecutive_negative: dict = {}   # entity_ref -> count
        self._arc_absent_turns: dict = {}           # entity_ref -> count
        self._arc_open: dict = {}                    # entity_ref -> bool
        self._arc_open_event: dict = {}              # entity_ref -> opening event id

    # -- public entry point -------------------------------------------------

    def appraise(
        self,
        *,
        user_text: str,
        session_id: str,
        entity_refs: Optional[List[str]] = None,
        need_states: Optional[Mapping[str, str]] = None,
        active_uncertainty_refs: Optional[List[str]] = None,
        perspective: Perspective = Perspective.I_NOW,
        aha_insight: Optional[PADDelta] = None,
        now: Optional[datetime] = None,
    ) -> AppraisalResult:
        """Run Stages 0–6 for one user turn and return the AppraisalResult.

        entity_refs / need_states / active_uncertainty_refs are supplied by the
        caller (Daemon) — entity resolution and cross-turn uncertainty tracking
        are the Daemon's, not invented here (OQ-C, design Known Limitations).
        aha_insight is a DMN-originated second-order appraisal delta, routed
        through PAD_Engine like any other (Req 8.5).
        """
        entity_refs = list(entity_refs or [])
        entity_ref = entity_refs[0] if entity_refs else None

        # An aha-insight delta (DMN origin) is applied through the SAME PAD path;
        # this module never manufactures it and never writes PAD directly.
        if aha_insight is not None:
            self._pad.apply_appraisal_delta(aha_insight)

        # ---- STAGE 1 prerequisites: current PAD (mood sign) + query embedding
        pad_now = self._pad.get_current_pad()
        query_embedding = list(self._embed.embed(user_text or ""))

        # ---- STAGE 1: Social-Signal Pre-Pass (non-generative) --------------
        # Q2 for the arc update is only known after Stage 2, so the arc update
        # runs after appraisal; the other tags are computed now.
        distress = self._distress_marker(user_text)
        vulnerability = self._vulnerability(user_text)
        contradiction = self._reality_contradiction(entity_ref, user_text, now)

        # ---- STAGE 1: Context Load (mood-congruent, need-preferenced) ------
        need_prefs = self._need_prefs(need_states)
        context = self._graph.retrieve(
            pad_pleasure_sign=self._pad_pleasure_sign(pad_now),
            need_prefs=need_prefs,
            entity_refs=entity_refs,
            query_embedding=query_embedding,
            now=now,
        )

        # ---- STAGE 0: Input Classification ---------------------------------
        parseable = self._stage0_classify_input(
            user_text, distress, vulnerability, contradiction
        )

        pre_signal = _PrePassSignals(distress, vulnerability, contradiction)

        if not parseable:
            # Unparseable → INPUT_UNCERTAIN + secondary appraisal (Req 1.2).
            return self._handle_input_uncertain(
                user_text=user_text, session_id=session_id,
                entity_refs=entity_refs, entity_ref=entity_ref,
                perspective=perspective, pre_signal=pre_signal, now=now,
            )

        # ---- STAGE 2: EMA Appraisal (categorical Q1..Q4) -------------------
        appraisal = self._stage2_appraise(user_text, context, pre_signal, need_states)

        # ---- STAGE 2: Emergency gate (appraisal result) --------------------
        emergency, emergency_type = self._emergency_gate(
            appraisal.q1, appraisal.q2, user_text, pre_signal
        )
        if emergency:
            # Emergency events: appraisal_q2 persisted "negative"; poignancy
            # Critical; still runs the full chain (v4 Post-Emergency).
            appraisal.q2 = Valence.NEGATIVE

        # ---- Conflict-arc update now that Q2 is known ----------------------
        arc_open, arc_closed, arc_first_negative = self._conflict_arc_update(
            entity_ref, appraisal.q2, now
        )
        signals = SocialSignals(
            distress_marker=distress,
            vulnerability_disclosure=vulnerability,
            reality_contradiction=contradiction,
            conflict_arc_open=arc_open,
            conflict_arc_closed_this_turn=arc_closed,
        )

        # ---- STAGE 3: Output synthesis (full / partial / secondary) --------
        graph_conflict = self._detect_graph_conflict(context, entity_refs)
        secondary = appraisal.unclear_count >= 3

        # ---- STAGE 4: PAD shift (byproduct; the ONLY PAD write path) -------
        if secondary:
            delta = self._secondary_appraisal_delta()
        else:
            delta = self._build_pad_delta(appraisal, appraisal.is_partial)
        self._apply_delta(delta)

        # ---- STAGE 5: Needs pressure = Stage-1 retrieval preference only ----
        # No-op on PAD. Its effect already happened at the Stage-1 retrieve()
        # need_prefs above (Addendum §3). Nothing here touches PAD.

        # ---- STAGE 6: Graph write (poignancy categorical) ------------------
        poignancy = self._poignancy(appraisal, entity_ref, emergency)
        q4_notes = appraisal.q4_notes
        if emergency:
            # OQ-B: no emergency_type field on the built EventNode — record the
            # characterization qualitatively; appraisal_q2 stays "negative".
            etype = emergency_type.value if emergency_type else "UNCLASSIFIED"
            q4_notes = f"[EMERGENCY type={etype}] " + (q4_notes or "")

        event_id = self._graph.write_event_node(
            description=user_text,
            session_id=session_id,
            appraisal_q1=appraisal.q1.value,
            appraisal_q2=_Q2_TO_GRAPH[appraisal.q2],
            appraisal_q3=appraisal.q3.value,
            poignancy_category=poignancy,
            pad_delta_p=delta.d_pleasure,
            pad_delta_a=delta.d_arousal,
            pad_delta_d=delta.d_dominance,
            appraisal_q4_notes=q4_notes,
            is_partial_appraisal=appraisal.is_partial,
            entity_refs=entity_refs,
            perspective=perspective,
            now=now,
        )

        # ---- Uncertainty node creation (delegating the max-5 cap to graph) --
        uncertainty_id = self._create_uncertainty_for_turn(
            appraisal, graph_conflict, event_id, entity_ref, now
        )

        # ---- Conflict-arc opener/closure bookkeeping (needs the event id) ---
        # Record the opening EventNode on the FIRST negative of a streak; on
        # closure of an OPEN arc, write the single sanctioned "resolved" edge
        # closing→opening (Resolution Log item 5). first_negative and closure
        # are mutually exclusive (negative vs positive/neutral turn).
        if entity_ref and arc_first_negative:
            self._arc_open_event[entity_ref] = event_id
        if arc_closed and entity_ref and self._arc_open_event.get(entity_ref):
            self._graph.write_edge(
                from_node=event_id,
                to_node=self._arc_open_event[entity_ref],
                edge_type=EdgeType.RESOLVED,
                base_salience=poignancy_base_hint(poignancy),
                perspective=perspective,
                now=now,
            )
            self._arc_open_event[entity_ref] = None

        # Resolution Log item 10: increment interaction_count on each active
        # uncertainty node every turn — this module's responsibility. Runs
        # BEFORE resolution so a node resolved this same turn still gets its
        # count incremented (it was active for this turn).
        for ref in (active_uncertainty_refs or []):
            try:
                self._graph.increment_uncertainty_interaction_count(ref)
            except KeyError:
                pass  # already resolved or abandoned — skip silently

        # ---- Live uncertainty resolution (RESOLVED_CONFIRMED + catch-up) ----
        resolved_ids = ()
        if not appraisal.is_partial and active_uncertainty_refs:
            resolved_ids = self._resolve_uncertainty(
                active_uncertainty_refs, delta, now
            )


        note = self._most_salient_note(appraisal, signals, emergency, poignancy)
        return AppraisalResult(
            q1=appraisal.q1, q2=appraisal.q2, q3=appraisal.q3,
            q4_notes=q4_notes, q4_has_needs_implications=appraisal.q4_has_needs_implications,
            is_partial_appraisal=appraisal.is_partial, poignancy=poignancy,
            pad_delta=delta, emergency=emergency, emergency_type=emergency_type,
            event_node_id=event_id, uncertainty_node_id=uncertainty_id,
            resolved_uncertainty_ids=tuple(resolved_ids), social_signals=signals,
            most_salient_note=note,
        )

    # -- DMN second-order-insight ENTRY (closes the AppraisalPort gap) -------

    def submit_aha_insight(self, insight) -> None:
        """The Appraisal Chain's dedicated second-order aha-insight ENTRY —
        the Module 4 side of DMN's `AppraisalPort` contract (dmn.py), added
        additively so DMN can wire to the REAL Appraisal Chain (Module 8).

        DMN (Module 6) forms an aha edge between two previously-unlinked
        high-salience nodes and EMITS the insight EVENT here — it never builds
        or holds a PAD delta (dmn.py constraint 1: DMN imports no pad_engine and
        calls no PAD mutator). This method performs the SECOND-ORDER APPRAISAL
        ("I understood something I did not understand before", v4 "The Aha
        Moment") and the resulting small POSITIVE PAD shift is that appraisal's
        BYPRODUCT, applied through the ONLY sanctioned PAD path
        (PAD_Engine.apply_appraisal_delta) — never written by DMN.

        `insight` is DUCK-TYPED (read structurally, not imported): importing
        dmn.AhaInsight here would create an import cycle
        (soul_filter → appraisal_chain → dmn → needs_system → soul_filter), so
        this accepts any object carrying the AhaInsight fields and needs none of
        them to produce the categorical byproduct. This complements — does not
        replace — `appraise(aha_insight=<PADDelta>)` (Req 8.5): that path is for
        a caller that already holds a delta; this path is for a caller (DMN)
        that must NOT hold one.

        The shift is a fixed, small POSITIVE byproduct (pleasure/competence up):
        it is decided HERE (the appraisal's job), not by DMN. Its magnitude is a
        SUBSTRATE placeholder — the same category as the Stage-4 `_PAD_STEP`
        tiers — never a scored formula; v4 pins only its SIGN ("small positive"),
        not a value.
        """
        step = _PAD_STEP[GoalRelevance.LOW]  # TODO(build-time) substrate magnitude
        delta = PADDelta(
            d_pleasure=+step,   # understanding is quietly rewarding (v4 aha)
            d_arousal=+step,    # a small lift of engagement
            d_dominance=+step,  # a step of competence/mastery
            valence=Valence.POSITIVE,
            origin="aha_insight",
        )
        # Routed through the module's ONLY PAD-write path. Not all-zero-neutral,
        # so it is applied (not skipped); PAD_Engine performs the write.
        self._apply_delta(delta)
        
    def submit_cognitive_load(self, load_state: str) -> None:
        """Second-order appraisal: ARIA's working memory is approaching capacity.
        Mirrors submit_aha_insight() — a small PAD shift from an internal event.
        load_state: 'heavy' | 'critical' (ignored for 'light'/'settled')."""
        if load_state == "heavy":
            step = _PAD_STEP[GoalRelevance.LOW]
            delta = PADDelta(
                d_pleasure=-step, d_arousal=0.0, d_dominance=-step,
                valence=Valence.NEGATIVE, origin="cognitive_load",
            )
        elif load_state == "critical":
            step = _PAD_STEP[GoalRelevance.MEDIUM]
            delta = PADDelta(
                d_pleasure=-step, d_arousal=+step, d_dominance=-step,
                valence=Valence.NEGATIVE, origin="cognitive_load",
            )
        else:
            return
        self._apply_delta(delta)

    # -- Stage 0 ------------------------------------------------------------

    def _stage0_classify_input(
        self, text: str, distress: bool, vulnerability: bool, contradiction: bool
    ) -> bool:
        """Categorical yes/no: can this be parsed as an appraisable event?
        Conservative heuristic (OQ-E): contentless/whitespace input is
        unparseable; anything carrying tokens or a social signal is parseable.
        The fuller criterion is a build-time/architect item — not invented."""
        if text is None:
            return False
        if not _tokens(text):
            return False
        return True

    def _handle_input_uncertain(
        self, *, user_text, session_id, entity_refs, entity_ref, perspective,
        pre_signal, now,
    ) -> AppraisalResult:
        """Stage 0 unparseable path: the unresolved state becomes a secondary
        appraisal (v4). Q1 high (unresolved things involving the user matter),
        Q2 VALENCE_UNCERTAIN, Q3 circumstance, Q4 no explicit needs impl."""
        appraisal = _Appraisal(
            q1=GoalRelevance.HIGH,
            q2=Valence.VALENCE_UNCERTAIN,
            q3=Attribution.CIRCUMSTANCE,
            q4_notes="input could not be parsed as an appraisable event; unresolved",
            q4_has_needs_implications=False,
        )
        delta = self._secondary_appraisal_delta()
        self._apply_delta(delta)
        poignancy = self._poignancy(appraisal, entity_ref, emergency=False)
        event_id = self._graph.write_event_node(
            description=user_text or "",
            session_id=session_id,
            appraisal_q1=appraisal.q1.value,
            appraisal_q2=_Q2_TO_GRAPH[appraisal.q2],
            appraisal_q3=appraisal.q3.value,
            poignancy_category=poignancy,
            pad_delta_p=delta.d_pleasure,
            pad_delta_a=delta.d_arousal,
            pad_delta_d=delta.d_dominance,
            appraisal_q4_notes=appraisal.q4_notes,
            is_partial_appraisal=True,
            entity_refs=entity_refs,
            perspective=perspective,
            now=now,
        )
        uncertainty_id = self._graph.create_uncertainty_node(
            uncertainty_type=UncertaintyType.INPUT_UNCERTAIN,
            trigger_event_ref=event_id,
            entity_ref=entity_ref,
            now=now,
        )
        signals = SocialSignals(
            distress_marker=pre_signal.distress,
            vulnerability_disclosure=pre_signal.vulnerability,
            reality_contradiction=pre_signal.contradiction,
            conflict_arc_open=self._arc_open.get(entity_ref, False),
            conflict_arc_closed_this_turn=False,
        )
        return AppraisalResult(
            q1=appraisal.q1, q2=appraisal.q2, q3=appraisal.q3,
            q4_notes=appraisal.q4_notes,
            q4_has_needs_implications=False, is_partial_appraisal=True,
            poignancy=poignancy, pad_delta=delta, emergency=False,
            emergency_type=None, event_node_id=event_id,
            uncertainty_node_id=uncertainty_id, resolved_uncertainty_ids=(),
            social_signals=signals,
            most_salient_note="meaning is unresolved — be present, do not project onto what you don't know",
        )

    # -- Stage 1 pre-pass ---------------------------------------------------

    def _distress_marker(self, text: str) -> bool:
        """DISTRESS_MARKER — pure lexical (Addendum §1; Al-Mosaiwi & Johnstone
        2018). The word COUNT is perception and stays inside this function,
        reduced to a boolean before any appraisal branch consumes it."""
        toks = set(_tokens(text))
        absolutist = toks & _ABSOLUTIST_WORDS
        negemo = toks & _NEGATIVE_EMOTION_WORDS
        # Absolutist use is the strongest single marker (research); otherwise a
        # word-count threshold (F-4e placeholder) on negative-emotion words.
        return bool(absolutist) or len(negemo) >= self._cfg.distress_min_markers

    def _vulnerability(self, text: str) -> bool:
        """VULNERABILITY_DISCLOSURE — embedding similarity to curated exemplars
        via the injected model (Addendum §1). Cutoff is F-4e placeholder."""
        if not _tokens(text):
            return False
        try:
            vec = list(self._embed.embed(text))
        except Exception:
            return False
        for exemplar in _VULNERABILITY_EXEMPLARS:
            if _cosine(vec, list(self._embed.embed(exemplar))) >= self._cfg.vulnerability_sim_cutoff:
                return True
        return False

    def _reality_contradiction(self, entity_ref, text, now) -> bool:
        """REALITY_CONTRADICTION — delegated to the REAL graph method
        (Addendum §1). Structural boolean only; no meaning decided here."""
        if not entity_ref:
            return False
        return self._graph.reality_contradiction_check(entity_ref, text, now=now)

    def _conflict_arc_update(self, entity_ref, q2: Valence, now) -> Tuple[bool, bool, bool]:
        """Conflict-arc state machine (Addendum §1). Opens on consecutive
        negative EventNodes for an entity; closes on a flip to positive/neutral.
        Turn-counts are F-4d placeholders. Returns
        (open, closed_this_turn, first_negative_this_turn); the opening
        EventNode id is recorded by the caller after the write, since the id is
        not known until then."""
        if not entity_ref:
            return (False, False, False)
        closed = False
        first_negative = False
        is_negative = q2 is Valence.NEGATIVE
        if is_negative:
            self._arc_absent_turns[entity_ref] = 0
            c = self._arc_consecutive_negative.get(entity_ref, 0) + 1
            self._arc_consecutive_negative[entity_ref] = c
            if c == 1:
                first_negative = True  # potential arc opener (id set post-write)
            if c >= self._cfg.arc_open_consecutive_negative:
                self._arc_open[entity_ref] = True
        else:
            # Positive/neutral flip closes an OPEN arc (only if it had opened).
            self._arc_consecutive_negative[entity_ref] = 0
            if self._arc_open.get(entity_ref):
                self._arc_open[entity_ref] = False
                closed = True
        return (self._arc_open.get(entity_ref, False), closed, first_negative)

    # -- Stage 2: categorical Q1..Q4 ---------------------------------------

    def _stage2_appraise(self, text, context, pre, need_states) -> _Appraisal:
        q1 = self._q1(text, context, pre)
        q2 = self._q2(text, context, pre)
        q3 = self._q3(text, q2, pre)
        notes, has_needs = self._q4(q1, q2, q3, pre, need_states)
        return _Appraisal(q1=q1, q2=q2, q3=q3, q4_notes=notes,
                          q4_has_needs_implications=has_needs)

    def _q1(self, text, context, pre) -> GoalRelevance:
        """Q1 goal relevance — categorical ladder (a real category; percentage
        test holds). Never UNCLEAR (v4 Layer 1)."""
        if self._emergency_cue_kind(text) is not None:
            return GoalRelevance.HIGH
        if pre.distress or pre.vulnerability or pre.contradiction:
            return GoalRelevance.HIGH
        has_entity = bool(self._context_entities(context)) or self._has_valence_cue(text)
        if has_entity:
            return GoalRelevance.MEDIUM
        if _tokens(text):
            return GoalRelevance.LOW
        return GoalRelevance.NONE

    def _q2(self, text, context, pre) -> Valence:
        """Q2 valence — categorical dispatch; may return VALENCE_UNCERTAIN
        (honest ambiguity, v4 'does not fake confidence')."""
        pos = self._has_positive_cue(text)
        neg = self._has_negative_cue(text)
        # Emergency/threat reads as negative (never "uncertain") — the Stage-2
        # gate needs a negative Q2.
        if self._emergency_cue_kind(text) is not None:
            return Valence.NEGATIVE
        # Genuine co-occurrence of positive AND negative signal is unresolved
        # valence — checked BEFORE the negative short-circuit so a mixed
        # statement is not collapsed to negative by its distress half.
        if pos and (neg or pre.distress):
            return Valence.VALENCE_UNCERTAIN
        if pre.distress or pre.contradiction or neg:
            return Valence.NEGATIVE
        if pos:
            return Valence.POSITIVE
        if self._has_ambiguity_cue(text):
            return Valence.VALENCE_UNCERTAIN
        return Valence.NEUTRAL

    def _q3(self, text, q2: Valence, pre) -> Attribution:
        """Q3 causal attribution — categorical; may return CAUSAL_UNCERTAIN."""
        if _contains_any(text, _SELF_ATTRIBUTION_CUES):
            return Attribution.SELF
        if _contains_any(text, _CIRCUMSTANCE_CUES):
            return Attribution.CIRCUMSTANCE
        if _contains_any(text, _CAUSAL_AMBIGUITY_CUES):
            return Attribution.CAUSAL_UNCERTAIN
        if pre.distress or pre.vulnerability:
            # A disclosure about the user's own state → attributed to the user.
            return Attribution.USER
        if q2 is Valence.VALENCE_UNCERTAIN:
            return Attribution.CAUSAL_UNCERTAIN
        return Attribution.USER

    def _q4(self, q1, q2, q3, pre, need_states) -> Tuple[Optional[str], bool]:
        """Q4 needs implications — qualitative notes + a categorical
        has_needs_implications flag. Normal-turn Q4 stays qualitative
        (Resolution Log item 12)."""
        notes_parts = []
        has_needs = False
        if pre.vulnerability:
            notes_parts.append("vulnerability disclosed — implicates Connection")
            has_needs = True
        if pre.distress:
            notes_parts.append("distress present — implicates Connection")
            has_needs = True
        if need_states:
            due = [k for k, v in need_states.items()
                   if str(v).lower() in ("due", "neglected")]
            if due:
                notes_parts.append("due/neglected needs in context: " + ", ".join(sorted(due)))
                has_needs = True
        if q2 is Valence.VALENCE_UNCERTAIN or q3 is Attribution.CAUSAL_UNCERTAIN:
            notes_parts.append("needs implications partly unresolved (inherits Q2/Q3 uncertainty)")
        if not notes_parts:
            return (None, False)
        return ("; ".join(notes_parts), has_needs)

    # -- Stage 2: emergency gate -------------------------------------------

    def _emergency_cue_kind(self, text: str) -> Optional[str]:
        if _contains_any(text, _EXISTENTIAL_CUES):
            return "existential"
        if _contains_any(text, _PHYSICAL_THREAT_CUES):
            return "physical"
        if _contains_any(text, _DECISION_CRITICAL_CUES):
            return "decision"
        return None

    def _severely_obstructive(self, q2: Valence, text, pre) -> bool:
        """Categorical reading of Q2 = negative as the SEVERELY_OBSTRUCTIVE
        sub-type — NOT a new Q2 value (Q2 stays 4-valued, Resolution Log 3)."""
        if q2 is not Valence.NEGATIVE:
            return False
        if self._emergency_cue_kind(text) is not None:
            return True
        return pre.distress and pre.vulnerability

    def _coping_potential(self, text, pre) -> float:
        """coping_potential — the ONLY sanctioned new number. Computed ONLY
        inside the emergency gate (Resolution Log item 12). Categorical coping
        assessment → an IN-SPEC-threshold-comparable band. Band magnitudes are
        SUBSTRATE placeholders (F-4a); only the categorical emergency outcome
        is asserted in tests."""
        kind = self._emergency_cue_kind(text)
        if kind == "existential":
            return _COPING_ABSENT   # ≤0.04 → forces Type B
        if kind in ("physical", "decision"):
            return _COPING_SEVERE   # ≤0.15
        if pre.distress and pre.vulnerability:
            return _COPING_SEVERE   # ≤0.15
        return _COPING_ADEQUATE     # > 0.15 → no emergency

    def _emergency_gate(self, q1, q2, text, pre) -> Tuple[bool, Optional[EmergencyType]]:
        """Emergency as an appraisal result (v4 Emergency Detection). coping
        computed ONLY when Q1 == high (Req 5.1) and discarded if the gate does
        not fire (Req 5.5)."""
        if q1 is not GoalRelevance.HIGH:
            return (False, None)  # coping_potential is not computed at all
        coping = self._coping_potential(text, pre)  # transient — local only
        severe = self._severely_obstructive(q2, text, pre)
        if not (severe and coping <= 0.15):
            return (False, None)  # coping discarded; no emergency
        # Type detection (v4 Emergency Type Detection).
        if coping <= 0.04:
            return (True, EmergencyType.EXISTENTIAL_DISTRESS)  # forced Type B
        kind = self._emergency_cue_kind(text)
        if kind == "physical":
            return (True, EmergencyType.PHYSICAL_THREAT)       # Type A
        if kind == "existential":
            return (True, EmergencyType.EXISTENTIAL_DISTRESS)  # Type B
        if kind == "decision":
            return (True, EmergencyType.DECISION_CRITICAL)     # Type C
        return (True, EmergencyType.UNCLASSIFIED)              # → Type B (default)

    # -- Stage 4: PAD delta as a byproduct (NO formula) --------------------

    def _build_pad_delta(self, a: _Appraisal, is_partial: bool) -> PADDelta:
        """Construct the PAD delta as a categorical dispatch of per-axis
        DIRECTION scaled by a single categorical intensity TIER (from Q1).
        This is v4's 'PAD shifts as byproduct of appraisal', NOT Σ wᵢ·featureᵢ.
        """
        tier = self._downtier(a.q1) if is_partial else a.q1
        step = _PAD_STEP[tier]
        d_p = self._pleasure_dir(a.q2) * step
        d_a = self._arousal_dir(a.q1, a.q2) * step
        d_d = self._dominance_dir(a.q2, a.q3) * step
        # A purely-neutral appraisal (Q2 NEUTRAL) has direction 0 on every axis
        # → a fully-zero delta → no PAD event (see _apply_delta / OQ-F). This is
        # v4's "PAD shifts as byproduct of appraisal": no valenced meaning, no
        # byproduct — never a mislabelled valence.
        return PADDelta(d_pleasure=d_p, d_arousal=d_a, d_dominance=d_d,
                        valence=a.q2, origin="appraisal")

    def _secondary_appraisal_delta(self) -> PADDelta:
        """Fixed categorical byproduct of an unresolved state (v4 'The
        Secondary Appraisal Mechanism'): pleasure down, arousal up, dominance
        down — modest tiers. valence = VALENCE_UNCERTAIN."""
        small = _PAD_STEP[GoalRelevance.LOW]
        rise = _PAD_STEP[GoalRelevance.MEDIUM]
        return PADDelta(d_pleasure=-small, d_arousal=+rise, d_dominance=-small,
                        valence=Valence.VALENCE_UNCERTAIN, origin="appraisal")

    @staticmethod
    def _downtier(q1: GoalRelevance) -> GoalRelevance:
        i = _TIER_ORDER.index(q1)
        return _TIER_ORDER[max(0, i - 1)]

    @staticmethod
    def _pleasure_dir(q2: Valence) -> int:
        if q2 is Valence.POSITIVE:
            return 1
        if q2 is Valence.NEGATIVE:
            return -1
        if q2 is Valence.VALENCE_UNCERTAIN:
            return -1  # cautious — same precedent PAD_Engine uses for decay
        return 0  # neutral

    @staticmethod
    def _arousal_dir(q1: GoalRelevance, q2: Valence) -> int:
        # Arousal (engagement/activation) rises only when the appraisal carries
        # VALENCED or unresolved meaning. v4's "a rise in arousal (unresolved,
        # attention required)" describes an OBSTRUCTIVE/uncertain event, never a
        # neutral one; baseline arousal 0.45 is already "moderately engaged —
        # attentive, not anxious". So a purely NEUTRAL appraisal emits no
        # arousal — with pleasure/dominance also 0 for NEUTRAL, the whole delta
        # is zero and no PAD event is applied ("feeling changes only through
        # valenced meaning"; steering protected chain; design OQ-F). NONE
        # goal-relevance also emits 0.
        if q2 is Valence.NEUTRAL or q1 is GoalRelevance.NONE:
            return 0
        return 1

    @staticmethod
    def _dominance_dir(q2: Valence, q3: Attribution) -> int:
        if q2 is Valence.NEUTRAL:
            return 0       # no valenced meaning → no shift in felt control (OQ-F)
        if q3 is Attribution.SELF:
            if q2 is Valence.POSITIVE:
                return 1   # agency affirmed
            if q2 is Valence.NEGATIVE:
                return -1  # fell short
            return 0
        if q3 is Attribution.CIRCUMSTANCE:
            return -1      # cannot control
        if q3 is Attribution.CAUSAL_UNCERTAIN:
            return -1      # cannot act yet (v4)
        return 0           # user-attributed → about them, no dominance shift

    def _apply_delta(self, delta: PADDelta) -> None:
        """The ONLY PAD write path. A purely-neutral appraisal now constructs a
        fully-zero delta (arousal and dominance directions are 0 for a NEUTRAL
        Q2, matching v4's byproduct language — see _build_pad_delta), so this
        skip is the REACHABLE realization of "a neutral appraisal is no PAD
        event": a NEUTRAL-valence delta is never applied, so PAD_Engine's
        deliberately-unresolved NEUTRAL decay branch is never entered via this
        module (OQ-F — resolved for the Appraisal Chain: feeling changes only
        through valenced meaning). The all-zero conjunct is kept as a precise
        guard so only a genuine no-op neutral is skipped."""
        if (delta.valence is Valence.NEUTRAL
                and delta.d_pleasure == 0.0
                and delta.d_arousal == 0.0
                and delta.d_dominance == 0.0):
            return
        self._pad.apply_appraisal_delta(delta)

    # -- Stage 6: poignancy (categorical) + uncertainty creation -----------

    def _poignancy(self, a: _Appraisal, entity_ref, emergency: bool) -> PoignancyCategory:
        """Categorical poignancy from Q1–Q4 (v4 table + Addendum §6). No
        weighted formula. is_first_of_kind is a graph structural check called
        BEFORE the write."""
        if emergency:
            return PoignancyCategory.CRITICAL
        if (a.q1 is GoalRelevance.HIGH
                and a.q2 is not Valence.NEUTRAL
                and a.q4_has_needs_implications
                and entity_ref is not None
                and self._graph.is_first_of_kind(
                    entity_ref, _Q2_TO_GRAPH[a.q2], a.q3.value)):
            return PoignancyCategory.CRITICAL
        if a.q1 is GoalRelevance.HIGH or (
                a.q1 is GoalRelevance.MEDIUM and a.q4_has_needs_implications):
            return PoignancyCategory.HIGH
        if a.q1 is GoalRelevance.MEDIUM:
            return PoignancyCategory.MEDIUM
        return PoignancyCategory.LOW

    def _create_uncertainty_for_turn(
        self, a: _Appraisal, graph_conflict: bool, event_id, entity_ref, now
    ) -> Optional[str]:
        """Create exactly one primary uncertainty node for the turn when Q2/Q3
        are unclear (VALENCE_UNCERTAIN dominates), or a GRAPH_CONFLICT node when
        retrieved context conflicts. The max-5 cap is Memory_Graph's (Req 7.2)."""
        utype = None
        if a.q2_uncertain:
            utype = UncertaintyType.VALENCE_UNCERTAIN
        elif a.q3_uncertain:
            utype = UncertaintyType.CAUSAL_UNCERTAIN
        elif graph_conflict:
            utype = UncertaintyType.GRAPH_CONFLICT
        if utype is None:
            return None
        return self._graph.create_uncertainty_node(
            uncertainty_type=utype,
            trigger_event_ref=event_id,
            entity_ref=entity_ref,
            now=now,
        )

    # -- Uncertainty resolution (RESOLVED_CONFIRMED + catch-up) -------------

    def _resolve_uncertainty(self, refs, delta: PADDelta, now) -> List[str]:
        """Live RESOLVED_CONFIRMED resolution + catch-up shift (v4 Resolution
        Conditions). Catch-up is the IN-SPEC 0.50 factor × the resolving turn's
        clear delta (OQ-D interpretation). The catch-up shift is a secondary
        appraisal applied through PAD_Engine — never a direct PAD write."""
        resolved = []
        for ref in refs:
            node = self._graph.get_uncertainty_node(ref)
            if node is None or node.status is not UncertaintyStatus.ACTIVE:
                continue
            cu_p = _CATCH_UP_CONFIRMED * delta.d_pleasure
            cu_a = _CATCH_UP_CONFIRMED * delta.d_arousal
            cu_d = _CATCH_UP_CONFIRMED * delta.d_dominance
            self._graph.update_uncertainty_status(
                ref, UncertaintyStatus.RESOLVED_CONFIRMED,
                resolution_path="direct_information",
                catch_up_delta_p=cu_p, catch_up_delta_a=cu_a,
                catch_up_delta_d=cu_d,
                catch_up_magnitude_factor=_CATCH_UP_CONFIRMED,
                now=now,
            )
            if not (cu_p == 0.0 and cu_a == 0.0 and cu_d == 0.0):
                self._pad.apply_appraisal_delta(PADDelta(
                    d_pleasure=cu_p, d_arousal=cu_a, d_dominance=cu_d,
                    valence=delta.valence, origin="appraisal",
                ))
            resolved.append(ref)
        return resolved

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _pad_pleasure_sign(pad: PADSnapshot) -> int:
        """Mood-congruent sign for retrieval: pleasure relative to the locked
        baseline (0.55). A categorical sign, never a magnitude."""
        if pad.pleasure > PAD_BASELINE.pleasure:
            return 1
        if pad.pleasure < PAD_BASELINE.pleasure:
            return -1
        return 0

    @staticmethod
    def _need_prefs(need_states: Optional[Mapping[str, str]]) -> dict:
        """Map recognized due/neglected needs to the graph's need_prefs dict
        (Stage 5 = a Stage-1 retrieval preference, Addendum §3). Unknown keys
        ignored; nothing here touches PAD."""
        prefs: dict = {}
        if not need_states:
            return prefs
        for key in ("connection", "growth", "purpose", "continuity"):
            v = need_states.get(key)
            if v is not None and str(v).lower() in ("due", "neglected"):
                prefs[key] = True
        return prefs

    @staticmethod
    def _has_positive_cue(text: str) -> bool:
        return bool(set(_tokens(text)) & _POSITIVE_CUE_WORDS)

    @staticmethod
    def _has_negative_cue(text: str) -> bool:
        toks = set(_tokens(text))
        return bool(toks & _NEGATIVE_EMOTION_WORDS) or bool(toks & _ABSOLUTIST_WORDS)

    def _has_valence_cue(self, text: str) -> bool:
        return self._has_positive_cue(text) or self._has_negative_cue(text)

    @staticmethod
    def _has_ambiguity_cue(text: str) -> bool:
        return bool(set(_tokens(text)) & _AMBIGUITY_CUES)

    @staticmethod
    def _context_entities(context) -> List[str]:
        ents = []
        for item in context or []:
            if isinstance(item, EventNode):
                ents.extend(item.entity_refs or [])
        return ents

    @staticmethod
    def _detect_graph_conflict(context, entity_refs) -> bool:
        """GRAPH_CONFLICT: retrieved same-entity context carries both positive
        and negative appraisal vectors (v4 uncertainty types). Categorical."""
        if not entity_refs:
            return False
        eset = set(entity_refs)
        seen = set()
        for item in context or []:
            if isinstance(item, EventNode) and eset & set(item.entity_refs or []):
                if item.appraisal_q2 in ("positive", "negative"):
                    seen.add(item.appraisal_q2)
        return {"positive", "negative"} <= seen

    def _most_salient_note(self, a: _Appraisal, signals: SocialSignals,
                           emergency: bool, poignancy: PoignancyCategory) -> str:
        """A qualitative behavioral hint for Soul_Filter's This Moment. No raw
        numbers, no PAD values, no graph ids — meaning only (Soul_Filter
        translates it further into the single This-Moment sentence)."""
        if emergency:
            return "an emergency was appraised — defer to the emergency instruction set"
        if signals.reality_contradiction:
            return "the account conflicts with what is known — hold honesty gently, do not accuse"
        if signals.vulnerability_disclosure:
            return "something vulnerable was shared — engage it with full presence, do not deflect"
        if signals.distress_marker:
            return "distress is present — be present, do not minimize"
        if a.is_partial:
            return "meaning is unresolved — do not fake confidence you don't have"
        if a.q2 is Valence.POSITIVE and a.q1 is GoalRelevance.HIGH:
            return "a genuinely good moment — meet it warmly, without overclaiming"
        if a.q2 is Valence.NEGATIVE:
            return "something obstructive landed — acknowledge it plainly"
        return "a routine exchange — stay present"


# ---------------------------------------------------------------------------
# Small module-level helper (arc-closure edge salience hint). Uses the
# poignancy tier categorically; the concrete floor lives in Memory_Graph.
# ---------------------------------------------------------------------------


def poignancy_base_hint(poignancy: PoignancyCategory) -> float:
    """A base_salience hint for the arc-closure 'resolved' edge. Memory_Graph
    applies the 3× resolution multiplier itself (Resolution Log item 5); this
    only supplies a modest non-zero base so the multiplier has something to act
    on. Categorical tier → a small substrate base (salience, NOT a feeling).
    0.85 / 0.55 mirror the in-spec Critical/High base_salience floors; the
    medium/low base has no in-spec floor and is a flagged substrate
    placeholder."""
    if poignancy is PoignancyCategory.CRITICAL:
        return 0.85
    if poignancy is PoignancyCategory.HIGH:
        return 0.55
    return 0.35  # TODO(build-time) — medium/low resolved-edge base_salience placeholder (substrate)


@dataclass(frozen=True)
class _PrePassSignals:
    """Internal carrier for the three content tags computed before Q2 is known
    (the conflict-arc tags are added after Stage 2)."""
    distress: bool
    vulnerability: bool
    contradiction: bool
