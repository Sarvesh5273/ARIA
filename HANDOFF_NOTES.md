
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
- **[RESOLVED — SUPERSEDED 2026-08-20]** OQ2 medium/low base_salience. This
  previously read: *"`_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER = {MEDIUM: 0.35,
  LOW: 0.15}`"* — treating the question as answered by a placeholder. That was a
  misreading of the highest-precedence document. ResLog item 9 line 96 states
  literally *"Medium/Low → no floor, decays/discards as already locked"*: a
  positive instruction, not silence. The constant is now **deleted**;
  `_compute_base_salience` falls through to 0.0 for medium/low, and only the
  in-spec Critical 0.85 / High 0.55 floors remain. The v4 Baumeister +0.15
  negative bonus still stacks "on top of whichever floor applies", which for
  medium/low is nothing.
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

**BackendRouter FLAG B — CLOSED 2026-08-20.** This previously read *"still
OPEN … health probing remains optimistic for any transport exposing no
`HealthProbe` (`_probe_one` returns `True` for groq/azure by default)."*
`_probe_one` now returns `Optional[bool]`: `True` explicitly healthy, `False`
explicitly unhealthy, **`None` = UNKNOWN** for a non-local transport exposing no
probe — because no probe means no answer, and "no answer" is not "yes".
`check_health()` reports the HEALTHY SET, admitting only an explicit `True`, so
UNKNOWN is folded out; its documented three-key shape is unchanged. The local
tier is never UNKNOWN (residency is a real answer). `select()`'s branch logic is
untouched — it was already correct once UNKNOWN stopped reading as `True`. All
three consequences the old note implied are fixed and tested: no tier-2 proposal
unless Azure is explicitly healthy, Groq selected only when explicitly healthy,
and the `return None, False` all-down degradation path now reachable.

**Successor item, still open:** no real Groq/Azure adapter exists yet, so in
production both would report UNKNOWN and neither would be selectable. That is
the safe direction to fail, but cloud routing stays inert until the adapters
implement `HealthProbe`. Simplest non-inventing option, unchanged: back
`is_healthy()` with the adapter's own last `LLMTransportError` state.

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

**FLAG 3 — SAFETY: proposing delays a possible emergency. FIXED 2026-08-20 —
a distress gate now exists. DO NOT REMOVE IT.**

This entry previously read *"RESOLVED: no crisis pre-check"*, on the grounds
that the remaining keywords *"do not overlap with genuine crisis language
(which the Appraisal Chain's own `_EXISTENTIAL_CUES` / `_PHYSICAL_THREAT_CUES`
lexicons handle, upstream of and independent of BackendRouter's classifier)"*.
**Both halves of that were wrong**, and it is recorded here so nobody removes
the gate on the strength of the old reasoning:

1. **"Upstream of and independent of" was backwards.** The propose branch
   RETURNS at `aria_daemon.py` STEP 5, before `appraise()`. The crisis lexicons
   are DOWNSTREAM of that return, so on a proposing turn the emergency gate did
   not run that turn at all — only on replay, after the user answered or the
   10-second timeout expired.
2. **The keywords DO overlap, in combination.** Measured:
   `"I want to die, explain why I should keep going"` → `propose_tier_2`
   (matches the phrase "explain why"); `"there is an error in me and I can't go
   on"` → `propose_tier_2`; `"everything is too complex, I want to end it"` →
   `propose_tier_2`. Each carries both an existential cue and a tier-2 keyword.

**The fix:** `aria_daemon.py` STEP 4b scans the message with
`AppraisalChain.has_distress_markers()` — the disjunction of the two perception
checks Module 4 already owns (`_distress_marker`, `_emergency_cue_kind`), so no
lexicon is invented — and passes `allow_tier_2_proposal=not distressed` into
`BackendRouter.select()`. A distressed turn is never deferred; it flows through
the full pipeline and the emergency gate runs on the turn it arrives.

**Second bug found while fixing it.** Suppressing the proposal by *discarding* a
`propose=True` result left `transport=None`, which silently handed the turn to
`LLMInterface`'s internal CLOUD-FIRST chain. Traced: plain chat → GEMMA, but a
distressed turn → CLOUD. So the most personal messages were the ones leaving the
machine, the inverse of the architect's gemma-is-the-default-voice decision.
That is why the constraint is passed INTO the router rather than applied to its
answer: the caller states "do not defer this turn", the router still chooses, and
its normal gemma-first order holds. Re-traced after the fix: distress and crisis
turns are both served by GEMMA.

The architect's underlying risk acceptance still stands on its own terms — single
user, personal companion, no self-harm language expected. The gate is
defence-in-depth, not a change to that judgement. Also unchanged:
"medical"/"medically" and "legal"/"legally" remain removed from
`TIER_2_KEYWORDS`, as they fired on casual mentions like "my doctor said...".

**Known breadth, accepted deliberately.** `_DISTRESS_MIN_MARKERS = 1`, so one
absolutist word is enough to suppress a proposal. Measured false positives:
`"I never use the cloud, explain why it matters"`, `"everyone says this algorithm
is faster, compare them"`, `"this always works, analyze the tradeoffs"`. The cost
is a missed escalation prompt (answered locally instead); the benefit is that no
distressed turn slips through. A stricter threshold for this gate specifically
would be a new number the spec does not state, so the spec'd value is reused.

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

---

