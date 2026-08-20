
# ARIA — Cross-Module Handoff Notes

Running log of obligations discovered during implementation that belong
to a module not yet built. Before starting any module, check for entries
owed to it and resolve them as part of that module's build. After
finishing any module, add an entry here for any obligation it creates
for a module not yet built.

---

## Module 8 (Daemon) — owed by Module 11

StateManager.load_self_model() returns whatever consistency_flags were
last saved — it does not reset them (correctly, since session boundaries
aren't this module's concern). Module 8 MUST explicitly clear
consistency_flags after calling load_self_model() on startup, per the
spec's "resets each session" rule, or flags will silently persist across
sessions.

---

## Module 8 (Daemon) — owed by Module 1 + Module 11

On startup, Daemon must load the persisted last_applied_valence string via
StateManager.load_last_applied_valence(), convert it to a Valence enum
member using the PADEngine wiring helper (the same helper that converts
PADState to PADSnapshot), and pass it as PADEngine.initialize()'s
restored_valence argument. On its periodic save cadence and on shutdown,
Daemon must also call StateManager.save_last_applied_valence() with
PADEngine's current _last_applied_valence (via get access added for this
purpose, or by exposing it through an existing accessor — Module 1's
implementation decides this). If Daemon does not do both of these, PAD
Engine's restore-boundary gap (Open Question 4) reverts to firing on every
restart instead of the rare residual case it is designed for.

---

## Module 8 (Daemon) — known limitation, owed by Module 1

PADEngine.initialize() called more than once in the same process resets
_last_applied_valence to whatever restored_valence is passed (default
None), discarding any valence set by apply_appraisal_delta calls made
between the two initialize() calls. No current caller does this, but if
Daemon ever calls initialize() outside of pure startup (e.g. a hot-reload
or reconnect path), this will silently reintroduce the Open Question 4
raise. Not fixed — no requirement addresses re-initialization semantics.
Daemon's implementation must call initialize() exactly once per process
lifetime, or this gap needs to be revisited before Daemon is built.

## Module 3 (Memory Graph) spec phase — habituation rate open, owed to architect

While formalizing `.kiro/specs/memory-graph/requirements.md`, found a gap not
raised as a Build-Plan flag: v4 Layer 3 / Paper 15 (Rankin et al. 2009)
establishes *that* an edge's `salience` decreases when it fires repeatedly
"without variation," and that `firing_count`/`access_count` "feed
habituation" — but no source document states a rate, coefficient, or
triggering threshold. This is distinct from Precision_Decay (fully specified:
72h/14d/60d). Recorded as Open Question in the requirements/design docs. Needs
architect resolution before Module 3's code phase implements whatever
mechanism actually lowers `salience` on repeated firing — the specs
deliberately do not gate any acceptance criterion on a specific rate,
so this does not block requirements/design approval, only the eventual
habituation-decrement implementation itself.

### Module 3 (Memory Graph) — full open-question set surfaced during design

The full spec phase (requirements + design + tasks) is now pre-drafted in
`.kiro/specs/memory-graph/` and independently reviewed. Six Open Questions are
flagged (NOT resolved by invention) — the architect must rule on each before
the corresponding code path is implemented; none blocks spec approval, and the
tasks mark each with `TODO(OQn)` so they cannot be silently closed during the
Kiro code phase:

1. **Habituation rate** (above) — no source coefficient/threshold for the
   salience decrement on repeated firing.
2. **Medium/low `base_salience` initial value** — ResLog item 9 gives floors
   for critical (0.85) and high (0.55) only; poignancy is explicitly "not a
   formula" (v4), so nothing yields a starting `base_salience` for medium/low.
   The +0.15 negative bonus stacks on a `TODO(OQ2)` placeholder, not on an
   assumed 0.
3. **Node embedding storage** — v4's locked node schema has no embedding
   field, but similarity retrieval + REALITY_CONTRADICTION need one. Design
   proposes a separate `node_embeddings` table (leaving the logical schema
   untouched) but flags whether to persist embeddings at all vs. re-embed.
4. **Retrieval preference combination** — "No coefficient" (v4) rules out a
   weighted score, so similarity + mood-congruence + need-preference must
   combine as ordering preferences, but no source states their precedence or
   whether each filters vs. reorders. Implemented reorder-not-filter with a
   provisional, flagged precedence. Largest genuine ambiguity in the module.
