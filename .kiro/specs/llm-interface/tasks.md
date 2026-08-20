# Implementation Plan — Module 9: LLM Interface

This plan implements `design.md` exactly as written. Each task is small and
independently testable. All tasks are complete; the suite is green
(`python3 -m pytest tests/test_llm_interface.py -q` → 35 passed; full suite →
229 passed, 194 prior + 35 new, no regressions).

## Quoted from design.md (verified against current file content)

**The contract this module implements** (imported, never redefined — Rule 6),
from `daemon/soul_filter.py`:
```python
@runtime_checkable
class LLMClient(Protocol):
    def generate(self, instruction: "LLMInstruction", user_message: str) -> str: ...

LLMInstruction = Union[
    FiveFieldInstruction, EmergencyInstruction, RetryInstruction, MinimumSafeInstruction
]
```

**The fallback lifecycle** (design.md "Fallback lifecycle"): try cloud first →
success returns verbatim and unloads Gemma if it was loaded (Restore) → cloud
`LLMTransportError` loads Gemma (once) and serves the SAME prompt → local
`LLMTransportError` raises `LLMUnavailableError`. "Loads on cloud failure,
unloads on restore" (v4 Brain Structure).

**The F-9a mechanism** (design.md): `assemble_prompt` is a pure function of
`(instruction, user_message)`; `generate` calls it once and shares the one
`AssembledPrompt` with whichever backend serves — identical inputs → identical
prompt → identical bytes to cloud and Gemma (Resolution Log item 14).

---

## Tasks

- [x] 1. Module scaffold and contract import
  - Create `daemon/llm_interface.py`; import `LLMClient`, `LLMInstruction`, and
    the four instruction dataclasses from `daemon.soul_filter` (never redefine).
  - Confirm no circular import: `soul_filter.py` does not import
    `llm_interface` (verified).
  - _Requirements: 1.1, 10.1, 10.2_

- [x] 2. Transport failure signals
  - `LLMTransportError` — the ONLY signal a transport uses to mean "unavailable
    → fall back". `LLMUnavailableError` — raised by the Interface when both
    backends fail (never fabricate).
  - _Requirements: 8.3, 9.1, 9.2_

- [x] 3. `AssembledPrompt` frozen dataclass
  - Fields `instruction_text: str`, `user_message: str`, `kind: str`; method
    `as_text()` = `instruction_text` + blank line + `user_message` (no injected
    labels/numbering). Frozen → structural equality (the F-9a substrate).
  - Unit test: `as_text()` is exactly framing + user message; the user's digits
    appear only in the user-message portion.
  - _Requirements: 2.4, 3.1_

