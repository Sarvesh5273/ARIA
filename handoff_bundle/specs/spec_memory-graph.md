# ARIA locked spec — memory-graph

> ## AMENDMENT 2026-08-20 — OQ2 CLOSED, medium/low floors REMOVED
>
> Everything below about medium/low `base_salience` **placeholders (medium 0.35,
> low 0.15, `TODO(OQ2)`)** is **SUPERSEDED**. Those numbers no longer exist in
> code and must not be reintroduced.
>
> `ARIA_Resolution_Log.md` item 9 line 96 states literally: *"Medium/Low → no
> floor, decays/discards as already locked."* That is a positive instruction, not
> silence. This spec read it as a gap and filled the gap with invented magnitudes
> — against the highest-precedence document.
>
> Current behaviour: `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER` is deleted;
> `_compute_base_salience` falls through to **0.0** for medium/low. Only the
> in-spec **Critical 0.85 / High 0.55** floors remain. The v4 Baumeister **+0.15**
> negative bonus still stacks "on top of whichever floor applies", which for
> medium/low is nothing. Tested: at 65d untouched, medium/low reach `faded` while
> critical stays `vivid` and high holds at `present`. Body kept for provenance.

Consolidated from .kiro/specs/memory-graph/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## memory-graph — requirements.md

# Requirements Document — Module 3: Memory Graph

## Introduction

