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
