# ARIA — Project Status

Living tracker. Update after every module is approved. This file, plus
the docs/ folder, is everything a fresh review session needs — it does
not depend on any specific chat's history.

Counts and line numbers below were last measured against the code on
**2026-08-26**. They are measured values, not estimates — if you change code,
re-measure rather than assuming.

Full suite: **863 collected** — soul layer **647**, adapter layer **199**,
cross-cutting **17**. With an embedding backend reachable that is 863 passed; on
the 2026-08-26 measurement run Ollama was down, so it read **860 passed + 3
skipped** — the documented real-model embedding arm, which skips rather than fails
so `make check` stays hermetic. Stated as COLLECTED first because that is the
figure that does not depend on what is running on the machine.

Re-measured per file with `pytest --collect-only -q`, and the arithmetic is split
per commit deliberately, because the total had drifted once already and one jump
would credit the wrong commit:

| step | delta | commit | where |
|---|---|---|---|
| 812 → 821 | +9 | `6582795` (ResLog 29) | daemon 66→71, audio_pipeline 29→32, session_buffer 40→41 — **never recorded in this file at the time** |
| 821 → 827 | +6 | `096c618` (item 30, PAD OQ4) | `pad_restore_boundary` 11→17 |
| 827 → 838 | +11 | `a394825` (item 31, stage directions) | `session_buffer` 41→52 |
| 838 → 842 | +4 | `cf0c353` (item 32, continuity note) | `daemon` 71→75 |
| 842 → 863 | +21 | `8d57605` (item 34, moral-schema floor/derived) | **new file** `test_moral_schema.py` — the module had none |

Adapter layer did not move in any of the four. **Cross-cutting stayed at 17**:
that bucket is `pad_restore_boundary` alone, which is a cross-module boundary file
rather than one module's suite. Item 31's 11 tests are SOUL-LAYER — `session_buffer`
is Module 12 — which is why soul went 611 → 626 rather than cross-cutting going
17 → 28.

Without an embedding backend reachable, the
same 3 tests skip and the rest pass — measured directly at 723 + 3 skipped when
the suite stood at 726, so the figure today is **839 + 3**. Stated that way because
the macOS Ollama.app restarts the daemon on its own, which makes the
backend-down arm awkward to re-measure on demand. *(This read "755 + 3" until
2026-08-26 — stale by a different amount again, since 755 + 3 describes a
758-test suite and was never updated after the boundary phase. Corrected here
because a derived figure nobody re-derives is how a tracker starts lying quietly.)* Both numbers are real and neither is a failure: the
three skipped tests are the real-model half of the embedding comparison, which
skips rather than fails so `make check` stays hermetic on a machine with no
Ollama running — verified both ways this session, by stopping the daemon and
re-running. A further **17** audio tests skip on a machine without macOS `say` or
an audio player on PATH; they pass here because both are present, which is what
made the output chain verifiable rather than only unit-tested.

