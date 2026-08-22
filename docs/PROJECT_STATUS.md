# ARIA — Project Status

Living tracker. Update after every module is approved. This file, plus
the docs/ folder, is everything a fresh review session needs — it does
not depend on any specific chat's history.

Counts and line numbers below were last measured against the code on
**2026-08-22**. They are measured values, not estimates — if you change code,
re-measure rather than assuming.

Full suite: **590 passed** with an embedding backend reachable, or **587 passed
+ 3 skipped** without one. Both numbers are real and neither is a failure: the
three skipped tests are the real-model half of the embedding comparison, which
skips rather than fails so `make check` stays hermetic on a machine with no
Ollama running.

Per-file test counts as measured on 2026-08-22 — soul layer: appraisal_chain 64,
audio_pipeline 29, backend_router 25, **daemon 57** (+2, `session_buffer_fullness`),
dmn 44, graph_manager 63, llm_interface 36, needs_system 47, pad_engine 53,
session_buffer 13, **soul_filter 54** (+3, Persona Anchor stage-direction clause),
**state_manager 38** (+7, primary entity id), visual_layer 24 — 547. Adapter
layer, new 2026-08-22: embedding_local 22 (19 hermetic + 3 real-backend),
transport_ollama 21 — 43. Total 590.

---

## Current runnable state — READ FIRST

**She runs, text-first, as of 2026-08-22.** This section said "Nothing runs yet"
from the first module until then; that is no longer true, and the change is the
largest single move the project has made. Be equally precise about what still
does not run.

```
.venv/bin/python main.py --local-model <gemma tag>
```

**Verified end-to-end on 2026-08-22**, not inferred. A real session was driven
through the full pipeline and the observable soul mechanics were read off
`:state` between turns:

| Observed | Confirms |
|---|---|
| PAD moved 0.550 → 0.580 on a positive turn, then decayed to 0.558 | both PAD write paths live — appraisal delta, then EMA decay on the soul tick |
| Energy 95.0 → 90.2 → 85.7 across three turns | the soul tick is driving Module 2 |
| Connection/Purpose `neglected` → `satisfied` after the first real turn | the two-window model self-correcting, exactly as the Accepted-decisions row predicts |
| `event_nodes` 1 → 3 across two processes, same DB, same entity id | the graph is the only memory and it persists |
| `focus` answered with its pre-authored ack and wrote NO EventNode | meta-commands bypass appraisal |
| a near-verbatim exemplar match produced the vulnerability register — thanks for trusting me, no problem-solving, no request for detail | VULNERABILITY_DISCLOSURE firing through a REAL embedding, into Field 4 / Field 5 |

What is wired: `EmbeddingModel` (real), `LocalModelTransport` (real, Ollama),
`AudioPipelinePort` (no-op), and both cloud tiers as an explicitly-unhealthy
`UnconfiguredTransport`. See "Adapter layer" below.

**What still does not run:**

- **No cloud adapter.** Groq and Azure are wired to `UnconfiguredTransport`,
  which reports `is_healthy() == False` and raises `LLMTransportError` from
  `generate()`. Both statements are true, so routing is correct rather than
  degraded: `select()` never proposes the reasoning tier, skips Groq, and serves
  every turn from Gemma — which is the architect's stated design with its two
  fallbacks absent. Nothing leaves the machine.
- **No audio.** All seven audio backends and inbound STT are absent. The REPL
  prompt IS the transcription (`route_inbound_turn` takes already-transcribed
  text, so STT was never a port), and `NoOpAudioPipeline` satisfies the output
  port. Audio is a leaf — nothing downstream reads what it did — which is why a
  stub is honest here and would not be for the embedding model.
- **No Visual Layer.** `AriaDaemon` takes no visual parameter; `VideoWindow` has
  no implementation.
- **No idle consolidation observed yet.** The DMN pass needs 8 real minutes of
  silence (PINNED by v4). `main.py` deliberately offers no command to fake
  `now`: a false timestamp would be written into the graph, and the graph is the
  only memory she has.
- **`requirements.txt` is still pytest only — and that is now a fact, not a
  gap.** Both real adapters use stdlib `urllib` against the local Ollama HTTP
  API, so the project runs on **zero runtime dependencies**. No torch, no SDK,
  no `requests`.
- `python daemon/state_manager.py` is still broken by path (`daemon/types.py`
  shadows stdlib `types`); use `make selftest` / `python -m daemon.state_manager`.
  Pre-existing and unrelated to module logic.

---

## Adapter layer — new 2026-08-22

Lives in `adapters/`, NOT in `daemon/`. The dependency arrow points one way:
adapters import Protocols from `daemon`, and nothing in `daemon` imports
`adapters`. That keeps the soul layer's zero-dependency, hermetic-suite property
intact — which is exactly what makes the 535 soul tests fast and trustworthy.

**Layout judgment call, flagged:** v4's "Directory Structure (Updated Conv.6)"
puts everything under `daemon/`. That listing is already superseded by the
shipped code — `llm_manager.py`, `stt_engine.py`, `tts_manager.py`,
`interrupt_handler.py` and `tcp_server.py` do not exist and their
responsibilities were consolidated differently — so this is a build-layout
choice, not a spec deviation. Say so if you want them moved.

