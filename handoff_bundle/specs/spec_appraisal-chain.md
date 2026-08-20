# ARIA locked spec — appraisal-chain

Consolidated from .kiro/specs/appraisal-chain/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## appraisal-chain — requirements.md

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


---

## appraisal-chain — design.md

# Design Document — Module 4: Appraisal Chain

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
_ARC_CLOSE_ABSENT_TURNS        = 3   # TODO(build-time, F-4d)

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


---

## appraisal-chain — tasks.md

# Implementation Plan — Module 4: Appraisal Chain

This plan implements `design.md` exactly as written. Each task is small and
independently testable. It targets `daemon/appraisal_chain.py`, calling the
REAL `daemon/pad_engine.py` and `daemon/graph_manager.py` interfaces and an
injected `EmbeddingModel` (the Protocol from `graph_manager.py`). No other
module's files are modified.

## Quoted from design.md (verified against current file content)

**Reused external types (NOT redefined):** `PADEngine`, `PADDelta`,
`PADSnapshot`, `Valence` (pad_engine); `MemoryGraph`, `PoignancyCategory`,
`Perspective`, `UncertaintyType`, `UncertaintyStatus`, `EdgeType`,
`EmbeddingModel`, `RetrievalItem`, `EventNode`, `Edge` (graph_manager). Q2 IS
`pad_engine.Valence`; poignancy IS `graph_manager.PoignancyCategory`; the PAD
delta IS `pad_engine.PADDelta`.

**Own types:** `GoalRelevance` (Q1), `Attribution` (Q3), `EmergencyType`,
`SocialSignals`, `AppraisalResult`, `AppraisalConfig`.

**The protected-chain invariants (Hard Constraints):** Q1–Q4 categorical (no
formula); PAD moves ONLY via `pad_engine.apply_appraisal_delta`;
`coping_potential` only at the Stage-2 gate, discarded otherwise; no other
invented number (substrate magnitudes are flagged placeholders); Active
Inference is framing only; emergency is a result, not an LLM-format branch;
pre-pass is non-generative and writes nothing to PAD/graph directly; Stage 5 is
a retrieval preference only.

**Flag disposition:** F-4a RESOLVED (ResLog 12, transient gate-only; band
values placeholder), F-4b RESOLVED (ResLog 10, framing only), F-4d FLAGGED
placeholder, F-4e FLAGGED placeholder, F-4f RESOLVED (ResLog 10, no overlap).
Cross-module gaps OQ-A (no increment surface), OQ-B (no emergency_type field),
OQ-C (no active-uncertainty-by-entity query), OQ-D (catch-up storage), OQ-E
(Stage-0 criterion) — flagged, not invented. OQ-F (NEUTRAL decay interaction) —
RESOLVED on this module's side (a neutral appraisal emits no PAD event, so
PAD_Engine's unresolved NEUTRAL branch is never entered); Module 1's NEUTRAL
decay itself remains the architect's.

---

## Tasks

- [ ] 1. Set up module scaffold and reused imports
  - Create `daemon/appraisal_chain.py`. Import the REAL types from
    `daemon.pad_engine` (`PADEngine`, `PADDelta`, `PADSnapshot`, `Valence`) and
    `daemon.graph_manager` (`MemoryGraph`, `PoignancyCategory`, `Perspective`,
    `UncertaintyType`, `UncertaintyStatus`, `EdgeType`, `EmbeddingModel`,
    `EventNode`, `Edge`). Do NOT re-declare any of these.
  - Add stdlib imports (`Enum`, `dataclass`, `Optional`, `List`, `Mapping`,
    `Tuple`, `Sequence`, `datetime`).
  - _Requirements: 14.4 (inject/reuse, no redefinition)_

