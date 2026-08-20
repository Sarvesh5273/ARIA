# Requirements Document — Module 4: Appraisal Chain

## Introduction

This document transcribes and formalizes, in EARS format, the Module 4
(Appraisal Chain) entry from `ARIA_Module_Build_Plan.md`, applying every
locked decision in `ARIA_Resolution_Log.md` and `ARIA_Soul_Spec_v4_Addendum.md`
that bears on it. That entry is the locked, approved scope for this module. No
requirement here introduces a mechanism, threshold, or behavior that is not
already stated in the Module 4 entry or in the supporting architecture
documents (`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`). Where the Module 4 entry references a value or
mechanism defined elsewhere (the Stage 0–6 chain, the emergency thresholds,
the poignancy table, the social-signal pre-pass), the supporting document is
cited as the source of that value, not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` provides covering context only.

**The inviolable constraint this module lives under (steering/project-rules.md,
"The protected chain"):** the meaning Aria assigns and the feeling that follows
change ONLY through appraisal (categorical meaning) → PAD (feeling). The
Appraisal Chain is the *meaning* step of that chain. It produces categorical
Q1–Q4 appraisals by categorical logic — never by a scoring formula or weighted
feature sum — and a PAD delta that is a *byproduct* of that categorical
appraisal, routed through PAD_Engine. Nothing in this module computes
"feeling = number × weight". The percentage test governs every ambiguous
choice: if "what percent of the way there is this?" is meaningful, it is a
number in disguise and is wrong; if "it either holds or it doesn't", it is a
real category and is implemented as one.

Genuinely undefined items discovered while formalizing the entry — and the
Module 4 flags F-4a/F-4b/F-4d/F-4e/F-4f — are recorded in the **Open
Questions** and **Build-Time Tuning Constants** sections, resolved by the
Resolution Log / Addendum where those documents resolve them, and left as
flagged placeholders where they do not. Nothing is resolved by invention
(Rule 1); no document conflict is silently picked (Rule 2).

## Glossary

- **Appraisal_Chain**: The module specified here (Module 4). Runs the per-turn
  meaning-making pass over user input through Stages 0–6 and emits a PAD delta,
  a graph EventNode write, uncertainty-node lifecycle signals, a most-salient
  appraisal result, and an emergency flag + type.
- **Stage 0 — Input Classification**: Categorical yes/no — can the input be
  parsed as an appraisable event? (`ARIA_Soul_Spec_v4.md`, Layer 1, the
  6-stage chain.) NO → an INPUT_UNCERTAIN node is created and a secondary
  appraisal fires. YES → proceed.
- **Stage 1 — Context Load**: Retrieval of the top 3–5 mood-congruent,
  need-preferenced graph items for this turn (via Memory_Graph), plus the
  non-generative Social_Signal_Pre_Pass. (`ARIA_Soul_Spec_v4.md` Layer 1;
  Addendum §1, §3.)
- **Social_Signal_Pre_Pass**: A non-generative classification step inside
  Stage 1, running before Q1–Q4 (Addendum §1). No cloud LLM, no local Gemma.
  Emits categorical tags only — DISTRESS_MARKER, VULNERABILITY_DISCLOSURE,
  REALITY_CONTRADICTION — and drives the conflict-arc state machine. Feeds
  Q3/Q4 as context; writes nothing to PAD or the graph directly.
- **DISTRESS_MARKER**: A categorical tag set by pure lexical analysis —
  negative-emotion words, absolutist language ("always/never/completely"),
  first-person-singular density (Addendum §1; Al-Mosaiwi & Johnstone 2018). A
  word count is *perception*, not appraisal.
- **VULNERABILITY_DISCLOSURE**: A categorical tag set by embedding similarity
  of the input to a small curated set of self-disclosure exemplars, using the
  injected Embedding_Model (Addendum §1). The similarity cutoff is a build-time
  tuning constant (F-4e).
- **REALITY_CONTRADICTION**: A categorical tag set by comparing the factual
  content of the input against same-entity EventNode descriptions in a short
  window, via `Memory_Graph.reality_contradiction_check` (Addendum §1). The
  comparison window and contradiction criterion are build-time tuning constants
  (F-4e).
- **Conflict_Arc_State_Machine**: A state machine (no classifier) reading the
  per-turn appraisal output already produced. Opens when consecutive EventNodes
  share an entity_ref with Q2 = negative; closes when a later EventNode on that
  entity_ref flips to Q2 = positive/neutral, or enough turns pass without that
  entity recurring (Addendum §1). Open/close turn-counts are build-time tuning
  constants (F-4d).
- **Q1 (Goal_Relevance)**: Categorical appraisal outcome ∈ {none, low, medium,
  high}. Cannot return UNCLEAR — goal relevance is the threshold question
  (`ARIA_Soul_Spec_v4.md`, Layer 1).
- **Q2 (Valence)**: Categorical appraisal outcome ∈ {positive, negative,
  neutral, VALENCE_UNCERTAIN}. Reuses PAD_Engine's `Valence` enum as the
  in-code type (`daemon/pad_engine.py`), translated to Memory_Graph's
  `appraisal_q2` string domain at the write boundary. Stays 4-valued
  (Resolution Log item 3).
- **Q3 (Causal_Attribution)**: Categorical appraisal outcome ∈ {self, user,
  circumstance, CAUSAL_UNCERTAIN} (`ARIA_Soul_Spec_v4.md`, Layer 1; matches
  Memory_Graph's `appraisal_q3` string domain).
- **Q4 (Needs_Implications)**: Qualitative notes resolved from Q1–Q3, inheriting
  uncertainty from Q2/Q3. Persisted as `appraisal_q4_notes` (str/null).
  Normal-turn Q4 stays purely qualitative (Resolution Log item 12). A
  categorical `has_needs_implications` flag derived from Q4 feeds the poignancy
  decision (see Poignancy).
- **coping_potential**: A transient substrate value, the ONLY sanctioned new
  number in this module, computed ONLY during the Stage-2 emergency-gate check
  and discarded if the gate does not fire (Resolution Log item 12). Compared to
  the already-in-spec thresholds ≤ 0.15 and ≤ 0.04
  (`ARIA_Soul_Spec_v4.md`, Emergency Gate). Never persisted, never fed to PAD.
- **Emergency (as appraisal result)**: Not a separate detection subsystem — an
  appraisal result (`ARIA_Soul_Spec_v4.md`, Emergency Detection). The gate is
  Q1 = high AND Q2 sub-type = SEVERELY_OBSTRUCTIVE AND coping_potential ≤ 0.15.
- **emergency_type**: One of PHYSICAL_THREAT (Type A) / EXISTENTIAL_DISTRESS
  (Type B) / DECISION_CRITICAL (Type C) / UNCLASSIFIED (→ Type B) / null,
  populated only on turns where the gate fires (Resolution Log item 3;
  `ARIA_Soul_Spec_v4.md` Emergency Type Detection). null otherwise.
- **PAD_Delta**: The `PADDelta` type owned by PAD_Engine
  (`daemon/pad_engine.py`) — `(d_pleasure, d_arousal, d_dominance, valence,
  origin)`. The Appraisal Chain constructs it as the byproduct of the
  categorical appraisal and applies it via `PAD_Engine.apply_appraisal_delta`.
  This module does not define its own PAD delta type.
- **Poignancy_Category**: The `PoignancyCategory` enum owned by Memory_Graph
  (`daemon/graph_manager.py`) — critical/high/medium/low. Decided categorically
  by the Appraisal Chain (`ARIA_Soul_Spec_v4.md` Poignancy table, as widened by
  Addendum §6), passed to `write_event_node`.
- **PAD_Engine**: Module 1 (`daemon/pad_engine.py`, built/approved). The sole
  owner/mutator of PAD; the Appraisal Chain's only PAD-writing path is
  `PAD_Engine.apply_appraisal_delta(PADDelta(...))`.
- **Memory_Graph**: Module 3 (`daemon/graph_manager.py`, built/approved). The
  only persistent memory store. The Appraisal Chain calls its real interface:
  `write_event_node`, `create_uncertainty_node`, `update_uncertainty_status`,
  `retrieve`, `is_first_of_kind`, `reality_contradiction_check`,
  `resolved_edge_exists`, `write_edge`, `get_entity_node`.
- **Embedding_Model**: The shared local sentence-embedding model (encoder-only,
  non-generative), injected as the `EmbeddingModel` Protocol defined in
  `daemon/graph_manager.py` (Addendum §1 "one model serves both"). Not
  instantiated inside this module, not hardcoded to a model name.
- **Needs_System**: Module 2 (not yet built). Supplies categorical need states
  (satisfied/due/neglected). The Appraisal Chain accepts them as an input and
  uses them only as a Stage-1 retrieval preference (Addendum §3).
- **Soul_Filter**: Module 5. Consumes the most-salient appraisal result (This
  Moment) and the emergency flag + type. The Appraisal Chain does NOT itself
  branch the LLM instruction format — Soul_Filter does (Resolution Log item 1).
- **DMN**: Module 6. Shares UncertaintyNode resolution and owns the aha-insight
  second-order appraisal (which arrives back as a PAD delta via this chain).
- **Active_Inference**: A descriptive framing over the Stage 0–6 chain, NOT a
  separate subsystem and NOT a free-energy engine (Resolution Log item 10;
  F-4b).

## Requirements

### Requirement 1: Stage 0 — Input Classification

**User Story:** As the Appraisal Chain, I want to first decide whether the
input is an appraisable event, so that contentless or unparseable input creates
an uncertainty state instead of a fabricated appraisal.

#### Acceptance Criteria

1. WHEN a user turn arrives, THE Appraisal_Chain SHALL categorically classify
   whether the input can be parsed as an appraisable event (a yes/no decision,
   not a score).
2. IF the input cannot be parsed as an appraisable event, THEN THE
   Appraisal_Chain SHALL create an INPUT_UNCERTAIN UncertaintyNode via
   `Memory_Graph.create_uncertainty_node` and run a secondary appraisal on the
   unresolved state (Requirement 7), rather than emit a positive/negative/
   neutral primary appraisal.
3. IF the input can be parsed as an appraisable event, THEN THE Appraisal_Chain
   SHALL proceed to Stage 1.

### Requirement 2: Stage 1 — Context Load (Graph Retrieval)

**User Story:** As the Appraisal Chain, I want the turn appraised against
mood-congruent, need-preferenced memory, so that meaning is graph-aware rather
than computed from the input alone.

#### Acceptance Criteria

1. WHEN Stage 1 runs, THE Appraisal_Chain SHALL retrieve the top 3–5 relevant
   graph items via `Memory_Graph.retrieve`, passing the current PAD pleasure
   sign (mood-congruence), the need-preference set (Requirement 9), the turn's
   entity references, and the query embedding (from the injected
   Embedding_Model).
2. THE Appraisal_Chain SHALL obtain the current PAD from `PAD_Engine.
   get_current_pad` for the mood-congruent sign, and SHALL NOT read or mutate
   PAD by any other path.
3. THE Appraisal_Chain SHALL treat retrieved context as *input to* Q1–Q4
   (informing the appraisal), never as a direct write to PAD (v4 Layer 1: "The
   graph does not write to PAD directly. It informs the appraisal at Stage 1").

### Requirement 3: Stage 1 — Social-Signal Pre-Pass (Non-Generative)

**User Story:** As the Appraisal Chain, I want a non-generative pre-pass that
tags distress, vulnerability, and reality-contradiction, so that Q3/Q4 have
research-grounded perception signals without any LLM deciding meaning.

#### Acceptance Criteria

1. THE Social_Signal_Pre_Pass SHALL run inside Stage 1, before Q1–Q4, and SHALL
   NOT call any cloud LLM or local Gemma (Addendum §1).
2. THE Social_Signal_Pre_Pass SHALL emit DISTRESS_MARKER by pure lexical
   analysis (negative-emotion words, absolutist language, first-person-singular
   density) — a word count, which is perception, not appraisal (Addendum §1).
3. THE Social_Signal_Pre_Pass SHALL emit VULNERABILITY_DISCLOSURE by embedding
   similarity of the input to curated self-disclosure exemplars via the injected
   Embedding_Model, using a build-time similarity cutoff (F-4e).
4. THE Social_Signal_Pre_Pass SHALL emit REALITY_CONTRADICTION via
   `Memory_Graph.reality_contradiction_check` over same-entity EventNode
   descriptions in a short window (Addendum §1; F-4e).
5. THE Conflict_Arc_State_Machine SHALL open when consecutive EventNodes share
   an entity_ref with Q2 = negative, and close when a later EventNode on that
   entity_ref flips to Q2 = positive/neutral or enough turns pass without that
   entity recurring (Addendum §1); the open/close turn-counts are build-time
   tuning constants (F-4d).
6. THE Social_Signal_Pre_Pass SHALL write nothing to PAD and nothing to the
   graph directly — its tags are consumed by Q3/Q4 only (Addendum §1).
7. WHEN the Conflict_Arc_State_Machine reports arc closure, THE Appraisal_Chain
   SHALL write a single `"resolved"` edge (closing→opening EventNode) via
   `Memory_Graph.write_edge` (Resolution Log item 5), and SHALL NOT create a
   new node type for the arc.

### Requirement 4: Stage 2 — EMA Appraisal (Categorical Q1–Q4)

**User Story:** As the Appraisal Chain, I want Q1–Q4 decided by categorical
logic over perception signals and graph context, so that meaning is a real
category and never a weighted feature sum.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL produce Q1 ∈ {none, low, medium, high}; Q1 SHALL
   NOT return UNCLEAR (v4 Layer 1).
2. THE Appraisal_Chain SHALL produce Q2 ∈ {positive, negative, neutral,
   VALENCE_UNCERTAIN}; Q2 SHALL be allowed to return VALENCE_UNCERTAIN when
   valence cannot be determined (v4 Layer 1).
3. THE Appraisal_Chain SHALL produce Q3 ∈ {self, user, circumstance,
   CAUSAL_UNCERTAIN}; Q3 SHALL be allowed to return CAUSAL_UNCERTAIN when
   attribution cannot be determined (v4 Layer 1).
4. THE Appraisal_Chain SHALL resolve Q4 (needs implications) qualitatively from
   Q1–Q3, inheriting uncertainty from Q2/Q3, and SHALL keep normal-turn Q4
   purely qualitative (Resolution Log item 12).
5. THE Appraisal_Chain SHALL decide Q1–Q4 by categorical logic over the
   Social_Signal_Pre_Pass tags, retrieved graph context, and current PAD sign,
   and SHALL NOT decide any of Q1–Q4 by a scoring formula, weighted feature sum,
   or continuous threshold not already in the spec (steering/project-rules.md;
   v4 Poignancy section "invented weights … replace meaning with arithmetic").

### Requirement 5: Stage 2 — Emergency Gate (Appraisal Result)

**User Story:** As the Appraisal Chain, I want emergency detected as an
appraisal result on the user's input, so that a catastrophic prediction error
can be flagged to Soul_Filter without a separate detection system.

#### Acceptance Criteria

1. WHEN Q1 = high, THE Appraisal_Chain SHALL evaluate whether Q2 is the
   SEVERELY_OBSTRUCTIVE sub-type and SHALL compute coping_potential; when Q1 ≠
   high, THE Appraisal_Chain SHALL NOT compute coping_potential (Resolution Log
   item 12).
2. THE Appraisal_Chain SHALL set the emergency flag true IF AND ONLY IF Q1 =
   high AND Q2 sub-type = SEVERELY_OBSTRUCTIVE AND coping_potential ≤ 0.15
   (v4 Emergency Gate).
3. WHEN the emergency flag is true, THE Appraisal_Chain SHALL characterize
   emergency_type as PHYSICAL_THREAT (Type A) / EXISTENTIAL_DISTRESS (Type B) /
   DECISION_CRITICAL (Type C) / UNCLASSIFIED, and SHALL default UNCLASSIFIED to
   Type B (v4 Emergency Type Detection).
4. WHEN coping_potential ≤ 0.04, THE Appraisal_Chain SHALL force emergency_type
   to EXISTENTIAL_DISTRESS (Type B) regardless of the Q2 sub-type (v4 Emergency
   Gate special case).
5. THE Appraisal_Chain SHALL treat coping_potential as transient: computed only
   inside this gate check and discarded if the gate does not fire; it SHALL NOT
   be persisted and SHALL NOT be fed into any PAD delta (Resolution Log item 12).

### Requirement 6: Stage 3 — Appraisal Output Synthesis

**User Story:** As the Appraisal Chain, I want the number of UNCLEAR dimensions
to determine whether the appraisal is full, partial, or a secondary appraisal,
so that uncertainty is represented honestly rather than smoothed over.

#### Acceptance Criteria

1. WHEN all of Q2, Q3, Q4 are clear, THE Appraisal_Chain SHALL produce a full
   appraisal vector and SHALL check whether an active uncertainty node on this
   entity can now resolve (Requirement 7).
2. WHEN 1–2 of {Q2, Q3, Q4} are UNCLEAR, THE Appraisal_Chain SHALL produce a
   partial appraisal (missing dimensions null, not zero), set
   `is_partial_appraisal = true`, and create the matching UncertaintyNode(s):
   VALENCE_UNCERTAIN for an unclear Q2, CAUSAL_UNCERTAIN for an unclear Q3
   (v4 Layer 1).
3. WHEN 3 of {Q2, Q3, Q4} are UNCLEAR, THE Appraisal_Chain SHALL fire a
   secondary appraisal on the unresolved state itself (Requirement 7), rather
   than emit a primary vector.
4. WHEN retrieved graph context for this entity carries contradictory appraisal
   vectors, THE Appraisal_Chain SHALL create a GRAPH_CONFLICT UncertaintyNode
   (v4 Layer 1 uncertainty types).

### Requirement 7: Uncertainty as a First-Class Internal State

**User Story:** As the Appraisal Chain, I want unresolved appraisal to become a
second-order appraisal event, so that PAD moves as a byproduct of meaning-making
and never as a direct injection.

#### Acceptance Criteria

1. WHEN a secondary appraisal fires (Stage 0 INPUT_UNCERTAIN, or Stage 3 with
   3 UNCLEAR), THE Appraisal_Chain SHALL run the unresolved state through the
   four questions (matters=yes → Q1 high; obstructive → Q2 negative; ambiguous
   → Q3 circumstance; partial coping → Q4), producing a PAD delta as a byproduct
   (v4 "The Secondary Appraisal Mechanism").
2. THE Appraisal_Chain SHALL create UncertaintyNodes only via
   `Memory_Graph.create_uncertainty_node`, delegating the max-5 active-node cap
   and force-abandon-oldest-GRAPH_CONFLICT enforcement to Memory_Graph (which
   owns it) rather than enforcing it here.
3. WHEN the user or context provides the missing piece for an active uncertainty
   this turn, THE Appraisal_Chain SHALL resolve it RESOLVED_CONFIRMED via
   `Memory_Graph.update_uncertainty_status` and apply the catch-up PAD shift as
   a secondary appraisal through `PAD_Engine.apply_appraisal_delta`, using the
   in-spec 0.50 (confirmed) / 0.25 (inferred) magnitude factors (v4 Resolution
   Conditions table).
4. THE Appraisal_Chain SHALL be the module responsible for incrementing an
   active uncertainty node's `interaction_count` per user turn (Resolution Log
   item 10), reading it back via DMN — subject to Open Question OQ-A (the built
   Memory_Graph exposes no public increment surface).

### Requirement 8: Stage 4 — PAD Shift as a Byproduct of Appraisal

**User Story:** As the Aria system architect, I want the only PAD movement from
a turn to be the appraisal-derived delta routed through PAD_Engine, so that no
emotion-formula and no direct PAD write can ever exist in this module.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL construct the PAD delta as a byproduct of the
   categorical appraisal outcome (Q1–Q3): the per-axis *direction* is decided
   categorically (Requirement 4), and the magnitude is a single categorical
   intensity tier selected by Q1 — never a weighted sum of features (v4 Layer 1
   "PAD shifts as byproduct of appraisal — never as direct assignment").
2. THE Appraisal_Chain SHALL apply the PAD delta only via
   `PAD_Engine.apply_appraisal_delta(PADDelta(...))`, setting `PADDelta.valence`
   from Q2, and SHALL NOT write PAD by any other path.
3. THE Appraisal_Chain SHALL NOT inflate the PAD delta magnitude for negative
   valence; negativity bias is realized by PAD_Engine's asymmetric decay
   (driven by the valence passed) and by Memory_Graph's +0.15 negative
   base_salience bonus (driven by Q2 = negative) — not by this module (v4
   Negativity Bias; Resolution Log — no double-counting).
4. WHEN the appraisal is partial (uncertainty present), THE Appraisal_Chain
   SHALL reduce the delta intensity categorically (a lower intensity tier),
   reflecting v4's "primary appraisal intensity naturally reduced … when
   uncertainty is present", WITHOUT computing coping_potential on a normal turn
   (Resolution Log item 12).
5. THE Appraisal_Chain SHALL accept an aha-insight second-order appraisal
   (originating in DMN) and route its PAD shift through
   `PAD_Engine.apply_appraisal_delta` like any other delta (Build Plan Module 1
   inputs), never directly to PAD.

### Requirement 9: Stage 5 — Needs Pressure as a Retrieval Preference Only

**User Story:** As the Aria system architect, I want Stage 5 to shape *what is
retrieved*, never to pull on PAD, so that needs cannot become a back-door
emotion formula.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL treat need states (due/neglected) as a Stage-1
   retrieval preference only, surfacing need-relevant context first via
   `Memory_Graph.retrieve`'s `need_prefs` (Addendum §3).
2. THE Appraisal_Chain SHALL NOT add any needs-derived pull, coefficient, or
   pressure onto PAD or onto the Q1–Q4 outputs (Addendum §3 "It is a context
   shaper via Stage 1 retrieval preference, not a formula acting on appraisal
   output").

### Requirement 10: Stage 6 — Graph Write

**User Story:** As the Appraisal Chain, I want each appraised turn written as an
EventNode with its appraisal vector and poignancy, so that memory is the record
of meaning.

#### Acceptance Criteria

1. WHEN Stage 6 runs, THE Appraisal_Chain SHALL write one EventNode via
   `Memory_Graph.write_event_node`, passing appraisal_q1/q2/q3 (as the graph's
   string domain), appraisal_q4_notes, poignancy_category, the PAD delta
   components, `is_partial_appraisal`, `uncertainty_node_ref` (when one was
   created), entity_refs, and perspective.
2. THE Appraisal_Chain SHALL write exactly one live EventNode per appraised
   turn and SHALL NOT write DMN Step-1 buffer nodes — live Stage-6 writes and
   DMN buffer writes are different node populations with no overlap (Resolution
   Log item 10; F-4f).
3. THE Appraisal_Chain SHALL NOT map PAD to a video zone or prosody, and SHALL
   NOT synthesize the Soul_Filter behavioral instruction — those Stage-6
   outputs are owned by Visual_Layer, Audio_Pipeline, and Soul_Filter
   respectively (Build Plan). This module emits the *appraisal result* those
   modules consume.

### Requirement 11: Poignancy — Categorical System

**User Story:** As the Appraisal Chain, I want poignancy derived categorically
from Q1–Q4 (no separate weighted computation), so that the graph acts on the
meaning the chain already produced.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL assign Poignancy_Category categorically:
   Critical, High, Medium, or Low — never by a weighted formula (v4 Poignancy).
2. THE Appraisal_Chain SHALL assign Critical WHEN Q1 = high AND Q2 ≠ neutral AND
   Q4 has explicit needs implications AND (novel entity involvement OR
   event-type is first-of-kind for this entity), determining first-of-kind via
   `Memory_Graph.is_first_of_kind(entity_ref, appraisal_q2, appraisal_q3)`
   called before the EventNode write (Addendum §6).
3. THE Appraisal_Chain SHALL assign High WHEN Q1 = high OR (Q1 = medium AND Q4
   has needs implications); Medium WHEN Q1 = medium AND Q4 is null/partial; Low
   WHEN Q1 ∈ {none, low} (v4 Poignancy table).
4. WHEN the emergency flag is true, THE Appraisal_Chain SHALL assign Critical
   (guaranteed by Q1 max + Q2 ≠ neutral + Q4 needs implications) (v4
   Post-Emergency Behavior item 2).

### Requirement 12: Emergency as an Appraisal Result Output

**User Story:** As Soul_Filter, I want the emergency flag and type from the
appraisal, so that I — not the Appraisal Chain — branch the LLM instruction
format.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL output the emergency flag and emergency_type to
   Soul_Filter, and SHALL NOT itself assemble or branch the five-field vs.
   Type A/B/C instruction format (Resolution Log item 1 — that branch is
   Soul_Filter's).
2. WHEN the emergency gate fires, THE Appraisal_Chain SHALL persist the turn's
   EventNode with appraisal_q2 = "negative" (not a new sub-type value) and
   SHALL record the emergency characterization in appraisal_q4_notes, per
   Resolution Log item 3 — subject to Open Question OQ-B (the built EventNode
   schema has no dedicated `emergency_type` field).
3. THE Appraisal_Chain SHALL run the emergency event through the normal
   appraisal chain (PAD shift + graph write) — emergency does not bypass memory
   (v4 Post-Emergency Behavior item 1).

### Requirement 13: Outputs to Consumers

**User Story:** As the Aria system, I want the Appraisal Chain to emit exactly
the outputs the architecture defines, so that each downstream module receives
what it needs and nothing more.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL output the PAD delta to PAD_Engine (Requirement 8).
2. THE Appraisal_Chain SHALL output the EventNode + poignancy category to
   Memory_Graph (Requirement 10).
3. THE Appraisal_Chain SHALL output UncertaintyNode create/resolve signals to
   Memory_Graph / DMN (Requirement 7).
4. THE Appraisal_Chain SHALL output the most-salient appraisal result to
   Soul_Filter (This Moment) as a categorical/qualitative result — never raw
   PAD numbers, graph node contents, or Q1–Q4 raw values crossing to the LLM
   (steering/project-rules.md, Five-field LLM boundary; that translation is
   Soul_Filter's job — this module hands Soul_Filter the salient meaning).
5. THE Appraisal_Chain SHALL output the emergency flag + Q2 sub-type to
   Soul_Filter (Requirement 12).

### Requirement 14: Boundaries — PAD Purity, No Invented Numbers, Framing Only

**User Story:** As the Aria system architect, I want it structurally clear that
this module never becomes a machine that computes feeling, so that the
anti-machine philosophy holds in code, not just intent.

#### Acceptance Criteria

1. THE Appraisal_Chain SHALL change PAD only through the appraisal-derived
   PAD_Delta routed via `PAD_Engine.apply_appraisal_delta` (Requirement 8);
   it SHALL expose no method that writes PAD directly (steering PAD-purity).
2. THE Appraisal_Chain SHALL introduce no continuous score, percentage, or
   threshold other than coping_potential (Requirement 5) and the PAD delta
   substrate magnitudes (Build-Time Tuning Constants) — and SHALL treat those
   substrate magnitudes as flagged placeholders, not derived values
   (steering "No invented numbers").
3. THE Appraisal_Chain SHALL NOT implement Active Inference as a separate
   subsystem or a free-energy engine; Active Inference is a descriptive framing
   over Stages 0–6 (Resolution Log item 10; F-4b).
4. THE Appraisal_Chain SHALL depend on PAD_Engine, Memory_Graph, and the
   Embedding_Model by injection, SHALL call only their real public interfaces,
   SHALL NOT redefine their types, and SHALL NOT instantiate or hardcode a
   concrete embedding model (Addendum §1; Rule 6).

## Open Questions

Items genuinely undefined across the source documents, or cross-module
interface gaps discovered while formalizing this entry. Per Rule 1 and Rule 2,
they are flagged here rather than resolved by invention. None blocks building
and testing the specified paths; each is called out where it affects a
requirement's testability.

- **OQ-A — `interaction_count` increment surface (Resolution Log item 10 vs.
  built Memory_Graph).** Resolution Log item 10 assigns the Appraisal Chain the
  responsibility of incrementing an active uncertainty node's
  `interaction_count` each user turn. The built `daemon/graph_manager.py`
  exposes `create_uncertainty_node` (sets the initial count) and
  `update_uncertainty_status` (does not touch the count) but **no public
  method to increment `interaction_count` on an existing active node**.
  Reaching into the private `_conn` would violate "call their real interfaces".
  **Flagged, not resolved:** the responsibility is recorded (Requirement 7.4);
  the chain will call such a method (e.g. a future
  `Memory_Graph.increment_uncertainty_interaction_count`) when Module 3 adds
  it. This module does not invent that surface or a private-write workaround.
- **OQ-B — EventNode `emergency_type` field (Resolution Log item 3 vs. built
  Memory_Graph).** Resolution Log item 3 says to add a nullable
  `emergency_type` field to EventNode. The built EventNode schema in
  `daemon/graph_manager.py` does **not** include it, and `write_event_node`
  does not accept it. Redefining Memory_Graph's type is out of scope ("Do NOT
  redefine their types"). **Flagged, not resolved:** the emergency_type is
  emitted on the AppraisalResult to Soul_Filter (Requirement 12.1), and the
  emergency characterization is recorded qualitatively in `appraisal_q4_notes`
  so it is not lost (Requirement 12.2), with `appraisal_q2` persisted as
  "negative" per item 3. First-class persistence awaits a Module 3 schema
  addition owned by the architect.
- **OQ-C — Active-uncertainty-by-entity retrieval.** v4 Stage 3 says "check if
  any active uncertainty nodes on this entity can now resolve," but the built
  Memory_Graph exposes no public "list active uncertainty nodes for entity"
  query (`retrieve` returns Event/Edge items; `get_uncertainty_node` needs an
  id). **Flagged:** the chain accepts the relevant active uncertainty node
  id(s) as an input (`active_uncertainty_refs`, held cross-turn by the Daemon)
  so live RESOLVED_CONFIRMED resolution (Requirement 7.3) is exercised when
  refs are provided, without reaching into Memory_Graph internals.
- **OQ-D — Catch-up "original damped magnitude" storage.** v4 says a
  RESOLVED_CONFIRMED catch-up fires at "50% of original damped magnitude", but
  the built graph does not store the original secondary-appraisal delta on the
  UncertaintyNode at creation time (the `catch_up_*` fields are written only at
  resolution). **Flagged interpretation:** this module computes the catch-up as
  the in-spec factor (0.50 / 0.25) times the *resolving turn's* freshly-clear
  appraisal delta, and stores it via `update_uncertainty_status`. The factors
  are in-spec; the "of what" realization is documented as an interpretation,
  not silently chosen (Rule 2).
- **OQ-E — "Parseable as an appraisable event" criterion (Stage 0).** v4 gives
  the intent ("Things are complicated right now." → no specific event) but no
  closed criterion, and it must be non-generative (no LLM). **Flagged:** the
  module uses a conservative categorical heuristic (empty/whitespace/contentless
  input, or input the pre-pass finds carries no appraisable referent) and marks
  the fuller criterion as a build-time/architect item. It is not resolved by
  invention.

## Build-Time Tuning Constants

Values intentionally left as flagged placeholders (`TODO(build-time)`), to be
set during implementation/tuning, exactly as Module 1 carried
`PAD_HISTORY_LENGTH` and Module 3 carried the medium/low `base_salience`
placeholders. Each is SUBSTRATE or PERCEPTION plumbing, never a computed
feeling.

- **F-4d — Conflict-arc open/close turn-counts.** How many consecutive negative
  EventNodes open an arc, and how many entity-absent turns close it (Addendum
  §1; Resolution Log "Open — build-time tuning constants"). Placeholder
  constants, clearly marked.
- **F-4e — Social-signal thresholds/windows.** VULNERABILITY_DISCLOSURE
  embedding-similarity cutoff; REALITY_CONTRADICTION comparison-window duration
  and contradiction criterion; DISTRESS_MARKER word-count threshold and the
  lexicons (negative-emotion / absolutist words) (Addendum §1; Resolution Log
  "Open — build-time tuning constants"). Placeholder constants/lexicons.
- **PAD delta magnitude step-sizes (substrate).** The per-Q1-tier magnitude of
  the appraisal-derived PAD delta (none < low < medium < high). No source
  document states these; PAD is sanctioned substrate and *some* magnitude is
  required to call `apply_appraisal_delta`, so they are placeholders — ordered
  and non-negative — asserted only for their ordering, never their exact value
  (mirrors Module 3's OQ2 base_salience placeholders). NOT weights on features.
- **coping_potential band values (F-4a substrate).** The transient
  coping_potential (Requirement 5) is compared to the in-spec thresholds ≤ 0.15
  / ≤ 0.04. The categorical coping assessment (problem-focused × emotion-focused
  ∈ available/limited/absent) maps to band values whose exact magnitudes are
  placeholders; tests assert only the categorical emergency outcome, never the
  exact band value.
- **Emergency sub-type cue lexicons.** The physical-threat / existential-
  distress / decision-critical cue sets used to characterize emergency_type
  (v4 Emergency Type Detection). Placeholder lexicons; UNCLASSIFIED → Type B is
  the spec-locked default and is NOT a placeholder.

## Flag Disposition Summary (Module 4 flags F-4a/F-4b/F-4d/F-4e/F-4f)

- **F-4a (coping_potential representation) — RESOLVED by Resolution Log item
  12:** transient, computed only at the Stage-2 emergency gate, discarded
  otherwise; normal-turn Q4 stays qualitative. The exact numeric derivation
  (band values) is a flagged build-time substrate placeholder.
- **F-4b (Active Inference) — RESOLVED by Resolution Log item 10:** descriptive
  framing over Stages 0–6, no separate subsystem, no free-energy engine.
- **F-4d (conflict-arc parameters) — FLAGGED build-time tuning constant**
  (Resolution Log "Open — build-time tuning constants").
- **F-4e (social-signal thresholds/windows) — FLAGGED build-time tuning
  constant** (Resolution Log "Open — build-time tuning constants").
- **F-4f (live vs. buffer writes) — RESOLVED by Resolution Log item 10:**
  different node populations, no overlap, no double-write; this module writes
  only live Stage-6 EventNodes.
