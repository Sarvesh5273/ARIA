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

- [x] 1. Set up module scaffold and reused imports
  - Create `daemon/appraisal_chain.py`. Import the REAL types from
    `daemon.pad_engine` (`PADEngine`, `PADDelta`, `PADSnapshot`, `Valence`) and
    `daemon.graph_manager` (`MemoryGraph`, `PoignancyCategory`, `Perspective`,
    `UncertaintyType`, `UncertaintyStatus`, `EdgeType`, `EmbeddingModel`,
    `EventNode`, `Edge`). Do NOT re-declare any of these.
  - Add stdlib imports (`Enum`, `dataclass`, `Optional`, `List`, `Mapping`,
    `Tuple`, `Sequence`, `datetime`).
  - _Requirements: 14.4 (inject/reuse, no redefinition)_

- [x] 2. Implement the own enums and dataclasses
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

- [x] 3. Implement module constants as flagged placeholders
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

- [x] 4. Implement `AppraisalChain.__init__` (dependency injection)
  - Store injected `pad_engine`, `graph`, `embedding_model`, `config`.
  - Initialize in-memory conflict-arc bookkeeping (per-entity counters).
  - Do NOT instantiate a concrete embedding model; do NOT hold a PAD-writing
    handle other than `pad_engine`.
  - Unit test: constructing with a real `PADEngine`, in-memory `MemoryGraph`,
    and a `FakeEmbedding` succeeds; the chain exposes no attribute that is a
    concrete embedding model class instance it created itself.
  - _Requirements: 14.4_

- [x] 5. Implement the Social-Signal Pre-Pass — DISTRESS_MARKER (lexical)
  - `_distress_marker(text) -> bool`: count absolutist + negative-emotion words
    and first-person-singular density; return True iff the count meets
    `_DISTRESS_MIN_MARKERS`. The count is PERCEPTION and stays inside this
    function — reduced to a boolean before any appraisal branch sees it.
  - Unit tests: absolutist/negative text → True; neutral text → False. Do NOT
    assert the exact count threshold value.
  - _Requirements: 3.2_

- [x] 6. Implement the Social-Signal Pre-Pass — VULNERABILITY_DISCLOSURE
  - `_vulnerability(text) -> bool`: embed `text` via the injected model and
    compare (cosine) to embedded `_VULNERABILITY_EXEMPLARS`; True iff max
    similarity ≥ `_VULNERABILITY_SIM_CUTOFF`.
  - Reuse a cosine helper (may import `daemon.graph_manager._cosine` or define a
    local equivalent — do not depend on a private if a public path exists;
    a small local cosine is acceptable and avoids private coupling).
  - Unit test (with `FakeEmbedding` table): text embedded near an exemplar →
    True; far text → False. Cutoff value itself not asserted.
  - _Requirements: 3.3; F-4e_

- [x] 7. Implement the Social-Signal Pre-Pass — REALITY_CONTRADICTION + conflict arc
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

- [x] 8. Implement Stage 0 — input classification
  - `_stage0_classify_input(text, signals) -> bool`: conservative categorical
    heuristic (non-empty/non-whitespace and carries an appraisable referent);
    empty/contentless → unparseable. Comment `TODO(build-time, OQ-E)` on the
    fuller criterion.
  - Unit tests: `"   "` → unparseable (False); a normal sentence → True.
  - _Requirements: 1.1; OQ-E_

- [x] 9. Implement Stage 2 — categorical Q1, Q2, Q3
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

- [x] 10. Implement Stage 2 — Q4 (qualitative) + needs-implications flag
  - `_q4(q1, q2, q3, signals, need_states) -> (notes: Optional[str],
    has_needs_implications: bool)`: qualitative notes; the boolean is decided
    categorically (a need is implicated by the appraisal / social tags). Keep
    normal-turn notes purely qualitative (ResLog 12).
  - Unit tests: a vulnerability disclosure → `has_needs_implications True` with a
    Connection note; a flat neutral turn → False, notes null/partial.
  - _Requirements: 4.4_

- [x] 11. Implement Stage 2 — emergency gate (transient coping_potential)
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

- [x] 12. Implement Stage 3 — output synthesis (full/partial/secondary + GRAPH_CONFLICT)
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

- [x] 13. Implement Stage 4 — `_build_pad_delta` (byproduct, no formula)
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

- [x] 14. Implement the secondary-appraisal delta
  - `_secondary_appraisal_delta() -> PADDelta`: fixed categorical profile —
    pleasure down (small tier), arousal up (a tier), dominance down (small
    tier), `valence = VALENCE_UNCERTAIN` — matching v4's described byproduct.
  - Used by Stage 0 (INPUT_UNCERTAIN) and Stage 3 (3 unclear).
  - Unit test: signs are (pleasure<0, arousal>0, dominance<0) and valence is
    VALENCE_UNCERTAIN.
  - _Requirements: 7.1, 8.1_

- [x] 15. Implement Stage 4 application through PAD_Engine (the only PAD write)
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

- [x] 16. Implement Stage 5 — needs pressure as retrieval preference only
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

- [x] 17. Implement Stage 6 — poignancy (categorical) + graph write
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

- [x] 18. Implement uncertainty resolution (RESOLVED_CONFIRMED + catch-up)
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

- [x] 19. Implement `appraise(...)` — orchestrate Stages 0–6, return AppraisalResult
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

- [x] 20. Boundary / anti-machine API-surface tests
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

- [x] 21. Wire together, run the full suite, and confirm flag/OQ status in code
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
