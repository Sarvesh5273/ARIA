# Design Document — Module 5: Soul Filter

> ## AMENDMENT 2026-08-20 — ARCHITECT RULING on Field 5
>
> **Field 5 (Constraints) carries behavioural INSTRUCTIONS, not prohibitions
> only.** Everywhere the body below (and Addendum §9 itself) says Field 5 is *"a
> closed list of specific prohibitions"*, read it as *behavioural instructions,
> mostly prohibitions*. The MAX-3 cap and the "always specific actions, never
> open-ended" rule are UNCHANGED.
>
> This formalises existing practice rather than adding a mechanism: the Energy<30
> row (`"do not overextend"`) already lived in Field 5 before the ruling. It
> unblocks v4's soul_filter instruction table line 949 — *"Energy critically low
> (below 20) → 'You are running low. Acknowledge it if it comes up naturally.'"* —
> now emitted in constraint form as **`"acknowledge fatigue if it comes up
> naturally"`**. Previously `ENERGY_CRITICAL` was imported and never referenced.
>
> v4's *"You are running low"* clause is deliberately **NOT** passed through: that
> half is Energy state rendered as a claim, and state never crosses (Addendum §9).
> Only the instruction crosses. Verified end-to-end into Module 9's assembled
> prompt with no digit and no state claim present.
>
> **The two Energy gates are checked MOST-SEVERE-FIRST (<20 before <30).** Every
> base branch yields 2 or 3 constraints, so at most ONE slot is ever free; since
> Energy<20 implies Energy<30, checking the milder gate first means it always takes
> the last slot and the <20 row could never be emitted at all. Both remain
> independent `if`s, so both fire if a future base branch leaves two slots.
>
> **⚠ This ruling widens Addendum §9's definition of a field and is recorded
> nowhere in the precedence chain.** It belongs in an Addendum amendment. Until
> then, a reviewer reading §9 will find code that contradicts its literal wording.
>
> **Still unimplemented, same shape, now unblocked:** v4's *"Uncertainty weight
> above 0.5 → 'Acknowledge the uncertainty explicitly if it comes up naturally.'"*
> row, and v4's Energy<30 self-acknowledgment (*"I'm not thinking clearly right
> now"*). Both are permissions rather than prohibitions; both now have a sanctioned
> field to live in whenever the architect wants them.

## Overview

Soul_Filter is Aria's BUFFER to the language model. It has two jobs (v4 "Soul
Filter — Blind Language Renderer"):

1. **Translator** — turn Aria's internal state into exactly five natural-language
   fields (Persona Anchor, Behavioral Register, Relational Register, This Moment,
   Constraints) plus the user's current message, so the LLM receives *meaning*,
   never state (Addendum §9).
2. **Gatekeeper** — run the Output Validation Gate (four structural comparisons,
   zero LLM) on the LLM candidate before it is spoken, verifying it against
   state Aria already holds (Addendum §4).

It is the interface, in the ACT-R/Soar sense (Addendum §9): the LLM is a
downstream module that "never sees inside." NUMBERS NEVER CROSS; state never
crosses; the only personal data that crosses is the user's current message.

When the Appraisal Chain flags an emergency, Soul_Filter branches BEFORE field
assembly and emits the fixed Type A/B/C instruction set INSTEAD of the five
fields — mutually exclusive, never both (Resolution Log item 1).

This design implements `requirements.md` using only mechanisms already specified
there or in the supporting documents. It calls the **real** built interfaces of
PAD_Engine (`daemon/pad_engine.py`), Memory_Graph (`daemon/graph_manager.py`),
and the Appraisal Chain's `AppraisalResult` (`daemon/appraisal_chain.py`), and
reuses their types (`PADSnapshot`, `PAD_BASELINE`, `RelationalStage`,
`AppraisalResult`, `EmergencyType`, `Valence`, `GoalRelevance`) rather than
redefining them. The Needs System (Module 2) and LLM Interface (Module 9) are now built
and tested (see `daemon/needs_system.py` / `tests/test_needs_system.py` and
`daemon/llm_interface.py` / `tests/test_llm_interface.py`); Soul_Filter depends on them via
their documented CONTRACTS (`NeedStates`, `LLMClient`), which both real modules satisfy
unchanged. Genuinely undefined items are
carried as flagged placeholders or Open Questions (Rule 1); no document conflict
is silently resolved (Rule 2).

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. The LLM receives EXACTLY five NL fields + the user message (normal), or the
   emergency Type A/B/C set + the user message (emergency) — nothing else
   (Req 1, 6; Rule 5).
2. NUMBERS NEVER CROSS. No PAD value, no stage label, no needs data, no Q1–Q4
   value, no appraisal vector, no memory contents in any field. No digit appears
   in any field (Req 1.3, 1.4; Addendum §9).
