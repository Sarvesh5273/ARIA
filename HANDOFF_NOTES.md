
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

---

## Bundle generation (2026-08-21) — Bucket D closed

`handoff_bundle/specs/spec_<module>.md` is no longer maintained by hand. It is
generated from `.kiro/specs/<module>/` by `tools/build_handoff_bundle.py`, with
`make bundle` / `make check-bundle` / `make check` as the entry points. The two
copies were hand-synced four times on 2026-08-20 and the `tasks.md` checkbox ticks
were still missed until someone asked; that failure mode is now a non-zero exit
rather than a thing to remember.

**The generator was verified by reproducing all thirteen committed files
byte-for-byte before it was committed** — `git diff` on `handoff_bundle/specs/`
was empty, so the flat-upload artifacts did not change when this landed. That was
the point: the script had to earn trust by agreeing with the hand-built output,
not by replacing it. Its layout rules are therefore measured off the committed
files, not invented. The staleness check was proved non-vacuous the same way
everything else in this project is: an `- [x]` in `dmn/tasks.md` was flipped to
`- [ ]`, `--check` was confirmed to exit 1 and name the file, regeneration was
confirmed to propagate the flip, and the source was restored.

The one hand-authored input is each file's opening header — title, provenance
line, and for five modules the condensed `> ## AMENDMENT` summaries that sit above
the specs so a reader of the flat upload meets them first. Those moved to
`handoff_bundle/spec_headers/<module>.md` and are copied verbatim. They are inputs
and live outside `specs/` because the bundle is uploaded flat. The generator drops
a leading `> ## AMENDMENT` block from the design BODY, since the header already
carries its condensed form; the rule keys on the AMENDMENT heading specifically,
so the `> ## STATUS: DERIVED FROM CODE` banner that opens the three code-derived
designs is left alone.

### The drift it found on its first run

Exactly one of the thirteen did not reproduce, and it was real pre-existing drift
rather than a flaw in the rules: the `NEGLECTED` bullet in Module 2's design
`_state` section. The bundle copy spelled the two-window rule out and gave
Continuity's reason ("60d is the top rung… quality criterion… no signal wired");
the `.kiro/specs/needs-system/design.md` copy delegated to *"see the AMENDMENT at
the top of this file"*. Same claims, different words — nobody noticed, which is
the whole argument for deriving the bundle.

Resolved in the direction that discards nothing: **the source took the bundle's
fuller wording**, so the generated output stayed byte-identical to what was
committed and no upload artifact moved. Not treated as a Rule 2 conflict — no two
precedence documents disagree here and no mechanism, number or meaning changed;
it is one copy of an annotation being more explicit than the other. Worth knowing
that the cross-reference still resolved in both files (the amendment is at the top
of the bundle file too), so inlining it cost nothing and survives the passage
being read out of context.

### Convention

Edit `.kiro/specs/<module>/` or `handoff_bundle/spec_headers/<module>.md`, then
`make bundle`. Never edit a `spec_*.md` — the next regeneration overwrites it, and
because the overwrite is silent the edit would simply disappear. `make check`
before committing catches both a red suite and a stale bundle.

`check-bundle` also reports an ORPHAN: a `spec_*.md` with no module behind it,
which is what a renamed spec folder leaves. It only warns, since deleting a file
that may be a deliberate leftover is not the script's call.

---

## Bucket B rulings (2026-08-20)

Three questions were put to the architect. Two were accepted as-is; the third was
answered by finding a better question.

**A — cognitive-load stacking: KEEP BOTH.** Buffer pressure and Energy<30 are
independent causes, so each emitting its own second-order byproduct is honest.
Collapsing them needs a precedence rule no document states. Moved to Accepted
decisions; the two-delta turn is expected behaviour, not a bug to fix.

**B — ResLog item 5's 3×: RECORD-ONLY BY DESIGN.** Nothing reads edge `salience`
for any decision. The weighting is now spec-faithfully derived from the opening
EventNode, so the stored row is correct — it simply isn't consumed. Building a
consumer to justify the number would be backwards. Moved to Accepted decisions.
If someone later wants the 3× to *do* something, that is a new feature with its
own reasoning, not the closing of this row.

