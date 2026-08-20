# ARIA — Module-Level Build Plan

**Produced under:** ARIA_GLM_Covering_Instruction.md
**Sources:** ARIA_Soul_Spec_v4.md (v4) with ARIA_Soul_Spec_v4_Addendum.md (addendum) applied — addendum supersedes v4 on every listed conflict.
**Scope:** Plan only. No code, no implementation detail, no invented mechanisms. Each module states Name, Responsibility, Inputs, Outputs, Dependencies, and Flags (ambiguities needing architect resolution before coding).

**Conventions applied:**
- `relational_stage` (categorical: observing / engaging / invested / bonded) replaces `EntityNode.trust_score` everywhere (addendum §2).
- Output Validation Gate = four structural comparisons, zero LLM (addendum §4).
- Stage 5 = Stage-1 retrieval preference (addendum §3).
- F4 = audio stop only, zero internal effect (addendum §5).
- Poignancy Critical = "… OR event-type is first-of-kind for this entity" (addendum §6).
- Social-signal pre-pass runs in Stage 1 via the local embedding model (addendum §1).
- Five-field soul_filter interface (addendum §9).
- LLM receives exactly the five fields + the user's current message, nothing else (Rule 5).
- Continuous numbers confined to PAD and Energy; the only other numeric values used are already-in-spec graph aggregates (salience, appraisal vectors, net PAD) and operational thresholds (emergency coping_potential ≤ 0.15 / ≤ 0.04), all sanctioned by v4 Principle 26 and therefore within Rule 4 (Rule 4 forbids only numbers *not already in the spec*).

**Flag-handling policy:** genuine silences in both documents, and covering-Rule-vs-v4 conflicts, are flagged for the system architect (Rules 1 & 2 and the closing paragraph place resolution with the architect, not the planner). Items the spec/addendum actually answer are recorded as notes below, not as open questions.

---

## Notes from re-review (not open questions — already answered by the spec/addendum)
- **Stage 5** is a context shaper at Stage 1 (addendum §3 + the explicit conflicts table): it surfaces due/neglected needs as a retrieval preference. It does **not** touch PAD directly.
- **Shallow DMN pass (Energy < 20)** = Steps 1 + 4 only — Steps 2 and 3 are both suppressed.
- **PAD-derivative ownership** (v4 Layer 5): prosody → Audio Pipeline (TTS); PAD→video → Visual Layer; thinking sounds → Daemon.
- **Graph numeric aggregates** (salience, appraisal vectors, net PAD, overall_salience) and the emergency thresholds (coping_potential ≤ 0.15, ≤ 0.04) are already in the locked schema and sanctioned by v4 Principle 26; Rule 4 only forbids numbers not already in the spec.
- **F4** constants-table PAD entry is removed (addendum §5): F4 = audio stop only, zero internal effect.

---

## Shared resources (referenced by modules — not modules themselves)
- **Local sentence-embedding model** (encoder-only, tens of MB, non-generative) — used by Appraisal Chain (VULNERABILITY_DISCLOSURE, REALITY_CONTRADICTION) and Memory Graph (similarity retrieval). One model serves both (addendum §1).
- **Moral schema** — four values (honesty, non-manipulation, genuine care, self-consistency) + named closed anti-pattern list. Read by Soul Filter (Output Gate Check 3, Constraints) and DMN (Step 4 narrative gate, addendum §8).
- **State persistence** — `aria_state.json` (PAD, needs), `self_model.json` (5-field self-model). Runtime/working state, not memory.

---

## Module 1 — PAD Engine

**Responsibility:** Maintains Pleasure, Arousal, Dominance as three continuous values and applies asymmetric EMA decay on every soul-tick, accepting only the appraisal chain's PAD delta as an external shift.

**Inputs:**
- PAD delta (dP, dA, dD from Stage 4) — from Appraisal Chain
- Soul-tick signal — from Daemon
- Aha-insight PAD delta (second-order appraisal) — from Appraisal Chain (originating in DMN)

**Outputs:**
- Current PAD coordinates — to Soul Filter (Behavioral Register), Visual Layer (zone), Audio Pipeline (prosody), Appraisal Chain Stage 1 (mood-congruent sign + coping context), Daemon (thinking-sound + zone)
- PAD history (last N ticks) — to DMN (EmotionNode crystallization)

**Dependencies:** Daemon (soul-tick); Appraisal Chain (deltas).

**Flags:** None. Baseline [0.55, 0.45, 0.58] and decay 0.6/0.75 are spec-locked.