- [ ] 2. Implement the own enums and dataclasses
  - `GoalRelevance` (none/low/medium/high), `Attribution` (self/user/
    circumstance/CAUSAL_UNCERTAIN), `EmergencyType` (PHYSICAL_THREAT/
    EXISTENTIAL_DISTRESS/DECISION_CRITICAL/UNCLASSIFIED), with exact string
    values from design.md.
  - `SocialSignals` (frozen), `AppraisalResult` (frozen, with `q2: Valence`,
    `poignancy: PoignancyCategory`, `pad_delta: PADDelta` — reused types),
    `AppraisalConfig` (frozen, carrying the flagged placeholders).
  - Unit tests: enum members/values are exactly the design's domains;
    `AppraisalResult.q2` accepts a `Valence`; `AppraisalResult` is frozen.
  - _Requirements: 4.1, 4.2, 4.3, 5.3, 13.4_

- [ ] 3. Implement module constants as flagged placeholders
  - `_PAD_STEP` (none 0.0 < low < medium < high) — `TODO(build-time)` SUBSTRATE
    placeholders; comment: ordered/non-negative only, NOT weights on features.
  - `_COPING_ABSENT`/`_COPING_SEVERE`/`_COPING_ADEQUATE` — `TODO(build-time,
    F-4a)`; comment: compared to IN-SPEC ≤0.15/≤0.04 only.
  - `_ARC_OPEN_CONSECUTIVE_NEGATIVE`/`_ARC_CLOSE_ABSENT_TURNS` —
    `TODO(build-time, F-4d)`.
  - `_VULNERABILITY_SIM_CUTOFF`, `_DISTRESS_MIN_MARKERS`, `_ABSOLUTIST_WORDS`,
    `_NEGATIVE_EMOTION_WORDS`, `_VULNERABILITY_EXEMPLARS` — `TODO(build-time,
    F-4e)`.
  - `_PHYSICAL_THREAT_CUES`/`_EXISTENTIAL_CUES`/`_DECISION_CRITICAL_CUES` —
    `TODO(build-time)` emergency sub-type lexicons.
  - `_CATCH_UP_CONFIRMED = 0.50`, `_CATCH_UP_INFERRED = 0.25` — IN-SPEC (v4
    Resolution Conditions table), NOT placeholders.
  - `_Q2_TO_GRAPH` mapping `Valence → graph appraisal_q2 string` (note the
    `VALENCE_UNCERTAIN` upper-case string the graph expects vs the enum value).
  - Unit test: `_PAD_STEP` is strictly ordered none<low<medium<high and
    none==0.0; `_Q2_TO_GRAPH[Valence.VALENCE_UNCERTAIN] == "VALENCE_UNCERTAIN"`.
    Do NOT assert the exact placeholder magnitudes elsewhere.
  - _Requirements: 5.5, 8.1, 14.2; F-4a/F-4d/F-4e placeholders_

- [ ] 4. Implement `AppraisalChain.__init__` (dependency injection)
  - Store injected `pad_engine`, `graph`, `embedding_model`, `config`.
  - Initialize in-memory conflict-arc bookkeeping (per-entity counters).
  - Do NOT instantiate a concrete embedding model; do NOT hold a PAD-writing
    handle other than `pad_engine`.
  - Unit test: constructing with a real `PADEngine`, in-memory `MemoryGraph`,
    and a `FakeEmbedding` succeeds; the chain exposes no attribute that is a
    concrete embedding model class instance it created itself.
  - _Requirements: 14.4_

- [ ] 5. Implement the Social-Signal Pre-Pass — DISTRESS_MARKER (lexical)
  - `_distress_marker(text) -> bool`: count absolutist + negative-emotion words
    and first-person-singular density; return True iff the count meets
    `_DISTRESS_MIN_MARKERS`. The count is PERCEPTION and stays inside this
    function — reduced to a boolean before any appraisal branch sees it.
  - Unit tests: absolutist/negative text → True; neutral text → False. Do NOT
    assert the exact count threshold value.
  - _Requirements: 3.2_

