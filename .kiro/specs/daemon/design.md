# Design Document — Module 8: Daemon / Soul Tick

## Overview

The Daemon (`daemon/aria_daemon.py`) is Aria's ORCHESTRATOR. It drives two separate clocks,
routes an inbound turn through the full pipeline, selects pre-cached thinking sounds,
evaluates initiative, detects idle, and honors the HANDOFF startup contract. It is the
CALLER of every core module and the top of the dependency tree — nothing imports it, so it
may import everything without a cycle.

The single most important property is what the Daemon does NOT do: it computes no meaning and
no feeling (steering/project-rules.md). PAD moves only inside PAD_Engine (EMA decay on the
soul tick) and inside the Appraisal Chain (its Stage-4 delta). Need states come only from
Needs_System. The Daemon routes signals and drives clocks; the modules decide.

This design implements requirements.md as written, using only mechanisms already specified
there or in the supporting documents. No new mechanism, formula, or threshold is introduced.
Genuine gaps are carried as flagged Open Questions / build-time placeholders (requirements.md
OQ-1…OQ-4), never resolved by invention.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **COMPUTES NO FEELING.** The Daemon never calls `apply_appraisal_delta` (grep-clean: the
   call `.apply_appraisal_delta(` never appears in the source). It calls
   `PAD_Engine.on_soul_tick()` (driving the decay clock — the module does the math) and
   `get_current_pad()` (a presentation read), but writes no PAD (Req 1).
2. **TWO SEPARATE CLOCKS.** `soul_tick()` drives PAD + Energy + attention and never runs a
   DMN pass; `dmn_tick()` runs a DMN pass and never decays PAD. Neither triggers the other
   (Req 2).
3. **F4 / BARGE-IN = ZERO INTERNAL EFFECT.** Each interrupt's entire body is one call into
   the Audio Pipeline. No path to PAD, appraisal, graph, needs, or state (Req 8; Addendum §5).
4. **HANDOFF CONTRACT, EXACTLY.** initialize() once (guarded); consistency_flags cleared and
   persisted; last_applied_valence round-tripped on save + shutdown (Req 9/10/11).
5. **INITIATIVE:** highest-pressure `due` need, once, no nag, enters at soul_filter directly;
   no numeric threshold (Req 7; Addendum §7).
6. **NO OTHER CORE MODULE IS MUTATED** except the additive, doc-anticipated DMN-contract-gap
   closures (Req 13), each new-method-only.

## Architecture

```
                                external world
   voice(STT text)  F4 / barge-in   wall-clock          shutdown / cadence
        │                 │             │                       │
        ▼                 ▼             ▼                       ▼
   ┌──────────────────────────── AriaDaemon (Module 8) ────────────────────────────┐
   │ startup()  — HANDOFF: initialize() ONCE (guarded) + restored valence;          │
   │              clear consistency_flags; restore Energy.                          │
   │                                                                                │
   │  CLOCK 1 soul_tick():   PAD_Engine.on_soul_tick()   [Module 1 owns the math]   │
   │      (maintenance)      Needs.on_soul_tick / on_idle_recovery   [Module 2]     │
   │                         refresh attentional policy + evaluate initiative       │
   │                                                                                │
   │  CLOCK 2 dmn_tick():    if idle(1&2) → DMN.run_idle_pass()   [Module 6]         │
   │      (consolidation)    (DMN reads Energy → FULL/SHALLOW depth = condition 3)   │
   │                                                                                │
   │  route_inbound_turn():  thinking sound → Appraisal → Soul_Filter → LLM → gate  │
   │                         → TTS ; (poignancy=critical → DMN.run_forced_partial)  │
   │                                                                                │
   │  on_f4_interrupt()/on_barge_in():  audio.stop_playback()   ← ZERO else         │
   │  _route_initiative():  build minimal appraisal → Soul_Filter → TTS (skip STT)  │
   │  save_periodic()/shutdown():  save PAD + Energy + last_applied_valence          │
   └────────────────────────────────────────────────────────────────────────────────┘
        │            │            │             │            │             │
        ▼            ▼            ▼             ▼            ▼             ▼
   PAD_Engine   Needs_System  Memory_Graph  Appraisal   Soul_Filter   DMN   State_Manager
   [M1 REAL]    [M2 REAL]     [M3 REAL]     [M4 REAL]   [M5 REAL]    [M6]   [M11 REAL]
                                                            │
                                                       LLM_Interface [M9 REAL]
   Audio_Pipeline [M7 CONTRACT — fake]     Visual_Layer [M10 CONTRACT — not wired here]
```