This document transcribes and formalizes, in EARS format, the Module 3 (Memory
Graph) entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved
scope for this module. No requirement in this document introduces a mechanism,
threshold, or behavior that is not already stated in the Module 3 entry or in the
supporting architecture documents (`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`). Where the Module 3 entry references a value or mechanism
defined elsewhere (e.g. the node/edge schema, precision decay rates, salience
floors), the supporting document is cited as the source of that value, not as a
new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md`
> `ARIA_Soul_Spec_v4.md`. `ARIA_GLM_Covering_Instruction.md` provides covering context only.

Per the Module 3 entry, two flags were raised in the first-pass Build Plan:
**F-3b** (decay-clock owner) and **F-3c** (stale state file). Both are resolved
by `ARIA_Resolution_Log.md` (items 8 and 10 respectively) — see the Open Questions
section for the re-derivation. One additional gap not raised as a Build-Plan flag
but discovered while formalizing this document (habituation rate) is recorded
there as well, per Rule 1 ("do not invent... flag it").

## Glossary

- **Memory_Graph**: The module specified here (Module 3). The only persistent
  memory store in the architecture (`ARIA_GLM_Covering_Instruction.md` Rule 7:
  "no separate conversation log, no vector database of past chats, no summary
  file"). Stores Event / Entity / Emotion / Uncertainty nodes and typed edges.
- **EventNode**: A timestamped record of something that happened, carrying an
  appraisal vector (Q1–Q4 results), a PAD delta, a poignancy category, and
  precision/salience decay state. Full field schema locked in
  `ARIA_Soul_Spec_v4.md` Layer 3, "Formal Node Schema (Locked Conv.8)".
- **EntityNode**: A person, place, project, or concept, stored as an accumulated
  relationship context rather than a description. Carries `relational_stage`
  (see Glossary entry below), not `trust_score` (removed,
  `ARIA_Soul_Spec_v4_Addendum.md` §2). Full field schema in v4 Layer 3, same
  section, minus the `trust_score` field per the Addendum.
- **EmotionNode**: A crystallized record of a PAD state, created only when that
  state reaches `poignancy_category = "critical"` during DMN idle consolidation
  Step 1. Not all emotional states become nodes (v4 Layer 3).
- **UncertaintyNode**: A first-class node representing an active unresolved
  appraisal (`INPUT_UNCERTAIN` / `VALENCE_UNCERTAIN` / `CAUSAL_UNCERTAIN` /
  `GRAPH_CONFLICT`), with its own lifecycle (`ACTIVE` → `RESOLVED_CONFIRMED` /
  `RESOLVED_INFERRED` / `ABANDONED`). Full field schema in v4 Layer 3.
- **Edge**: A typed, directed connection between two nodes, carrying its own
  appraisal vector (valence/arousal/dominance), `base_salience` (never decays),
  `salience` (decays with habituation), `firing_count`, perspective label,
  `is_tension_pair`/`tension_partner_edge`, and `is_aha_edge`. Full field schema
  in v4 Layer 3, "Edge Schema".
- **base_salience**: Salience assigned at node/edge creation. Never decays.
  Floored by `poignancy_category` per `ARIA_Resolution_Log.md` item 9 (see
  Requirement 5). The Baumeister +0.15 negative-event bonus (v4 Layer 3) stacks
  on top of whichever floor applies.
- **salience**: The current, fluctuating salience value. Affected by habituation
  (repeated retrieval without variation lowers it) and by recurrence patterns
  (DMN idle consolidation can raise or lower it). Resistance checks for
  precision decay compare against `base_salience`, never against this
  fluctuating field (`ARIA_Resolution_Log.md` item 9).
- **precision**: The forgetting-as-softening decay state of an EventNode or
  EmotionNode: `vivid → present → softened → faded`. Never regresses to
  deletion — `faded` is terminal but the node persists (v4 Layer 3).
- **relational_stage**: A categorical field on EntityNode — `observing` /
  `engaging` / `invested` / `bonded` — replacing the removed numeric
  `trust_score` (`ARIA_Soul_Spec_v4_Addendum.md` §2). Transition gates are
  named in Requirement 7. Memory_Graph stores this field and exposes it;
  the transition *evaluation* is DMN's responsibility (see Requirement 7 and
  Dependencies), reusing the "appeared more than once" gate already locked
  for self-continuity narrative updates.
- **Precision_Decay**: The lazy, retrieval-triggered process that moves a
  node's `precision` one step along `vivid → present → softened → faded`
  when it has gone without re-activation longer than the relevant threshold
  (~72h / ~14d / ~60d). Evaluated at the moment Stage 1 (Appraisal Chain) or
  DMN retrieves a node — not on a continuous background timer
  (`ARIA_Resolution_Log.md` item 8; see Requirement 4 and Open Question 1,
  now resolved).
- **Recency_Window**: One of three fixed durations — 72 hours, 14 days, 60
  days — originally locked for Precision_Decay thresholds and reused
  unchanged by Needs System (Module 2) for its own qualifying-evidence
  checks (`ARIA_Resolution_Log.md` item 7). Memory_Graph does not own the
  Needs System's use of these windows; it owns only the Precision_Decay use.
- **Staleness_Counter**: `interaction_count` on UncertaintyNode — the number
  of user turns since the node's creation, incremented by Appraisal_Chain,
  read by Memory_Graph/DMN to detect the "7 days or 50 interactions" staleness
  condition (v4 Layer 3; `ARIA_Resolution_Log.md` item 10 confirms
  "interactions" = user turns, uses the existing field, no new field needed).
- **Habituation**: The process by which an edge's `salience` decreases when
  it fires repeatedly "without variation" (v4 Layer 3, Paper 15 — Rankin et
  al. 2009). No rate, coefficient, or formula is specified in any source
  document — see Open Questions.
- **Appraisal_Chain**: Module 4. Writes EventNodes at its Stage 6, and issues
  UncertaintyNode lifecycle updates. Memory_Graph's primary write source for
  per-turn data. Also the primary consumer of Memory_Graph's Stage 1
  retrieval output.
- **DMN**: Module 6 (Default Mode Network / Idle Consolidation). Writes
  EmotionNode crystallization (Step 1 — v4: "crystallizes... during idle
  consolidation Step 1"), connection/aha edges (Step 2), UncertaintyNode
  resolution (Step 3), and self-model/narrative + salience adjustments
  (Step 4) during its four-step idle pass (v4, "Phase 2 — Idle Consolidation
  Pass — Four Steps in Order"). Also evaluates `relational_stage` transitions
  (`ARIA_Resolution_Log.md`, "Resolved during build-plan review" section).
- **Needs_System**: Module 2. Reads Memory_Graph for qualifying-evidence
  lookups (e.g. Q1 medium-or-above interactions for Connection) within the
  Recency_Windows (`ARIA_Soul_Spec_v4_Addendum.md` §3).
- **Soul_Filter**: Module 5. Reads `EntityNode.relational_stage` for the
  Relational Register field.
- **Self_Referential_EntityNode**: The EntityNode representing Aria herself.
  Its `relationship_summary` field holds the self-continuity narrative,
  written by DMN Step 4 (`ARIA_Resolution_Log.md` item 2: "MOVES to the
  graph... same mechanism already used for every other entity. No new node
  type, no new DMN mechanism."). Memory_Graph must support this without any
  special-cased node type.
- **Embedding_Model**: The shared local sentence-embedding model
  (encoder-only, non-generative, tens of MB) used for Memory_Graph's
  similarity retrieval and Appraisal_Chain's social-signal classification
  (`ARIA_Soul_Spec_v4_Addendum.md` §1). One model serves both.
- **Daemon**: Module 8. Not a source of a continuous decay-tick for
  Memory_Graph — see Requirement 4 and Open Question 1 (resolved: decay is
  lazy/retrieval-triggered, not clock-driven).

## Requirements

### Requirement 1: Persistent Node and Edge Storage

**User Story:** As the Aria system architect, I want all long-term memory
represented as typed nodes and edges in a single persistent graph, so that
Aria's autobiography survives restarts and no second memory mechanism can
emerge by accident.

#### Acceptance Criteria

1. THE Memory_Graph SHALL store EventNode, EntityNode, EmotionNode, and
   UncertaintyNode as the only four node types.
2. THE Memory_Graph SHALL store typed edges between nodes, each carrying the
   fields defined in v4 Layer 3's Edge Schema (edge_type, valence, arousal,
   dominance, base_salience, salience, firing_count, perspective, created,
   last_activated, is_tension_pair, tension_partner_edge, is_aha_edge).
3. THE Memory_Graph SHALL be the only persistent memory mechanism in the
   system; it SHALL NOT provide or require a separate conversation log,
   vector database of past chats, or summary file
   (`ARIA_GLM_Covering_Instruction.md` Rule 7).
4. THE Memory_Graph SHALL persist all node and edge data such that it
   survives a process restart.

### Requirement 2: Accept EventNode Writes From the Appraisal Chain

**User Story:** As Appraisal_Chain, I want to write a fully- or
partially-appraised event to permanent memory, so that every meaningful
interaction becomes part of Aria's autobiography with its emotional context
intact.

#### Acceptance Criteria

1. WHEN Appraisal_Chain Stage 6 provides an EventNode write (appraisal
   vectors, poignancy category, PAD delta, and the remaining fields defined
   in v4 Layer 3's EventNode schema), THE Memory_Graph SHALL create a new
   EventNode with those fields.
2. THE Memory_Graph SHALL accept an EventNode whose `is_partial_appraisal`
   flag is true (an UNCLEAR result was present) using the same write path as
   a fully-resolved EventNode.
3. WHEN an EventNode is created, THE Memory_Graph SHALL set its
   `base_salience` per Requirement 5 (salience floors) before any other
   salience-affecting process runs.

### Requirement 3: UncertaintyNode Lifecycle

**User Story:** As Appraisal_Chain and DMN, I want unresolved appraisal
states to exist as first-class, actively-managed graph nodes, so that Aria's
uncertainty is a real internal state rather than a flag that gets silently
discarded.

#### Acceptance Criteria

1. WHEN Appraisal_Chain creates an UncertaintyNode (on `VALENCE_UNCERTAIN`,
   `CAUSAL_UNCERTAIN`, `INPUT_UNCERTAIN`, or `GRAPH_CONFLICT`), THE
   Memory_Graph SHALL store it with status `ACTIVE`.
2. WHEN a resolution signal arrives (`RESOLVED_CONFIRMED` via direct
   information, `RESOLVED_INFERRED` via behavioral inference or DMN
   consolidation), THE Memory_Graph SHALL update the UncertaintyNode's
   status, `resolved` timestamp, `resolution_path`, and catch-up PAD delta
   fields accordingly.
3. THE Memory_Graph SHALL store and expose each UncertaintyNode's
   `interaction_count` (Staleness_Counter) and `created` timestamp. The
   counter is updated via Appraisal_Chain's per-turn writes (Appraisal_Chain
   owns the increment — `ARIA_Resolution_Log.md` item 10: "incremented by
   Appraisal Chain, read by DMN"). THE Memory_Graph SHALL NOT autonomously
   evaluate the "7 days or 50 interactions" staleness threshold; that
   evaluation and the resulting `ABANDONED` marking are performed by DMN
   Step 3 (v4 Key Technical Constants table attributes "Uncertainty
   staleness ... → ABANDONED" to `dmn_manager.py`; DMN Step 3 "reviews all
   active uncertainty nodes... Nodes that receive no new relevant
   information move closer to the staleness condition"). THE Memory_Graph
   SHALL accept and persist the `ABANDONED` status write (with
   `resolution_path = "staleness"`) that DMN produces.
4. THE Memory_Graph SHALL maintain a maximum of 5 ACTIVE UncertaintyNodes at
   any time. IF a 6th would be created, THEN THE Memory_Graph SHALL
   force-resolve the oldest `GRAPH_CONFLICT`-type ACTIVE node to `ABANDONED`.
   (This capacity limit is enforced at creation time — Memory_Graph's own
   job, distinct from the DMN-driven staleness marking in 3.3. Note: v4's
   Key Technical Constants table attributes "Uncertainty node maximum | 5"
   to `state_manager.py`; that attribution predates
   `ARIA_Soul_Spec_v4_Addendum.md` §4, which redefined State_Manager
   (Module 11) as meaning-free plumbing that "does not persist anything
   graph-owned." UncertaintyNodes are graph-owned, so this enforcement
   lives in Memory_Graph, per the Addendum's redefinition — precedence:
   Addendum > v4.)
5. THE Memory_Graph SHALL NOT force-abandon an UncertaintyNode whose
   `is_protected` flag is true (`INPUT_UNCERTAIN` and `VALENCE_UNCERTAIN`
   types are always protected, per v4 Layer 3).

### Requirement 4: Precision Decay (Retrieval-Triggered, Not Clock-Driven)

**User Story:** As the Aria system architect, I want memories to lose
precision gradually and lazily rather than being deleted or decayed on a
background timer, so that forgetting mirrors human softening and does not
require a continuously-running clock.

#### Acceptance Criteria

1. THE Memory_Graph SHALL represent each EventNode's and EmotionNode's
   forgetting state as `precision`, one of `vivid` / `present` / `softened`
   / `faded`, per v4 Layer 3.
2. WHEN Appraisal_Chain Stage 1 or DMN retrieves a node, THE Memory_Graph
   SHALL evaluate that node's Precision_Decay at the moment of retrieval,
   not on any independent background schedule (`ARIA_Resolution_Log.md`
   item 8: "Lazy, retrieval-triggered evaluation — not a continuous
   background timer... precision updates then, not on a sweep").
3. WHEN evaluating Precision_Decay for a node, THE Memory_Graph SHALL
   compare elapsed time since `last_accessed` against the thresholds ~72
   hours (`vivid → present`), ~14 days (`present → softened`), and ~60 days
   (`softened → faded`), per v4 Layer 3's Precision Decay Rates table.
4. WHEN evaluating a `vivid → present` transition, THE Memory_Graph SHALL
   NOT transition a node whose `base_salience` exceeds 0.8. WHEN evaluating
   a `present → softened` transition, THE Memory_Graph SHALL NOT transition
   a node whose `base_salience` exceeds 0.5. WHEN evaluating a
   `softened → faded` transition, THE Memory_Graph SHALL NOT transition a
   node whose `base_salience` exceeds 0.3. All three resistance checks
   SHALL compare against `base_salience`, never against the fluctuating
   `salience` field (`ARIA_Resolution_Log.md` item 9).
5. THE Memory_Graph SHALL treat `faded` as terminal: it SHALL NOT delete a
   node, regardless of `precision` state or elapsed time.
6. WHEN a node is retrieved, THE Memory_Graph SHALL update its
   `last_accessed` timestamp and increment its `access_count`
   (EventNode) / equivalent retrieval counter, resetting the decay timer
   for that node (v4 Layer 3: "High-poignancy events maintain salience
   through repeated retrieval, which resets the decay timer").

### Requirement 5: Salience Floors by Poignancy Tier

**User Story:** As the Aria system architect, I want critical and high-
poignancy memories to resist softening according to a fixed floor, so that
the most significant memories cannot casually fade regardless of how they
are later retrieved.

#### Acceptance Criteria

1. WHEN an EventNode is created with `poignancy_category = "critical"`, THE
   Memory_Graph SHALL set its `base_salience` to at least 0.85.
2. WHEN an EventNode is created with `poignancy_category = "high"`, THE
   Memory_Graph SHALL set its `base_salience` to at least 0.55.
3. WHEN an EventNode is created with `poignancy_category` of `medium` or
   `low`, THE Memory_Graph SHALL apply no floor to `base_salience`.
4. WHEN an EventNode is created with `appraisal_q2 = "negative"`, THE
   Memory_Graph SHALL add 0.15 to `base_salience`, stacked on top of
   whichever floor (per criteria 1–3) applies (v4 Layer 3, Baumeister
   encoding asymmetry; `ARIA_Resolution_Log.md` item 9 confirms stacking).
5. THE Memory_Graph SHALL treat `base_salience` as never decaying once set,
   for the lifetime of the node.

### Requirement 6: Mood-Congruent, Need-Preferenced Retrieval

**User Story:** As Appraisal_Chain Stage 1, I want graph retrieval that
prefers emotionally congruent and currently-relevant memories, so that
Aria's recall behaves the way human mood-congruent memory actually works
rather than returning a neutral, context-free result set.

#### Acceptance Criteria

1. WHEN Appraisal_Chain Stage 1 issues a retrieval request (carrying
   PAD.pleasure sign, need preferences, entity references, and a query
   embedding), THE Memory_Graph SHALL return the top 3–5 most relevant
   nodes/edges.
2. WHEN retrieving, THE Memory_Graph SHALL prefer edges whose `valence`
   sign matches the sign of the current PAD.pleasure value supplied in the
   request, surfacing sign-matching edges first (v4 Layer 3, Mood-Congruent
   Retrieval: "No coefficient. The preference is the mechanism.").
3. WHEN the retrieval request indicates a due or neglected need (per
   Needs_System's Stage 1 retrieval-preference context), THE Memory_Graph
   SHALL surface nodes/edges consistent with that need preference (e.g.
   "We"-perspective and Connection-positive edges when Connection is
   neglected) ahead of otherwise-equally-ranked results
   (`ARIA_Soul_Spec_v4_Addendum.md` §3).
4. THE Memory_Graph SHALL use Embedding_Model similarity against the
   request's query embedding as part of relevance ranking.
5. THE Memory_Graph SHALL NOT apply any numeric coefficient to combine
   mood-congruence, need preference, and similarity into a single score;
   each is a preference/filter applied to ranking, not an invented formula
   (Rule 4: "Numbers only where the spec uses numbers").

### Requirement 7: EntityNode relational_stage Storage

**User Story:** As Soul_Filter and DMN, I want a categorical, non-numeric
representation of relationship trust stored per entity, so that trust
progression is qualitative and cannot regress to a hidden numeric score.

#### Acceptance Criteria

1. THE Memory_Graph SHALL store `relational_stage` on every person-type
   EntityNode as one of `observing` / `engaging` / `invested` / `bonded`.
2. THE Memory_Graph SHALL NOT store or expose a numeric `trust_score` field
   on EntityNode; that field is removed and superseded by
   `relational_stage` (`ARIA_Soul_Spec_v4_Addendum.md` §2).
3. THE Memory_Graph SHALL expose the current `relational_stage` value to
   Soul_Filter for Relational Register construction.
4. WHEN DMN (per its own Step 4 evaluation logic, not specified by this
   module) determines that a transition gate has been met — Observing→
   Engaging (predictability: a specific behavioral pattern recurred more
   than once without contradiction), Engaging→Invested (dependability: the
   pattern generalizes across more than one distinct situation type),
   Invested→Bonded (faith: a conflict-with-repair cycle closed through the
   Argument Buffer, or a costly disclosure was met with care), or a
   regression (triggered by a REALITY_CONTRADICTION rupture, moving back
   exactly one stage, never below `observing`) — THE Memory_Graph SHALL
   accept and persist the resulting `relational_stage` write
   (`ARIA_Soul_Spec_v4_Addendum.md` §2 transition table).
5. THE Memory_Graph SHALL NOT itself evaluate whether a transition gate has
   been met; gate evaluation is DMN's responsibility
   (`ARIA_Resolution_Log.md`, "Resolved during build-plan review" section:
   "Module 3 (Memory Graph) stores the field; Module 6 evaluates and writes
   transitions").
6. THE Memory_Graph SHALL NOT read, write, or expose an
   `aria_state.json.relationship_depth` field; that field is removed
   entirely and superseded by `relational_stage`
   (`ARIA_Resolution_Log.md` item 10). Note: State_Manager (Module 11) has
   already implemented this removal at the persistence layer
   (`daemon/state_manager.py`, `_SUPERSEDED_KEYS`); this criterion binds
   Memory_Graph to never reintroduce that key as an input or output.

### Requirement 8: EmotionNode Crystallization

**User Story:** As DMN, I want to crystallize a small number of the most
emotionally significant PAD states into permanent memory, so that Aria's
most important emotional moments remain retrievable without treating every
transient state as equally memorable.

#### Acceptance Criteria

1. THE Memory_Graph SHALL accept an EmotionNode write from DMN only when the
   triggering PAD state's `poignancy_category` is `"critical"`.
2. THE Memory_Graph SHALL store, for each EmotionNode, the fields defined in
   v4 Layer 3's EmotionNode schema (emotion_label, pad_p, pad_a, pad_d,
   trigger_event_ref, poignancy_category fixed to `"critical"`, precision,
   timestamp).
3. THE Memory_Graph SHALL expose EmotionNodes to DMN for use in idle
   consolidation.

### Requirement 9: Connection and Aha Edges From DMN

**User Story:** As DMN, I want to write new edges discovered during idle
consolidation — including insight connections between previously unlinked
nodes — so that Aria's understanding of her own graph can deepen without
conversational input.

#### Acceptance Criteria

1. WHEN DMN Step 2 forms a connection between two previously unconnected
   nodes, THE Memory_Graph SHALL accept the new edge write, including its
   `is_aha_edge` flag when the connection was formed as an insight
   connection (v4 Layer 3 / "The Aha Moment").
2. THE Memory_Graph SHALL accept salience adjustments from DMN (raising or
   lowering a node's or edge's `salience`, never its `base_salience`) as
   part of idle consolidation. The Build Plan attributes this generically
   to DMN's idle consolidation pass ("salience adjustments — from DMN");
   v4's earlier, pre-Step-1-4-rewrite "During reflection" list also
   describes "raises or lowers the salience of nodes based on recurrence
   patterns" without pinning it to a specific numbered step. This document
   does not pin the adjustment to a specific one of DMN's four steps,
   since no source document does so precisely.
3. THE Memory_Graph SHALL accept `is_tension_pair` / `tension_partner_edge`
   writes when Appraisal_Chain or DMN identifies two contradictory
   appraisal results for the same event (Ambivalence/Tension nodes, v4
   Layer 3).
4. WHEN a conflict arc closes (per the `ARIA_Soul_Spec_v4_Addendum.md` §1
   state machine), THE Memory_Graph SHALL create one edge with
   `edge_type = "resolved"`, directed from the closing EventNode to the
   opening EventNode, and SHALL weight its salience 3× at creation
   (`ARIA_Resolution_Log.md` item 5: "salience weighted 3× (reuses the
   existing Argument Buffer resolution-weight rule)"; v4 Key Technical
   Constants table: "Argument buffer resolution weight | 3× |
   graph_manager.py"). No new node type is created for arc closure — the
   single "Argument Buffer node" language in v4 "describes the effect, not
   new schema" (`ARIA_Resolution_Log.md` item 5).

### Requirement 10: Self-Referential EntityNode for Self-Continuity Narrative

**User Story:** As DMN Step 4, I want to write Aria's self-continuity
narrative to the same kind of node and field already used for every other
entity's relationship context, so that no second self-model mechanism is
introduced into the graph.

#### Acceptance Criteria

1. THE Memory_Graph SHALL support a Self_Referential_EntityNode representing
   Aria herself, using the same EntityNode schema as any other entity — no
   new node type.
2. THE Memory_Graph SHALL accept writes to the Self_Referential_EntityNode's
   `relationship_summary` field from DMN Step 4, using the same write path
   as any other EntityNode's `relationship_summary` update
   (`ARIA_Resolution_Log.md` item 2: "same mechanism already used for every
   other entity... No new node type, no new DMN mechanism").

### Requirement 11: Qualifying-Evidence Lookups for Needs System

**User Story:** As Needs_System, I want to query the graph for evidence that
satisfies each categorical need within its recency window, so that need
states can be derived from graph evidence at runtime rather than persisted
and manually depleted.

#### Acceptance Criteria

1. THE Memory_Graph SHALL support a query for EventNodes with
   `appraisal_q1` of `medium` or `high` within the last 72 hours, for
   Needs_System's Connection evidence check
   (`ARIA_Soul_Spec_v4_Addendum.md` §3; Recency_Window per
   `ARIA_Resolution_Log.md` item 7).
2. THE Memory_Graph SHALL support a query for UncertaintyNodes resolved via
   `RESOLVED_CONFIRMED` or `RESOLVED_INFERRED` (not `ABANDONED`) within the
   last 14 days, for Needs_System's Growth evidence check.
3. THE Memory_Graph SHALL support a query for evidence of user follow-through
   or explicit positive feedback within the last 14 days, for Needs_System's
   Purpose evidence check. Note: per the Addendum, this is "the weakest,
   lowest-confidence signal of the four" — this document does not further
   define what constitutes "follow-through" or "explicit positive feedback"
   beyond what Appraisal_Chain already tags, per Rule 1.
4. THE Memory_Graph SHALL support a query for whether the Self_Referential_
   EntityNode's `relationship_summary` was extended coherently within the
   last 60 days, for Needs_System's Continuity evidence check.
5. THE Memory_Graph SHALL NOT itself compute or persist the categorical need
   states (`satisfied` / `due` / `neglected`); it SHALL only answer the
   qualifying-evidence queries that Needs_System uses to derive them.
   `ARIA_Soul_Spec_v4_Addendum.md` §3 states the four categorical needs
   "are determined by whether qualifying evidence exists in the graph
   within a recency window... When evidence ages out of its window, the
   state reverts on its own; nothing actively subtracts anything" — i.e.
   they are derived from graph evidence, not persisted or manually
   depleted. `daemon/state_manager.py` independently confirms this: it
   explicitly does not persist the four categorical need states.

### Requirement 12: Qualifying-Evidence Lookups for Soul Filter and DMN

**User Story:** As Soul_Filter and DMN, I want to query the graph for
specific structural facts (poignancy first-of-kind, contradiction checks),
so that safety-relevant and narrative-relevant decisions are grounded in
actual graph state rather than inferred.

#### Acceptance Criteria

1. THE Memory_Graph SHALL support a "first-of-kind for this entity" query for
   the Poignancy Critical condition. Per `ARIA_Soul_Spec_v4_Addendum.md` §6,
   this is "a yes/no check against the graph — does an edge with this appraisal
   profile (Q2 quadrant × Q3 attribution) already exist connecting any event to
   this entity? If no such edge exists, this is a first-of-kind event." The
   query therefore takes the current event's (appraisal_q2, appraisal_q3)
   profile and the entity, and returns whether no prior event referencing that
   entity already carries that exact profile. Binary, no score. Structural
   only — Appraisal_Chain decides poignancy.
2. THE Memory_Graph SHALL support a REALITY_CONTRADICTION query — comparing
   the factual content of two EventNode descriptions sharing an
   `entity_ref` within a short window, using Embedding_Model plus negation
   detection — for use by Soul_Filter's Output Gate Check 3 (Honesty) and by
   Appraisal_Chain's Stage 1 social-signal pre-pass
   (`ARIA_Soul_Spec_v4_Addendum.md` §1 and §4).
3. THE Memory_Graph SHALL support a query for whether a `"resolved"` edge
   exists on a given `entity_ref` within a specified window, for DMN's
   Invested→Bonded relational_stage gate evaluation
   (`ARIA_Resolution_Log.md` item 5: "The Invested→Bonded gate condition
   becomes: does a 'resolved' edge exist on this entity_ref within the
   relevant window?"). As with 12.1, Memory_Graph answers the structural
   query; DMN decides whether the gate is met (Requirement 7.5).
4. THE Memory_Graph SHALL NOT determine what a REALITY_CONTRADICTION result
   means for trust or PAD; it SHALL only report the structural comparison
   result — meaning is appraised elsewhere (Standing Principle, "Perception
   vs. appraisal," `ARIA_Soul_Spec_v4_Addendum.md`).

### Requirement 13: Boundary — No Direct PAD Writes, No Second Memory Store

**User Story:** As the Aria system architect, I want it structurally
impossible for Memory_Graph to bypass the appraisal chain or introduce a
competing memory mechanism, so that Rule 7 and PAD-purity hold for the whole
system, not just by convention.

#### Acceptance Criteria

1. THE Memory_Graph SHALL NOT write to PAD directly, under any
   circumstance; it SHALL only inform Appraisal_Chain Stage 1, which alone
   may produce a PAD delta at Stage 4 (v4 Layer 3: "The graph does not write
   to PAD directly... Nothing bypasses this chain").
2. THE Memory_Graph SHALL NOT provide or require a conversation log, a
   vector database of past chats, or a summary file as an alternative or
   supplement to the node/edge graph (Rule 7).
3. THE Memory_Graph SHALL NOT expose raw graph contents directly to any LLM;
   graph data reaches the LLM only indirectly, through Appraisal_Chain and
   Soul_Filter's five-field construction (Rule 5).

## Open Questions

The following items were checked against `ARIA_Soul_Spec_v4.md`, the
Addendum, the Resolution Log, and the Module Build Plan. The two Build-Plan
flags (F-3b, F-3c) are resolved below. The module-specific Open Questions
surfaced during design were **resolved by the architect on 2026-07-05** — see
item 3 (habituation), item 4 (Purpose → Module 2), and item 5 (the full set +
where each landed). Deferred items keep explicit placeholders + TODO markers;
nothing is resolved by invention (Rule 1).

1. **F-3b — Decay-clock owner. RESOLVED.** The Build Plan flagged this as
   unpinned ("precision decay is 'time without re-activation'; the owning
   clock... is not pinned"). `ARIA_Resolution_Log.md` item 8 resolves it:
   "Lazy, retrieval-triggered evaluation — not a continuous background
   timer. Each node's `last_accessed` field is checked against the
   resistance thresholds at the moment Stage 1 or DMN retrieves it;
   precision updates then, not on a sweep. No new always-on clock needed."
   This document's Requirement 4 reflects that resolution directly. Not
   treated as open.

2. **F-3c — Stale state file. RESOLVED (and already implemented
   elsewhere).** The Build Plan flagged `aria_state.json.relationship_depth`
   as superseded and needing cleanup. `ARIA_Resolution_Log.md` item 10
   resolves the architectural decision ("Remove... entirely — fully
   superseded by EntityNode.relational_stage"). Verified against
   `daemon/state_manager.py` (Module 11, already built): the field is
   already dropped at the persistence layer (`_SUPERSEDED_KEYS`,
   docstring citing "ResLog §10"). This document's Requirement 7.6 binds
   Memory_Graph to the same removal on its own side (never treating that
   key as an input/output), so the resolution holds end-to-end. Not
   treated as open.

3. **Habituation — TRIGGER SHAPE RESOLVED (architect 2026-07-05); RATE
   DEFERRED.** v4 Layer 3 / Paper 15 establish *that* an edge's `salience`
   decreases when it "fires repeatedly without variation" but state no
   mechanism. The architect RESOLVED the trigger shape: a firing counts as
   "without variation" if its retrieval-context embedding is embedding-similar
   to recent firings of the SAME edge (reuse-before-invent — existing embedding
   model). GUARD: habituation adjusts edge `salience` ONLY — never PAD, never
   appraisal (salience is substrate, not feeling). The RATE (decrement amount,
   similarity cutoff, recent-firings window) is DEFERRED — runtime-tuned
   placeholders, `TODO(OQ1-rate)`. See design.md "Open Questions — Architect
   Resolutions" and `register_edge_firing`. Flagged as the item for hardest
   review.

4. **Purpose evidence-check specificity — NOT this module's decision
   (architect 2026-07-05): deferred to Needs System (Module 2).** The Addendum
   flags Purpose as "the weakest, lowest-confidence signal of the four" with no
   structural test for "follows through". The architect ruled this is not
   Memory Graph's call: Memory Graph only answers whatever query Module 2 gives
   it over existing Appraisal_Chain fields; it does not define "follow-through".
   Requirement 11.3's current query is a stand-in over existing fields
   (`TODO(OQ6-M2)`), to be superseded by Module 2's specification. Not invented
   here.

5. **Full Open-Question set + architect resolutions.** Beyond items 3–4 above,
   design.md surfaced and the architect resolved: OQ2 (medium/low
   `base_salience` — DEFERRED placeholders medium 0.35 / low 0.15), OQ3 (node
   embedding storage — RESOLVED: separate `node_embeddings` side-table,
   regenerate on model change), OQ4 (retrieval preference combination —
   RESOLVED: reorder-not-filter, mood-congruence PRIMARY / need SECONDARY, no
   coefficient), OQ5 (precision-decay semantics — RESOLVED: total-elapsed,
   multi-step catch-up), and the max-5-no-evictable case (keep the raise).
   The authoritative, detailed decision record is design.md's "Open Questions —
   Architect Resolutions (2026-07-05)" section; this list is the requirements-
   level summary.

## Build-Time Tuning Constants

None identified specific to this module beyond the already-locked Recency_Window
values (72h/14d/60d) and Precision_Decay thresholds (same three durations),
which are spec-locked values, not open constants. `PAD_HISTORY_LENGTH` (Module
1) and Soul_Tick/DMN_Tick cadences (Module 8) are cross-module build-time
constants that do not originate in this module and are not restated here.


---

## memory-graph — design.md

# Design Document — Module 3: Memory Graph

## Overview

Memory_Graph is Aria's only persistent long-term memory store. It holds four
node types (Event / Entity / Emotion / Uncertainty) and typed edges, and
provides four service surfaces to the rest of the system: (1) write paths for
per-turn appraised events and their uncertainty/edge/emotion consequences, (2)
mood-congruent, need-preferenced retrieval for Appraisal_Chain Stage 1, (3)
qualifying-evidence lookups for Needs_System, Soul_Filter, Appraisal_Chain,
and DMN, and (4) lazy, retrieval-triggered precision decay. It computes
salience floors at node creation and stores — but never itself evaluates —
the `relational_stage` field and the self-continuity narrative.

This design implements `requirements.md` as written, using only mechanisms
already specified there or in the supporting documents
(`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`, `ARIA_Module_Build_Plan.md` Module 3 entry, and the
already-built `daemon/state_manager.py`). No new mechanism, formula, threshold,
or numeric coefficient is introduced. Items that were genuinely undefined across
all source documents were carried as flagged Open Questions and have since been
**resolved by the architect (2026-07-05)** — node embedding storage (OQ3),
precision-decay semantics (OQ5), retrieval-preference combination (OQ4), and the
habituation trigger shape (OQ1) are now documented decisions; the habituation
*magnitudes* (OQ1-rate) and medium/low `base_salience` (OQ2) remain DEFERRED
runtime-tuned placeholders; Purpose evidence specificity (OQ6) is deferred to
Module 2. See "Open Questions — Architect Resolutions" below. Nothing is resolved
by invention (`ARIA_GLM_Covering_Instruction.md` Rule 1).

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`. Two places in this
design rely on that precedence and are called out explicitly: the
salience-resistance check compares against `base_salience` (Resolution Log
item 9) rather than the fluctuating `salience` (v4's Precision Decay table
wording), and the UncertaintyNode max-5 / staleness ownership follows the
Addendum's redefinition of State_Manager (§4) rather than v4's older file
attributions.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. Memory_Graph is the only persistent memory store — no conversation log, no
   vector DB of past chats, no summary file (Req 1.3, Req 13.2;
   `ARIA_GLM_Covering_Instruction.md` Rule 7).