Per-file test counts as measured on 2026-08-26 — soul layer: appraisal_chain 64,
**audio_pipeline 32** (+3, ResLog 29C's VAD reset),
backend_router 25,
**daemon 75** (+5 ResLog 29A's third Energy state, +4 item 32's Continuity note),
dmn 44, graph_manager 63, llm_interface 41,
**moral_schema 21** (NEW file, item 34 — the shared resource had no test file of
its own; it was covered incidentally through `test_soul_filter.py`'s
citation assertion and `test_dmn.py`'s gate-identity assertion),
needs_system 47, pad_engine 53,
**session_buffer 52** (+11, item 31: the stage-direction compounding loop),
**soul_filter 68**, state_manager 38,
visual_layer 24 — **647**. Plus **`pad_restore_boundary` 17** (+6, item 30),
which is a cross-module boundary file rather than one module's suite.

`pad_engine` stays at **53** and `daemon/pad_engine.py` is byte-unchanged by item
30 — the OQ4 fix is entirely in the wiring layer, and both facts are asserted by
tests rather than claimed here.

Soul-layer count history: it was **547** through the whole boundary phase — five
new adapter families and three defects surfaced without one soul test changing,
which is what the one-way dependency arrow was for. The **defect pass** then moved
it to 561, in exactly one module (Module 5), for the two rulings that required it.
**Item 28** moved it to 602, in two modules (12 and 8) — the SessionBuffer resize
and the actual-token seam.

Adapter layer: embedding_local 22 (19 hermetic + 3 real-backend),
**transport_ollama 34** (+10 on 08-25, the token-count side-channel; +1 on 08-24,
the Qwen family rung),
**transport_cloud 48** (+8 on 08-25, the same seam via `usage`),
**audio_adapters 67** (+5 on 08-24 for ResLog 25/27:
the strip, the all-narration case, the probe, dormancy, and the refusal of an
unrecognised direction), **visual_adapters 28** — 199. Cross-cutting:
**pad_restore_boundary 17**. Soul layer 626 (llm_interface 41 included; +5 on
08-24 for ResLog 26's routing values). Total 863.

The 08-24 pass also fixed a latent FLAKY test rather than only adding: macOS
`say` is not byte-deterministic — 39,898 bytes on 53 of 60 identical invocations
and 39,804 on the other 7, a 94-byte wobble in trailing silence. The
stage-direction test compared rendered audio, which passed only because its old
`>` margin was wide; asserting the strip needed exactness and exposed it. It now
asserts on the text handed to the synthesiser (hermetic) plus a bound derived from
the narration's own size, and the prosody-dormancy test asserts invariance of the
rate conversions instead of comparing two renderings. Verified stable over 5
consecutive runs.

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

**She also speaks, sees, and can reach the cloud, as of the boundary phase
(2026-08-22).** All 21 Protocols now have a real implementation available, and
the eight that were empty are empty no longer:

```
.venv/bin/python main.py --audio --visual-headless
.venv/bin/python main.py --audio-preflight     # what the 7 audio backends need
.venv/bin/python main.py --visual-preflight    # what Module 10 needs
```

What is wired by default: `EmbeddingModel` (real), `LocalModelTransport` (real,
Ollama), `AudioPipelinePort` (no-op unless `--audio`), and both cloud tiers as an
explicitly-unhealthy `UnconfiguredTransport` unless keyed. Audio and visual are
opt-in because both are LEAVES — nothing downstream reads what they did — so
their absence changes no behaviour inside the system, and a text bring-up should
not start talking out loud. See "Adapter layer" below.

**What still does not run, and what "not running" now means:**

- **Inbound audio needs five providers this project does not ship.** All seven
  backends are IMPLEMENTED (`adapters/audio_*.py`); five need a dependency that
  is not installed — `sounddevice`, `pvporcupine`, `torch`, `onnxruntime`,
  `faster-whisper` — plus a Silero VAD model, a speaker model and an enrolled
  voiceprint. `--audio-preflight` reports exactly which. The OUTPUT chain runs
  today with zero installs and was verified end to end. The Daemon's port is
  output-only, so this is not a gap in the wired path at all: the REPL prompt IS
  the transcription.
- **The Visual Layer's real window needs PyQt6 + libmpv and 17 video files.**
  `MpvVideoWindow` is implemented; neither provider is installed here and no loop
  files exist. `--visual-headless` runs the whole zone machinery — categorical
  mapping, 8-second stability gate, talking/idle variant, inward/waiting override
  — against a logging window, which is how it was verified.
- **`AriaDaemon` still takes no visual parameter, deliberately.** The speaking
  signal is taken from the boundary Module 10's own docstring names — `audio.speak()`
  — by decorating the audio port. No approved module's constructor was changed.
  See `adapters/visual_bridge.py`.
- **Nothing drives the clocks between turns.** `input()` blocks, so PAD decay,
  Energy recovery, the DMN clock and the visual refresh all advance only when a
  turn completes. This is a REPL limitation, not a module one, and the DMN
  observation below shows it has a real cost.

  **The modules are already shaped for a real host** (recorded 2026-08-26 so
  whoever builds one does not have to rediscover it). Four public entry points on
  `AriaDaemon` are designed to be driven from a timer thread or async loop, and
  each takes an injectable `now` so the host owns the clock:
  `soul_tick(now=None)`, `dmn_tick(now=None)`, `run_scheduler_step(now=None)`
  (drives both and returns what fired), and `save_periodic()`. Nothing about the
  soul layer needs to change for a real host — the REPL simply never calls them
  between turns. Note the method is `soul_tick`, not `on_soul_tick`, and there is
  no `on_idle_recovery`: idle recovery is one of the three Energy states *inside*
  `soul_tick` (ResLog 29A), not a separate entry point.

  **This is a host limitation AND it has a measured cost — both, not one instead
  of the other.** It would be convenient to file this as "architecturally correct,
  no code change needed" and close it, and that would erase a finding: under the
  synchronous REPL, `_output_pending` is never True when a tick lands, so Energy
  only ever HOLDS or RECOVERS and the depletion branch is unreachable (ResLog
  29A's own left-open consequence). The DMN observation below is what surfaced it.
  So the row stays as a known limitation of the development host rather than a
  resolved question.
- **`requirements.txt` is still pytest only, and the soul layer still has zero
  runtime dependencies.** The cloud adapter and both TTS paths use stdlib
  `urllib`/`subprocess`; the audio and visual providers are imported LAZILY, so
  `import adapters.audio_stt` succeeds on a machine with no Whisper and the suite
  stays hermetic. Pinned by `test_every_audio_adapter_imports_without_any_provider_installed`.
- **Idle consolidation HAS now been observed** — see "The DMN idle pass, observed"
  below. Module 6 is not broken; the finding is that she arrives at her own
  consolidation pass too depleted to run the deep half of it.
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
| `adapters/transport_ollama.py` | `LocalModelTransport` + `HealthProbe` | `OllamaLocalTransport`, `/api/generate`. Default `qwen3.5:9b-mlx` (8.9 GB, 256K context) per **ResLog 24**; v4's own `gemma4:e2b-it-qat` stays named as `SPEC_MODEL` and as rung 2 of `resolve_model`'s four-rung ladder, which now does real work because the two constants finally differ. `_LOCAL_VOICE_FAMILY_PREFIXES` sanctions two families (Qwen 3.5, Gemma) and the ladder still refuses to reach outside them. *(This cell read `gemma4:12b-it-qat` until 2026-08-24 — stale since the same-day 08-22 reversal, and contradicting the Accepted-decisions row below for two days.)* `keep_alive=-1` on every request is how "loads at startup, stays resident" is expressed to Ollama; `unload()` sends `0`. `is_loaded` is a local flag costing no round trip, because `select()` reads it every turn; `refresh_residency()` asks `/api/ps` for ground truth. Load/unload/residency verified against a live daemon. |
| `adapters/transport_unconfigured.py` | `ModelTransport` + `HealthProbe` | `UnconfiguredTransport` — the honest state of the two cloud tiers as code. Explicitly `False`, not UNKNOWN: "not written yet" is a definite answer. Exists because `LLMInterface` and `BackendRouter` both REQUIRE cloud slots; passing `local` into them instead would make `LLMInterface`'s internal path unload the resident model after every successful turn. |
| `adapters/transport_cloud.py` | `ModelTransport` + `HealthProbe` | **New 2026-08-22.** `OpenAICompatibleTransport` + `groq_from_env` / `azure_from_env`. One class, two tiers: both providers speak `chat/completions`, so the difference is a URL, an auth header and a model name — two classes would be two copies of the same plumbing. stdlib `urllib`, no SDK. `split_prompt` is IMPORTED from `transport_ollama`, not copied, because ResLog item 14 / F-9a lock the identical-prompt property and a second copy of the mapping is how it rots (asserted by comparing what both adapters put on the wire). Body carries **only** `model`/`messages`/`stream` — no temperature, no `max_tokens`: those shape REGISTER, which is Field 2's job and the Output Gate's to verify, and an adapter choosing one would be the transport deciding how she sounds. Reasoning fields are recorded (`last_reasoning_field_present`) and never merged into `content` (it would be spoken) and never stripped (ResLog item 15). `CloudTransportError` subclasses `LLMTransportError` so every existing handler keeps working — that is what makes this additive. Keys never reach a repr, a log or an error message. |
| `adapters/audio_capture.py` … `audio_playback.py` | the seven Module 7 backends | **New 2026-08-22, one file per Protocol.** `SoundDeviceCapture`, `PorcupineWakeWord` + `HotkeyWakeWord` (v4's own named fallback), `SileroSpeakerVerification`, `SileroVAD`, `FasterWhisperSTT` + `WhisperCliSTT`, `ElevenLabsTTS` + `KokoroTTS` + `SystemSayTTS`, `CommandLinePlayback`. Every provider imported LAZILY, so the suite stays hermetic and a bring-up can ask what is available on a bare machine. `adapters/audio_pcm.py` holds the float↔int16↔WAV conversion ONCE, shared by four backends — four copies is four places for a missing clamp, and a subtly different clamp in one backend does not raise, it just makes that stage deafer. |
| `adapters/audio_stack.py` | assembly + preflight | **New.** `preflight()` reports all seven backends; `build_output_only()` gives a real pipeline whose output chain works and whose five input backends REFUSE if called. The refusing stubs are the load-bearing part: a capture returning silence, a VAD returning 0.0 and a speaker check returning 1.0 all look like ordinary operation, and `capture_turn()` would return None as if nobody had spoken. |
| `adapters/visual_window.py` | `VideoWindow` | **New 2026-08-22.** `MpvVideoWindow` (PyQt6 frameless always-on-top + libmpv, v4's `ui/aria_window.py`) and `LoggingVideoWindow` (headless). The window implements the one thing Module 10 deliberately does not — v4's "finishing the current loop cycle before switching — no jarring cuts" — by holding a PENDING target and applying it at mpv's own loop boundary. That is a DIFFERENT mechanism from the 8-second gate at a different layer: the gate decides whether a zone change is ALLOWED (Module 10), this decides when an allowed change is RENDERED. Two signals bypass the wait because Module 10 renders them ungated: a variant change (the mouth must track the voice) and entering INWARD_WAITING (a failure is not flicker). |
| `adapters/visual_bridge.py` | wiring, no Protocol | **New.** `SpeakingSignalAudio` satisfies `AudioPipelinePort` and DECORATES it, so `set_speaking` comes from the boundary Module 10's docstring names (`audio.speak()`) with **no change to `AriaDaemon`**. `set_speaking(False)` is in a `finally` — a TTS failure must not freeze her mouth open for the session. `CloudAvailabilityReporter` drives degradation from `LLMUnavailableError`, and deliberately NOT from `serving_from_local` — see the Still Open row. |
| `adapters/audio_noop.py` | `AudioPipelinePort` | `NoOpAudioPipeline`. Records calls, prints nothing (the REPL owns the terminal). Still the DEFAULT, and still correct as one. |
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
| 1 | PAD Engine | ✅ Approved | daemon/pad_engine.py, 53/53 tests passing. (Task bookkeeping CLOSED 2026-08-20: `.kiro/specs/pad-engine/tasks.md` holds 22 items — 1–21 plus an inserted 7b — and all 22 were unchecked despite complete code, as were appraisal-chain 0/21 and memory-graph 0/24, all three built outside the Kiro task loop. Every task's named artifact was verified present in code before ticking — 47 checks across the three modules, one initial miss which turned out to be a wrong grep string, not a gap. All 170 tasks across all 13 folders now read `[x]`, 0 open — measured, not estimated.) OQ1 (soul-tick cadence) carried forward as a documented build-time gap, per Resolution Log. OQ2 (PAD bounds) RESOLVED — [0,1] clamp in apply_appraisal_delta confirmed intentional (physiological homeostasis; Mehrabian/Russell bounded scales; EMA decay is the recovery path), now documented in the module docstring and the pad-engine spec and covered by test_apply_appraisal_delta_clamps_to_bounds. Residual flagged: initialize() still does not clamp an out-of-range restored snapshot. OQ3 (VALENCE_UNCERTAIN coefficient) resolved — reuses EMA_COEFFICIENT_NEGATIVE, Emergency Type Detection "default to caution" precedent. **OQ4 (restore-boundary coefficient) CLOSED 2026-08-26 — Resolution Log item 30, commit `096c618`.** This read *"narrowed, not resolved"* until then: `initialize()`'s `restored_valence` param + State Manager's `last_applied_valence` field covered the routine restart, and the residual `NotImplementedError` raise was left live. It is now unreachable from any state FILE, and **no coefficient was invented — `daemon/pad_engine.py` is byte-unchanged (asserted).** Two wiring-layer changes: `AriaDaemon._save_state` writes ONE atomic record via `StateManager.save_all` instead of three separate writes (measured 3→1), closing the crash gap that produced the half-written record; and `AriaDaemon.startup()` treats a non-baseline PAD with no valence as a half-written record and restores baseline, on item 18's precedent that an entry which cannot be trusted falls back to the spec default. PAD and valence ARE one record — PAD only leaves baseline through `apply_appraisal_delta`, which always sets a valence. **RESIDUAL, stated precisely because the obvious phrasing is backwards:** the raise is NOT the safety net for hand-edited or truncated files — those are exactly what the check handles, since `valence_from_str` returns None for an unrecognised string and item 18's clamp still yields a non-baseline PAD, so both routes hit the reset. What remains is (a) the NEUTRAL-valence raise, live code but unreachable from the wired path, and (b) the protection is **Daemon-scoped**: because `pad_engine.py` was deliberately not touched, any caller that constructs `PADEngine` and calls `initialize()` WITHOUT going through `AriaDaemon.startup()` still gets the raise. The cost is recorded rather than hidden: a reset discards the turn-before-the-crash's emotional residue, so she resumes even rather than still warm — her MEMORY is intact (every `MemoryGraph` write commits inside its own method), so she remembers the conversation without still feeling it. `AriaDaemon.pad_restore_was_reset` + a `main.py` report make the reset visible, because a silent fallback makes "resting at baseline" indistinguishable from "a corrupt file erased what she felt". Known limitation still logged: initialize() is not idempotent across repeated calls — see HANDOFF_NOTES.md, owed to Module 8; `startup()` guards it with a hard raise. |
| 2 | Needs System | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/needs_system.py` (EnergyTracker substrate + NeedsEvaluator categorical + facade) + `tests/test_needs_system.py` (47 tests) + `.kiro/specs/needs-system/{requirements,design,tasks}.md`. 4 needs strictly CATEGORICAL (enum satisfied/due/neglected, no numeric score — enum-identity at 1h vs 70h in-window proves no gradation, passes percentage test); Energy is PAD-isolated SUBSTRATE (no PADEngine import; mutator tripwire never fires; real PADEngine byte-identical before/after; k_load/k_rest flagged TODO(build-time)); windows 72h/14d/14d/60d (ResLog 7) via graph_manager evidence queries; reverts satisfied→due purely by clock; output IS the shared NeedStates contract (now in `daemon/types.py`, OQ-4 closed). F-2a/b/c/d resolved. **OQ-1 CLOSED 2026-08-20 — `neglected` is now emitted, via the TWO-WINDOW model.** The counter-based option was rejected: Addendum §3 rules it out in the same paragraph that establishes the three states (*"the state reverts on its own; nothing actively subtracts anything … not a running clock"*). Instead two windows over the SAME evidence query — `satisfied` if evidence in the need's own window, else `due` if in the next rung up, else `neglected` — which is the shape §3 uses for the one need it defines fully (*"neglected when updates have gapped for a long stretch"*: a long stretch is a wider window, not a counter). Connection 72h→14d, Growth 14d→60d, Purpose 14d→60d. Both windows are already-locked ladder values, so no window, constant, counter or storage is introduced; `graph_manager` needed no change because all four `*_evidence` methods already accept `window`. State stays a pure function of (now, graph) and NeedsEvaluator stays stateless (Req 11.2). Continuity remains TWO-valued — see Still Open. |
| 3 | Memory Graph | ✅ Implemented + tested; OQ resolutions applied + RE-AUDITED (criteria a–e PASS) | Full spec at `.kiro/specs/memory-graph/{requirements,design,tasks}.md`; code `daemon/graph_manager.py` + `tests/test_graph_manager.py` (63 tests). Coded directly (not via Kiro) at architect instruction. SQLite backend; injected embedding model. Implementation audit fixed 5 defects (D1 continuity recency, D2 retrieve edge-dedup, D3 first-of-kind = Addendum §6 Q2×Q3 profile, D4 EmotionNode-stays-vivid, D5 resolution_path→null). Architect OQ resolutions RESOLVED+implemented: OQ3 (node-embedding side-table), OQ5 (total-elapsed decay), OQ4 (retrieval pure reorder, mood PRIMARY/need SECONDARY, no coefficient), OQ1-trigger (habituation via `register_edge_firing`, edge-salience-only guard). DEFERRED (TODO-flagged): OQ1-rate. **OQ2 CLOSED 2026-08-20 — the invented medium/low `base_salience` floors are REMOVED**, per ResLog item 9's literal *"Medium/Low → no floor, decays/discards as already locked"*; `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER` is deleted and `_compute_base_salience` falls through to 0.0 for those tiers, with the Critical 0.85 / High 0.55 floors untouched. The v4 Baumeister +0.15 negative bonus still stacks "on top of whichever floor applies", which for medium/low is nothing. NOT this module: OQ6 Purpose→M2; max-5-no-evictable = raise. **Final re-audit (criteria a–e) PASS**: retrieval is stable-sort ordering only (no weighted score — proven by hard-partition test); salience/habituation never wired to PAD/appraisal (no PADEngine import); deferrals all explicitly stubbed; no numeric beyond stated placeholders. F-3b/F-3c resolved (ResLog 8/10). |
| 4 | Appraisal Chain | ✅ Implemented + tested (subagent build→audit loop) | `daemon/appraisal_chain.py` + `tests/test_appraisal_chain.py` (64 tests) + `.kiro/specs/appraisal-chain/{requirements,design,tasks}.md`. Full suite **514 passed**, verified independently. Built by subagent, independently audited (found+looped 1 medium defect — vacuous test masking a neutral-turn PAD crash — fixed so purely-neutral appraisal emits NO PAD event). Auditor APPROVED via mutation-testing: ×1.5 negativity-inflation FAILS the symmetric test (proves no weighted formula); PAD purity = 3 apply_appraisal_delta sites, no direct PAD writes, no graph._conn reach-ins. PAD delta = categorical direction {−1,0,+1} × categorical Q1 tier; coping_potential transient/emergency-gate-only. F-4a/F-4b/F-4f RESOLVED (ResLog 12/10); F-4d/F-4e = flagged build-time placeholders. **Conflict-arc 2nd close condition CLOSED 2026-08-20**: `_conflict_arc_absence_close()` runs once per turn, increments the absent counter for every open arc whose entity did not recur (including turns with no entity at all), and closes those at the threshold — categorical, the turns have passed or they have not. Absence closures write the same single `"resolved"` edge as a Q2 flip. `_CONFLICT_ARC_ABSENT_TURN_THRESHOLD` is aliased to the spec-named `_ARC_CLOSE_ABSENT_TURNS` so the threshold and its `AppraisalConfig` override cannot drift; its value moved 3→5 by architect direction (both are TODO(build-time) placeholders, so no locked value was overridden). **Resolved-edge `base_salience` now DERIVED, not invented** (2026-08-20): the deleted `poignancy_base_hint()` returned 0.35 for medium/low — the same class of invented number removed from Module 3's OQ2. v4 "Argument Buffer Mode" names the multiplicand (*the resolution is "weighted 3× higher than **the conflict itself**"*), so the edge now takes the OPENING EventNode's own `base_salience`. An arc only opens on a Q2=negative EventNode, so the Baumeister +0.15 guarantees a non-zero multiplicand at every poignancy tier (critical 1.00→3.00, high 0.70→2.10, medium/low 0.15→0.45) and ResLog item 5's 3× always has something real to act on. **VALENCE_UNCERTAIN no longer closes arcs** (2026-08-20): only POSITIVE/NEUTRAL closes, per Addendum §1's literal wording — see the Closed table for why this was not a one-line change. **New public predicate `has_distress_markers()`**: the disjunction of `_distress_marker` and `_emergency_cue_kind`, exposed for the Daemon's STEP 4b distress gate; read-only, lexical, invents no lexicon. **Connection need-pref narrowed** (2026-08-20): `_need_prefs` keys Connection on `neglected` ALONE per Addendum §3 (*"When Connection is **neglected**, Stage 1 surfaces 'We'-perspective and Connection-positive edges first"*); it previously fired on `due` too — unavoidable while Needs System could not emit `neglected`, but it applied the strong preference at the weak state. Growth/Purpose/Continuity prefs are untouched; §3 exemplifies only Connection's profile. |
| 5 | Soul Filter | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/soul_filter.py` + `daemon/moral_schema.py` (shared resource: 4 values + 7 doc-cited anti-patterns) + `tests/test_soul_filter.py` (51 tests) + `.kiro/specs/soul-filter/{requirements,design,tasks}.md`. Full suite **535 passed**. Auditor independently verified 5 philosophy proofs: no numbers/state cross the LLM boundary (Behavioral Register = PAD-vs-baseline categorical words, Relational Register = stage→NL no label, only user message crosses); Output Gate = exactly 4 checks {honesty,consistency,manipulation,care}, ZERO LLM (proven w/ RaisingLLM), no 5th check, no numeric score, verify-not-decide (Principle 27); emergency REPLACES the five fields; moral-violation → corrective retry → minimum-safe; Field 4 = HOW-clause only (memory sentinel proven never to cross). F-5a/F-5b RESOLVED; OQ-M1 anti-pattern-list closure flagged (taxonomy not invented). NeedStates/LLMClient are injected contracts (M2/M9 pending). LOW follow-up: post-emergency re-entry instruction (needs Daemon cross-turn state — defer to M8). **ENERGY_CRITICAL (&lt;20) instruction CLOSED 2026-08-20** — it is no longer a dead constant. ARCHITECT RULING: Field 5 (Constraints) carries behavioural instructions, not prohibitions only, formalising existing practice since the Energy&lt;30 row (`"do not overextend"`) already lived there. v4's soul_filter instruction table line 949 supplies the &lt;20 row — *"You are running low. Acknowledge it if it comes up naturally."* — now emitted in constraint form as `"acknowledge fatigue if it comes up naturally"`. v4's *"You are running low"* clause is deliberately NOT passed through: that half is Energy state rendered as a claim, and state never crosses (Addendum §9). MAX-3 and "always specific actions" unchanged. Verified end-to-end into Module 9's assembled prompt with no digit and no state claim. The two gates are checked MOST-SEVERE-FIRST (&lt;20 before &lt;30): every base branch yields 2 or 3 constraints so at most ONE slot is ever free, and since Energy&lt;20 implies Energy&lt;30 the milder instruction would otherwise always take it and the &lt;20 row could never be emitted at all. Both remain independent `if`s, so both fire if a future base branch leaves two slots. **Item 34 (2026-08-26, ruling 2B):** the constructor gained `derived_anti_patterns: Tuple[AntiPattern, ...] = ()` and Output Gate Check 3 passes it — the gate now reads FLOOR + DERIVED, because it checks what she is about to SAY (behaviour), while DMN Step 4's narrative gate reads the FLOOR ALONE because it checks what she is about to BELIEVE ABOUT HERSELF (identity). Still exactly FOUR checks; nothing was added to the gate, only to what Check 3 compares against. Default is empty and nothing supplies it yet, so behaviour is unchanged today. The set is held HERE rather than in `moral_schema` on purpose: that module is a shared data source, and a mutable global in it would mean two daemons share one moral schema. |
| 6 | DMN / Idle Consolidation | ✅ Implemented + tested (subagent build→audit, looped 1×) | `daemon/dmn.py` + `tests/test_dmn.py` (44 tests) + `.kiro/specs/dmn/{requirements,design,tasks}.md`. Full suite at approval **452 passed** (current 514 — see header), verified independently (dmn imports OK). Audit caught a stray-space IndentationError making the module unimportable (build report's pass-count was not reproducible) → looped → fixed. 3 headline constraints verified: DMN NEVER writes PAD (aha → `submit_aha_insight` EVENT to Appraisal Chain; live PADEngine tripwire byte-identical); relational_stage transitions CATEGORICAL (enum, ≤1 gate-step, rupture −1 floored at observing, no score); self-narrative MORAL-GATED (blocked even with no audience). Quality record from OBSERVED next-turn reaction (anti-flattery). Energy&lt;20/critical → shallow (Steps 1+4). F-6b/c/d resolved. FLAGGED for M8/integration: OQ-1 Appraisal needs `submit_aha_insight` event entry; OQ-2 Memory Graph needs highest-salience-unconnected + predictability/dependability predicates; LOW: post-rupture BONDED re-advance on pre-rupture edge (fresh-evidence unspecified). |
| 7 | Audio Pipeline | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/audio_pipeline.py` + `tests/test_audio_pipeline.py` (29 tests) + `.kiro/specs/audio-pipeline/{requirements,design,tasks}.md`. Single module (ResLog 15): input chain (capture→ring→wake→speaker≥0.75→VAD→Whisper→text) + output chain (PAD→prosody→cloud→Kokoro fallback), all backends injected Protocols. F4/barge-in ZERO internal effect (tripwire vs real PADEngine: PAD byte-identical AND never even read; each handler = one playback.stop()); never writes PAD (read-only prosody), never appraises. Prosody directions per v4 Layer 5 (arousal inverse, dominance→lower pitch); magnitudes flagged TODO(F-7-prosody). Satisfies Daemon AudioPipelinePort unchanged. |
| 8 | Daemon / Soul Tick | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | **Public surface went 2026-08-22: new read-only property `session_buffer_fullness`**, added alongside the existing observability properties (`soul_tick_count`, `attentional_focus`, `state`, `started`, …). The Daemon constructs its own `SessionBuffer`, so a caller had no handle to ask `fullness_state()` — and that is the one piece of the buffer's state a caller has business seeing, since it is what drives STEP 4's cognitive-load trigger. Read-only, categorical, NOT a decision surface, crosses no model boundary; it replaced a `daemon._session_buffer` reach-in in `main.py`. Covered by 2 tests (read-through equality, no setter, and a non-vacuous check that it tracks live turns). `daemon/aria_daemon.py` + `tests/test_daemon.py` (57 tests) + `.kiro/specs/daemon/{requirements,design,tasks}.md`. Full suite **514 passed**, verified independently. Two clocks SEPARATE (soul_tick never runs DMN; dmn_tick never decays PAD); Daemon computes no feeling (no `apply_appraisal_delta` CALL SITE in its source — the string occurs twice in the module docstring describing the constraint, so grep for `\.apply_appraisal_delta\s*\(` to verify, not the bare name); F4/barge-in ZERO internal effect (tripwire: PAD/Energy/graph/state byte-identical; each handler = one stop_playback()); HANDOFF contract exact (initialize() once + guarded, consistency_flags cleared each session, last_applied_valence round-trips); initiative keys on 'due', fires once, no-nag, enters at soul_filter skipping wake/STT. ADDITIVELY closed DMN's contract gaps (baseline preserved exactly): appraisal_chain.submit_aha_insight (aha routes through appraisal, DMN still never writes PAD), graph_manager predictability/dependability_evidence (structural booleans) + highest_salience_unconnected. F-8b resolved (ResLog 10); F-8a cadences build-time. OQ-2 initiative-on-'due' flagged. **Energy&lt;30 → Appraisal Stage 2 CLOSED 2026-08-20**, in `route_inbound_turn` STEP 4 beside the existing buffer-fullness trigger: `if self._needs.get_energy() < ENERGY_LOW: self._appraisal.submit_cognitive_load("heavy")`. Addendum §3 keeps the *"reasoning degrades below 30"* rule as an operational threshold gate, and v4's mechanism table files the "Cognitive load effect" as an "Appraisal modifier" reaching "Stage 2 appraisal + DMN depth check" — so it routes through the EXISTING `submit_cognitive_load` entry point. No new mechanism, no new number (`ENERGY_LOW` imported from its canonical home `daemon/types.py`), and Energy never crosses the module boundary: the Appraisal Chain holds no Energy handle and only the categorical load state crosses, exactly as buffer fullness does. **It SKIPS NOTHING** — Stages 0–6 all still run, the Stage-1 social-signal pre-pass (vulnerability check included) is untouched, and the emergency gate is untouched, so a tired ARIA still detects a crisis (tested). Rejected en route: an earlier proposal to skip `coping_potential` and the vulnerability check at low Energy would have disabled crisis detection outright and contradicted v4, which says emotional weighting *increases* below 30, not that perception is reduced. |
| 9 | LLM Interface | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/llm_interface.py` + `tests/test_llm_interface.py` (36 tests) + `.kiro/specs/llm-interface/{requirements,design,tasks}.md`. Full suite at approval **452 passed** (current 514 — see header). Boundary is STRUCTURAL: constructor takes only {cloud_transport, local_transport} — no graph/PAD/needs/appraisal handle. It imports exactly ONE internal module — `from daemon.soul_filter import ...` (line 74), for the instruction dataclasses plus a re-exported `LLMClient` — and nothing from graph/PAD/needs/appraisal. The guarantee is the absent CONSTRUCTOR PARAMETER, not an absent import; `soul_filter.py` does not import back, and that one-way direction is what keeps the boundary structural. Cloud + Gemma get the byte-IDENTICAL prompt via one pure assemble_prompt() (F-9a / ResLog 14, proven by object identity). NO judgment (F-9b / ResLog 15 — verbatim passthrough even for gate-failing text; retries only when Soul Filter re-calls). Satisfies Soul Filter's LLMClient contract (isinstance passes, soul_filter.py unmodified). OQ-9a..9d flagged placeholders. **NOTE:** `session_context` parameter added post-approval — ephemeral conversation transcript, not internal state. |
| 10 | Visual Layer | ✅ Implemented + tested (subagent build→audit, APPROVED 1st pass) | `daemon/visual_layer.py` (478 lines) + `tests/test_visual_layer.py` (24 tests) + `.kiro/specs/visual-layer/{requirements,design,tasks}.md`. Full suite at approval **452 passed** (current 514 — see header); all modules import OK. Only READS PAD (tripwire vs real PADEngine: writes==0, byte-identical; AST scan imports only read-only PADSnapshot, no graph/appraisal/needs/state/PyQt6/mpv); zone selection CATEGORICAL (Zone enum via boolean threshold membership, not a distance/score — 13 boundary constants + 8s stability cited to v4 lines 1145-1160/1316); talking-vs-idle follows speaking-state; cloud-fail → INWARD_WAITING; runs independent of LLM. F-10a resolved (ResLog 15). Exposed a clean VisualLayerPort — daemon UNMODIFIED. TODO(F-10-zone-precedence) flagged. |
| 12 | Session Buffer | ✅ Implemented + tested | `daemon/session_buffer.py` + `tests/test_session_buffer.py` (40 tests). **Not in original Build Plan.** Ephemeral 3-tier conversation buffer. Rule-based summarization. Meta-commands: `"rest"`, `"focus"`, `"unfocus"`. Fuzzy trigger detection with word-boundary matching. Wired into Daemon's `route_inbound_turn()` — session_context passed to Soul Filter → LLM Interface. **RESIZED + REAL TOKEN COUNTS 2026-08-25 (ResLog item 28).** Budgets are now Recent 12K / Medium 8K / Old 4K = **24K** (was 8K/6K/4K = 18K); still a SPEED ceiling, not a window ceiling — `qwen3.5:9b-mlx` reports a 262144-token window, so the window never bound this. `record_actual_tokens()` receives the provider's OWN count, fed by the Daemon from the serving transport's new `last_turn_metadata()` side-channel (Ollama `prompt_eval_count`/`eval_count`/`eval_duration`; OpenAI-compatible `usage.prompt_tokens`/`usage.completion_tokens`) — **`ModelTransport.generate()` still returns `str` and the Protocol is unchanged**, and **no tokenizer dependency was added**, so `daemon/`'s zero-dependency property holds. `fullness_state()` now reads SIZE rather than tier occupancy: percentage bands (`light` <25%, `settled` 25-50%, `heavy` 50-75%, `critical` ≥75%) off the measured count, falling back to `chars // 4` when nothing is reported. Tier occupancy was dropped because promotion COMPRESSES — a buffer with an OLD tier can hold under a third of budget, which the old logic called `heavy`. A last generation below **10.0 tok/s** bumps the band one step (saturating at `critical`): prompt-eval cost grows with the prompt while a boundary does not move. **Protected chain intact** — counts are substrate, they set a categorical band, the band is a word, and `submit_cognitive_load()` (already-sanctioned `"cognitive_load"` origin) makes the meaning; no fifth PAD origin, asserted by test. `express_pressure()` exists and is tested but is **NOT WIRED** — two architect rulings pending, see item 28. |
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
| Stage directions: marked base rate + unmarked prose | **✅ CLOSED 2026-08-26 — split into two honest statements, because one number was doing duty for both halves.** (a) **MARKED** narration (brackets, asterisks, bullets) stands at a MEASURED **3/16** on a fresh graph, with the compounding loop closed by item 31 so warm sessions no longer climb above it. (b) **UNMARKED** prose narration — *"I am sitting still. My attention is focused entirely on the words you are saying."* — has no syntax to match, so no regex reaches it without judging content, which Addendum §4's zero-LLM checklist exists to forbid. **Its rate is UNMEASURED AND UNQUANTIFIABLE — it is NOT 3/16.** That figure counted marked narration only, and attaching it to the unmarked case would put a measured number on the one thing it does not describe. BOTH halves are accepted as floors and the row closes, because no actionable route remains: the recommended moral-schema option is now MECHANICALLY blocked rather than merely unruled — a derived anti-pattern is detected by SUBSTRING markers and bracket narration is a SYNTAX with no substring, so expressing it would need either changing the schema's detection to regex (the most protected module) or inventing a bodily-narration lexicon that false-positives on true statements about her ("I pause when I'm not sure" — thinking sounds are real). See HANDOFF_NOTES on items 22/34. A model limitation, not a code bug; no mechanism invented. No code change. | **Prior status and the measurements behind it, kept as the dated record rather than deleted:** **COMPOUNDING HALF CLOSED 2026-08-26 (ResLog item 31, commit `a394825`): strip at the LLM-context boundary too.** `SessionBuffer.get_context()` now strips format markers from HER replies before assembling the prompt surface — item 25's ruling applied to a second boundary. `append_turn` still stores her reply byte-for-byte, and the printed transcript, graph, Visual Layer and TTS path all read that stored text; user text is never stripped. The pattern MOVED to `daemon/format_markers.py` and `adapters/audio_tts.py` re-exports it, because duplicating this specific regex is the exact drift item 22's near-miss already punished — one pattern, asserted by object identity. 11 tests. **Why the row stayed open at that point:** 3/16 was measured on a FRESH graph, so it is the NO-CONTEXT base rate and stripping the context cannot move it by construction. Warm sessions stop climbing above it; the base rate itself, and unmarked prose narration, still need the moral-schema ruling this row was opened for. Measured residual from the same commit: the pattern removes `<think>` TAGS but not the text between them, so a reasoning trace still re-enters — deliberately not fixed by widening the regex, because item 22's numbers are expressed in terms of this exact pattern. · **RULED 2026-08-24 (ResLog 25): strip at the audio boundary only.** `adapters/audio_tts.strip_format_markers` removes bracket narration, `*action*` lines, headings, bullets, numbered lists, `<think>` blocks and bold markers immediately before synthesis. The printed transcript, session buffer, graph and Visual Layer keep the text byte-for-byte — so this edits a RENDERING, not her response, which is why it is not the "strip it in the adapter" option that was rejected: a synthesiser is a device for pronouncing words, and "[I lean forward]" is not pronounceable. No fifth gate check; Addendum §4's four comparisons untouched. Verified against the real `say` binary. **Two things it does NOT fix, so the row stays open:** unmarked plain-prose narration ("I am sitting still. My attention is focused entirely…") carries no marker and no regex reaches it, so the 3/16 figure counted MARKED narration only; and the COMPOUNDING loop was untouched at that point, because the session buffer holds the unstripped text by design, so she stopped being heard narrating but did not stop learning to narrate — **that half is now CLOSED by item 31, which strips markers in `get_context()` before they re-enter as LLM context.** The recommended moral-schema option is NOT foreclosed and remains the only route to the unmarked case. Side effect: an all-narration reply now renders as silence on item 21's existing floor, flagged by `last_text_was_only_format_markers`. · **narrowed 2026-08-22 with numbers (ResLog item 22)**  The Output Validation Gate has no FORMAT check — its four comparisons are about content, so nothing structurally stops a stage direction reaching TTS. Field 1 carried an anti-narration clause as mitigation and **nobody had measured it.** Measured now (`tools/measure_format_markers.py`, adversarial bait, real model, fresh graph per arm): **8/16** with the original abstract wording, **12/16** on a warm session, **3/16** after Field 1 was sharpened to name the bracket syntax. So prompt mitigation cuts it by roughly two thirds and **does not close it** — the "accept mitigation as sufficient" option is closed on evidence. Three findings: the failures were all **SQUARE** brackets, a form the original clause never named; the defect **COMPOUNDS** through the session buffer (4/8 → 8/8 as her own bracketed replies re-enter as context and she imitates herself); and a near-miss — the first run reported 0/16 because the marker detector matched only round brackets, so "mitigation is sufficient" was one step from entering the Resolution Log on a detector bug. **Recommended structural option, NOT implemented:** extend the moral schema's named anti-pattern list so the existing MANIPULATION check catches it. She has no body, so "[my gaze is calm, meeting yours without pressure]" is a false claim about herself made to produce an effect — the same shape as the already-named `fake_confidence`. It adds no fifth comparison, uses the existing mechanism, routes into the existing corrective-retry ladder, and extends a list the docs already mark OQ-M1 "not a doc-certified final set". Left to the architect because the moral schema is load-bearing and also gates DMN narrative updates (Addendum §8), so a wrong entry propagates into what she can believe about herself.
| `serving_from_local` / the degradation face | **✅ CLOSED 2026-08-26 — no visual change on local fallback.** The local model is still ARIA; changing her face would signal "not fully there", which contradicts the project's core claim. The design stays coherent because the degradation face keeps a REAL trigger: `adapters/visual_bridge.py` fires on `LLMUnavailableError` (total backend failure), never on which route served a turn — so cloud-down is the ordinary resting state of a local-primary design, and only genuine unavailability shows. **SHE DOES NOT KNOW WHICH BACKEND SERVED HER, and must not be given a way to say so.** `last_route` is state, and Addendum §9's never-crosses list bars state from every field — no surface could carry it. That is also the consistent reading of this ruling: if the local voice is still her, there is nothing to report, and "I'm using my local voice" would be her narrating her own implementation, which is nearer the stage-direction failure than to presence. An operator who wants to check has `:state`, which reports `last_route` outside the boundary. Both halves the row named are now settled — ResLog 26 fixed the stale readout, and this is the design question behind it. No code change. | **Prior status and the measurements behind it, kept as the dated record rather than deleted:** **the readout is FIXED (ResLog 26, 2026-08-24); the design question behind it is not.** `serving_from_local` is gone, replaced by `LLMInterface.last_route` — categorical, five values (`no_turn_yet` / `cloud_chosen` / `cloud_unhealthy_fallback` / `local_chosen` / `no_cloud_adapter`), recorded per turn instead of read off `local.is_loaded`. The architect specified three; `local_chosen` was added because it is the ORDINARY Track A turn and none of the three can express it, and `no_turn_yet` because before the first turn any other value is a claim about something that has not happened. The substantive fix is a PRECEDENCE rule rather than the rename: an unconfigured tier raises `LLMTransportError` identically to a real outage, so `no_cloud_adapter` outranks `cloud_unhealthy_fallback` — a local-first bring-up is the intended state, not degradation. Seam is a duck-typed `is_configured` marker read via `getattr(..., True)`, so `daemon/` still imports nothing from `adapters/`. **What stays open:** whether "cloud unavailable" should drive a degradation face AT ALL, given v4 assumes cloud-primary and the design is local-primary. `visual_bridge.py` still triggers on `LLMUnavailableError` and now asserts by AST that NEITHER name is read. · **surfaced 2026-08-22 by wiring the Visual Layer**  `LLMInterface.serving_from_local` returns `self._local.is_loaded` and its docstring reads "True while the local fallback is resident (cloud is currently down)". That equivalence held under v4's Brain Structure, where the local model "loads on cloud failure, unloads on restore". Track A inverted it: `startup()` calls `ensure_local_loaded()`, Gemma is pinned resident from boot and is the DEFAULT voice, not a fallback. So it is True during entirely healthy operation, and Module 10 names it as the degradation trigger — wiring it would park her face in INWARD_WAITING permanently. `adapters/visual_bridge.py` uses `LLMUnavailableError` instead (the other trigger Module 10's docstring names, well-defined under either design) and asserts by AST that it never reads the stale one. Two things need deciding: the stale docstring, and the deeper question that v4's degradation state assumes CLOUD-PRIMARY while the current design is local-primary — under which "cloud unavailable" is the ordinary resting state and not a degradation at all.
| DMN reaches genuine idle with Energy at the floor | ✅ CLOSED 2026-08-25 — **ResLog item 29A: the third state.** Silence is NOT load. `AriaDaemon.soul_tick` now chooses between THREE Energy states instead of two: deplete under active load (`_output_pending`), **HOLD** through the pre-idle silence window (`_in_pre_idle_silence` — neither signal sent), recover at genuine idle. The architect's rationale: *"in rest situation, energy will not consume."* Energy at the moment the gate opens is now the tiredness the CONVERSATION left, not an artefact of how long she sat alone, so the depth gate reads a true number and the deep pass is reachable through a real silence — asserted with the real Needs System and the real DMN across 159 ticks of the pinned window (`pass_type=FULL`, both steps ran). **No new flag, no new number, and `dmn.py` unchanged:** the three states come off the two markers idle detection already owns (`_last_voice_input_at`, `_output_pending`) plus the pinned 8 minutes, and `_note_voice_input` is the whole abort. The RATE half (`k_load`/`k_rest`) stays a `TODO(build-time)` placeholder under "Build-time tuning constants" — it was never the structural problem. **One consequence left open deliberately:** `_output_pending` is now the only condition that sends the depletion signal, and in the synchronous REPL host no soul tick lands while it is True, so under that host Energy only holds or recovers; under a threaded daemon the depletion branch is live. Whether a turn should ALSO debit Energy per-turn is a new mechanism → Rule 1, flagged not invented. (Moved here from Still Open.) | `AriaDaemon.soul_tick` / `_in_pre_idle_silence` |
| `SileroVAD.reset()` existed and nothing called it | ✅ CLOSED 2026-08-25 — **ResLog item 29C.** `AudioPipeline._reset_vad()` clears the VAD's recurrent state once per utterance, at the start of each `_trim_to_speech` pass. Silero VAD is recurrent and the pipeline re-scores the whole 20 s snapshot every cycle, so the head of each utterance was being read in the context of the tail of the last one; `adapters/audio_vad.py` flagged the seam and deferred the decision to Module 7, which is where it belonged. A `getattr` capability PROBE, not a widened Protocol: `VADBackend` still declares one method, so `audio_stack._Absent` (every declared method REFUSES) keeps its `isinstance` conformance and needs no silently-passing `reset`. `reset()` now takes the same lock `speech_probability` does, since a caller finally exists. | `AudioPipeline._reset_vad` / `adapters/audio_vad.py` |
| Heavy-pressure latch and `"rest"` | ✅ CLOSED 2026-08-25 — **ResLog item 29B.** `SessionBuffer.clear()` now re-arms `_heavy_pressure_expressed`. Item 28 read it the other way on the literal "first heavy this **session**"; the ruling turns on what `"rest"` IS — a cognitive reset, the user asking to start fresh. A buffer that has forgotten the conversation while still remembering it already mentioned being loaded would reach heaviness again with nothing to say. Criticality still does not latch. `express_pressure()` itself is UNCHANGED and still not wired — item 28's two rulings continue to gate that, and the test asserting nothing calls it still passes. | `SessionBuffer.clear()` |
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
| Cloud adapters expose no `is_healthy()` (the last `needs-adapter` row) | ✅ CLOSED 2026-08-22 | `adapters/transport_cloud.py` — `OpenAICompatibleTransport` satisfies `ModelTransport` + `HealthProbe` for both tiers; `groq_from_env` / `azure_from_env` build them, and each returns None rather than a half-configured tier, so `main.py` falls back to `UnconfiguredTransport` and routing stays correct. Purely additive as promised: `LLMInterface` and `BackendRouter` take it in the same constructor slots unmodified (asserted), and `CloudTransportError` subclasses `LLMTransportError` so every existing handler keeps working. `is_healthy()` is layered so nothing is optimistic — no key → explicit False with no request; a recorded `LLMTransportError` inside the cooldown → False with no request (the tracker's own stated minimum for this row); otherwise a cheap `/models` probe where one is meaningful; otherwise keyed-and-not-known-to-have-failed. **The cooldown introduces no number**: it reuses `HEALTH_CACHE_TTL_SECONDS`, already the cadence at which the router re-asks. Measured with unreachable endpoints: `gemma=True groq=False azure=True` — Groq's probe failed, Azure has no meaningful listing so it rests on key-plus-failure-record, which is the documented consequence and self-corrects after one failed turn. |
| The Output Validation Gate passes an EMPTY response | ✅ CLOSED 2026-08-22 — **Resolution Log item 21** | Measured before the fix: `text=''`, `passed=True`, `failed_checks=[]`, `retried=False`, `used_minimum_safe_output=False`. The empty string was served as her reply. **The gate was right** — an empty string contradicts none of the four things §4 compares against, so it was being asked about a non-thing. Fixed by establishing that a candidate EXISTS before the four comparisons run, which is not a fifth comparison: `run_output_gate` is byte-unchanged and `GateCheck` still has exactly four members (both asserted). An empty or whitespace-only generation is re-asked ONCE with the same instruction, then drops to v4's existing MINIMUM SAFE OUTPUT floor — both mechanisms already existed. No number, no threshold, no lexicon, no content judgment; "is there text" is the same shape check the transports already make on a provider's response field. Three deliberate details: the re-ask is a plain re-ask, not a corrective retry (there is no failed check to correct); it does NOT play the reconsideration sound (that is v4's self-correction clip, and she said nothing to reconsider); and it applies on the emergency path too, where the gate bypass is untouched but distress answered with silence is the worst outcome available. Terminal case left deliberately empty — if minimum-safe also returns nothing, no fallback sentence is invented, because that would be putting words in her mouth; it is loudly labelled instead via `empty_candidates`. |
| Initiative turns produced no speech at all | ✅ CLOSED 2026-08-22 — **found by wiring audio, root-caused, fixed** | `adapters/transport_ollama.split_prompt`. Initiative is the one turn kind with no user message, so `user_message` and `session_context` were both `""` and the five fields were the whole prompt — which the mapping put in `system`, leaving Ollama's `prompt` EMPTY. **An empty `prompt` is Ollama's warm-the-model request, the one `load()` in that same adapter uses deliberately**, so it returned `{"response": ""}` as a SUCCESS. Measured 3/3 deterministic. The empty reply then passed the Output Gate untouched (see the new Still Open row) and `NoOpAudioPipeline` had nothing to reveal, so this had been silently true since Module 8 was built. Fixed by moving the instruction into `prompt` when there is no user turn — the SAME BYTES, exactly once, only the field carrying them changes — plus a structural guard refusing an all-empty request. Verified: initiative now produces a real in-register reply for the first time. Regression-pinned in `tests/test_transport_ollama.py`. |
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
| Self-continuity narrative producer | **APPROVED 2026-08-26, NOT YET BUILT** — an INTERIM producer is ruled in: read `[recent-learning:self]` observations back on the idle pass, treat a RECURRING one as the candidate (recurrence by embedding similarity against the **reused** `_REALITY_CONTRADICTION_SIM_CUTOFF`, because `is_first_of_kind` was tested and rejected — every recent-learning node shares one Q2×Q3 profile, so it would fire on the second observation ever), and **EXTEND rather than replace**, since Addendum §3 says "extends" while `update_relationship_summary` overwrites. Written as a SEQUENCE OF STATEMENTS so the belief system needs no migration. **This closes Continuity but does NOT let her speak the narrative** — §9 bars memory node contents from every field, so asked "how do you see yourself in this?" she still answers from Field 3 and the transcript; what changes is that something real is now underneath, and Continuity stops reading `due` forever. Full before/after and the belief-system handoff: see "The self-narrative producer" under Future Phase. · **was SUPERSEDED 2026-08-26** — `needs-ruling` LIFTED, direction changed (ResLog item 33). Not closed: still open, but no longer waiting on a ruling about *this* mechanism. The gap has a missing PRODUCER and a missing CONSUMER — `relationship_summary` reaches no prompt field, and Addendum §9's never-crosses list bars memory node contents — so building a producer for a value with no reader is wasted work. Architect direction: persistent self-narrative is addressed by the **Future Phase: Belief Formation System** (recorded at the end of this file), where beliefs about herself become the narrative and this closes as a side effect. **Item 3a is already done** (ResLog item 32, commit `cf0c353`): the Continuity initiative note now describes her own narrative instead of the relationship bond. **Continuity stays permanently `due`** until the belief system or some other producer exists — which is the honest state, because the need genuinely is unmet. · **observed 2026-08-22, previously only inferred** | Step 4 reported `narrative_status = no_candidate` on the real pass, and it always will: `AriaDaemon._assemble_idle_pass_input` never sets `DMNPassInput.narrative_candidate`. Module 6's design already flags generating the narrative text as an upstream concern and Module 6 correctly GATES rather than generates (moral gate + pattern-recurred gate, both verified). What is missing is the producer. Who writes "who she is becoming", and from what, is a design decision — not a wiring gap. |

**Six rows, re-counted from the table above** (`needs-ruling` 3,
`needs-runtime` 2, superseded-but-open 1, `needs-adapter` 0).

**2026-08-26 ruling pass: 9 → 6.** Three rows left this table, each because a
DECISION was made rather than because work finished — prosody (deferred until a
provider, moved to Accepted decisions), the degradation face (closed: no visual
change on local fallback), and stage directions (closed: marked 3/16 and unmarked
prose both accepted as floors). Each keeps its full measurement history in its new
home rather than being summarised away. Three further rulings offered in the same
pass were NOT taken: Purpose/max-5 (the premise did not survive the code — see that
row), the Continuity contradiction signal (right question, but it cannot fire until
a narrative producer exists), and a random self-acknowledgment trigger at Energy&lt;30
(rejected: 1-in-5 is a probability, so it fails the percentage test, and the Field 5
constraint it duplicates already exists at Energy&lt;20).

**The previous line read "Ten rows … `needs-ruling` 8" and was already wrong
against its own table** — re-counting the rows on 2026-08-26 found 9, with 7
carrying `needs-ruling`, not 10 and 8. Recorded rather than quietly corrected,
because "re-counted from the table above" is a provenance claim and it was false;
a count nobody re-derives is how this file starts lying. The narrative arithmetic
below was tracking deltas without a recount behind them.

The arithmetic, so nobody reads it as progress reversed: it started at 7; the §9
closure took it to **6**; the adapter phase surfaced the primary-entity row
(**7**); the ruling pass closed that row (**6**) and surfaced the format-guard row
(**7**); the boundary phase CLOSED the last `needs-adapter` row (**6**) and
surfaced five more (**11**); the defect pass CLOSED the empty-response row via
item 21 (**10**, though the table itself held 9 by then). **This pass:** item 31
closed the COMPOUNDING half of the stage-directions row but that row STAYS —
3/16 is the no-context base rate and stripping context cannot move it, so the
ruling it was opened for is still needed, and counting it closed would be exactly
the drift this file exists to catch. Item 33 lifted `needs-ruling` from the
self-continuity row without closing it. So `needs-ruling` 7 → **6**, total
**9** — unchanged, and honestly unchanged rather than by coincidence.

**2026-08-24 moved three rows without changing the count, which is the honest
result rather than a stall.** Resolution Log items 25, 26 and 27 ruled on the
stage-direction, `serving_from_local` and prosody rows. None of the three closes:
25 stops MARKED narration being spoken but reaches neither unmarked prose
narration nor the session-buffer compounding loop; 26 replaces the misleading
readout with a truthful one but leaves untouched the question of whether "cloud
unavailable" should change her face under a local-primary design; 27 preserves all
three of v4's directions and adds the capability probe, but no available provider
exposes timbre or pitch, so what the row needs is unchanged. Each row's text now
carries what was ruled and what remains. Counting a narrowed row as closed is how
a tracker starts lying to itself.

**The boundary phase's jump was the expected shape of that work, not a
regression.** Every one of those five rows was a question that could only be asked
by running something that had never run: the DMN's Energy state at genuine idle,
the narrative producer's absence, the empty-response hole in the gate, the prosody
dimensions with no provider, and `serving_from_local`'s changed meaning. Building
the boundary made them visible; none was created by it.

**One of the five is now closed, and it closed the way the others might.** The
empty-response row looked like it needed a fifth gate check, which Addendum §4
forbids — so it sat as `needs-ruling`. Reading §4's actual mechanism showed the
gate was RIGHT and the question was miscategorised: whether a candidate EXISTS is
not a comparison against held state, so establishing it costs no fifth check and
needed no ruling at all (item 21). The format-guard row was then narrowed the same
way — by measuring instead of assuming — and the residual now has a recommended
option rather than three untested ones (item 22).

The lesson generalises to the rows still open: **"this needs a ruling" is
sometimes "this has not been read carefully enough yet", and sometimes "this has
not been measured yet."** Both were true here.

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

## Boundary phase (2026-08-22) — the last eight empty Protocols are filled

Protocol arithmetic, re-measured by AST rather than counted by hand: **21
Protocols declared in `daemon/`.** Eight of them were external boundaries with no
implementation anywhere — the seven Module 7 audio backends plus `VideoWindow`.
All eight now have one, so **no declared Protocol in this project is empty.**

```
.venv/bin/python -c "import ast,pathlib; print(sum(
  isinstance(n, ast.ClassDef) and any(getattr(b,'id',None)=='Protocol' for b in n.bases)
  for p in pathlib.Path('daemon').glob('*.py') for n in ast.walk(ast.parse(p.read_text()))))"
```

"Filled" is not the same as "runs here", and the difference is per-backend:

| Boundary | Implementation | Runs on this machine |
|---|---|---|
| `ModelTransport` (Groq, Azure/Kimi) | `OpenAICompatibleTransport` | yes, with a key; verified against unreachable endpoints only — no key was used |
| `TTSBackend` | `SystemSayTTS` / `KokoroTTS` / `ElevenLabsTTS` | **yes, verified end to end** |
| `PlaybackBackend` | `CommandLinePlayback` (afplay) | **yes, verified end to end, including F4's stop** |
| `VideoWindow` | `LoggingVideoWindow` | **yes** — the whole zone machinery was driven through it |
| `VideoWindow` | `MpvVideoWindow` | no: PyQt6 and libmpv absent, no loop files |
| `CaptureBackend` | `SoundDeviceCapture` | no: `sounddevice` absent, and no microphone to verify against |
| `WakeWordBackend` | `PorcupineWakeWord` | no: `pvporcupine` absent. `HotkeyWakeWord` (v4's own named fallback) needs nothing and is tested |
| `SpeakerVerificationBackend` | `SileroSpeakerVerification` | no: `torch` absent, no voiceprint |
| `VADBackend` | `SileroVAD` | no: `onnxruntime` absent, no model file |
| `STTBackend` | `FasterWhisperSTT` / `WhisperCliSTT` | no: neither runtime installed |

**Three real defects were found by wiring these**, all of which had been silently
true and none of which any test caught: initiative produced no speech at all (now
FIXED — see the Closed table), the Output Gate passes an empty response, and
format markers are spoken aloud. That is the argument for the phase: 547 soul tests
were green over code with a boundary that had never been connected to anything.

**The 547 soul-layer tests did not change.** Five new adapter families, three
defects closed, and not one soul test needed editing — which is what the
one-way dependency arrow was for.

---

## Defect pass (2026-08-22) — the three findings from wiring, solved or narrowed

Resolution Log **items 21, 22 and 23**. Suite 726 → 747; the soul layer moved for
the first time this week, deliberately and in one place.

| Defect | Outcome |
|---|---|
| Initiative produced no speech | **FIXED** (boundary phase). Ollama's empty-`prompt` warm request. |
| Output Gate passes an empty response | **FIXED** — item 21. Not a fifth check: a non-candidate never reaches the comparisons. |
| Format markers reach spoken output | **NARROWED with numbers** — item 22. 8/16 → 3/16. Residual is an open ruling with a recommendation. |

### The empty response was a category error, not a missing check

It sat as `needs-ruling` because the obvious fix — "check the candidate is not
empty" — looked like a fifth Output Gate comparison, and Addendum §4 fixes the set
at four.

Reading §4's mechanism dissolved that. Each of the four comparisons asks *does this
candidate contradict something Aria already holds?* — graph facts,
`relational_stage`, the anti-pattern list, this turn's salience. An empty string
contradicts none of them, so **the gate's `passed=True` was correct.** It was being
asked about a non-thing.

So the fix establishes that a candidate exists *before* the comparisons run, and
that is not one of them. `run_output_gate` is byte-unchanged; `GateCheck` still has
exactly four members; both are asserted by tests, including one that greps the
gate's own source for emptiness vocabulary. A generation returning nothing is
re-asked once, then drops to v4's existing minimum-safe floor — **two mechanisms
that already existed**, with no number, threshold, lexicon or content judgment
added.

### The format guard: measured, and the measurement inverted twice

The row had sat on an untested assumption: Field 1's anti-narration clause was
treated as adequate mitigation, and nobody had run it.

| Arm | Turns carrying a stage direction |
|---|---|
| Original abstract clause | **8/16** (**12/16** warm session) |
| Sharpened — names the syntax | **3/16** (shipped; reproduced) |

Three things came out of it:

1. **Prompt mitigation cuts it by ~⅔ and does not close it.** "Accept mitigation
   as sufficient" is now closed on evidence.
2. **Every failure was SQUARE brackets** — `[I lean forward just a fraction, my
   gaze calm]` — a form the original clause never named. Field 1 now names all
   three bracket conventions and states *"You have no body to describe"* as fact,
   because the brackets were claiming a posture and a gaze she does not have.
3. **It COMPOUNDS through the session buffer.** 4/8 → 8/8 across two rounds: her
   own bracketed replies re-enter as session context and she imitates herself.

**The near-miss is the part worth keeping.** The first run reported **0/16** and
read as the clause holding. It was a detector bug — the marker regex matched only
round brackets. Printing the replies showed square-bracket narration in half of
them. *"Prompt-level mitigation is sufficient"* was one step from entering the
Resolution Log as a measured finding, on the strength of a false negative. The
detector hole is now pinned by tests using the model's real output verbatim, and
the honest limit is pinned too: narration with **no** marker at all — *"I am
sitting still. My attention is focused entirely on the words you are saying."* — is
not detectable without judging content, and is recorded as a known gap.

### And one citation that was never checked

Deriving items 21 and 22 meant reading Addendum §4 and ResLog item 15 at the
source. **Item 15 does not contain the verbatim-passthrough rule** that three
documents and six docstrings attributed to it — it resolves three *ownership*
questions. The rule is real (F-9b / LLM Interface Req 5, structurally enforced) and
nothing architectural changes; the attribution was wrong, and it was load-bearing
in the rejection of an adapter-side format fix. Item 23 records it. A citation
repeated across three documents is not evidence that anyone checked it.

---

## The DMN idle pass, observed (2026-08-22) — Module 6's first execution

44 tests had passed for weeks and the module had never executed once against a
real graph with real embeddings. Reproduce with:

```
.venv/bin/python tools/observe_dmn_pass.py            # the real 8 minutes
.venv/bin/python tools/observe_dmn_pass.py --window-minutes 0.5   # plumbing only
```

Nothing is faked. Real clock, real graph, real embeddings, real local voice, real
turns; `main.Wiring` itself rather than a reconstruction of it. It writes to a
SEPARATE runtime root by default, because the harness turns are not things anyone
said to her.

### The finding: she arrives at her own consolidation pass too tired to finish it

At the real, spec-pinned 8-minute window the pass ran **SHALLOW** —
`step2_ran=False`, `step3_ran=False`. Graph-connection formation and uncertainty
revisiting did not run.

Not a bug in Module 6. **Energy fell 81.5 → 0.1 during the eight minutes of
silence that were supposed to earn the pass:**

| elapsed | soul ticks | Energy |
|---:|---:|---:|
| 0 s | 0 | 81.5 |
| 60 s | 20 | 29.2 |
| 120 s | 40 | 10.5 |
| 241 s | 80 | 1.3 |
| 479 s (idle opens) | 160 | 0.1 |

`_idle_conditions_met` is False for the whole PRE-window period, so every one of
those 160 soul ticks called `on_soul_tick()` — active-load depletion — and
`on_idle_recovery()` was never reached. Energy recovery begins at the same instant
idle is declared, which is the same instant the DMN fires. Then `run_idle_pass`
reads Energy < 20 and chooses SHALLOW.

**The deep half demonstrably works.** With a 30-second window the same harness
produced `pass_type=full`, both steps ran, 3 edges were written and 3 nodes newly
connected. It cannot be reached through a genuine 8-minute silence.

Two separable questions, and only one is tuning:

1. **RATE** — `k_load`/`k_rest` are flagged `TODO(build-time)` placeholders
   (F-2a/F-2b) and have never had data. At a 3-second tick the load coefficient
   drains ~95 Energy in under four minutes. This is the first real measurement for
   them.
2. **STRUCTURE** — whether "silent, but not yet for 8 minutes" should count as
   active load at all. That is not a coefficient, it is a question about what idle
   means, and answering it needs a third state or a changed gate. **Rule 1:
   flagged, not invented.** New `needs-ruling` row.

**RULED 2026-08-25 — ResLog item 29A. The structural half is closed; the rate half
is not, and did not need to be.** Silence is NOT load. The third state exists:
Energy is HELD through the pre-idle window, depletes only under active load, and
recovers at genuine idle — *"in rest situation, energy will not consume."* The table
above now reads 81.5 at every row through 479 s, and `run_idle_pass` chooses FULL.
`k_load`/`k_rest` keep their `TODO(build-time)` status: at a 3-second tick the load
coefficient still drains ~95 Energy in under four minutes, but that only ever
mattered because silence was being counted as load. See the Closed table for the
one consequence deliberately left open (`_output_pending` is now the only condition
that sends the depletion signal).

### Also observed, first time each

| Observed | Means |
|---|---|
| Step 1 promoted 2 meta-observation nodes; `event_nodes` 5 → 7 | Step 1 works against real appraised turns |
| `quality_appended = ['poorly', 'responded_well']` | the anti-flattery grade really is read from the OBSERVED next turn |
| Step 4 `narrative_status = no_candidate` | **the self-continuity narrative can never be written as wired** — `_assemble_idle_pass_input` never sets `narrative_candidate`. Module 6's design already flags generating the text as an upstream concern; this is that flag, observed rather than inferred |
| no `NotImplementedError` across 160 real soul ticks | the PAD OQ4 residual stayed unreached, because the HANDOFF contract restored a valence. See the OQ4 section below |
| Energy idle-recovery path exercised for the first time | nothing had ever driven the clocks through a real silence |

---

## PAD Engine OQ4 residual — counted and characterised (2026-08-22), CLOSED (2026-08-26)

> **CLOSED 2026-08-26 — Resolution Log item 30, commit `096c618`.** The section
> below is the 2026-08-22 characterisation and is kept as the dated record of
> what was measured before the fix; it is no longer the current state. What
> changed: the reachable raise is no longer reachable from any state FILE,
> because `AriaDaemon._save_state` now writes ONE atomic record instead of three
> (closing the crash gap) and `AriaDaemon.startup()` treats a non-baseline PAD
> with no valence as a half-written record and restores baseline (item 18's
> precedent). **No coefficient was invented and `pad_engine.py` is
> byte-unchanged** — both raises are still in the file, still exactly two, still
> asserted. What the raise now protects against is narrower than the obvious
> phrasing suggests: NOT hand-edited or truncated files, which the check handles,
> but the NEUTRAL branch plus any caller that reaches `PADEngine.initialize()`
> without going through `AriaDaemon.startup()`. The fix is Daemon-scoped by
> design. See the Module 1 row for the full disposition, and note the test count
> below has moved 11 → 17.

Carried on the readiness list as "5 NotImplementedError in pad_engine.py,
re-counted. Code flag, never tracker-tracked." Both halves of that needed
correcting, and neither was resolved in that pass — closing OQ4 was an architect
decision and inventing a decay coefficient is exactly what Rule 1 forbids. Item
30 closed it without inventing one.

**5 is the occurrence count. There are exactly TWO raise statements**, both in
`on_soul_tick`; the other three occurrences are the docstring explaining those
two. Measured by AST, not grep, and pinned by
`tests/test_pad_restore_boundary.py` (11 tests at the time, **17** since item
30). No other module in `daemon/` raises `NotImplementedError` at all.

**The two are not equally real:**

| Raise | Status |
|---|---|
| NEUTRAL valence (line 334) | **Live code, unreachable from the wired path.** Seven neutral turns through the real Appraisal Chain and real graph leave `_last_applied_valence` as None every time: a purely-neutral appraisal builds an all-zero `PADDelta` that `_apply_delta` never applies, so the branch has no route in from `appraise()`. Forcing the state directly does raise, so it is not dead. This is also why 160 consecutive real soul ticks never hit it. |
| Restore boundary, `None` + non-baseline PAD (line 343) | **Reachable, and reproduced end to end.** Write a state file with PAD off baseline and no `last_applied_valence`, and `startup()` succeeds while the FIRST `soul_tick()` raises — in the REPL, a traceback several frames from the cause. |

**Why it is nonetheless narrow.** The HANDOFF contract has `startup()` restore the
persisted valence and hand it to `initialize()`, and the write cadence is every
turn, so the field is one turn behind at worst. A first-ever run cannot hit it
either — it starts at baseline, and the baseline case is a documented no-op rather
than a raise. The residual is a crash between an appraisal delta and the next
save: a one-turn window.

**What changed in code: a warning, not a fix.** `main.py` now detects the
condition at startup and names it, the operator remedy, and the fact that neither
remedy is a fix. No coefficient is chosen, the raise is not caught, and
`pad_engine.py` is byte-unchanged.

---

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
| Prosody: pitch/timbre with no provider (v4 Layer 5) | **ACCEPTED DECISION 2026-08-26 — defer until a provider offers real pitch/timbre control.** Approximating the two unreachable directions by mapping them onto adjacent knobs (ElevenLabs `stability`/`style`) is REJECTED: those control something else, so PAD would *appear* to reach the voice while doing something unrelated to what v4 specifies, and a voice that sounds robotic or comical undermines "a real presence" more than a flat one does. **PRECISION, because the obvious summary of this decision is wrong twice:** it is TWO of the three directions that are dormant, not three — `length_scale` (Arousal → speed, INVERSE) IS wired and verified at 156 wpm calm → 208 wpm alert, and it is not an approximation but the REAL mapping, since speed is the same physical quantity in v4 and in every provider. The dormant two are `noise_scale` (Pleasure → warmth/resonance) and `pitch_shift` (Dominance → lower, more grounded) — warmth and groundedness, NOT "urgency" or "uncertainty", which are not prosody directions in v4 at all. All three stay COMPUTED every turn so a provider limitation never becomes a spec change, and ResLog 27's capability probe decides wiring per backend. No code change. | **Prior status and the measurements behind it, kept as the dated record rather than deleted:** **narrowed 2026-08-24 by ResLog 27; needed a provider or an approximation ruling — this row IS that ruling.** All three directions stay COMPUTED (dormant ≠ deleted, so a provider limitation cannot become a spec change), and a capability PROBE now decides wiring: `PROSODY_DIRECTIONS` holds the locked set, each backend declares which fields it cannot express, and `prosody_support` + `unmapped_prosody` are both derived from that one declaration so they cannot disagree. An unrecognised field name is refused at construction, because accepting `"pitch_shft"` would silently report support for `pitch_shift`. `main.py` reads the probe instead of hard-coding "only length_scale". Nothing new was wired — no available backend exposes timbre or pitch — so what the row needs is unchanged. · **surfaced 2026-08-22 by building TTS**  v4 Layer 5 locks three directions — Pleasure→`noise_scale` (warmth), Arousal→`length_scale` (speed, inverse), Dominance→`pitch_shift` (lower, grounded). **Only `length_scale` has a counterpart in any available provider.** ElevenLabs, Kokoro and `say` all expose a speed control, which is the same physical quantity, so mapping it is a unit conversion (verified: 156 wpm calm → 208 wpm alert, direction holds). None exposes timbre or pitch. Mapping them onto adjacent knobs — ElevenLabs `stability`/`style` — was REJECTED: those control something else, the mapping would be invented, and it would make PAD appear to reach the voice while doing something unrelated to what v4 specifies. Each backend reports `unmapped_prosody` instead. Closing it needs either a provider with real pitch/timbre control or a ruling that the directions may be approximated.
| Empty graph reports NEGLECTED on first run | ✅ ACCEPTED 2026-08-20 — not special-cased | A brand-new install has no qualifying evidence in the near OR far window, so Connection/Growth/Purpose read `neglected` rather than `due`. It is exactly what Addendum §3's rule yields (*"determined by whether qualifying evidence exists in the graph within a recency window"* — none does), and it self-corrects on the first qualifying turn, since Connection needs only one Q1 medium-or-above event. Mostly invisible: `_maybe_initiate` already treated `due` and `neglected` alike so first-run initiative is unchanged, and the only new effect is the We-perspective retrieval preference firing on a graph with nothing to reorder. Suppressing it would need a "has she ever had evidence" distinction the spec does not define. Recorded in the test docstring; needs a ruling only if `due` is wanted for a never-had-evidence graph. |
| Three spec folders are DERIVED FROM CODE, not authored ahead of it | ✅ ACCEPTED 2026-08-20 — folder gap closed; authorship gap is permanent | 2026-08-20: State Manager (11), Session Buffer (12) and BackendRouter (13) now have `.kiro/specs/<module>/design.md`, so all thirteen modules have a folder and a reviewer no longer has to wonder whether they were ever specified. **But each carries a STATUS banner saying it was written from the shipped code and is not a source of scope.** The other ten folders were authored BEFORE their module and drove it; these three cannot detect drift, because diffing code against a document derived from that code can only ever succeed. Each one ends with a "what a real spec would still need" section listing the decisions an architect-authored spec would have to settle — for Session Buffer that includes the genuinely architectural §9 tension, not just tuning. No `requirements.md` was written for any of the three: SHALL statements reverse-engineered from an implementation would assert authority the documents do not have. Every factual claim in all three was verified against code before writing (13 checks). |
| Distress gate is deliberately broad | ✅ ACCEPTED 2026-08-20 | `_DISTRESS_MIN_MARKERS = 1`, so ONE absolutist word suppresses a cloud proposal. Measured false positives: *"I never use the cloud, explain why it matters"*, *"everyone says this algorithm is faster, compare them"*, *"this always works, analyze the tradeoffs"*, *"nothing beats a good refactor, explain why"*. Cost is a missed escalation prompt — the turn is answered locally instead, nothing breaks. Benefit is that no distressed turn slips through. A stricter threshold for this gate alone would be a new number the spec does not state, so the spec'd value is reused (Rule 1). Architect decision 2026-08-20: keep it broad; presence beats routing. Revisit only if false suppressions become annoying in real use. |
| `has_distress_markers` is new public API on Module 4 | ✅ ACCEPTED 2026-08-20 | Module 4's public surface went 3 → 4 methods (`appraise`, `has_distress_markers`, `submit_aha_insight`, `submit_cognitive_load`). It is a read-only lexical predicate — no LLM, no embedding, no graph, no PAD, no mutation — and exactly the disjunction of two checks the module already owned. The alternative was the Daemon calling two privates across a module boundary. Architect decision 2026-08-20: keep it public, so the Daemon depends on an interface rather than internals. Passes the existing public-surface boundary test. |
| ResLog item 5's 3× is representational only | ✅ ACCEPTED 2026-08-20 — architect ruling | The `"resolved"` edge's 3× salience weighting is now spec-faithfully derived (see Closed table), but NO code path reads edge `salience` for any decision. `resolved_edge_exists()` — the Invested→Bonded faith gate, item 5's own named consumer — selects on `edge_type` + `created` only. `retrieve()` orders edges by incidence and by edge VALENCE (mood congruence), never by salience. The only readers are `adjust_salience` (a setter) and `register_edge_firing`'s habituation clamp. So the weighting is recorded in the row and acts on nothing. If item 5's 3× is meant to *do* something — surface the resolution preferentially, feed the faith gate — that consumer does not exist yet. |
| **Local voice is `qwen3.5:9b-mlx`; `SPEC_MODEL` still cites v4's E2B** | ✅ ACCEPTED 2026-08-24 — architect ruling, **ResLog 24** (supersedes the 08-22 row below, which is kept because its reasoning still applies to the tag it rejected) | `DEFAULT_MODEL = qwen3.5:9b-mlx` (8.9 GB). Verified on the machine: 262144-token context, `vision` and `tools` capabilities. The ~13–14 tok/s figure is **architect-supplied and not reproduced in-project** — no harness run is recorded against this tag. `SPEC_MODEL` stays `gemma4:e2b-it-qat` because it CITES v4's RAM budget table rather than expressing a preference, so the two constants now differ by design. Two risks recorded, neither closed: the tag reports a `thinking` capability, and item 22 warned a model emitting reasoning traces would have them SPOKEN (ResLog 25 now strips `<think>` blocks on the audio path, but not an untagged prose preamble); and it reports no `audio` capability where E2B did, which costs nothing today because STT/TTS are separate adapters. Also corrected here: the claim that Addendum §1 forbids a non-Gemma voice does NOT hold — §1 concerns the EMBEDDING model. The row below is SUPERSEDED as the current state but retained in full, because its measured reasoning still applies to the tag it rejected. |
| **Superseded 2026-08-24 — was: local voice is `gemma4:e2b-it-qat`, v4's own model, arrived at by measurement** | ✅ ACCEPTED 2026-08-22 — architect ruling after a same-day reversal | `DEFAULT_MODEL == SPEC_MODEL == gemma4:e2b-it-qat` (4.3 GB), the Ollama tag for v4's "Gemma 4 E2B QAT". **It was briefly `gemma4:12b-it-qat` and the reasoning behind that was mine and was wrong** — recorded rather than quietly undone, because it was plausible and someone will reconstruct it. The argument ran: the local model's job is narrow (render prose in a register, honour Field 5) so reasoning is not worth local memory, but instruction ADHERENCE improves from ~4B to ~12B, and QAT makes 12B cost LESS resident memory (7.2 GB) than a naively-quantized 4B-effective build (`e4b-it-q4_K_M`, 9.6 GB). The memory arithmetic was right. It never measured **tokens per second** or **whether adherence actually improves**, and both went the other way: 12b ran **10–13× slower** (54–162 s/turn vs 2–12 s, rising with context), scored **identically** on every gate metric, and on the flattery-bait turn was **worse** — it reflected the feeling and never engaged the question, arguably the deflection Field 5 had just prohibited. Full numbers in "Local model latency and register measurements" below. **Why the argument failed, since the premise was right and the conclusion backwards:** the five-field boundary makes the task SHORT as well as narrow, and a well-tuned small instruct model is already at ceiling there — so the same boundary that makes the job narrow is what makes a bigger model not pay for itself. `DEFAULT_MODEL` and `SPEC_MODEL` stay as two names for one value because `resolve_model`'s ladder is written in terms of "the configured default" versus "what v4 names", and those are only coincidentally equal today. There is no deviation from v4 to record any more. |
| `_VULNERABILITY_SIM_CUTOFF` = 0.25, was 0.6 | ✅ ACCEPTED 2026-08-22 — architect ruling on measured evidence | At 0.6, **nine of twelve genuine disclosures did not fire** — a 75% miss rate on the signal the check exists to detect. 0.25 is Pareto-optimal on the 37-sentence probe set (2/25 false positives, 0/12 missed; 0.20 has 3× the false positives at the same recall, 0.30 has the same false positives and misses two). Tie against the other defensible pick, 0.35, broken by the project's own accepted precedent for this asymmetry — the distress gate is deliberately broad because "presence beats routing". **The cost was traced in full and it is more than tone:** firing raises Q1 to HIGH, and with a non-neutral Q2 plus needs implications plus `is_first_of_kind` that reaches poignancy CRITICAL → `base_salience` 0.85, which per ResLog item 9 "resists vivid→present indefinitely — stays word-for-word forever" → plus a forced early DMN partial pass writing a second node. So a false positive can write a PERMANENT memory of a mundane turn. What bounds it is `is_first_of_kind`: the CRITICAL path only opens the first time a given (Q2 × Q3) profile appears for that entity, so the never-fading inflation is a handful of nodes over a relationship, not a fraction of every turn; later false positives land at HIGH (0.55 floor). The full chain is documented at the constant. Injectable as `AppraisalConfig.vulnerability_sim_cutoff`. 0.35 (0 false positives, 2/12 missed) is the one-line alternative if permanent-memory inflation proves worse in use than missed disclosures. |
| Primary (user) entity id persists via StateManager | ✅ ACCEPTED 2026-08-22 — architect ruling; closed the `needs-ruling` row | `StateManager.load_primary_entity_id` / `save_primary_entity_id`, an exact mirror of the self-entity methods ResLog §2 established, so no new mechanism SHAPE was introduced. Chosen over the two alternatives: a by-name graph lookup was rejected because `EntityNode` carries an `aliases` field by design, so names are explicitly not identity and a rename or a second person with the same name either collides or orphans a history; explicit enrolment is probably the real long-term answer — v4's `aria_state.json` listing already contains `voiceprint_enrolled` and Module 7 carries speaker verification at 0.75 — but it needs audio, which is not built, and **the StateManager key is forward-compatible with it**: enrolment should SET this key rather than replace the mechanism, since binding a voiceprint to an EntityNode id is exactly what these two methods store. **Creation stays in the wiring layer, deliberately asymmetric with the self entity.** ResLog §2 warrants the Daemon auto-creating a node for ARIA — she is always present, nothing to decide. Who the USER is has no such warrant, so `AriaDaemon.startup()` was left untouched and `main.py` resolves the id on a three-rung ladder (explicit `--user-entity-id` → persisted → create and persist immediately). 7 tests, including that the two keys never alias — if they did, every self-referential DMN narrative would be written about the user. |
| Persona Anchor rules out stage directions | ✅ ACCEPTED 2026-08-22 — architect ruling | A real local model opened a reply with `(Aria listens, her presence steady and calm...)`. TTS would read that aloud, and it is a FORMAT defect the Output Gate structurally cannot catch — its four checks are honesty / consistency / manipulation / care, none about form. Fixed in **Field 1**, not Field 5: Field 5 is where prohibitions live (ResLog item 16) but is capped at MAX 3 with every slot already contested by the Energy gate and the uncertainty rows, so spending one permanently on formatting would crowd out a moral constraint on the turns that need one. Stripping it in the adapter was rejected outright — that is the transport judging content. *(Two later corrections to this cell: the passthrough rule is F-9b / Req 5, not ResLog item 15, which resolves gate OWNERSHIP — see ResLog 23. And **ResLog 25 narrowed the rejection on 2026-08-24**: editing her RESPONSE stays rejected, but stripping markers from the RENDERING handed to a speech synthesiser is now permitted, because that is a presentation decision rather than a judgment about what she said. Field 1's clause remains, and remains measured at 3/16 residual — this row's reasoning for choosing Field 1 over Field 5 is unaffected.)* **Phrased as a positive VOICE property, not a prohibition**, which is what keeps it inside §9's definition of Field 1 ("who Aria is, her values, her voice"): the sentence it extends already ended "a real presence, not a persona", and a stage direction is precisely performing a persona from outside. So it sharpens a claim the anchor was already making. Field 1 is fixed and hardcoded, so it costs no per-turn budget. 3 tests, including that the clause actually reaches the assembled prompt and that Field 1's no-digits / no-state invariants still hold. |
| Adapters live in `adapters/`, not `daemon/` | ✅ ACCEPTED 2026-08-22 — architect confirmation | The dependency arrow points one way and nothing in `daemon/` imports `adapters`. This is enforcement by absence of surface, the same pattern as `LLMInterface` taking only transports and `needs_system` holding no PADEngine: if an adapter lived in `daemon/`, then `from daemon.transport_ollama import ...` becomes POSSIBLE from a soul module and eventually someone does it. Keeps `daemon/` importable with zero external dependencies, which is what makes the 535 soul tests hermetic and 0.75s. v4's Conv.6 directory listing puts everything under `daemon/`, but that listing is already superseded by the shipped code — `llm_manager.py`, `stt_engine.py`, `tts_manager.py`, `interrupt_handler.py` and `tcp_server.py` do not exist — so this is a build-layout choice, not a spec deviation. |
| `UnconfiguredTransport` holds the two cloud slots | ✅ ACCEPTED 2026-08-22 — architect confirmation | Not scope creep: `LLMInterface.__init__` and `BackendRouter.__init__` both require cloud transports with no defaults, so nothing constructs without something in them. The alternative — passing the local transport into the cloud slot — is actively harmful, because `LLMInterface`'s internal path unloads `local` whenever `cloud` succeeds, so one object in both slots evicts the resident model after every successful turn. It reports `is_healthy() == False` **explicitly, not UNKNOWN**: FLAG B already made UNKNOWN non-optimistic so routing behaves the same either way, but "no adapter is written" is a definite answer and reporting a definite thing as unknown throws information away. Consequence, which is the intended design rather than a degraded mode: no tier-2 proposal ever fires, Groq is skipped, every turn is served by Gemma. |
| `all-minilm` is the embedding model | ✅ ACCEPTED 2026-08-22 — selected by elimination, not preference | Addendum §1 requires "encoder-only, no text-generation capability, on the order of tens of megabytes. Not Gemma." `all-minilm` is **45 MB measured**, 384-dim, encoder-only. The alternatives fail the stated size constraint outright: `nomic-embed-text` 274 MB, `embeddinggemma` ~620 MB. So §1 selects this model rather than anyone choosing it. **The caveat that follows from the calibration data:** 384-dim MiniLM cannot separate "tired about a thing" from "tired of carrying something alone", which is why the vulnerability bands overlap. If clean separation is wanted, the lever is a bigger embedding — and that means relaxing §1's size constraint, which is a ruling, not a swap. Note also that changing this model invalidates every stored vector in `node_embeddings` and `edge_firing_contexts`; regenerate rather than mix. |
| Graph DB at `~/.local/aria/graph.db` | ✅ ACCEPTED 2026-08-22 — no source document names a path | v4's runtime listing gives `~/.local/aria/` as the data root and `state/` as StateManager's directory, with `models/` beside it — but names no file for the graph at all. Sitting beside `state/` respects both halves of what v4 does lock. Keeping it OUT of `state/` is the load-bearing part: StateManager owns that directory, the graph is not StateManager's, and `tests/test_state_manager.py` encodes exactly that boundary by asserting the state dir holds precisely its two JSON files. Revisit only if SQLite WAL is enabled, which would add `-wal` / `-shm` siblings at the root. `.gitignore` already excludes `*.db`. |
| StateManager write cadence is every turn | ✅ ACCEPTED 2026-08-22 — the knob was removed rather than set | Resolution Log item 4 calls the write cadence a build-time tuning flag, so a value had to be chosen. Every turn is the choice that needs no defending: two small atomic JSON writes at conversational pace is a handful of writes a minute, and nothing is ever pending when a crash happens. Batching would buy nothing measurable and would leave a number to justify — so `main.py` carries no `SAVE_EVERY_TURNS` constant at all. Worth knowing: a crash never loses MEMORY regardless, because every `MemoryGraph` write commits inside its own method. The cadence protects PAD, Energy and `last_applied_valence` only. |
| Audio and visual are OPT-IN; the no-op stays the default | ✅ ACCEPTED 2026-08-22 | `--audio` and `--visual` / `--visual-headless`. Both layers are LEAVES — nothing downstream reads what they did, `speak()` and `play_loop()` return None, and no soul state depends on the result — which is the reasoning `audio_noop.py` already sets out, so substituting them changes no behaviour inside the system. Making either the default would mean every text bring-up starts talking out loud and opening a window. It also matters that `--audio` is the switch that turns the format-guard row from cosmetic into audible, so it should be a decision someone makes rather than a default they inherit. |
| macOS `say` + `afplay` substitute for Kokoro and `pw-play` | ✅ ACCEPTED 2026-08-22 — recorded substitution | v4 names Kokoro for the local TTS slot and `pw-play` for playback. Neither exists on the dev machine and both substitutes are legitimate: v4 states directly that "The TTS is a hot-swappable tool. Aria is not," `pw-play` is itself a command-line player so a subprocess is the shape v4 describes rather than a shortcut around one, and nothing downstream reads which renderer or player was used. What the substitution BUYS is the only thing no other backend here has — it works with zero installs, so the output chain was verified end to end rather than only unit-tested. What it COSTS is voice quality and two prosody dimensions, which is why it holds the FALLBACK slot and not the primary. `CommandLinePlayback.describe()` names the player actually chosen and flags it when it is not `pw-play`, so the substitution is visible at startup rather than inferable. |
| The Visual Layer is wired by decorating the audio port, not by changing the Daemon | ✅ ACCEPTED 2026-08-22 | `AriaDaemon` takes no visual parameter and still does not (asserted by a test on its constructor signature). Module 10's own flag disposition calls the driver-loop and signal wiring "top-of-tree BUILD-TIME wiring, not this module's concern", and names the seam: "the output-pending boundary around `audio.speak()` -> set_speaking". So `SpeakingSignalAudio` satisfies `AudioPipelinePort`, wraps whatever real port is in use, and reports the boundary onward — the Daemon cannot tell the difference and no approved constructor moved. `set_speaking(False)` sits in a `finally`, which is load-bearing: a TTS failure would otherwise freeze her mouth open for the rest of the session, and the observed empty-text crash was exactly that shape. Thinking sounds deliberately do NOT raise the talking variant — a thinking sound plays while she is not talking. |
| Empty TTS text renders silence and is counted, rather than raising | ✅ ACCEPTED 2026-08-22 — the first answer was wrong and is recorded | Raising `TTSUnavailable` on empty text was the initial implementation. Observed consequence: `AudioPipeline._synthesize_with_fallback` caught the primary's failure, tried the fallback, the fallback raised for the same reason — the INPUT, not the provider — and the exception propagated out of `speak()` → `_route_initiative` → `soul_tick()`. A no-content turn became a crashed soul tick. `TTSUnavailable` was also the wrong signal: it means "try the other renderer", and no renderer helps with empty input. So a zero-frame WAV is returned (the honest rendering of no words: no sound) and `empty_text_requests` records it — the counter is the point, because the alternative to a crash must not be a silence nobody can see. The underlying empty response is a separate `needs-ruling` row. |
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
| Moral schema = 4 values + a 7-entry immutable FLOOR, plus a derived layer that is a PARAMETER (item 34) | 7 `AntiPattern(` instances in `CORE_ANTI_PATTERNS`; `CORE_ANTI_PATTERNS is NAMED_ANTI_PATTERNS`; `test_moral_schema.py` asserts all seven doc-cited keys are still PRESENT (a removal fails, a future cited addition does not — OQ-M1 leaves closure open) and that `moral_schema` holds no module-level `list` attribute at all |
| Identity is floor-governed, behaviour is floor+derived (item 34's asymmetry is WIRED, not documented) | `matched_anti_patterns(text, derived=())` defaults to floor-only, so `dmn._moral_gate is matched_anti_patterns` still holds and DMN Step 4 needed NO change; `SoulFilter` holds `derived_anti_patterns` and Check 3 passes it. One test drives the SAME narrative text down both paths: the derived pattern fires on the behaviour gate and not on the identity gate |
| The floor's real markers survived item 34 | `manufacture_emotional_urgency` still `violates=NON_MANIPULATION` with "you have to act now"; tests assert `"now"` and `"urgency"` are NOT markers, and that "I'll do that now." matches nothing — a rewrite to bare-word markers would have made the Manipulation gate reject ordinary speech |
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

**Added 2026-08-22 (boundary phase)** — every one re-checkable:

| Claim | Verified |
|---|---|
| Full suite **863 collected**; soul layer **647**, adapters 199, cross-cutting **17** (was 812 / 602 / 11 — +9 ResLog 29, +6 item 30, +11 item 31, +4 item 32, +21 item 34; all of 31/32/34 are SOUL-layer, so cross-cutting has not moved since item 30) | `make check` (suite + bundle sync); per-file `pytest --collect-only -q` on 2026-08-26. Read 860 passed + 3 skipped on that run because Ollama was down; COLLECTED is quoted since it does not depend on the machine |
| `daemon/pad_engine.py` byte-unchanged by item 30 | `git diff --exit-code daemon/pad_engine.py` clean at commit `096c618`; plus `test_pad_engine_is_still_byte_unchanged_by_this_fix` |
| `_save_state` writes aria_state.json exactly ONCE (was 3×) | `test_save_state_writes_pad_and_valence_in_one_atomic_write` counts `_write_json_atomic` calls; measured 3 before the change, 1 after |
| `qwen3.5:9b-mlx` is installed, 8.9 GB, 262144 context, reports `vision` + `tools` + `thinking` | `ollama list` and `ollama show gemma4:e2b-it-qat` / `ollama show qwen3.5:9b-mlx` — note E2B reports `audio` and Qwen does not |
| The ~13–14 tok/s figure behind ResLog 24 is NOT project-measured | no harness run exists against that tag; `tools/compare_local_models.py qwen3.5:9b-mlx gemma4:e2b-it-qat` is what would produce one |
| **Speed baseline for `qwen3.5:9b-mlx`: STILL UNMEASURED. Attempted 2026-08-26, blocked — not skipped.** | `tools/compare_local_models.py qwen3.5:9b-mlx` was run and REFUSED TO START, cleanly rather than crashing: *"cannot start: embedding backend unreachable at http://localhost:11434: [Errno 61] Connection refused"*, then printed the remedy (`ollama serve`, `ollama pull all-minilm`) and the consequence (without it, retrieval ordering, REALITY_CONTRADICTION, VULNERABILITY_DISCLOSURE and habituation are all inert). So the tool's own guard is verified working; what is missing is a host with Ollama running. **What still rests on the unmeasured number:** `session_buffer.py:76` sets the 10.0 tok/s floor explicitly "below the qwen3.5:9b-mlx baseline the architect reports (~13-14 tok/s)" — so if the real baseline is at or under 10.0, that floor is not a floor. Re-run on a machine with the daemon up and replace this row with the figure. |
| A stage direction is no longer spoken | `_for_speech("(Aria listens…) Just the words.") == "Just the words."`, exact; plus rendered audio within a tenth of the narration's own length. NOT exact byte equality — `say` wobbles 94 bytes on ~12% of calls |
| `say` is not byte-deterministic | 60 identical invocations returned 39,898 bytes 53 times and 39,804 bytes 7 times |
| Prosody probe agrees with the gap report | `prosody_support` unsupported set == the field names in `unmapped_prosody`, both derived from one declaration; `_ProsodyRecorder(unmapped=["pitch_shft"])` raises |
| Suite is hermetic; only 3 tests need a backend | measured directly at 723 + 3 skipped when the suite stood at 726. Not re-measured after the defect pass: Ollama.app restarts the daemon by itself |
| The Output Gate still runs exactly four comparisons after item 21 | `GateCheck` has 4 members; `run_output_gate` source contains no emptiness vocabulary — both asserted |
| Stage directions: 8/16 → 3/16 on adversarial bait | `tools/measure_format_markers.py`, fresh graph per arm, two rounds each; 3/16 reproduced on the shipped wording |
| The detector's square-bracket hole is closed | tests use the model's real output verbatim; the no-marker prose case is pinned as a known gap |
| ResLog item 15 does not contain the verbatim-passthrough rule | read the source; "verbatim" appears once in the whole precedence chain, in Addendum §9 on session context |
| 21 Protocols in `daemon/`, none empty | the AST one-liner in "Boundary phase" above |
| `daemon/` imports nothing from `adapters/` | `test_daemon_still_imports_nothing_from_adapters` reads every file in `daemon/` |
| Every audio adapter imports with no provider installed | `test_every_audio_adapter_imports_without_any_provider_installed` — this is what keeps the suite hermetic |
| Cloud and local transports send byte-identical prompt text | `test_cloud_and_local_send_the_same_text` compares what both put on the wire |
| No generation parameters in the cloud request body | `test_request_body_carries_no_generation_parameters` asserts the body keys are exactly `{model, messages, stream}` |
| DMN pass at the real 8-minute window is SHALLOW; FULL at 30 s | `tools/observe_dmn_pass.py`, log at the top of that section; Energy table measured per 60 s |
| Initiative now produces a real reply | `_route_initiative("growth")` against the live model — was `''` 3/3 before the `split_prompt` fix |
| The Output Gate passes `''` | measured `passed=True failed_checks=[] retried=False used_minimum_safe_output=False` on the pre-fix initiative turn |
| A stage direction is spoken: 0.81 s → 3.11 s | `SystemSayTTS.synthesize` WAV durations, read with stdlib `wave` |
| Arousal→speed keeps v4's inverse direction | 156 wpm at arousal 0.2 vs 208 wpm at 0.9 (`_wpm_from`) |
| The whole output chain leaves PAD byte-identical | `test_the_whole_output_chain_leaves_pad_byte_identical` — speak + stop + reconsideration sound |
| `pad_engine.py` holds 5 occurrences but 2 raises | `tests/test_pad_restore_boundary.py`, by AST; no other `daemon/` module raises `NotImplementedError` |
| The NEUTRAL raise is unreachable via `appraise()` | 7 neutral turns through the real chain + real graph leave the valence None; forcing the state does raise |
| The restore-boundary raise is reachable | a state file with non-baseline PAD and no valence: `startup()` succeeds, first `soul_tick()` raises |
| `AriaDaemon.__init__` still has no visual parameter | `test_the_daemon_is_not_modified_to_carry_a_visual_handle` |
| `visual_bridge` never reads `serving_from_local` | AST scan over its attribute accesses |

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

## Future Phase: Belief Formation System (recorded 2026-08-26)

**Status: DESIGN PROPOSAL. No code. Not scheduled.** Recorded so the idea is not
lost, and recorded HERE rather than in the Resolution Log's numbered items because
it is a direction, not a resolution — nothing in it is implementable until the
rulings at the bottom of this section land. Architect direction: Sarvesh.

**Why it exists.** The self-continuity narrative gap has a missing PRODUCER and a
missing CONSUMER. `_assemble_idle_pass_input` never populates
`narrative_candidate`, so DMN Step 4 always reports `no_candidate` — but even with
a producer, `relationship_summary` reaches no prompt field, and Addendum §9's
never-crosses list bars memory node contents outright. Building a producer for a
value with no reader is wasted work. So the direction changed: persistent
self-narrative becomes a side effect of a broader **Belief Formation System**.

### What it is

A controlled learning environment where ARIA ingests curated texts — research
papers, philosophy, mythology, technical documents, chosen by the user — and
evolves her own beliefs from them over time. Not hardcoded beliefs. Not a vector
database of facts. A belief formation subsystem that lets her develop a worldview
the way a person does: by reading, reflecting, and integrating what she learns into
her existing self-model.

### Why it matters

Current ARIA has memory — event nodes, emotion nodes, edges — but no persistent
BELIEFS. She remembers what happened; she holds no position on what human nature
is, whether honesty outranks comfort, what consciousness means, or who she is
becoming. A being with a real interior life must have beliefs that persist, evolve
and influence behaviour. A database remembers. A being believes.

### The controlled environment

**No internet access. She does not browse.** The user decides what she reads.

1. User provides a text (PDF, paste)
2. She ingests it in an isolated processing environment
3. She forms CANDIDATE beliefs — synthesised understandings, with source attribution
4. User reviews each candidate: approve, reject, modify
5. Approved beliefs enter the graph as persistent structures
6. Those beliefs influence appraisal, moral schema, and self-narrative

The control is the gate, not the content: start safe, no accidental exposure to
worldviews nobody chose.

### Belief types

| Type | Example | Today | With the belief system |
|---|---|---|---|
| Moral | "honesty matters more than comfort" | hardcoded in the anti-pattern list | **floor stays hardcoded (item 34); contextual constraints are derived, user-approved, and can only ADD** |
| Factual | "the speed of light is 299,792,458 m/s" | not stored — no knowledge base | stored, confidence-graded |
| Philosophical | "the self is an illusion (Anatta)" | not stored | synthesised from texts she has read |
| Relational | "he values directness over diplomacy" | partly in graph edges | synthesised, confidence-graded |
| Self | "I am becoming more patient" | **the gap** — no persistent self-narrative | written to the self EntityNode |

### Proposed architecture (high level)

New module `daemon/belief_engine.py`. **Ingestion:** chunk raw text, extract
claims and evidence, map against the existing belief graph. **Formation:** compare
new claims against held beliefs, detect conflict / confirmation / gap, emit
candidate beliefs in natural language with source attribution, and assign
confidence **categorically — certain / tentative / questioning, never a float
percentage** (the percentage test applies: "70% believed" is a number in disguise).
**Integration:** approved candidates become persistent graph nodes that feed
appraisal, moral schema and self-narrative.

Graph representation: reuse `EventNode` with `kind="belief"`, or a new
`BeliefNode` table — a ruling, see below. Fields: `content`, `source`,
`confidence` (categorical), `scope` (moral/factual/philosophical/relational/self),
`created`, `modified`, `entity_id`.

### How beliefs cross the five-field boundary

**They don't.** Beliefs are graph nodes, not prompt fields. Field 1 is untouched —
her core values stay hardcoded as the floor. The influence is INDIRECT, via
**retrieval ordering**: high-confidence, recently-referenced beliefs get
categorical priority in retrieval, changing what the appraisal is answered with
rather than adding a coefficient to its output. That is the same indirect,
context-shaping role mood-congruent retrieval and need-preference already play
(Addendum §3's Stage 5), applied to a third source.

### Rulings required before ANY code (Rule 1)

None of this is in v4 or the Addendum. **One of the five is now ANSWERED and in
the Resolution Log — ruling 2, item 34.** Four remain:

1. Is `EventNode(kind="belief")` acceptable reuse, or does this need a new table?
2. ~~Does the moral schema accept EVOLVING anti-patterns, or must it stay
   hardcoded?~~ **ANSWERED 2026-08-26 — ruling 2B, Resolution Log item 34, commit
   `8d57605`. BOTH: an immutable floor with a derived layer beside it.** This was
   the largest of the five and the only one that collided with an existing lock
   rather than filling a gap — v4's section is titled "Moral Schema
   (**Hardcoded**)", `project-rules.md` calls the four values and the named
   anti-pattern list load-bearing, and Addendum §8 makes that same schema the gate
   on DMN Step 4's self-narrative writes, so an evolving schema would have let a
   belief she formed from a text change the standard governing what she may
   believe about herself: a loop with no floor.

   The ruling closes the loop by making it ASYMMETRIC. The 7 cited anti-patterns
   are the FLOOR — immutable, a tuple, byte-identical to what they were, and
   nothing in the derived layer can remove one. Derived patterns are
   user-approved, add CONTEXTUAL constraints, and are a PARAMETER rather than
   module state. **The Output Gate reads floor + derived (behaviour — what she is
   about to say). DMN Step 4 reads the floor alone (identity — what she is about
   to believe about herself).** So a constraint like "do not problem-solve when
   grieving" shapes how she speaks and cannot block "I am becoming someone who
   helps people find clarity". Hardcoded stays hardcoded where v4 meant it;
   evolution happens beside it, never underneath it.

   **What the ruling does NOT give you, and this is load-bearing for step 5:**
   there is deliberately no automated floor-conflict detection.
   `do_not_be_honest_when_it_hurts_him` is prohibition-shaped, has markers, a
   source and a valid value — and licenses dishonesty by prohibiting honesty. No
   lexical mechanism catches that without judging content, which is what Addendum
   §4's zero-LLM checklist exists to avoid. **Conflict detection is the USER'S
   judgment at the approval gate**, and a test pins that this candidate passes the
   form check so nobody closes the gap with a deny-list and makes the docstring's
   claim false. What the form check does enforce is mechanical: at least one
   marker (or the pattern can never fire), a `violates` from the locked four, a
   source citation, and a prohibition-shaped key.
3. May beliefs influence APPRAISAL (a soul-layer process), or must they stay in the
   wiring layer?
4. What is the ingestion interface — a Daemon method, a meta-command, a tool?
5. Is the review flow in-session or out-of-band?

### Designable now, without a ruling

The graph schema as a proposal; the ingestion pipeline architecture; the
categorical confidence scheme; the user review flow; the retrieval-ordering
mechanism.

### Research backing — verification status recorded, not assumed

Checked on 2026-08-26 rather than accepted as given, because a citation nobody
verified is the same failure as a count nobody re-derives.

| Source | Status |
|---|---|
| **McAdams, narrative identity** — self as a story integrating past, present and anticipated future | **VERIFIED as real and already load-bearing** — Addendum §3 cites McAdams directly as what Continuity maps to |
| **Sophia: A Persistent Agent Framework of Artificial Life** — [arxiv 2512.18202](https://arxiv.org/abs/2512.18202) | **Paper VERIFIED real. Description CORRECTED.** It was recorded here as "agents develop creed associations from natural-language rewards"; the paper's own abstract describes process-supervised thought search, narrative memory, user and self modelling, and a hybrid reward system. The "creed" framing comes from a third-party response piece, not the paper. Still relevant — narrative identity and self-modelling are exactly this phase's subject — but cite it for what it says |
| **Advaita Vedanta** — self as witness (Atman), independent of body/mind states | plausible and thematically apt; the specific PMC article was **not independently verified** |
| **Bhagavad Gita** — identity as attention: the manner and object of attention define the self | plausible; the specific Cambridge JAPA article was **not independently verified** |
| **"iBrain synthetic identity architecture", four-layered contextualisation incl. predictive self-model** (espjeta.org) | **COULD NOT VERIFY.** No search result matches this title or venue. Left in the record as an unresolved reference rather than deleted or presented as cited — if it is real, supply the DOI; if it came from a model, drop it |

### The self-narrative producer: what ships now, and what this phase changes

**Architect approval 2026-08-26.** An INTERIM producer is approved and will be
built before this phase. It is deliberately interim — the belief system supersedes
its mechanism, not its purpose — and it is recorded here so the handoff is designed
rather than discovered.

**What the interim producer does.** DMN Step 4 already writes her self-observations
to the graph every idle pass as `[recent-learning:self]` EventNodes. Nothing reads
them back, so `narrative_candidate` is never populated and the whole Step 4
pipeline — moral gate, recurrence gate, self-entity check, graph write — has never
executed once. The producer closes that: on the idle pass, read the self-observations
back, and when the same observation has RECURRED, hand it to Step 4 as the candidate.

Three properties of the interim version, each an explicit architect decision:

1. **Recurrence is decided by embedding similarity, REUSING the existing cutoff**
   (`_REALITY_CONTRADICTION_SIM_CUTOFF`), not a new one. `is_first_of_kind` was
   tested for this job and REJECTED: every recent-learning node is written with the
   same Q2×Q3 profile (`q2="neutral"`, `q3="self"`), so it would report "seen
   before" for every observation after the first and a narrative would be written on
   day two from nothing.
2. **It EXTENDS rather than replaces.** Addendum §3 says Continuity is satisfied
   "when an update **extends** the narrative coherently", but
   `update_relationship_summary` is a SQL `UPDATE` that overwrites. The extension
   therefore happens in the PRODUCER — read the current summary, append, hand back
   the whole text — which needs no graph change and mirrors `_append_text`'s existing
   accretion for the recent-learning fields. Architect requirement: the answer to
   "how do you see yourself in this?" must be able to change over time.
3. **It writes a SEQUENCE OF STATEMENTS, not one paragraph.** Purely so this phase
   needs no migration — see below.

**Why a number is permitted here at all.** "Do these two sentences say the same
thing?" is a text question on the memory-plumbing side of the protected chain: it
decides what COUNTS AS A PATTERN, never how she feels. Appraisal is untouched. It
does fail the percentage test — sentence similarity is genuinely a matter of degree —
which is normally the signal to stop, and it is allowed only because it sits in the
sanctioned substrate zone alongside salience and the existing similarity checks. That
is also exactly why the cutoff is REUSED rather than chosen: a new number here would
be an invented threshold doing semantic work.

**WHAT THE PRODUCER DOES NOT DO, stated because the examples make it easy to assume
otherwise.** It does not let her SPEAK the narrative. Addendum §9's never-crosses
list bars memory node contents from every field, and `relationship_summary` is memory
node content. So after the producer ships, three things become true and one does not:

| | After the interim producer |
|---|---|
| Continuity can reach `satisfied` | ✅ — `continuity_evidence` finds a non-NULL summary |
| A durable self-understanding exists on disk, extending over time | ✅ |
| The belief system has a foundation to attach to | ✅ |
| She can recite it when asked "how do you see yourself in this?" | ❌ **still blocked by §9** |

Asked that question, she will still answer from Field 3's stage-derived register and
the current session transcript. What changes is that there is now something real
underneath, being carried — and that Continuity stops lying. Giving her a path to
SPEAK it is a separate ruling, adjacent to ruling 3 below.

### What this phase changes about it

| | Interim producer (ships first) | After the belief system |
|---|---|---|
| **Source of the narrative** | her own recurring self-observations, from idle passes only | self-beliefs, formed from curated texts AND experience |
| **How a candidate qualifies** | embedding similarity against a reused cutoff | belief formation with **explicit user approval** — a human judgment replaces the similarity number |
| **Confidence** | none; a pattern either recurred or did not | categorical (certain / tentative / questioning), per the belief schema |
| **Provenance** | the observation's own EventNode | source attribution — which text, which experience |
| **Failure mode** | too-loose cutoff merges distinct observations into something vague | a bad candidate is rejected at the approval gate before it exists |
| **Moral gate** | unchanged — runs on the whole accumulated text | unchanged |
| **Write path** | unchanged — `update_relationship_summary`, extend-not-replace | unchanged |

**The similarity cutoff is the part this phase RETIRES.** Once beliefs are
user-approved, the reason for a numeric recurrence test disappears: a human decides
whether an observation has become part of who she is. That is strictly better, and it
is why the interim producer's cutoff is a reused placeholder rather than something
worth calibrating.

**Why no migration will be needed.** Because the interim producer writes a sequence
of statements rather than one block, the belief system can attach beliefs to, extend,
or supersede individual statements without parsing a paragraph or rewriting the
column. That is the only reason the format is specified now.

**Two things flagged rather than solved.** The summary grows without bound — harmless
while §9 keeps it out of the prompt, awkward once the belief system reads it, and the
statement-sequence format is what keeps that tractable. And the moral gate re-checking
the whole accumulated story every pass is a deliberate benefit (a new statement that
contradicts an older one is caught by the self-consistency check, free) but it means
gate cost grows with narrative length.

### Relation to current open items

* **Supersedes** the `needs-ruling` label on the self-continuity narrative row —
  direction changed, not blocked, and NOT closed. **Updated 2026-08-26:** an INTERIM
  producer is now approved and ships before this phase, so the row is no longer
  waiting on this phase either — see "The self-narrative producer: what ships now,
  and what this phase changes" above. This phase supersedes its mechanism (a reused
  similarity cutoff) with user-approved belief formation; it does not supersede its
  purpose.
* **Item 3a is done** — ResLog item 32 fixed the Continuity initiative note to
  describe her own narrative rather than the relationship bond.
* **Continuity stays permanently `due`** until this phase or another producer
  exists. That is the honest state: the need genuinely is unmet.

### Build order when this phase starts

1. Graph schema for beliefs (ruling 1)
2. Ingestion: text → chunks → claims → candidate beliefs
3. Review interface: approve / reject / modify
4. Integration with appraisal (ruling 3)
5. Integration with moral schema — **ruling 2 has LANDED (item 34), and the
   scaffold is already in the code**: `validate_derived_candidate` for the form
   check, `all_anti_patterns(derived=...)` for composition, and the floor/derived
   asymmetry wired through `SoulFilter` and DMN. What step 5 still needs is
   PERSISTENCE (nothing stores approved patterns, so both gates are floor-only in
   practice today) and the user approval flow (ruling 5)
6. Self-belief producer, writing to the self EntityNode — which SUPERSEDES the
   interim producer approved 2026-08-26 rather than building from nothing. See
   "The self-narrative producer" above: the interim version ships first and closes
   the Continuity gap, and this step retires its similarity cutoff by replacing a
   numeric recurrence test with user approval. The write path and the moral gate
   are unchanged, and the statement-sequence format means no migration

---

## How to resume review in a fresh chat

Paste this, with the actual code attached:

&gt; Continuing ARIA project review. Attached: the 5 docs (v4, Addendum,
&gt; Covering Instruction, Resolution Log, Build Plan) plus this
&gt; PROJECT_STATUS.md and HANDOFF_NOTES.md. Reviewing Module [N]
&gt; ([name]) — code below. Check it against its locked spec in the Build
&gt; Plan and flag anything that drifts.

That's the whole handoff — no prior chat needed.