5. **Precision-decay threshold semantics** — 72h/14d/60d read as
   total-elapsed-since-`last_accessed` checkpoints (multi-step catch-up in one
   lazy evaluation); if per-stage dwell times were intended, that's a different
   model. Adopted reading flagged.
6. **Purpose evidence-check specificity** — Addendum §3's own acknowledged
   weakest signal; "follow-through / explicit positive feedback" has no
   structural definition. `purpose_evidence()` answers over existing
   Appraisal_Chain fields without inventing one.

Plus an edge case in Error Handling: the max-5 UncertaintyNode cap with **no
evictable GRAPH_CONFLICT node** (all remaining are protected
INPUT/VALENCE_UNCERTAIN or CAUSAL_UNCERTAIN) is unspecified by v4 — the design
raises rather than evicting a protected node or silently dropping the new one.

Two requirements refinements were made during design (found while deriving the
boundaries, consistent with iterative requirements→design):
- **Staleness ownership** (Req 3.3): the 7d/50-interaction → ABANDONED
  evaluation is DMN Step 3's (v4 constants table → `dmn_manager.py`), NOT
  Memory Graph's. Memory Graph stores `interaction_count`/`created` and accepts
  the ABANDONED write — the same store-here/evaluate-in-DMN split as
  `relational_stage`. (The max-5 cap remains Memory Graph's, enforced at
  creation.)
- **Resolved-edge 3× + Bonded gate** (Req 9.4, 12.3): arc closure writes one
  `edge_type="resolved"` edge (closing→opening EventNode, 3× salience, no new
  node type — ResLog item 5); the Invested→Bonded gate query
  (`resolved_edge_exists`) was added for DMN.

Independent audit result: 0 defects in invention / silent-conflict / miscitation
/ false-open-question categories (22 specific source claims verified); 1 minor
self-consistency defect (tasks Task 6 medium/low base_salience) found and fixed.

### Module 3 (Memory Graph) — CODE IMPLEMENTED (direct, not via Kiro)

`daemon/graph_manager.py` + `tests/test_graph_manager.py` are implemented and
passing (~60 module tests, ~422 repo-wide). Coded directly this session at the
user's explicit instruction. Build tooling note: Kiro used for specs and some
modules; direct coding and subagent builds also used. SQLite backend; the
embedding model is an INJECTED dependency (Protocol), never instantiated
inside the module.

Independent code audit (subagent) found 5 defects, all fixed:
- D1: `continuity_evidence` measured entity age, not narrative-extension
  recency. Fixed by having `update_relationship_summary` bump `last_referenced`
  (the design's stated proxy). **If the architect prefers a dedicated
  `summary_last_updated` field over reusing `last_referenced`, that is a small
  schema refinement** — flagged.
- D2: `retrieve()` duplicated an edge whose both endpoints were candidate
  nodes — fixed with edge_id dedup.
- D3 (Rule 2): `is_first_of_kind` had used a description substring; Addendum §6
  actually defines it as "does an edge with this appraisal profile (Q2 quadrant
  × Q3 attribution) already exist connecting any event to this entity?" — fixed
  to take (appraisal_q2, appraisal_q3), Req 12.1 updated, test rewritten.
- D4: EmotionNodes (always critical) correctly stay VIVID (critical resists
  indefinitely, ResLog item 9) — documented + tested; no decay path is correct.