2. Memory_Graph never writes to PAD directly; it informs Appraisal_Chain
   Stage 1, which alone produces a PAD delta at Stage 4 (Req 13.1; v4 Layer 3
   "The graph does not write to PAD directly").
3. Graph data never reaches an LLM directly — only indirectly through
   Appraisal_Chain and Soul_Filter's five-field construction (Req 13.3;
   Rule 5).
4. `base_salience` never decays once set; precision-decay resistance checks
   compare against `base_salience`, never against the fluctuating `salience`
   (Req 5.5, Req 4.4; Resolution Log item 9).
5. `EntityNode.trust_score` does not exist; `relational_stage` (categorical)
   is the sole trust representation, and Memory_Graph stores it but does not
   evaluate its transition gates — DMN does (Req 7.2, 7.5; Addendum §2;
   Resolution Log "Resolved during build-plan review").
6. No numeric coefficient combines retrieval preferences; mood-congruence and
   need-preference are ordering preferences, not weights (Req 6.5; v4 Layer 3
   "No coefficient. The preference is the mechanism.").
7. Only four node types exist; no new node type is introduced for the
   self-continuity narrative (self-referential EntityNode, Req 10.1;
   Resolution Log item 2) or for argument-arc closure (a `"resolved"` edge,
   Req 9.4; Resolution Log item 5).