## Startup contract (HANDOFF_NOTES) — the exact sequence

`startup()` runs ONCE (guarded by `_started`; a second call raises — initialize() is not
idempotent, HANDOFF (c)):

1. `pad_state, energy, self_model, valence_str = StateManager.load_all()`.
2. `restored_snapshot = pad_state_to_snapshot(pad_state)` and
   `restored_valence = valence_from_str(valence_str)` — BOTH conversions at the wiring call
   site (HANDOFF: the same wiring helper that converts PADState→PADSnapshot; NOT inside
   PAD_Engine or State_Manager).
3. `PAD_Engine.initialize(restored_snapshot, restored_valence)` — EXACTLY ONCE (HANDOFF (a)/(c)).
4. `Needs_System.initialize(energy)`.
5. CLEAR `consistency_flags` (all → False) and `save_self_model(...)` — HANDOFF (b); the
   quality record and recent-learning fields are untouched.
6. Arm the two clocks and the idle timer at boot.

`save_periodic()` / `shutdown()` persist PAD (snapshot→PADState), Energy, and the
last_applied_valence string (HANDOFF (a)). The valence is read from PAD_Engine's
`_last_applied_valence` via the wiring helper `read_pad_last_valence()` — the HANDOFF's "get
access added for this purpose … Module 1's implementation decides this" is fulfilled by
reading the HANDOFF-NAMED field in the Daemon's wiring layer, WITHOUT expanding Module 1's
locked public API (Req 11.4).

**Round-trip proof (Req 11):** save writes `Valence.value`; a fresh process loads the string,
`valence_from_str` converts it back, and it is passed to `initialize(restored_valence)` — so
PAD_Engine's `_last_applied_valence` is restored, keeping its restore-boundary raise rare.

## The two clocks (Req 2)

Modeled as two independent public methods plus a scheduler:

- `soul_tick(now)`: `PAD_Engine.on_soul_tick()`; then `Needs.on_idle_recovery()` if idle else
  `Needs.on_soul_tick()` ("soul tick recovers Energy during extended idle", v4);
  `_refresh_attentional_policy()`; `_maybe_initiate()`. Never runs a DMN pass.
- `dmn_tick(now)`: if idle conditions 1 & 2 → `DMN.run_idle_pass(...)`. Never decays PAD.
- `run_scheduler_step(now)`: fires each clock when `now - last_fire ≥ interval`, each on its
  OWN interval; neither triggers the other. Intervals are F-8a placeholders (injectable).

The direct `soul_tick`/`dmn_tick` methods are the primary interface (and the test surface
that proves independence): ticking soul N times decays PAD and runs no DMN pass; ticking DMN
at idle runs a pass and leaves PAD identical.

## Idle detection (Req 4)

`_idle_conditions_met(now)` returns `(now - last_voice_input) ≥ 8min AND not output_pending`.
Only conditions 1 & 2 (Daemon-owned). Condition 3 (Energy > 20) is NOT gated here: DMN reads
Energy to choose FULL vs SHALLOW depth (DMN spec Req 2.3). Gating idle on Energy here would
make the shallow pass unreachable — so the split follows the DMN spec's own division of
responsibility. The 8-minute window is PINNED (v4); it is injectable but defaults to 8min.

## Inbound-turn routing (Req 5)

`route_inbound_turn(user_text, session_id, entity_refs, entity_node_id,
active_uncertainty_refs, now)`:

1. Meta-command interception: `self._session_buffer.is_meta_command(user_text)` — if
   "rest"/"focus"/"unfocus" is detected, return `_handle_meta_command(...)` IMMEDIATELY,
   bypassing appraisal, Soul_Filter, the LLM, and the Output Gate entirely. "rest" also
   forces a DMN partial-consolidation pass and clears the session buffer; "focus"/
   "unfocus" toggle `SessionBuffer.set_focus_mode`. Each returns a hardcoded
   `SoulFilterResponse` with `gate_results=()`.
2. Cognitive-load check: if `self._session_buffer.fullness_state()` is "heavy" or
   "critical", call `self._appraisal.submit_cognitive_load(fullness)` — a second-order
   appraisal event distinct from the per-turn Stage 0-6 appraisal below.
