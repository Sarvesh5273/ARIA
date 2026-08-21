# Design Document — Module 4: Appraisal Chain

> ## AMENDMENT 2026-08-20 — conflict-arc 2nd close condition implemented
>
> Three changes; the body below is superseded on each.
>
> **1. Addendum §1's SECOND close condition now exists in behaviour.** The arc
> *"closes when a later EventNode on that entity_ref flips to Q2=positive/neutral,
> **or enough turns pass without that entity recurring**"*. Only the flip was
> implemented; `_arc_absent_turns` was reset but never incremented and never read.
> New `_conflict_arc_absence_close()` runs once per turn, increments the counter for
> every open arc whose entity did NOT recur (including turns with no entity at
> all), and closes those at the threshold. **Categorical** — the turns have passed
> or they have not; no score, no partial close. Absence closures write the same
> single `"resolved"` edge as a Q2 flip.
>
> **2. `_ARC_CLOSE_ABSENT_TURNS` is 5, not 3** — architect-set when the mechanism
> landed. Both are `TODO(build-time)` placeholders, so no locked value was
> overridden. In code the name is an ALIAS of
> `_CONFLICT_ARC_ABSENT_TURN_THRESHOLD`, so the knob and its `AppraisalConfig`
> override cannot drift apart.
>
> **3. The `"resolved"` edge's `base_salience` is DERIVED, not invented.**
> `poignancy_base_hint()` is **deleted** — it returned 0.35 for medium/low, the
> same class of invented magnitude removed from Module 3's OQ2. v4 "Argument Buffer
> Mode" names the multiplicand: the resolution is *"weighted 3× higher than **the
> conflict itself**"*. The edge now takes the **opening EventNode's own
> `base_salience`**. An arc only opens on a Q2=negative EventNode, so the Baumeister
> +0.15 guarantees a non-zero multiplicand at every tier (critical 1.00→3.00, high
> 0.70→2.10, medium/low 0.15→0.45) and ResLog item 5's 3× always has something real
> to act on.
>
> **Also:** `_need_prefs` now keys Connection on `neglected` ALONE, per Addendum §3
> (*"When Connection is **neglected**, Stage 1 surfaces 'We'-perspective and
> Connection-positive edges first"*). It previously fired on `due` too —
> unavoidable while Needs System could not emit `neglected`, but it applied the
> strong preference at the weak state. Growth/Purpose/Continuity untouched; §3
> exemplifies only Connection's profile.
>
> **Known open item:** nothing in the codebase READS edge `salience` for any
> decision, so item 5's 3× is representational only. `resolved_edge_exists()` — its
> own named consumer — selects on `edge_type` + `created`.

## Overview

Appraisal_Chain is Aria's per-turn meaning-making engine. It runs the locked
Stage 0–6 chain (`ARIA_Soul_Spec_v4.md`, Layer 1) over one user turn and emits
five things: a PAD delta (routed through PAD_Engine), one live EventNode write
(to Memory_Graph), UncertaintyNode create/resolve signals, a most-salient
appraisal result (for Soul_Filter's This Moment), and an emergency flag + type
(for Soul_Filter's bypass branch).

It is the *meaning* step of the protected chain — memory mechanics → retrieval
ORDERING → **appraisal (categorical meaning)** → PAD (feeling). Everything it
decides that matters (Q1–Q4, poignancy, emergency, emergency_type) is a
category decided by categorical logic. The one place a number leaves this
module — the PAD delta — is a *byproduct* of that categorical appraisal,
applied only via `PAD_Engine.apply_appraisal_delta`. There is no path in this
module from "input features × weights" to a feeling, and no direct PAD write.

This design implements `requirements.md` using only mechanisms already
specified there or in the supporting documents. It calls the **real** built
interfaces of PAD_Engine (`daemon/pad_engine.py`) and Memory_Graph
(`daemon/graph_manager.py`) and reuses their types (`PADDelta`, `Valence`,
`PoignancyCategory`, `Perspective`, `UncertaintyType`, `UncertaintyStatus`,
`EdgeType`, the `EmbeddingModel` Protocol) rather than redefining them.
Genuinely undefined items are carried as flagged placeholders or Open
Questions (Rule 1), and no document conflict is silently resolved (Rule 2).

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. Q1–Q4 are categorical outcomes decided by categorical logic — never a
   scoring formula or weighted feature sum (Req 4.5; steering "The protected
   chain").
2. The Stage-4 PAD delta is a byproduct of the categorical appraisal and is the
   ONLY thing that shifts PAD; it is applied ONLY via
   `PAD_Engine.apply_appraisal_delta(PADDelta(...))` (Req 8.1, 8.2; steering
   PAD-purity). No method on this module writes PAD directly.
3. `coping_potential` is the only sanctioned new number, computed ONLY inside
   the Stage-2 emergency-gate check and discarded otherwise; never persisted,
   never fed to PAD (Req 5.5; Resolution Log item 12).
4. No other invented score/percentage/threshold. Substrate magnitudes (PAD
   delta step-sizes, coping band values) are flagged placeholders, asserted
   only for ordering/category, never a derived value (Req 14.2).
5. Active Inference is descriptive framing over Stages 0–6 — no separate
   subsystem, no free-energy engine (Req 14.3; Resolution Log item 10).
6. Emergency is an appraisal result: this module emits the flag + type; it does
   NOT branch the LLM instruction format (Soul_Filter does — Req 12.1;
   Resolution Log item 1).
7. The Social-Signal Pre-Pass is non-generative (no cloud LLM, no Gemma) and
   writes nothing to PAD or the graph directly (Req 3.1, 3.6; Addendum §1).
8. Stage 5 is a Stage-1 retrieval preference only — never a pull on PAD
   (Req 9; Addendum §3).
9. PAD_Engine, Memory_Graph, and the Embedding_Model are injected; only their
   real public interfaces are called; their types are not redefined; no
   concrete embedding model is instantiated or hardcoded (Req 14.4).

## Architecture

```
                       ┌──────────────────────────────────────────────────────┐
  user turn (text) ───▶│                   Appraisal_Chain                      │
  entity_refs          │                (appraisal_chain.py)                    │
  need_states ─────────│                                                        │
  active_uncertainty   │   ┌─────────────────────────────────────────────────┐ │
  (Daemon cross-turn)  │   │ STAGE 0  Input Classification (categorical y/n)  │ │
                       │   │   unparseable → INPUT_UNCERTAIN + secondary appr.│ │
                       │   └───────────────────────┬─────────────────────────┘ │
   PAD_Engine ─────────┼─get_current_pad()─┐       ▼                            │
   (Module 1)          │   ┌───────────────┴─────────────────────────────────┐ │
                       │   │ STAGE 1  Context Load                            │ │
   Memory_Graph ◀──────┼─retrieve(pad_sign,need_prefs,entity_refs,query_emb)  │ │
   (Module 3)          │   │   + Social-Signal Pre-Pass (NON-generative):     │ │
   Embedding_Model ────┼─▶ │     DISTRESS_MARKER (lexical word-count)         │ │
   (injected Protocol) │   │     VULNERABILITY_DISCLOSURE (embed similarity)  │ │
                       │   │     REALITY_CONTRADICTION (graph.rcc)            │ │
                       │   │     Conflict-arc state machine → resolved edge   │ │
                       │   └───────────────────────┬─────────────────────────┘ │
                       │   ┌───────────────────────▼─────────────────────────┐ │
                       │   │ STAGE 2  EMA Appraisal — categorical Q1..Q4      │ │
                       │   │   + Emergency gate (Q1=high & SEV_OBSTR &        │ │
                       │   │     coping_potential≤0.15; ≤0.04→Type B)         │ │
                       │   └───────────────────────┬─────────────────────────┘ │
                       │   ┌───────────────────────▼─────────────────────────┐ │
                       │   │ STAGE 3  Output synthesis                        │ │
                       │   │   full / partial(+UncertaintyNode) / secondary   │ │
                       │   │   GRAPH_CONFLICT; resolve prior uncertainty      │ │
                       │   └───────────────────────┬─────────────────────────┘ │
                       │   ┌───────────────────────▼─────────────────────────┐ │
   PAD_Engine ◀────────┼─apply_appraisal_delta(PADDelta) STAGE 4  PAD shift   │ │
                       │   │   byproduct: dir(cat) × tier(cat); valence=Q2    │ │
                       │   └───────────────────────┬─────────────────────────┘ │
                       │   ┌───────────────────────▼─────────────────────────┐ │
                       │   │ STAGE 5  Needs pressure = Stage-1 retrieval pref │ │
                       │   │          only (NO PAD pull)  → no-op on PAD      │ │
                       │   └───────────────────────┬─────────────────────────┘ │
                       │   ┌───────────────────────▼─────────────────────────┐ │
   Memory_Graph ◀──────┼─write_event_node(...)  STAGE 6  Graph write         │ │
   is_first_of_kind ◀──┼─ (poignancy: categorical, first-of-kind check)      │ │
                       │   └───────────────────────┬─────────────────────────┘ │
                       │                           ▼                            │
                       │                    AppraisalResult ────────────────────┼─▶ Soul_Filter
                       │        (most-salient note + emergency flag/type;        │   (This Moment,
                       │         categorical/qualitative — no raw PAD/graph)     │    bypass)
                       └────────────────────────────────────────────────────────┘
```

The chain has exactly one public entry point, `appraise(...)`, which runs
Stages 0–6 in order and returns an `AppraisalResult`. Side effects (PAD delta,
graph writes) happen through the injected modules' real interfaces during the
relevant stages.

## Components and Interfaces

### AppraisalChain (class, `appraisal_chain.py`)

Constructed with injected dependencies; owns no persistent state beyond the
conflict-arc bookkeeping (which is per-entity, in-memory, cross-turn).

```python
class AppraisalChain:
    def __init__(
        self,
        *,
        pad_engine: "PADEngine",           # daemon.pad_engine.PADEngine (real)
        graph: "MemoryGraph",              # daemon.graph_manager.MemoryGraph (real)
        embedding_model: "EmbeddingModel", # graph_manager.EmbeddingModel Protocol
        config: "AppraisalConfig" = DEFAULT_CONFIG,
    ) -> None: ...

    def appraise(
        self,
        *,
        user_text: str,
        session_id: str,
        entity_refs: Optional[List[str]] = None,
        need_states: Optional[Mapping[str, str]] = None,   # {"connection":"neglected",...}
        active_uncertainty_refs: Optional[List[str]] = None,  # OQ-C (Daemon-held)
        perspective: "Perspective" = Perspective.I_NOW,
        aha_insight: Optional["PADDelta"] = None,          # Req 8.5 (DMN origin)
        now: Optional[datetime] = None,
    ) -> "AppraisalResult": ...
```

`appraise` orchestrates the stages. It reads current PAD via
`pad_engine.get_current_pad()` (Req 2.2), embeds `user_text` via
`embedding_model.embed(...)`, and calls Memory_Graph's real methods. If
`aha_insight` is supplied, its delta is routed to
`pad_engine.apply_appraisal_delta` (Req 8.5) — the chain does not manufacture
aha deltas; DMN supplies them.

### Stage helpers (private, one per stage — each pure/categorical where possible)

- `_stage0_classify_input(user_text, signals) -> bool` — categorical
  parseability (Req 1; OQ-E heuristic).
- `_stage1_context_load(...) -> (List[RetrievalItem], SocialSignals)` — calls
  `graph.retrieve(...)` and `_social_signal_pre_pass(...)`.
- `_social_signal_pre_pass(user_text, entity_refs, now) -> SocialSignals` —
  DISTRESS_MARKER (lexical), VULNERABILITY_DISCLOSURE (embedding), 
  REALITY_CONTRADICTION (`graph.reality_contradiction_check`), conflict-arc
  update. Non-generative; no PAD/graph write except the arc-closure
  `"resolved"` edge (Req 3.7) which is a graph *edge* write, explicitly
  sanctioned by Resolution Log item 5 and is not a PAD write.
- `_stage2_appraise(user_text, context, signals) -> _Q` — decides Q1, Q2, Q3
  categorically; returns an internal `_Q` holding the four categorical outcomes
  plus the SEVERELY_OBSTRUCTIVE sub-flag.
- `_emergency_gate(q, signals) -> (bool, Optional[EmergencyType])` — computes
  the transient `coping_potential` and the categorical gate (Req 5).
- `_stage3_synthesis(q, context, active_uncertainty_refs) -> _Synthesis` —
  full/partial/secondary; creates UncertaintyNode(s); resolves prior
  uncertainty.
- `_build_pad_delta(q, is_partial) -> PADDelta` — the byproduct construction
  (see "PAD Delta as a Byproduct").
- `_stage6_write(...) -> str` — poignancy (categorical, with
  `graph.is_first_of_kind`) + `graph.write_event_node`.

### Reused external types (NOT redefined here)

From `daemon/pad_engine.py`: `PADEngine`, `PADDelta`, `PADSnapshot`, `Valence`.
From `daemon/graph_manager.py`: `MemoryGraph`, `PoignancyCategory`,
`Perspective`, `UncertaintyType`, `UncertaintyStatus`, `EdgeType`,
`EmbeddingModel`, `RetrievalItem`, `EventNode`, `Edge`.

Q2 uses PAD_Engine's `Valence` enum directly (its four members are exactly the
Q2 domain). The only friction is the graph's string domain: Memory_Graph
expects `appraisal_q2 == "VALENCE_UNCERTAIN"` (upper) while
`Valence.VALENCE_UNCERTAIN.value == "valence_uncertain"` (lower). This design
translates via an explicit `_Q2_TO_GRAPH` mapping at the write boundary — it
does NOT introduce a second Valence enum.

## Data Types (owned by this module)

```python
class GoalRelevance(Enum):     # Q1 — v4 Layer 1 (cannot be UNCLEAR)
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Attribution(Enum):       # Q3 — v4 Layer 1 (graph appraisal_q3 domain)
    SELF = "self"
    USER = "user"
    CIRCUMSTANCE = "circumstance"
    CAUSAL_UNCERTAIN = "CAUSAL_UNCERTAIN"

class EmergencyType(Enum):     # v4 Emergency Type Detection (Resolution Log 3)
    PHYSICAL_THREAT = "PHYSICAL_THREAT"        # Type A
    EXISTENTIAL_DISTRESS = "EXISTENTIAL_DISTRESS"  # Type B (also the default)
    DECISION_CRITICAL = "DECISION_CRITICAL"    # Type C
    UNCLASSIFIED = "UNCLASSIFIED"              # → Type B

@dataclass(frozen=True)
class SocialSignals:           # Addendum §1 — categorical tags only
    distress_marker: bool
    vulnerability_disclosure: bool
    reality_contradiction: bool
    conflict_arc_open: bool
    conflict_arc_closed_this_turn: bool

@dataclass(frozen=True)
class AppraisalResult:         # emitted to callers / Soul_Filter
    q1: GoalRelevance
    q2: Valence                # reused from pad_engine
    q3: Attribution
    q4_notes: Optional[str]
    q4_has_needs_implications: bool
    is_partial_appraisal: bool
    poignancy: PoignancyCategory   # reused from graph_manager
    pad_delta: PADDelta            # reused from pad_engine (already applied)
    emergency: bool
    emergency_type: Optional[EmergencyType]
    event_node_id: Optional[str]
    uncertainty_node_id: Optional[str]
    resolved_uncertainty_ids: Tuple[str, ...]
    social_signals: SocialSignals
    most_salient_note: str         # categorical/qualitative — for This Moment
```

`Q2` is `pad_engine.Valence`; `poignancy` is `graph_manager.PoignancyCategory`;
`pad_delta` is `pad_engine.PADDelta` — all reused, none redefined.
`AppraisalResult` is frozen so no consumer mutates it.

`AppraisalConfig` is a frozen dataclass carrying the **flagged build-time
placeholders** (below) so they are injectable/tunable without editing logic —
the same spirit as Module 1's `PAD_HISTORY_LENGTH` constant, but grouped for
clarity that they are tuning knobs, not architecture.

## Constants and Flagged Placeholders

```python
# ── PAD delta magnitude step-sizes (SUBSTRATE placeholders) ────────────────
# TODO(build-time): the per-Q1-tier magnitude of the appraisal-derived PAD
# delta. PAD is sanctioned substrate; SOME magnitude is required to call
# apply_appraisal_delta, but no source document states these. Ordered and
# non-negative ONLY; NOT weights on features; tests assert ordering, never the
# exact value (mirrors Module 3's OQ2 base_salience placeholders 0.35/0.15).
_PAD_STEP = {
    GoalRelevance.NONE:   0.00,
    GoalRelevance.LOW:    0.05,   # TODO(build-time) placeholder
    GoalRelevance.MEDIUM: 0.12,   # TODO(build-time) placeholder
    GoalRelevance.HIGH:   0.20,   # TODO(build-time) placeholder
}

# ── coping_potential band values (F-4a SUBSTRATE placeholders) ─────────────
# TODO(build-time): coping_potential is compared to the IN-SPEC thresholds
# ≤0.15 / ≤0.04. The categorical coping assessment maps to these bands; only
# the categorical emergency OUTCOME is asserted in tests, never the value.
_COPING_ABSENT   = 0.02   # both coping paths absent → ≤0.04 (forces Type B)
_COPING_SEVERE   = 0.10   # severe obstruction, minimal coping → ≤0.15
_COPING_ADEQUATE = 0.50   # coping available → no emergency

# ── F-4d conflict-arc turn-counts (build-time placeholders) ────────────────
_ARC_OPEN_CONSECUTIVE_NEGATIVE = 2   # TODO(build-time, F-4d)
_ARC_CLOSE_ABSENT_TURNS        = 5   # TODO(build-time, F-4d) — was 3; architect
                                     # set 5 on 2026-08-20 when the absence close
                                     # was implemented. In code this name is an
                                     # ALIAS of _CONFLICT_ARC_ABSENT_TURN_THRESHOLD
                                     # so the knob and its AppraisalConfig
                                     # override cannot drift apart.

# ── F-4e social-signal thresholds / lexicons (build-time placeholders) ─────
_VULNERABILITY_SIM_CUTOFF = 0.6      # TODO(build-time, F-4e)
_DISTRESS_MIN_MARKERS     = 1        # TODO(build-time, F-4e) word-count threshold
_ABSOLUTIST_WORDS = frozenset({"always","never","completely","totally",
    "everyone","nobody","everything","nothing","forever"})   # TODO(build-time)
_NEGATIVE_EMOTION_WORDS = frozenset({"afraid","scared","hopeless","worthless",
    "alone","hate","terrible","awful","broken","failing","lost","overwhelmed",
    "anxious","depressed","exhausted","numb"})               # TODO(build-time)
_VULNERABILITY_EXEMPLARS = (                                  # TODO(build-time)
    "I've never told anyone this",
    "I'm scared and I don't know what to do",
    "I feel like I'm failing at everything",
)

# ── Emergency sub-type cue lexicons (build-time placeholders) ──────────────
_PHYSICAL_THREAT_CUES = frozenset({"bleeding","can't breathe","overdose",
    "hurt myself","he's hitting","fire","accident","chest pain"})  # TODO(build-time)
_EXISTENTIAL_CUES = frozenset({"want to die","end it","no reason to live",
    "kill myself","give up","worthless","can't go on"})            # TODO(build-time)
_DECISION_CRITICAL_CUES = frozenset({"about to send","signing now","quitting today",
    "deleting everything","on my way to","final decision"})        # TODO(build-time)

# ── In-spec catch-up magnitude factors (NOT placeholders) ──────────────────
_CATCH_UP_CONFIRMED = 0.50   # v4 Resolution Conditions table
_CATCH_UP_INFERRED  = 0.25   # v4 Resolution Conditions table
```

Every placeholder above is either SUBSTRATE (PAD delta magnitudes, coping
bands) or PERCEPTION plumbing (lexicons, cutoffs, arc counts). None computes a
feeling; each is marked `TODO(build-time)`. The catch-up factors and the
emergency thresholds (≤0.15/≤0.04) and UNCLASSIFIED→Type B are in-spec and are
NOT placeholders.

## Stage 2 — Deciding Q1–Q4 Categorically (the core anti-formula design)

The chain answers the four questions with **categorical decision procedures**
over categorical inputs — never a numeric score. The inputs are:

- the `SocialSignals` tags (perception primitives — a word count / similarity /
  contradiction flag is perception, per Addendum §1 Standing Principle
  "Perception vs. appraisal");
- categorical lexical cues (`_positive_cue`, `_negative_cue` presence — booleans
  derived from small flagged lexicons; presence/absence, not a tally-threshold
  score);
- the retrieved graph context's prior appraisal profile for the entity
  (categorical: prior-positive / prior-negative / conflicting);
- the current PAD pleasure *sign* (categorical: +/0/−), used only as a tie
  context, never as a magnitude.

**Q1 (Goal_Relevance)** — categorical ladder (a real category; the percentage
test holds — "either it clears the threshold or it doesn't"):
- `high` if a DISTRESS_MARKER, VULNERABILITY_DISCLOSURE, or REALITY_CONTRADICTION
  tag is present, or the turn references a known entity with a strong prior
  appraisal profile;
- `medium` if it references a known entity or carries a valence cue;
- `low` if it is on-topic but affectively flat;
- `none` if contentless (and Stage 0 already routes truly unparseable input to
  INPUT_UNCERTAIN).

**Q2 (Valence)** — categorical dispatch, allowed to return VALENCE_UNCERTAIN:
- `negative` if DISTRESS_MARKER or REALITY_CONTRADICTION present, or a negative
  cue with no positive cue;
- `positive` if a positive cue with no negative/distress signal;
- `neutral` if no valence cue and no distress/vulnerability;
- `VALENCE_UNCERTAIN` if positive and negative cues both present with no
  tie-break, or the signals conflict — honest ambiguity, not a forced pick
  (v4 "Aria does not fake confidence she does not have").

**Q3 (Causal_Attribution)** — categorical, allowed to return CAUSAL_UNCERTAIN:
- `user` when the disclosure is about the user's own state (default for
  VULNERABILITY_DISCLOSURE / DISTRESS_MARKER about the speaker);
- `self` when cues attribute the event to Aria's own action;
- `circumstance` when cues attribute it to external situation;
- `CAUSAL_UNCERTAIN` when attribution genuinely cannot be read.

**Q4 (Needs_Implications)** — qualitative notes + a categorical
`has_needs_implications` flag. The notes are free text summarizing which need
the appraisal implicates (Connection for vulnerability/connection cues, etc.),
inheriting uncertainty from Q2/Q3. Normal-turn Q4 stays qualitative (Resolution
Log item 12); the boolean flag is what the poignancy decision reads.

None of these is `score = Σ wᵢ·featureᵢ`. Each is a branch table over
categorical presence/absence. The lexicons and the DISTRESS count threshold are
flagged build-time placeholders (F-4e); the word *count* stays entirely inside
the perception pre-pass and is reduced to a boolean tag before any appraisal
branch consumes it, so the appraisal logic sees only categories.

## Stage 2 — Emergency Gate

Computed only when `Q1 == high` (Req 5.1). The gate is categorical over a
transient substrate value:

1. **SEVERELY_OBSTRUCTIVE sub-type**: Q2 is characterized as the severe sub-type
   when the negative appraisal reflects a threat (physical / existential /
   decision-critical cue present, or DISTRESS_MARKER + VULNERABILITY_DISCLOSURE
   together). This is a categorical reading of Q2 = negative, not a new Q2 value
   (Q2 stays 4-valued; Resolution Log item 3).
2. **coping_potential** (the only sanctioned new number): a categorical coping
   assessment — problem-focused coping (can anyone act on it?) × emotion-focused
   coping (can it be endured now?) ∈ {available, limited, absent}. The
   assessment maps to a band value (`_COPING_ABSENT` / `_COPING_SEVERE` /
   `_COPING_ADEQUATE`). Computed here and discarded after the gate (Req 5.5).
3. **Gate** (Req 5.2): emergency ⇔ `Q1 == high AND severely_obstructive AND
   coping_potential <= 0.15`.
4. **Type** (Req 5.3, 5.4): `coping_potential <= 0.04` → force
   `EXISTENTIAL_DISTRESS` (Type B). Otherwise PHYSICAL_THREAT cue → Type A;
   existential cue → Type B; decision-critical cue → Type C; none readable →
   UNCLASSIFIED → Type B (default; v4 "Type B is the default").

The gate outcome is a category; `coping_potential`'s exact band magnitudes are
flagged placeholders and are never asserted directly in tests — only the
categorical emergency/type outcome is.

## PAD Delta as a Byproduct (Stage 4 — no formula)

The PAD delta is constructed by `_build_pad_delta(q, is_partial)` as a
**categorical dispatch of direction, scaled by a single categorical intensity
tier**. This is the honest realization of v4's "PAD shifts as byproduct of
appraisal — never as direct assignment." It is NOT `Σ wᵢ·featureᵢ`.

**Per-axis direction** (each a categorical sign ∈ {−1, 0, +1}, grounded in
v4's own directional language — "a drop in pleasure (obstructive), a rise in
arousal (unresolved, attention required), and a slight drop in dominance
(cannot act yet)"):

- **Pleasure** ← Q2: `positive → +1`, `negative → −1`, `neutral → 0`,
  `VALENCE_UNCERTAIN → −1` (cautious — the same "ambiguous defaults to the more
  cautious treatment" precedent PAD_Engine uses for VALENCE_UNCERTAIN decay).
- **Arousal** ← engagement, but only for VALENCED/unresolved meaning:
  `Q2 = neutral → 0` and `Q1 = none → 0`; otherwise `+1` (a valenced or
  uncertain event engages attention). v4's "a rise in arousal (unresolved,
  attention required)" is described for an *obstructive/uncertain* event, never
  a neutral one, and baseline arousal 0.45 is already "moderately engaged" — so
  a purely-neutral appraisal emits no arousal.
- **Dominance** ← (Q2 × Q3): `neutral → 0` (no valenced meaning → no shift in
  felt control); `self+positive → +1` (agency), `self+negative → −1`,
  `circumstance → −1` (cannot control), `CAUSAL_UNCERTAIN → −1` (cannot act
  yet), `user → 0`, else `0`.

**Magnitude** = a single categorical tier `_PAD_STEP[Q1]` (none/low/medium/high
→ one of four discrete step-sizes). Exactly one tier per turn, applied in the
directions the categories dictate: `d_pleasure = pleasure_dir × step`, likewise
for arousal/dominance.

**Damping under uncertainty** (Req 8.4): when `is_partial`, the tier is stepped
DOWN one level categorically (`high→medium→low→none`) before use — a categorical
step-down, not a damping coefficient, and NOT a coping_potential multiplication
(coping_potential is not computed on normal turns).

**Purely-neutral appraisal → no PAD event** (design decision resolving OQ-F on
this module's side): when Q2 = neutral, all three directions are 0, so the
constructed delta is fully zero with `valence = NEUTRAL`, and `_apply_delta`
skips it — PAD does not move and PAD_Engine's `_last_applied_valence` is never
set to NEUTRAL. This is the faithful realization of "PAD shifts as byproduct of
appraisal" (v4 Stage 4): a neutral appraisal carries no valenced meaning, so
there is no byproduct ("feeling changes only through valenced meaning",
steering protected chain). It is NOT a mislabelled valence and NOT an invented
neutral coefficient — it *removes* a movement rather than inventing one, and
keeps this module from ever steering PAD_Engine into its deliberately-unresolved
NEUTRAL decay branch. Module 1's own NEUTRAL `on_soul_tick` behavior is
unchanged and remains the architect's call; it is simply never reached via the
Appraisal Chain.

**Secondary-appraisal delta** (Stage 0 INPUT_UNCERTAIN, Stage 3 with 3 UNCLEAR):
a fixed categorical profile matching v4's described byproduct — pleasure down
one small tier, arousal up one tier, dominance down one small tier — with
`valence = VALENCE_UNCERTAIN`.

**Valence** on the `PADDelta` is `Q2` directly (a `Valence` member). PAD_Engine
then selects the decay coefficient from it (negative & VALENCE_UNCERTAIN → 0.6;
positive → 0.75) — that is where negativity bias lives, NOT in the delta
magnitude (Req 8.3). This module never inflates the negative delta and never
touches decay.

**Application**: `pad_engine.apply_appraisal_delta(delta)` — the only PAD write
(Req 8.2). The same components are passed to `write_event_node` as
`pad_delta_p/a/d` so the graph records the appraisal vector (Req 10.1).

## Stage 6 — Poignancy (categorical) and Graph Write

Poignancy is derived directly from Q1–Q4 (no separate weighted computation, v4):

- **Critical**: `Q1 == high AND Q2 != neutral AND q4_has_needs_implications AND
  is_first_of_kind`, where `is_first_of_kind = graph.is_first_of_kind(entity_ref,
  q2_str, q3_str)` — called BEFORE the write so the current event does not make
  itself non-first (Addendum §6; novel entities return True trivially). With no
  entity_ref, first-of-kind cannot hold → falls through to High.
- **High**: `Q1 == high OR (Q1 == medium AND q4_has_needs_implications)`.
- **Medium**: `Q1 == medium` (and Q4 null/partial).
- **Low**: `Q1 in {none, low}`.
- **Emergency turns** → Critical (Req 11.4).

Then `graph.write_event_node(...)` with the graph-domain strings for Q1/Q2/Q3,
`appraisal_q4_notes` (including the emergency characterization when the gate
fired — OQ-B), `poignancy_category`, the PAD delta components,
`is_partial_appraisal`, `uncertainty_node_ref`, `entity_refs`, `perspective`.
Exactly one live EventNode per turn (Req 10.2; F-4f — no overlap with DMN buffer
writes). Zone/prosody/Soul_Filter synthesis are NOT done here (Req 10.3).

## Uncertainty Lifecycle Handling

- **Creation**: via `graph.create_uncertainty_node(uncertainty_type=...,
  trigger_event_ref=..., entity_ref=...)`. The max-5 cap and force-abandon are
  Memory_Graph's (Req 7.2) — this module does not re-implement them.
  `trigger_event_ref` links to the turn's EventNode; because the EventNode id
  is only known after `write_event_node`, the chain writes the EventNode first,
  then creates the UncertaintyNode with that id, then (if needed) the EventNode
  already carries `uncertainty_node_ref` — see Known Limitations for the
  ordering note and how it is handled (create uncertainty first with a deferred
  trigger, or write event then uncertainty then accept the one-way link).
- **Resolution (live, RESOLVED_CONFIRMED)**: when Stage 3 is all-clear and
  `active_uncertainty_refs` were supplied (OQ-C), each matching node is resolved
  via `graph.update_uncertainty_status(node_id, RESOLVED_CONFIRMED,
  resolution_path="direct_information", catch_up_*=..., 
  catch_up_magnitude_factor=_CATCH_UP_CONFIRMED)` and the catch-up PAD shift
  (`_CATCH_UP_CONFIRMED × this turn's clear delta`, OQ-D) is applied via
  `pad_engine.apply_appraisal_delta`.
- **interaction_count increment** (Req 7.4): responsibility recorded; blocked by
  OQ-A (no public increment surface on the built graph). Not implemented via a
  private-write workaround.

## Error Handling

- **Empty/whitespace `user_text`**: treated as unparseable at Stage 0 →
  INPUT_UNCERTAIN + secondary appraisal (Req 1.2). Not an exception — it is a
  valid (if contentless) turn.
- **Embedding model returns an empty/degenerate vector**: retrieval degrades
  gracefully (Memory_Graph already handles empty candidate sets);
  VULNERABILITY_DISCLOSURE is simply not flagged. No crash.
- **`entity_refs` empty**: retrieval and REALITY_CONTRADICTION run with no
  entity constraint (contradiction check needs an entity, so it returns False);
  poignancy Critical cannot be reached (no first-of-kind entity) → High ceiling.
  Documented, not an error.
- **Calls with an un-wired PAD_Engine (before `initialize()`)**: PAD_Engine
  raises `RuntimeError` from its own guard; the chain does not suppress it — a
  caller must initialize PAD_Engine first (documented precondition).
- **NEUTRAL-valence PAD delta**: a neutral appraisal (Q2 = neutral) has
  direction 0 on ALL THREE axes — pleasure 0 by valence, and arousal 0 /
  dominance 0 because they carry no direction without valenced meaning (see "PAD
  Delta as a Byproduct"). The constructed delta is therefore fully zero with
  `valence = NEUTRAL`, and `_apply_delta` skips it: `apply_appraisal_delta` is
  not called, so `_last_applied_valence` is never set to NEUTRAL and PAD_Engine's
  deliberately-unresolved NEUTRAL `on_soul_tick` branch (Module 1 raises there)
  is never entered via this module. This resolves OQ-F on the Appraisal Chain's
  side — a neutral appraisal is "no PAD event" — without inventing a neutral
  coefficient or mislabelling the valence. Not an exception path; it is the
  ordinary construction for neutral meaning.
- **Unknown/invalid `need_states` keys**: ignored for retrieval (only
  recognized need keys map to `need_prefs`); no crash, no invented need.

## Testing Strategy

Plain pytest, no `hypothesis` (matching Modules 1 & 3). "Property" checks use
representative hand-picked inputs. Fakes: a deterministic `FakeEmbedding`
(mirroring `tests/test_graph_manager.py`) and a real in-memory `MemoryGraph`
(`":memory:"`) plus a real `PADEngine` initialized to baseline — so the chain is
tested against the REAL pad_engine/graph_manager interfaces, not mocks of them.

Tests map to acceptance criteria:

1. **Stage 0** — contentless input creates an INPUT_UNCERTAIN node and produces
   a secondary-appraisal delta; a normal sentence proceeds (Req 1).
2. **Stage 1 retrieval** — `retrieve` is called with the mood-congruent
   pleasure sign, the derived `need_prefs`, entity_refs, and a query embedding;
   retrieved context is available to Stage 2 (Req 2).
3. **Social-signal pre-pass** — DISTRESS_MARKER fires on absolutist/negative
   text and not on neutral text; VULNERABILITY_DISCLOSURE fires when the fake
   embedding is close to an exemplar; REALITY_CONTRADICTION delegates to
   `graph.reality_contradiction_check`; the pre-pass writes nothing to PAD
   (PAD unchanged after a pre-pass-only path) and nothing to the graph except a
   `"resolved"` edge on arc closure (Req 3).
4. **Q1–Q4 categorical** — the four outcomes are enum members from the exact
   domains; ambiguous cues yield VALENCE_UNCERTAIN / CAUSAL_UNCERTAIN rather
   than a forced pick; no method computes a numeric appraisal score (Req 4).
5. **Emergency gate** — a high-relevance physical-threat turn with absent coping
   fires emergency Type A; an existential turn fires Type B; `coping_potential
   ≤ 0.04` forces Type B even with a physical cue; a non-severe high turn does
   NOT fire; coping_potential is not present on a non-emergency turn's result;
   Q1 ≠ high never computes it (Req 5). Assertions are on the categorical
   outcome/type, never on a coping band value.
6. **Stage 3 synthesis** — full appraisal (0 unclear) sets
   `is_partial_appraisal = False`; 1 unclear creates the matching uncertainty
   node and sets partial; 3 unclear fires a secondary appraisal; a conflicting
   graph context creates GRAPH_CONFLICT (Req 6).
7. **Uncertainty** — creation goes through `graph.create_uncertainty_node`
   (verified by active count / node lookup); a supplied `active_uncertainty_ref`
   resolves RESOLVED_CONFIRMED with a catch-up delta applied via PAD_Engine
   (Req 7). OQ-A increment is asserted absent (documented gap), not faked.
8. **PAD byproduct** — after `appraise`, PAD moved by exactly the constructed
   delta (compare `get_current_pad()` before/after minus the delta = 0);
   direction signs match Q2/Q3 (positive → pleasure up, negative → pleasure
   down, obstructive/uncertain → dominance down, arousal up when relevant);
   negative and positive deltas of the same Q1 tier have equal magnitude
   (no negativity inflation — Req 8.3); a partial appraisal uses a strictly
   smaller magnitude tier than the equivalent full appraisal (damping — Req
   8.4). Magnitudes themselves are NOT pinned to `_PAD_STEP` values, only their
   ordering/sign.
9. **PAD purity** — the only PAD change across a turn equals the sum of the
   applied appraisal delta(s); the chain exposes no direct-PAD-write method
   (API-surface check); an aha_insight delta is routed through
   `apply_appraisal_delta` (Req 8.5, 14.1); and a purely-neutral appraisal
   (Q2 = neutral) emits NO PAD event — its delta is fully zero on every axis,
   PAD does not move, `_last_applied_valence` is not set to NEUTRAL, and a
   subsequent `on_soul_tick` does not raise (OQ-F resolution — asserted both
   directly on `_build_pad_delta`/`_apply_delta` and through the reachable
   `appraise()` path for a bare-neutral and a neutral-circumstance turn).
10. **Stage 5** — supplying `need_states={"connection":"neglected"}` changes
    only the `need_prefs` passed to `retrieve` and does NOT change PAD relative
    to the same turn without need pressure (Req 9).
11. **Poignancy** — Critical requires all four conjuncts incl. first-of-kind
    (verified against a seeded graph where a prior matching (Q2,Q3) event on the
    entity makes the second non-Critical); High/Medium/Low per the table;
    emergency → Critical (Req 11).
12. **Emergency as result / no LLM branch** — the result carries the flag +
    `emergency_type`; the chain has no method that emits five-field or Type
    A/B/C instruction text (API-surface check, Req 12.1); the persisted
    EventNode has `appraisal_q2 == "negative"` on an emergency turn and the
    emergency characterization appears in `appraisal_q4_notes` (Req 12.2, OQ-B);
    the emergency turn still writes an EventNode and shifts PAD (Req 12.3).
13. **Outputs** — one EventNode per turn (graph count grows by 1); the result
    object exposes the salient note + emergency fields; no raw PAD/graph value
    is embedded in `most_salient_note` (it is a qualitative string) (Req 13).
14. **Boundaries** — no PAD-writing method; no LLM handle/return; only real
    injected interfaces used; no concrete embedding model instantiated;
    `_build_pad_delta` contains no `Σ wᵢ·featureᵢ` (reviewed + asserted via the
    magnitude-ordering/sign tests) (Req 14).

**Explicitly not tested to a value (flagged placeholders):** `_PAD_STEP`
magnitudes, `_COPING_*` bands, arc turn-counts, similarity cutoffs — tests
assert their PROPERTIES (ordering, sign, categorical outcome), never the tunable
magnitude, exactly as Module 3 handled OQ1-rate/OQ2.

## Open Questions

Carried from `requirements.md` (OQ-A … OQ-E) plus one surfaced by the design:

- **OQ-A** — no public `interaction_count` increment surface on the built
  Memory_Graph (Resolution Log item 10). Responsibility recorded; not
  implemented via private writes. Flagged.
- **OQ-B** — no `emergency_type` field on the built EventNode (Resolution Log
  item 3). Emitted on the result + recorded in `appraisal_q4_notes`;
  `appraisal_q2` persisted "negative". Flagged.
- **OQ-C** — no active-uncertainty-by-entity query on the built Memory_Graph.
  `active_uncertainty_refs` accepted as input. Flagged.
- **OQ-D** — catch-up "original damped magnitude" storage not present; catch-up
  computed from the resolving turn's clear delta × the in-spec factor.
  Interpretation documented, not silently chosen.
- **OQ-E** — Stage-0 parseability criterion under-specified; conservative
  categorical heuristic used, fuller criterion flagged.
- **OQ-F — NEUTRAL PAD delta and PAD_Engine's NEUTRAL decay branch — RESOLVED
  on this module's side.** PAD_Engine deliberately leaves NEUTRAL-valence
  `on_soul_tick` decay unresolved (Module 1 raises there). *Previously* a
  relevant-but-neutral event produced a `valence = NEUTRAL` delta with a
  non-zero arousal component (and, for a circumstance/causal-uncertain
  attribution, a non-zero dominance component); applying it set
  `_last_applied_valence = NEUTRAL`, which made the NEXT `on_soul_tick` raise —
  so every neutral-but-relevant turn left PAD_Engine in a crash-on-next-tick
  state. **Resolution (Rule 1 / Rule 2 clean):** a neutral appraisal carries no
  valenced meaning, so — per "PAD shifts as byproduct of appraisal" (v4 Stage 4;
  its "rise in arousal" is described for an obstructive/uncertain event, not a
  neutral one) and "feeling changes only through valenced meaning" (steering) —
  it emits NO PAD event: arousal and dominance directions are 0 for a neutral
  Q2, the delta is fully zero on every axis, and `_apply_delta` skips it. The
  Appraisal Chain therefore never applies a NEUTRAL-valence delta and never
  enters PAD_Engine's unresolved NEUTRAL branch. This *removes* a movement (the
  conservative, non-inventive choice) rather than inventing a neutral
  coefficient or lying about the valence. The underlying Module 1 question —
  what a NEUTRAL `on_soul_tick` decay *should* do if it were ever reached — is
  untouched and remains the architect's; it is simply unreachable through this
  module. Verified by `test_neutral_appraisal_builds_a_fully_zero_delta_and_apply_skips`,
  `test_reachable_neutral_turn_emits_no_pad_event_and_next_tick_is_safe`, and
  `test_neutral_circumstance_turn_does_not_crash_next_tick`.

## Known Limitations

- **EventNode ↔ UncertaintyNode link ordering.** `write_event_node` returns the
  node id, and `create_uncertainty_node` needs a `trigger_event_ref`. The chain
  writes the EventNode first (so the uncertainty node can reference it), which
  means the EventNode's own `uncertainty_node_ref` is set at write time only
  when the uncertainty type is known before the write (it is — Stage 3 decides
  it before Stage 6). The chain therefore creates the UncertaintyNode in Stage 3
  with a deferred `trigger_event_ref` filled at Stage 6, or writes the event
  with `uncertainty_node_ref=None` and accepts the one-way (uncertainty→event)
  link. This is an implementation ordering detail, not a schema change.
- **Entity resolution is caller-provided.** The chain does not itself resolve
  which entity a turn is about; `entity_refs` are supplied by the caller
  (Daemon/perception). Deeper entity resolution is out of scope and not
  invented here.
- **Conflict-arc state is in-memory and per-process.** The state machine's
  per-entity open/absent-turn counters live in the chain instance; they are not
  persisted (the arc *closure* effect — the `"resolved"` edge — IS persisted in
  the graph). A restart resets the counters; this matches the graph being the
  only persistent store and is acceptable per the spec (the durable artifact is
  the resolved edge).
- **coping_potential and the emergency bands are substrate placeholders.** The
  gate DECISION is categorical and tested; the band magnitudes are tuned at
  runtime and are not asserted.