- [ ] 6. Implement the Social-Signal Pre-Pass — VULNERABILITY_DISCLOSURE
  - `_vulnerability(text) -> bool`: embed `text` via the injected model and
    compare (cosine) to embedded `_VULNERABILITY_EXEMPLARS`; True iff max
    similarity ≥ `_VULNERABILITY_SIM_CUTOFF`.
  - Reuse a cosine helper (may import `daemon.graph_manager._cosine` or define a
    local equivalent — do not depend on a private if a public path exists;
    a small local cosine is acceptable and avoids private coupling).
  - Unit test (with `FakeEmbedding` table): text embedded near an exemplar →
    True; far text → False. Cutoff value itself not asserted.
  - _Requirements: 3.3; F-4e_

- [ ] 7. Implement the Social-Signal Pre-Pass — REALITY_CONTRADICTION + conflict arc
  - `_reality_contradiction(entity_ref, text, now) -> bool`: delegate to
    `graph.reality_contradiction_check(entity_ref, text, now=now)` (real
    interface); no entity → False.
  - `_conflict_arc_update(entity_ref, q2, now) -> (open, closed_this_turn)`:
    the state machine (Addendum §1) using `_ARC_OPEN_CONSECUTIVE_NEGATIVE` /
    `_ARC_CLOSE_ABSENT_TURNS`. On closure, write ONE `"resolved"` edge
    (closing→opening EventNode) via `graph.write_edge(edge_type=EdgeType.
    RESOLVED, ...)` — the ONLY graph write the pre-pass performs, and it is an
    edge, not a PAD write.
  - `_social_signal_pre_pass(...) -> SocialSignals` assembles all four tags.
  - Unit tests: contradiction delegates to the graph method (seed a
    contradicting description, assert True); the pre-pass leaves PAD unchanged
    (compare `pad_engine.get_current_pad()` before/after a pre-pass-only call)
    and writes nothing to the graph except the arc-closure resolved edge.
  - _Requirements: 3.1, 3.4, 3.5, 3.6, 3.7; F-4d_

- [ ] 8. Implement Stage 0 — input classification
  - `_stage0_classify_input(text, signals) -> bool`: conservative categorical
    heuristic (non-empty/non-whitespace and carries an appraisable referent);
    empty/contentless → unparseable. Comment `TODO(build-time, OQ-E)` on the
    fuller criterion.
  - Unit tests: `"   "` → unparseable (False); a normal sentence → True.
  - _Requirements: 1.1; OQ-E_

- [ ] 9. Implement Stage 2 — categorical Q1, Q2, Q3
  - `_q1(text, context, signals) -> GoalRelevance`, `_q2(text, context, signals)
    -> Valence`, `_q3(text, context, signals) -> Attribution` — pure categorical
    dispatch over the pre-pass tags, small flagged lexical cue sets
    (presence/absence booleans), the retrieved context's prior appraisal
    profile, and the current PAD sign (as tie context only). Follow design.md's
    Stage-2 tables exactly.
  - NO numeric appraisal score anywhere: assert (by construction + a review
    test) there is no `score`/threshold-comparison that decides Q1–Q4.
  - Unit tests: absolutist distress → Q1 high, Q2 negative; positive-cue text →
    Q2 positive; conflicting cues → Q2 VALENCE_UNCERTAIN; unreadable attribution
    → Q3 CAUSAL_UNCERTAIN; Q1 never returns an UNCLEAR sentinel.
  - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [ ] 10. Implement Stage 2 — Q4 (qualitative) + needs-implications flag
  - `_q4(q1, q2, q3, signals, need_states) -> (notes: Optional[str],
    has_needs_implications: bool)`: qualitative notes; the boolean is decided
    categorically (a need is implicated by the appraisal / social tags). Keep
    normal-turn notes purely qualitative (ResLog 12).
  - Unit tests: a vulnerability disclosure → `has_needs_implications True` with a
    Connection note; a flat neutral turn → False, notes null/partial.
  - _Requirements: 4.4_