- [x] 4. `assemble_prompt(instruction, user_message)` — pure, blind, deterministic
  - Dispatch on concrete instruction type; render framing from ONLY the
    instruction's own fields; pair with the `user_message` argument verbatim
    (no inspection/reconciliation). Unknown type → `TypeError`.
  - Unit tests: deterministic for identical inputs; unknown type raises;
    `user_message` argument (not the instruction's own copy) is what crosses.
  - _Requirements: 2.1, 3.1, 3.4, 5.3, 7.4_

- [x] 5. Per-kind renderers
  - `_render_five_field`: Persona Anchor, Behavioral Register, Relational
    Register, This Moment in FIXED ORDER, then Constraints as `- ` bullets
    (never numbered — no digit injected). Uses `field_texts()`-equivalent
    content only.
  - `_render_emergency`: the three Type A/B/C sentences only; NO `letter`, NO
    `emergency_type` (v4 "stays local … never crosses").
  - `_render_retry`: base five fields + state-free correctives.
  - `_render_minimum_safe`: the three minimum-safe sentences.
  - Unit tests: five-field prompt contains each `field_texts()` element in fixed
    order and no digit/state; emergency prompt contains the three sentences and
    NO type name/value and NO "Type X"/letter label and no digit; retry = base +
    correctives; minimum-safe = three sentences.
  - _Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3_

- [x] 6. Injected transport Protocols
  - `ModelTransport.generate(prompt) -> str`; `LocalModelTransport` adds
    `is_loaded` (property), `load()`, `unload()`. Both `@runtime_checkable`. No
    concrete provider imported.
  - Unit test: the fakes satisfy `ModelTransport` / `LocalModelTransport`.
  - _Requirements: 8.1, 8.2_

- [x] 7. `LLMInterface.__init__` — transports only (the structural boundary)
  - Keyword-only `cloud_transport`, `local_transport`; store as `_cloud`,
    `_local`. NO graph/PAD/state/needs/appraisal/memory/embedding parameter.
  - Unit tests: constructor params are exactly `{cloud_transport,
    local_transport}` with no forbidden name; instance `vars` are exactly
    `{_cloud, _local}`; the module imports none of `pad_engine`,
    `graph_manager`, `appraisal_chain`, `state_manager`, `moral_schema` (import
    scan) and DOES import `soul_filter`.
  - _Requirements: 2.2, 2.3_

- [x] 8. `generate` — cloud-primary orchestration + verbatim passthrough
  - Assemble once; try cloud; on success return verbatim and unload Gemma if it
    was loaded; on `LLMTransportError` delegate to the local path.
  - Unit tests: healthy cloud never loads Gemma and returns its text verbatim;
    manipulative/empty/odd cloud text is returned unchanged (no judgment).
  - _Requirements: 1.2, 1.3, 4.1, 4.2, 5.1, 5.2, 5.4_

- [x] 9. `_serve_from_local` — load on failure, same prompt, or report
  - Load Gemma if not loaded; serve the SAME `AssembledPrompt`; on local
    `LLMTransportError` raise `LLMUnavailableError` (chained), never fabricate.
  - Unit tests: cloud failure loads + serves Gemma (verbatim, incl.
    manipulative text); both-down raises `LLMUnavailableError` with the local
    error as `__cause__` and after attempting `load()`.
  - _Requirements: 4.3, 4.4, 5.4, 9.1, 9.2_

- [x] 10. Restore + sustained-outage behavior
  - First post-outage cloud success unloads Gemma; a sustained outage loads
    Gemma exactly once and never unloads mid-outage.
  - Unit tests: `test_fallback_unloads_gemma_on_cloud_restore`,
    `test_fallback_stays_on_gemma_across_a_sustained_outage`.
  - _Requirements: 4.5, 4.6_

- [x] 11. `serving_from_local` observability property
  - Read-through of `local_transport.is_loaded`; no independent state, no
    decision.
  - Covered by the fallback/restore tests.
  - _Requirements: 5.1 (it decides nothing); 9.3 (readout for the degradation
    owner)_

- [x] 12. F-9a proofs — identical prompt to cloud and Gemma
  - Force a cloud outage; assert `cloud.received[0] is local.received[0]` AND
    equality, parametrized over all four instruction kinds; assert deterministic
    assembly; assert it holds end-to-end via `SoulFilter.respond` (normal +
    emergency).
  - _Requirements: 3.2, 3.3, 3.4_

- [x] 13. Contract conformance
  - `isinstance(interface, soul_filter.LLMClient)`; `generate` signature is
    `(self, instruction, user_message)`.
  - _Requirements: 1.1, 1.4, 10.2_

- [x] 14. No-gate/no-scoring surface proof (F-9b)
  - Assert the public surface is exactly `{generate, serving_from_local}` and no
    method name contains gate/validate/score/check/judge/filter/moderate/
    correct/retry.
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 15. Integration with the REAL Soul Filter (Module 5)
  - Build a real `SoulFilter` (real `PADEngine`, real `MemoryGraph` +
    `FakeEmbedding`) with `llm_client=LLMInterface(...)`; drive
    `SoulFilter.respond()`:
    - normal turn → cloud candidate flows through; the assembled five-field
      prompt carries `PERSONA_ANCHOR` and no digit; user message carried;
    - gate-failing first candidate → SoulFilter retries → the second call to the
      Interface carries a `RetryInstruction` (kind `"retry"`) with the corrective
      and no digit;
    - emergency → Interface prompt kind `"emergency"`; internal type does not
      cross; gate bypassed;
    - cloud down → the ENTIRE respond flow completes via Gemma and the Output
      Gate still runs on Gemma's candidate; Gemma got the identical prompt;
    - Energy<30 → "do not overextend" crosses with no digit.
  - Do NOT modify `daemon/soul_filter.py` (unchanged; verified).
  - _Requirements: 1.4, 3.2, 5.4, 6.1, 6.2, 10.1, 10.3_

- [x] 16. Full-suite verification
  - `python3 -m pytest tests/test_llm_interface.py -q` → 35 passed.
  - `python3 -m pytest -q` → 229 passed (194 prior + 35), no regressions.
  - Confirm, by inspection and tests, that the two Module 9 flags are resolved
    (F-9a via ResLog 14, F-9b via ResLog 15) and OQ-9a…9d remain flagged
    build-time/other-module concerns, not invented here.
  - _Requirements: all_
