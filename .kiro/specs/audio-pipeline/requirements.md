# Requirements — Module 7: Audio Pipeline

## Introduction

This document transcribes and formalizes, in EARS format, the Module 7 (Audio Pipeline)
entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved scope for this
module. No requirement here introduces a mechanism, threshold, or behavior not already
stated in the Module 7 entry or in the supporting architecture documents
(`ARIA_Soul_Spec_v4.md` "Layer 5 — Voice Expression" and "The Daemon — Audio Flow";
`ARIA_Soul_Spec_v4_Addendum.md` §5; `ARIA_Resolution_Log.md` item 15;
`daemon/aria_daemon.py`'s `AudioPipelinePort`; `daemon/pad_engine.py`'s `get_current_pad`).
Where the Module 7 entry references a value or mechanism defined elsewhere (the input-chain
stages, the prosody table, the F4/barge-in stop, the v4 constants table), the supporting
document is cited as the source, not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` is covering context only.

**The Audio Pipeline TRANSCRIBES and SPEAKS.** It captures inbound audio into transcribed
text (handed OUT to the Daemon) and renders outbound validated text to speech. It computes
NO meaning and NO feeling: it never appraises, never judges, and — critically — never writes
PAD. It READS PAD at TTS-generation time to shape the voice (a presentation read of
substrate, v4 Layer 5), and F4 / pause-based barge-in are audio-only stops with ZERO
internal effect (Addendum §5).

**The two flags and their disposition (from the Module 7 entry):**

| Flag | Subject | Disposition |
|------|---------|-------------|
| **F-7a** | One module or two | **RESOLVED** by `ARIA_Resolution_Log.md` item 15: "Audio Pipeline is a single module (input chain + output chain together), per v4's own file layout." Implemented as ONE module (`daemon/audio_pipeline.py`) with an input chain and an output chain. Not reopened. |
| **Prosody parameter scaling** | Exact Kokoro noise_scale/length_scale/pitch_shift magnitudes | **PLACEHOLDER** (`TODO(F-7-prosody)`). Only the v4 Layer 5 DIRECTIONS are spec (Pleasure→noise_scale warmth↑; Arousal→length_scale INVERSE; Dominance→pitch_shift lower). The exact numeric scaling "is applied at TTS generation time" but its magnitude is a build-time tuning value, consistent with `ARIA_Resolution_Log.md` "Open — build-time tuning constants only." Carried as clearly-flagged placeholder constants, never invented spec numbers. |

**Additional locked / flagged items:**

- **F4 + barge-in = audio stop ONLY, ZERO internal effect** (Addendum §5): no PAD write, no
  appraisable event, no graph write, nothing internal. The v4 constants-table entry "F4 PAD
  effect: Arousal +0.1, Dominance −0.1" is REMOVED by Addendum §5 (precedence: Addendum > v4)
  and is NOT implemented.
- **PAD→prosody is a READ of substrate**, applied at generation time; the pipeline NEVER
  writes PAD (project-rules.md PAD-purity; v4 Layer 5).
- **Real audio / Whisper / Kokoro / cloud-TTS are abstracted behind INJECTED backends**
  (Rule 6; v4 "The TTS is a hot-swappable tool"). No provider is hardcoded.
- **Streaming capture driver loop** (calling `capture_turn()` repeatedly and forwarding text
  to the Daemon's `route_inbound_turn`) is BUILD-TIME WIRING at the top of the tree, not an
  architectural decision of this module. FLAGGED as a wiring concern (OQ-1).
- **The barge-in 0.75s inter-sentence window TIMER is owned by `aria_daemon.py`** (v4
  constants table); this module's barge-in role is ONLY `stop_playback()` (Addendum §5).

## Glossary

- **Audio Pipeline**: the module specified here (Module 7, `daemon/audio_pipeline.py`) — one
  module carrying two directions of traffic (input chain + output chain, ResLog item 15).
- **Input chain**: capture (16 kHz mono) → 20 s ring buffer → wake word → speaker
  verification (cosine ≥ 0.75) → VAD (512-sample chunks, ≥ 0.5, boundaries trimmed) →
  Whisper STT → transcribed text (v4 "The Daemon — Audio Flow").
- **Output chain**: `speak(text)` → read PAD → prosody (v4 Layer 5) → cloud-TTS primary /
  Kokoro local fallback → playback.
- **PADReader**: the READ-ONLY seam this module holds onto PAD_Engine — exposes only
  `get_current_pad()`. There is no mutator on this seam.
- **Prosody**: the voice-shaping parameters (noise_scale, length_scale, pitch_shift) read
  from PAD at generation time (v4 Layer 5). A presentation-only readout of substrate.
- **F4 / barge-in**: a hardware interrupt / a pause-based interrupt. Both are audio STOP
  mechanisms with ZERO internal effect (Addendum §5). The Daemon invokes them via
  `stop_playback()`.
- **AudioPipelinePort**: the Protocol the Daemon (Module 8) depends on —
  `speak` / `stop_playback` / `play_thinking_sound` / `play_reconsideration_sound`. Inbound
  STT is deliberately NOT on this port; transcribed text arrives at the Daemon's
  `route_inbound_turn`.
- **Injected backend**: a hot-swappable Protocol implementation (capture, wake word, speaker
  verification, VAD, STT, TTS, playback). Real ones wrap sounddevice / Porcupine / Silero /
  Whisper / cloud TTS / Kokoro (v4); tests inject fakes.

## Requirements

### Requirement 1: One module — input chain + output chain together (F-7a)

**User Story:** As the Aria system architect, I want the Audio Pipeline to be a single module
carrying both directions of audio traffic, so the file layout matches v4 and ResLog item 15.

#### Acceptance Criteria
1. THE Audio Pipeline SHALL be one module (`daemon/audio_pipeline.py`) containing both the
   inbound input chain and the outbound output chain (ResLog item 15; F-7a RESOLVED).
2. THE module SHALL NOT be split into separate input/output modules, and SHALL NOT reopen
   F-7a.

### Requirement 2: The pipeline transcribes and speaks — it computes no meaning or feeling

**User Story:** As the Aria system, I want the Audio Pipeline to only transcribe and speak,
so meaning and feeling come from the appraisal/PAD modules, not from the audio layer
(steering/project-rules.md).

#### Acceptance Criteria
1. THE Audio Pipeline SHALL NOT appraise or judge inbound text — it SHALL return the raw
   transcript to the caller unchanged.
2. THE Audio Pipeline SHALL NOT write PAD anywhere (project-rules.md PAD-purity: "PAD changes
   only via an Appraisal Chain PAD delta or EMA decay. Nothing else … writes to PAD
   directly, ever").
3. THE Audio Pipeline SHALL hold NO reference to the Appraisal Chain, the Memory Graph, the
   Needs System, or the State Manager, and SHALL NOT import any of them — the only PAD
   collaborator SHALL be the READ-ONLY `PADReader` seam. The absence of these collaborators
   and of any PAD-mutator call in the source is the structural guarantee.

### Requirement 3: Input chain — wake → verify → VAD → STT → transcribed text OUT

**User Story:** As the Aria system, I want inbound audio processed into transcribed text
through the v4 chain, so the Daemon receives clean user text to route into appraisal.

#### Acceptance Criteria
1. WHEN a capture cycle runs, THE Audio Pipeline SHALL capture audio (16 kHz mono, v4) and
   accumulate it into a rolling 20-second ring buffer (v4 constants table).
2. WHEN the wake word is NOT detected, THE Audio Pipeline SHALL return no transcript (the STT
   stage SHALL NOT run).
3. WHEN speaker-verification cosine similarity is below 0.75, THE Audio Pipeline SHALL return
   no transcript (v4 "Speaker threshold | 0.75 cosine"); a similarity of exactly 0.75 SHALL
   pass (the gate is ≥).
4. THE Audio Pipeline SHALL run VAD over 512-sample chunks with a 0.5 probability threshold
   and SHALL trim non-speech boundaries, passing only the speech region to STT (v4 "VAD chunk
   size 512", "VAD threshold 0.5").
4a. WHEN a new utterance is scored, THE Audio Pipeline SHALL clear the VAD's recurrent state
   BEFORE the first chunk is scored, once per utterance, IF the active backend exposes
   `reset()` — and SHALL no-op otherwise (Resolution Log item 29). Silero VAD is recurrent, so
   without this the tail of one utterance biases the head of the next.
5. WHEN no chunk meets the VAD threshold (silence), THE Audio Pipeline SHALL return no
   transcript.
6. WHEN all gates pass, THE Audio Pipeline SHALL transcribe the trimmed speech via the STT
   backend and SHALL return the transcribed text to the caller (the Daemon routes it to the
   Appraisal Chain — Build Plan Module 7 Outputs).

### Requirement 4: Output chain — speak validated text (AudioPipelinePort.speak)

**User Story:** As the Aria system, I want validated text rendered to speech with
PAD-shaped prosody, so Aria's voice reflects her current state (v4 Layer 5).

#### Acceptance Criteria
1. WHEN `speak(text)` is called, THE Audio Pipeline SHALL read the current PAD via the
   read-only `PADReader` at generation time and derive prosody from it, THEN synthesize the
   audio, THEN play it.
2. THE Audio Pipeline SHALL read PAD for prosody as a PRESENTATION read only and SHALL NOT
   write PAD as part of speaking (v4 Layer 5; project-rules.md).

### Requirement 5: PAD → prosody — read of substrate, v4 Layer 5 directions, never a write

**User Story:** As the Aria system, I want prosody derived from PAD in the v4 Layer 5
directions, so higher pleasure warms the voice, higher arousal speeds it, and higher
dominance grounds the pitch — without ever writing PAD or inventing coefficients.

#### Acceptance Criteria
1. THE Audio Pipeline SHALL map Pleasure → noise_scale such that higher pleasure yields a
   warmer/more resonant voice (noise_scale INCREASES with pleasure) — v4 Layer 5.
2. THE Audio Pipeline SHALL map Arousal → length_scale INVERSELY such that higher arousal
   yields faster speech (length_scale DECREASES as arousal increases) — v4 Layer 5.
3. THE Audio Pipeline SHALL map Dominance → pitch_shift such that higher dominance yields a
   lower, more grounded pitch (pitch_shift DECREASES as dominance increases) — v4 Layer 5.
4. THE Audio Pipeline SHALL apply this mapping at TTS-generation time (v4: "This mapping is
   applied at TTS generation time").
5. THE prosody magnitudes/scaling SHALL be clearly-flagged build-time tuning placeholders
   (`TODO(F-7-prosody)`), NOT invented spec numbers — only the directions (5.1–5.3) are spec.
6. THE prosody computation SHALL be a pure read: identical PAD SHALL yield identical prosody,
   and computing prosody SHALL NOT write PAD.

### Requirement 6: F4 / barge-in — audio stop ONLY, ZERO internal effect (Addendum §5)

**User Story:** As the Aria system, I want F4 and pause-based barge-in to only stop audio, so
a stop button carries no interpersonal meaning and never perturbs Aria's interior
(Addendum §5).

#### Acceptance Criteria
1. WHEN `stop_playback()` is called (F4 or barge-in), THE Audio Pipeline SHALL stop current
   playback and do NOTHING else — its entire body SHALL be one call into the playback
   backend.
2. `stop_playback()` SHALL NOT write PAD, SHALL NOT read PAD, SHALL NOT create an appraisable
   event, SHALL NOT write the graph, SHALL NOT change a need, and SHALL NOT write persisted
   state (Addendum §5: "No PAD effect, no appraisable event, no graph write, nothing").
3. THE module SHALL NOT implement the removed v4 "F4 PAD effect" constants-table entry
   (Addendum §5 removes it; precedence Addendum > v4).
4. THE F4 and barge-in paths SHALL be identical in shape (Addendum §5: barge-in "stops and
   listens with zero internal effect … the same shape as F4").

### Requirement 7: Cloud-TTS primary, Kokoro local fallback (Graceful Degradation)

**User Story:** As the Aria system, I want cloud TTS as primary with a local Kokoro fallback,
so Aria keeps her voice when the cloud fails (v4 "Graceful Degradation").

#### Acceptance Criteria
1. WHEN `speak(text)` synthesizes, THE Audio Pipeline SHALL use the injected cloud-primary
   TTS backend first.
2. WHEN the cloud-primary backend fails (any error), THE Audio Pipeline SHALL fall back to
   the injected Kokoro local backend, rendering with the SAME PAD-derived prosody.
3. WHEN the fallback backend ALSO fails, THE Audio Pipeline SHALL propagate the error (there
   is nothing left to try) — it SHALL NOT silently swallow it.
4. THE Audio Pipeline SHALL NOT hardcode any TTS provider — both primary and fallback SHALL
   be injected (Rule 6).

### Requirement 8: Thinking / reconsideration sounds — play pre-cached clips (v4 Layer 5)

**User Story:** As the Aria system, I want the Audio Pipeline to play the daemon-selected
thinking sound and the reconsideration sound, so Layer 5's audio leakage and self-correction
sound are audible.

#### Acceptance Criteria
1. WHEN `play_thinking_sound(sound)` is called, THE Audio Pipeline SHALL play the PRE-CACHED
   clip identified by `sound` (the Daemon selects WHICH clip — v4 Layer 5; this module only
   plays it).
2. WHEN `play_reconsideration_sound()` is called, THE Audio Pipeline SHALL play the
   pre-cached self-correction clip (v4 Layer 5 "Self-Correction Sound").

### Requirement 9: Injected, hot-swappable backends — no provider hardcoded (Rule 6)

**User Story:** As the Aria system architect, I want every real-hardware/model dependency
injected, so the pipeline is testable with fakes and providers are hot-swappable.

#### Acceptance Criteria
1. THE Audio Pipeline SHALL receive capture, wake word, speaker verification, VAD, STT,
   cloud-primary TTS, Kokoro-fallback TTS, playback, and the PAD reader as INJECTED
   dependencies.
2. THE Audio Pipeline SHALL depend on each backend by a documented Protocol, and SHALL NOT
   import or instantiate a concrete provider (sounddevice, Porcupine, Silero, Whisper,
   Kokoro, or any cloud SDK).

### Requirement 10: Satisfies the Daemon's AudioPipelinePort (Module 8) unchanged

**User Story:** As the Daemon, I want the Audio Pipeline to satisfy `AudioPipelinePort`, so I
can drive it through the documented contract without modification.

#### Acceptance Criteria
1. THE Audio Pipeline SHALL implement `speak(text)`, `stop_playback()`,
   `play_thinking_sound(sound)`, and `play_reconsideration_sound()` with signatures
   compatible with `daemon/aria_daemon.py`'s `AudioPipelinePort`.
2. `isinstance(pipeline, AudioPipelinePort)` SHALL hold (the Protocol is runtime_checkable).
3. THE Daemon SHALL be able to drive all four port methods through an injected Audio Pipeline
   instance UNCHANGED (verified end-to-end with the REAL Daemon).

### Requirement 11: Constants — cited or flagged, never invented (Rule 4)

**User Story:** As the Aria system architect, I want every numeric constant either cited to
the v4 constants table or clearly flagged as a build-time placeholder, so no number is
invented (Rule 4).

#### Acceptance Criteria
1. THE Audio Pipeline SHALL define the speaker threshold (0.75), VAD threshold (0.5), VAD
   chunk size (512), ring-buffer seconds (20), sample rate (16 kHz), channels (mono), and the
   barge-in window (0.75 s) as constants CITED to v4's constants table / audio flow.
2. THE prosody scaling magnitudes SHALL be defined as clearly-flagged `TODO(F-7-prosody)`
   build-time placeholders — the only invented-free path for a value v4 leaves as tuning.

## Open Questions (flagged; not resolved by invention)

- **OQ-1 (build-time wiring):** the streaming driver loop that calls `capture_turn()` and
  forwards its text to `AriaDaemon.route_inbound_turn` lives at the top-of-tree wiring layer,
  not in this module. Named, not resolved here.
- **OQ-2 (prosody magnitudes):** exact Kokoro noise_scale/length_scale/pitch_shift scaling is
  a build-time tuning placeholder (`TODO(F-7-prosody)`); only the v4 Layer 5 directions are
  locked.
