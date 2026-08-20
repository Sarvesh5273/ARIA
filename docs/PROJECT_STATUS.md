# ARIA — Project Status

Living tracker. Update after every module is approved. This file, plus
the docs/ folder, is everything a fresh review session needs — it does
not depend on any specific chat's history.

Counts and line numbers below were last measured against the code on
**2026-08-19** (full suite: 452 passed). They are measured values, not
estimates — if you change code, re-measure rather than assuming.

---

## Current runnable state — READ FIRST

**Nothing runs yet.** Thirteen modules are implemented and tested, which makes
it easy to read this file and conclude a working system exists. It does not:

- **No entry point.** No `main.py`, no runnable package, no CLI. The only
  `if __name__ == "__main__"` in the tree is a self-test inside
  `state_manager.py`.
- **No concrete adapters.** Nothing imports Ollama, MLX, the Groq SDK, the
  Azure SDK, `requests`, `httpx`, Whisper, Kokoro, Porcupine, Silero,
  sounddevice, PyQt6, libmpv, or any embedding library. Each is referenced
  only in docstrings, as the named reference implementation.
- **`requirements.txt` is pytest and its dependencies only.** No runtime
  dependency is declared.
- **Every external boundary is an injected Protocol** satisfied by test fakes:
  seven audio backends, `VideoWindow`, `EmbeddingModel`, three model
  transports.

So the state is a fully-specified, fully-tested soul architecture with no body
attached. The next build phase is adapters plus a wiring entry point, not more
soul modules.

---

## Modules — approval status

