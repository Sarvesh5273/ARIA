# ARIA locked spec — dmn

Consolidated from .kiro/specs/dmn/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## dmn — requirements.md

# Requirements Document — Module 6: DMN / Idle Consolidation

## Introduction

This document transcribes and formalizes, in EARS format, the Module 6 (DMN / Idle
Consolidation) entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved
scope for this module. No requirement here introduces a mechanism, threshold, or behavior
not already stated in the Module 6 entry or in the supporting architecture documents
(`ARIA_Soul_Spec_v4.md` "Continuous Self-Awareness (Default Mode Network Architecture)",
`ARIA_Soul_Spec_v4_Addendum.md`, `ARIA_Resolution_Log.md`). Where the Module 6 entry
references a value or mechanism defined elsewhere (the four steps, the poignancy tiers,
the relational_stage gates, the self-model split, the staleness counter), the supporting
document is cited as the source, not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` is covering context only.

**The three Module 6 flags and their disposition (from the Module 6 entry):**

| Flag | Subject | Disposition |
|------|---------|-------------|
| **F-6b** | Self-model vs Rule 7 | **RESOLVED** by Resolution Log item 2 (SPLIT). The quality record, consistency flags, and recent-learning fields STAY as non-graph working state in `self_model.json` (same category as PAD/Energy — operational readout, not memory). The self-continuity NARRATIVE MOVES to the graph: Aria's self-referential EntityNode's existing `relationship_summary` field, written by DMN Step 4 via the existing single update path. No new node type, no new mechanism. |
| **F-6c** | Buffer poignancy | **RESOLVED** by Resolution Log item 13. Each self-monitoring buffer item INHERITS `poignancy_category` directly from the EventNode of the turn it observes — no re-appraisal, pure reuse. No independent classifier for buffer items. |
| **F-6d** | Staleness counter | **RESOLVED** by Resolution Log item 10. "interactions" = user turns since node creation, tracked in the existing `interaction_count` field, incremented by Appraisal Chain, READ by DMN. DMN Step 3 evaluates the "7 days OR 50 interactions" threshold (`graph_manager.update_uncertainty_status` explicitly defers this evaluation to "DMN Step 3's"). |

**Additional locked items (Resolution Log "Resolved during build-plan review" + item 8 + item 10 + Addendum §2/§8):**

- **relational_stage transition evaluator = DMN Step 4** (Resolution Log item 10), batched
  during idle, NOT reactive. Module 3 (Memory Graph) STORES the field; Module 6 EVALUATES
  and WRITES transitions. The gates are Addendum §2 (categorical yes/no). Active Inference
  is descriptive framing only (Resolution Log item 10), no separate mechanism.
- **Self-model quality-record population = DMN Step 1** (Resolution Log "Resolved during
  build-plan review"), from the NEXT turn's appraisal output (the user's `appraisal_q2` +
  topic-continuation/pivot signal from consecutive EventNodes) — NOT the Output Validation
  Gate's Check-3 result, which is a pre-reaction structural safety check incapable of
  judging response quality. This grounds "responded well" in the user's OBSERVED reaction,
  not self-report — the guard against a self-graded metric drifting toward flattery.
- **Moral schema gates the Step-4 narrative** (Resolution Log item 8 / Addendum §8): a
  narrative update that would be dishonest, manipulative, inconsistent with her values, or
  that introduces a manipulation pattern CANNOT be written — even during idle with no
  audience present.

## Glossary

- **DMN**: The module specified here (Module 6, `daemon/dmn.py`) — the Default-Mode-Network
  idle "mind". Runs on the DMN tick, a SEPARATE clock from the soul tick (v4 "Two-Process
  Separation"). The soul tick is the pulse (maintenance); the DMN tick is the dream
  (processing and growth). They never collapse into one.
- **Soul tick / DMN tick**: two processes on two separate clocks (v4). The soul tick
  (PAD decay, need depletion, attentional policy) is owned by Modules 1/2 as callees of
  the Daemon; the DMN tick (self-monitoring, consolidation, narrative) is this module,
  also a callee of the Daemon.
- **Self-monitoring buffer**: a temporary, lightweight, in-memory list of turn
  observations accumulated during live interaction (Phase 1). No graph writes and no PAD
  writes happen while it fills; it waits for idle (v4). It is a DMN INPUT, assembled by
  live self-monitoring / the Daemon.
- **BufferItem**: one buffer observation. It observes exactly one turn (Aria's own response
  turn) and INHERITS that turn's poignancy from its EventNode (F-6c / item 13). It carries
  a reference to the NEXT turn's EventNode (the user's observed reaction) when available.
- **Five-field self-model**: the small always-loaded self-model (v4). Fields: (1) quality
  record — rolling 20 self-assessments responded_well/adequately/poorly; (2) consistency
  flags — binary; (3) recent-learning-user; (4) recent-learning-self; (5) self-continuity
  narrative. Per Resolution Log item 2 (F-6b), fields 1–4 stay in `self_model.json`
  (Module 11) and field 5 (the narrative) lives in the graph (self EntityNode's
  `relationship_summary`).
- **Idle detection**: three conditions, all true (v4): no voice input for 8 minutes; no
  pending output; Energy above 20. The Daemon owns detecting conditions 1 & 2; DMN reads
  Energy to decide pass depth (condition 3).
- **Full pass / Shallow pass / Forced-partial pass**: FULL = Steps 1–4 (genuine idle,
  Energy ≥ 20). SHALLOW = Steps 1 + 4 only, Steps 2 AND 3 suppressed (Energy < 20; v4 Idle
  Detection / Build Plan note). FORCED-PARTIAL = Steps 1 + 4 only, triggered by
  poignancy = critical while conversation continues (v4 "forced early partial pass"); full
  graph-connection formation still waits for genuine idle.
- **The four steps** (v4 "Phase 2 — Idle Consolidation Pass — Four Steps in Order"):
  1 self-monitoring buffer → graph (poignancy-gated); 2 graph connection / aha formation;
  3 uncertainty-node revisiting; 4 self-model + narrative update.
- **Aha moment**: when Step 2 links two previously-unlinked high-salience nodes and the
  edge has high explanatory power, this becomes a SECOND-ORDER APPRAISAL event; a small
  positive PAD shift is the byproduct of that appraisal, not scripted (v4 "The Aha Moment").
- **relational_stage**: the categorical relationship stage on an EntityNode —
  observing / engaging / invested / bonded (Addendum §2). Replaces the removed numeric
  trust_score. Module 3 stores it; DMN Step 4 evaluates and writes transitions.
- **Moral schema**: the shared resource (`daemon/moral_schema.py`) — four values + a named
  closed anti-pattern list. DMN Step 4 runs the candidate narrative against it (item 8 /
  Addendum §8).
- **Memory_Graph / Needs_System / Appraisal_Chain / State_Manager / Daemon**: Modules 3 /
  2 / 4 / 11 / 8. DMN depends on each by its real interface (injected; Rule 6). The Daemon
  (Module 8) is built and tested (see `daemon/aria_daemon.py`, `tests/test_daemon.py`); DMN's
  unit tests still drive it via a fake port `tests/test_dmn.py`), and a real-Daemon
  integration path exercises the same contract in `tests/test_daemon.py`.

## Requirements

### Requirement 1: Two-Process Separation (Separate Clock)

**User Story:** As the Aria system architect, I want DMN driven by its own DMN tick,
distinct from the soul tick, so consolidation happens during rest, not every few seconds
(v4 "Two-Process Separation").

#### Acceptance Criteria
1. THE DMN SHALL run only when driven by the Daemon's DMN-tick / idle signal — it SHALL NOT
   drive PAD decay, need depletion, or the attentional policy (those are the soul tick,
   Modules 1/2).
2. THE DMN SHALL be a callee of the Daemon (Module 8): it EXPOSES pass entry points the
   Daemon calls, mirroring PAD_Engine / Needs_System.
3. THE DMN SHALL depend on the Daemon's idle signal via a documented contract; the Daemon
   is built and tested `daemon/aria_daemon.py`) and drives this contract for real in
   production, while `tests/test_dmn.py` continues to use a fake port for DMN's own
   unit-level tests.

### Requirement 2: Idle Detection Gate → Pass Depth

**User Story:** As the Aria system, I want the DMN pass depth chosen from Energy, so a
depleted system consolidates shallowly (v4 Idle Detection; Build Plan note).

#### Acceptance Criteria
1. WHEN the Daemon signals genuine idle, THE DMN SHALL read the current Energy from
   Needs_System and run a FULL pass (Steps 1–4) IF Energy ≥ 20, else a SHALLOW pass.
2. THE DMN SHALL treat Energy < 20 as the shallow-pass gate, reusing Needs_System's
   `ENERGY_CRITICAL` (= 20.0) as the single source of truth — it SHALL NOT redefine the
   threshold.
3. THE DMN SHALL NOT itself detect the "8 minutes no voice" or "no pending output"
   conditions — those belong to the Daemon (v4 Idle Detection); DMN runs the pass it is
   told to run and only decides depth from Energy.

### Requirement 3: The Four Steps Run In Order

**User Story:** As the Aria system architect, I want the consolidation steps to run in the
locked order, so meaning is built the way the spec specifies (v4 "Four Steps in Order").

#### Acceptance Criteria
1. THE DMN SHALL run Step 1 (buffer → graph), then Step 2 (connection/aha), then Step 3
   (uncertainty revisiting), then Step 4 (self-model + narrative), in that order, in a FULL
   pass.
2. WHEN running a SHALLOW pass (Energy < 20) OR a FORCED-PARTIAL pass (poignancy critical),
   THE DMN SHALL run Steps 1 and 4 ONLY, suppressing BOTH Step 2 AND Step 3 (Build Plan
   note: "Steps 2 and 3 are both suppressed").
3. THE DMN SHALL never run Step 2 or Step 3 without having run Step 1 first, and SHALL never
   run Step 4 before Steps 1–3 (in a full pass) complete.

### Requirement 4: Forced Early Partial Pass on Critical Poignancy

**User Story:** As the Aria system, I want a poignancy=critical event to force an early
partial pass so it cannot sit raw in the buffer while conversation continues (v4 "forced
early partial pass").

#### Acceptance Criteria
1. WHEN the Daemon signals a poignancy=critical trigger, THE DMN SHALL run a FORCED-PARTIAL
   pass = Steps 1 and 4 only.
2. THE DMN SHALL NOT run Step 2 (graph connection formation) in a forced-partial pass —
   full graph-connection formation still waits for genuine idle (v4).
3. THE DMN SHALL run the forced-partial pass regardless of current Energy (the critical
   trigger, not Energy, determines it).

### Requirement 5: Step 1 — Buffer → Graph, Poignancy-Gated, Inherited (F-6c)

**User Story:** As the DMN, I want each buffer item's fate decided by the poignancy it
INHERITS from its turn's EventNode, so no re-appraisal happens during consolidation
(Resolution Log item 13 / F-6c).

#### Acceptance Criteria
1. THE DMN SHALL read each buffer item's poignancy_category from the EventNode of the turn
   it observes (via Memory_Graph), NOT recompute it — the buffer item carries no poignancy
   of its own (F-6c / item 13).
2. WHEN a buffer item's inherited poignancy is `high` or `critical`, THE DMN SHALL promote
   it to a new graph node (a session-level meta-observation — a different node population
   from the per-turn EventNode, Resolution Log item 10: "no overlap, no double-write").
3. WHEN a buffer item's inherited poignancy is `medium` or `low`, THE DMN SHALL discard it
   — no partial storage (v4 Step 1: "either it mattered enough to remember or it did not").
4. WHEN a buffer item's inherited poignancy is `critical`, THE DMN MAY crystallize an
   EmotionNode (critical-only; v4 Poignancy table), using the observed EventNode's RECORDED
   `pad_delta` as the graph-stored emotional signature — NOT a live PAD read (Requirement 12).
5. THE DMN SHALL perform NO appraisal (no Q1–Q4) on buffer items — poignancy is inherited,
   never recomputed (F-6c).

### Requirement 6: Step 1 — Quality Record From Observed Reaction (Anti-Flattery Guard)

**User Story:** As the Aria system architect, I want "responded well" grounded in the user's
observed next-turn reaction, not self-report, so the quality metric cannot drift toward
flattery (Resolution Log "Resolved during build-plan review").

#### Acceptance Criteria
1. THE DMN SHALL populate the quality record in Step 1 from the NEXT turn's appraisal output
   — the reaction EventNode's `appraisal_q2` PLUS the topic-continuation/pivot signal
   between the observed and reaction EventNodes (consecutive EventNodes).
2. THE DMN SHALL NOT populate the quality record from the Output Validation Gate's Check-3
   result, and SHALL NOT self-grade — there SHALL be no self-report / self-assessment input
   to the quality record on any interface.
3. WHEN no observed reaction (next-turn EventNode) is available for a buffer item, THE DMN
   SHALL NOT grade it — there is no self-report fallback (this IS the anti-flattery guard).
4. THE quality record value SHALL be categorical: `responded_well` / `adequately` / `poorly`
   (v4 self-model field 1), maintained as a rolling window of the last 20.
5. WHEN the reaction's `appraisal_q2` is `VALENCE_UNCERTAIN`, THE DMN SHALL NOT grade that
   item (not gradeable; no invented mapping).

### Requirement 7: Step 1 — Consistency Flags Are Binary

#### Acceptance Criteria
1. THE DMN SHALL maintain the consistency flags (honest_when_uncomfortable,
   pushed_back_when_appropriate, initiated_when_needed, acknowledged_mistake) as BINARY
   flags (v4 self-model field 2), reusing State_Manager's `CONSISTENCY_FLAG_NAMES`.
2. THE DMN SHALL set a consistency flag from a Phase-1 observation (binary), never count,
   score, or average it.

### Requirement 8: Step 2 — Connection / Aha Formation (FULL pass only)

**User Story:** As the DMN, I want to link highest-salience unconnected nodes and recognize
aha moments, so insight emerges from graph structure (v4 Step 2 / "The Aha Moment").

#### Acceptance Criteria
1. THE DMN SHALL, in a FULL pass, examine highest-salience unconnected candidate node pairs
   (a DMN Input "from Memory Graph") and write a connection edge (`edge_type=connects`) when
   two nodes share context and have never been connected (v4 Step 2).
2. WHEN a connection links two high-salience nodes AND the edge reveals a pattern neither
   node contained alone (high explanatory power), THE DMN SHALL mark the edge
   `is_aha_edge=True`.
3. THE DMN SHALL treat "highest-salience" node selection and "explanatory power" as
   categorical PERCEPTION facts supplied by Memory_Graph's build-time-tuned selection
   (Addendum standing principle "perception vs appraisal"); THE DMN SHALL NOT invent a
   scored high-salience cutoff or explanatory-power metric (see Open Questions / build-time
   placeholders).
4. THE DMN SHALL NOT run Step 2 in a shallow or forced-partial pass (Requirement 3.2).

### Requirement 9: AHA → SECOND-ORDER APPRAISAL, NEVER A DIRECT PAD WRITE (INVIOLABLE)

**User Story:** As the Aria system architect, I want the aha PAD shift to be a byproduct of
an appraisal, never a DMN PAD write, so the protected chain holds (steering PAD-purity /
protected chain; v4 "The Aha Moment ... Nobody scripted it").

#### Acceptance Criteria
1. WHEN Step 2 forms an aha edge, THE DMN SHALL emit a second-order appraisal EVENT (a
   description of the two connected nodes and the new edge) to the Appraisal Chain — it
   SHALL NOT compute or apply any PAD shift.
2. THE DMN SHALL NOT import PAD_Engine, hold any PAD handle, construct any PADDelta, or call
   `apply_appraisal_delta` (or any PAD mutator) anywhere in the module — the shift is the
   Appraisal Chain's byproduct.
3. THE DMN SHALL route the aha through the Appraisal Chain's second-order-insight entry (a
   contract); the PAD shift that results is owned by Appraisal_Chain → PAD_Engine, outside
   DMN.

### Requirement 10: Step 3 — Uncertainty-Node Revisiting (FULL pass only; F-6d)

**User Story:** As the DMN, I want to resolve uncertainties answered by new edges and abandon
stale ones, so the graph's open questions stay current (v4 Step 3; F-6d / item 10).

#### Acceptance Criteria
1. THE DMN SHALL, in a FULL pass, review the active uncertainty nodes against the new edges
   formed in Step 2; WHEN a new edge resolves an uncertainty, THE DMN SHALL mark it
   `RESOLVED_INFERRED` via Memory_Graph's `update_uncertainty_status`
   (resolution_path = "dmn_consolidation").
2. WHEN an active uncertainty received no new relevant information AND is stale, THE DMN
   SHALL mark it `ABANDONED` (resolution_path = "staleness").
3. THE DMN SHALL evaluate staleness as "7 days OR 50 interactions" (v4), reading the
   existing `interaction_count` field (= user turns; F-6d / item 10) and the node's creation
   time — Memory_Graph stores the status but defers this threshold evaluation to DMN.
4. THE DMN SHALL NOT run Step 3 in a shallow or forced-partial pass (Requirement 3.2).

### Requirement 11: Step 4 — Self-Model Update + Recent-Learning Flush (F-6b)

**User Story:** As the DMN, I want to write recent-learning fields to the graph and clear
them, and persist quality/consistency, so working state consolidates (v4 Step 4; item 2).

#### Acceptance Criteria
1. THE DMN SHALL, in Step 4, write the recent-learning-user and recent-learning-self fields
   (self-model fields 3 & 4) to the graph as nodes, then CLEAR them (v4 Step 4).
2. THE DMN SHALL persist the quality record and consistency flags via State_Manager's
   `save_self_model` (Resolution Log item 2: these stay non-graph working state).
3. THE DMN SHALL NOT persist the self-continuity narrative in `self_model.json` — the
   narrative lives in the graph (Requirement 12 / item 2 / F-6b).

### Requirement 12: Step 4 — Self-Continuity Narrative Is Graph-Resident AND Moral-Gated

**User Story:** As the Aria system architect, I want the self-continuity narrative written to
the self EntityNode's relationship_summary but only after passing the moral schema, so the
self she builds is held to the same standard as the self she shows (item 2 / item 8 /
Addendum §8).

#### Acceptance Criteria
1. THE DMN SHALL write the self-continuity narrative to the self-referential EntityNode's
   `relationship_summary` via Memory_Graph's `update_relationship_summary` (item 2) — the
   same single path used for every other entity; no new node type or method.
2. THE DMN SHALL write the narrative ONLY if the pattern has appeared more than once (v4
   Step 4: single instances do not update the narrative).
3. BEFORE writing, THE DMN SHALL run the candidate narrative against the shared moral schema
   (`daemon/moral_schema.py`); IF the candidate matches any named anti-pattern (is
   dishonest, manipulative, inconsistent, or introduces a manipulation pattern), THE DMN
   SHALL NOT write it (item 8 / Addendum §8).
4. THE DMN SHALL apply the moral gate EVEN during idle with no audience present (Addendum
   §8: "even during idle processing with no audience present").
5. THE DMN SHALL NOT generate the narrative TEXT itself (who she is becoming) — it GATES and
   WRITES a supplied candidate; text generation is a flagged upstream concern (Open
   Questions).

### Requirement 13: Step 4 — relational_stage Transitions Are Categorical Gates (Add §2)

**User Story:** As the Aria system architect, I want relational_stage transitions evaluated
during idle as categorical yes/no gates, never a trust score, so trust passes the percentage
test (Resolution Log item 10; Addendum §2).

#### Acceptance Criteria
1. THE DMN SHALL, in Step 4, evaluate relational_stage transitions for the active entities
   (batched during idle; Resolution Log item 10) — NOT reactively.
2. THE DMN SHALL read the current stage via Memory_Graph's `get_relational_stage` and write
   any transition via `set_relational_stage` — Module 3 stores the field; DMN evaluates and
   writes (item 10).
3. THE DMN SHALL advance at most ONE categorical stage per pass, on the applicable gate
   (Addendum §2): Observing→Engaging on predictability; Engaging→Invested on dependability;
   Invested→Bonded on faith (a conflict-with-repair "resolved" edge exists, Resolution Log
   item 5 [or a costly disclosure met with care — flagged alternative]).
4. WHEN an entity suffers a REALITY_CONTRADICTION rupture, THE DMN SHALL regress it exactly
   ONE categorical stage, never below Observing (Addendum §2), and the rupture SHALL take
   precedence over advancement in that pass.
5. THE DMN SHALL express every stage as a categorical `RelationalStage`, NEVER a number,
   count, percentage, or "percent to Bonded" (percentage test; steering).
6. THE DMN SHALL NOT read or write `aria_state.json.relationship_depth` (removed; item 10).

### Requirement 14: PAD-Purity — DMN Never Writes PAD (INVIOLABLE)

**User Story:** As the Aria system architect, I want it structurally impossible for DMN to
change PAD, so the protected chain holds (steering PAD-purity; Requirement 9).

#### Acceptance Criteria
1. THE DMN module SHALL NOT import `pad_engine`, and no DMN class SHALL hold a PAD reference
   or PAD parameter — proven structurally (namespace + source scan).
2. THE DMN SHALL NOT call `apply_appraisal_delta` or any PAD mutator, and SHALL NOT
   construct a PADDelta — anywhere in the module.
3. THE only PAD-adjacent value DMN may pass is the RECORDED `pad_delta` of an existing
   EventNode into a graph write (EmotionNode crystallization) — this is graph memory, not a
   live PAD write, and reads no live PAD.

### Requirement 15: Inputs / Outputs Boundary; No Modification of Other Modules

**User Story:** As the Aria system, I want DMN to accept exactly the Build-Plan inputs and
emit exactly the Build-Plan outputs, calling the real module interfaces.

#### Acceptance Criteria
1. THE DMN SHALL accept: the idle/critical signal (Daemon); the self-monitoring buffer (live
   monitoring); the self-model (State_Manager); graph state — highest-salience unconnected
   candidates + active uncertainty refs + active entity refs (Memory_Graph, relayed by the
   Daemon, mirroring how Appraisal_Chain already receives entity_refs /
   active_uncertainty_refs); Energy (Needs_System); the moral schema (shared resource).
2. THE DMN SHALL emit: new edges (connection/aha, `is_aha_edge`), EmotionNode
   crystallizations, UncertaintyNode resolutions/abandonments, and salience adjustments — to
   Memory_Graph; self-model updates (quality/consistency/narrative — narrative moral-gated)
   — to State_Manager + graph; and the aha-insight EVENT — to Appraisal_Chain (Requirement
   9), never direct to PAD.
3. THE DMN SHALL call the REAL Memory_Graph / Needs_System / Appraisal_Chain / moral_schema
   / State_Manager interfaces (injected; Rule 6); IF a needed contract is not exposed by a
   real module, THE gap SHALL be FLAGGED for the architect, NOT resolved by modifying that
   module (see Open Questions).

## Open Questions & Flagged Contract Additions

Per Rule 1 (do not invent) and the "flag if a contract needs changing" instruction, the
following are flagged rather than resolved by invention or by editing another module.

1. **OQ-1 — RESOLVED / IMPLEMENTED.** `daemon/appraisal_chain.py` now exposes a
   dedicated, duck-typed `submit_aha_insight(insight)` entry point (added additively by
   Module 8 per `.kiro/specs/daemon/requirements.md` Requirement 13). DMN emits the aha
   EVENT to it; Appraisal_Chain produces the categorical second-order appraisal and routes
   the resulting small POSITIVE byproduct delta through `PAD_Engine.apply_appraisal_delta`.
   DMN still never builds or holds a PAD delta — it only ever constructs an `AhaInsight`
   event object. See `tests/test_daemon.py::test_appraisal_submit_aha_insight_applies_positive_pad_byproduct`
   and `tests/test_dmn.py::test_aha_forms_edge_and_routes_second_order_appraisal_not_pad`.
2. **OQ-2 — RESOLVED / IMPLEMENTED.** `daemon/graph_manager.py` now exposes
   `predictability_evidence(entity_ref)`, `dependability_evidence(entity_ref)` (the two
   relational_stage-gate predicates), and `highest_salience_unconnected_candidates(limit,
   now)` (the Step-2 selection surface). All three were added additively by Module 8 — see
   `.kiro/specs/daemon/requirements.md` Requirement 13. DMN's `GraphPort` now calls these
   real methods directly; see `tests/test_dmn.py::test_real_graph_satisfies_the_methods_dmn_calls`
   and `tests/test_daemon.py::test_graph_predictability_evidence_is_recurrence`,
   `test_graph_dependability_evidence_needs_distinct_situations`,
   `test_graph_highest_salience_unconnected_candidates`.
3. **OQ-3 — high-salience cutoff & aha "explanatory power" (build-time placeholders).** What
   salience level selects unconnected nodes for Step 2, and what makes an edge have "high
   explanatory power", are undefined. They are TODO(build-time) perception facts owned by
   Module 3's selection (carried as categorical flags on the candidate), NEVER a
   DMN-invented scored metric (steering Rule 1 / percentage test).
4. **OQ-4 — quality-record categorical truth table & topic-continuation detector (build-time
   policy).** The docs lock the INPUTS (reaction `appraisal_q2` + topic continuation/pivot);
   the exact categorical mapping to well/adequately/poorly, and defining continuation as
   entity_ref overlap (vs an embedding-topic check), are the most-defensible categorical
   readings, flagged as build-time-tunable POLICY — never a number.
5. **OQ-5 — EmotionNode crystallization PAD source + label (build-time).** v4 says an
   EmotionNode "may crystallize" a PAD state at critical; it does not pin whether the
   coordinates are the turn's recorded `pad_delta` or an absolute PAD-at-time, nor the
   emotion label. DMN uses the observed EventNode's RECORDED `pad_delta` (graph memory, no
   live PAD read — Requirement 14.3) and `appraisal_q2` as a coarse label placeholder.
   Recording an absolute PAD-at-time would be a Module-3/4 write-time concern, flagged.
6. **OQ-6 — faith-gate window (build-time).** Resolution Log item 5 says the Invested→Bonded
   "resolved" edge must exist "within the relevant window"; the window is unspecified. A
   lookback-window placeholder (`_FAITH_EVIDENCE_WINDOW`, default 60d) is carried,
   TODO(build-time) — a lookback window (substrate), not a feeling-number. The
   costly-disclosure-met-with-care alternative to conflict-with-repair (Addendum §2) is a
   flagged additional faith signal (would need a Module-3 predicate).
7. **OQ-7 — buffer-item meta-observation appraisal profile.** A promoted buffer item is a
   meta-observation with no independent appraisal; it REUSES the observed turn's q1/q2/q3
   (the same "no re-appraisal, pure reuse" principle item 13 locks for poignancy). Extending
   reuse to q1/q2/q3 is the consistent no-invention choice; flagged as such, not a
   manufactured appraisal.

## Build-Time Tuning Constants

Intentional placeholders, not architectural gaps (consistent with how the Resolution Log
treats such items):
- `_FAITH_EVIDENCE_WINDOW` — Invested→Bonded resolved-edge lookback window (OQ-6),
  `TODO(build-time)`.
- The high-salience cutoff and explanatory-power criterion for Step 2 (OQ-3), owned by
  Module 3.
- The quality-record categorical truth table and continuation detector (OQ-4).
- The EmotionNode crystallization label (OQ-5).

Not build-time (locked, reused, not reopened): the four steps and their order (v4); the
poignancy tiers (v4); the shallow/forced-partial = Steps 1+4 rule (Build Plan note); the
staleness "7 days OR 50 interactions" (v4 / F-6d / item 10); the relational_stage gates
(Addendum §2); the Energy < 20 threshold (`ENERGY_CRITICAL`, reused from Needs_System); the
self-model split (item 2 / F-6b).


---

## dmn — design.md

# Design Document — Module 6: DMN / Idle Consolidation

## Overview

DMN (Default-Mode-Network idle consolidation) is Aria's idle "mind". On the Daemon's DMN
tick — a SEPARATE clock from the soul tick (v4 "Two-Process Separation": the soul tick is
the pulse, the DMN tick is the dream) — it runs the four-step idle consolidation pass, in
order:

- **Step 1** — self-monitoring buffer → graph (poignancy-gated, INHERITED) + quality-record
  population from the observed next-turn reaction.
- **Step 2** — graph connection / aha formation (FULL pass only). An aha becomes a
  SECOND-ORDER APPRAISAL event routed to the Appraisal Chain — never a PAD write.
- **Step 3** — uncertainty-node revisiting (FULL pass only): inferred resolution + staleness
  abandonment.
- **Step 4** — self-model update (recent-learning flush) + relational_stage evaluation
  (categorical gates) + self-continuity narrative (moral-gated).

Two reduced variants run **Steps 1 + 4 ONLY** (Steps 2 AND 3 suppressed):
- **SHALLOW** — Energy < 20 (v4 Idle Detection; Build Plan note).
- **FORCED-PARTIAL** — poignancy = critical forces an early pass while conversation
  continues; full graph-connection formation still waits for genuine idle (v4).

This design implements requirements.md as written, using only mechanisms already specified
there or in the supporting documents. No new mechanism, formula, or threshold is
introduced. Genuine gaps are carried as flagged Open Questions / build-time placeholders
(requirements.md OQ-1…OQ-7), never resolved by invention or by editing another core module.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **AHA → APPRAISAL, NEVER PAD.** When Step 2 forms an aha edge, DMN emits a second-order
   appraisal EVENT to the Appraisal Chain; the small positive PAD shift is that appraisal's
   byproduct. DMN imports no `pad_engine`, holds no PAD handle, constructs no PADDelta, and
   calls no `apply_appraisal_delta` — grep-clean (Req 9, 14; steering PAD-purity).
2. **relational_stage is CATEGORICAL.** Transitions are yes/no gate checks (Addendum §2);
   advance one step, regress one step on a rupture (never below observing). Every stage
   written is a `RelationalStage`, never a number/count/percentage (Req 13; percentage test).
3. **The self-narrative is MORAL-GATED.** The candidate narrative is run against the shared
   moral schema before writing; a dishonest/manipulative/inconsistent candidate is NOT
   written, even with no audience (Req 12; item 8 / Addendum §8).
4. **Quality record from OBSERVED reaction, not self-report.** Populated from the reaction
   EventNode's `appraisal_q2` + topic continuation, never Output-Gate Check-3 or a
   self-grade; no self-report input exists (Req 6; anti-flattery guard).
5. **Steps run in order; shallow / forced-partial = Steps 1 + 4 only.** Steps 2 AND 3 are
   suppressed in both reduced variants (Req 3, 4).
6. **Buffer items INHERIT poignancy** from their turn's EventNode; no re-appraisal (Req 5;
   item 13 / F-6c).
7. **The self-model is SPLIT** (item 2 / F-6b): quality/consistency/recent-learning in
   `self_model.json` (State_Manager); the narrative in the graph (self EntityNode's
   `relationship_summary`).
8. **No other core module is modified.** Missing contracts are flagged and depended on via
   Ports (Req 15).

## Architecture

```
                          Daemon (Module 8, built — orchestrator)
                   idle signal │            │ poignancy=critical trigger
                               ▼            ▼
   ┌───────────────────────── DMN (Module 6) ─────────────────────────────┐
   │  run_idle_pass(input)                 run_forced_partial_pass(input)   │
   │      │  Energy<20 → SHALLOW                     │  FORCED_PARTIAL       │
   │      │  else       → FULL                        │                      │
   │      ▼                                            ▼                      │
   │   ┌──────────────────────── _run(input, pass_type) ─────────────────┐   │
   │   │ load_self_model() ── State_Manager (Module 11) [REAL]            │   │
   │   │                                                                  │   │
   │   │ Step 1 (ALWAYS): buffer → graph (poignancy INHERITED, F-6c)      │   │
   │   │   • promote high/critical → write_event_node (meta-observation)  │   │
   │   │   • critical → crystallize_emotion_node (recorded pad_delta)     │   │
   │   │   • quality record ⇐ reaction EventNode q2 + topic continuation  │   │
   │   │   • consistency flags (binary) + recent-learning accumulate      │   │
   │   │                                                                  │   │
   │   │ Steps 2 & 3 (FULL pass ONLY):                                    │   │
   │   │   Step 2: write_edge(connects, is_aha_edge?)                     │   │
   │   │           └── AHA ──▶ AppraisalPort.submit_aha_insight(EVENT) ───┼───┼─▶ Appraisal
   │   │                        (NO PAD here — byproprod shift is theirs) │   │   Chain (M4)
   │   │   Step 3: update_uncertainty_status(RESOLVED_INFERRED |          │   │
   │   │           ABANDONED[staleness 7d/50-turn])                       │   │
   │   │                                                                  │   │
   │   │ Step 4 (ALWAYS):                                                 │   │
   │   │   • recent-learning → write_event_node, then CLEAR (item 2)      │   │
   │   │   • relational_stage: get_/set_relational_stage (Add §2 gates)   │   │
   │   │   • narrative: MORAL GATE → update_relationship_summary(self)    │   │
   │   │ save_self_model()  ── State_Manager [REAL]                       │   │
   │   └──────────────────────────────────────────────────────────────────┘  │
   └──── GraphPort ── NeedsPort ── StatePort ── MoralGate ── AppraisalPort ────┘
          │              │            │            │              │
     Memory_Graph   Needs_System  State_Manager  moral_schema  Appraisal_Chain
       (M3)[REAL]    (M2)[REAL]    (M11)[REAL]   (shared)[REAL]  (M4)[REAL]

   PAD_Engine (Module 1): NO inbound arrow from DMN. DMN cannot reach it —
   no import, no handle, no delta (constraint 1 / Req 14).
