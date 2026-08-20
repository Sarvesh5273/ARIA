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