---

## Module 2 — Needs System

**Responsibility:** Maintains Energy as a continuous resource with EMA decay, and Connection / Growth / Purpose / Continuity as categorical states (satisfied / due / neglected) set by qualifying graph evidence within recency windows.

**Inputs:**
- Qualifying-evidence query results — from Memory Graph
- Soul-tick (Energy decay) — from Daemon
- Energy refill signal — from Daemon (idle)

**Outputs:**
- Energy level (continuous) — to Soul Filter (Constraints <30 / <20), Appraisal Chain Stage 2 (<30 cognitive-load modifier), DMN (<20 shallow-pass gate)
- Categorical need states — to Appraisal Chain Stage 1 (retrieval preference), Soul Filter (This Moment / Constraints), Daemon (initiative)

**Dependencies:** Memory Graph; Daemon.

**Flags:**
- **F-2a Energy decay rate** — addendum §3 says Energy uses "the same EMA-style math as PAD," but PAD has two sign-dependent coefficients; Energy's coefficient(s) are not specified.
- **F-2b Energy refill mechanism** — qualitative only ("rest periods, clean task completion," "soul tick recovers Energy during extended idle"); discrete increments vs drift-to-baseline undefined.
- **F-2c Need→window mapping** — which recency window (72h / 14d / 60d) governs each of the four categorical needs is not specified.
- **F-2d One module or two** — Energy (continuous resource) and the four categorical needs are architecturally distinct mechanisms (addendum §3); the covering instruction lists them as one layer.

---

## Module 3 — Memory Graph

**Responsibility:** Stores all long-term memory as Event / Entity / Emotion / Uncertainty nodes and typed edges with appraisal vectors and salience, and provides mood-congruent, need-preferenced retrieval plus precision decay — the only persistent memory store.

**Inputs:**
- EventNode writes (appraisal vectors, poignancy category, PAD delta) — from Appraisal Chain Stage 6
- UncertaintyNode lifecycle updates — from Appraisal Chain / DMN
- Connection / aha edges, EmotionNode crystallization, salience adjustments — from DMN
- Retrieval requests (PAD.pleasure sign, need preferences, entity refs, query embedding) — from Appraisal Chain Stage 1
- Precision-decay tick — from Daemon / DMN

**Outputs:**
- Retrieved top 3–5 nodes/edges — to Appraisal Chain Stage 1
- Qualifying-evidence lookups (need states, relational_stage gates, poignancy first-of-kind check, REALITY_CONTRADICTION) — to Needs System, Appraisal Chain, Soul Filter, DMN
- `EntityNode.relational_stage` — to Soul Filter (Relational Register)

**Dependencies:** Daemon (decay tick); embedding model (similarity).

**Flags:**
- **F-3b Decay-clock owner** — precision decay is "time without re-activation"; the owning clock (wall-time vs retrieval-event vs DMN pass) is not pinned.
- **F-3c Stale state file** — `aria_state.json.relationship_depth` is superseded by `EntityNode.relational_stage` (addendum §2); flagged for cleanup.

---

## Module 4 — Appraisal Chain

**Responsibility:** Runs the per-turn appraisal of user input through Stages 0–6 (input classification, context load with social-signal pre-pass, EMA Q1–Q4, output synthesis, PAD shift) to produce a PAD delta and a graph EventNode write, and detects emergency conditions as an appraisal result.

**Inputs:**
- Transcribed user text — from Audio Pipeline (via Daemon)
- Retrieved graph context — from Memory Graph (Stage 1)
- Current PAD — from PAD Engine
- Social-signal tags (DISTRESS_MARKER lexical; VULNERABILITY_DISCLOSURE / REALITY_CONTRADICTION via embedding model; conflict-arc state machine) — from Stage 1 pre-pass
- Need states (Stage 1 retrieval preference) — from Needs System

**Outputs:**
- PAD delta (Stage 4) — to PAD Engine
- EventNode + poignancy category (Stage 6) — to Memory Graph
- UncertaintyNode create/resolve signals — to Memory Graph / DMN
- Most-salient appraisal result — to Soul Filter (This Moment)
- Emergency flag + Q2 sub-type — to Soul Filter (bypass)

**Dependencies:** Memory Graph; PAD Engine; Needs System; embedding model.