```

## Components and Interfaces

DMN depends on narrow **Ports** (Protocols; Rule 6 "depend on a contract, inject fakes").
Methods marked **[REAL]** exist on the real module today (verified — the integration test
drives them). Every method DMN's Ports call is now **[REAL]** — the two GraphPort stage-gate
predicates and the AppraisalPort aha entry, previously flagged contract additions, were
closed additively by Module 8 (Daemon); see `.kiro/specs/daemon/requirements.md`
Requirement 13 and requirements.md OQ-1/OQ-2 (RESOLVED / IMPLEMENTED).

### `GraphPort` — Memory_Graph (Module 3, `daemon/graph_manager.py`)
Reads: `get_event_node`, `get_entity_node`, `get_uncertainty_node`,
`get_relational_stage` — all **[REAL]**.
Writes: `write_event_node`, `write_edge` (with `is_aha_edge`), `crystallize_emotion_node`
(critical-only), `update_uncertainty_status`, `set_relational_stage`,
`update_relationship_summary` (self + others — one path), `adjust_salience` — all **[REAL]**.
Categorical stage-gate evidence: `resolved_edge_exists` (faith gate) — **[REAL, reused]**;
`predictability_evidence` (Observing→Engaging), `dependability_evidence`
(Engaging→Invested) — **IMPLEMENTED — see `daemon/graph_manager.py` and
`tests/test_daemon.py`.** (Build Plan Module 3 Outputs promises "relational_stage gates"
lookups; these two were closed additively by Module 8 — Daemon Requirement 13 — and are now
public.)

### `AppraisalPort` — Appraisal_Chain (Module 4, `daemon/appraisal_chain.py`)
`submit_aha_insight(insight: AhaInsight)` — **IMPLEMENTED — see `daemon/appraisal_chain.py`
and `tests/test_daemon.py`.** The real chain exposes this dedicated, duck-typed entry point
(added additively by Module 8): DMN emits an insight EVENT; Appraisal_Chain produces the
categorical "I understood something new" second-order appraisal and routes the resulting
small POSITIVE byproduct delta through `PAD_Engine.apply_appraisal_delta`. DMN still never
builds or holds PAD (constraint 1) — it only ever constructs and passes an `AhaInsight`
event object, never a `PADDelta`.

### `NeedsPort` — Needs_System (Module 2, `daemon/needs_system.py`)
`get_energy() -> float` — **[REAL]**. Used only for the Energy < 20 shallow-pass gate,
reusing `ENERGY_CRITICAL` (= 20.0) from Module 2. DMN never touches the categorical need
states.

### `StatePort` — State_Manager (Module 11, `daemon/state_manager.py`)
`load_self_model() / save_self_model(sm)` — **[REAL]**. The narrowed self-model working
state (quality_record / consistency_flags / recent_learning_*; item 2 / F-6b).

### `MoralGate` — `moral_schema.matched_anti_patterns` (shared resource) [REAL]
`Callable[[str], Sequence[AntiPattern]]` — returns the named anti-patterns a candidate
matches (empty ⇒ clean). The default gate is the real shared function; injectable for tests.

### The DMN class
`DMN(*, graph, appraisal, needs, state, self_entity_id=None,
moral_gate=matched_anti_patterns, clock=_now)`. Public entry points (the Daemon contract):
- `run_idle_pass(pass_input) -> DMNPassResult` — reads Energy; Energy < 20 → SHALLOW, else
  FULL.
- `run_forced_partial_pass(pass_input) -> DMNPassResult` — FORCED_PARTIAL (Steps 1 + 4).

Both delegate to `_run(pass_input, pass_type)`, which loads the self-model once, runs Step 1,
runs Steps 2 & 3 **iff FULL**, runs Step 4, and saves the self-model once.

## Data Types

```python
class DMNPassType(Enum): FULL / SHALLOW / FORCED_PARTIAL