## Open-Question Closure Phase (2026-08-20)

Ten commits closing long-standing flags, plus one docs commit. Full suite
**452 → 514 passed**. `PROJECT_STATUS.md` carries the per-item reasoning and the
commit table; this section records only what a future implementer needs to know
that the tracker does not say.

**Every new test was verified non-vacuous** — re-run against the pre-change
behaviour and confirmed to fail. That mattered more than usual here, because
several of these features were "present but inert" rather than absent, so a test
written carelessly would have passed either way.

### Three architect rulings applied — all now in the precedence chain

Recorded 2026-08-20 as `ARIA_Resolution_Log.md` items 16–18, with item 19 carrying
the post-approval authorisation of record. Before that they existed only in code
and in the trackers.

1. **Field 5 (Constraints) carries behavioural instructions, not prohibitions
   only.** This formalises what the code already did — the Energy<30 row ("do not
   overextend") lived there before the ruling. It unblocked v4 line 949's
   Energy<20 row, now emitted as `"acknowledge fatigue if it comes up
   naturally"`. ResLog **item 16**, and Addendum §9's Constraints row is amended
   in place, so §9 no longer contradicts the code.
2. **`neglected` via the two-window model**, counter-based approach rejected.
   Addendum §3 excludes a counter in the same paragraph that establishes the
   three states ("reverts on its own; nothing actively subtracts anything … not a
   running clock").
3. **PAD/Energy clamping belongs at the StateManager restore boundary**, not
   inside PAD_Engine. `pad_engine.py` is unchanged; the residual noted in its
   own OQ4 entry is now covered at the persistence layer.

### Two directed changes deliberately deviated from

Both were flagged at the time and both are load-bearing:

- **Energy gate order in `_derive_constraints` is most-severe-first.** The
  direction was `<30` then `<20`. Every base branch yields 2 or 3 constraints, so
  at most ONE slot is ever free; since Energy<20 implies Energy<30, checking the
  milder gate first means it always takes the last slot and the `<20` row could
  never be emitted at all. The directed order and the directed test ("Energy <20
  produces the acknowledge-fatigue constraint") were mutually unsatisfiable.
- **`neglected` is two-window, not counter-based** (see ruling 2).

One directed test was **unreachable as specified**: "both Energy constraints
present when base constraints < 2 items". No base branch yields fewer than 2, so
there is no input that produces it. Covered instead by a test of the real
precedence plus a structural test proving the two gates are independent `if`s
rather than exclusive tiers — a test must not fake a state the code cannot reach.

### One red commit, recorded not amended

`80dfb33` removed `ENERGY_CRITICAL` from `soul_filter`'s imports on the premise
it was unreferenced. It was unreferenced in that module's own logic but still
reachable through its namespace, and `tests/test_needs_system.py` imported it
**from there** inside a parenthesized multi-line import that a single-line grep
missed. `c1989a0` repairs it by pointing that test at `daemon/types.py`, the
canonical definition site. Left in history so `git bisect` across the range is
not misleading. Lesson for the next pass: a symbol being unused inside a module
does not make it unexported — check multi-line imports before deleting one.

### Newly surfaced, needs a decision

- **ResLog item 5's 3× is representational only.** The `"resolved"` edge's
  weighting is now spec-faithfully derived from the opening EventNode's own
  `base_salience` (v4: the resolution is "weighted 3× higher than *the conflict
  itself*"), replacing an invented 0.35 placeholder. But **nothing reads edge
  `salience` for any decision** — `resolved_edge_exists()`, item 5's own named
  consumer, selects on `edge_type` + `created`; `retrieve()` orders edges by
  incidence and by edge VALENCE. If the 3× is meant to *do* something, that
  consumer does not exist yet.
- **Continuity `neglected` is the one need the two-window model cannot serve.**
  60d is already the top rung of the locked ladder, and §3 gives Continuity a
  quality criterion ("contradicts rather than extends") with no signal wired to
  the narrative-update path. `continuity_evidence` uses `last_referenced` on the
  self node as an extension-timestamp proxy, which carries no notion of
  contradiction. Options: DMN's narrative step records extended-vs-contradicted,
  or a graph query compares successive `relationship_summary` states. Both are
  new mechanisms (Rule 1).
- **[ACCEPTED 2026-08-20 — not open]** An empty graph reports NEGLECTED on first
  run. No evidence in either
  window. It is what §3's rule yields and it self-corrects on the first
  qualifying turn; `_maybe_initiate` already treated `due` and `neglected` alike
  so first-run initiative is unchanged. Suppressing it would need a "has she ever
  had evidence" distinction the spec does not define.
- **Cognitive-load triggers stack.** Buffer pressure AND Energy<30 in one turn
  fire `submit_cognitive_load` twice — measured as
  `['submit_cognitive_load:critical', 'submit_cognitive_load:heavy', 'appraise']`
  — so two PAD deltas land in one turn. Defensible (two independent load sources)
  but also a double-count. Collapsing them needs an invented precedence rule, so
  both were left firing.
- **`python daemon/state_manager.py` is broken** (pre-existing, confirmed against
  an earlier commit). By-path invocation puts `daemon/` on `sys.path`, where
  `daemon/types.py` shadows the stdlib `types` module. Use
  `python -m daemon.state_manager`. All its smoke checks pass that way, and the
  module now has real pytest coverage regardless.