**Flags:**
- **F-4a coping_potential representation** — on non-emergency turns it is under-specified (the emergency gate implies a continuous value; Q4 is otherwise described categorically). Emergency thresholds themselves (≤ 0.15, ≤ 0.04) are already-in-spec and not in question.
- **F-4b Active Inference** — described qualitatively (beliefs / predictions / prediction-error) with no formal mechanism distinct from the Stage 0–6 chain: separate subsystem or framing?
- **F-4d Conflict-arc parameters** — state-machine open ("consecutive EventNodes, Q2=negative") and close ("enough turns pass") counts are unspecified.
- **F-4e Social-signal thresholds/windows** — VULNERABILITY_DISCLOSURE similarity cutoff and REALITY_CONTRADICTION "short window" + contradiction criterion are unspecified.
- **F-4f Live writes vs buffer writes** — overlap between live Stage-6 EventNode writes and DMN Step-1 buffer→graph writes is unclear.

---

## Module 5 — Soul Filter

**Responsibility:** Translates internal state into exactly five natural-language fields (Persona Anchor, Behavioral Register, Relational Register, This Moment, Constraints) plus the user message for the LLM, and runs the Output Validation Gate (four structural comparisons, addendum §4) on the LLM candidate before TTS.

**Inputs:**
- Current PAD — from PAD Engine (Behavioral Register)
- `relational_stage` — from Memory Graph (Relational Register)
- Most-salient appraisal output + emergency flag/type — from Appraisal Chain
- Need states — from Needs System
- Moral schema (4 values + anti-pattern list) — shared resource
- Candidate LLM output — from LLM Interface
- Graph facts (Check 3 Honesty via REALITY_CONTRADICTION) — from Memory Graph / embedding model

**Outputs:**
- Five-field instruction + user message — to LLM Interface
- Validated response text — to Audio Pipeline (TTS)
- Corrective / minimum-safe-output / emergency instructions — back to LLM Interface (retry)
- Reconsideration-sound trigger (on retry) — to Daemon

**Dependencies:** PAD Engine; Memory Graph; Needs System; Appraisal Chain; LLM Interface; embedding model; moral schema.

**Flags:**
- **F-5a Gate-ownership grouping** — the covering instruction groups the Output Validation Gate under both the Appraisal layer (4) and the LLM layer (9); v4 + addendum §4 place it here (Soul Filter). Placed here; flagged.
- **F-5b Field 4 "This Moment"** — addendum §9's stated highest-stakes translation step; flagged for implementation care (not an invention gap).

---

## Module 6 — DMN / Idle Consolidation

**Responsibility:** On the DMN tick (separate clock from soul-tick) it runs the four-step idle consolidation pass (buffer→graph, connection/aha formation, uncertainty revisiting, self-model + narrative update), and the forced early partial pass (Steps 1 + 4) on poignancy = critical.

**Inputs:**
- Idle signal (3 conditions met) — from Daemon
- Self-monitoring buffer (turn observations) — from live self-monitoring
- Self-model (5 fields) — persisted (`self_model.json`)
- Graph state (highest-salience unconnected nodes, active uncertainty nodes) — from Memory Graph
- Energy level (shallow vs full pass) — from Needs System
- Moral schema (gates Step 4 narrative) — shared resource

**Outputs:**
- New edges (connection/aha, `is_aha_edge`), EmotionNode (critical crystallization), UncertaintyNode resolutions, salience adjustments — to Memory Graph
- Self-model updates (quality record, consistency flags, narrative; narrative moral-schema-gated, addendum §8) — persisted
- Aha-insight event (for second-order appraisal → PAD shift) — to Appraisal Chain (not direct to PAD)

**Dependencies:** Memory Graph; Needs System; Appraisal Chain; Daemon; moral schema.

**Flags:**
- **F-6b Self-model vs Rule 7** — the persistent non-graph self-model / self-continuity narrative is in tension with Rule 7 ("graph is the only memory / no summary file"), even though layer 6 sanctions narrative updates.
- **F-6c Buffer poignancy** — how turn-level buffer items (no Q1–Q4) receive a poignancy category for the Step-1 high/critical threshold is unspecified.
- **F-6d Staleness counter** — "7 days or 50 interactions": confirm "interactions" = turns and which module counts them.

---

## Module 7 — Audio Pipeline

**Responsibility:** Captures/processes inbound audio (wake word, speaker verification, VAD, Whisper STT) into transcribed text, and renders outbound speech (TTS with PAD→prosody; cloud primary, Kokoro fallback) to audio, handling pause-based barge-in and the F4 interrupt as audio-only stops.