@dataclass BufferItem:            # a self-monitoring observation (DMN input)
    observed_event_ref: str       # the turn Aria observed; poignancy INHERITED from its EventNode
    reaction_event_ref: Optional[str]  # NEXT turn = user's observed reaction (None ⇒ not graded)
    meta_observation, entity_refs, learning_user, learning_self,
    honest_when_uncomfortable / pushed_back_when_appropriate /
    initiated_when_needed / acknowledged_mistake  # binary consistency observations

@dataclass ConnectionCandidate:   # Step-2 candidate (from Memory_Graph selection, via Daemon)
    node_a_ref, node_b_ref, already_connected, shares_context,
    both_high_salience, reveals_new_pattern   # categorical PERCEPTION facts (Module 3, build-time)

@dataclass AhaInsight:            # the second-order appraisal EVENT (NO PAD)
    node_a_ref, node_b_ref, edge_id, description

@dataclass DMNPassInput:          # everything one pass consumes (assembled by the Daemon)
    buffer, connection_candidates, active_uncertainty_refs, entity_refs,
    rupture_entity_refs, narrative_candidate, narrative_pattern_recurred,
    salience_adjustments, session_id, now
    # NOTE: NO self-report / Output-Gate / self-grade field (anti-flattery guard, Req 6)

@dataclass DMNPassResult:         # observability record (lets the Daemon act; lets tests assert)
    pass_type, step2_ran, step3_ran, buffer_poignancy, buffer_promoted,
    buffer_discarded, emotion_nodes, quality_appended, edges_written,
    aha_insights, uncertainties_resolved/abandoned, stage_transitions,
    narrative_status, narrative_written, narrative_block_reasons, ...
