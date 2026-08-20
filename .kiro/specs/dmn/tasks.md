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
