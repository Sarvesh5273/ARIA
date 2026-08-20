# Implementation Plan — Module 8: Daemon / Soul Tick

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing reopens a locked item (F-8b RESOLVED by item 10; F-8a values
are build-time placeholders). Genuinely-undefined values are `TODO(F-8a)` / OQ placeholders,
never invented. All prior-module edits are ADDITIVE and doc-anticipated (Req 13 / HANDOFF).

- [x] 1. Module scaffold + reuse-not-redefine imports (top of the dependency tree).
  - Create `daemon/aria_daemon.py` with a docstring citing the five constraints, v4
    "Two-Process Separation" / Layer 5 / Layer 2, Addendum §5/§7, HANDOFF_NOTES, and the
    F-8a/F-8b disposition.
  - Import REAL interfaces from every core module (pad_engine, state_manager, needs_system,
    graph_manager, appraisal_chain, soul_filter, dmn). No import cycle (nothing imports the
    Daemon).
  - _Requirements: 1.4_

- [x] 2. Constants — PINNED cadences vs FLAGGED placeholders.
  - `IDLE_NO_VOICE_WINDOW = 8min`, `REFLECTION_INTERVAL = 6h` (PINNED, v4).
  - `DEFAULT_SOUL_TICK_INTERVAL` / `DEFAULT_DMN_TICK_INTERVAL` — `TODO(F-8a)` placeholders.
  - `_NEED_ORDER` (canonical tie-break order, F-8b/OQ-3). `_now()` aware-UTC helper.
  - _Requirements: 3.5, 4.4, 7.5_