```

Reused, not redefined: `PoignancyCategory`, `RelationalStage`, `EdgeType`,
`UncertaintyStatus`, `Perspective` (graph_manager); `SelfModel`, `CONSISTENCY_FLAG_NAMES`,
`QUALITY_RECORD_MAX`, `QUALITY_VALUES` (state_manager); `matched_anti_patterns`, `AntiPattern`
(moral_schema); `ENERGY_CRITICAL` (needs_system).

## The Four Steps — detailed logic

### Step 1 — buffer → graph (poignancy INHERITED) + quality record
For each buffer item: read the OBSERVED turn's EventNode; **inherit** its
`poignancy_category` (F-6c — no re-appraisal). High/critical ⇒ promote to a new
meta-observation EventNode (distinct node population, item 10), reusing the observed turn's
q1/q2/q3 (OQ-7, "no re-appraisal, pure reuse"). Critical ⇒ also `crystallize_emotion_node`
using the observed EventNode's **recorded** `pad_delta` (graph memory, no live PAD — Req
14.3). Medium/low ⇒ discard (no partial storage). Then: **quality record** from the reaction
EventNode (below); **consistency flags** set binary from observations; **recent-learning**
accumulated into the self-model.

### The quality grade (categorical; from the OBSERVED reaction — the anti-flattery guard)
Inputs are locked by the docs (reaction `appraisal_q2` + topic continuation/pivot); the
exact truth table is the most-defensible categorical reading (OQ-4, build-time-tunable
POLICY — never a number):

| reaction `appraisal_q2` | topic | grade |
|---|---|---|
| negative | any | `poorly` |
| positive | continued | `responded_well` |
| positive | pivoted | `adequately` |
| neutral | continued | `adequately` |
| neutral | pivoted | `poorly` |
| VALENCE_UNCERTAIN | any | *not graded* (no invention) |

Topic continuation = the reaction turn shares ≥1 `entity_ref` with the observed turn (the
minimal graph-grounded categorical signal; embedding-topic refinement is build-time, OQ-4).
No reaction ⇒ not graded (no self-report fallback — the guard).

### Step 2 — connection / aha (FULL only)
For each candidate: skip if already connected or if it shares no context; else
`write_edge(connects, is_aha_edge = both_high_salience AND reveals_new_pattern)`. If aha ⇒
`AppraisalPort.submit_aha_insight(AhaInsight(...))` — the PAD shift is the appraisal's
byproduct, never written here (Req 9). The salience cutoff and explanatory-power criterion
are Module-3 build-time perception facts carried as candidate flags (OQ-3), not DMN scores.

### Step 3 — uncertainty revisiting (FULL only)
For each active uncertainty ref (read via `get_uncertainty_node`): if its
`trigger_event_ref` was newly connected in Step 2 ⇒ `RESOLVED_INFERRED`
(`resolution_path="dmn_consolidation"`); else if stale ⇒ `ABANDONED`
(`resolution_path="staleness"`). Staleness = `interaction_count ≥ 50` OR
`now − created ≥ 7 days` (v4; F-6d / item 10 — DMN evaluates, Memory_Graph stores).

### Step 4 — self-model + narrative + relational_stage
(a) Flush recent-learning-user/self to graph nodes, then clear (item 2). (b) Evaluate
relational_stage per active entity (below). (c) Apply any supplied recurrence-based
`salience_adjustments` via `adjust_salience` (recurrence detection is Module-3 substrate).
(d) Update the moral-gated narrative (below). Finally `save_self_model` once.

### The relational_stage evaluator (categorical; Addendum §2)
```
current = get_relational_stage(entity);  base = current or OBSERVING
if ruptured:                         # REALITY_CONTRADICTION (relayed from live appraisal)
    target = one_stage_down(base)    # exactly one down, floored at OBSERVING