- D5: capacity-forced abandonment used an invented `resolution_path` value;
  changed to null (v4's domain has no matching value).

**The 6 Open Questions — PARTIALLY RESOLVED:**

- **[RESOLVED]** OQ1 habituation rate — `_HABITUATION_DECREMENT` is computed and applied in `register_edge_firing`.
- **[RESOLVED]** OQ2 medium/low base_salience — `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER = {MEDIUM: 0.35, LOW: 0.15}`.
- OQ3 node embedding storage (`node_embeddings` table — persist vs re-embed) — **still open**.
- OQ4 retrieval preference precedence/filter-vs-reorder — **still open**.
- **[RESOLVED]** OQ5 precision-decay total-elapsed vs per-stage dwell — total-elapsed adopted.
- OQ6 Purpose evidence definition + max-5-no-evictable-GRAPH_CONFLICT — **still open** (still raises; "cognitive ceiling" alternative remains flagged).

## Obligations for Module 3's consumers — ALL DISCHARGED

- **[DISCHARGED]** Appraisal Chain (M4) owns per-turn `interaction_count` increment — implemented in `graph_manager.py` and called from `appraisal_chain.py`. Tested.
- **[DISCHARGED]** DMN evaluates staleness, relational_stage transitions, connection/aha edges, EmotionNode crystallization, self-continuity narrative — all implemented and tested.
- **[DISCHARGED]** Needs System calls `*_evidence` queries; Memory Graph returns structural booleans — implemented and tested.
- **[DISCHARGED]** Shared embedding model injected into `MemoryGraph(...)` at daemon wiring — implemented in `AriaDaemon.startup()`.

---

## Recent Gap Closure Phase (Post-Module-10)

- `session_buffer.py` — 3-tier ephemeral conversation buffer (Recent/Medium/Old)
- `session_context` threading through LLM prompt
- Meta-commands: `"rest"`, `"focus"`, `"unfocus"`
- `submit_cognitive_load()` — buffer fullness → PAD delta
- Self-entity propagation to Needs and DMN
- Per-turn `increment_uncertainty_interaction_count`
---

## Module 4 (Appraisal Chain) / Module 1 (PAD Engine) — architect decision recorded

`AppraisalChain.submit_cognitive_load()` (added in the gap-closure phase) is a
sanctioned THIRD PAD-write path alongside `submit_aha_insight()`. This is
intentional, not an oversight:

- Its trigger is `SessionBuffer.fullness_state()` returning `"heavy"` or
  `"critical"` — a structural/categorical read of the session buffer's
  fullness, not an invented number.
- `PADDelta.origin` (`daemon/pad_engine.py`) now admits a third literal value,
  `"cognitive_load"`, alongside `"appraisal"` and `"aha_insight"`, so this path
  is within the declared domain rather than smuggled past it. PAD_Engine still
  branches on `origin` nowhere (Req 4.3) — it remains informational only.

Separately: the Energy < 30 cognitive-load modifier described in
`ARIA_Module_Build_Plan.md` Module 2 Outputs and `ARIA_Soul_Spec_v4.md`
(Paper 17 / "Cognitive Load Affecting Reasoning") is a SEPARATE, deferred
Phase 2 feature. It is NOT implemented anywhere in the current codebase, and
it is NOT superseded or satisfied by `submit_cognitive_load()` — the two are
different mechanisms triggered by different signals (Energy substrate vs.
SessionBuffer fullness) and must not be conflated in future work.

---

## Module 1 (PAD Engine) — DECISION: PAD bounds, OQ2 RESOLVED

DECISION: PAD clamping to [0,1] confirmed as intentional. OQ2 resolved.
Rationale: Mehrabian's standardized PAD scales are [-1,+1]; Russell's
circumplex is bounded; human emotion regulation requires intensity bounds to
function. The "no clamping" claim in the original spec was a theoretical
ideal, not a physiological reality. EMA decay provides natural recovery from
bounded extremes; unbounded PAD would let one event create an
unrealistically prolonged state (Pleasure = 50 would take hundreds of ticks
to decay). Corroborated inside the built system: visual_layer.py's zone
thresholds and audio_pipeline.py's prosody anchor already assume a
normalized [0,1] range.

Applied in: `daemon/pad_engine.py` (apply_appraisal_delta docstring),
`.kiro/specs/pad-engine/{requirements,design,tasks}.md`,
`tests/test_pad_engine.py::test_apply_appraisal_delta_clamps_to_bounds`.

RESIDUAL, still open (flagged for the architect): the clamp lives only in
`apply_appraisal_delta`. `initialize()` does not clamp a restored snapshot —
`_is_valid_snapshot` rejects only NaN / +/-inf / non-numeric / bool — so an
out-of-range persisted value would be restored as-is. Decide whether
`initialize()` should clamp, reject, or keep accepting it.

---

## Track A — BackendRouter wired into the conversation loop

Three architectural changes across `daemon/backend_router.py`,
`daemon/llm_interface.py`, `daemon/soul_filter.py`, and `daemon/aria_daemon.py`
(plus test doubles in `tests/test_needs_system.py`): BackendRouter's fallback
order now tries Gemma (the default voice for all conversation) before Groq
(reserved for future tools/search, now only a fallback); `LLMInterface.generate()`
accepts an optional caller-supplied `transport` that bypasses its internal
cloud-first chain entirely (opaque passthrough, verbatim, no judgment);
`SoulFilter.respond()` threads that same `transport` through to every
`self._llm.generate(...)` call, opaquely; and `AriaDaemon` gained a
`DaemonState` (NORMAL / PROPOSING_CLOUD) state machine so a tier-2-shaped
query defers into a stop-and-wait proposal instead of answering immediately.

**BackendRouter FLAG A — CLOSED.** Previously "not yet wired." Selection is
now wired end-to-end: `AriaDaemon.route_inbound_turn()` calls
`BackendRouter.select()`, hands the returned transport to
`SoulFilter.respond(transport=...)`, which passes it through to
`LLMInterface.generate(transport=...)`, which calls it directly instead of
running its own cloud-first chain. Gemma's lifecycle owner is now the Daemon:
`AriaDaemon.startup()` calls `BackendRouter.ensure_local_loaded()` once, and
nothing in this codebase unloads it afterward (architect decision: Gemma
loads at startup and stays resident on a 16GB machine).

**BackendRouter FLAG B — still OPEN**, unchanged by this pass. Health probing
remains optimistic for any transport exposing no `HealthProbe`
(`daemon/backend_router.py::_probe_one` returns `True` for groq/azure by
default). Still deferred to when the real cloud adapters are written.

**FLAG 1 — "light PAD delta on timeout" NOT IMPLEMENTED, by design.** The
Daemon cannot write PAD (invariant + the source-scanning test
`test_daemon_source_never_writes_pad`, which still passes — grep-clean of
`.apply_appraisal_delta(`). The replayed query's own appraisal supplies the
PAD movement when `_expire_proposal` replays it through the full pipeline. If
the architect wants an ADDITIONAL, distinct shift specifically for "he didn't
answer me," the only sanctioned route is a new second-order entry on the
Appraisal Chain (the pattern `submit_aha_insight` and `submit_cognitive_load`
already use) — which would be a THIRD such entry and needs an explicit
decision. Not invented here.

**FLAG 2 — Ambiguous proposal response is UNSPECIFIED.** A response matching
neither the affirmative nor the negative lexicon (`_AFFIRMATIVE` /
`_NEGATIVE` in `daemon/aria_daemon.py`) currently defaults to negative
(`tier_0`) and still replays the pending query, so no user input is lost.
This is an INFERRED default consistent with the locked "auto-answer with the
cheap backend" decision — it is not stated in any source document.
Alternatives the architect may prefer: re-ask once; or abandon the proposal
and treat the utterance as a brand-new turn. Covered by
`test_unrecognized_response_defaults_to_negative_and_still_replays` in
`tests/test_daemon.py`.

**FLAG 3 — SAFETY: proposing delays a possible emergency. RESOLVED: no crisis
pre-check.** This is a personal companion for a single user, not a public
product. The user has confirmed they will not use self-harm language, so
suicide-prevention delay is not a relevant scenario. As defense-in-depth
against false proposals on casual conversation, "medical"/"medically" and
"legal"/"legally" were removed from `TIER_2_KEYWORDS`
(`daemon/backend_router.py`) — too broad for a personal companion, firing on
casual mentions like "my doctor said..." or "my legal paperwork...". The
remaining keywords do not overlap with genuine crisis language (which the
Appraisal Chain's own `_EXISTENTIAL_CUES` / `_PHYSICAL_THREAT_CUES` lexicons
handle, upstream of and independent of BackendRouter's classifier).

### Judgment calls made during Track A (not covered by the task's own text)

- **Naming collision on `self._state`**: the task's literal text names the new
  proposal-state field `self._state`, but `self._state` was ALREADY bound to
  the injected `StateManager` throughout `daemon/aria_daemon.py`
  (`startup()`/`shutdown()`/`_save_state()`). Reusing the name would have
  silently clobbered that reference. Implemented as `self._daemon_state`
  instead; the PUBLIC read-only property is still named `state` (matching the
  task's Part 4h contract), so the observable API is unchanged — only the
  private attribute name differs.
- **`test_clear_override_resets`** in `tests/test_backend_router.py` was not
  in the task's enumerated list of three tests to update (a/b/c), but it also
  asserted `groq` for plain chat text via `select()` and would have failed
  under the new gemma-first fallback order for the same reason test (c) was
  explicitly called out for. Updated for consistency rather than left as an
  unexplained failure.
- **`test_timeout_writes_no_pad_directly`** needed an emotionally-charged
  tier-2 query ("there is an error here and it is terrible" — NEGATIVE
  valence, HIGH relevance), not a neutral one. A purely neutral appraisal
  builds an all-zero `PADDelta` that `AppraisalChain._apply_delta` never
  applies at all, so a neutral phrase would have made the test's "+1"
  assertion pass vacuously (0 == 0) rather than proving the replay's own
  byproduct is the only delta.
