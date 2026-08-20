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