else:
    target = base
    if base is OBSERVING and predictability_evidence(entity):  target = ENGAGING
    elif base is ENGAGING and dependability_evidence(entity):  target = INVESTED
    elif base is INVESTED and resolved_edge_exists(entity, FAITH_WINDOW): target = BONDED
    # BONDED: top of the ladder
if target is not base: set_relational_stage(entity, target)   # write only on a real transition
```
Pure categorical: each gate is a bool; advance ≤ 1 step; regression 1 step, floored;
rupture takes precedence. No score, no counting, no "percent to Bonded" (percentage test).
Recovery after regression is not time-based — re-advancement re-checks the same gate (needs
fresh qualifying evidence), exactly as Addendum §2 requires.

### The moral-gated narrative (item 8 / Addendum §8)
```
if candidate is None:                    status = no_candidate;          return
if not pattern_recurred:                 status = blocked_single_instance; return  # v4 Step 4
hits = moral_gate(candidate)             # moral_schema.matched_anti_patterns
if hits:                                 status = blocked_moral_gate;    return   # NOT written
if self_entity_id is None:               status = no_self_entity;        return
update_relationship_summary(self_entity_id, candidate);  status = written
```
The gate runs with no audience present (Addendum §8). DMN GATES + WRITES; it does not
generate the text (OQ-5 upstream concern).

## PAD-purity: how "DMN never writes PAD" is guaranteed (Req 9, 14)

- **Structural.** `dmn.py` does not import `pad_engine`; no PAD symbol is in the module
  namespace; no DMN attribute holds a PAD reference. No line calls `apply_appraisal_delta(`
  or constructs `PADDelta(`. Verified by a namespace scan + a source scan in the tests.
- **The aha path.** An aha becomes an `AhaInsight` EVENT handed to `AppraisalPort` — a
  description, not a delta. DMN cannot even express a PAD shift.
- **Live tripwire.** A test monkeypatches `PADEngine.apply_appraisal_delta` to raise, runs a
  full aha-forming pass beside a real, initialized PAD_Engine, and asserts PAD is
  byte-identical afterward and the mutator never fired.
- **Crystallization is graph memory, not feeling.** `crystallize_emotion_node` receives the
  observed EventNode's RECORDED `pad_delta` (already in the graph) — DMN reads no live PAD
  and writes to a memory node, not the PAD engine (Req 14.3).

## Error Handling

- **Missing observed EventNode.** If a buffer item's observed EventNode is absent, the item
  is skipped (nothing to inherit poignancy from) — no crash.
- **Missing reaction EventNode.** Quality is simply not graded (Req 6.3) — no self-report
  fallback.
- **Missing self EntityNode.** Narrative reports `no_self_entity` and is not written — no
  crash.
- **Stage-less entity.** `get_relational_stage` may return None; the effective base is
  OBSERVING; a transition writes only if the gate advances it (no spurious "observing"
  write).
- **VALENCE_UNCERTAIN reaction.** Not graded (Req 6.5) — never coerced to a category.
- **Graph is authoritative.** Poignancy, appraisal_q2, interaction_count, created, and the
  stage-gate booleans are read from the graph and used directly — DMN post-processes none of
  them into a number.

## Testing Strategy

Plain `pytest`, no `hypothesis` (matches Modules 1–5). Fakes injected via the Ports; the
real MemoryGraph / StateManager / moral_schema are driven in a dedicated integration test.
Proves:
1. **Never writes PAD:** namespace + source scan (no PAD import, no `apply_appraisal_delta(`,
   no `PADDelta(`); DMN holds no pad-ish attribute; a live tripwire keeps a real PAD_Engine
   byte-identical through a full aha pass; the aha routes to the appraisal port instead.
   (Req 9, 14)
2. **relational_stage categorical:** advance one step per gate; regress one step on rupture,
   floored at observing; rupture beats advancement; every written stage is a
   `RelationalStage` (never a number); repeating identical evidence never accumulates past
   one step (no counting). (Req 13)
3. **Moral gate:** a manipulative candidate ("You need me…") and a dishonest one
   ("I'm absolutely certain…") are BLOCKED and not written, even with no audience; a clean
   candidate with `pattern_recurred=True` is written; a single instance is not. Uses the
   REAL moral schema as the default gate. (Req 12)
4. **Quality from observed reaction:** grade comes from the reaction EventNode's q2 +
   continuation (observed q2 differs, proving it is the reaction, not self-report);
   negative→poorly; positive+continued→responded_well; neutral+pivot→poorly;
   VALENCE_UNCERTAIN→not graded; no reaction→not graded; and DMNPassInput/BufferItem expose
   no self-grade field. (Req 6)
5. **Energy < 20 shallow (Steps 1+4 only):** Energy 15 ⇒ SHALLOW, step2/step3 not run, no
   edge/aha, no uncertainty update, but buffer promoted + stage advanced; Energy 20 ⇒ FULL;
   boundary 19.999 ⇒ SHALLOW. Forced-partial ⇒ same Steps 1+4 regardless of Energy. (Req 3, 4)
6. **Buffer inherits poignancy:** HIGH observed ⇒ promoted; LOW/MEDIUM observed ⇒ discarded
   (same item, decided by the EventNode's poignancy); CRITICAL ⇒ promoted + crystallized; no
   re-appraisal call in a buffer-only pass. (Req 5)
7. **Step 3:** inferred-resolve when the trigger is newly connected; abandon on 50-turn and
   on 7-day staleness; leave fresh unconnected untouched. (Req 10)
8. **Real integration:** the actual MemoryGraph + StateManager + moral_schema driven
   end-to-end (buffer promotion + critical crystallization; quality persisted; categorical
   stage advance via real set/get; moral-gated narrative written to the real self EntityNode
   `relationship_summary`; and a moral-block leaves it untouched). Plus
   `test_real_graph_satisfies_the_methods_dmn_calls` — IMPLEMENTED — see
   `daemon/graph_manager.py` and `tests/test_dmn.py` — confirms the real graph now exposes
   EVERY GraphPort method DMN calls, including `predictability_evidence` and
   `dependability_evidence` (closed additively by Module 8; no longer flagged).

## Open Questions

See requirements.md OQ-1…OQ-7. **OQ-1 and OQ-2 are RESOLVED / IMPLEMENTED** (Module 8 closed
both gaps additively — see `.kiro/specs/daemon/requirements.md` Requirement 13):
`AppraisalPort.submit_aha_insight` is real (`daemon/appraisal_chain.py`), and
`predictability_evidence` / `dependability_evidence` /
`highest_salience_unconnected_candidates` are real (`daemon/graph_manager.py`). Remaining
open items: **OQ-3** high-salience cutoff &
explanatory power (build-time perception, Module 3); **OQ-4** quality truth table &
continuation detector (build-time policy); **OQ-5** crystallization PAD source + label
(build-time; recorded pad_delta used, no live PAD); **OQ-6** faith-gate window (build-time
lookback placeholder); **OQ-7** buffer meta-observation q1/q2/q3 reuse (no re-appraisal).
None are resolved by invention or by modifying another core module.


---

## dmn — tasks.md

# Implementation Plan — Module 6: DMN / Idle Consolidation

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing here reopens a locked flag (F-6b/F-6c/F-6d RESOLVED — see
requirements.md). Genuinely-undefined thresholds are TODO(build-time) placeholders, never
invented as a scored metric.

- [x] 1. Module scaffold + reuse-not-redefine imports (PAD-free).
  - Create `daemon/dmn.py` with a docstring citing the four constraints, v4 "Continuous
    Self-Awareness", the flag disposition (item 2/8/10/13, Addendum §2/§8), and the Port
    contracts.
  - Import categorical vocab from `graph_manager` (PoignancyCategory, RelationalStage,
    EdgeType, UncertaintyStatus, Perspective); `matched_anti_patterns` + `AntiPattern` from
    `moral_schema`; `SelfModel` + `CONSISTENCY_FLAG_NAMES` + `QUALITY_RECORD_MAX` +
    `QUALITY_VALUES` from `state_manager`; `ENERGY_CRITICAL` from `needs_system`.
  - Do NOT import `pad_engine` or any PAD symbol anywhere (Req 9.2, 14.1).
  - _Requirements: 14.1, 15.3_

- [x] 2. Module constants + enums.
  - `STALENESS_MAX_INTERACTIONS = 50`, `STALENESS_MAX_AGE = 7 days` (v4; F-6d/item 10).
  - `_FAITH_EVIDENCE_WINDOW` = 60d, clearly `TODO(build-time)` (OQ-6).
  - `DMNPassType` enum (FULL / SHALLOW / FORCED_PARTIAL). `_now` / `_parse_dt` helpers.
  - _Requirements: 2.2, 10.3, 13.3_

- [x] 3. Input/output dataclasses.
  - `BufferItem` (observed_event_ref, reaction_event_ref, meta_observation, entity_refs,
    learning_user/self, four binary consistency observations) — NO poignancy field
    (inherited, F-6c). `ConnectionCandidate` (categorical perception flags). `AhaInsight`
    (description, NO PAD). `DMNPassInput` (NO self-grade field — anti-flattery guard).
    `DMNPassResult` (observability).
  - _Requirements: 5.1, 6.2, 8.3, 9.1_

- [x] 4. Port Protocols (contracts; [REAL] vs [FLAG]).
  - `GraphPort` (reads + writes [REAL]; `resolved_edge_exists` [REAL, reused];
    `predictability_evidence`/`dependability_evidence` [FLAG]); `AppraisalPort`
    (`submit_aha_insight` [FLAG]); `NeedsPort` (`get_energy` [REAL]); `StatePort`
    (`load_/save_self_model` [REAL]); `MoralGate` = `matched_anti_patterns`.
  - _Requirements: 9.3, 15.1, 15.3_

- [x] 5. `DMN.__init__` + public entry points.
  - Inject graph/appraisal/needs/state + self_entity_id + moral_gate(default real) + clock.
  - `run_idle_pass` (Energy < `ENERGY_CRITICAL` → SHALLOW else FULL);
    `run_forced_partial_pass` (FORCED_PARTIAL). Both call `_run`.
  - _Requirements: 1.2, 2.1, 2.2, 4.1, 4.3_

- [x] 6. `_run` orchestration — steps IN ORDER; 2 & 3 only in FULL.
  - load_self_model once → Step 1 (always) → Steps 2&3 (FULL only) → Step 4 (always) →
    save_self_model once. Set `step2_ran`/`step3_ran`.
  - _Requirements: 3.1, 3.2, 3.3, 4.2_

- [x] 7. Step 1 — buffer → graph (poignancy INHERITED) + crystallization.
  - Read observed EventNode; inherit `poignancy_category` (F-6c, no re-appraisal). High/
    critical → `write_event_node` (meta-observation, reuse q1/q2/q3 — OQ-7). Critical →
    `crystallize_emotion_node` with the observed EventNode's RECORDED pad_delta (graph
    memory, no live PAD — Req 14.3). Medium/low → discard.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 14.3_

- [x] 8. Step 1 — quality record from OBSERVED reaction + `_grade_quality` + `_topic_continued`.
  - Read the reaction EventNode; grade from its `appraisal_q2` + entity-overlap continuation
    (categorical truth table, OQ-4). Append to the rolling-20 quality record. No reaction /
    VALENCE_UNCERTAIN → not graded (no self-report fallback). NO Output-Gate/self-grade input.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 9. Step 1 — consistency flags (binary) + recent-learning accumulation.
  - Set binary flags from observations (reuse `CONSISTENCY_FLAG_NAMES`); accumulate
    learning_user/self into the self-model.
  - _Requirements: 7.1, 7.2, 11.1_

- [x] 10. Step 2 — connection / aha formation (FULL only) → second-order appraisal EVENT.
  - Skip already-connected / no-shared-context. `write_edge(connects, is_aha_edge=…)`. On
    aha → `AppraisalPort.submit_aha_insight(AhaInsight)`; NO PAD (Req 9). Collect
    newly-connected node ids for Step 3.
  - _Requirements: 8.1, 8.2, 8.4, 9.1, 9.2, 9.3_

- [x] 11. Step 3 — uncertainty revisiting (FULL only): inferred-resolve + staleness.
  - For each active uncertainty: trigger newly connected → RESOLVED_INFERRED
    (dmn_consolidation); else stale (50-turn OR 7-day, `_is_stale`) → ABANDONED (staleness).
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 12. Step 4 — recent-learning flush + salience adjustments.
  - Write recent-learning-user/self to graph nodes, then CLEAR (item 2). Apply any supplied
    `salience_adjustments` via `adjust_salience`.
  - _Requirements: 11.1, 11.2, 11.3_

- [x] 13. Step 4 — relational_stage evaluator (categorical gates) + `_one_stage_down`.
  - `get_relational_stage` → apply the single applicable gate (predictability / dependability
    / faith via `resolved_edge_exists`); rupture → one step down (floored); write via
    `set_relational_stage` only on a real transition. No score, no counting.
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [x] 14. Step 4 — moral-gated self-continuity narrative.
  - Gate: pattern-recurred (v4) AND `matched_anti_patterns(candidate)` empty. Write to the
    self EntityNode's `relationship_summary` via `update_relationship_summary` (item 2). Gate
    runs with no audience (Addendum §8). DMN gates + writes, does not generate text (OQ-5).
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 15. Tests — `tests/test_dmn.py` (plain pytest, no hypothesis).
  - Never-writes-PAD (namespace + source scan + live tripwire + aha-routes-to-appraisal);
    relational_stage categorical (advance/regress one step, floor, rupture precedence, enum
    not number, no accumulation); moral gate blocks manipulative/dishonest narrative even
    with no audience; quality from observed reaction not self-report (+ no self-grade field);
    Energy<20 shallow = Steps 1+4 only (+ boundary + forced-partial); buffer inherits
    poignancy (high promoted / low+medium discarded / critical crystallized / no
    re-appraisal); Step 3 resolve+staleness; recent-learning flush+clear; REAL-interface
    integration end-to-end.
  - _Requirements: all_

- [x] 16. Verify.
  - `python3 -m pytest tests/test_dmn.py -q` green (44 passed); then `python3 -m pytest -q`
    stays 273 + 44 = 317. No modification to any other core module. Temp files cleaned
    (StateManager uses pytest `tmp_path`; MemoryGraph uses `:memory:`).
  - _Requirements: all_

## Notes

- **F-6b** (self-model vs Rule 7): RESOLVED, Resolution Log item 2 — split (fields 1–4 in
  `self_model.json`; narrative → self EntityNode `relationship_summary`, written by Step 4).
- **F-6c** (buffer poignancy): RESOLVED, Resolution Log item 13 — inherited from the observed
  EventNode; no re-appraisal.
- **F-6d** (staleness counter): RESOLVED, Resolution Log item 10 — interactions = user turns
  (`interaction_count`); DMN Step 3 evaluates 7d/50-turn; Memory_Graph stores.
- **relational_stage evaluator** = DMN Step 4 (item 10), batched during idle; gates = Addendum
  §2. **Quality record** = DMN Step 1 from the observed next-turn reaction (anti-flattery
  guard). **Narrative** moral-gated (item 8 / Addendum §8).
- **Flagged contract additions** (NOT implemented here; other modules unmodified):
  `AppraisalPort.submit_aha_insight` (OQ-1, Module 4); `GraphPort.predictability_evidence` /
  `dependability_evidence` + highest-salience-unconnected selection (OQ-2, Module 3).
- **Build-time placeholders** (not architectural gaps): `_FAITH_EVIDENCE_WINDOW` (OQ-6);
  high-salience cutoff / explanatory power (OQ-3, Module 3); quality truth table +
  continuation detector (OQ-4); crystallization label (OQ-5).