## Architecture

```
                       ┌───────────────────────────────────────────────┐
                       │                 Memory_Graph                   │
                       │              (graph_manager.py)                │
  Appraisal_Chain ─────┼─▶ write_event_node() ─────┐                    │
   Stage 6             │   create_uncertainty_node()│                   │
  Appraisal_Chain ─────┼─▶ update_uncertainty_status()                  │
   / DMN               │                            ▼                   │
  DMN Step 2 ──────────┼─▶ write_edge() (connection/aha/tension/resolved)│
  DMN Step 2/4 ────────┼─▶ adjust_salience()        │                   │
  DMN Step 1 ──────────┼─▶ crystallize_emotion_node()│                  │
  DMN Step 4 ──────────┼─▶ update_relationship_summary() (any entity,   │
                       │       incl. self-referential EntityNode)       │
  DMN Step 4 ──────────┼─▶ set_relational_stage() (accept only; no gate │
                       │       evaluation here)                         │
                       │                            │                   │
                       │            ┌───────────────▼────────────────┐  │
                       │            │   SQLite store (four node       │  │
                       │            │   tables + edges + embeddings*) │  │
                       │            └───────────────┬────────────────┘  │
                       │                            │                   │
  Appraisal_Chain ─────┼─▶ retrieve(pad_pleasure_sign, need_prefs,      │
   Stage 1             │        entity_refs, query_embedding)           │
                       │        │  (lazy precision-decay eval on        │
                       │        │   each touched node, then top 3–5)    │
                       │        ▼                                       │
                       │   top 3–5 nodes/edges ─────────────────────────┼─▶ Appraisal_Chain S1
                       │                                                │
  Needs_System ────────┼─▶ qualifying-evidence queries ─────────────────┼─▶ need evidence
  Soul_Filter ─────────┼─▶ get_relational_stage() ──────────────────────┼─▶ Relational Register
  Soul_Filter / ───────┼─▶ reality_contradiction_check() ───────────────┼─▶ Honesty / social signal
   Appraisal_Chain     │                                                │
  Appraisal_Chain ─────┼─▶ is_first_of_kind(entity_ref, event_type) ────┼─▶ poignancy Critical input
  DMN ─────────────────┼─▶ resolved_edge_exists(entity_ref, window) ────┼─▶ Invested→Bonded input
                       │                                                │
                       │   depends on: Embedding_Model (injected),      │
                       │   Daemon (no decay tick needed — decay is lazy)│
                       └───────────────────────────────────────────────┘
   * "embeddings" table is an architect-DECIDED side-table — see OQ3 (Resolved).
```

Memory_Graph exposes write methods (used by Appraisal_Chain and DMN), a single
retrieval method (used by Appraisal_Chain Stage 1), and a set of
read-only/structural query methods (used by Needs_System, Soul_Filter,
Appraisal_Chain, DMN). It has no method that mutates PAD, and no method that
returns data to an LLM.

Note on the decay tick: the Build Plan's Module 3 "Inputs" list includes a
"Precision-decay tick — from Daemon / DMN." Resolution Log item 8 supersedes
this: precision decay is **lazy and retrieval-triggered**, so no periodic
decay-tick input is consumed. The Daemon dependency is retained in name only
(the daemon orchestrates process lifecycle and may drive DMN passes that
retrieve nodes), but Memory_Graph does not implement a `on_decay_tick()`
entry point. This is called out in Open Question 5 of `requirements.md`'s
lineage (F-3b, resolved) and re-stated here so the absence of a tick handler
is understood as deliberate, not an omission.

## Storage Backend and Persistence

The backend is **SQLite**, named directly in v4 ("Unlimited (SQLite,
Phase 3+)", Context Window vs. Graph table) and implemented in
`graph_manager.py` (v4 Key Technical Constants table attributes every graph
mechanism — the +0.15 bonus, poignancy conditions, precision-decay times,
salience-resistance thresholds, the 3× argument-buffer weight — to
`graph_manager.py`). No other backend is introduced. SQLite satisfies the
"persists across sessions" and "unlimited" requirements without a second store
(Rule 7).

