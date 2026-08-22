# ARIA — CODE STATE: architecture reference (verified 2026-08-20)

**What this file is:** a structural description of the code as it exists —
the PAD write paths, the two distinct structural guarantees, the internal
dependency graph, the implemented turn flow, and where each open item lives in
the source. These are things `PROJECT_STATUS.md` does not record.

**What this file is NOT:** a source of scope, a spec, or a precedence document.
It resolves nothing and decides nothing. Precedence is unchanged:
`ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Rule 1 (do not invent) and Rule 2 (do not resolve
conflicts silently) apply exactly as before.

**Relationship to `PROJECT_STATUS.md`:** none of the tracker's counts,
line numbers, or open/closed states are duplicated here. `PROJECT_STATUS.md` was
audited claim-by-claim against the code on 2026-08-19 and re-measured on
2026-08-20 after the open-question closure phase; it is the authority on module
status, test counts, and which open questions are open. If this file and the
tracker ever appear to disagree, that is a defect in this file — report it, do
not reconcile it.

One caution on its line-number claims: `apply_appraisal_delta`'s three call sites
moved twice on 2026-08-20. Match the call pattern
`\.apply_appraisal_delta\s*\(`, not a recorded line number.

---

## 1. PAD has TWO write paths, not one

This is the most commonly mis-stated constraint in the project, so it is first.

```
1. Appraisal delta   PADEngine.apply_appraisal_delta(delta)
                     called ONLY from appraisal_chain.py, 3 call sites
                     (lines shift often — match `\.apply_appraisal_delta\s*\(`):
                       appraise()               -> the Stage-4 turn delta
                       submit_aha_insight()     -> DMN's aha, routed as an EVENT
                       submit_cognitive_load()  -> TWO triggers as of 2026-08-20:
                                                   SessionBuffer fullness, and
                                                   Energy < 30 (Addendum §3's
                                                   operational threshold gate).
                                                   Both are categorical load
                                                   states handed in by the
                                                   Daemon; Energy itself never
                                                   crosses into this module.

2. EMA decay         PADEngine.on_soul_tick()
                     called from aria_daemon.py's soul_tick(), on its own clock.
                     The Daemon TRIGGERS decay; PAD_Engine owns the math. This
                     is not the Daemon writing PAD.
```

"Appraisal Chain is the sole PAD writer" is **wrong** — it is the sole source of
PAD *deltas*. Decay is the second path and it is driven by the soul tick.
Both live inside `PADEngine`; nothing outside it assigns to P, A, or D.

Nothing else writes PAD, ever: not needs pressure, not F4 or barge-in, not the
graph, not the State Manager, not the Daemon directly.

---

## 2. Two DIFFERENT structural guarantees — do not conflate them

These are separate constraints with separate evidence. Confusing them is easy
because both are enforced by absent imports.

**(a) The protected chain** — numbers never compute feeling. Evidence:

- `needs_system.py` imports `graph_manager` and `types`, and **no PADEngine**.
  Needs pressure therefore *cannot* reach PAD; there is no handle to reach it
  with. Energy is a float that no feeling reads.
- `graph_manager.py` imports **nothing internal at all**. Salience,
  habituation, and precision decay are numeric substrate with no path to PAD
  or appraisal.
- `graph_manager.retrieve()` returns an ordered list, not scored items. Mood
  congruence is the primary sort key and need-preference the secondary; the
  ordering carries no number a caller could multiply by.
- `dmn.py` never writes PAD. Its aha insight leaves as an *event* via
  `AppraisalPort.submit_aha_insight`, so meaning is assigned by the Appraisal
  Chain rather than computed by the DMN.

**(b) The five-field LLM boundary** — no internal state reaches the model.
Evidence:

- `LLMInterface.__init__(*, cloud_transport, local_transport)` takes only
  transports. No graph, PAD, needs, or appraisal parameter exists to pass.
- `llm_interface.py` imports the instruction dataclasses **from**
  `soul_filter.py`; `soul_filter.py` does not import back. It depends on the
  `LLMClient` Protocol it declares itself.
- Per the current `project-rules.md`, three surfaces cross: the five-field
  self-description, the ephemeral session transcript (explicitly NOT internal
  state), and the user's message. Emergency mode replaces the five fields and
  session context is still appended.

An example of (b) does not demonstrate (a). The protected chain is about
numbers and feeling; the boundary is about what the model sees.

---

## 3. Internal dependency graph (`from daemon.…` imports)

Leaves — import nothing internal:

```
types.py   pad_engine.py   state_manager.py   graph_manager.py
moral_schema.py   session_buffer.py
```

Everything else:

```
needs_system.py    <- graph_manager, types
appraisal_chain.py <- graph_manager, pad_engine
soul_filter.py     <- appraisal_chain, graph_manager, moral_schema, pad_engine, types
llm_interface.py   <- soul_filter
backend_router.py  <- llm_interface
dmn.py             <- graph_manager, moral_schema, needs_system, state_manager
audio_pipeline.py  <- pad_engine
visual_layer.py    <- pad_engine
aria_daemon.py     <- appraisal_chain, backend_router, dmn, graph_manager,
                      needs_system, pad_engine, session_buffer, soul_filter,
                      state_manager
```

Outside the package, above everything (2026-08-22) — see §5:

```
adapters/*         -> daemon (Protocols only)
main.py            -> daemon + adapters
```

No `daemon` module imports either. That one-way arrow is what keeps the soul
layer dependency-free.

`aria_daemon.py` does not import `audio_pipeline.py` or `visual_layer.py`. It
declares its own `AudioPipelinePort`; Module 10 exposes its own
`VisualLayerPort` and is wired above the Daemon.

---

## 4. Turn flow as implemented

`AriaDaemon.route_inbound_turn()`, six steps (4 splits into 4 and 4b):

1. Proposal-response interception — if the previous turn asked whether to
   escalate to the reasoning tier, this turn IS the answer; nothing below runs.
2. SessionBuffer meta-command check (`rest` / `focus` / `unfocus`) — bypasses
   appraisal and the gate entirely.
3. Backend meta-command check (`use cloud` / `stay local` / …) — sets or clears
   the router override, returns a pre-authored acknowledgement. No EventNode.
4. Cognitive-load checks — TWO triggers: buffer fullness `heavy`/`critical`,
   and Energy below the in-spec 30 gate. Both call
   `appraisal.submit_cognitive_load()`, so both can fire in one turn.
4b. Distress gate — `appraisal.has_distress_markers(user_text)`, one local
   lexical scan over Module 4's own lexicons. Feeds step 5; see §6.
5. Routing decision — `BackendRouter.select(user_text,
   allow_tier_2_proposal=not distressed)`. A `propose=True` result defers the
   turn into `PROPOSING_CLOUD` instead of answering. When the distress gate
   fires the tier-2 branch is skipped, so a distressed turn is never deferred
   and the router's normal gemma-first order serves it. The constraint is passed
   IN rather than applied to the result: discarding a `propose=True` would leave
   `transport=None`, which hands the turn to `LLMInterface`'s CLOUD-FIRST
   internal chain — measured as plain chat → GEMMA but distressed → CLOUD before
   the fix.
6. The pipeline proper: note voice input → thinking sound (reads PAD, plays a
   pre-cached clip) → `NeedsSystem.get_need_states()` →
   `AppraisalChain.appraise()` → track turn →
   `SoulFilter.respond(transport=…)` → `audio.speak()` → append to session
   buffer → if poignancy is CRITICAL, forced early DMN partial pass.

Within a turn, the appraisal delta at step 6 is the only PAD movement. EMA
decay is the other write path and runs on the soul-tick clock, not here
(see §1).

Steps 3 and 5 are no-ops when no `BackendRouter` is injected, so the
pre-Track-A behaviour is preserved exactly.

Two clocks, never merged: `soul_tick()` (PAD decay → Energy load-or-recover →
attentional policy → initiative) and `dmn_tick()` (idle-gated consolidation
pass). `run_scheduler_step()` advances both on independent intervals. A soul
tick never runs a DMN pass; a DMN pass never decays PAD.

`aria_daemon.py` contains **no `apply_appraisal_delta` call site**. The string
does occur twice in its module docstring — in the sentences describing this very
constraint — so a raw grep returns 2. Match on `\.apply_appraisal_delta\s*\(`
to check for real calls; that returns nothing.

---

## 5. It runs, text-first (2026-08-22)

This section read "Nothing runs yet" until 2026-08-22. `main.py` exists, wires
the soul layer to real adapters, and drives turns from a text prompt. Verified
end-to-end, with the per-turn evidence in `PROJECT_STATUS.md`'s "Current
runnable state" table — that file is the authority on what was confirmed.

```
.venv/bin/python main.py --local-model <gemma tag>
```

**`requirements.txt` is still pytest only, and that is now a property rather
than a gap.** Both real adapters speak to the local Ollama HTTP API through
stdlib `urllib`, so the system runs on zero runtime dependencies. No torch, no
provider SDK, no `requests`.

### The adapter layer, and why it is not in `daemon/`

```
adapters  ->  daemon         adapters import Protocols from daemon
daemon    -/->  adapters     nothing in daemon imports adapters
```

That direction is the point: it keeps `daemon/` importable with zero external
dependencies, which is what makes the 535 soul tests hermetic. v4's Conv.6
directory listing puts everything under `daemon/`, but that listing is already
superseded by the shipped code (`llm_manager.py`, `stt_engine.py`,
`tts_manager.py`, `interrupt_handler.py`, `tcp_server.py` do not exist), so this
is a layout choice, flagged in `PROJECT_STATUS.md`, not a spec deviation.

The Protocol to-do list, with what is now filled:

```
graph_manager.py    EmbeddingModel        DONE  adapters/embedding_local.py
                                                OllamaEmbeddingModel, all-minilm,
                                                384-dim, 45 MB measured
llm_interface.py    LocalModelTransport   DONE  adapters/transport_ollama.py
                                                + HealthProbe, keep_alive residency.
                                                DEFAULT_MODEL == SPEC_MODEL ==
                                                gemma4:e2b-it-qat, v4's own
                                                "Gemma 4 E2B QAT". A 12B build was
                                                tried and reverted the same day on
                                                measurement (10-13x slower, equal
                                                gate metrics, worse register).
                                                Two names for one value on purpose:
                                                resolve_model's ladder is written
                                                in terms of "configured default"
                                                vs "what v4 names".
llm_interface.py    ModelTransport        OPEN  adapters/transport_unconfigured.py
                    (cloud x2)                  holds the slot and answers an
                                                explicit False. Real Groq/Azure
                                                adapters are purely additive
aria_daemon.py      AudioPipelinePort     STUB  adapters/audio_noop.py — a LEAF,
                                                nothing downstream reads it
audio_pipeline.py   CaptureBackend, WakeWordBackend, SpeakerVerification,
                    VADBackend, STTBackend, TTSBackend (primary + fallback),
                    PlaybackBackend       OPEN  all leaves; text-first skips them.
                                                Inbound STT was never a port —
                                                route_inbound_turn takes text
visual_layer.py     VideoWindow           OPEN  leaf; the Daemon takes no visual
                                                parameter at all
```

### The one adapter that could not be stubbed, and the measured reason

`EmbeddingModel` is read by FOUR behaviours — `retrieve()` (as the base
ORDER, no cutoff), `reality_contradiction_check` (0.6), `_vulnerability`
(0.6), and habituation inside `register_edge_firing` (0.9). Not five: the
handoff listed `is_first_of_kind`, which is a pure SQL check on the (Q2, Q3)
profile and reads no embedding.

`tests/test_embedding_local.py` measures the fake against the real thing rather
than asserting the difference. Against the repo's own token-hash
`FakeEmbedding`: a paraphrase sharing words scores 0.869, a paraphrase sharing
NO words scores 0.000 — identical to the unrelated floor. The fake measures word
overlap, not meaning, so every existing `retrieve()` test has been ordering on
noise for any two turns phrased differently. That is the substantive reason the
embedding cannot be faked, and it is now pinned by
`test_contract_token_hash_fake_FAILS_similarity_ordering`.

Cutoff calibration numbers live in `PROJECT_STATUS.md`, measured over a
37-sentence three-band probe set. The headline: at the old
`_VULNERABILITY_SIM_CUTOFF = 0.6`, nine of twelve genuine disclosures did not
fire — a 75% miss rate on the signal that part of the architecture exists to
detect. **Set to 0.25 on 2026-08-22** (architect ruling), which is Pareto-optimal
on that probe set: 2/25 false positives, 0/12 missed.

Two consequences worth knowing before touching it again:

* **A false positive is expensive, and the chain is not obvious.** Firing raises
  Q1 to HIGH; with a non-neutral Q2, needs implications and `is_first_of_kind`
  that reaches poignancy CRITICAL, which means `base_salience` 0.85 — per ResLog
  item 9 it "resists vivid→present indefinitely" — plus a forced early DMN
  partial pass writing a second node. So a mundane turn can become a permanent
  memory. `is_first_of_kind` bounds it: the CRITICAL path only opens once per
  (Q2 × Q3) profile per entity.
* **The bands OVERLAP** (non-disclosure ceiling 0.337, disclosure floor 0.296), so
  no threshold separates them cleanly. The colliding pair both contain "tired": a
  384-dim MiniLM reads surface affect and cannot tell *tired about a thing* from
  *tired of carrying something alone*. That is a model ceiling, and the lever for
  it collides with Addendum §1's "tens of megabytes".

Lowering the cutoff also broke the repo's own test fake — see `tests/
test_embedding_local.py`. Function-word overlap alone put ordinary text at 0.286
against an exemplar, which flipped an end-to-end daemon test from one EventNode to
two. The fake was sharpened (stopwords skipped) rather than the cutoff bent to
suit it, and two tests now pin that relationship.

---

## 6. Where the open items live in code

`PROJECT_STATUS.md` is the authority on *what* is open, and since 2026-08-20 it
tags every open row with a BLOCKER TYPE — `needs-ruling` / `needs-runtime` /
`needs-adapter` — and keeps decisions-already-made in a separate "Accepted
decisions" section rather than in "Still Open". This section is only *where* each
thing lives in the source.

FOUR of the entries below are ACCEPTED decisions in the tracker, not open work,
and are listed here purely so a reader who finds the behaviour can locate it:
`first-run NEGLECTED`, `distress gate is broad`, `item 5's 3x is inert` and
`load triggers stack`. Do not "fix" any of them — the reasoning is in the
tracker's "Accepted decisions" section. In particular: do not collapse the two
cognitive-load deltas, and do not invent a consumer for edge salience.

```
OQ6 Purpose evidence        graph_manager.py purpose_evidence + max-5 cap raise
Continuity `neglected`      needs_system.py evaluate_continuity stays 2-valued;
                            60d is the TOP rung of the locked ladder so there is
                            no wider window, and Addendum §3 gives Continuity a
                            QUALITY criterion ("contradicts rather than extends")
                            that has no signal wired to the narrative path
first-run NEGLECTED         ACCEPTED (self-corrects on first qualifying turn).
                            needs_system.py; empty graph has no evidence in
                            either window -> neglected, not due. Self-corrects on
                            the first qualifying turn
item 5's 3x is inert        ACCEPTED (record-only by design).
                            graph_manager.py; nothing READS edge salience for any
                            decision. resolved_edge_exists() selects on
                            edge_type+created; retrieve() orders edges by
                            incidence and VALENCE. The weighting is recorded and
                            acts on nothing
load triggers stack         ACCEPTED (keep both — independent causes).
                            aria_daemon.py; buffer pressure AND Energy<30 in one
                            turn fire submit_cognitive_load twice -> two PAD
                            deltas. Measured, not collapsed (collapsing needs an
                            invented precedence rule)
cloud adapters unprobed     backend_router.py; FLAG B is closed (UNKNOWN is no
                            longer optimistic), but no real Groq/Azure adapter
                            implements HealthProbe, so both report UNKNOWN and
                            neither is selectable. Safe direction; still inert
Daemon FLAG 2               ambiguous proposal response defaults to negative —
                            an inferred default, in no source document
distress gate is broad      ACCEPTED (presence beats routing).
                            aria_daemon.py STEP 4b; _DISTRESS_MIN_MARKERS = 1, so
                            ONE absolutist word suppresses a cloud proposal.
                            Measured false positives ("I never use the cloud,
                            explain why it matters"). ACCEPTED: presence beats
                            routing, and a stricter threshold would be a new
                            number the spec does not state
```

CLOSED 2026-08-20, listed so a reader of an older copy of this file knows where
the claim went (`PROJECT_STATUS.md` carries the full reasoning):

```
v4 uncertainty rows        3 of 4 NOW LIVE in soul_filter._derive_constraints:
                            943 "don't fake confidence" (base branch), 944
                            INPUT_UNCERTAIN -> "do not project onto what you do
                            not know yet", 946 resolved-this-turn -> "let it show
                            that something became clearer". 944 reads the node's
                            TYPE from the graph (identity is on AppraisalResult,
                            type is not). Row 945 "uncertainty weight above 0.5"
                            is PARKED and NOT implementable: the phrase occurs
                            once in the whole precedence chain, no such quantity
                            exists, and manufacturing one would be a number
                            deciding what she says about her own interior.
                            test_v4_uncertainty_row_945_is_not_implemented pins
                            the absence -- delete it and say why, or leave it
ENERGY_CRITICAL unused      NOW EMITTED. soul_filter._derive_constraints appends
                            "acknowledge fatigue if it comes up naturally"
                            (v4 line 949) below ENERGY_CRITICAL; architect ruling
                            that Field 5 carries behavioural instructions
Energy<30 -> Stage 2        WIRED. aria_daemon.route_inbound_turn STEP 4 calls
                            submit_cognitive_load("heavy") below ENERGY_LOW
`neglected` never emitted   NOW EMITTED for Connection/Growth/Purpose, via the
                            two-window model in NeedsEvaluator._state
conflict-arc 2nd close      IMPLEMENTED. appraisal_chain
                            ._conflict_arc_absence_close() reads the counter and
                            closes the arc; absence closures write the same one
                            "resolved" edge as a Q2 flip
FLAG B optimistic health    FIXED. _probe_one returns Optional[bool] with
                            None = UNKNOWN; check_health() admits only explicit
                            True to the healthy set
PAD restore not clamped     CLAMPED at the persistence boundary instead:
                            state_manager.load_pad/load_energy bound to [0,1] and
                            [0,100]; non-finite treated as corrupt. pad_engine.py
                            itself is unchanged
state_manager no tests      tests/test_state_manager.py now exists (31 tests)
VALENCE_UNCERTAIN closed    FIXED. appraisal_chain._conflict_arc_update closes on
  conflict arcs             POSITIVE/NEUTRAL only, per Addendum §1. Ambiguity is
                            not repair, so it no longer writes a "resolved" edge
                            and no longer feeds the Invested->Bonded faith gate
Daemon FLAG 3               FIXED, and DO NOT REMOVE THE GATE. aria_daemon STEP 4b
  proposal delays an        scans with AppraisalChain.has_distress_markers() and
  emergency                 passes allow_tier_2_proposal=not distressed into
                            select(). The old "RESOLVED: no crisis pre-check"
                            note rested on two false claims — see HANDOFF_NOTES
```

Build-time tuning placeholders still carrying `TODO` — mechanism locked, value
open. A value existing here is NOT the question being answered:

```
pad_engine       PAD_HISTORY_LENGTH
needs_system     K_LOAD = 0.05, K_REST = 0.03                        (F-2a/F-2b)
graph_manager    habituation 0.9 cutoff / 0.05 decrement / 5 window  (OQ1-rate)
appraisal_chain  arc turn-counts, distress + social lexicons         (F-4d/F-4e)
                 arc absent-turn threshold = 5, aliased to the
                 spec-named _ARC_CLOSE_ABSENT_TURNS (was 3)
moral_schema     anti-pattern marker lexicons                        (OQ-M1)
soul_filter      deflection markers
audio_pipeline   prosody magnitudes                                  (F-7-prosody)
visual_layer     zone precedence for overlapping signatures          (F-10-zone-precedence)
backend_router   TIER_2_KEYWORDS, HEALTH_CACHE_TTL_SECONDS = 30
aria_daemon      soul-tick 3s / DMN-tick 30s intervals                (F-8a)
```

Pinned, not placeholders: idle window 8 min, reflection 6 h, precision decay
72h/14d/60d, poignancy floors 0.85/0.55 — **critical and high ONLY; medium/low
have NO floor** (ResLog item 9, enforced in code since 2026-08-20) — Baumeister
+0.15, speaker verification ≥0.75, VAD ≥0.5, emergency coping thresholds
≤0.15/≤0.04, Energy gates 30/20, PAD restore bounds [0,1] and Energy [0,100],
need windows 72h/14d/14d/60d reused as the two-window `neglected` ladder,
visual stability 8 s.

---

## 7. Note on flat-file uploads

In a flat knowledge base the repo paths cited throughout the source and the
tracker do not resolve. Mapping: `.kiro/specs/<module>/{requirements,design,
tasks}.md` is uploaded as a single consolidated `spec_<module>.md`, and
`daemon/<file>.py` is uploaded as plain `<file>.py`. A "file not found" for a
cited path is this, not a missing file.

**Those consolidated files are GENERATED as of 2026-08-21. Do not hand-edit
them.** `.kiro/specs/` is the source of truth; `tools/build_handoff_bundle.py`
derives the bundle from it.

```
make bundle        regenerate handoff_bundle/specs/ from .kiro/specs/
make check-bundle  verify in sync, non-zero exit if stale, writes nothing
make check         test + check-bundle — run before committing
```

They were hand-synced before this, which is why the `tasks.md` checkbox ticks
were missed on 2026-08-20 until someone asked. The generator was verified by
reproducing all thirteen committed files BYTE-FOR-BYTE before it was committed,
so the upload artifacts did not change when it landed — it only removed the
possibility of them drifting again. One real drift it found on its first run is
recorded in `HANDOFF_NOTES.md`.

The only hand-authored part of a bundle file is its opening header — title,
provenance line, and for five modules the condensed `> ## AMENDMENT` summaries
hoisted above the specs. Those live in `handoff_bundle/spec_headers/<module>.md`
(see its `README.md`) and are copied verbatim. The generator paraphrases nothing
and decides nothing; it is not in the precedence chain.

Thirteen modules, thirteen `spec_*.md` files as of 2026-08-20. Three of them —
`spec_state-manager.md`, `spec_session-buffer.md`, `spec_backend-router.md` — are
titled "module reference (NOT a locked spec)" rather than "locked spec", and say
so in their own banner. They hold a design reference only, derived from the
shipped code rather than authored ahead of it, and no requirements or tasks. Do
not read a SHALL into them; they record what the code does, not what it must do.