- [x] 3. Wiring helpers (the conversions HANDOFF assigns to the Daemon's wiring layer).
  - `pad_state_to_snapshot` / `snapshot_to_pad_state`; `valence_from_str` / `valence_to_str`
    (None/unknown → None, no invented resolution); `read_pad_last_valence` (reads the
    HANDOFF-named field WITHOUT expanding Module 1's locked API); `need_states_to_mapping`.
  - _Requirements: 9.3, 11.1, 11.2, 11.3, 11.4, 5.2_

- [x] 4. Thinking-sound selection (Layer 5).
  - `ThinkingSound` enum + `select_thinking_sound(text, pad)` — v4 table's exact words +
    thresholds; content → PAD-mood → contemplation default; contentless → None. Reading PAD
    is presentation, not a write.
  - _Requirements: 6.1, 6.2, 6.4_

- [x] 5. Initiative constants + minimal appraisal builder.
  - `_INITIATIVE_NOTES` (pre-authored HOW instructions per need, v4 "single gentle reach-out");
    `_INERT_PAD_DELTA` (never applied) + `_NEUTRAL_SOCIAL_SIGNALS`; `build_initiative_appraisal`
    (non-emergency, low poignancy, all-clear signals).
  - _Requirements: 7.4_

- [x] 6. `AudioPipelinePort` Protocol (Module 7 contract; fake in tests).
  - `speak` / `stop_playback` / `play_thinking_sound` / `play_reconsideration_sound`.
  - _Requirements: 1.4, 5.1, 8.1_

- [x] 7. `AriaDaemon.__init__` — inject all modules + volatile working state + two clocks.
  - Inject pad/needs/graph/appraisal/soul_filter/dmn/state/audio + ids + clock + intervals.
  - Init `_started=False`, volatile working state (present world model, language, idle timer,
    output_pending, attentional focus, no-nag latch, DMN-input buffers).
  - _Requirements: 1.4, 12.1, 12.2_

- [x] 8. `startup()` — the HANDOFF contract, EXACTLY ONCE.
  - Guard `_started` (second call raises — initialize() not idempotent, HANDOFF (c)).
  - `load_all()`; `initialize(restored_snapshot, restored_valence)` ONCE; `Needs.initialize`;
    CLEAR consistency_flags + `save_self_model`; arm the clocks/idle timer.
  - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.2, 11.3_

- [x] 9. `shutdown()` / `save_periodic()` / `_save_state()` — round-trip valence.
  - Save PAD (snapshot→PADState), Energy, and `read_pad_last_valence` → string (HANDOFF (a)).
  - _Requirements: 11.1, 11.4_

- [x] 10. CLOCK 1 — `soul_tick()`.
  - `PAD_Engine.on_soul_tick()`; `Needs.on_idle_recovery()` if idle else `on_soul_tick()`;
    `_refresh_attentional_policy()`; `_maybe_initiate()`. Never runs a DMN pass.
  - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4_

- [x] 11. CLOCK 2 — `dmn_tick()` + `run_scheduler_step()`.
  - `dmn_tick`: at idle(1&2) → `DMN.run_idle_pass`; else None. Never decays PAD.
  - `run_scheduler_step`: fire each clock on its OWN interval, independently.
  - _Requirements: 2.1, 2.3, 2.4, 4.1, 4.2, 4.3_

- [x] 12. Idle detection — `_idle_conditions_met()` + `_note_voice_input()`.
  - Conditions 1 & 2 only (Daemon-owned); Energy (condition 3) left to DMN's depth choice.
  - _Requirements: 4.1_

- [x] 13. Inbound-turn routing — `route_inbound_turn()`.
  - Thinking sound → Appraisal (need-states mapping) → `_track_turn` → Soul_Filter → TTS;
    poignancy=critical → `run_forced_partial_pass` (DMN clock, not a soul tick).
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 4.5_

- [x] 14. F4 / barge-in — ZERO internal effect.
  - `on_f4_interrupt()` / `on_barge_in()`: single-statement `audio.stop_playback()`. No path
    to PAD/appraisal/graph/needs/state.
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 15. Attentional policy + initiative.
  - `_refresh_attentional_policy` (highest-pressure need + most-recently-salient node, reset
    no-nag latches on satisfied); `_select_highest_pressure_need` (categorical, keyed on
    `due`, canonical tie-break); `_maybe_initiate` (once, no nag); `_route_initiative` (enter
    at soul_filter, skip STT/appraisal, TTS).
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 12.1, 12.3_

- [x] 16. Thinking-sound playback + reconsideration + language state.
  - `_play_thinking_sound` (presentation PAD read); `on_reconsideration` (audio);
    `set_language` / `language` (volatile, conversation-driven).
  - _Requirements: 6.3, 12.2, 12.3_

- [x] 17. DMN-pass input assembly + result consumption + turn tracking.
  - `_assemble_idle_pass_input` (maps graph's `highest_salience_unconnected_candidates` →
    ConnectionCandidate 1:1); `_consume_dmn_result` (clear consumed buffer + ruptures);
    `_track_turn` (buffer + reaction linking + uncertainty/entity/rupture relay).
  - _Requirements: 5.1, 4.5_

- [x] 18. ADDITIVE — `appraisal_chain.submit_aha_insight(insight)`.
  - Duck-typed (no import cycle); small POSITIVE byproduct delta via PAD_Engine; DMN never
    builds/writes PAD. New method only; existing signatures/behavior unchanged.
  - _Requirements: 13.1, 13.4_

- [x] 19. ADDITIVE — `graph_manager.predictability_evidence` / `dependability_evidence`.
  - Structural/categorical booleans (Addendum §2): recurrence of a specific (q2×q3) profile;
    generalization across ≥2 sessions. Never a score. New methods only.
  - _Requirements: 13.2, 13.4_

- [x] 20. ADDITIVE — `graph_manager.highest_salience_unconnected_candidates`.
  - Substrate selection of unconnected high-salience EventNode pairs + structural facts
    (cutoff = in-spec HIGH floor 0.55; `reveals_new_pattern` = flagged cross-session proxy).
    Forms no edge, decides no meaning. New method + `_edge_exists_between` helper only.
  - _Requirements: 13.3, 13.4_

- [x] 21. Update the single DMN gap assertion to reflect closure.
  - `test_dmn.py::test_real_graph_satisfies_the_methods_dmn_calls` — the two `assert not
    hasattr(...)` lines become `assert callable(getattr(...))` (the gap is now closed).
  - _Requirements: 13.4_

- [x] 22. Tests — `tests/test_daemon.py` (plain pytest, NO hypothesis).
  - Two clocks independent; initialize() once + second-startup guard; consistency_flags
    cleared + persisted; last_applied_valence round-trip (shutdown + periodic); F4/barge-in
    zero-effect tripwire; initiative keys on `due`, once, no nag, enters at soul_filter;
    full inbound turn end-to-end with REAL modules; thinking-sound selection; grep-clean "no
    PAD write"; and the additive-closure tests (submit_aha_insight; predictability /
    dependability / unconnected-candidates; DMN wired to the REAL predicate).
  - Verify: `pytest tests/test_daemon.py -q` green, then `pytest -q` — prior 317 stay green.
  - _Requirements: all_
