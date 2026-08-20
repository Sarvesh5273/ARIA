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