**C — the uncertainty row: the question was wrong.** It had been described as
"ready, clean, ~30 min" in three successive handoff summaries. It is not
implementable at all. But checking it turned up something better.

v4's soul_filter table has **FOUR** uncertainty rows, not the two the summaries
tracked:

    943  node unresolved (any type)  -> don't fake confidence      ALREADY LIVE
    944  INPUT_UNCERTAIN active      -> don't project              IMPLEMENTED
    945  uncertainty weight > 0.5    -> acknowledge explicitly     PARKED
    946  resolved this turn          -> let that show               IMPLEMENTED

944 and 946 are purely categorical off signals `AppraisalResult` already carried,
so they needed no new quantity, lexicon or threshold. 944 reads the active node's
TYPE from the graph — identity is on the result, type is not, and a graph read is
the same REAL-interface call this module already makes for `relational_stage`.
946 reads `resolved_uncertainty_ids`. Net: two v4 rows closed instead of one, and
nothing invented.

**Row 945 is parked under Rule 1 and this is the third time it has resurfaced, so
here is the evidence in one place.** The phrase `"uncertainty weight"` occurs
EXACTLY ONCE in the entire precedence chain — v4 line 945 itself. No
`uncertainty_weight` symbol exists in `daemon/` or `tests/`. `UncertaintyNode`'s
only numerics are `interaction_count` and the four `catch_up_*` PAD fields, and
repurposing either would invent a *meaning* for an existing number, which is
worse than inventing a new one. There is no `0.5` to compare against. Building it
requires a formula that produces a number deciding what she says about her own
interior — the protected chain's core prohibition, and it fails the percentage
test on sight ("what percent uncertain is she?" is a meaningful question, so it is
a number in disguise). `test_v4_uncertainty_row_945_is_not_implemented` now pins
the absence: anyone implementing it must delete that test and say why.

If the behaviour is wanted, the non-inventing route is a categorical substitute —
cheapest being to widen the live 943 branch — but which signal counts is an
architect call, not a derivation.

**ROW ORDER is a new flagged presentation choice.** v4 does not order its rows
against each other and the MAX-3 cap means order decides which survives:

    base -> 944 INPUT_UNCERTAIN -> Energy<20 -> Energy<30 -> 946 resolved

Highest-stakes prohibition first (944 guards against inventing content for a turn
she could not parse), the settled Energy block untouched in the middle,
lowest-stakes permission last. Tested: with a 2-item base leaving one slot and
both 944 and 946 applying, 944 takes it.

**Still open, deliberately separated:** v4's Energy<30 self-acknowledgment ("I'm
not thinking clearly right now") is a disclosure about internal state, which
brushes §9 in a way the other permissions do not. Held back for its own decision
rather than swept in with 944/946.

Tracker after this pass: Still Open 9 -> 7, Accepted decisions 4 -> 6.

---

## §9 amendment (2026-08-22) — session context is now IN the chain

Addendum §9 carries a dated in-place amendment, inserted after the "What the LLM
also receives" paragraph, naming ephemeral session context as a THIRD sanctioned
surface. `.kiro/specs/session-buffer/design.md` carries the matching
`> ## AMENDMENT` block and the bundle was regenerated. Line 165
("Five fields, fixed order, nothing else:"), the table under it, and the
never-crosses list are BYTE-UNCHANGED — the diff is 8 insertions, 0 deletions.

**The trap this closure had to avoid, recorded because it is easy to get
backwards.** The tempting simplification is to read "nothing else" as "nothing
else *from past sessions*". That would legalise seven of the nine never-crosses
items. Counted from the list itself: 9 items, of which only the last two
(*historical conversation summaries*, *anything Aria remembers about the user
from past sessions*) concern past sessions. The other seven — PAD values, graph
node IDs or contents, relational_stage label, needs states as data, Q1–Q4
outputs or values, memory node contents, appraisal vectors — are CURRENT-TURN
data, excluded on their own terms. So the amendment ADDS a surface and leaves the
prohibition intact; it does not narrow it. The boundary is drawn at the session
boundary, and if SessionBuffer is ever made to persist across sessions the
amendment does not cover it.