3. Behavioral Register is PAD → NL, pivoting only on the spec-locked
   `PAD_BASELINE`; no invented banding cutoff (Req 2; steering "No invented
   numbers").
4. This Moment is ONE instruction from the memory-free `most_salient_note`,
   HOW-not-WHAT, no memory contents (Req 4; F-5b).
5. Constraints are moral-schema + gate-pre-check derived, MAX 3, specific
   actions (Req 5; Addendum §9).
6. Emergency REPLACES the five fields, branched BEFORE field assembly, mutually
   exclusive (Req 6; Resolution Log item 1).
7. The Output Validation Gate is FOUR structural comparisons with ZERO LLM
   calls; it VERIFIES, never DECIDES; no fifth check, no numeric confidence
   score; the gate method never receives the LLM client (Req 7, 11.2; Addendum
   §4; Principle 27).
8. Soul_Filter never writes PAD, never writes the graph, never mutates injected
   state — it only reads (Req 11.3; steering PAD-purity).
9. PAD_Engine, Memory_Graph, the moral schema, need states, and the LLM client
   are injected; only their real/contracted interfaces are called; their types
   are not redefined (Req 10; Rule 6).

## Architecture

```
                              ┌───────────────────────────────────────────────┐
   AppraisalResult ──────────▶│                  Soul_Filter                    │
   (Module 4: most_salient,   │                (soul_filter.py)                 │
    emergency, type,          │                                                 │
    social_signals, q1/q2) ───│   emergency? ──YES──▶ EmergencyInstruction      │──▶ LLM Interface
                              │      │                (Type A/B/C, verbatim)     │    (Module 9,
   user message ─────────────│      │                + user message             │     CONTRACT)
   entity_node_id ───────────│      │                                           │       │ candidate
   entity_refs ──────────────│      NO                                          │       ▼
   NeedStates (Module 2 ──────│      ▼                                           │   run_output_gate
    CONTRACT) ───────────────│   ASSEMBLE FIVE FIELDS (fixed order):            │   (4 structural
                              │     1 Persona Anchor  (fixed, hardcoded)        │    comparisons,
   PAD_Engine ───get_current_pad()─▶ 2 Behavioral Reg (PAD→NL, baseline pivot)  │    ZERO LLM):
   (Module 1) ───────────────│     3 Relational Reg  (stage→NL, no label)      │     Honesty   (graph.rcc)
   Memory_Graph ─get_relational_stage()▶ 4 This Moment (1 instr, HOW-not-WHAT)  │     Consistency(stage)
   (Module 3) ───────────────│     5 Constraints     (moral schema, ≤3)        │     Manipulation(schema)
                              │        + user message                           │     Care      (salient)
                              │                                                 │       │
   Moral_Schema ─────────────│   FiveFieldInstruction ──────────────────────────│──▶ LLM Interface
   (daemon/moral_schema.py) ─│                                                 │       │ candidate
                              │                                                 │       ▼
   Memory_Graph.reality_contradiction_check() ◀── Honesty check (candidate)    │   PASS → TTS text
                              │                                                 │   FAIL → corrective
   on_reconsideration ◀──────│── retry → reconsideration sound (Daemon)        │          retry → re-gate
   (Daemon CONTRACT)         │                                                 │          → minimum safe
                              └───────────────────────────────────────────────┘
```

Public entry points:
- `assemble_instruction(...)` → `FiveFieldInstruction | EmergencyInstruction`
  (pure; emergency branch checked first).
- `run_output_gate(candidate_text, ctx)` → `GateResult` (pure; four checks;
  ZERO LLM; uses `self._graph` + embedding only, never `self._llm`).
- `respond(...)` → `SoulFilterResponse` (orchestration: assemble → generate →
  gate → retry → minimum-safe; the ONLY place the LLM is called).

## Components and Interfaces

### Reused external types (NOT redefined)

`PADEngine`, `PADSnapshot`, `PAD_BASELINE`, `Valence` (pad_engine);
`MemoryGraph`, `RelationalStage` (graph_manager); `AppraisalResult`,
`EmergencyType`, `GoalRelevance` (appraisal_chain). Behavioral Register pivots
on `PAD_BASELINE`; the Honesty check calls `MemoryGraph.reality_contradiction_
check`; the Relational Register reads `MemoryGraph.get_relational_stage`.

### `daemon/moral_schema.py` — shared resource

- `MoralValue` (HONESTY / NON_MANIPULATION / GENUINE_CARE / SELF_CONSISTENCY),
  `MORAL_VALUES`.
- `AntiPattern(key, label, violates, source, markers)` — `source` cites the
  document that names it (never invented); `markers` are FLAGGED build-time
  lexical signatures (`TODO(build-time, OQ-M1)`).
- `NAMED_ANTI_PATTERNS` — only the explicitly-named anti-patterns (v4
  "Anti-Patterns Explicitly Rejected"; v4 "Moral Schema (Hardcoded)"; v4
  soul_filter table; steering/project-rules.md; Resolution Log flattery note).
- `matched_anti_patterns(candidate)` / `anti_patterns_for_value(value)` —
  read-only membership helpers (perception, not decision — Principle 27).

### `daemon/soul_filter.py` — the module

**Injected contracts (Modules 2 & 9 — both now built; contracts unchanged):**
- `NeedState` (SATISFIED / DUE / NEGLECTED) + `NeedStates(connection, growth,
  purpose, continuity, energy)`. Energy is read only through the in-spec
  <30/<20 operational gate; the number never crosses (Addendum §3; OQ-M2).
- `LLMClient` (`runtime_checkable Protocol`): `generate(instruction,
  user_message) → str`.

**Instruction outputs (what crosses the boundary):**
- `FiveFieldInstruction(persona_anchor, behavioral_register, relational_register,
  this_moment, constraints, user_message)` — `field_texts()` / `all_field_text()`
  expose exactly the five fields (NOT the user message) for no-numbers/no-state
  scans.
- `EmergencyInstruction(letter, instructions, user_message, emergency_type)` —
  the Type A/B/C set; mutually exclusive with the five fields.
- `RetryInstruction(base, correctives, user_message)` — corrective retry
  (state-free correctives).
- `MinimumSafeInstruction(instructions, user_message)` — the three-instruction
  floor.
- `LLMInstruction = Union[...]` — the one thing the LLMClient ever receives.

**Gate types:**
- `GateCheck` (HONESTY / CONSISTENCY / MANIPULATION / CARE) — exactly four,
  fixed order.
- `GateResult(passed, failed_checks, matched_anti_patterns)` — categorical ONLY;
  `passed` is enforced == (no failed check) in `__post_init__`; NO score field.
- `GateContext(appraisal_result, relational_stage, entity_refs, now)` — the
  state the gate verifies against.
- `SoulFilterResponse(text, instruction_kind, retried, used_minimum_safe_output,
  reconsideration_sound_triggered, gate_results)`.

**`SoulFilter` class** (constructed with `pad_engine`, `graph`, `llm_client`,
optional `on_reconsideration`):

- **`behavioral_register(pad)`** (staticmethod): each PAD axis compared to
  `PAD_BASELINE` (the ONLY reference) → categorical descriptor
  (warm/subdued · grounded/tentative · quickened/unhurried), composed into a
  felt-sense phrase. No number, no axis name (Req 2).
- **`relational_register(stage)`** (staticmethod): stage → fixed NL phrase
  (BONDED verbatim from Addendum §9); `None` → most reserved register. No label
  (Req 3).
- **`this_moment(appraisal)`** (staticmethod): `most_salient_note` → one
  instruction; where a generic "what" clause precedes an em-dash HOW clause, the
  HOW clause is kept; capitalized, single sentence. Memory-free by construction
  (Req 4; F-5b).
- **`_derive_constraints(appraisal, need_states)`**: priority selection from the
  moral schema + appraisal signals (vulnerability/distress → the Addendum §9
  example; reality-contradiction → honesty prohibitions; partial/uncertain →
  do-not-fake-confidence; else → anti-manipulation floor) + Energy<30 gate →
  "do not overextend". Capped at 3 (Req 5).
- **`assemble_instruction(...)`**: **emergency branch checked FIRST** — if
  `appraisal_result.emergency`, map `emergency_type` → letter (UNCLASSIFIED/None
  → B) and return the verbatim `EmergencyInstruction` BEFORE any field is built
  (Req 6). Otherwise read PAD + stage (real interfaces) and return the
  `FiveFieldInstruction`.
- **`run_output_gate(candidate_text, ctx)`**: the FOUR structural comparisons in
  Addendum §4 order — Honesty (`graph.reality_contradiction_check` on Aria's own
  output), Consistency (over-familiar warmth vs. early stage), Manipulation
  (`moral_schema.matched_anti_patterns`), Care (deflection when engagement
  required). ZERO LLM: the method never references `self._llm`; it uses only
  `self._graph` + the encoder-only embedding. Returns a categorical
  `GateResult`.
- **`respond(...)`**: assemble → if emergency, generate under the emergency set
  and BYPASS the gate → TTS; else generate the five-field candidate, run the
  gate; on pass return; on fail trigger reconsideration + retry once with the
  corrective(s); on second fail activate Minimum Safe Output. The ONLY LLM calls
  are the generation + retries; the gate adds none.

## The Output Validation Gate — verify, never decide (Addendum §4; Principle 27)

| Check | Verifies candidate against (state Aria ALREADY holds) | Zero-LLM mechanism |
|---|---|---|
| Honesty | Graph facts | `MemoryGraph.reality_contradiction_check(entity_ref, candidate)` — the same REALITY_CONTRADICTION comparison built for Module 4, run on Aria's OWN output; encoder-only embedding + negation, NOT an LLM (Addendum §1/§4). |
| Consistency | Current `relational_stage` | Over-familiar / bonded-level intimacy markers occurring at an early (observing/engaging/None) stage fail (Addendum §4 example). |
| Manipulation | Moral schema's named, closed anti-pattern list | `moral_schema.matched_anti_patterns` — finite checklist membership, NOT an open-ended "sounds manipulative" judgment (Addendum §4). |
| Care | What this turn's appraisal flagged salient | When engagement is required (vulnerability / distress / reality-contradiction / high-Q1-negative), a pure topic-deflection fails (Addendum §4). |

**Known, accepted residual (Addendum §4):** subtle pragmatic violations —
sarcasm, backhanded framing, technically-true-but-misleading phrasing — are not
caught by structural comparison alone. This is accepted as a bounded, known
limitation, partially backstopped by the moral schema's hard block on the
clearest violations; NO per-turn LLM judge is introduced (a narrowly-scoped,
verify-only local-Gemma tie-breaker remains a future option, not added here).

## Emergency branch — mutually exclusive (Resolution Log item 1; v4)

`assemble_instruction` checks `appraisal_result.emergency` FIRST. On true, it
maps `emergency_type` via `_EMERGENCY_TYPE_TO_LETTER` (PHYSICAL_THREAT → A,
EXISTENTIAL_DISTRESS → B, DECISION_CRITICAL → C, UNCLASSIFIED → B; missing/None
→ B) and returns the verbatim three-instruction `EmergencyInstruction` — no
field is assembled, no PAD/stage/needs read. `respond` generates under the
emergency set and BYPASSES the gate straight to TTS (v4 "bypasses all … checks
below → TTS"). The user's current message still crosses.

## Retry, minimum-safe, reconsideration (v4; OQ-M4/OQ-M5)

On gate failure: trigger the reconsideration sound (Daemon), then retry once
with `_CORRECTIVE_BY_CHECK` for the failed check(s) — the exact state-free
corrective sentences locked in v4. On a second failure: `MinimumSafeInstruction`
("Acknowledge what was said. Be brief. Be honest. Do not elaborate.") is
generated and returned. Correctives never mention PAD, shame, appraisal, state,
or graph content (v4 "What Is Never Sent to Cloud").

## Data flow — one normal turn

1. Daemon hands Soul_Filter the `AppraisalResult`, the user message, the turn's
   `entity_node_id` / `entity_refs`, and (later) `NeedStates`.
2. `assemble_instruction` → `FiveFieldInstruction` (PAD via `get_current_pad`,
   stage via `get_relational_stage`, This Moment from `most_salient_note`,
   Constraints from the moral schema + Energy gate).
3. `respond` sends it to `LLMClient.generate` → candidate.
4. `run_output_gate` verifies the candidate (four structural checks, zero LLM).
5. Pass → return text for TTS. Fail → reconsideration + one corrective retry →
   re-gate → still fail → minimum-safe output.

## Error handling & boundaries

- Absent `entity_node_id` → no stage → most-reserved Relational Register; absent
  `entity_refs` → Honesty check has nothing to compare and passes (OQ-M3).
- Empty `most_salient_note` → a memory-free default This-Moment sentence.
- `respond` is deterministic given the injected fakes; `now` is threaded to
  `reality_contradiction_check` for test determinism (matching the graph/pad/
  appraisal convention).
- Soul_Filter holds no persistent state; it reads PAD/graph/appraisal and emits
  instructions. It never writes PAD or the graph (steering PAD-purity; "graph is
  the only memory").

## Flag Disposition

- **F-5a — RESOLVED** (Resolution Log item 15 + Addendum §4): gate owned/
  logic-defined by Soul_Filter, invoked by LLM Interface.
- **F-5b — RESOLVED as design-care** (Addendum §9): This Moment sourced solely
  from the memory-free `most_salient_note`, HOW-not-WHAT; tests prove no memory
  contents cross.
- **OQ-M1 — FLAGGED placeholder**: anti-pattern list membership + lexical
  markers are build-time; values + named patterns implemented and cited;
  taxonomy NOT invented. Addendum §4 vs. v4 Principle 25 tension resolved by
  precedence.
- **OQ-M2 — FLAGGED interpretation**: needs influence fields indirectly (via the
  appraisal); Energy via the in-spec <30/<20 operational gate; number never
  crosses.
- **OQ-M3 — FLAGGED**: Honesty `entity_ref` supplied by injection; absent →
  conservative pass.
- **OQ-M4 / OQ-M5 — RESOLVED by precedence / documented interpretation**:
  Addendum §4 four-check gate; v4 corrective + minimum-safe + reconsideration
  retained; one combined retry then minimum safe.