3. `_note_voice_input(now)` (reset idle condition 1); `output_pending = True`; update the
   volatile Present World Model (`last_user_text`) — working state, not persisted.
4. Play a pre-cached thinking sound (Layer 5): reads current PAD + the user's text for
   PRESENTATION only; never a PAD write.
5. Appraisal (Module 4): get need states from Needs_System, call
   `Appraisal_Chain.appraise(...)`, then `_track_turn(...)` to update session-entity /
   active-uncertainty / most-recently-salient-node working state. PAD moves here ONLY as
   the appraisal's own byproduct via PAD_Engine — the Daemon writes no PAD.
6. Compute the post-emergency flag: read `_last_turn_was_emergency` (set by the PREVIOUS
   turn) before calling Soul_Filter, then update it to this turn's `appraisal.emergency`
   AFTER appraisal.
7. Soul_Filter (Module 5): assemble `session_context = self._session_buffer.
   get_context()` (the ephemeral 3-tier conversation transcript) and call
   `Soul_Filter.respond(appraisal_result=appraisal, user_message=user_text,
   entity_node_id=..., entity_refs=..., need_states=..., now=now,
   post_emergency=post_emergency_this_turn, session_context=session_context)`. The
   five-field boundary and the Output Gate remain Soul_Filter's; the Daemon passes the
   appraisal, the raw user message, and the session context through unchanged.
8. Audio Pipeline (Module 7 contract): `self._audio.speak(response.text)` (TTS);
   `output_pending = False`.
9. Append the turn to the session buffer: `self._session_buffer.append_turn(user_text,
   response.text)` — ephemeral working memory only, not the graph.
10. Reflection trigger: if `appraisal.poignancy is CRITICAL` and an EventNode was
    written, force an EARLY DMN partial pass (`run_forced_partial_pass`) with a
    single-item buffer. This is a DMN-CLOCK event triggered by content — it does NOT
    decay PAD and does NOT merge the soul-tick and DMN-tick clocks.

## Thinking sounds (Req 6; v4 Layer 5)

`select_thinking_sound(text, pad)` is a pure categorical function using the v4 table's exact
words and PAD thresholds (0.7 / 0.6 / 0.5 — IN-SPEC presentation thresholds, same category as
the emergency coping thresholds). Precedence (a documented presentation choice, OQ-1): content
triggers (Concern: worry/problem/fail/error; Surprise: surprise/unexpected/suddenly) →
PAD-mood (Playfulness: D>0.6 & P>0.5; Warmth: P>0.7) → Contemplation (default). Contentless
input → no sound. Reading PAD is presentation, not a write (Req 6.2).

## Initiative (Req 7; v4 Layer 2/6; Addendum §7)

- `_select_highest_pressure_need(need_states)`: returns the first need in canonical order
  (Connection, Growth, Purpose, Continuity) whose state is `DUE` (or `NEGLECTED`, accepted
  defensively though Needs_System never emits it — OQ-2), else None. CATEGORICAL — no number
  (percentage test holds); canonical order is the tie-break (F-8b, OQ-3).
- `_maybe_initiate()`: fires ONCE per due-episode for the highest-pressure need, latching
  `_initiative_expressed[need]=True`; never repeats while still due (no nag). The latch resets
  to False in `_refresh_attentional_policy` when the need is SATISFIED again — so a LATER drop
  can express once more (v4 "expresses a need exactly once when it drops").
- `_route_initiative(need)`: enters at soul_filter DIRECTLY (Addendum §7). The Appraisal Chain
  is NOT invoked (no user turn). The Daemon selects a PRE-AUTHORED behavioral instruction by
  which need is due (`_INITIATIVE_NOTES`, hardcoded like Soul_Filter's PERSONA_ANCHOR — the
  MEANING that the need is due came from Needs_System) and packages it into a minimal
  `AppraisalResult` (non-emergency, low poignancy, all-clear signals, and an INERT PAD delta
  that Soul_Filter never applies). Soul_Filter renders → LLM → gate → TTS. The Daemon writes
  no PAD (the inert delta is a data placeholder for a frozen contract field).

## F4 / barge-in (Req 8; Addendum §5)