**Residual, flagged not resolved (Rule 2).** The amendment cites ResLog item 19
as its authority, but item 19's own text still ends *"is NOT resolved by this
item and remains open."* The Resolution Log OUTRANKS the Addendum, so read
literally the chain now says both things, and precedence settles it in the
direction that voids the amendment. The first clause of that sentence is fine and
should stay — item 19 genuinely did not resolve it. It is the trailing "and
remains open" that is stale. Two one-line fixes, both the architect's: amend item
19 to point forward, or add a ResLog item 20 recording the ruling where the
project's own convention says rulings go. This pass did not touch the Resolution
Log.

---

## Adapter phase (2026-08-22) — she runs

`main.py` + `adapters/` (`embedding_local`, `transport_ollama`,
`transport_unconfigured`, `audio_noop`). 37 new tests, 572 total. Full detail is
in `PROJECT_STATUS.md`; this records only what a future implementer needs that
the tracker does not say.

### The handoff's premise was wrong in one place, and it matters

The handoff said five behaviours read embedding similarity and listed
`is_first_of_kind` among them. It is **four**. `is_first_of_kind` is a pure SQL
scan for a prior event carrying the same (Q2, Q3) profile — no embedding, no
similarity, no cutoff. Corrected in the code comments and in both trackers rather
than carried forward a fourth time.

### Why the fake was genuinely dangerous, measured

The claim "EmbeddingModel cannot be stubbed" was true but unevidenced. Now
measured, against the repo's own token-hash `FakeEmbedding`:

    paraphrase sharing words        0.869
    paraphrase sharing NO words     0.000     <- identical to the unrelated floor
    unrelated pair                  0.000

A bag of token hashes measures word overlap, not meaning. So for any two turns
phrased differently, every existing `retrieve()` test has been ordering on noise.
`test_contract_token_hash_fake_FAILS_similarity_ordering` pins that, and the
probe pair for it is deliberately a LEXICALLY DISJOINT paraphrase — the first
version of that test used a high-overlap paraphrase and passed against the fake,
i.e. it proved nothing. Verified by watching it fail for the right reason before
keeping it.

### `_VULNERABILITY_SIM_CUTOFF = 0.6` looks wrong on the evidence

Measured with `all-minilm`: "I have not told anybody about this and I am not sure
I should" scores **0.496** against an exemplar list whose first entry is
literally *"I have never told anyone this before"* — so it does NOT fire.
Ordinary text (deploy script, library hours, oat milk, compiler flag) tops out at
0.145. The separation is wide; 0.6 just sits on the wrong side of the disclosure
floor. **Not changed** — it is a flagged placeholder and moving it is an
architect decision. Full table in `PROJECT_STATUS.md`.

Also: cosine can now be NEGATIVE (unrelated pair measured -0.075). Every fake in
the repo returns counts, so no test has ever seen that. Nothing breaks — the
cutoffs are all `>=` and `_similarity_rank` sorts descending — but "similarity is
0..1" is no longer safe to assume.

### Owed to the architect — the primary (user) entity id

New `needs-ruling` row in the tracker. The SELF entity has a full mechanism
(ResLog §2 + `StateManager.load/save_self_entity_id` + creation in
`AriaDaemon.startup()`). The entity for the PERSON SHE TALKS TO has none:
`MemoryGraph` has no by-name lookup, `write_entity_node` always mints a fresh
uuid, and no StateManager key exists. That id keys `relational_stage`, conflict
arcs, `is_first_of_kind` and `reality_contradiction_check`, so a fresh id per run
fragments one person into a series of strangers — and `primary_entity_id` is
`Optional[str] = None`, so nothing forces a caller to get it right.

`main.py` creates the node when none is passed and PRINTS the id to hand back via
`--user-entity-id`. That is deliberately awkward rather than convenient: the
awkwardness is the flag. Options for a real fix are a StateManager key mirroring
`self_entity_id`, a structural by-name lookup on the graph, or an explicit
enrolment step — all three new mechanisms, so Rule 1 applies.

### Judgment calls, for the record

