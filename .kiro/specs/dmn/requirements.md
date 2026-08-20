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