**Inputs:**
- Microphone audio (16 kHz mono); wake/voiceprint models
- Outbound validated text — from Soul Filter
- Current PAD (prosody) — from PAD Engine
- Barge-in / F4 signals — from Daemon / interrupt handler

**Outputs:**
- Transcribed user text — to Daemon (→ Appraisal Chain)
- Speech audio (WAV) — to speakers / PyQt audio
- F4 / barge-in produce **zero internal effect** (addendum §5)

**Dependencies:** Daemon; PAD Engine.

**Flags:**
- **F-7a One module or two** — input chain (wake / VAD / STT) and output chain (TTS) are distinct in v4's file layout; the covering instruction groups them as one layer.

---

## Module 8 — Daemon / Soul Tick

**Responsibility:** Orchestrates the system — drives the soul-tick (PAD decay, need depletion, attentional policy) and DMN-tick on separate clocks, routes an inbound turn, selects/plays thinking sounds from PAD+text, evaluates initiative, and detects idle.

**Inputs:**
- Transcribed text + audio events — from Audio Pipeline
- Current PAD — from PAD Engine
- Need states — from Needs System
- Appraisal / emergency flags — from Appraisal Chain

**Outputs:**
- Soul-tick and DMN-tick signals — to PAD Engine, Needs System, Memory Graph (decay), DMN
- Thinking-sound playback
- Idle signal — to DMN
- Initiative instruction — to Soul Filter (Aria-initiated speech enters at soul_filter, skipping wake/STT — addendum §7)

**Dependencies:** All core modules.

**Flags:**
- **F-8a Tick cadences** — qualitative (soul-tick "every few seconds"; DMN "slower during interaction, deep during idle"); only idle = 8 min and reflection = 6 h are pinned. Confirm timer values.
- **F-8b Attentional policy** — ("driven by highest-pressure needs and most-recently-salient nodes") is qualitative; overlaps initiative; mechanism not formalized.

---

## Module 9 — LLM Interface

**Responsibility:** Sends the five-field instruction + user message to the cloud LLM and returns candidate text, loading Gemma locally only on cloud failure and unloading on restore; applies no judgment (all validation is in Soul Filter).

**Inputs:**
- Five-field instruction + user message — from Soul Filter
- Corrective / retry / minimum-safe / emergency instructions — from Soul Filter
- Cloud availability status

**Outputs:**
- Candidate response text — to Soul Filter (Output Validation Gate)

**Dependencies:** Soul Filter; Gemma model (local fallback).

**Flags:**
- **F-9a Gemma and the graph** — confirm Gemma-fallback receives the **same** five-field-only + user-message limit as the cloud LLM (Rule 5): graph informs indirectly via appraisal/soul_filter, never injected directly into Gemma's context.
- **F-9b Output-gate label** — the covering instruction lists an "Output Gate" under this layer; the gate itself lives in Soul Filter (see F-5a).

---

## Module 10 — Visual Layer

**Responsibility:** Maps current PAD to one of eight video zones (idle + talking variants) and drives the PyQt6 frameless always-on-top window with libmpv, running independently and in parallel with language generation.

**Inputs:**
- Current PAD — from PAD Engine
- Speaking state (idle vs talking variant) — from Daemon / Audio Pipeline

**Outputs:**
- Video-zone loop signal — to PyQt6 window
- Graceful-degradation "inward/waiting" loop on cloud failure

**Dependencies:** PAD Engine; Daemon.

**Flags:**
- **F-10a Video-owner discrepancy** — v4 Layer 5 states "Video selection is soul_filter's job, not the LLM's"; the covering instruction places PAD→video in the Visual Layer. Placed in the Visual Layer per the covering instruction; the discrepancy is flagged.

---

## Global / cross-cutting flags (need architect ruling before coding)

1. **Active Inference (F-4b)** — qualitatively specified, no formal mechanism: separate subsystem or framing for the appraisal chain?
2. **Self-model vs Rule 7 (F-6b)** — persistent non-graph self-continuity narrative vs "graph is the only memory / no summary file."
3. **relational_stage persistence (F-3c)** — lives on EntityNode (graph); `aria_state.json.relationship_depth` is stale.
4. **Module-boundary ambiguities** between the covering instruction's 10-layer grouping and v4's file layout: Needs split (F-2d), Audio split (F-7a), Output-Gate ownership (F-5a / F-9b), video ownership (F-10a).
5. **State-persistence module** — none of the 10 layers names a persistence module; clarify whether a State Manager is intended or persistence is internal to each module.