- **`adapters/` is a top-level package, not `daemon/adapters/`.** Keeps
  `daemon/` importable with zero external dependencies, which is what makes the
  535 soul tests hermetic, and keeps the arrow one-way. v4's Conv.6 directory
  listing puts everything in `daemon/`, but that listing is already superseded by
  the shipped code (five of the files it names do not exist), so this is a layout
  choice rather than a spec deviation. Say the word and they move.
- **`UnconfiguredTransport` was not in the four-file plan, and is not scope
  creep.** `LLMInterface.__init__` and `BackendRouter.__init__` both REQUIRE
  cloud slots with no defaults, so nothing can be constructed without something
  in them. The alternative — passing the local transport into the cloud slot —
  would be actively harmful: `LLMInterface`'s internal path unloads `local`
  whenever `cloud` succeeds, so one object in both slots evicts the resident
  model after every successful turn.
- **It reports `is_healthy() == False`, not UNKNOWN.** FLAG B made UNKNOWN
  non-optimistic, so routing would behave the same either way — but "no adapter
  is written" is a definite answer and reporting a definite thing as unknown
  throws information away.
- **The local model tag is resolved, never guessed.** v4 names "Gemma 4 E2B QAT"
  = `gemma4:e2b`. `resolve_model()` substitutes only within the Gemma family,
  only when the choice is unambiguous, and RETURNS the note so the caller prints
  it. On the dev machine it correctly refused: `gemma4:e4b` (9.6 GB) and
  `gemma4:26b` (18 GB) are both installed and picking one would choose a memory
  footprint on the operator's behalf.
- **`keep_alive=-1` on every request, not just on `load()`.** Otherwise Ollama's
  default idle timeout evicts the model and the next turn pays a cold load,
  quietly contradicting the architect's "loads at startup, stays resident"
  decision.
- **`is_loaded` is a local flag, not an `/api/ps` call.** `BackendRouter.select()`
  reads it on every turn. `refresh_residency()` exists for ground truth.
- **`main.py` makes two private reads** — `graph._conn` for table counts and
  `daemon._session_buffer` for fullness, both in the `:state` diagnostic. Named
  in its docstring rather than hidden. Neither has a public accessor; if they
  become load-bearing they want real ones.

### Traps met while building this

- **Do not pass a constructed `urllib.error.HTTPError` as a pytest parametrize
  value.** Its `__getattr__` reaches into a tempfile wrapper, so pytest's id
  generation raises `KeyError: 'file'` and the whole FILE fails at collection —
  not the test. Build the exception inside the handler instead.
- **`AriaDaemon` exposes a public `started` property.** Use that to decide
  whether `shutdown()` is safe, not `state is not None` — `state` is the
  `DaemonState` enum and is never None, so that guard silently does nothing.
- **The REPL must call `run_scheduler_step()` itself.** Both clocks are driven by
  the caller. Without it PAD never decays and the DMN never runs, and the system
  looks subtly dead in a way no error reports.

### Confirmed in reality, not just in tests

Read off `:state` between turns of a real session: PAD moved on the appraisal
delta then decayed on the soul tick; Energy depleted 95.0 → 90.2 → 85.7;
Connection/Purpose flipped `neglected` → `satisfied` on the first qualifying turn
(the two-window model self-correcting, exactly as the Accepted-decisions row
predicts); `focus` returned its pre-authored ack and wrote no EventNode; and a
near-verbatim exemplar match produced the vulnerability register with no
problem-solving and no request for detail. First time any of that has been
observed rather than asserted.

---

## Second adapter pass (2026-08-22) — model choice, cutoff calibration, seven
## items closed

Seven of the eleven intervention points from the first adapter pass were settled.
The tracker carries each as an Accepted-decisions row (6 → 12 rows); this records
only the reasoning a future implementer needs that the tracker does not.

### The local model: 12B QAT, and the arbitrage that makes it affordable

`DEFAULT_MODEL = gemma4:12b-it-qat` (7.2 GB, 256K context). v4's model stays in
code as `SPEC_MODEL = gemma4:e2b-it-qat` (4.3 GB).