`on_f4_interrupt()` and `on_barge_in()` each have a single-statement body:
`self._audio.stop_playback()`. There is no reference to PAD_Engine, Appraisal, Graph, Needs,
or State — proving structurally there is no path to a PAD write or any state mutation. The
`_output_pending` flag is intentionally NOT touched here: "return to listening" is the Audio
Pipeline's `stop_playback()` responsibility, keeping F4 a pure, zero-internal-effect audio
stop. Whatever the user says AFTER enters appraisal normally, as any input (Addendum §5).

## Volatile working state (Req 12; Resolution Log item 10)

Held in memory, NEVER persisted: `_present_world_model`, `_language` (default "en",
conversation-driven only), `_last_voice_input_at`, `_output_pending`,
`_most_recently_salient_node`, `_highest_pressure_need`, `_attentional_focus`,
`_initiative_expressed`, the self-monitoring buffer, and the tracked active-uncertainty /
session-entity / rupture refs relayed to DMN.

## DMN-contract-gap closures (Req 13) — additive, doc-anticipated

- **`appraisal_chain.submit_aha_insight(insight)`** — accepts DMN's aha EVENT (DUCK-TYPED, to
  avoid the import cycle soul_filter→appraisal_chain→dmn→needs_system→soul_filter), builds a
  small POSITIVE byproduct delta (pleasure/competence up, valence POSITIVE), and applies it
  through the module's only PAD-write path (PAD_Engine). Magnitude is a SUBSTRATE placeholder
  (the `_PAD_STEP` tiers); v4 pins only the SIGN ("small positive"). Complements — does not
  replace — `appraise(aha_insight=<PADDelta>)`.
- **`graph_manager.predictability_evidence(entity_ref)`** — Observing→Engaging (Addendum §2
  "a specific behavioral pattern has recurred"): a specific (q2×q3) profile appears on ≥2
  events for the entity (uncertain profiles excluded). Categorical boolean; the count feeds
  only the ">1" gate, never a magnitude.
- **`graph_manager.dependability_evidence(entity_ref)`** — Engaging→Invested (Addendum §2
  "generalizes across more than one distinct kind of situation"): a specific profile appears
  in ≥2 distinct `session_id`s (session = situation, a structural proxy — finer definitions
  build-time). Categorical boolean.
- **`graph_manager.highest_salience_unconnected_candidates(limit)`** — pairs of the
  highest-salience UNCONNECTED EventNodes (cutoff = the in-spec HIGH floor 0.55; limit is a
  build-time placeholder) with the structural facts DMN's ConnectionCandidate needs
  (already_connected=False, shares_context, both_high_salience, reveals_new_pattern — a
  FLAGGED structural proxy for "explanatory power": a shared entity ACROSS sessions). Substrate
  selection only; forms no edge, decides no meaning. The Daemon maps each record 1:1 to a
  ConnectionCandidate (pure packaging).

The only existing test affected is the single DMN assertion that documented
predictability/dependability as not-yet-present; it is updated to assert closure (Req 13.4).

## Data types / helpers

- `ThinkingSound` (enum: CONTEMPLATION/SURPRISE/CONCERN/WARMTH/PLAYFULNESS).
- `AudioPipelinePort` (Protocol: speak / stop_playback / play_thinking_sound /
  play_reconsideration_sound) — the Module 7 contract.
- Module-level wiring helpers: `pad_state_to_snapshot`, `snapshot_to_pad_state`,
  `valence_from_str`, `valence_to_str`, `read_pad_last_valence`, `need_states_to_mapping`,
  `select_thinking_sound`, `build_initiative_appraisal`.

## Error handling

- `startup()` twice → RuntimeError (initialize() not idempotent).
- Any tick/route before `startup()` → RuntimeError (`_require_started`).
- Unrecognised / missing persisted valence → `valence_from_str` returns None → PAD Engine's
  own residual restore-boundary handling stands (the Daemon invents no resolution).
- Entity refs passed to routing are expected to be resolved EntityNode ids (the entity
  resolution layer's job, upstream), consistent with the DMN stage-evaluation contract.

## Testing strategy

Plain pytest (no hypothesis), matching Modules 1–6. Real core modules + fakes for the
unbuilt Audio Pipeline and the LLM transports; a spy DMN for clock-independence; counting /
tripwire PAD engines for the initialize-once and zero-effect proofs. See test_daemon.py.
