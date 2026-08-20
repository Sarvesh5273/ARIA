# Implementation Plan — Module 5: Soul Filter

This plan implements `design.md` exactly as written. Each task is small and
independently testable. It targets `daemon/soul_filter.py` and the shared
resource `daemon/moral_schema.py`, calling the REAL `daemon/pad_engine.py`,
`daemon/graph_manager.py`, and `daemon/appraisal_chain.py` interfaces and the
injected `NeedStates` / `LLMClient` CONTRACTS. No other module's files are
modified. `pad_engine.py`, `graph_manager.py`, and `appraisal_chain.py` are
NOT modified.

## Quoted from design.md (verified against current file content)

**Reused external types (NOT redefined):** `PADEngine`, `PADSnapshot`,
`PAD_BASELINE`, `Valence` (pad_engine); `MemoryGraph`, `RelationalStage`
(graph_manager); `AppraisalResult`, `EmergencyType`, `GoalRelevance`
(appraisal_chain). The Behavioral Register pivots on `PAD_BASELINE`; the Honesty
check calls `MemoryGraph.reality_contradiction_check`; the Relational Register
reads `MemoryGraph.get_relational_stage`; This Moment reads
`AppraisalResult.most_salient_note`.

**Own types:** `MoralValue`, `AntiPattern` (moral_schema); `NeedState`,
`NeedStates`, `LLMClient`, `EmergencyLetter`, `FiveFieldInstruction`,
`EmergencyInstruction`, `RetryInstruction`, `MinimumSafeInstruction`,
`GateCheck`, `GateResult`, `GateContext`, `SoulFilterResponse`, `SoulFilter`.

**The boundary invariants (Hard Constraints):** exactly five NL fields + user
message (or emergency Type A/B/C + user message); NUMBERS NEVER CROSS (no digit
in any field); Behavioral Register pivots only on `PAD_BASELINE`; This Moment is
one memory-free instruction; Constraints ≤ 3; emergency REPLACES the five fields
before assembly; the gate is FOUR structural comparisons with ZERO LLM
(verify-not-decide, no fifth check, no score, gate never holds the LLM client);
Soul_Filter never writes PAD/graph.

**Flag disposition:** F-5a RESOLVED (ResLog 15 + Addendum §4), F-5b RESOLVED as
design-care (Addendum §9). OQ-M1 (anti-pattern list closure + markers) FLAGGED
placeholder — values + named patterns implemented/cited, taxonomy NOT invented.
OQ-M2 (needs→field) FLAGGED interpretation. OQ-M3 (Honesty entity_ref)
FLAGGED. OQ-M4/OQ-M5 (three-vs-four-check gate; retry shape) RESOLVED by
precedence / documented interpretation.

---

## Tasks

- [x] 1. Create the shared moral-schema resource (`daemon/moral_schema.py`)
  - `MoralValue` (honesty / non-manipulation / genuine care / self-consistency)
    + `MORAL_VALUES`.
  - `AntiPattern(key, label, violates, source, markers)`; `NAMED_ANTI_PATTERNS`
    enumerating ONLY doc-named anti-patterns, each with a `source` citation and
    FLAGGED `TODO(build-time, OQ-M1)` markers. Record the Addendum §4 vs. v4
    Principle 25 tension + its precedence resolution in the module docstring.
  - `matched_anti_patterns` / `anti_patterns_for_value` read-only helpers
    (perception, not decision).
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 2. Set up module scaffold and reused imports (`daemon/soul_filter.py`)
  - Import the REAL types from `daemon.pad_engine` (`PADEngine`, `PADSnapshot`,
    `PAD_BASELINE`, `Valence`), `daemon.graph_manager` (`MemoryGraph`,
    `RelationalStage`), `daemon.appraisal_chain` (`AppraisalResult`,
    `EmergencyType`, `GoalRelevance`), and `daemon.moral_schema`. Do NOT
    re-declare any of these.
  - _Requirements: 10.1_

- [x] 3. Define the injected CONTRACTS for the not-yet-built modules
  - `NeedState` + `NeedStates` (four categorical needs + continuous Energy;
    Energy read only via the <30/<20 gate — number never crosses).
  - `LLMClient` (`runtime_checkable Protocol`): `generate(instruction,
    user_message) → str`.
  - _Requirements: 10.2, 10.3_

- [x] 4. Define the instruction output types
  - `EmergencyLetter` (A/B/C); `FiveFieldInstruction` (fixed field order +
    `field_texts()` / `all_field_text()` exposing ONLY the five fields);
    `EmergencyInstruction`; `RetryInstruction`; `MinimumSafeInstruction`;
    `LLMInstruction` union.
  - Unit tests: `FiveFieldInstruction` field order is exactly persona /
    behavioral / relational / this_moment / constraints; `all_field_text`
    excludes the user message.
  - _Requirements: 1.1, 1.2, 6.1, 6.2, 8.1, 8.3_