| # | Module | Status | Notes |
|---|--------|--------|-------|
| 11 | State Manager | ✅ Approved | Restored to daemon/state_manager.py after project reset. Reviewed line-by-line against spec — atomic writes, sibling-key preservation, superseded-key drop, PAD baseline fallback all confirmed correct. Extended additively for Module 1 (last_applied_valence field/methods, load_all/save_all widened) — not logically reopened. **GAP: no `tests/test_state_manager.py` exists** — this is the only module with no test file; verification is a `__main__` self-test block inside the module. Also no `.kiro/specs/state-manager/` folder. |
| 1 | PAD Engine | ✅ Approved | daemon/pad_engine.py, 53/53 tests passing. (Task bookkeeping note: `.kiro/specs/pad-engine/tasks.md` holds 22 items — 1–21 plus an inserted 7b — and all 22 are still unchecked. The code is complete and tested; the checkboxes were never ticked. Same for appraisal-chain 0/21 and memory-graph 0/24, both built outside the Kiro task loop.) OQ1 (soul-tick cadence) carried forward as a documented build-time gap, per Resolution Log. OQ2 (PAD bounds) RESOLVED — [0,1] clamp in apply_appraisal_delta confirmed intentional (physiological homeostasis; Mehrabian/Russell bounded scales; EMA decay is the recovery path), now documented in the module docstring and the pad-engine spec and covered by test_apply_appraisal_delta_clamps_to_bounds. Residual flagged: initialize() still does not clamp an out-of-range restored snapshot. OQ3 (VALENCE_UNCERTAIN coefficient) resolved — reuses EMA_COEFFICIENT_NEGATIVE, Emergency Type Detection "default to caution" precedent. OQ4 (restore-boundary coefficient) narrowed, not resolved — initialize()'s new restored_valence param + State Manager's last_applied_valence field cover the routine restart case; residual NotImplementedError raise (rare case: first-ever run, corrupted field, or crash before save) left unchanged. Known limitation logged: initialize() is not idempotent across repeated calls — see HANDOFF_NOTES.md, owed to Module 8. |
| 2 | Needs System | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/needs_system.py` (EnergyTracker substrate + NeedsEvaluator categorical + facade) + `tests/test_needs_system.py` (44 tests) + `.kiro/specs/needs-system/{requirements,design,tasks}.md`. 4 needs strictly CATEGORICAL (enum satisfied/due/neglected, no numeric score — enum-identity at 1h vs 70h in-window proves no gradation, passes percentage test); Energy is PAD-isolated SUBSTRATE (no PADEngine import; mutator tripwire never fires; real PADEngine byte-identical before/after; k_load/k_rest flagged TODO(build-time)); windows 72h/14d/14d/60d (ResLog 7) via graph_manager evidence queries; reverts satisfied→due purely by clock; output IS the shared NeedStates contract (now in `daemon/types.py`, OQ-4 closed). F-2a/b/c/d resolved. due/neglected kept binary (satisfied⇔evidence-in-window else due); 'neglected' preserved but never emitted → OQ-1 flagged (no percentage-free split). |
| 3 | Memory Graph | ✅ Implemented + tested; OQ resolutions applied + RE-AUDITED (criteria a–e PASS) | Full spec at `.kiro/specs/memory-graph/{requirements,design,tasks}.md`; code `daemon/graph_manager.py` + `tests/test_graph_manager.py` (60 tests). Coded directly (not via Kiro) at architect instruction. SQLite backend; injected embedding model. Implementation audit fixed 5 defects (D1 continuity recency, D2 retrieve edge-dedup, D3 first-of-kind = Addendum §6 Q2×Q3 profile, D4 EmotionNode-stays-vivid, D5 resolution_path→null). Architect OQ resolutions RESOLVED+implemented: OQ3 (node-embedding side-table), OQ5 (total-elapsed decay), OQ4 (retrieval pure reorder, mood PRIMARY/need SECONDARY, no coefficient), OQ1-trigger (habituation via `register_edge_firing`, edge-salience-only guard). DEFERRED (TODO-flagged): OQ1-rate, OQ2 (base_salience 0.35/0.15). NOT this module: OQ6 Purpose→M2; max-5-no-evictable = raise. **Final re-audit (criteria a–e) PASS**: retrieval is stable-sort ordering only (no weighted score — proven by hard-partition test); salience/habituation never wired to PAD/appraisal (no PADEngine import); deferrals all explicitly stubbed; no numeric beyond stated placeholders. F-3b/F-3c resolved (ResLog 8/10). |
| 4 | Appraisal Chain | ✅ Implemented + tested (subagent build→audit loop) | `daemon/appraisal_chain.py` + `tests/test_appraisal_chain.py` (53 tests) + `.kiro/specs/appraisal-chain/{requirements,design,tasks}.md`. Full suite **452 passed**, verified independently. Built by subagent, independently audited (found+looped 1 medium defect — vacuous test masking a neutral-turn PAD crash — fixed so purely-neutral appraisal emits NO PAD event). Auditor APPROVED via mutation-testing: ×1.5 negativity-inflation FAILS the symmetric test (proves no weighted formula); PAD purity = 3 apply_appraisal_delta sites, no direct PAD writes, no graph._conn reach-ins. PAD delta = categorical direction {−1,0,+1} × categorical Q1 tier; coping_potential transient/emergency-gate-only. F-4a/F-4b/F-4f RESOLVED (ResLog 12/10); F-4d/F-4e = flagged build-time placeholders. LOW follow-up: conflict-arc 2nd close condition (absent-turns) is dead code + inert knob — wire or mark deferred-with-F-4d. |
| 5 | Soul Filter | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/soul_filter.py` + `daemon/moral_schema.py` (shared resource: 4 values + 7 doc-cited anti-patterns) + `tests/test_soul_filter.py` (36 tests) + `.kiro/specs/soul-filter/{requirements,design,tasks}.md`. Full suite **452 passed**. Auditor independently verified 5 philosophy proofs: no numbers/state cross the LLM boundary (Behavioral Register = PAD-vs-baseline categorical words, Relational Register = stage→NL no label, only user message crosses); Output Gate = exactly 4 checks {honesty,consistency,manipulation,care}, ZERO LLM (proven w/ RaisingLLM), no 5th check, no numeric score, verify-not-decide (Principle 27); emergency REPLACES the five fields; moral-violation → corrective retry → minimum-safe; Field 4 = HOW-clause only (memory sentinel proven never to cross). F-5a/F-5b RESOLVED; OQ-M1 anti-pattern-list closure flagged (taxonomy not invented). NeedStates/LLMClient are injected contracts (M2/M9 pending). LOW follow-ups: post-emergency re-entry instruction (needs Daemon cross-turn state — defer to M8); dead ENERGY_CRITICAL=20 constant. |
| 6 | DMN / Idle Consolidation | ✅ Implemented + tested (subagent build→audit, looped 1×) | `daemon/dmn.py` + `tests/test_dmn.py` (44 tests) + `.kiro/specs/dmn/{requirements,design,tasks}.md`. Full suite **452 passed**, verified independently (dmn imports OK). Audit caught a stray-space IndentationError making the module unimportable (build report's pass-count was not reproducible) → looped → fixed. 3 headline constraints verified: DMN NEVER writes PAD (aha → `submit_aha_insight` EVENT to Appraisal Chain; live PADEngine tripwire byte-identical); relational_stage transitions CATEGORICAL (enum, ≤1 gate-step, rupture −1 floored at observing, no score); self-narrative MORAL-GATED (blocked even with no audience). Quality record from OBSERVED next-turn reaction (anti-flattery). Energy&lt;20/critical → shallow (Steps 1+4). F-6b/c/d resolved. FLAGGED for M8/integration: OQ-1 Appraisal needs `submit_aha_insight` event entry; OQ-2 Memory Graph needs highest-salience-unconnected + predictability/dependability predicates; LOW: post-rupture BONDED re-advance on pre-rupture edge (fresh-evidence unspecified). |
| 7 | Audio Pipeline | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/audio_pipeline.py` + `tests/test_audio_pipeline.py` (29 tests) + `.kiro/specs/audio-pipeline/{requirements,design,tasks}.md`. Single module (ResLog 15): input chain (capture→ring→wake→speaker≥0.75→VAD→Whisper→text) + output chain (PAD→prosody→cloud→Kokoro fallback), all backends injected Protocols. F4/barge-in ZERO internal effect (tripwire vs real PADEngine: PAD byte-identical AND never even read; each handler = one playback.stop()); never writes PAD (read-only prosody), never appraises. Prosody directions per v4 Layer 5 (arousal inverse, dominance→lower pitch); magnitudes flagged TODO(F-7-prosody). Satisfies Daemon AudioPipelinePort unchanged. |
| 8 | Daemon / Soul Tick | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/aria_daemon.py` (1,348 lines) + `tests/test_daemon.py` (44 tests) + `.kiro/specs/daemon/{requirements,design,tasks}.md`. Full suite **452 passed**, verified independently. Two clocks SEPARATE (soul_tick never runs DMN; dmn_tick never decays PAD); Daemon computes no feeling (no `apply_appraisal_delta` CALL SITE in its source — the string occurs twice in the module docstring describing the constraint, so grep for `\.apply_appraisal_delta\s*\(` to verify, not the bare name); F4/barge-in ZERO internal effect (tripwire: PAD/Energy/graph/state byte-identical; each handler = one stop_playback()); HANDOFF contract exact (initialize() once + guarded, consistency_flags cleared each session, last_applied_valence round-trips); initiative keys on 'due', fires once, no-nag, enters at soul_filter skipping wake/STT. ADDITIVELY closed DMN's contract gaps (baseline preserved exactly): appraisal_chain.submit_aha_insight (aha routes through appraisal, DMN still never writes PAD), graph_manager predictability/dependability_evidence (structural booleans) + highest_salience_unconnected. F-8b resolved (ResLog 10); F-8a cadences build-time. OQ-2 initiative-on-'due' flagged. |
| 9 | LLM Interface | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/llm_interface.py` + `tests/test_llm_interface.py` (36 tests) + `.kiro/specs/llm-interface/{requirements,design,tasks}.md`. Full suite **452 passed**. Boundary is STRUCTURAL: constructor takes only {cloud_transport, local_transport} — no graph/PAD/needs/appraisal handle. It imports exactly ONE internal module — `from daemon.soul_filter import ...` (line 74), for the instruction dataclasses plus a re-exported `LLMClient` — and nothing from graph/PAD/needs/appraisal. The guarantee is the absent CONSTRUCTOR PARAMETER, not an absent import; `soul_filter.py` does not import back, and that one-way direction is what keeps the boundary structural. Cloud + Gemma get the byte-IDENTICAL prompt via one pure assemble_prompt() (F-9a / ResLog 14, proven by object identity). NO judgment (F-9b / ResLog 15 — verbatim passthrough even for gate-failing text; retries only when Soul Filter re-calls). Satisfies Soul Filter's LLMClient contract (isinstance passes, soul_filter.py unmodified). OQ-9a..9d flagged placeholders. **NOTE:** `session_context` parameter added post-approval — ephemeral conversation transcript, not internal state. |
| 10 | Visual Layer | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/visual_layer.py` (478 lines) + `tests/test_visual_layer.py` (24 tests) + `.kiro/specs/visual-layer/{requirements,design,tasks}.md`. Full suite **452 passed**; all modules import OK. Only READS PAD (tripwire vs real PADEngine: writes==0, byte-identical; AST scan imports only read-only PADSnapshot, no graph/appraisal/needs/state/PyQt6/mpv); zone selection CATEGORICAL (Zone enum via boolean threshold membership, not a distance/score — 13 boundary constants + 8s stability cited to v4 lines 1145-1160/1316); talking-vs-idle follows speaking-state; cloud-fail → INWARD_WAITING; runs independent of LLM. F-10a resolved (ResLog 15). Exposed a clean VisualLayerPort — daemon UNMODIFIED. TODO(F-10-zone-precedence) flagged. |
| 12 | Session Buffer | ✅ Implemented + tested | `daemon/session_buffer.py` + `tests/test_session_buffer.py` (13 tests). **Not in original Build Plan.** Ephemeral 3-tier conversation buffer (Recent 8K tokens / Medium 6K / Old 4K). Rule-based summarization. Meta-commands: `"rest"`, `"focus"`, `"unfocus"`. Cognitive load tracking (`fullness_state()`). Fuzzy trigger detection with word-boundary matching. Wired into Daemon's `route_inbound_turn()` — session_context passed to Soul Filter → LLM Interface. |
| 13 | BackendRouter | ✅ Implemented + tested | `daemon/backend_router.py` + `tests/test_backend_router.py` (16 tests). Pure INFRASTRUCTURE: 3-tier backend pool (tier_0 Gemma local / tier_1 Groq / tier_2 Azure-Kimi), keyword-heuristic tier-2 classifier (no neural model, word-boundary regex), session-scoped override, 30s-cached health probe, and `select()` returning `(transport, propose_flag)`. Touches NO PAD/graph/needs/appraisal/personality state — proven by an AST import scan and a `vars()` check. TODO(build-time): `TIER_2_KEYWORDS` lexicon, `HEALTH_CACHE_TTL_SECONDS`. FLAG A: CLOSED (Track A) — selection is now wired end-to-end: `AriaDaemon.route_inbound_turn()` calls `BackendRouter.select()`, hands the returned transport to `SoulFilter.respond(transport=...)`, which passes it through opaquely to `LLMInterface.generate(transport=...)`, which calls it directly instead of running its own cloud-first chain. Fallback order swapped: Gemma (default voice for conversation) is now tried BEFORE Groq (reserved for future tools/search, now only a fallback); new `ensure_local_loaded()` is called once by `AriaDaemon.startup()` so Gemma loads at startup and stays resident. `medical`/`legal` removed from `TIER_2_KEYWORDS` (too broad for a personal companion). FLAG B: still OPEN — health probing is optimistic (a transport exposing no `is_healthy()` is assumed reachable). NOTE: no `.kiro/specs/backend-router/` folder yet — spec deferred. Three modules have no spec folder: State Manager (11), Session Buffer (12), BackendRouter (13); ten folders exist for thirteen modules. |

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
| BackendRouter FLAG A — selection wired (Track A) | ✅ CLOSED | `LLMInterface.generate()` accepts an optional caller-supplied `transport` (opaque passthrough, bypasses the internal cloud-first chain); `AriaDaemon.route_inbound_turn()` calls `BackendRouter.select()` and threads the result through `SoulFilter.respond(transport=...)`; a `DaemonState` (NORMAL/PROPOSING_CLOUD) state machine owns the pause-and-ask UX for `propose=True`, including a soul-tick-driven timeout; backend meta-commands ("use cloud"/"stay local"/...) are intercepted and call `set_override`/`clear_override`; `AriaDaemon.startup()` calls `BackendRouter.ensure_local_loaded()` once, so Gemma loads at startup and stays resident (the router never unloads it). See HANDOFF_NOTES.md "Track A" for the three FLAGS this raised (timeout PAD delta not implemented by design; ambiguous proposal response defaults to negative; no crisis pre-check). (Moved here from the Still Open table, where it sat marked ✅ CLOSED.) |

## Still Open

| Item | Status | Note |
|------|--------|------|
| OQ6 Purpose evidence + max-5 cap | 🔓 OPEN | raises; cognitive ceiling alternative flagged |
| `state_manager.py` has no test file | 🔓 OPEN | Module 11 is marked ✅ Approved but there is no `tests/test_state_manager.py` — its only verification is a `__main__` self-test block inside the module |
| ENERGY_CRITICAL (&lt;20) instruction | 🔓 OPEN | imported in soul_filter.py, never emitted |
| Energy &lt;30 → Appraisal Stage 2 | 🔓 OPEN | documented, not implemented |
| `neglected` need state emission | 🔓 OPEN — **OQ-1's stated rationale is wrong for Continuity** | Addendum §3 mandates three categorical states: *"satisfied / due / neglected"*. The code emits two. `needs_system.py` justifies this by claiming no source gives a percentage-free categorical basis to split `neglected` from `due` — but Addendum §3's Continuity row does: *"Satisfied when an update extends the narrative coherently; **neglected** when updates have gapped for a long stretch, or new evidence contradicts rather than extends it."* "Contradicts rather than extends" is categorical and needs no percentage. So `neglected` is implementable for Continuity at least. Connection / Growth / Purpose have no comparable stated basis and remain genuinely open. Corrected 2026-08-19. |
| Conflict-arc 2nd close condition | 🔓 OPEN — **unimplemented spec requirement, not merely dead code** | Addendum §1 specifies TWO close conditions: the arc *"closes when a later EventNode on that entity_ref flips to Q2=positive/neutral, **or enough turns pass without that entity recurring**"*. Only the first is implemented. `_arc_absent_turns` is written to and never read, so the second spec'd condition does not exist in behaviour. Reclassified 2026-08-19 — earlier described as "dead code / inert knob", which understated it: this is a required mechanism that is absent, not a spare knob. |
| OQ1-rate habituation magnitudes | 🔓 DEFERRED | `_HABITUATION_SIMILARITY_CUTOFF = 0.9`, `_HABITUATION_DECREMENT = 0.05`, `_HABITUATION_RECENT_FIRINGS = 5` — all carry `TODO(OQ1-rate)` and the module docstring lists them under "DEFERRED (explicit placeholder + TODO — do NOT treat as final)". Runtime-tuned. **This row previously appeared in the Closed table marked resolved, which contradicted both the code and the Module 3 row. The trigger shape is closed; the rate is not.** |
| OQ2 medium/low base_salience | � **CONTRADICTS ResLog item 9** | **Escalated 2026-08-19 — needs an architect ruling.** Resolution Log item 9, line 96 states literally: *"Medium/Low → no floor, decays/discards as already locked."* That is a positive instruction — no floor — not silence. But `graph_manager.py` sets `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER = {MEDIUM: 0.35, LOW: 0.15}`, and its comment justifies this by claiming *"no source yields a starting base_salience for medium/low"*. That is a misreading: the source yields "no floor". An explicit instruction was read as a gap and the gap was filled with invented numbers — the exact failure the no-invented-numbers rule exists to prevent, against the HIGHEST-precedence document. This row and the same claim in the Module 3 row previously repeated the misreading. Ruling needed: remove the floors so medium/low decay as ResLog specifies, or record a Resolution Log amendment authorising them. Do NOT silently keep both. |
| Build-time tuning constants | 🔓 OPEN | All still placeholders (intentional). Full inventory: `PAD_HISTORY_LENGTH`; `K_LOAD`/`K_REST` (F-2a/F-2b); OQ2 base_salience and OQ1-rate habituation (above); appraisal arc turn-counts + distress/social lexicons (F-4d/F-4e); moral-schema anti-pattern markers (OQ-M1); soul-filter deflection markers; prosody magnitudes (F-7-prosody); zone precedence (F-10-zone-precedence); `TIER_2_KEYWORDS` + `HEALTH_CACHE_TTL_SECONDS`; soul-tick 3s / DMN-tick 30s (F-8a). |
| Gap-closure work is unrecorded in the precedence documents | 🔓 OPEN — bookkeeping, **not** a Rule 1 violation | Session Buffer (12), BackendRouter (13), meta-commands (`rest`/`focus`/`unfocus`), backend meta-commands, and Track A wiring appear in NONE of v4, the Addendum, or the Resolution Log. Verified 2026-08-19: `backend`, `Ollama`, `Groq`, `Azure`, `Kimi`, `"rest"`, `unfocus`, `session buffer` return zero hits across all four source documents. These were architect-directed, and Rule 1 explicitly ends "the architect resolves it" — so they are authorised, not invented. The gap is that the authorisation is recorded nowhere in the precedence chain, leaving a future reviewer unable to distinguish "architect approved" from "agent invented". Fix: add a Resolution Log entry covering the gap-closure phase. |
| `session_context` vs Addendum §9 | 🔓 OPEN — **Rule 2 flag, do not resolve silently** | Addendum §9 says *"Five fields, fixed order, nothing else"* and lists *"historical conversation summaries"* among what never crosses under any circumstance. SessionBuffer's Medium tier passes exactly that — summaries — and the Old tier passes topic tags. The prohibition's wording targets *past sessions* ("anything Aria remembers about the user from past sessions"), and session context is current-session only, so this may be outside its scope. But "nothing else" is unqualified. `project-rules.md` resolves this in favour of allowing session context as a third sanctioned surface — however `project-rules.md` is the always-loaded non-negotiables file, NOT one of the three documents in the precedence chain. So the resolution currently lives outside the chain it would be overriding. Needs an explicit Addendum or Resolution Log amendment. |
| BackendRouter FLAG B — optimistic health | 🔓 OPEN | `_probe_one` returns True for any non-local transport exposing no `HealthProbe`, so `check_health()` always reports groq and azure healthy. Three real consequences, not just a placeholder: (1) the tier-2 propose branch is gated on `health["azure"]`, so a keyword match always proposes escalation even when Azure is down; (2) groq is selected whenever gemma is unavailable, even if groq is dead; (3) the `return None, False` "everything is down" degradation path is effectively unreachable. Failures therefore surface as an `LLMTransportError` at `generate()` time rather than being pre-empted. NOTE: gemma is tried FIRST and groq is the fallback (Track A order swap) — an earlier version of this row described the chain backwards. Resolve when the real cloud adapters are written (simplest non-inventing option: adapters implement `is_healthy()` backed by their own last `LLMTransportError` state). |

## Verification provenance (2026-08-19)

This file mixes two kinds of claim. Know which you are reading.

**Verified against the code on 2026-08-19** — re-checkable any time:

| Claim | Verified |
|---|---|
| Full suite 452 passed | `pytest tests/` |
| Per-module test counts | per-file `pytest` runs |
| `apply_appraisal_delta` = 3 call sites | `appraisal_chain.py` lines 412, 995, 1065 |
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