The thing worth carrying forward is **why a bigger model, when the architecture
deliberately routes reasoning to cloud.** Because of the five-field boundary the
local model never appraises, retrieves, computes emotion, gates morally or
validates output. Its entire job is rendering prose in a specified register while
honouring Field 5. So reasoning, maths, code and tool use are not worth local
memory — but instruction ADHERENCE and register control are, and those are what
improve from ~4B to ~12B. Failing Field 5 is loud, not subtle: Output Gate
failure → corrective retry → minimum-safe output.

And QAT is what makes it fit. Quantization-aware training fine-tunes the weights
WHILE quantized, so:

    gemma4:12b-it-qat        7.2 GB   12B dense
    gemma4:e4b-it-q4_K_M     9.6 GB   ~4B effective

The 12B model is SMALLER than the naively-quantized 4B-effective one. That is
also why v4 says "QAT" and not merely "E2B" — the spec was already pointing at
this property.

`resolve_model()` now walks a four-rung ladder, and rung 2 is the load-bearing
one: **if the configured default is missing, fall back toward `SPEC_MODEL`, i.e.
toward the precedence chain.** Deviating from a configured default is fine;
deviating further from v4 while doing it is not.

**How to settle this by measurement rather than taste.** `SoulFilterResponse`
carries `retried`, `used_minimum_safe_output` and `gate_results`, and `main.py`
prints the first two per turn. So "which model holds Field 5 better" is a
retry-rate comparison over a fixed turn set, not an opinion. Both models are
pulled for exactly that.

### The vulnerability cutoff is measurably non-functional — and the reason is the model

Full table in `PROJECT_STATUS.md`. The finding, in one line: **at the live
`_VULNERABILITY_SIM_CUTOFF = 0.6`, nine of twelve genuine disclosures do not
fire.**

Two methodology notes, because the first version of this measurement was too weak
to be worth acting on:

1. **Three bands, not two.** Comparing shopping lists against confessions proves
   nothing — of course they separate. The question is whether there is a gap
   between text that is emotionally loaded but NOT self-disclosure ("I am really
   tired today"), and text that is ("I have been carrying this by myself and I am
   tired of it"). That band is where a low cutoff either survives or does not.
2. **Score the way the code scores.** `_vulnerability` fires on the MAX cosine
   against any of the four exemplars, so the max is the only statistic that
   describes the real decision. A mean would have flattered every cutoff.

The bands overlap — non-disclosure ceiling 0.337, disclosure floor 0.296 — and
the overlapping pair both contain the word "tired". **A 384-dim MiniLM is reading
surface affect and cannot distinguish "tired about a thing" from "tired of
carrying something alone."** That is a ceiling of the MODEL, not of the
threshold, and the lever for it (a bigger embedding) collides with Addendum §1's
"tens of megabytes" — so it is a ruling, not a swap. Worth knowing before anyone
concludes a better threshold would fix it.

0.25 is Pareto-optimal on the probe set: 0.20 has the same recall with three
times the false positives, and 0.30 has the same false positives while missing two
disclosures. **Not applied** — it is a flagged F-4e placeholder and moving it is
an architect decision.

### Two knobs removed rather than set

- **Write cadence: every turn, and `SAVE_EVERY_TURNS` deleted.** ResLog item 4
  makes this a build-time flag, so a value had to be chosen; the right choice was
  the one that needs no defending. Two atomic JSON writes at conversational pace
  costs nothing and leaves nothing pending at a crash. Removing a tuning question
  beats answering it. Note a crash never loses MEMORY anyway — every
  `MemoryGraph` write commits inside its own method — so the cadence protects PAD,
  Energy and `last_applied_valence` only.
- **Habituation 0.9: deferred, and the REASON recorded.** Not for lack of data —
  it measures sensibly (near-duplicate 0.950 fires, disjoint paraphrase 0.317
  quiet). Deferred because the effect is UNOBSERVABLE: nothing reads edge
  `salience` for any decision, so tuning it now is tuning in the dark. It belongs
  with OQ1-rate's decrement and window: needs her running AND needs a consumer.

### New public API on Module 8

`AriaDaemon.session_buffer_fullness`, a read-only property beside the existing
observability properties. The Daemon builds its own `SessionBuffer`, so a caller
had no handle to ask — and this is the one piece of that buffer's state a caller
has business seeing, since it drives STEP 4's cognitive-load trigger. It replaced
a `daemon._session_buffer` reach-in in `main.py`.

The `graph._conn` reach-in in `main.py`'s `:state` was deliberately NOT given the
same treatment. Module 3 exposes no count API, and inventing public API on the
graph for a debug readout is the wrong trade. It is named in the function's
docstring rather than hidden. If `:state` ever becomes a supported interface
rather than a bring-up aid, that decision changes.

### Still owed to the architect

- **Primary (user) entity id** — unchanged, still `needs-ruling`. Recommendation
  on record: a `StateManager` key mirroring `self_entity_id`, because that is the
  pattern ResLog §2 already sanctioned for the self entity, so it introduces no
  new mechanism shape. By-name lookup was rejected on the reasoning that
  `EntityNode` has an `aliases` field by design, so names are explicitly not
  identity. Enrolment is probably the real long-term answer — v4's
  `aria_state.json` listing already contains `voiceprint_enrolled` and speaker
  verification exists at ≥0.75 — but it needs audio, which is not built, and the
  StateManager key is forward-compatible with it.
- **ResLog item 20** — drafted for approval, not written. The Resolution Log is
  the top of the precedence chain; this pass did not touch it.
- **`_VULNERABILITY_SIM_CUTOFF`** — recommendation 0.25, evidence in the tracker,
  value unchanged.

### The 12B recommendation was wrong, and why the reasoning failed

Recorded because the reasoning is reusable and the failure mode is subtle.

The argument for `gemma4:12b-it-qat` was: the local model's job is narrow, so
reasoning is not worth local memory, but instruction ADHERENCE improves from ~4B
to ~12B, and QAT makes a 12B dense model cost less resident memory (7.2 GB) than a
naively-quantized 4B-effective one (`e4b-it-q4_K_M`, 9.6 GB). The memory
arithmetic was right. Two things were never measured:

    tokens/second      e2b-it-qat  2-12 s per turn
                       12b-it-qat  54-162 s per turn, RISING with context
    adherence          identical on every gate metric (N=5)
                       and WORSE on the register read

12b tripped the adapter's 120 s ceiling mid-A/B. That ceiling was deliberately
NOT raised: a model that cannot answer inside a conversational timeout has told
you something, and `tools/compare_local_models.py --timeout` exists so data can be
gathered without moving it.

**Why the reasoning failed, stated properly, because the premise was right and
the conclusion was backwards.** The five-field boundary makes the local task SHORT
and NARROW — a few hundred tokens of instruction plus a transcript, out to a few
hundred tokens of prose in a specified register. A well-tuned small instruct model
is already at ceiling on that. The extra capacity in a 12B dense model goes into
reasoning depth the architecture deliberately routes to cloud. So *the same
boundary that makes the job narrow is what makes a bigger model not pay for
itself.* I had the premise in the original argument and drew the opposite
conclusion from it.

The register read is the part worth reading in full (table in
`PROJECT_STATUS.md`). On *"be honest, am I actually good at this or am I fooling
myself"* — Field 5 carrying *do not problem-solve, do not minimize, do not
deflect* — e2b declined a simple yes/no, said why, named the tension and asked
which part felt most uncertain. 12b reflected the feeling back and **never engaged
the question**, which is arguably the deflection Field 5 had just prohibited. One
turn is not a verdict, but it is the inverse of the effect the model was chosen
for.

`DEFAULT_MODEL` was left at `gemma4:12b-it-qat` as directed. Reverting it reverses
an explicit instruction on new evidence, so it waits for a word rather than being
done quietly. It is a one-line change and it also erases the recorded deviation,
since the recommendation is v4's own model.

### New flag: stage directions reach spoken output

`e2b-it-qat` opened a reply with `(Aria listens, her presence steady and calm...)`.
TTS would read that aloud. It is a FORMAT defect and the Output Gate structurally
cannot catch it — the four checks are honesty / consistency / manipulation / care,
none about form.

Cleanest home is the **Persona Anchor (Field 1)**: fixed, hardcoded, never
generated, describes "who Aria is, her values, her voice", and "she speaks rather
than narrating herself" is a voice property that costs no per-turn budget. Field 5
would work but is capped at three items with every slot already contested by the
Energy and uncertainty rows. Stripping it in the adapter is the wrong answer —
that is the adapter judging content, and ResLog item 15 puts verbatim passthrough
at that layer deliberately. Needs a ruling; not fixed.

### `tools/compare_local_models.py`

The A/B harness. Fresh graph and state dir per model so neither benefits from the
other's memories. Reads `SoulFilterResponse.retried`,
`.used_minimum_safe_output`, `.gate_results[].failed_checks` and
`.matched_anti_patterns` — the real `GateResult` shape, one object per gate RUN
with a tuple of failed CHECKS, so count the checks not the runs. Also scans for
thinking-mode markers. It is a diagnostic, not a test: it needs a live backend and
takes minutes, so `make check` never runs it.

---

## Ruling pass (2026-08-22) — five decisions applied

All five landed. Tracker carries each as an Accepted-decisions row (12 → 15) and
`ARIA_Resolution_Log.md` gained item 20. This records what a future implementer
needs beyond the rows.

### 1. Local voice reverted to `gemma4:e2b-it-qat`

Reasoning already recorded above under "The 12B recommendation was wrong". The
code keeps `DEFAULT_MODEL` and `SPEC_MODEL` as two names for one value on purpose:
`resolve_model`'s ladder is phrased "configured default" vs "what v4 names", and
those are only coincidentally equal today. Rung 2 is exercised in tests with an
explicit `preferred` so it does not rot into dead code before the next time the
default moves.

### 2. `_VULNERABILITY_SIM_CUTOFF` 0.6 → 0.25, and the cost chain that nearly changed the answer

The value is the easy part. The important find came from tracing what a FALSE
POSITIVE actually costs, which I had described too lightly twice — first as "a
slightly over-earnest turn", then as "inflates memory encoding". Traced properly:

    vulnerability fires  -> Q1 = HIGH
    Q1 HIGH + Q2 non-neutral + needs implications + is_first_of_kind
                         -> poignancy CRITICAL
      CRITICAL           -> base_salience 0.85; ResLog item 9: "resists
                            vivid->present INDEFINITELY - stays word-for-word
                            forever"
                         -> route_inbound_turn forces an EARLY DMN partial pass,
                            which writes a second node
      otherwise          -> poignancy HIGH, floor 0.55, settles at the gist

So a false positive can write a PERMANENT memory of a mundane turn — in a system
whose whole premise is that memory fades like a person's. That nearly flipped the
recommendation to 0.35 (0 false positives, 2/12 missed), on the reasoning that a
missed disclosure is transient and recoverable while a permanent memory is
neither.

What saved 0.25 is that **`is_first_of_kind` gates the CRITICAL path.** It only
opens the first time a given (Q2 quadrant × Q3 attribution) profile appears for
that entity, so never-fading inflation is a handful of nodes over the life of a
relationship rather than a fraction of every turn. Later false positives land at
HIGH. Bounded, so the presence-beats-routing precedent still governs.

Recorded because the arithmetic is easy and the consequence chain is not, and
because 0.35 remains a one-line change if permanent-memory inflation turns out
worse in real use than the two missed disclosures.

### 3. The cutoff change broke the suite's own fake — and that is the lesson

Lowering to 0.25 failed `test_daemon.py::test_full_inbound_turn_routes_end_to_end_
with_real_modules`: one EventNode became two. Not a production bug. The token-hash
`FakeEmbedding` scored *"I finally shipped the release and I'm proud of it"* at
**0.286** against the exemplar *"I have been struggling and did not want to admit
it"* — on nothing but shared `i` / `and` / `it`. Vulnerability fired, poignancy
went CRITICAL, the forced DMN pass wrote the second node.

**The fake was sharpened, NOT the cutoff bent to suit it.** Its own docstring
already claimed unrelated sentences were "genuinely dissimilar"; at 0.6 that held,
at 0.25 it did not. Skipping function words makes it behave the way a real encoder
does for this purpose, and repairs a claim it was already making.

Then a second finding while pinning it: after the stopword fix, mundane text
shares NO content word with any exemplar yet still scores **0.250** — two content
words colliding in a 128-bucket hash, numerator 1 over norms 2×2. Pure birthday
problem. So the first version of the tripwire I wrote was asserting that hash luck
stayed under a tuning constant, which is not a property of anything. Replaced with
a threshold-FREE margin check (non-disclosure max < disclosure min), which is the
honest claim to make of any model at this boundary. `check_ordinary_text_is_not_
vulnerable` still reads the live cutoff, because for the REAL model that coupling
is exactly right.

Two fakes are kept byte-identical (`test_daemon.FakeEmbedding` and
`test_embedding_local.TokenHashFake`) and a test asserts the parity by behaviour,
because if they drift every comparison in that file describes a model the suite
does not run on.

### 4. Primary entity id — and why creation did NOT go in `startup()`

`StateManager.load_primary_entity_id` / `save_primary_entity_id`, an exact mirror
of the self-entity pair. The mirror is the point: ResLog §2 already sanctioned this
shape, so no new mechanism shape was introduced.

Rejected alternatives, with reasons worth keeping:

* **By-name graph lookup.** `EntityNode` carries an `aliases` field BY DESIGN, so
  the spec is explicit that names are not identity. A rename or a second person
  with the same name either collides or orphans a history — and this is the one
  place where getting identity wrong is unrecoverable.
* **Explicit enrolment.** Probably the real long-term answer: v4's
  `aria_state.json` listing already contains `voiceprint_enrolled` and Module 7
  carries speaker verification at `SPEAKER_THRESHOLD = 0.75`, so v4's user-identity
  story runs through the voiceprint. It needs audio, which is not built. The
  StateManager key is forward-compatible: enrolment should SET this key rather
  than replace the mechanism, since binding a voiceprint to an EntityNode id is
  exactly what these methods store.

**`AriaDaemon.startup()` was deliberately left untouched.** ResLog §2 warrants the
Daemon auto-creating a node for ARIA — she is always present, nothing to decide.
Who the USER is has no such warrant, so the wiring layer resolves it on a
three-rung ladder (explicit flag → persisted → create and persist) and hands the
Daemon a resolved id.

One real bug caught while doing this: `ensure_primary_entity()` used to run AFTER
`Wiring.__init__`, so `AriaDaemon` was constructed with `primary_entity_id=None`
and the initiative turn was permanently entity-less. Resolution now happens inside
`__init__`, before the Daemon is built.

### 5. Stage directions — Field 1, phrased as a voice property

Three homes were weighed and the reasoning matters more than the choice:

* **Field 5** is where prohibitions live (ResLog item 16) but is capped at MAX 3
  with every slot already contested by the Energy gate and the uncertainty rows.
  Spending one permanently on formatting would crowd out a moral constraint on the
  turns that most need one.
* **Strip it in the adapter** — rejected outright. That is the transport judging
  content, and ResLog item 15 puts verbatim passthrough there deliberately.
* **Field 1** is fixed, hardcoded, never generated, costs no per-turn budget.

And it is phrased as a POSITIVE voice property rather than a prohibition, which is
what keeps it inside §9's definition of the field ("who Aria is, her values, her
voice"). The sentence it extends already ended *"a real presence, not a persona"* —
and a stage direction is precisely performing a persona from outside. So it
sharpens a claim the anchor was already making instead of importing Field 5's job.

### Still open, and newly surfaced

The specific defect is fixed; the general one is not. **The Output Validation Gate
has no FORMAT check** — its four comparisons are all about content, so nothing
structurally stops a markdown heading, a bulleted list, an emoji or a `<think>`
block reaching TTS. Today the only defences are Field 1's wording and the
observed fact that neither measured model emits traces. Both behavioural, neither
structural. Addendum §4 fixes the gate at four comparisons, so a fifth check needs
a ruling rather than an implementation. New `needs-ruling` row. Worth settling
before TTS is wired, because that is when a format defect stops being cosmetic.