Proposed table layout (implementation detail, not new scope — a faithful
relational encoding of v4 Layer 3's locked schema):

- `event_nodes`, `entity_nodes`, `emotion_nodes`, `uncertainty_nodes` — one
  table per node type, columns matching that type's v4 field list verbatim
  (field names and types as in v4 Layer 3's "Formal Node Schema").
  `entity_nodes` **omits** `trust_score` and **includes** `relational_stage`
  (Addendum §2).
- `edges` — columns matching v4's Edge Schema verbatim (`edge_id`, `from_node`,
  `to_node`, `edge_type`, `valence`, `arousal`, `dominance`, `base_salience`,
  `salience`, `firing_count`, `perspective`, `created`, `last_activated`,
  `is_tension_pair`, `tension_partner_edge`, `is_aha_edge`).
- `node_embeddings` — **architect-DECIDED (OQ3 Resolved): a separate side-table
  keyed by node_id.** v4's node schema has no embedding field, yet similarity
  retrieval (v4 Layer 3; Addendum §1) and the REALITY_CONTRADICTION comparison
  require embeddings. The separate `node_embeddings(node_id, embedding)` table
  keeps the locked logical node schema pure; it is regenerated if the embedding
  model changes.

`aria_state.json` and `self_model.json` remain State_Manager's (Module 11)
working-state files and are **not** touched by Memory_Graph. In particular,
`relationship_depth` is neither read nor written (Req 7.6; already dropped in
`daemon/state_manager.py`'s `_SUPERSEDED_KEYS`). The self-continuity narrative
lives in the self-referential EntityNode's `relationship_summary` column in
SQLite, not in `self_model.json` (Resolution Log item 2).

## Data Types

Dataclasses mirror v4 Layer 3's locked field lists exactly. Enumerations use
the exact string domains v4 specifies. No field is added to or removed from the
locked schema except the two the Addendum mandates (`trust_score` removed,
`relational_stage` added on EntityNode) and the architect-decided out-of-band
embedding side-table (OQ3 Resolved), which is not a field on the node dataclasses.

```python
class NodeType(Enum):
    EVENT = "event"
    ENTITY = "entity"
    EMOTION = "emotion"
    UNCERTAINTY = "uncertainty"

class Precision(Enum):          # v4 Layer 3 decay path
    VIVID = "vivid"
    PRESENT = "present"
    SOFTENED = "softened"
    FADED = "faded"

class PoignancyCategory(Enum):  # v4 Poignancy table
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Perspective(Enum):        # v4 Layer 3
    I_NOW = "I-Now"
    USER_NOW = "User-Now"
    WE = "We"

class RelationalStage(Enum):    # Addendum §2 — replaces trust_score
    OBSERVING = "observing"
    ENGAGING = "engaging"
    INVESTED = "invested"
    BONDED = "bonded"

class UncertaintyType(Enum):    # v4 Layer 1 / Layer 3
    INPUT_UNCERTAIN = "INPUT_UNCERTAIN"
    VALENCE_UNCERTAIN = "VALENCE_UNCERTAIN"
    CAUSAL_UNCERTAIN = "CAUSAL_UNCERTAIN"
    GRAPH_CONFLICT = "GRAPH_CONFLICT"

class UncertaintyStatus(Enum):  # v4 Layer 3
    ACTIVE = "ACTIVE"
    RESOLVED_CONFIRMED = "RESOLVED_CONFIRMED"
    RESOLVED_INFERRED = "RESOLVED_INFERRED"
    ABANDONED = "ABANDONED"

# EdgeType is the 7-value domain from v4's Edge Schema.
class EdgeType(Enum):
    TRIGGERED = "triggered"
    CAUSED = "caused"
    RELATES_TO = "relates_to"
    RESOLVED = "resolved"       # arc closure, 3× salience (Resolution Log item 5)
    CONTRADICTS = "contradicts"
    CONNECTS = "connects"
    CRYSTALLIZED_INTO = "crystallized_into"
```

`EventNode`, `EntityNode`, `EmotionNode`, `UncertaintyNode`, and `Edge`
dataclasses carry exactly the fields v4 Layer 3 lists for each (transcribed in
`requirements.md`'s Glossary). They are **not** frozen: unlike Module 1's
PADSnapshot, several fields (`salience`, `precision`, `last_accessed`,
`access_count`, `relational_stage`, `relationship_summary`, uncertainty
`status`) are legitimately mutable over a node's lifetime. Mutation is confined
to Memory_Graph's own methods; no returned object aliases live storage (reads
return detached copies — see Boundary Enforcement).

## Components and Interfaces

### MemoryGraph (class, `graph_manager.py`)

Constructed with a SQLite connection/path and an injected `Embedding_Model`
(see Embedding Dependency). Owns all reads and writes to the graph.

**Write methods (Appraisal_Chain / DMN facing):**

- `write_event_node(fields...) -> node_id` — Req 2.1, 2.2, 2.3. Creates an
  EventNode from Appraisal_Chain Stage 6 output. Accepts `is_partial_appraisal
  = True` via the same path (Req 2.2). Computes `base_salience` from
  `poignancy_category` and `appraisal_q2` **before** any other salience
  process (Req 2.3, Req 5 — see Salience Design). Sets initial `precision =
  "vivid"` (a newly-encoded memory is full-detail, v4 Layer 3) and
  `last_accessed = timestamp` / `access_count = 0`. If the caller supplies a
  `description` embedding (or one is computed — Open Question 3), it is stored
  in `node_embeddings`.
- `create_uncertainty_node(fields...) -> node_id` — Req 3.1. Stores with
  `status = ACTIVE`. Enforces the max-5 capacity limit at this point (Req 3.4
  — see UncertaintyNode Lifecycle). Sets `is_protected = True` for
  INPUT_UNCERTAIN and VALENCE_UNCERTAIN.
- `update_uncertainty_status(node_id, status, resolution_path, catch_up_*)` —
  Req 3.2. Accepts resolution/abandonment writes (including DMN's
  staleness-driven ABANDONED write, Req 3.3). Stores the `catch_up_delta_*` /
  `catch_up_magnitude_factor` fields as data — it does **not** apply any PAD
  shift (that is a secondary appraisal via Appraisal_Chain; Req 13.1).
- `write_edge(from_node, to_node, edge_type, ...) -> edge_id` — Req 9.1, 9.3,
  9.4. Accepts connection/aha edges (`is_aha_edge`), tension-pair edges
  (`is_tension_pair` / `tension_partner_edge`), and `"resolved"` arc-closure
  edges. For `edge_type = "resolved"`, applies the 3× salience weighting at
  creation (Req 9.4; see Argument Buffer Design).
- `adjust_salience(node_or_edge_id, new_salience)` — Req 9.2. Applies DMN
  salience raises/lowers to the fluctuating `salience` field only; never
  touches `base_salience`.
- `crystallize_emotion_node(fields...) -> node_id` — Req 8.1, 8.2. Accepts an
  EmotionNode write **only** when `poignancy_category == "critical"` (rejects
  otherwise — see Error Handling).
- `update_relationship_summary(entity_node_id, text)` — Req 10.2. One path for
  every entity, including the self-referential EntityNode (Req 10.1). No
  special-case branch for the self node.
- `set_relational_stage(entity_node_id, stage)` — Req 7.4. Accepts and persists
  a DMN-decided stage transition (advance or one-step regression). Does **not**
  evaluate whether a gate was met (Req 7.5) — it is a setter, not an evaluator.

**Retrieval method (Appraisal_Chain Stage 1 facing):**

- `retrieve(pad_pleasure_sign, need_prefs, entity_refs, query_embedding)
  -> list[Node|Edge]` — Req 6.1–6.5. Returns the top 3–5 relevant results,
  applying mood-congruence and need-preference as ordering preferences (no
  coefficient). Lazily evaluates precision decay on each node it touches, then
  updates `last_accessed`/`access_count` (see Retrieval Design and Precision
  Decay Design). The exact preference-combination order is flagged (Open
  Question 4).

**Structural / qualifying-evidence query methods:**

- `get_relational_stage(entity_node_id) -> RelationalStage` — Req 7.3
  (Soul_Filter).
- `connection_evidence(window=72h)`, `growth_evidence(window=14d)`,
  `purpose_evidence(window=14d)`, `continuity_evidence(window=60d)` — Req 11.1–
  11.4 (Needs_System). Each returns whether qualifying evidence exists in the
  window; Memory_Graph does not compute the resulting need *state* (Req 11.5).
- `is_first_of_kind(entity_ref, event_type) -> bool` — Req 12.1
  (Appraisal_Chain poignancy Critical input).
- `reality_contradiction_check(entity_ref, candidate_text, window) -> bool` —
  Req 12.2 (Soul_Filter Honesty, Appraisal_Chain social pre-pass). Structural
  compare only; does not decide meaning (Req 12.4).
- `resolved_edge_exists(entity_ref, window) -> bool` — Req 12.3 (DMN
  Invested→Bonded input).

No method accepts a PAD-mutation request, a Needs-pressure value as a PAD
input, an F4/barge-in signal, or an LLM handle. This absence is the structural
enforcement of Req 13 (see Boundary Enforcement).

## Salience Design

Salience has two fields per node/edge (v4 Layer 3): `base_salience` (set at
creation, never decays) and `salience` (fluctuates via habituation and DMN
adjustment). At EventNode creation, `base_salience` is computed as:

```
base_salience = poignancy_floor(poignancy_category) + (0.15 if appraisal_q2 == "negative" else 0.0)
```

where `poignancy_floor` is (Resolution Log item 9):

- `critical` → 0.85
- `high` → 0.55
- `medium` → 0.35 · `low` → 0.15 — DEFERRED architect placeholders (OQ2)

The +0.15 negative-event bonus (v4 Layer 3, Baumeister encoding asymmetry)
stacks on top of whichever floor/placeholder applies (Resolution Log item 9:
"stacks on top of whichever floor"). `base_salience` is then frozen for the
node's lifetime (Req 5.5).

**The medium/low placeholders (OQ2 — DEFERRED):** critical/high take the
spec-locked floor (0.85 / 0.55). Medium/low have no source-defined floor
(poignancy is explicitly "not a weighted formula", v4), so the architect set
DEFERRED PLACEHOLDER magnitudes — **medium 0.35, low 0.15** — chosen only to be
ordered and both below the 0.55 high floor; real values are tuned at runtime
(`TODO(OQ2)`). Poignancy itself stays categorical; only its substrate salience
gets these placeholder numbers. The initial `salience` field is set equal to
`base_salience` at creation for all tiers (a node's current salience at creation
equals its encoding salience).

## Precision Decay Design

Precision decay is **lazy and retrieval-triggered** (Resolution Log item 8:
"not a continuous background timer... checked against the resistance thresholds
at the moment Stage 1 or DMN retrieves it; precision updates then, not on a
sweep"). There is no background clock and no `on_decay_tick()` method.

On each retrieval that touches a node, in this order:

1. **Evaluate decay** using the node's *current* `last_accessed` (i.e. the
   value from the previous access, before this one). Compute `elapsed = now -
   last_accessed`.
2. **Advance precision** along `vivid → present → softened → faded`, applying
   each transition whose time threshold `elapsed` has exceeded, stopping at the
   first transition blocked by `base_salience` resistance, or at `faded`
   (terminal). Time thresholds (v4 Precision Decay Rates): `vivid→present` ~72h,
   `present→softened` ~14d, `softened→faded` ~60d. Resistance (v4 table wording
   is "salience", **corrected to `base_salience` by Resolution Log item 9** —
   precedence): `vivid→present` blocked if `base_salience > 0.8`;
   `present→softened` blocked if `base_salience > 0.5`; `softened→faded` blocked
   if `base_salience > 0.3`.
3. **Reset the timer**: set `last_accessed = now`, increment `access_count`
   (Req 4.6). This is why repeated retrieval "resets the decay timer" (v4) — a
   frequently-retrieved node never accumulates enough `elapsed` to advance.
4. A `faded` node is never deleted (Req 4.5); `faded` is terminal.

This yields the coherent lifetimes Resolution Log item 9 describes: a critical
node (`base_salience` 0.85 > 0.8) never leaves `vivid`; a high node
(`base_salience` 0.55, between 0.5 and 0.8) can go `vivid→present` (0.55 is not
> 0.8) but resists `present→softened` (0.55 > 0.5), settling at `present`
("~72h to soften from exact wording, then holds"); medium/low nodes with low
`base_salience` decay fully.

**Multi-step catch-up (design interpretation, flagged — Open Question 5):**
**Multi-step catch-up (OQ5 — RESOLVED, architect):** because decay is lazy, a
node untouched for, say, 65 days is only re-evaluated when next retrieved, at
which point `elapsed` (65d) exceeds the `vivid→present` (72h), `present→softened`
(14d), and `softened→faded` (60d) thresholds — so it advances multiple steps in
one evaluation. The architect resolved that the three time thresholds are
**total-elapsed-since-`last_accessed` checkpoints** on a single axis (NOT
per-stage dwell): a memory nothing has touched in 60 days is `faded` now; it
need not have "dwelt" in intermediate states unobserved. The design advances
through all crossed, non-resisted transitions in one pass.

## Retrieval Design

Retrieval must return the "top 3–5 most relevant nodes" (v4 Layer 3),
"weighted by mood-congruence", where mood-congruence is a **preference, not a
coefficient** ("No coefficient. The preference is the mechanism.", v4), and
must additionally honor need-preference ("When Connection is neglected, Stage 1
surfaces 'We'-perspective and Connection-positive edges first", Addendum §3).

Inputs (Build Plan Module 3): `pad_pleasure_sign`, `need_prefs`, `entity_refs`,
`query_embedding`. The query is pre-embedded by the caller (Appraisal_Chain's
Stage 1 pre-pass owns the embedding model use for the incoming turn); Memory_
Graph compares it against stored node embeddings (Open Question 3).

The design applies, without any numeric score:

1. **Candidate selection** by semantic similarity between `query_embedding` and
   stored node embeddings (cosine similarity is the standard metric for
   sentence embeddings; the "top 3–5" range is v4-stated), optionally
   constrained/boosted by `entity_refs` (nodes whose `entity_refs`/`entity_ref`
   match are clearly relevant candidates).
2. **Mood-congruence preference**: among candidates, edges/nodes whose
   `valence` sign matches `pad_pleasure_sign` are surfaced first (Req 6.2).
3. **Need-preference**: when `need_prefs` marks a need due/neglected,
   need-relevant candidates (e.g. "We"-perspective and Connection-positive
   edges for Connection) are surfaced first (Req 6.3).

**Preference combination (OQ4 — RESOLVED, architect):** with "no coefficient",
the three inputs cannot be combined into a weighted score — they are applied as
ordering preferences (reorder, not filter). The architect resolved the
precedence: **mood-congruence PRIMARY, need-preference SECONDARY**, over the
similarity-generated candidate set. Similarity gathers candidates; her current
mood surfaces congruent ones first; need breaks the remaining ties.
Implementation: stable sorts, need applied first then mood applied last, so mood
dominates. NO `similarity*w1 + valence*w2 + need*w3` — pure ordering. ("The
preference IS the mechanism", v4; need-preference as a secondary context-shaper,
Addendum §3.) ⚠️ This flips the design's earlier *provisional* need-primary
choice to mood-primary — see Open Questions for the explicit change note.

## UncertaintyNode Lifecycle Design

- **Creation & the max-5 cap (Req 3.4):** on `create_uncertainty_node`, if 5
  ACTIVE UncertaintyNodes already exist, force-resolve the oldest
  `GRAPH_CONFLICT`-type ACTIVE node to `ABANDONED` before creating the 6th.
  INPUT_UNCERTAIN and VALENCE_UNCERTAIN are `is_protected` and are never
  force-abandoned (Req 3.5; v4 Layer 3). If no `GRAPH_CONFLICT` node exists to
  evict, see Error Handling. This cap is enforced here, at creation, because
  node creation is Memory_Graph's own operation — v4's attribution of the max-5
  to `state_manager.py` predates the Addendum §4 redefinition of State_Manager
  as meaning-free plumbing (precedence: Addendum > v4).
- **Resolution (Req 3.2):** `update_uncertainty_status` accepts
  RESOLVED_CONFIRMED (direct information), RESOLVED_INFERRED (behavioral
  inference or DMN consolidation), storing `resolved` timestamp,
  `resolution_path`, and the catch-up fields. The catch-up magnitude factors
  (0.50 / 0.25, v4 Resolution Conditions table) are stored as data; the actual
  PAD catch-up shift is applied elsewhere via secondary appraisal, never by
  Memory_Graph (Req 13.1).
- **Staleness (Req 3.3):** Memory_Graph stores/exposes `interaction_count`
  (incremented via Appraisal_Chain's writes — Resolution Log item 10) and
  `created`, but does **not** evaluate the "7 days or 50 interactions"
  threshold. DMN Step 3 evaluates staleness (v4 Key Technical Constants:
  `dmn_manager.py`) and writes the resulting `ABANDONED` /
  `resolution_path = "staleness"`, which Memory_Graph accepts via
  `update_uncertainty_status`. This mirrors the `relational_stage` boundary:
  Memory_Graph stores, DMN evaluates.

## relational_stage Design

`relational_stage` is a categorical column on `entity_nodes`
(`observing`/`engaging`/`invested`/`bonded`), replacing the removed
`trust_score` (Addendum §2). Memory_Graph:

- exposes it via `get_relational_stage()` to Soul_Filter (Req 7.3),
- accepts DMN-decided transitions via `set_relational_stage()` (Req 7.4),
  including one-step regressions (never below `observing`) triggered by a
  REALITY_CONTRADICTION rupture,
- **never evaluates** the transition gates — predictability / dependability /
  faith advancement and regression are DMN Step 4's batched idle evaluation
  (Req 7.5; Resolution Log "Resolved during build-plan review"). Memory_Graph
  provides the raw evidence DMN needs (`resolved_edge_exists`,
  `is_first_of_kind`, edge/perspective queries) but makes no stage decision,
- never reads or writes `aria_state.json.relationship_depth` (Req 7.6; already
  dropped in `state_manager.py`).

## Self-Referential EntityNode Design

Aria's own self-continuity narrative is stored in the `relationship_summary`
column of a normal EntityNode representing Aria herself (Resolution Log item 2:
"Aria gets a self-referential EntityNode; the narrative lives in that node's
existing `relationship_summary` field... No new node type, no new DMN
mechanism"). `update_relationship_summary()` is the single write path for both
this node and every other entity — there is no self-model-specific method,
table, or node type. DMN Step 4 writes it under the same "appeared more than
once" gate it uses for any narrative update (Req 10.2). Memory_Graph does not
gate or interpret the narrative content (the moral-schema gate on narrative
updates is DMN's, Addendum §8).

## Argument Buffer / Resolved-Edge Design

Arc closure creates **no new node type** (Resolution Log item 5: the single
"Argument Buffer node" language "describes the effect, not new schema"). When
the conflict-arc state machine (Addendum §1, owned by Appraisal_Chain's Stage 1
pre-pass) reports closure, `write_edge` is called with `edge_type = "resolved"`,
directed from the closing EventNode to the opening EventNode, and Memory_Graph
weights its salience 3× at creation (Req 9.4; v4 Key Technical Constants:
"Argument buffer resolution weight | 3× | graph_manager.py"; Resolution Log
item 5). The existence of such an edge on an `entity_ref` within a window is the
signal DMN queries for the Invested→Bonded gate (`resolved_edge_exists`, Req
12.3).

## Embedding Dependency

Memory_Graph depends on the shared local sentence-embedding model (encoder-only,
non-generative, tens of MB — Addendum §1; Rule 6), injected at construction as
an interface, not instantiated internally and not hardcoded to a specific model
(mirroring how Module 1 injects no model and how the Addendum treats "one model
serves both" Appraisal_Chain and Memory_Graph). It is used for:

- similarity ranking in `retrieve()` (comparing `query_embedding` to stored
  node embeddings), and
- the `reality_contradiction_check()` comparison of two same-entity EventNode
  descriptions ("using the same embedding model plus basic negation detection",
  Addendum §1).

The VULNERABILITY_DISCLOSURE similarity cutoff, the REALITY_CONTRADICTION
comparison-window duration, and the exact negation-detection criterion are
**build-time tuning constants**, not architectural gaps (Addendum "Open —
build-time tuning constants only" lists the cutoff and window duration
explicitly). They are carried as placeholder constants, exactly as Module 1
carried `PAD_HISTORY_LENGTH`.

## Boundary Enforcement (Req 13)

- **No direct PAD writes (Req 13.1):** Memory_Graph holds no reference to
  PAD_Engine's mutators and exposes no PAD-writing method. Enforcement is
  structural (absent surface), the same pattern Module 1 uses for its rejection
  paths — not a runtime check.
- **No second memory store (Req 13.2):** the SQLite graph is the only
  persistent store Memory_Graph creates or requires. No conversation log,
  vector-DB-of-chats, or summary file is introduced. (The `node_embeddings`
  side-table, architect-decided per OQ3, is an index over graph nodes, not a
  second *memory* — it holds derived vectors keyed by `node_id`, not
  independent chat content.)
- **No LLM exposure (Req 13.3):** retrieval and query methods return graph data
  to Appraisal_Chain / Soul_Filter / Needs_System / DMN only. No method takes an
  LLM handle or returns data formatted for an LLM. Graph content reaches the LLM
  only after Appraisal_Chain and Soul_Filter reduce it to the five fields
  (Rule 5).
- **Reads return detached copies:** query/retrieval methods return dataclass
  copies (or immutable views), so a consumer cannot mutate live graph state
  through a returned reference (parallels Module 1's `get_pad_history()`
  immutable-return rule).

## Error Handling

- **EmotionNode write with non-critical poignancy:** `crystallize_emotion_node`
  raises `ValueError` if `poignancy_category != "critical"` (Req 8.1 — only
  critical states crystallize; a non-critical write is a caller contract
  violation, not silently coerced).
- **max-5 with no GRAPH_CONFLICT node to evict:** if 5 ACTIVE UncertaintyNodes
  exist and none is `GRAPH_CONFLICT` (all are protected INPUT/VALENCE_UNCERTAIN,
  or CAUSAL_UNCERTAIN), v4 specifies only that the oldest `GRAPH_CONFLICT` is
  evicted and that INPUT/VALENCE_UNCERTAIN are protected — it does **not**
  specify what happens when the cap is hit with no evictable node. This is
  **flagged (Open Question 6)**: the design does not invent an eviction of a
  CAUSAL_UNCERTAIN or a protected node, nor silently drop the new node; it
  raises so the condition is visible pending architect decision.
- **Retrieval / query before initialization:** methods raise `RuntimeError` if
  called before the SQLite store and embedding model are wired (parallels
  Module 1's pre-`initialize()` guard).
- **Corrupt/missing embedding for a node:** a node lacking a stored embedding is
  excluded from similarity ranking (it can still be returned via entity_ref
  match or other queries) rather than crashing retrieval; this follows the
  "faded nodes are never deleted, only lose precision" spirit — a node without
  an embedding is degraded, not fatal. (Depends on Open Question 3's
  resolution.)
- **Invalid node/edge writes** (missing required field, unknown enum value):
  raise `ValueError` at the write boundary rather than persisting a malformed
  row.

## Testing Strategy

Property-based tests for the numeric/ordering logic; example-based tests for
schema round-trips, boundary guarantees, and the flagged/raising paths.

**Property-based tests:**

1. *Salience floor* — for any EventNode created with `poignancy_category ==
   critical`, `base_salience >= 0.85`; with `high`, `>= 0.55`; and the +0.15
   negative bonus is added iff `appraisal_q2 == "negative"`, stacking on the
   floor. (Req 5.1–5.4.) Medium/low base_salience is **not** asserted to any
   value — see Open Question 2; the test asserts only that no floor is applied,
   not a specific number.
2. *base_salience never decays* — after any sequence of `adjust_salience` calls
   and retrievals, `base_salience` is unchanged from creation. (Req 5.5.)
3. *Precision decay monotonicity & resistance* — for any node, precision only
   advances along `vivid→present→softened→faded` (never regresses), never
   deletes, and never advances past a transition its `base_salience` resists
   (0.8 / 0.5 / 0.3 checked against `base_salience`, not `salience`). Includes
   the boundary cases: `base_salience` 0.85 never leaves `vivid`; 0.55 settles
   at `present`. (Req 4.1, 4.4, 4.5.)
4. *Decay timer reset* — a node retrieved more frequently than the 72h threshold
   never advances past `vivid`. (Req 4.6.)
5. *Retrieval size* — `retrieve()` returns at most 5 results. (Req 6.1.)
6. *Mood-congruence ordering* — for a candidate set with mixed valence signs and
   a given `pad_pleasure_sign`, sign-matching results are ordered ahead of
   non-matching ones. (Req 6.2.) *(This test encodes the reorder-not-filter and
   provisional-precedence choices from Open Question 4; it must be revisited if
   the architect resolves that ordering differently.)*
7. *Uncertainty cap* — creating a 6th ACTIVE UncertaintyNode when a
   `GRAPH_CONFLICT` node exists force-abandons the oldest `GRAPH_CONFLICT` and
   never a protected INPUT/VALENCE_UNCERTAIN node; active count stays ≤ 5.
   (Req 3.4, 3.5.)

**Example-based / integration tests:**

8. Node/edge SQLite round-trip preserves every v4-schema field exactly for each
   of the four node types and edges. (Req 1.1, 1.2, 1.4.)
9. `entity_nodes` has no `trust_score` column and has a `relational_stage`
   column; a static/schema check. (Req 7.1, 7.2.)
10. `EmotionNode` write rejects non-critical poignancy with `ValueError`.
    (Req 8.1.)
11. `"resolved"` edge is created closing→opening with 3× the salience of an
    otherwise-equivalent non-resolved edge. (Req 9.4.)
12. Self-referential EntityNode narrative round-trips through
    `update_relationship_summary` using the same path as any other entity — no
    special method exists. (Req 10.1, 10.2.)
13. Each qualifying-evidence query (`connection_evidence` 72h,
    `growth_evidence` 14d, `purpose_evidence` 14d, `continuity_evidence` 60d,
    `is_first_of_kind`, `resolved_edge_exists`, `reality_contradiction_check`)
    returns the correct structural result on a seeded graph, and none of them
    computes a need *state* or a trust decision. (Req 11.*, 12.*.)
14. `set_relational_stage` accepts a DMN-supplied transition but MemoryGraph
    exposes no gate-evaluation method — API-surface check. (Req 7.4, 7.5.)
15. Staleness: MemoryGraph does not auto-abandon on `interaction_count >= 50` or
    age ≥ 7d; a node stays ACTIVE until an explicit `update_uncertainty_status`
    (standing in for DMN) writes ABANDONED. (Req 3.3.)
16. Boundary: MemoryGraph exposes no PAD-mutating method, no method taking an
    LLM handle, and no method taking a Needs-pressure/F4/barge-in PAD input —
    API-surface check. (Req 13.1, 13.3.)
17. `relationship_depth` is never read or written by MemoryGraph — a check that
    no code path references that key. (Req 7.6.)

**Not tested to an exact value (DEFERRED placeholders only):** medium/low
`base_salience` magnitudes (OQ2 — tests assert ordering + below-floor + stacking
properties, not the exact 0.35/0.15) and the habituation decrement/cutoff/window
(OQ1-rate — tests assert habituation *fires and lowers salience*, not the exact
amount). These are runtime-tuned placeholders, so tests pin the architect's
stated *properties*, not the tunable magnitudes. The RESOLVED items (OQ3, OQ4
mood-primary precedence, OQ5 total-elapsed, OQ1 trigger-shape) ARE tested for
their decided behavior.

## Open Questions — Architect Resolutions (2026-07-05)

The architect resolved these as ARIA's system architect (not as gap-filling).
Governing frame: PAD/relational_stage/poignancy/need-states change ONLY through
appraisal and categorical logic — never a formula or invented coefficient. The
sanctioned numbers (PAD, Energy, salience, spec-locked thresholds) are
SUBSTRATE (memory/attention plumbing); they may exist and be adjusted but are
NEVER wired to directly compute a feeling. Protected chain: memory mechanics
(salience, may be numeric) → retrieval ORDERING (preference, never a weighted
score) → appraisal (categorical meaning) → PAD (feeling). Deciding lens: the
percentage test — if "what percent of the way there?" is meaningful, it's a
number in disguise; a real category "either holds or it doesn't."

### RESOLVED — structural (implemented, TODO removed)

- **OQ3 — Node embedding storage.** DECISION: persist embeddings in a SEPARATE
  `node_embeddings` side-table keyed by node_id; do NOT add an embedding field
  to v4's locked node schema; regenerate the table if the embedding model
  changes. RATIONALE: reuses the one shared embedding model (Addendum §1),
  leaves the locked schema pure; pure plumbing, touches no feeling. (Confirms
  the design's earlier provisional side-table choice.)
- **OQ5 — Precision-decay semantics.** DECISION: total-elapsed-since-
  `last_accessed` (multi-step catch-up in one lazy evaluation), NOT per-stage
  dwell. RATIONALE: matches lazy, retrieval-triggered decay (Resolution Log
  item 8) and human forgetting — a memory nothing has touched in 60 days is
  `faded` now; it need not have "dwelt" in intermediate states unobserved.
  precision stays categorical; the durations are spec-locked. (Confirms the
  design's earlier adopted reading.)

### RESOLVED — judgment calls (implemented; flagged for hardest review)

- **OQ4 — Retrieval preference combination (flagship of the philosophy).**
  DECISION: reorder-not-filter over a similarity-generated candidate set, with
  MOOD-CONGRUENCE **PRIMARY** and NEED-PREFERENCE **SECONDARY**. Pure ordering —
  NO coefficient, NO weighted score, NO `similarity*w1 + valence*w2 + need*w3`.
  Similarity gathers candidates; her current mood surfaces congruent ones first;
  need breaks remaining ties. RATIONALE: v4 grounds mood-congruent recall as how
  human memory works ("the preference IS the mechanism"); Addendum §3 makes
  need-preference a secondary context-shaper. This is how her feeling shapes
  what she remembers — by preference, never by arithmetic.
  ⚠️ **CHANGE FROM PRIOR DESIGN:** the earlier *provisional* implementation made
  **need** primary (need-sort applied last on a stable sort). This is now
  flipped to **mood primary** per the architect (need-sort applied first, mood
  last). Reported explicitly rather than silently overridden.
- **OQ1 (trigger shape) — Habituation "without variation".** DECISION: a firing
  counts as "without variation" if its retrieval-context embedding is
  embedding-similar to recent firings of the SAME edge (`register_edge_firing`).
  RATIONALE: reuse-before-invent (existing embedding model, no new subsystem).
  ⚠️ **GUARD (hardest-review item):** habituation adjusts edge `salience` ONLY —
  it must NEVER produce a PAD change or feed appraisal directly; it only makes a
  worn-smooth, repetitive memory surface less readily.

### DEFERRED — explicit placeholder + TODO (do NOT finalize)

- **OQ1 (rate) — Habituation magnitudes.** PLACEHOLDER, tune at runtime: the
  salience decrement, the similarity cutoff, and the recent-firings window are
  `TODO(OQ1-rate)` constants. salience is sanctioned substrate so a numeric
  decrement is allowed, but the amount cannot be chosen well before watching her
  behave.
- **OQ2 — Medium/low initial `base_salience`.** PLACEHOLDER (ordered, both below
  the 0.55 high floor): medium 0.35, low 0.15, `TODO(OQ2)`. The +0.15 negative
  bonus stacks on the placeholder. Poignancy itself stays categorical
  (critical/high/medium/low) — only its substrate salience gets a placeholder
  number. Real values tuned at runtime.

### NOT THIS MODULE'S DECISION (leave as-is)

- **OQ6 — Purpose evidence specificity.** Defer to Needs System (Module 2).
  Memory Graph only answers whatever query it is given over existing
  Appraisal_Chain fields; it does not define "follow-through". Marked
  `TODO(OQ6-M2)`.
- **Max-5-UncertaintyNode eviction with no evictable GRAPH_CONFLICT.** Keep the
  design's "raise rather than silently mishandle" stub. Do NOT implement an
  eviction-of-protected-node policy. NOTE for later (flag, don't implement): the
  human-like resolution may be that a new uncertainty simply does not FORM when
  she is already at her limit — a real cognitive ceiling — rather than raising.

## Known Limitations

- **Concurrency / transaction model.** The soul-tick and DMN run on separate
  clocks (v4), so retrieval, writes, and DMN passes can interleave. This design
  assumes single-process access serialized through one SQLite connection with
  transactions; it does not design a multi-writer locking protocol, because no
  source document specifies concurrent-access semantics and the Daemon (Module
  8) orchestrates when DMN vs. live turns run. If Module 8 introduces true
  concurrent graph access, the transaction model must be revisited.
- **Embedding-model version stability.** Stored node embeddings (the OQ3-decided
  side-table) are only comparable if produced by the same embedding model.
  Per the architect's OQ3 decision, the `node_embeddings` table is REGENERATED
  if the embedding model changes. This is an operational/build concern, noted so
  it is not
  discovered late.
- **No decay-tick entry point.** Because decay is lazy (Resolution Log item 8),
  a node that is written and then never retrieved never advances in precision —
  which is correct per the spec (decay is "time without *re-activation*", and an
  unretrieved node's precision is only observed when it is next retrieved), but
  means precision is a lazily-materialized property, not a continuously-accurate
  one. Consumers must not assume a node's stored `precision` reflects wall-clock
  elapsed time until it has been retrieved at least once since that time passed.


---

## memory-graph — tasks.md

# Implementation Plan — Module 3: Memory Graph

This plan implements design.md exactly as written. Each task is small and
independently testable. It targets `graph_manager.py` (v4 Key Technical
Constants table's named file for every graph mechanism).

## Quoted from design.md (verified against current file content)

**The four node types and edge type domain** (Data Types section) — exactly
v4 Layer 3's locked schema, with the two Addendum §2 changes (EntityNode
`trust_score` removed, `relational_stage` added) and no others:
```
NodeType: event / entity / emotion / uncertainty
EdgeType: triggered / caused / relates_to / resolved / contradicts /
          connects / crystallized_into
RelationalStage: observing / engaging / invested / bonded   (replaces trust_score)
```

**base_salience computation at EventNode creation** (Salience Design):
```
base_salience = poignancy_floor(poignancy_category) + (0.15 if appraisal_q2 == "negative" else 0)
poignancy_floor: critical → 0.85 · high → 0.55 · medium → 0.35 · low → 0.15
                 (medium/low are DEFERRED architect placeholders — TODO(OQ2))
```
`base_salience` never decays (Req 5.5); the +0.15 stacks on the floor/placeholder
(Resolution Log item 9).

**Precision decay** (Precision Decay Design) — lazy, retrieval-triggered
(Resolution Log item 8); **no `on_decay_tick()` method exists**. On each
retrieval touch, in order: (1) evaluate decay from the node's *previous*
`last_accessed`; (2) advance `vivid→present→softened→faded` through every
transition whose time threshold (~72h / ~14d / ~60d) is exceeded, stopping at
the first blocked by `base_salience` resistance (> 0.8 / > 0.5 / > 0.3 —
checked against **`base_salience`**, per Resolution Log item 9, **not** the
fluctuating `salience` that v4's table wording says); (3) reset
`last_accessed = now`, increment `access_count`; (4) `faded` is terminal, never
deleted.

**The three retrieval preferences do NOT combine via any coefficient**
(Retrieval Design; v4 "No coefficient. The preference is the mechanism.").
Similarity selects candidates; mood-congruence (valence-sign match to
`pad_pleasure_sign`) and need-preference reorder them. Precedence is
architect-RESOLVED (OQ4): **mood-congruence PRIMARY, need-preference SECONDARY**,
reorder-not-filter, over the similarity candidate set. NO coefficient/score.
(Implementation: stable sorts — need applied first, mood applied last so mood
dominates.)

**Ownership boundaries this plan must preserve:**
- Staleness (7d / 50 interactions → ABANDONED) is **DMN's** evaluation
  (`dmn_manager.py`); Memory_Graph stores `interaction_count`/`created` and
  *accepts* the ABANDONED write. The max-5 cap is **Memory_Graph's**, enforced
  at creation. (Req 3.3 vs 3.4.)
- `relational_stage` transitions are **DMN's** evaluation; Memory_Graph stores
  the field and *accepts* the write — no gate logic here. (Req 7.5.)
- catch-up PAD shift on uncertainty resolution is applied **elsewhere** (secondary
  appraisal); Memory_Graph only stores the `catch_up_*` fields. (Req 13.1.)
- The self-continuity narrative is a normal EntityNode's `relationship_summary`
  — **no** new node type, **no** self-model-specific method. (Req 10; Resolution
  Log item 2.)

**Open Question status** (architect-resolved 2026-07-05; see design.md "Open
Questions — Architect Resolutions"):
- RESOLVED, implemented: OQ3 (embedding side-table), OQ5 (total-elapsed decay),
  OQ4 (reorder-not-filter, mood PRIMARY / need SECONDARY, no coefficient),
  OQ1-trigger ("without variation" = context embedding-similar to recent
  firings; salience-only guard).
- DEFERRED, explicit placeholder + TODO (this plan must NOT finalize): OQ1-rate
  (habituation magnitudes), OQ2 (medium/low base_salience placeholders
  0.35/0.15).
- NOT this module's decision: OQ6 (Purpose → Module 2); max-5-with-no-evictable-
  GRAPH_CONFLICT (keep the raise — cognitive-ceiling alternative flagged, not
  implemented).
No invented value beyond the stated placeholders.

---

## Tasks

- [ ] 1. Set up module scaffold
  - Create `graph_manager.py` (no other module's files are touched;
    `daemon/state_manager.py` in particular is not modified).
  - Add imports for `Enum`, `dataclass`, `Optional`, `sqlite3`, `datetime`,
    `uuid`, typing helpers.
  - _Requirements: (structural only)_

- [ ] 2. Implement the enums
  - `NodeType`, `Precision`, `PoignancyCategory`, `Perspective`,
    `RelationalStage`, `UncertaintyType`, `UncertaintyStatus`, `EdgeType`,
    matching design.md's Data Types section verbatim (exact string values from
    v4 Layer 3 / Addendum §2).
  - Unit test: each enum has exactly the members/values listed — no
    `trust_score`-related member anywhere; `EdgeType` includes `"resolved"`;
    `RelationalStage` has exactly the four Addendum §2 stages.
  - _Requirements: 1.1, 7.1, 7.2, 9.4_

- [ ] 3. Implement the node and edge dataclasses
  - `EventNode`, `EntityNode`, `EmotionNode`, `UncertaintyNode`, `Edge` with
    exactly the fields v4 Layer 3 lists for each (per requirements.md Glossary).
    `EntityNode` omits `trust_score`, includes `relational_stage`.
  - NOT frozen (fields like `salience`, `precision`, `last_accessed`,
    `access_count`, `relational_stage`, uncertainty `status` are mutable over
    a node's lifetime) — design.md Data Types.
  - Unit test: `EntityNode` has no `trust_score` attribute and has a
    `relational_stage` attribute; each dataclass exposes exactly its
    v4-schema fields.
  - _Requirements: 1.1, 1.2, 7.1, 7.2_

- [ ] 4. Implement the SQLite store schema and initialization
  - Create tables `event_nodes`, `entity_nodes`, `emotion_nodes`,
    `uncertainty_nodes`, `edges` with columns matching the dataclass/schema
    fields, and `node_embeddings(node_id, embedding)` **as the architect-DECIDED
    side-table (OQ3 Resolved)** — comment at the DDL that the locked node schema
    is untouched and the table is regenerated if the embedding model changes.
    `entity_nodes` has a `relational_stage` column and **no** `trust_score`
    column.
  - Do NOT create any table, file, or store resembling a conversation log, a
    chat vector DB, or a summary file (Rule 7 / Req 13.2).
  - Unit test: schema round-trips a representative row of each node type and an
    edge with all v4 fields intact; `entity_nodes` schema check confirms
    presence of `relational_stage` and absence of `trust_score`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 7.1, 7.2, 13.2_

- [ ] 5. Implement `MemoryGraph.__init__` and the pre-init guard
  - Constructor takes a SQLite connection/path and an injected
    `Embedding_Model` interface (design.md Embedding Dependency) — do NOT
    instantiate a specific embedding model inside `MemoryGraph`, and do NOT
    hardcode a model name.
  - Public read/write/query methods raise `RuntimeError` if the store/embedding
    dependency is not wired (design.md Error Handling), before doing any work.
  - Unit test: calling a query method before wiring raises `RuntimeError`;
    after wiring it does not raise for that reason.
  - _Requirements: (Error Handling); dependency-injection per design Embedding
    Dependency section_

- [ ] 6. Implement `write_event_node` with base_salience floors
  - Create an EventNode with all v4 fields; set `precision = "vivid"`,
    `last_accessed = now`, `access_count = 0`.
  - Compute `base_salience = poignancy_floor + (0.15 if appraisal_q2 ==
    "negative" else 0)`, with `poignancy_floor` = 0.85 (critical) / 0.55
    (high). For medium/low, use the architect's DEFERRED PLACEHOLDER magnitudes
    — medium 0.35, low 0.15 (`TODO(OQ2)`, runtime-tuned) — on which the +0.15
    negative bonus stacks exactly as on the critical/high floor. The
    placeholders are only required to be ordered (medium > low) and both below
    the 0.55 high floor; do NOT treat the exact magnitudes as final.
  - Set initial `salience = base_salience`.
  - Accept `is_partial_appraisal = True` via the same path (Req 2.2).
  - Unit tests: critical → `base_salience >= 0.85`; high → `>= 0.55`; +0.15
    added iff `appraisal_q2 == "negative"`, stacking on the floor; medium/low
    asserted for the architect's stated PROPERTIES (medium > low, both < 0.55,
    +0.15 stacks) — not the exact placeholder magnitudes.
  - _Requirements: 2.1, 2.2, 2.3, 5.1, 5.2, 5.3, 5.4; OQ2 (DEFERRED placeholder
    medium 0.35 / low 0.15, TODO(OQ2))_

- [ ] 7. Implement `adjust_salience` and the base_salience-immutability invariant
  - `adjust_salience(node_or_edge_id, new_salience)` writes only the
    fluctuating `salience` field; it never modifies `base_salience`. It is the
    low-level setter used by DMN consolidation and by habituation (Task 7b).
  - Unit test: after any sequence of `adjust_salience` calls, `base_salience`
    is unchanged from creation.
  - _Requirements: 5.5, 9.2_

- [ ] 7b. Implement `register_edge_firing` — habituation (OQ1 trigger RESOLVED)
  - Record each edge FIRING's retrieval-context embedding in the
    `edge_firing_contexts` side-table; bump `firing_count`/`last_activated`.
  - A firing is "without variation" (architect OQ1 trigger shape) iff its
    context embedding is embedding-similar to recent firings of the SAME edge;
    when so, decrement the edge's `salience`.
  - GUARD (architect): touches edge `salience` ONLY — never PAD, never
    appraisal. The decrement amount, similarity cutoff, and recent-firings
    window are DEFERRED placeholders — `TODO(OQ1-rate)`, runtime-tuned.
  - Wire into `retrieve()` (Task 17): returned edges "fire" with the retrieval
    query_embedding as context (only when a query_embedding is present).
  - Unit tests: repeated similar-context firing decrements salience; varied
    context does not; base_salience and valence are never touched. Flag as the
    item for HARDEST review.
  - _Requirements: 5.5, 9.2; OQ1 trigger RESOLVED, OQ1-rate DEFERRED_

- [ ] 8. Implement lazy precision-decay evaluation
  - Internal `_evaluate_precision(node, now)` called on each retrieval touch
    (Task 18), in the design's order: evaluate from the node's *current*
    `last_accessed`; advance `vivid→present→softened→faded` through every
    transition whose time threshold (~72h / ~14d / ~60d) `elapsed` exceeds,
    stopping at the first blocked by resistance.
  - Resistance compares against **`base_salience`** (`> 0.8` blocks
    `vivid→present`; `> 0.5` blocks `present→softened`; `> 0.3` blocks
    `softened→faded`) — **not** the fluctuating `salience`. Add a comment
    citing Resolution Log item 9 as the reason v4's "salience" table wording is
    overridden here (precedence).
  - Treat the thresholds as total-elapsed-since-`last_accessed` checkpoints
    (multi-step catch-up in one pass) — architect-RESOLVED (OQ5); comment that
    this is the decided reading (not per-stage dwell).
  - `faded` is terminal; never delete a node.
  - Do the timer reset (`last_accessed = now`, `access_count += 1`) as part of
    the retrieval touch (Task 18), AFTER evaluation — not inside this helper if
    that helps keep evaluate/reset ordering explicit.
  - Unit/property tests: precision only advances, never regresses, never
    deletes; `base_salience` 0.85 never leaves `vivid`; 0.55 settles at
    `present` (goes vivid→present but not present→softened); a node retrieved
    more often than 72h never advances; a node untouched 65d advances multiple
    steps in one evaluation (if not resisted).
  - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6; OQ5 RESOLVED (total-elapsed,
    multi-step catch-up)_

- [ ] 9. Implement `create_uncertainty_node` with the max-5 cap
  - Store with `status = ACTIVE`; set `is_protected = True` for
    INPUT_UNCERTAIN and VALENCE_UNCERTAIN.
  - Before creating a 6th ACTIVE node, force-resolve the **oldest
    `GRAPH_CONFLICT`** ACTIVE node to `ABANDONED`. Never force-abandon a
    protected node.
  - If the cap is hit and there is **no** `GRAPH_CONFLICT` node to evict, raise
    (architect-CONFIRMED: keep this stub) — do NOT evict a CAUSAL_UNCERTAIN or
    protected node, and do NOT silently drop the new node. (Cognitive-ceiling
    alternative — a new uncertainty simply not forming at the limit — is flagged
    for later, NOT implemented.)
  - This cap is Memory_Graph's own creation-time enforcement (comment: v4's
    `state_manager.py` attribution predates Addendum §4; precedence Addendum >
    v4).
  - Unit tests: 6th creation with a `GRAPH_CONFLICT` present abandons the oldest
    `GRAPH_CONFLICT`, never a protected node; active count stays ≤ 5; 6th
    creation with no evictable `GRAPH_CONFLICT` raises.
  - _Requirements: 3.1, 3.4, 3.5; max-5-no-evictable → keep raise (architect-
    confirmed; cognitive-ceiling alternative flagged, not implemented)_

- [ ] 10. Implement `update_uncertainty_status`
  - Accept RESOLVED_CONFIRMED / RESOLVED_INFERRED / ABANDONED writes; set
    `resolved`, `resolution_path`, and store `catch_up_delta_*` /
    `catch_up_magnitude_factor` as **data only**.
  - Do NOT apply any PAD shift from the catch-up fields (Req 13.1) — Memory_Graph
    never touches PAD; the shift is a secondary appraisal elsewhere.
  - Accept a DMN-supplied staleness ABANDONED (`resolution_path = "staleness"`);
    do NOT compute the 7d/50-interaction threshold here (that is DMN's — Req
    3.3). Store/expose `interaction_count` and `created`, but never auto-abandon.
  - Unit tests: a resolution write sets the fields and stores (does not apply)
    the catch-up deltas; MemoryGraph does not auto-abandon a node whose
    `interaction_count >= 50` or age ≥ 7d — it stays ACTIVE until an explicit
    ABANDONED write.
  - _Requirements: 3.2, 3.3, 13.1_

- [ ] 11. Implement `write_edge` for connection / aha / tension edges
  - Create an edge with all v4 Edge Schema fields; support `is_aha_edge`
    (DMN Step 2 insight connection) and `is_tension_pair` /
    `tension_partner_edge` (ambivalence).
  - Unit tests: an aha edge round-trips with `is_aha_edge = True`; a tension
    pair round-trips with both edges linked via `tension_partner_edge`.
  - _Requirements: 9.1, 9.3_

- [ ] 12. Implement the `"resolved"` arc-closure edge with 3× salience
  - When `write_edge` is called with `edge_type = "resolved"`, direct it
    closing→opening EventNode and weight its salience 3× at creation
    (Resolution Log item 5; v4 constants "Argument buffer resolution weight |
    3×"). No new node type is created for arc closure.
  - Unit test: a `"resolved"` edge has 3× the salience of an otherwise-identical
    non-resolved edge created from the same inputs.
  - _Requirements: 9.4_

- [ ] 13. Implement `crystallize_emotion_node` (critical-only)
  - Create an EmotionNode with all v4 fields; `poignancy_category` fixed to
    `"critical"`.
  - Raise `ValueError` if asked to crystallize a non-critical state (Req 8.1;
    design Error Handling) — do not silently coerce.
  - Unit tests: a critical crystallization succeeds and round-trips; a
    non-critical crystallization raises `ValueError`.
  - _Requirements: 8.1, 8.2, 8.3_

- [ ] 14. Implement `update_relationship_summary` (single path incl. self node)
  - One write path for every EntityNode's `relationship_summary`, including the
    self-referential EntityNode. Do NOT add a self-model-specific method, table,
    or node type (Resolution Log item 2).
  - Unit test: the self-referential EntityNode's narrative is written and read
    through the exact same method as any other entity's summary; no
    `write_self_model`-style method exists.
  - _Requirements: 10.1, 10.2_

- [ ] 15. Implement `set_relational_stage` and `get_relational_stage`
  - `set_relational_stage` accepts and persists a DMN-decided stage (advance or
    one-step regression, never below `observing`). It performs **no** gate
    evaluation (Req 7.5).
  - `get_relational_stage` returns the stored stage to Soul_Filter.
  - Neither method reads or writes `aria_state.json.relationship_depth`
    (Req 7.6).
  - Unit tests: setting then getting round-trips the stage; no method on
    MemoryGraph evaluates a transition gate (API-surface check); no code path
    references `relationship_depth`.
  - _Requirements: 7.3, 7.4, 7.5, 7.6_

- [ ] 16. Implement embedding-backed similarity (using the injected model)
  - Add an internal similarity ranking over stored `node_embeddings` vs. a
    supplied `query_embedding` (cosine similarity — standard for sentence
    embeddings; the "top 3–5" size is v4-stated). A node lacking a stored
    embedding is excluded from *similarity* ranking (still reachable via
    entity_ref/other queries), not fatal (design Error Handling).
  - Do NOT instantiate an embedding model here — use the injected dependency
    from Task 5.
  - Unit test: given seeded embeddings, ranking orders candidates by descending
    similarity; a node without an embedding is skipped in similarity ranking
    without error.
  - _Requirements: 6.4; OQ3 RESOLVED (embeddings in `node_embeddings` side-table)_

- [ ] 17. Implement `retrieve()` with mood-congruence and need-preference
  - Signature `retrieve(pad_pleasure_sign, need_prefs, entity_refs,
    query_embedding)`. Select candidates by similarity (Task 16) and
    entity_refs; on each touched node run Task 8's precision evaluation, then
    the Task 18 timer reset.
  - Apply mood-congruence (valence-sign match to `pad_pleasure_sign` surfaces
    first) and need-preference (need-relevant surfaces first) as **stable-sort
    reorderings, not filters** — do NOT combine them with any numeric
    coefficient/weight (Req 6.5). Precedence is architect-RESOLVED (OQ4):
    **mood-congruence PRIMARY, need-preference SECONDARY**. Implement by
    applying the need sort FIRST and the mood sort LAST (stable sort → mood
    dominates).
  - Return at most 5 results (Req 6.1).
  - Unit/property tests: returns ≤ 5; sign-matching candidates ordered ahead of
    non-matching for a given `pad_pleasure_sign`; when mood and need disagree,
    MOOD wins (primary); no numeric blend of the three preferences exists.
  - _Requirements: 6.1, 6.2, 6.3, 6.5; OQ4 RESOLVED (mood PRIMARY / need
    SECONDARY, reorder-not-filter, no coefficient)_

- [ ] 18. Wire the retrieval touch: evaluate-then-reset ordering
  - Ensure every node returned by (or scanned during) `retrieve()` has its
    precision evaluated (Task 8) **before** its `last_accessed`/`access_count`
    are updated, and that the reset happens exactly once per touch.
  - Unit test: after a retrieval, touched nodes have `last_accessed == now` and
    `access_count` incremented by exactly 1, and precision reflects the elapsed
    time *before* this retrieval (not after the reset).
  - _Requirements: 4.6, 6.1_

- [ ] 19. Implement the Needs_System qualifying-evidence queries
  - `connection_evidence(now, window=72h)` — EventNodes with `appraisal_q1` in
    {medium, high} in the last 72h.
  - `growth_evidence(now, window=14d)` — UncertaintyNodes resolved
    CONFIRMED/INFERRED (not ABANDONED) in the last 14d.
  - `purpose_evidence(now, window=14d)` — a stand-in over existing
    Appraisal_Chain fields (positive-valence EventNode in-window); do NOT invent
    a structural definition of "follow-through" — this is NOT this module's
    decision (architect: deferred to Needs System / Module 2). Add a
    `TODO(OQ6-M2)` comment.
  - `continuity_evidence(now, window=60d)` — whether the self-referential
    EntityNode's `relationship_summary` was extended coherently in the last 60d.
  - None of these computes a need *state* (satisfied/due/neglected) — they
    return structural evidence only (Req 11.5).
  - Unit tests: each returns the correct boolean/evidence on a seeded graph for
    in-window and out-of-window cases; none returns a need state.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5; OQ6 (Purpose) NOT this
    module's decision — deferred to Needs System / Module 2_

- [ ] 20. Implement `is_first_of_kind` and `resolved_edge_exists`
  - `is_first_of_kind(entity_ref, event_type)` — whether this event type is
    novel for this entity (poignancy Critical "novel entity" / Addendum §6
    "first-of-kind" input for Appraisal_Chain).
  - `resolved_edge_exists(entity_ref, window)` — whether a `"resolved"` edge
    exists on this entity within the window (DMN Invested→Bonded input,
    Resolution Log item 5).
  - Both return structural results only; neither makes a poignancy or trust
    decision (Req 12.1, 12.3; the deciding module is Appraisal_Chain / DMN).
  - Unit tests: `is_first_of_kind` true for a novel entity/event pair, false
    once a prior matching event exists; `resolved_edge_exists` true iff a
    `"resolved"` edge is within the window.
  - _Requirements: 12.1, 12.3_

- [ ] 21. Implement `reality_contradiction_check`
  - Compare the factual content of two same-`entity_ref` EventNode descriptions
    within a window, using the injected embedding model + basic negation
    detection, returning a structural contradiction boolean (Addendum §1).
  - The similarity cutoff, window duration, and negation criterion are
    **build-time tuning constants** (Addendum "Open — build-time tuning
    constants"); carry them as clearly-commented placeholder constants, exactly
    as Module 1 carried `PAD_HISTORY_LENGTH` — not as invented architectural
    values.
  - Return the structural result only; do NOT decide what a contradiction means
    for trust or PAD (Req 12.4).
  - Unit tests: a clear contradiction returns True, a clear agreement returns
    False on seeded descriptions; the method returns a bool, not a
    trust/meaning verdict.
  - _Requirements: 12.2, 12.4_

- [ ] 22. Boundary-enforcement API-surface tests
  - Assert MemoryGraph exposes **no** method that mutates PAD, **no** method
    that accepts an LLM handle or returns LLM-formatted data, and **no** method
    that accepts a Needs-pressure / F4 / barge-in value as a PAD input
    (Req 13.1, 13.3).
  - Assert no code path reads or writes `relationship_depth` (Req 7.6).
  - Assert reads/retrievals return detached copies (mutating a returned object
    does not alter live graph state).
  - _Requirements: 13.1, 13.2, 13.3, 7.6_

- [ ] 23. Wire together, run the full suite, and confirm Open-Question status
      in code (architect-resolved 2026-07-05)
  - Ensure all tests from Tasks 2–22 pass together (each test seeds its own
    isolated in-memory SQLite store; no shared-state leakage).
  - Confirm by inspection and the existing tests that:
    - **OQ1 trigger (RESOLVED):** `register_edge_firing` treats a firing as
      "without variation" iff context is embedding-similar to recent firings of
      the same edge; **OQ1-rate (DEFERRED):** decrement/cutoff/window are
      `TODO(OQ1-rate)` placeholders. GUARD: habituation touches edge salience
      only — never PAD/appraisal.
    - **OQ2 (DEFERRED):** medium/low base_salience are placeholders
      (medium 0.35, low 0.15, `TODO(OQ2)`); tests assert the ordering/below-floor
      /stacking properties, not the exact magnitudes.
    - **OQ3 (RESOLVED):** `node_embeddings` side-table keyed by node_id; locked
      node schema untouched; regenerate on model change.
    - **OQ4 (RESOLVED):** reorder-not-filter, mood-congruence PRIMARY / need
      SECONDARY; NO numeric blend anywhere.
    - **OQ5 (RESOLVED):** total-elapsed decay, multi-step catch-up.
    - **OQ6 (NOT this module):** `purpose_evidence` is a stand-in over existing
      fields (`TODO(OQ6-M2)`), deferred to Module 2; the no-evictable-
      GRAPH_CONFLICT path raises (cognitive-ceiling alternative flagged, not
      implemented).
    - **Boundaries**: no PAD write surface, no LLM surface, no
      `relationship_depth` reference, precision-decay resistance checks
      `base_salience` (not `salience`), staleness/relational_stage/habituation
      never wired to PAD or appraisal.
  - _Requirements: all; OQ3/4/5/1-trigger RESOLVED, OQ1-rate/OQ2 DEFERRED
    placeholders, OQ6 deferred to Module 2._