- [ ] 11. Implement Stage 2 — emergency gate (transient coping_potential)
  - `_severely_obstructive(q2, text, signals) -> bool` (categorical reading of
    Q2 = negative + threat cue / distress+vulnerability), and
    `_coping_potential(text, signals) -> float` computed ONLY when Q1 == high,
    mapping the categorical coping assessment to `_COPING_*` bands.
  - `_emergency_gate(q, text, signals) -> (bool, Optional[EmergencyType])`:
    emergency iff `Q1==high AND severely_obstructive AND coping<=0.15`;
    `coping<=0.04` → force Type B; else physical→A / existential→B / decision→C
    / UNCLASSIFIED→B.
  - `coping_potential` is a local variable — never stored on the result, never
    passed into any PADDelta.
  - Unit tests: physical-threat high+absent-coping → (True, PHYSICAL_THREAT);
    existential → (True, EXISTENTIAL_DISTRESS); coping≤0.04 + physical cue →
    forced Type B; non-severe high → (False, None); `Q1 != high` → coping never
    computed (assert via a spy/flag) and (False, None). Assert on the
    category/type, never on the coping band value.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5; F-4a_

- [ ] 12. Implement Stage 3 — output synthesis (full/partial/secondary + GRAPH_CONFLICT)
  - Count UNCLEAR among {Q2, Q3, Q4}; set `is_partial_appraisal`. 1–2 unclear →
    create matching UncertaintyNode(s) (VALENCE_UNCERTAIN / CAUSAL_UNCERTAIN)
    via `graph.create_uncertainty_node`. 3 unclear → mark for secondary
    appraisal (Task 14). Conflicting retrieved context → create GRAPH_CONFLICT.
  - Delegate the max-5 cap to Memory_Graph (do NOT re-implement it).
  - Unit tests: 0 unclear → partial False, no uncertainty node; 1 unclear (Q2) →
    a VALENCE_UNCERTAIN node exists (graph active count rises), partial True; 3
    unclear → secondary path chosen; a seeded conflicting context → GRAPH_CONFLICT
    node created.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.2_

- [ ] 13. Implement Stage 4 — `_build_pad_delta` (byproduct, no formula)
  - Per-axis categorical direction (design.md tables): pleasure←Q2,
    arousal←relevance, dominance←(Q3×Q2). Magnitude = `_PAD_STEP[Q1]`, one tier.
    `d_axis = dir_axis × step`. When `is_partial`, step DOWN one tier first
    (high→medium→low→none) — categorical, not a coefficient.
  - `valence = Q2` on the returned `PADDelta`.
  - Unit tests: positive Q2 → `d_pleasure > 0`; negative Q2 → `d_pleasure < 0`;
    circumstance/uncertain → `d_dominance < 0`; relevant (Q1≥low) → `d_arousal >
    0`; a partial appraisal's magnitude < the equivalent full appraisal's;
    positive and negative deltas of the same Q1 tier have EQUAL magnitude (no
    negativity inflation). Do NOT assert exact `_PAD_STEP` numbers.
  - _Requirements: 8.1, 8.3, 8.4_

- [ ] 14. Implement the secondary-appraisal delta
  - `_secondary_appraisal_delta() -> PADDelta`: fixed categorical profile —
    pleasure down (small tier), arousal up (a tier), dominance down (small
    tier), `valence = VALENCE_UNCERTAIN` — matching v4's described byproduct.
  - Used by Stage 0 (INPUT_UNCERTAIN) and Stage 3 (3 unclear).
  - Unit test: signs are (pleasure<0, arousal>0, dominance<0) and valence is
    VALENCE_UNCERTAIN.
  - _Requirements: 7.1, 8.1_