- [x] 5. Define the gate result/context types (categorical only)
  - `GateCheck` (exactly four, fixed Addendum §4 order); `GateResult`
    (`passed`, `failed_checks`, `matched_anti_patterns`; `passed` enforced ==
    no-failed-check in `__post_init__`; NO score field); `GateContext`;
    `SoulFilterResponse`.
  - Unit tests: `GateCheck` has exactly four members; `GateResult` has no
    score/confidence/percent field.
  - _Requirements: 7.1, 7.8, 11.1_

- [x] 6. Hardcode the fixed content
  - `PERSONA_ANCHOR` (fixed, stateless, digit-free); `_EMERGENCY_SETS`
    (Type A/B/C verbatim from v4); `_EMERGENCY_TYPE_TO_LETTER` (UNCLASSIFIED/
    None → B); `_CORRECTIVE_BY_CHECK` (v4 verbatim, state-free);
    `_RELATIONAL_REGISTER` (+ default); `ENERGY_LOW`/`ENERGY_CRITICAL`.
  - Unit tests: persona has no digit; each emergency set is exactly three
    verbatim instructions.
  - _Requirements: 6.3, 6.4, 8.1, 8.2_

- [x] 7. Implement the FLAGGED build-time lexicons
  - `_OVERFAMILIAR_INTIMACY_MARKERS` (Consistency) and `_DEFLECTION_MARKERS`
    (Care), each `TODO(build-time, OQ-M1)`; the `_contains_any` helper
    (perception, substring membership).
  - _Requirements: 7.5, 7.7 (mechanism); Build-Time Tuning Constants (markers)_

- [x] 8. Implement the field translators (state → NL; numbers/state never cross)
  - `behavioral_register(pad)` — per-axis above/below `PAD_BASELINE` → descriptor
    phrase, no number/axis-name.
  - `relational_register(stage)` — stage → NL phrase (BONDED verbatim); `None`
    → reserved default; no label.
  - `this_moment(appraisal)` — one instruction from `most_salient_note`, prefer
    the HOW clause, memory-free.
  - `_derive_constraints(appraisal, need_states)` — moral-schema + appraisal
    signals + Energy<30 gate, capped at 3, specific prohibitions.
  - Unit tests: no digit in any translator output; stage label never appears;
    This Moment drops the generic "what" clause; Constraints ≤ 3.
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_

- [x] 9. Implement `assemble_instruction` with the emergency branch FIRST
  - If `appraisal_result.emergency`: map type → letter and return the verbatim
    `EmergencyInstruction` BEFORE any field is built. Else read PAD (real
    `get_current_pad`) + stage (real `get_relational_stage`) and return the
    `FiveFieldInstruction`.
  - Unit tests: emergency returns `EmergencyInstruction`, NOT `FiveFieldInstruction`
    (no `persona_anchor` attr); type→letter mapping incl. UNCLASSIFIED/None → B;
    user message crosses in both; five-field path uses real PAD/graph values.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 10. Implement `run_output_gate` — four structural comparisons, ZERO LLM
  - Honesty: `graph.reality_contradiction_check(entity_ref, candidate, now=)` on
    Aria's own output. Consistency: over-familiar warmth vs. early stage.
    Manipulation: `moral_schema.matched_anti_patterns`. Care: deflection when
    engagement required. Return categorical `GateResult` in Addendum §4 order.
    The method must NOT reference `self._llm`.
  - Unit tests: gate makes ZERO LLM calls (FakeLLM call-count 0; RaisingLLM does
    not raise); gate signature has no LLM param; gate uses the encoder embedding
    (Honesty) but no generation; each check fails on a clear violator and passes
    on a clean reply; failed checks are ordered; no numeric score.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 11.2_

- [x] 11. Implement `respond` — assemble → generate → gate → retry → minimum-safe
  - Emergency: generate under the emergency set, BYPASS the gate → TTS. Normal:
    generate five-field candidate; gate; pass → return; fail → trigger
    reconsideration + one corrective retry; second fail → Minimum Safe Output.
    The ONLY LLM calls are generation + retries.
  - Unit tests: emergency bypasses the gate (a would-fail candidate still
    returns; `gate_results == ()`); a moral-schema-violating candidate is
    rejected + retried (reconsideration fired, corrective carried, second clean
    candidate returned); double failure → minimum-safe; a clean candidate passes
    with no retry and exactly one LLM call.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 11.3_

- [x] 12. Wire the reconsideration-sound trigger (Daemon CONTRACT)
  - Optional injected `on_reconsideration` callback; `_trigger_reconsideration`
    fires it on any retry; the response also carries the
    `reconsideration_sound_triggered` flag.
  - Unit test: the callback fires exactly once on a single-retry turn.
  - _Requirements: 8.1_

- [x] 13. Full verification
  - `python3 -m pytest tests/test_soul_filter.py -q` green; then
    `python3 -m pytest -q` shows no regression (161 prior + new). Confirm
    `pad_engine.py` / `graph_manager.py` / `appraisal_chain.py` unmodified.
  - _Requirements: all_

## Verification status

- `tests/test_soul_filter.py`: **33 passed**.
- Full repo suite: **194 passed** (161 prior + 33 new), no regression.
- `daemon/pad_engine.py`, `daemon/graph_manager.py`, `daemon/appraisal_chain.py`:
  read-only, not modified.