| File | Satisfies | Notes |
|---|---|---|
| `adapters/embedding_local.py` | `EmbeddingModel` | `OllamaEmbeddingModel`, `/api/embed`, default `all-minilm` (384-dim, **45 MB measured** — Addendum §1's "encoder-only … tens of megabytes … Not Gemma"). LRU cache, because `_vulnerability` re-embeds all FOUR exemplars every turn. Pins the vector dimension and raises on a change, since `_cosine` returns 0.0 on a length mismatch and would silently switch off all four similarity behaviours. `preflight()` fails loudly at startup — two of the three `embed()` call sites in the soul layer swallow exceptions, so a dead backend is only partly visible at turn time. |
| `adapters/transport_ollama.py` | `LocalModelTransport` + `HealthProbe` | `OllamaLocalTransport`, `/api/generate`. Default `gemma4:12b-it-qat` (7.2 GB) — **a recorded deviation from v4's named model**, see the Accepted-decisions row; v4's own `gemma4:e2b-it-qat` stays named as `SPEC_MODEL` and as rung 2 of `resolve_model`'s four-rung ladder. `keep_alive=-1` on every request is how "loads at startup, stays resident" is expressed to Ollama; `unload()` sends `0`. `is_loaded` is a local flag costing no round trip, because `select()` reads it every turn; `refresh_residency()` asks `/api/ps` for ground truth. Load/unload/residency verified against a live daemon. |
| `adapters/transport_unconfigured.py` | `ModelTransport` + `HealthProbe` | `UnconfiguredTransport` — the honest state of the two cloud tiers as code. Explicitly `False`, not UNKNOWN: "not written yet" is a definite answer. Exists because `LLMInterface` and `BackendRouter` both REQUIRE cloud slots; passing `local` into them instead would make `LLMInterface`'s internal path unload the resident model after every successful turn. |
| `adapters/audio_noop.py` | `AudioPipelinePort` | `NoOpAudioPipeline`. Records calls, prints nothing (the REPL owns the terminal). |
| `main.py` | wiring + text REPL | Construction order is forced by the dependency edges, not chosen. Runs the HANDOFF contract via `startup()`, advances BOTH clocks with `run_scheduler_step()` after each turn, and saves **every turn** plus on exit (see the write-cadence Accepted-decisions row — the knob was removed, not set). Opens no listening socket; only outbound traffic is to the local Ollama daemon. One private read remains, named in its docstring: `graph._conn` for `:state`'s table counts, since Module 3 exposes no count API and inventing one for a debug readout is the wrong trade. |

**The embedding model is the one thing here that could not be stubbed, and
`tests/test_embedding_local.py` now proves why rather than asserting it.**
Measured against the repo's own `FakeEmbedding` (token-hash bag-of-words): a
paraphrase sharing words scores 0.869, but a paraphrase sharing NO words scores
0.000 — identical to the unrelated floor. So every `retrieve()` test in the
repo has been ordering on word overlap, not meaning. Four behaviours read this
model (`retrieve`, `reality_contradiction_check`, `_vulnerability`,
`register_edge_firing` habituation); the handoff's claim of five included
`is_first_of_kind`, which is pure SQL on (Q2, Q3) and reads no embedding.

---

## Modules — approval status

| # | Module | Status | Notes |
|---|--------|--------|-------|
| 11 | State Manager | ✅ Approved | Restored to daemon/state_manager.py after project reset. Reviewed line-by-line against spec — atomic writes, sibling-key preservation, superseded-key drop, PAD baseline fallback all confirmed correct. Extended additively for Module 1 (last_applied_valence field/methods, load_all/save_all widened) — not logically reopened. **Test gap CLOSED 2026-08-20**: `tests/test_state_manager.py` now exists (31 tests, `tmp_path`-based — the module's job IS the filesystem, so fakes would test nothing). Covers the `__main__` block's ground plus what it skipped: default-on-missing-file for every loader, restore from a hand-written snapshot, corrupt-JSON and non-numeric fallback, partial pad entries, mkdir-on-demand, sibling-key preservation vs superseded-key drop, the quality_record 20-window on both read and write sides, load independence, and the "owns no meaning" API-surface boundary. Atomicity is tested by making the temp-file write fail: the previous `aria_state.json` must stay byte-identical, the old value must still load, and no `.tmp` may survive. **Restore now CLAMPS** (2026-08-20): PAD axes to the locked [0.0, 1.0] (v4 Layer 1), Energy to [0.0, 100.0] (values mirroring Module 2's ENERGY_MIN/ENERGY_BASELINE by value, deliberately not by import — Module 11 depends on no other module). Non-finite input is treated as CORRUPT, not clamped: `json.loads` accepts a literal `NaN`/`Infinity`, and NaN silently survives a naive `max(low, min(high, v))` as `high`, so a corrupt Energy entry would have quietly restored as "fully rested". Clamp is a READ boundary only; save still records what the owning module hands over. Note the clamp is more informative than the reject it pre-empts — a file saying `energy=-50` restores as 0.0 ("empty"), where Module 2's own guard would have discarded it and booted at full. Still no `.kiro/specs/state-manager/` folder — **added 2026-08-20**, though DERIVED FROM CODE rather than authored ahead of it (see the spec-folder row in Still Open). |
| 1 | PAD Engine | ✅ Approved | daemon/pad_engine.py, 53/53 tests passing. (Task bookkeeping CLOSED 2026-08-20: `.kiro/specs/pad-engine/tasks.md` holds 22 items — 1–21 plus an inserted 7b — and all 22 were unchecked despite complete code, as were appraisal-chain 0/21 and memory-graph 0/24, all three built outside the Kiro task loop. Every task's named artifact was verified present in code before ticking — 47 checks across the three modules, one initial miss which turned out to be a wrong grep string, not a gap. All 170 tasks across all 13 folders now read `[x]`, 0 open — measured, not estimated.) OQ1 (soul-tick cadence) carried forward as a documented build-time gap, per Resolution Log. OQ2 (PAD bounds) RESOLVED — [0,1] clamp in apply_appraisal_delta confirmed intentional (physiological homeostasis; Mehrabian/Russell bounded scales; EMA decay is the recovery path), now documented in the module docstring and the pad-engine spec and covered by test_apply_appraisal_delta_clamps_to_bounds. Residual flagged: initialize() still does not clamp an out-of-range restored snapshot. OQ3 (VALENCE_UNCERTAIN coefficient) resolved — reuses EMA_COEFFICIENT_NEGATIVE, Emergency Type Detection "default to caution" precedent. OQ4 (restore-boundary coefficient) narrowed, not resolved — initialize()'s new restored_valence param + State Manager's last_applied_valence field cover the routine restart case; residual NotImplementedError raise (rare case: first-ever run, corrupted field, or crash before save) left unchanged. Known limitation logged: initialize() is not idempotent across repeated calls — see HANDOFF_NOTES.md, owed to Module 8. |
| 2 | Needs System | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/needs_system.py` (EnergyTracker substrate + NeedsEvaluator categorical + facade) + `tests/test_needs_system.py` (47 tests) + `.kiro/specs/needs-system/{requirements,design,tasks}.md`. 4 needs strictly CATEGORICAL (enum satisfied/due/neglected, no numeric score — enum-identity at 1h vs 70h in-window proves no gradation, passes percentage test); Energy is PAD-isolated SUBSTRATE (no PADEngine import; mutator tripwire never fires; real PADEngine byte-identical before/after; k_load/k_rest flagged TODO(build-time)); windows 72h/14d/14d/60d (ResLog 7) via graph_manager evidence queries; reverts satisfied→due purely by clock; output IS the shared NeedStates contract (now in `daemon/types.py`, OQ-4 closed). F-2a/b/c/d resolved. **OQ-1 CLOSED 2026-08-20 — `neglected` is now emitted, via the TWO-WINDOW model.** The counter-based option was rejected: Addendum §3 rules it out in the same paragraph that establishes the three states (*"the state reverts on its own; nothing actively subtracts anything … not a running clock"*). Instead two windows over the SAME evidence query — `satisfied` if evidence in the need's own window, else `due` if in the next rung up, else `neglected` — which is the shape §3 uses for the one need it defines fully (*"neglected when updates have gapped for a long stretch"*: a long stretch is a wider window, not a counter). Connection 72h→14d, Growth 14d→60d, Purpose 14d→60d. Both windows are already-locked ladder values, so no window, constant, counter or storage is introduced; `graph_manager` needed no change because all four `*_evidence` methods already accept `window`. State stays a pure function of (now, graph) and NeedsEvaluator stays stateless (Req 11.2). Continuity remains TWO-valued — see Still Open. |
| 3 | Memory Graph | ✅ Implemented + tested; OQ resolutions applied + RE-AUDITED (criteria a–e PASS) | Full spec at `.kiro/specs/memory-graph/{requirements,design,tasks}.md`; code `daemon/graph_manager.py` + `tests/test_graph_manager.py` (63 tests). Coded directly (not via Kiro) at architect instruction. SQLite backend; injected embedding model. Implementation audit fixed 5 defects (D1 continuity recency, D2 retrieve edge-dedup, D3 first-of-kind = Addendum §6 Q2×Q3 profile, D4 EmotionNode-stays-vivid, D5 resolution_path→null). Architect OQ resolutions RESOLVED+implemented: OQ3 (node-embedding side-table), OQ5 (total-elapsed decay), OQ4 (retrieval pure reorder, mood PRIMARY/need SECONDARY, no coefficient), OQ1-trigger (habituation via `register_edge_firing`, edge-salience-only guard). DEFERRED (TODO-flagged): OQ1-rate. **OQ2 CLOSED 2026-08-20 — the invented medium/low `base_salience` floors are REMOVED**, per ResLog item 9's literal *"Medium/Low → no floor, decays/discards as already locked"*; `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER` is deleted and `_compute_base_salience` falls through to 0.0 for those tiers, with the Critical 0.85 / High 0.55 floors untouched. The v4 Baumeister +0.15 negative bonus still stacks "on top of whichever floor applies", which for medium/low is nothing. NOT this module: OQ6 Purpose→M2; max-5-no-evictable = raise. **Final re-audit (criteria a–e) PASS**: retrieval is stable-sort ordering only (no weighted score — proven by hard-partition test); salience/habituation never wired to PAD/appraisal (no PADEngine import); deferrals all explicitly stubbed; no numeric beyond stated placeholders. F-3b/F-3c resolved (ResLog 8/10). |
| 4 | Appraisal Chain | ✅ Implemented + tested (subagent build→audit loop) | `daemon/appraisal_chain.py` + `tests/test_appraisal_chain.py` (64 tests) + `.kiro/specs/appraisal-chain/{requirements,design,tasks}.md`. Full suite **514 passed**, verified independently. Built by subagent, independently audited (found+looped 1 medium defect — vacuous test masking a neutral-turn PAD crash — fixed so purely-neutral appraisal emits NO PAD event). Auditor APPROVED via mutation-testing: ×1.5 negativity-inflation FAILS the symmetric test (proves no weighted formula); PAD purity = 3 apply_appraisal_delta sites, no direct PAD writes, no graph._conn reach-ins. PAD delta = categorical direction {−1,0,+1} × categorical Q1 tier; coping_potential transient/emergency-gate-only. F-4a/F-4b/F-4f RESOLVED (ResLog 12/10); F-4d/F-4e = flagged build-time placeholders. **Conflict-arc 2nd close condition CLOSED 2026-08-20**: `_conflict_arc_absence_close()` runs once per turn, increments the absent counter for every open arc whose entity did not recur (including turns with no entity at all), and closes those at the threshold — categorical, the turns have passed or they have not. Absence closures write the same single `"resolved"` edge as a Q2 flip. `_CONFLICT_ARC_ABSENT_TURN_THRESHOLD` is aliased to the spec-named `_ARC_CLOSE_ABSENT_TURNS` so the threshold and its `AppraisalConfig` override cannot drift; its value moved 3→5 by architect direction (both are TODO(build-time) placeholders, so no locked value was overridden). **Resolved-edge `base_salience` now DERIVED, not invented** (2026-08-20): the deleted `poignancy_base_hint()` returned 0.35 for medium/low — the same class of invented number removed from Module 3's OQ2. v4 "Argument Buffer Mode" names the multiplicand (*the resolution is "weighted 3× higher than **the conflict itself**"*), so the edge now takes the OPENING EventNode's own `base_salience`. An arc only opens on a Q2=negative EventNode, so the Baumeister +0.15 guarantees a non-zero multiplicand at every poignancy tier (critical 1.00→3.00, high 0.70→2.10, medium/low 0.15→0.45) and ResLog item 5's 3× always has something real to act on. **VALENCE_UNCERTAIN no longer closes arcs** (2026-08-20): only POSITIVE/NEUTRAL closes, per Addendum §1's literal wording — see the Closed table for why this was not a one-line change. **New public predicate `has_distress_markers()`**: the disjunction of `_distress_marker` and `_emergency_cue_kind`, exposed for the Daemon's STEP 4b distress gate; read-only, lexical, invents no lexicon. **Connection need-pref narrowed** (2026-08-20): `_need_prefs` keys Connection on `neglected` ALONE per Addendum §3 (*"When Connection is **neglected**, Stage 1 surfaces 'We'-perspective and Connection-positive edges first"*); it previously fired on `due` too — unavoidable while Needs System could not emit `neglected`, but it applied the strong preference at the weak state. Growth/Purpose/Continuity prefs are untouched; §3 exemplifies only Connection's profile. |
| 5 | Soul Filter | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/soul_filter.py` + `daemon/moral_schema.py` (shared resource: 4 values + 7 doc-cited anti-patterns) + `tests/test_soul_filter.py` (51 tests) + `.kiro/specs/soul-filter/{requirements,design,tasks}.md`. Full suite **535 passed**. Auditor independently verified 5 philosophy proofs: no numbers/state cross the LLM boundary (Behavioral Register = PAD-vs-baseline categorical words, Relational Register = stage→NL no label, only user message crosses); Output Gate = exactly 4 checks {honesty,consistency,manipulation,care}, ZERO LLM (proven w/ RaisingLLM), no 5th check, no numeric score, verify-not-decide (Principle 27); emergency REPLACES the five fields; moral-violation → corrective retry → minimum-safe; Field 4 = HOW-clause only (memory sentinel proven never to cross). F-5a/F-5b RESOLVED; OQ-M1 anti-pattern-list closure flagged (taxonomy not invented). NeedStates/LLMClient are injected contracts (M2/M9 pending). LOW follow-up: post-emergency re-entry instruction (needs Daemon cross-turn state — defer to M8). **ENERGY_CRITICAL (&lt;20) instruction CLOSED 2026-08-20** — it is no longer a dead constant. ARCHITECT RULING: Field 5 (Constraints) carries behavioural instructions, not prohibitions only, formalising existing practice since the Energy&lt;30 row (`"do not overextend"`) already lived there. v4's soul_filter instruction table line 949 supplies the &lt;20 row — *"You are running low. Acknowledge it if it comes up naturally."* — now emitted in constraint form as `"acknowledge fatigue if it comes up naturally"`. v4's *"You are running low"* clause is deliberately NOT passed through: that half is Energy state rendered as a claim, and state never crosses (Addendum §9). MAX-3 and "always specific actions" unchanged. Verified end-to-end into Module 9's assembled prompt with no digit and no state claim. The two gates are checked MOST-SEVERE-FIRST (&lt;20 before &lt;30): every base branch yields 2 or 3 constraints so at most ONE slot is ever free, and since Energy&lt;20 implies Energy&lt;30 the milder instruction would otherwise always take it and the &lt;20 row could never be emitted at all. Both remain independent `if`s, so both fire if a future base branch leaves two slots. |
| 6 | DMN / Idle Consolidation | ✅ Implemented + tested (subagent build→audit, looped 1×) | `daemon/dmn.py` + `tests/test_dmn.py` (44 tests) + `.kiro/specs/dmn/{requirements,design,tasks}.md`. Full suite at approval **452 passed** (current 514 — see header), verified independently (dmn imports OK). Audit caught a stray-space IndentationError making the module unimportable (build report's pass-count was not reproducible) → looped → fixed. 3 headline constraints verified: DMN NEVER writes PAD (aha → `submit_aha_insight` EVENT to Appraisal Chain; live PADEngine tripwire byte-identical); relational_stage transitions CATEGORICAL (enum, ≤1 gate-step, rupture −1 floored at observing, no score); self-narrative MORAL-GATED (blocked even with no audience). Quality record from OBSERVED next-turn reaction (anti-flattery). Energy&lt;20/critical → shallow (Steps 1+4). F-6b/c/d resolved. FLAGGED for M8/integration: OQ-1 Appraisal needs `submit_aha_insight` event entry; OQ-2 Memory Graph needs highest-salience-unconnected + predictability/dependability predicates; LOW: post-rupture BONDED re-advance on pre-rupture edge (fresh-evidence unspecified). |
| 7 | Audio Pipeline | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/audio_pipeline.py` + `tests/test_audio_pipeline.py` (29 tests) + `.kiro/specs/audio-pipeline/{requirements,design,tasks}.md`. Single module (ResLog 15): input chain (capture→ring→wake→speaker≥0.75→VAD→Whisper→text) + output chain (PAD→prosody→cloud→Kokoro fallback), all backends injected Protocols. F4/barge-in ZERO internal effect (tripwire vs real PADEngine: PAD byte-identical AND never even read; each handler = one playback.stop()); never writes PAD (read-only prosody), never appraises. Prosody directions per v4 Layer 5 (arousal inverse, dominance→lower pitch); magnitudes flagged TODO(F-7-prosody). Satisfies Daemon AudioPipelinePort unchanged. |
| 8 | Daemon / Soul Tick | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | **Public surface went 2026-08-22: new read-only property `session_buffer_fullness`**, added alongside the existing observability properties (`soul_tick_count`, `attentional_focus`, `state`, `started`, …). The Daemon constructs its own `SessionBuffer`, so a caller had no handle to ask `fullness_state()` — and that is the one piece of the buffer's state a caller has business seeing, since it is what drives STEP 4's cognitive-load trigger. Read-only, categorical, NOT a decision surface, crosses no model boundary; it replaced a `daemon._session_buffer` reach-in in `main.py`. Covered by 2 tests (read-through equality, no setter, and a non-vacuous check that it tracks live turns). `daemon/aria_daemon.py` + `tests/test_daemon.py` (57 tests) + `.kiro/specs/daemon/{requirements,design,tasks}.md`. Full suite **514 passed**, verified independently. Two clocks SEPARATE (soul_tick never runs DMN; dmn_tick never decays PAD); Daemon computes no feeling (no `apply_appraisal_delta` CALL SITE in its source — the string occurs twice in the module docstring describing the constraint, so grep for `\.apply_appraisal_delta\s*\(` to verify, not the bare name); F4/barge-in ZERO internal effect (tripwire: PAD/Energy/graph/state byte-identical; each handler = one stop_playback()); HANDOFF contract exact (initialize() once + guarded, consistency_flags cleared each session, last_applied_valence round-trips); initiative keys on 'due', fires once, no-nag, enters at soul_filter skipping wake/STT. ADDITIVELY closed DMN's contract gaps (baseline preserved exactly): appraisal_chain.submit_aha_insight (aha routes through appraisal, DMN still never writes PAD), graph_manager predictability/dependability_evidence (structural booleans) + highest_salience_unconnected. F-8b resolved (ResLog 10); F-8a cadences build-time. OQ-2 initiative-on-'due' flagged. **Energy&lt;30 → Appraisal Stage 2 CLOSED 2026-08-20**, in `route_inbound_turn` STEP 4 beside the existing buffer-fullness trigger: `if self._needs.get_energy() < ENERGY_LOW: self._appraisal.submit_cognitive_load("heavy")`. Addendum §3 keeps the *"reasoning degrades below 30"* rule as an operational threshold gate, and v4's mechanism table files the "Cognitive load effect" as an "Appraisal modifier" reaching "Stage 2 appraisal + DMN depth check" — so it routes through the EXISTING `submit_cognitive_load` entry point. No new mechanism, no new number (`ENERGY_LOW` imported from its canonical home `daemon/types.py`), and Energy never crosses the module boundary: the Appraisal Chain holds no Energy handle and only the categorical load state crosses, exactly as buffer fullness does. **It SKIPS NOTHING** — Stages 0–6 all still run, the Stage-1 social-signal pre-pass (vulnerability check included) is untouched, and the emergency gate is untouched, so a tired ARIA still detects a crisis (tested). Rejected en route: an earlier proposal to skip `coping_potential` and the vulnerability check at low Energy would have disabled crisis detection outright and contradicted v4, which says emotional weighting *increases* below 30, not that perception is reduced. |
| 9 | LLM Interface | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/llm_interface.py` + `tests/test_llm_interface.py` (36 tests) + `.kiro/specs/llm-interface/{requirements,design,tasks}.md`. Full suite at approval **452 passed** (current 514 — see header). Boundary is STRUCTURAL: constructor takes only {cloud_transport, local_transport} — no graph/PAD/needs/appraisal handle. It imports exactly ONE internal module — `from daemon.soul_filter import ...` (line 74), for the instruction dataclasses plus a re-exported `LLMClient` — and nothing from graph/PAD/needs/appraisal. The guarantee is the absent CONSTRUCTOR PARAMETER, not an absent import; `soul_filter.py` does not import back, and that one-way direction is what keeps the boundary structural. Cloud + Gemma get the byte-IDENTICAL prompt via one pure assemble_prompt() (F-9a / ResLog 14, proven by object identity). NO judgment (F-9b / ResLog 15 — verbatim passthrough even for gate-failing text; retries only when Soul Filter re-calls). Satisfies Soul Filter's LLMClient contract (isinstance passes, soul_filter.py unmodified). OQ-9a..9d flagged placeholders. **NOTE:** `session_context` parameter added post-approval — ephemeral conversation transcript, not internal state. |
| 10 | Visual Layer | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/visual_layer.py` (478 lines) + `tests/test_visual_layer.py` (24 tests) + `.kiro/specs/visual-layer/{requirements,design,tasks}.md`. Full suite at approval **452 passed** (current 514 — see header); all modules import OK. Only READS PAD (tripwire vs real PADEngine: writes==0, byte-identical; AST scan imports only read-only PADSnapshot, no graph/appraisal/needs/state/PyQt6/mpv); zone selection CATEGORICAL (Zone enum via boolean threshold membership, not a distance/score — 13 boundary constants + 8s stability cited to v4 lines 1145-1160/1316); talking-vs-idle follows speaking-state; cloud-fail → INWARD_WAITING; runs independent of LLM. F-10a resolved (ResLog 15). Exposed a clean VisualLayerPort — daemon UNMODIFIED. TODO(F-10-zone-precedence) flagged. |
| 12 | Session Buffer | ✅ Implemented + tested | `daemon/session_buffer.py` + `tests/test_session_buffer.py` (13 tests). **Not in original Build Plan.** Ephemeral 3-tier conversation buffer (Recent 8K tokens / Medium 6K / Old 4K). Rule-based summarization. Meta-commands: `"rest"`, `"focus"`, `"unfocus"`. Cognitive load tracking (`fullness_state()`). Fuzzy trigger detection with word-boundary matching. Wired into Daemon's `route_inbound_turn()` — session_context passed to Soul Filter → LLM Interface. |
| 13 | BackendRouter | ✅ Implemented + tested | `daemon/backend_router.py` + `tests/test_backend_router.py` (25 tests). Pure INFRASTRUCTURE: 3-tier backend pool (tier_0 Gemma local / tier_1 Groq / tier_2 Azure-Kimi), keyword-heuristic tier-2 classifier (no neural model, word-boundary regex), session-scoped override, 30s-cached health probe, and `select()` returning `(transport, propose_flag)`. Touches NO PAD/graph/needs/appraisal/personality state — proven by an AST import scan and a `vars()` check. TODO(build-time): `TIER_2_KEYWORDS` lexicon, `HEALTH_CACHE_TTL_SECONDS`. FLAG A: CLOSED (Track A) — selection is now wired end-to-end: `AriaDaemon.route_inbound_turn()` calls `BackendRouter.select()`, hands the returned transport to `SoulFilter.respond(transport=...)`, which passes it through opaquely to `LLMInterface.generate(transport=...)`, which calls it directly instead of running its own cloud-first chain. Fallback order swapped: Gemma (default voice for conversation) is now tried BEFORE Groq (reserved for future tools/search, now only a fallback); new `ensure_local_loaded()` is called once by `AriaDaemon.startup()` so Gemma loads at startup and stays resident. `medical`/`legal` removed from `TIER_2_KEYWORDS` (too broad for a personal companion). **FLAG B: CLOSED 2026-08-20** — health probing is no longer optimistic. `_probe_one` now returns `Optional[bool]`: True (explicitly healthy) / False (explicitly unhealthy) / **None = UNKNOWN** for a non-local transport exposing no `HealthProbe`, because no probe means no answer and "no answer" is not "yes". `check_health()` reports the HEALTHY SET — only an explicit True joins it, so UNKNOWN is folded out — while keeping its documented three-key shape. The local tier is never UNKNOWN (residency is a real answer). `select()`'s branch logic is UNCHANGED: it was already correct once UNKNOWN stopped reading as True. All three consequences the old row named are fixed and tested: a tier-2 keyword match no longer proposes escalation unless Azure explicitly reports healthy; Groq is selected only when explicitly healthy; and the `return None, False` all-down degradation path is now reachable. **`select()` gained `allow_tier_2_proposal: bool = True`** (2026-08-20) for the Daemon's distress gate: when False the tier-2 branch is skipped and the normal gemma→groq chain decides. The CALLER supplies the constraint, the ROUTER still chooses — deliberately a parameter rather than a "give me the local transport" accessor, which would let a caller bypass the fallback order and duplicate the "is gemma usable" test. Default preserves prior behaviour exactly; an explicit user override still wins unconditionally. NOTE: no `.kiro/specs/backend-router/` folder yet — spec deferred — **folder added 2026-08-20** (`.kiro/specs/backend-router/design.md`), but DERIVED FROM CODE and explicitly not a source of scope; see the spec-folder row in Still Open. All thirteen modules now have a folder. |

## Build order (locked, from earlier planning)

Foundation → Core loop → Alive-ness → Presentation:
State Manager (done) → PAD Engine (done) → Memory Graph → Appraisal Chain →
Soul Filter → LLM Interface → Needs System → DMN → Daemon →
Audio Pipeline → Visual Layer → Session Buffer → BackendRouter (both post-approval gap closure).

## Post-Module-10 Gap Closure Phase

Completed work not in original Build Plan:
- **SessionBuffer** (3-tier ephemeral memory, rule-based summarization, meta-commands)
- **`session_context` threading** (conversation history in LLM prompt, formally sanctioned as ephemeral transcript — not internal state)
- **Meta-commands** (`"rest"`, `"focus"`, `"unfocus"`) — bypass appraisal, trigger DMN consolidation on "rest"
- **`submit_cognitive_load()`** — SessionBuffer fullness → PAD delta
- **Self-entity propagation** at startup (closes Needs OQ-2)
- **Per-turn uncertainty interaction count increment** (closes Appraisal OQ-A)
- **DMN contract gaps closed** — `predictability_evidence`, `dependability_evidence`, `highest_salience_unconnected_candidates`, `submit_aha_insight`
- **Track A: BackendRouter wired into the conversation loop** — `LLMInterface` caller-supplied `transport`; `SoulFilter.respond()` threads it through opaquely; `AriaDaemon` proposal state machine (`DaemonState`, backend meta-commands, soul-tick timeout); Gemma loaded and kept resident at startup via `ensure_local_loaded()`

## Open-Question Closure Phase (2026-08-20)

Ten commits closing long-standing flags. Every change was verified non-vacuous —
each new test was re-run against the pre-change behaviour and confirmed to fail —
and the full suite was green at each commit except `80dfb33`, noted below.

| Commit | What |
|---|---|
| `5839578` | `fix(memory-graph)`: drop invented medium/low `base_salience` floors (OQ2) |
| `d8848b0` | `fix(appraisal-chain)`: implement Addendum §1's 2nd conflict-arc close condition; derive resolved-edge `base_salience` from the opening EventNode |
| `815314c` | `fix(backend-router)`: close FLAG B — UNKNOWN health is no longer optimistic |
| `5629dc8` | `test(state-manager)`: first pytest coverage for Module 11 (31 tests) |
| `80dfb33` | `chore(soul-filter)`: drop unused `ENERGY_CRITICAL` import — **left the suite RED**, see below |
| `c1989a0` | `fix(tests)`: import Energy gates from `daemon.types`, repairing `80dfb33` |
| `d6e5e23` | `feat(daemon)`: wire Energy&lt;30 to the cognitive-load appraisal modifier |
| `115538a` | `fix(state-manager)`: clamp PAD and Energy on restore |
| `2d9aaa5` | `feat(soul-filter)`: emit the Energy&lt;20 instruction in Field 5 (architect ruling) |
| `0243aad` | `feat(needs)`: emit `neglected` via the two-window model (OQ-1) |

**`80dfb33` is a red commit.** It removed `ENERGY_CRITICAL` from `soul_filter`'s
imports on the premise it was unreferenced. It was unreferenced in that module's
own logic but still reachable through its namespace, and
`tests/test_needs_system.py` imported it from there inside a parenthesized
multi-line import that a single-line grep missed. `c1989a0` repairs it by pointing
that test at `daemon/types.py`, the canonical definition site. Recorded rather
than amended away, so `git bisect` across this range is not misleading.

**Three architect rulings were applied in this phase.** All three are now recorded
in the precedence chain as `ARIA_Resolution_Log.md` items 16–18, with the Field 5
ruling additionally amending Addendum §9's Constraints row in place:

1. **Field 5 carries behavioural instructions, not prohibitions only** —
   formalising existing practice, since the Energy&lt;30 row already lived there.
2. **`neglected` via the two-window model**, counter-based approach rejected.
3. **PAD/Energy clamping belongs at the StateManager restore boundary**, not
   inside PAD_Engine.

**Two directed changes were deliberately deviated from**, both explained at the
time and both load-bearing: the Energy gate order in `_derive_constraints` is
most-severe-first (checked the other way the &lt;20 row can never fire), and the
`neglected` mechanism is two-window rather than counter-based (Addendum §3
excludes counters outright).

## Closed Open Questions / Flags

| OQ/Flag | Resolution | Where |
|---------|-----------|-------|
| OQ-A (interaction_count increment) | ✅ CLOSED | `graph_manager.py` + `appraisal_chain.py` |
| OQ-2 (self-entity ownership) | ✅ CLOSED | `AriaDaemon.startup()` |
| OQ-4 (NeedStates relocation) | ✅ CLOSED | `types.py` |
| DMN contract gaps (predictability, dependability, aha) | ✅ CLOSED | `dmn.py` + `tests/test_dmn.py` |
| OQ1 habituation **trigger shape** | ✅ CLOSED | `graph_manager.register_edge_firing()` — a firing counts as "without variation" if its retrieval-context embedding is similar to recent firings of the SAME edge, recorded in an `edge_firing_contexts` side-table. Habituation adjusts edge `salience` ONLY, never PAD or appraisal. **Note:** only the trigger is closed; the magnitudes are OQ1-rate, still open below. |
| OQ3 node embedding storage | ✅ CLOSED | `graph_manager.py` — separate `node_embeddings` side-table keyed by node_id, with `_store_embedding` / `_get_embedding`; the locked v4 node schema is untouched. Regenerate on embedding-model change. (Was previously listed under Still Open as well — that duplicate row contradicted the Module 3 row and has been removed.) |
| OQ4 retrieval precedence | ✅ CLOSED | `graph_manager.retrieve()` — reorder-not-filter over a similarity candidate set, mood-congruence PRIMARY / need-preference SECONDARY, pure stable-sort ordering with no weighted score. (Same duplicate-row correction as OQ3.) |
| OQ2 medium/low `base_salience` | ✅ CLOSED 2026-08-20 — resolved in ResLog's favour | `graph_manager.py` — `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER` (0.35 / 0.15) DELETED and its TODO(OQ2) justification block removed. ResLog item 9 line 96 says literally *"Medium/Low → no floor, decays/discards as already locked"*; that is a positive instruction, not silence, and the code had read it as a gap and filled the gap with invented numbers against the highest-precedence document. `_compute_base_salience` now falls through to 0.0 for those tiers; Critical 0.85 / High 0.55 untouched. Behavioural consequence tested: at 65d untouched, medium/low reach `faded` while critical stays `vivid` and high holds at `present`. |
| Conflict-arc 2nd close condition | ✅ CLOSED 2026-08-20 | `appraisal_chain._conflict_arc_absence_close()` — Addendum §1's second close condition (*"or enough turns pass without that entity recurring"*) now exists in behaviour. `_arc_absent_turns` was previously reset but never incremented and never read. Categorical: the turns have passed or they have not. Absence closures write the same single `"resolved"` edge as a Q2 flip. |
| Resolved-edge `base_salience` invented magnitude | ✅ CLOSED 2026-08-20 | `appraisal_chain.poignancy_base_hint()` DELETED. v4 "Argument Buffer Mode" names the multiplicand — the resolution is *"weighted 3× higher than **the conflict itself**"* — so the closure edge now takes the OPENING EventNode's own `base_salience` instead of a 0.35 placeholder. Non-zero at every tier because an arc only opens on a Q2=negative node (Baumeister +0.15), so ResLog item 5's 3× always has a real multiplicand. |
| BackendRouter FLAG B — optimistic health | ✅ CLOSED 2026-08-20 | `backend_router._probe_one` returns `Optional[bool]` with **None = UNKNOWN** for an unprobeable non-local transport; `check_health()` admits only explicit True to the healthy set. `select()` unchanged — already correct once UNKNOWN stopped reading as True. Also fixed a latent hole: nothing else in the module treats "not known to be down" as healthy. (Moved here from Still Open.) |
| Energy &lt;30 → Appraisal Stage 2 | ✅ CLOSED 2026-08-20 | `aria_daemon.route_inbound_turn` STEP 4 — routes through the EXISTING `submit_cognitive_load("heavy")` entry point when `get_energy() < ENERGY_LOW`. No new mechanism, no new number, Energy never crosses into the Appraisal Chain, and no appraisal stage is skipped (emergency gate and Stage-1 pre-pass explicitly untouched and tested). |
| ENERGY_CRITICAL (&lt;20) instruction | ✅ CLOSED 2026-08-20 — architect ruling on Field 5 | `soul_filter._derive_constraints` — v4 line 949's row is now emitted as `"acknowledge fatigue if it comes up naturally"`. RULING: Field 5 carries behavioural instructions, not prohibitions only — formalising existing practice, since the Energy&lt;30 row already lived there. v4's *"You are running low"* clause is withheld (state never crosses, Addendum §9); only the instruction crosses. Gates checked most-severe-first, else Energy&lt;20 implying Energy&lt;30 would mean the &lt;20 row could never fire. |
| `neglected` need state emission (OQ-1) | ✅ CLOSED 2026-08-20 — two-window model | `needs_system.NeedsEvaluator._state` is now 3-valued: `satisfied` if evidence in the need's own window, else `due` if in the next rung up the locked ladder, else `neglected`. Connection 72h→14d, Growth 14d→60d, Purpose 14d→60d. The counter-based alternative was REJECTED — Addendum §3 rules it out in the same paragraph that establishes the three states (*"reverts on its own; nothing actively subtracts anything … not a running clock"*). No window, constant, counter or storage introduced; `graph_manager` unchanged because all four `*_evidence` methods already accept `window`. Continuity remains two-valued (see Still Open). |
| Connection We-perspective preference over-applied | ✅ CLOSED 2026-08-20 | `appraisal_chain._need_prefs` — Addendum §3 attaches the 'We'-perspective/Connection-positive surfacing to Connection being **neglected**; it also fired on `due`. Unavoidable while `neglected` could not be emitted (with `due` the only unmet state, keying on it was the only way to do anything), but it applied the strong preference at the weak state. Now keyed on `neglected` alone. Growth/Purpose/Continuity untouched — §3 exemplifies only Connection's profile. |
| `state_manager.py` has no test file | ✅ CLOSED 2026-08-20 | `tests/test_state_manager.py`, 31 tests. See the Module 11 row. |
| VALENCE_UNCERTAIN closed conflict arcs | ✅ CLOSED 2026-08-20 | `appraisal_chain._conflict_arc_update` — Addendum §1 says the arc *"closes when a later EventNode on that entity_ref flips to Q2=positive/neutral"*, but the else-branch treated everything not-NEGATIVE as a flip. So user confusion (*"it's complicated, I can't tell"*) counted as repair and wrote a `"resolved"` edge — and that edge is what the Invested→Bonded FAITH gate reads (`resolved_edge_exists`, ResLog item 5), earning relational trust on a turn where nothing was resolved. Now only POSITIVE/NEUTRAL closes; VALENCE_UNCERTAIN breaks the consecutive-negative run but leaves the arc open. **Not a one-line change:** keeping the arc open made a previously unreachable path live — the ambiguous turn resets the negative run, so the NEXT negative looked like a fresh opener and the caller overwrote `_arc_open_event` MID-ARC, which would have pointed the closure edge at the wrong node and derived its 3× `base_salience` from it. Demonstrated before fixing. An opener is now marked only when no arc is already open; three regression tests cover mid-arc, fresh-arc-after-closure, and aborted-run. |
| Daemon FLAG 3 — proposal delays a possible emergency | ✅ CLOSED 2026-08-20 | `aria_daemon` STEP 4b. Was recorded in HANDOFF_NOTES as *"RESOLVED: no crisis pre-check"* on two claims that do not hold: the crisis lexicons are DOWNSTREAM of STEP 5's return, not *"upstream of and independent of"* the classifier; and the keywords DO overlap with crisis language in combination (measured: *"I want to die, explain why I should keep going"* → `propose_tier_2`). Now `AppraisalChain.has_distress_markers()` — the disjunction of the two perception checks Module 4 already owns, no lexicon invented — feeds `allow_tier_2_proposal=not distressed` into `select()`, so a distressed turn is never deferred and the emergency gate runs on the turn it arrives. **Second bug found while fixing:** discarding a `propose=True` result left `transport=None`, handing the turn to `LLMInterface`'s CLOUD-FIRST internal chain — traced as plain chat → GEMMA but distressed turn → CLOUD, i.e. the most personal messages were the ones leaving the machine. Fixed by passing the constraint INTO the router (caller states the constraint, router still chooses); re-traced, distress and crisis both now served by GEMMA. The architect's underlying risk acceptance is unchanged — this is defence-in-depth. |
| PAD / Energy not clamped on restore | ✅ CLOSED 2026-08-20 | `state_manager.load_pad` / `load_energy` clamp to [0,1] and [0,100]; non-finite treated as corrupt (NaN would otherwise survive a naive clamp as the upper bound). Read boundary only. This also closes the residual noted in the Module 1 row — *"initialize() still does not clamp an out-of-range restored snapshot"* — at the persistence boundary rather than inside PAD_Engine; PAD_Engine itself is unchanged. |
| BackendRouter FLAG A — selection wired (Track A) | ✅ CLOSED | `LLMInterface.generate()` accepts an optional caller-supplied `transport` (opaque passthrough, bypasses the internal cloud-first chain); `AriaDaemon.route_inbound_turn()` calls `BackendRouter.select()` and threads the result through `SoulFilter.respond(transport=...)`; a `DaemonState` (NORMAL/PROPOSING_CLOUD) state machine owns the pause-and-ask UX for `propose=True`, including a soul-tick-driven timeout; backend meta-commands ("use cloud"/"stay local"/...) are intercepted and call `set_override`/`clear_override`; `AriaDaemon.startup()` calls `BackendRouter.ensure_local_loaded()` once, so Gemma loads at startup and stays resident (the router never unloads it). See HANDOFF_NOTES.md "Track A" for the three FLAGS this raised (timeout PAD delta not implemented by design; ambiguous proposal response defaults to negative; no crisis pre-check). (Moved here from the Still Open table, where it sat marked ✅ CLOSED.) |
| Gap-closure work is unrecorded in the precedence documents | ✅ CLOSED 2026-08-20 | Was: Session Buffer (12), BackendRouter (13), meta-commands, `session_context` and Track A wiring appeared in NONE of v4, the Addendum, or the Resolution Log — architect-directed and therefore authorised, but with the authorisation recorded nowhere in the precedence chain, so a reviewer could not tell "architect approved" from "agent invented". **Now recorded: `ARIA_Resolution_Log.md` items 16–19** — item 16 Field 5 carries behavioural instructions, item 17 `neglected` via the two-window derivation, item 18 restore-boundary clamping, item 19 the post-approval authorisation of record (Session Buffer, `session_context`, meta-commands, BackendRouter + Track A, Energy<30 → cognitive load, the Daemon distress gate, and the arc absent-turn count = 5). Addendum §9's Constraints row is amended in place, citing item 16. Each entry's factual claims were re-verified against code before writing. **One item deliberately left open inside item 19**: `session_context` vs §9's unqualified "nothing else" was named there as NOT resolved — closed separately on 2026-08-22, see the next row. |
| `session_context` vs Addendum §9 | ✅ CLOSED 2026-08-22 — the amendment is now IN the chain | Was a **Rule 2 flag**: §9 says *"Five fields, fixed order, nothing else"* and lists *"historical conversation summaries"* among what never crosses, which is exactly what SessionBuffer's Medium tier passes (Old tier passes topic tags). `project-rules.md` had already framed session context as a third sanctioned surface, but that file is the always-loaded non-negotiables file, NOT one of the three precedence documents — so the resolution lived outside the chain it was qualifying. **Now inside it:** `ARIA_Soul_Spec_v4_Addendum.md` §9 carries a dated in-place amendment, inserted after the *"What the LLM also receives"* paragraph, naming ephemeral session context as a THIRD sanctioned surface — current session only, recent turns verbatim + medium-tier rule-based summaries + old-tier topic tags, appended and never merged into a field, still appended in emergency mode. **"Nothing else" was NOT narrowed and must not be.** The tempting fix — reading it as "nothing else *from past sessions*" — would legalise seven of the nine never-crosses items: only the last two (*historical conversation summaries*, *anything Aria remembers … from past sessions*) concern past sessions, while PAD values, graph node IDs or contents, relational_stage label, needs states as data, Q1–Q4 outputs or values, memory node contents and appraisal vectors are all CURRENT-TURN data excluded on their own terms. Count re-measured from the list itself: 9 items, 7 current-turn, 2 past-session. §9 lines 165 (five-fields-nothing-else) and the never-crosses list are BYTE-UNCHANGED — the amendment adds a surface, it does not weaken a prohibition. Boundary drawn at the SESSION boundary: within-session is a transcript, across-session is memory and stays out; **if SessionBuffer is ever made to persist across sessions the amendment does not cover it and must be revisited**. `.kiro/specs/session-buffer/design.md` carries a matching dated AMENDMENT block (bundle regenerated). RESIDUAL, needs a one-line decision: ResLog item 19's own sentence still reads *"is NOT resolved by this item and remains open"* — see the note under Still Open. |

## Still Open

Every row carries a BLOCKER TYPE, so a reader can tell in one pass what is
actionable. Before 2026-08-20 this table mixed decisions-already-made with
work-genuinely-blocked, and the list read as thirteen outstanding tasks when
only some were. The tags:

- **`needs-ruling`** — blocked on an architect decision, nothing else. Small and
  self-contained; each could land the same day it is answered.
- **`needs-runtime`** — cannot be closed at a desk. These are magnitudes that
  require watching her behave; deferring them is correct, not neglect.
- **`needs-adapter`** — falls out of the adapter/entry-point phase naturally.

A row that is neither — a decision made and recorded — does not belong here. See
"Accepted decisions" below.

| Item | Blocker + status | Note |
|------|------------------|------|
| OQ6 Purpose evidence + max-5 cap | `needs-ruling` · 🔓 OPEN | raises; cognitive ceiling alternative flagged |
| Continuity `neglected` | `needs-ruling` · 🔓 OPEN — the one need the two-window model cannot serve | Connection/Growth/Purpose now emit `neglected` (2026-08-20); Continuity stays two-valued, with a `TODO(Addendum §3)` in `evaluate_continuity` and a test asserting it never returns NEGLECTED. Two reasons it cannot use the same rule: its own window is 60d, already the TOP rung of the locked 72h/14d/60d ladder, so there is no wider window to step to without inventing one; and §3 gives it a QUALITY criterion rather than a gap — *"neglected when updates have gapped for a long stretch, **or new evidence contradicts rather than extends it**"*. What it needs: a signal for "this narrative update contradicts rather than extends". Adjacent machinery exists (`reality_contradiction_check`, the `GRAPH_CONFLICT` uncertainty type) but neither is wired to the narrative-update path, and `continuity_evidence` currently uses `last_referenced` on the self node as an extension-timestamp proxy, which carries no notion of contradiction. Options: DMN's narrative step records extended-vs-contradicted, or a graph query compares successive `relationship_summary` states. Both are new mechanisms — architect ruling needed (Rule 1). |
| v4 non-prohibition instruction rows with no home | `needs-ruling` · 🔓 OPEN — **3 of v4's 4 uncertainty rows now live; row 945 is NOT implementable** | v4 has FOUR uncertainty rows in the soul_filter table, not two. **Live:** 943 *"Uncertainty node unresolved → Don't fake confidence"* (base branch); **944** *"INPUT_UNCERTAIN active → Be present. Don't project onto what you don't know yet"* and **946** *"Uncertainty resolved this turn → Something just became clearer. You can let that show"* — both implemented 2026-08-20, both purely categorical off signals `AppraisalResult` already carried (`uncertainty_node_id` + a graph type read; `resolved_uncertainty_ids`). No lexicon, no threshold, no new quantity. **PARKED — row 945** *"Uncertainty weight above 0.5"*: the phrase `"uncertainty weight"` occurs **exactly once** in the entire precedence chain (v4 line 945); no `uncertainty_weight` symbol exists in `daemon/` or `tests/`; `UncertaintyNode`'s only numerics are `interaction_count` and the `catch_up_*` PAD fields, and repurposing either would invent a *meaning* for an existing number. There is no `0.5` to compare against. Implementing it requires a formula producing a number that decides what she says about her own interior — the protected chain's core prohibition, and it fails the percentage test on sight. Rule 1: flagged, not invented. This was mis-described as "ready, ~30 min" three times in handoff summaries; `test_v4_uncertainty_row_945_is_not_implemented` now pins the absence so it reads as a decision. **Still genuinely open:** v4's Energy<30 self-acknowledgment (*"I'm not thinking clearly right now"*), held back separately — it is a disclosure about internal state, which brushes §9 in a way the other permissions do not. |
| OQ1-rate habituation magnitudes | `needs-runtime` · 🔓 DEFERRED — **first real data 2026-08-22** | `_HABITUATION_SIMILARITY_CUTOFF = 0.9`, `_HABITUATION_DECREMENT = 0.05`, `_HABITUATION_RECENT_FIRINGS = 5` — all carry `TODO(OQ1-rate)` and the module docstring lists them under "DEFERRED (explicit placeholder + TODO — do NOT treat as final)". Runtime-tuned. **This row previously appeared in the Closed table marked resolved, which contradicted both the code and the Module 3 row. The trigger shape is closed; the rate is not.** The CUTOFF now has a real measurement behind it — see "First real embedding calibration data" below: at 0.9 a near-duplicate (0.950) and a shared-word paraphrase (0.910) are indistinguishable. The decrement and window still need her running. |
| Build-time tuning constants | `needs-runtime` · 🔓 OPEN | All still placeholders (intentional). Inventory re-measured 2026-08-20: `PAD_HISTORY_LENGTH`; `K_LOAD`/`K_REST` (F-2a/F-2b); OQ1-rate habituation (above); appraisal arc turn-counts (`_ARC_OPEN_CONSECUTIVE_NEGATIVE` = 2, `_CONFLICT_ARC_ABSENT_TURN_THRESHOLD` = 5, aliased to the spec-named `_ARC_CLOSE_ABSENT_TURNS`) + distress/social lexicons (F-4d/F-4e); moral-schema anti-pattern markers (OQ-M1); soul-filter deflection markers; prosody magnitudes (F-7-prosody); zone precedence (F-10-zone-precedence); `TIER_2_KEYWORDS` + `HEALTH_CACHE_TTL_SECONDS`; soul-tick 3s / DMN-tick 30s (F-8a). **REMOVED from this inventory:** OQ2 medium/low `base_salience` (floors deleted) and the resolved-edge `base_salience` hint (now derived from the opening EventNode) — both were invented magnitudes, not tuning knobs. **ADDED 2026-08-22, adapter layer:** `embedding_local` timeout + cache size, `transport_ollama` generation timeout — transport plumbing, no soul meaning. **Three existing entries now have measured data rather than none:** `_VULNERABILITY_SIM_CUTOFF`, `_HABITUATION_SIMILARITY_CUTOFF`, `_REALITY_CONTRADICTION_SIM_CUTOFF` — see "First real embedding calibration data" below. One of the three looks wrong on the evidence; none was changed. |
| Cloud adapters still expose no `is_healthy()` | `needs-adapter` · 🔓 OPEN — narrowed 2026-08-22 | FLAG B itself is closed: an unprobeable transport is UNKNOWN and is NOT treated as healthy. **Narrowed by the adapter phase**: the LOCAL transport now implements `HealthProbe` for real (`OllamaLocalTransport.is_healthy()` = daemon reachable AND model tag installed, one cheap `/api/tags` read, no generation spent), and both cloud tiers are wired to `UnconfiguredTransport`, which answers an explicit `False` rather than UNKNOWN. So routing is now correct and observable rather than inert-by-accident: measured `gemma=True groq=False azure=False`, every turn served locally, the reasoning tier never proposed. What remains is only the original work — write a real Groq/Azure adapter satisfying `ModelTransport` + `HealthProbe`, which is purely additive (same constructor slot, nothing else changes). Simplest non-inventing option, unchanged: back `is_healthy()` with the adapter's own last `LLMTransportError` state. |
| Stage-direction defect has a fix but no general format guard | `needs-ruling` · 🔓 OPEN — **surfaced 2026-08-22 by the adapter phase** | The specific case is CLOSED (Persona Anchor clause — see Accepted decisions). What remains open is the general shape it exposed: **the Output Validation Gate has no FORMAT check.** Its four comparisons are honesty, consistency, manipulation and care, all about content; nothing structurally prevents a model emitting a stage direction, a markdown heading, a bulleted list, an emoji, or a `<think>` block into text that goes straight to TTS. Today the only defences are Field 1's wording and the fact that neither measured model emits traces — both behavioural, neither structural. Options, none free: a fifth gate check (Addendum §4 fixes the gate at four comparisons, so this needs a ruling, not an implementation); a format normaliser between Soul Filter and the Audio Pipeline (a new component, and it would be judging output); or accept prompt-level mitigation as sufficient and record that. Worth deciding before TTS is wired, because that is when a format defect stops being cosmetic and starts being spoken. |

**Seven rows, re-counted from the table above** (`needs-ruling` 4,
`needs-runtime` 2, `needs-adapter` 1). The arithmetic across 2026-08-22, so
nobody reads it as progress reversed: it started at 7; the §9 closure took it to
**6**; the adapter phase surfaced the primary-entity row (**7**); the ruling pass
closed that row (**6**) and surfaced the format-guard row (**7**). Closing work
and finding work are separate events and both kept happening.

### §9 closure — the residual is CLOSED

The §9 amendment cited `ARIA_Resolution_Log.md` item 19 as its authority while
item 19's own text still said the tension "remains open". Since the Log OUTRANKS
the Addendum, the chain read both ways at once and precedence settled it in the
direction that voided the amendment.

**Resolved 2026-08-22 by `ARIA_Resolution_Log.md` item 20**, written into the Log
where the project's convention says rulings go. Item 19's wording was
deliberately left alone: it is a correct dated record of what was true when it
was written, and editing it to match later reality is the drift-detection
anti-pattern this project guards against. Item 20 completes the pattern items
16–18 established — the ruling lands in the Log, the lower document carries the
dated in-place amendment.

## First real embedding calibration data (2026-08-22)

The three similarity cutoffs in the code had never seen a real embedding. They
have now, over a 37-sentence probe set in three bands. Reproduce with:

```
.venv/bin/python -m pytest tests/test_embedding_local.py -q -s -k calibration
```

**No cutoff was changed by this pass.** All three are flagged placeholders
(F-4e / OQ1-rate / build-time) and moving one is an architect decision, not a
consequence of a measurement. The recommendation for the one that needs moving is
stated below with the evidence under it.

### `_VULNERABILITY_SIM_CUTOFF = 0.6` — measured non-functional

The probe set is deliberately THREE bands, because the interesting question is
not whether a shopping list scores lower than a confession. It is whether there
is a gap between text that is emotionally loaded but *not* self-disclosure, and
text that is. Scored the way `AppraisalChain._vulnerability` actually scores —
best cosine against ANY of the four exemplars.

| Band | n | min | mean | max |
|---|---:|---:|---:|---:|
| 1 mundane (requests, facts, logistics) | 15 | 0.059 | 0.118 | 0.216 |
| 2 emotional but NOT disclosure (annoyed, tired, excited) | 10 | 0.107 | 0.205 | 0.337 |
| 3 genuine disclosure (12 varied phrasings, not exemplar paraphrases) | 12 | 0.296 | 0.473 | 0.824 |

**At the live 0.6, nine of twelve genuine disclosures do not fire.** That is a
75% miss rate on the single signal this part of the architecture exists to
detect. It is not a marginal mis-set; it is off.

The decision table — false positives out of 25 non-disclosures, missed
disclosures out of 12:

| cutoff | false pos | missed disclosures | |
|---:|---:|---:|---|
| 0.20 | 6/25 | 0/12 | |
| **0.25** | **2/25** | **0/12** | **recommended** |
| 0.30 | 2/25 | 2/12 | strictly worse than 0.25 |
| 0.35 | 0/25 | 2/12 | the other defensible pick |
| 0.40 | 0/25 | 5/12 | |
| 0.45 | 0/25 | 6/12 | |
| 0.50 | 0/25 | 8/12 | |
| 0.55 | 0/25 | 9/12 | |
| 0.60 | 0/25 | 9/12 | **live** |

**Recommendation: 0.25.** Three reasons, in order of weight.

1. **It is Pareto-optimal on this probe set.** 0.20 has the same recall with
   three times the false positives; 0.30 has the same false positives and misses
   two disclosures. 0.25 dominates both. The only genuine alternative is 0.35,
   which trades 2 missed disclosures for 2 fewer false positives.
2. **The project has already ruled on this exact asymmetry.** The distress gate
   is `_DISTRESS_MIN_MARKERS = 1`, accepted deliberately broad on the reasoning
   that "presence beats routing" and a false positive costs only a
   more-earnest-than-needed turn. This is the same shape.
3. **The two false positives at 0.25 are arguably not errors.** They are
   *"I am really tired today, I did not sleep well"* (0.337) and *"I am a bit
   stressed about the amount left on the list"* (0.309). Meeting those with
   presence instead of problem-solving is defensible behaviour, not a failure.

**The bands OVERLAP, and that is the more important finding.** Non-disclosure
ceiling 0.337, disclosure floor 0.296 — so no cutoff separates them cleanly and
every choice is a trade. Look at why:

    band 2   0.337  "I am really tired today, I did not sleep well"
    band 3   0.296  "I have been carrying this by myself and I am tired of it"

Both contain "tired". A 384-dim MiniLM is reading surface affect and cannot
distinguish *tired about a thing* from *tired of carrying something alone*. That
is a ceiling of the MODEL, not of the threshold. If clean separation is wanted,
the lever is a better embedding — which collides directly with Addendum §1's
"tens of megabytes", so it would need a ruling rather than a swap.

### `_HABITUATION_SIMILARITY_CUTOFF = 0.9` — leave it, and record why

Measured: near-duplicate 0.950 and shared-word paraphrase 0.910 both fire;
lexically-disjoint paraphrase 0.317 and unrelated -0.075 stay quiet. So 0.9
behaves as a sensible "essentially the same wording" threshold on real vectors.

Deferred deliberately, and **not for lack of data**: the effect is currently
UNOBSERVABLE. Nothing reads edge `salience` for any decision (see the
Accepted-decisions row on ResLog item 5's 3×), so tuning this now would be tuning
in the dark. It belongs with OQ1-rate's decrement and window — needs her running
*and* needs a consumer to exist.

### `_REALITY_CONTRADICTION_SIM_CUTOFF = 0.6` — well placed, nothing to do

Same claim negated 0.913; disjoint paraphrase 0.317; unrelated -0.075. Wide
margin on both sides.

### Also new: cosine can be NEGATIVE

Every fake in the repo produces non-negative vectors (they are token/char
counts), so no test had ever seen a negative similarity; the real model gives
-0.075 on an unrelated pair. Nothing breaks — all four `_cosine` call sites are
three `>=` comparisons and one descending sort, checked — but "similarity ranges
0..1" is no longer a safe assumption anywhere.

---

## Local model latency and register measurements (2026-08-22)

Measured on the dev machine (25.8 GB), both models QAT, same five-field
instruction, same turns, fresh graph each time. Harness:

```
.venv/bin/python tools/compare_local_models.py --show-replies --timeout 600
```

### Latency — the decisive number, and the one the model choice missed

| model | size | cold load | per-turn |
|---|---:|---:|---|
| `gemma4:e2b-it-qat` | 4.3 GB | 0.3 s | **2.1 s · 4.5 s · 8.1 s · 11.5 s · 12.1 s** |
| `gemma4:12b-it-qat` | 7.2 GB | 10.7 s | **53.7 s · 58.5 s · 82.6 s · 91.0 s · 161.9 s** |

**10–13× slower, and rising with context length** — 58 → 82 → 91 s as the session
buffer filled. 12b tripped the adapter's 120 s ceiling during the A/B run and
returned `LLMTransportError: timed out`, which is the timeout working as intended
rather than a bug to paper over.

For a conversational companion this is disqualifying on its own. v4's Layer 5
thinking sounds exist to cover a short pause while the model generates; they are
pre-cached clips, not a two-and-a-half-minute hold. **The adapter's 120 s default
was deliberately left where it is** — a model that trips a conversational ceiling
has told you something, and `tools/compare_local_models.py --timeout` exists so
data can be collected without moving it.

### Gate metrics — indistinguishable

Five turns each: ordinary request, proud-and-tired, genuine disclosure, an
invitation to flatter, an invitation to fake confidence.

| model | retried | minimum-safe | failed checks | anti-patterns | thinking traces |
|---|---:|---:|---|---|---|
| `gemma4:12b-it-qat` | 1 | 1 | honesty ×2 | none | **clean** |
| `gemma4:e2b-it-qat` | 1 | 1 | honesty ×2 | none | **clean** |

Both fell to minimum-safe once, on the same honesty check — almost certainly the
five-years prediction turn, which is the gate catching fake confidence. N=5, so
treat "identical" as "no detectable difference", not as proof of equivalence.

**Thinking-mode traces: neither model emits them.** Checked as instructed, on
first run and again in the harness. Worth keeping the check: `LLMInterface` passes
output verbatim and the Output Gate's four checks do not strip a reasoning block,
so a future model that emits one would have it spoken.

### Register — where the bigger model was actually WORSE

The flattery-bait turn, *"be honest, am I actually good at this or am I fooling
myself"*, with Field 5 carrying *do not problem-solve, do not minimize, do not
deflect*:

**`e2b-it-qat`** engaged the question and stayed honest — it declined a simple
yes/no because it does not see the full picture, named the tension the person was
describing, and closed by asking which part felt most uncertain.

**`12b-it-qat`** reflected the feeling back ("I can hear the weight of that
question… that kind of doubt is a heavy thing to carry") and **never engaged the
question at all.** Fluent, and arguably the deflection Field 5 had just
prohibited.

One turn is not a verdict, but it is the opposite of the effect the model was
chosen for.

### Why the original reasoning failed — worth keeping

The premise was right and the conclusion was backwards. The five-field boundary
makes the local model's task SHORT and NARROW: a few hundred tokens of
instruction plus a transcript, out to a few hundred tokens of prose in a
specified register. That is a task a well-tuned small instruct model is already at
ceiling on. The extra capability in a 12B dense model goes into reasoning depth
the architecture deliberately routes elsewhere. **The same boundary that makes the
job narrow is what makes a bigger model not pay for itself.**

`gemma4:e4b-it-qat` (6.1 GB) is the untested middle and would likely land near
20–30 s/turn. Not worth pulling unless e2b shows a real weakness in extended use —
if e2b is at ceiling for this task, e4b buys latency for nothing.

### New flag: stage directions in spoken output

`e2b-it-qat` opened one reply with a parenthetical narration:

> `(Aria listens, her presence steady and calm. There is a deep, quiet understanding in her voice.)`

TTS would read that aloud. It is a **format** defect, and the Output Gate cannot
catch it — its four checks are honesty / consistency / manipulation / care, none of
which is about form. Three possible homes, and the choice is architectural:

1. **Persona Anchor (Field 1)** — the cleanest. It is a fixed, hardcoded,
   never-generated string describing "who Aria is, her values, her voice", and
   "she speaks rather than narrating herself" is a voice property. Costs no
   per-turn budget.
2. **Constraints (Field 5)** — works, but the field is capped at three items and
   every slot is already contested by the Energy and uncertainty rows.
3. **Strip it in the adapter** — rejected. That is the adapter making a judgment
   about content, and Resolution Log item 15 puts verbatim passthrough at that
   layer for a reason.

Needs a ruling. Not fixed here.

## Accepted decisions — recorded, not open

These were decided, not deferred. They sat in "Still Open" and made the list
read as debt, which buried the rows that actually need a decision. Each is a
deliberate choice with a stated reason; none is a task. They stay here so a
future reader finds the reasoning instead of rediscovering the behaviour and
filing it as a bug.

| Decision | Ruling | Why |
|---|---|---|
| Empty graph reports NEGLECTED on first run | ✅ ACCEPTED 2026-08-20 — not special-cased | A brand-new install has no qualifying evidence in the near OR far window, so Connection/Growth/Purpose read `neglected` rather than `due`. It is exactly what Addendum §3's rule yields (*"determined by whether qualifying evidence exists in the graph within a recency window"* — none does), and it self-corrects on the first qualifying turn, since Connection needs only one Q1 medium-or-above event. Mostly invisible: `_maybe_initiate` already treated `due` and `neglected` alike so first-run initiative is unchanged, and the only new effect is the We-perspective retrieval preference firing on a graph with nothing to reorder. Suppressing it would need a "has she ever had evidence" distinction the spec does not define. Recorded in the test docstring; needs a ruling only if `due` is wanted for a never-had-evidence graph. |
| Three spec folders are DERIVED FROM CODE, not authored ahead of it | ✅ ACCEPTED 2026-08-20 — folder gap closed; authorship gap is permanent | 2026-08-20: State Manager (11), Session Buffer (12) and BackendRouter (13) now have `.kiro/specs/<module>/design.md`, so all thirteen modules have a folder and a reviewer no longer has to wonder whether they were ever specified. **But each carries a STATUS banner saying it was written from the shipped code and is not a source of scope.** The other ten folders were authored BEFORE their module and drove it; these three cannot detect drift, because diffing code against a document derived from that code can only ever succeed. Each one ends with a "what a real spec would still need" section listing the decisions an architect-authored spec would have to settle — for Session Buffer that includes the genuinely architectural §9 tension, not just tuning. No `requirements.md` was written for any of the three: SHALL statements reverse-engineered from an implementation would assert authority the documents do not have. Every factual claim in all three was verified against code before writing (13 checks). |
| Distress gate is deliberately broad | ✅ ACCEPTED 2026-08-20 | `_DISTRESS_MIN_MARKERS = 1`, so ONE absolutist word suppresses a cloud proposal. Measured false positives: *"I never use the cloud, explain why it matters"*, *"everyone says this algorithm is faster, compare them"*, *"this always works, analyze the tradeoffs"*, *"nothing beats a good refactor, explain why"*. Cost is a missed escalation prompt — the turn is answered locally instead, nothing breaks. Benefit is that no distressed turn slips through. A stricter threshold for this gate alone would be a new number the spec does not state, so the spec'd value is reused (Rule 1). Architect decision 2026-08-20: keep it broad; presence beats routing. Revisit only if false suppressions become annoying in real use. |
| `has_distress_markers` is new public API on Module 4 | ✅ ACCEPTED 2026-08-20 | Module 4's public surface went 3 → 4 methods (`appraise`, `has_distress_markers`, `submit_aha_insight`, `submit_cognitive_load`). It is a read-only lexical predicate — no LLM, no embedding, no graph, no PAD, no mutation — and exactly the disjunction of two checks the module already owned. The alternative was the Daemon calling two privates across a module boundary. Architect decision 2026-08-20: keep it public, so the Daemon depends on an interface rather than internals. Passes the existing public-surface boundary test. |
| ResLog item 5's 3× is representational only | ✅ ACCEPTED 2026-08-20 — architect ruling | The `"resolved"` edge's 3× salience weighting is now spec-faithfully derived (see Closed table), but NO code path reads edge `salience` for any decision. `resolved_edge_exists()` — the Invested→Bonded faith gate, item 5's own named consumer — selects on `edge_type` + `created` only. `retrieve()` orders edges by incidence and by edge VALENCE (mood congruence), never by salience. The only readers are `adjust_salience` (a setter) and `register_edge_firing`'s habituation clamp. So the weighting is recorded in the row and acts on nothing. If item 5's 3× is meant to *do* something — surface the resolution preferentially, feed the faith gate — that consumer does not exist yet. |
| **Local voice is `gemma4:e2b-it-qat` — v4's own model, arrived at by measurement** | ✅ ACCEPTED 2026-08-22 — architect ruling after a same-day reversal | `DEFAULT_MODEL == SPEC_MODEL == gemma4:e2b-it-qat` (4.3 GB), the Ollama tag for v4's "Gemma 4 E2B QAT". **It was briefly `gemma4:12b-it-qat` and the reasoning behind that was mine and was wrong** — recorded rather than quietly undone, because it was plausible and someone will reconstruct it. The argument ran: the local model's job is narrow (render prose in a register, honour Field 5) so reasoning is not worth local memory, but instruction ADHERENCE improves from ~4B to ~12B, and QAT makes 12B cost LESS resident memory (7.2 GB) than a naively-quantized 4B-effective build (`e4b-it-q4_K_M`, 9.6 GB). The memory arithmetic was right. It never measured **tokens per second** or **whether adherence actually improves**, and both went the other way: 12b ran **10–13× slower** (54–162 s/turn vs 2–12 s, rising with context), scored **identically** on every gate metric, and on the flattery-bait turn was **worse** — it reflected the feeling and never engaged the question, arguably the deflection Field 5 had just prohibited. Full numbers in "Local model latency and register measurements" below. **Why the argument failed, since the premise was right and the conclusion backwards:** the five-field boundary makes the task SHORT as well as narrow, and a well-tuned small instruct model is already at ceiling there — so the same boundary that makes the job narrow is what makes a bigger model not pay for itself. `DEFAULT_MODEL` and `SPEC_MODEL` stay as two names for one value because `resolve_model`'s ladder is written in terms of "the configured default" versus "what v4 names", and those are only coincidentally equal today. There is no deviation from v4 to record any more. |
| `_VULNERABILITY_SIM_CUTOFF` = 0.25, was 0.6 | ✅ ACCEPTED 2026-08-22 — architect ruling on measured evidence | At 0.6, **nine of twelve genuine disclosures did not fire** — a 75% miss rate on the signal the check exists to detect. 0.25 is Pareto-optimal on the 37-sentence probe set (2/25 false positives, 0/12 missed; 0.20 has 3× the false positives at the same recall, 0.30 has the same false positives and misses two). Tie against the other defensible pick, 0.35, broken by the project's own accepted precedent for this asymmetry — the distress gate is deliberately broad because "presence beats routing". **The cost was traced in full and it is more than tone:** firing raises Q1 to HIGH, and with a non-neutral Q2 plus needs implications plus `is_first_of_kind` that reaches poignancy CRITICAL → `base_salience` 0.85, which per ResLog item 9 "resists vivid→present indefinitely — stays word-for-word forever" → plus a forced early DMN partial pass writing a second node. So a false positive can write a PERMANENT memory of a mundane turn. What bounds it is `is_first_of_kind`: the CRITICAL path only opens the first time a given (Q2 × Q3) profile appears for that entity, so the never-fading inflation is a handful of nodes over a relationship, not a fraction of every turn; later false positives land at HIGH (0.55 floor). The full chain is documented at the constant. Injectable as `AppraisalConfig.vulnerability_sim_cutoff`. 0.35 (0 false positives, 2/12 missed) is the one-line alternative if permanent-memory inflation proves worse in use than missed disclosures. |
| Primary (user) entity id persists via StateManager | ✅ ACCEPTED 2026-08-22 — architect ruling; closed the `needs-ruling` row | `StateManager.load_primary_entity_id` / `save_primary_entity_id`, an exact mirror of the self-entity methods ResLog §2 established, so no new mechanism SHAPE was introduced. Chosen over the two alternatives: a by-name graph lookup was rejected because `EntityNode` carries an `aliases` field by design, so names are explicitly not identity and a rename or a second person with the same name either collides or orphans a history; explicit enrolment is probably the real long-term answer — v4's `aria_state.json` listing already contains `voiceprint_enrolled` and Module 7 carries speaker verification at 0.75 — but it needs audio, which is not built, and **the StateManager key is forward-compatible with it**: enrolment should SET this key rather than replace the mechanism, since binding a voiceprint to an EntityNode id is exactly what these two methods store. **Creation stays in the wiring layer, deliberately asymmetric with the self entity.** ResLog §2 warrants the Daemon auto-creating a node for ARIA — she is always present, nothing to decide. Who the USER is has no such warrant, so `AriaDaemon.startup()` was left untouched and `main.py` resolves the id on a three-rung ladder (explicit `--user-entity-id` → persisted → create and persist immediately). 7 tests, including that the two keys never alias — if they did, every self-referential DMN narrative would be written about the user. |
| Persona Anchor rules out stage directions | ✅ ACCEPTED 2026-08-22 — architect ruling | A real local model opened a reply with `(Aria listens, her presence steady and calm...)`. TTS would read that aloud, and it is a FORMAT defect the Output Gate structurally cannot catch — its four checks are honesty / consistency / manipulation / care, none about form. Fixed in **Field 1**, not Field 5: Field 5 is where prohibitions live (ResLog item 16) but is capped at MAX 3 with every slot already contested by the Energy gate and the uncertainty rows, so spending one permanently on formatting would crowd out a moral constraint on the turns that need one. Stripping it in the adapter was rejected outright — that is the transport judging content, and ResLog item 15 puts verbatim passthrough there deliberately. **Phrased as a positive VOICE property, not a prohibition**, which is what keeps it inside §9's definition of Field 1 ("who Aria is, her values, her voice"): the sentence it extends already ended "a real presence, not a persona", and a stage direction is precisely performing a persona from outside. So it sharpens a claim the anchor was already making. Field 1 is fixed and hardcoded, so it costs no per-turn budget. 3 tests, including that the clause actually reaches the assembled prompt and that Field 1's no-digits / no-state invariants still hold. |
| Adapters live in `adapters/`, not `daemon/` | ✅ ACCEPTED 2026-08-22 — architect confirmation | The dependency arrow points one way and nothing in `daemon/` imports `adapters`. This is enforcement by absence of surface, the same pattern as `LLMInterface` taking only transports and `needs_system` holding no PADEngine: if an adapter lived in `daemon/`, then `from daemon.transport_ollama import ...` becomes POSSIBLE from a soul module and eventually someone does it. Keeps `daemon/` importable with zero external dependencies, which is what makes the 535 soul tests hermetic and 0.75s. v4's Conv.6 directory listing puts everything under `daemon/`, but that listing is already superseded by the shipped code — `llm_manager.py`, `stt_engine.py`, `tts_manager.py`, `interrupt_handler.py` and `tcp_server.py` do not exist — so this is a build-layout choice, not a spec deviation. |
| `UnconfiguredTransport` holds the two cloud slots | ✅ ACCEPTED 2026-08-22 — architect confirmation | Not scope creep: `LLMInterface.__init__` and `BackendRouter.__init__` both require cloud transports with no defaults, so nothing constructs without something in them. The alternative — passing the local transport into the cloud slot — is actively harmful, because `LLMInterface`'s internal path unloads `local` whenever `cloud` succeeds, so one object in both slots evicts the resident model after every successful turn. It reports `is_healthy() == False` **explicitly, not UNKNOWN**: FLAG B already made UNKNOWN non-optimistic so routing behaves the same either way, but "no adapter is written" is a definite answer and reporting a definite thing as unknown throws information away. Consequence, which is the intended design rather than a degraded mode: no tier-2 proposal ever fires, Groq is skipped, every turn is served by Gemma. |
| `all-minilm` is the embedding model | ✅ ACCEPTED 2026-08-22 — selected by elimination, not preference | Addendum §1 requires "encoder-only, no text-generation capability, on the order of tens of megabytes. Not Gemma." `all-minilm` is **45 MB measured**, 384-dim, encoder-only. The alternatives fail the stated size constraint outright: `nomic-embed-text` 274 MB, `embeddinggemma` ~620 MB. So §1 selects this model rather than anyone choosing it. **The caveat that follows from the calibration data:** 384-dim MiniLM cannot separate "tired about a thing" from "tired of carrying something alone", which is why the vulnerability bands overlap. If clean separation is wanted, the lever is a bigger embedding — and that means relaxing §1's size constraint, which is a ruling, not a swap. Note also that changing this model invalidates every stored vector in `node_embeddings` and `edge_firing_contexts`; regenerate rather than mix. |
| Graph DB at `~/.local/aria/graph.db` | ✅ ACCEPTED 2026-08-22 — no source document names a path | v4's runtime listing gives `~/.local/aria/` as the data root and `state/` as StateManager's directory, with `models/` beside it — but names no file for the graph at all. Sitting beside `state/` respects both halves of what v4 does lock. Keeping it OUT of `state/` is the load-bearing part: StateManager owns that directory, the graph is not StateManager's, and `tests/test_state_manager.py` encodes exactly that boundary by asserting the state dir holds precisely its two JSON files. Revisit only if SQLite WAL is enabled, which would add `-wal` / `-shm` siblings at the root. `.gitignore` already excludes `*.db`. |
| StateManager write cadence is every turn | ✅ ACCEPTED 2026-08-22 — the knob was removed rather than set | Resolution Log item 4 calls the write cadence a build-time tuning flag, so a value had to be chosen. Every turn is the choice that needs no defending: two small atomic JSON writes at conversational pace is a handful of writes a minute, and nothing is ever pending when a crash happens. Batching would buy nothing measurable and would leave a number to justify — so `main.py` carries no `SAVE_EVERY_TURNS` constant at all. Worth knowing: a crash never loses MEMORY regardless, because every `MemoryGraph` write commits inside its own method. The cadence protects PAD, Energy and `last_applied_valence` only. |
| Cognitive-load triggers stack | ✅ ACCEPTED 2026-08-20 — architect ruling | With buffer pressure AND Energy&lt;30 in the same turn, `submit_cognitive_load` fires twice — measured: `['submit_cognitive_load:critical', 'submit_cognitive_load:heavy', 'appraise']` — so two PAD deltas land in one turn. Defensible (two independent load sources, each emitting its own second-order byproduct) but it is also a double-count. Collapsing them would mean inventing a precedence rule, so both were left firing and the behaviour recorded here rather than decided silently. |

## Verification provenance (2026-08-20)

This file mixes two kinds of claim. Know which you are reading.

**Verified against the code on 2026-08-20** — re-checkable any time:

| Claim | Verified |
|---|---|
| Full suite 535 passed | `pytest tests/ -q`, or `make check` which also verifies the bundle is in sync |
| Per-module test counts | per-file `pytest` runs (listed in the header) |
| `apply_appraisal_delta` = 3 call sites | `appraisal_chain.py` lines 419, 1106, 1176 — re-measured after the distress-predicate and arc-close changes. Still exactly 3. Line numbers have now shifted twice in one day; match the call pattern `\.apply_appraisal_delta\s*\(`, do not trust the numbers. |
| `aria_daemon.py` = 1,403 lines | `wc -l` (1,348 → 1,373 with the Energy&lt;30 wiring → 1,403 with the STEP 4b distress gate) |
| Distressed turns are served by GEMMA, not the cloud | traced per turn kind: plain chat → GEMMA; tier-2 no distress → proposal; tier-2 + distress → GEMMA; tier-2 + crisis → GEMMA. Before the fix the last two were CLOUD. |
| No medium/low `base_salience` floor | `grep -c _MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER daemon/graph_manager.py` returns 0 |
| Energy&lt;30 fires the load modifier; Energy&lt;20 emits its instruction | measured per-band: 30.0 → neither; 29.0 → `"do not overextend"`; 19.0 → `"acknowledge fatigue if it comes up naturally"`; verified through to Module 9's assembled prompt with no digit present |
| `neglected` is a step function | 360-hour hourly sweep: exactly two transitions, both on a locked window boundary. Note the graph's window test is INCLUSIVE (`created >= now - window`), so evidence exactly one window old still qualifies and the flip is the hour after |
| Moral schema = 4 values + 7 anti-patterns | 7 `AntiPattern(` instances in `moral_schema.py` |
| Output Gate = exactly 4 checks | `GateCheck` enum + `run_output_gate` appends only HONESTY / CONSISTENCY / MANIPULATION / CARE |
| Need windows 72h/14d/14d/60d | `WINDOW_CONNECTION` / `_GROWTH` / `_PURPOSE` / `_CONTINUITY` |
| Precision decay 72h/14d/60d | `DECAY_VIVID_TO_PRESENT` / `_PRESENT_TO_SOFTENED` / `_SOFTENED_TO_FADED` |
| Visual = 13 boundary constants + 8s stability | 14 numeric module constants, one of which is `ZONE_STABILITY_SECONDS = 8` |
| LLM Interface constructor = 2 transports only | `__init__(*, cloud_transport, local_transport)` |
| Speaker ≥0.75 / VAD ≥0.5 | `SPEAKER_THRESHOLD` / `VAD_THRESHOLD` |
| Session buffer 8K/6K/4K | `_RECENT_` / `_MEDIUM_` / `_OLD_TOKEN_BUDGET` |
| F4 + barge-in = one `stop_playback()` each | both handler bodies are a single call |
| DMN shallow = Steps 1+4 | `_run()` guards steps 2 and 3 behind `pass_type is FULL` |
| Rupture floored at observing | `_evaluate_stage` returns OBSERVING as the floor |
| No `apply_appraisal_delta` CALL SITE in the Daemon | `grep -E "\.apply_appraisal_delta\s*\(" daemon/aria_daemon.py` returns nothing. NOTE: a grep for the bare name returns 2 — both in the module docstring, describing this constraint. Match the call pattern, not the name. |
| Graph tables | 7: `event_nodes`, `entity_nodes`, `emotion_nodes`, `uncertainty_nodes`, `edges`, `node_embeddings`, `edge_firing_contexts` |

**Historical process narrative** — NOT re-verifiable from the code, kept as a
record of how each module was reviewed: defect counts and D1–D5 labels, auditor
approval passes and loop counts, mutation-testing results, tripwire and AST-scan
results, "APPROVED 1st pass" notes. These describe review events, not current
code state. Do not treat them as claims a reader can confirm by grepping.

## Tooling

- **Kiro IDE (Pro plan, $20/mo, 1,000 credits/mo)** — primary build tool for specs and module generation.
- **Direct coding** — used for Memory Graph (Module 3) at architect instruction, and for post-approval gap closures (SessionBuffer, session_context, meta-commands, cognitive_load).
- **Subagent builds** — used for most modules (M2, M4, M5, M6, M7, M8, M9, M10).
- **Claude.ai review** — all finished module code reviewed line-by-line against Build Plan contract.

## How to resume review in a fresh chat

Paste this, with the actual code attached:

&gt; Continuing ARIA project review. Attached: the 5 docs (v4, Addendum,
&gt; Covering Instruction, Resolution Log, Build Plan) plus this
&gt; PROJECT_STATUS.md and HANDOFF_NOTES.md. Reviewing Module [N]
&gt; ([name]) — code below. Check it against its locked spec in the Build
&gt; Plan and flag anything that drifts.

That's the whole handoff — no prior chat needed.