- [ ] 15. Implement Stage 4 application through PAD_Engine (the only PAD write)
  - Apply the constructed delta via `pad_engine.apply_appraisal_delta(delta)`.
  - A neutral appraisal (Q2 = neutral) is fully zero on every axis
    (arousal/dominance carry no direction without valenced meaning), so
    `_apply_delta` skips it — no delta applied, `_last_applied_valence` never
    set to NEUTRAL (design Error Handling / OQ-F resolution).
  - Route a supplied `aha_insight` PADDelta through the same
    `apply_appraisal_delta` path (Req 8.5).
  - Unit tests: after `appraise`, `get_current_pad()` == pre-PAD + delta
    components (exact); an `aha_insight` delta is applied; a neutral turn (bare
    and neutral-circumstance) leaves PAD unchanged, does not set
    `_last_applied_valence` to NEUTRAL, and a subsequent `on_soul_tick` does not
    raise (never enters PAD_Engine's NEUTRAL decay branch).
  - _Requirements: 8.2, 8.5, 14.1; OQ-F_

- [ ] 16. Implement Stage 5 — needs pressure as retrieval preference only
  - `_need_prefs(need_states) -> dict`: map recognized due/neglected needs to
    the `need_prefs` dict `graph.retrieve` consumes (e.g.
    `{"connection": True}`); unknown keys ignored.
  - Stage 5 itself is a no-op on PAD (the effect already happened at Stage 1
    retrieval). No needs-derived PAD pull anywhere.
  - Unit test: `need_states={"connection":"neglected"}` yields
    `{"connection": True}` and is passed to `retrieve`; PAD after the turn is
    identical to the same turn with no need pressure (need affects retrieval
    ordering only, not PAD).
  - _Requirements: 9.1, 9.2_

- [ ] 17. Implement Stage 6 — poignancy (categorical) + graph write
  - `_poignancy(q1, q2, q3, has_needs, entity_ref, emergency) -> PoignancyCategory`
    per design.md, calling `graph.is_first_of_kind(entity_ref, q2_str, q3_str)`
    BEFORE the write for the Critical conjunct; emergency → Critical.
  - `graph.write_event_node(...)` with graph-domain Q1/Q2/Q3 strings,
    `appraisal_q4_notes` (incl. emergency characterization when the gate fired —
    OQ-B), `poignancy_category`, `pad_delta_*`, `is_partial_appraisal`,
    `uncertainty_node_ref`, `entity_refs`, `perspective`. Exactly one live
    EventNode per turn.
  - Unit tests: Critical needs all four conjuncts incl. first-of-kind (a seeded
    prior matching (Q2,Q3) event on the entity makes a second turn non-Critical);
    High/Medium/Low per the table; emergency → Critical; exactly one EventNode
    added per `appraise`; an emergency turn persists `appraisal_q2 == "negative"`
    with the emergency note in `appraisal_q4_notes`.
  - _Requirements: 10.1, 10.2, 11.1, 11.2, 11.3, 11.4, 12.2, 12.3_

- [ ] 18. Implement uncertainty resolution (RESOLVED_CONFIRMED + catch-up)
  - When Stage 3 is all-clear and `active_uncertainty_refs` are supplied (OQ-C),
    resolve each via `graph.update_uncertainty_status(ref, RESOLVED_CONFIRMED,
    resolution_path="direct_information", catch_up_delta_*=..., 
    catch_up_magnitude_factor=_CATCH_UP_CONFIRMED)`, and apply
    `_CATCH_UP_CONFIRMED × (this turn's clear delta)` via
    `pad_engine.apply_appraisal_delta` (OQ-D).
  - Record the increment responsibility (Req 7.4) with a clear `TODO(OQ-A)`
    comment where a `graph.increment_uncertainty_interaction_count` call WOULD
    go; do NOT reach into `graph._conn`.
  - Unit tests: a supplied active ref is set RESOLVED_CONFIRMED (status
    round-trips via `graph.get_uncertainty_node`), and the catch-up shift moved
    PAD (a second `apply_appraisal_delta` occurred); with no refs supplied, no
    resolution and no catch-up. Assert the OQ-A increment is NOT faked (no
    private write, count unchanged).
  - _Requirements: 7.3, 7.4; OQ-A, OQ-C, OQ-D_

- [ ] 19. Implement `appraise(...)` — orchestrate Stages 0–6, return AppraisalResult
  - Read current PAD (`pad_engine.get_current_pad`), embed text, run Stages 0→6
    in order, and assemble the frozen `AppraisalResult` (Q1–Q4, poignancy,
    applied `pad_delta`, emergency flag/type, node ids, social signals, and the
    qualitative `most_salient_note`).
  - `most_salient_note` is a qualitative/categorical string — NEVER raw PAD
    numbers, graph node ids/contents, or Q1–Q4 raw values (Soul_Filter
    translates further).
  - Emergency turns: still shift PAD and write the EventNode (Req 12.3); result
    carries flag + type; the chain does NOT assemble five-field or Type A/B/C
    text (Req 12.1).
  - Unit tests: an end-to-end normal turn returns a coherent result and moved
    PAD by exactly the delta and grew the graph by one EventNode; an emergency
    turn returns emergency True + a type, shifted PAD, and wrote an EventNode
    with `appraisal_q2 == "negative"`.
  - _Requirements: 1.3, 13.1, 13.2, 13.3, 13.4, 13.5, 12.1, 12.3_

- [ ] 20. Boundary / anti-machine API-surface tests
  - Assert `AppraisalChain` exposes NO method that writes PAD directly (the only
    PAD path is `pad_engine.apply_appraisal_delta`), NO method that emits
    five-field / Type A/B/C LLM instruction text, and NO method that
    instantiates a concrete embedding model.
  - Assert the PAD change across any turn equals exactly the sum of the
    `apply_appraisal_delta` calls that turn (PAD purity).
  - Assert `_build_pad_delta` produces its magnitude from a single `_PAD_STEP`
    tier × a categorical direction (reviewed) — the magnitude-ordering/sign
    tests (Task 13) stand in for "no `Σ wᵢ·featureᵢ`".
  - Assert `coping_potential` never appears on `AppraisalResult`.
  - _Requirements: 5.5, 8.2, 14.1, 14.2, 14.3, 14.4_

- [ ] 21. Wire together, run the full suite, and confirm flag/OQ status in code
  - Ensure all tests pass together (each test builds its own in-memory
    `MemoryGraph`, its own baseline-initialized `PADEngine`, and a
    `FakeEmbedding`; no shared state).
  - Confirm by inspection + tests:
    - **F-4a RESOLVED:** `coping_potential` computed only when Q1==high, only in
      `_emergency_gate`, never persisted/PAD-fed; band values `TODO(build-time)`.
    - **F-4b RESOLVED:** no free-energy/Active-Inference subsystem exists; it is
      only referenced as framing in comments/docstrings.
    - **F-4d / F-4e FLAGGED:** arc counts, similarity cutoff, distress threshold,
      lexicons are `TODO(build-time)` placeholders; tests assert properties, not
      magnitudes.
    - **F-4f RESOLVED:** exactly one live EventNode per turn; no DMN-buffer write.
    - **OQ-A/B/C/D/E/F:** each is flagged in code comments and behaves as
      designed (increment not faked; emergency_type on result + q4_notes,
      appraisal_q2 "negative"; active refs accepted as input; catch-up from
      resolving delta × in-spec factor; Stage-0 heuristic; NEUTRAL handled
      conservatively) — none resolved by invention.
    - **No emotion-formula:** PAD changes ONLY via `apply_appraisal_delta`;
      `_build_pad_delta` is direction(categorical) × tier(categorical).
  - Run `python3 -m pytest tests/test_appraisal_chain.py -q` (green), then
    `python3 -m pytest -q` (no regression to Modules 1/3/11).
  - _Requirements: all; F-4a/F-4b/F-4f RESOLVED, F-4d/F-4e placeholders; OQ-A…F
    flagged, not invented_

