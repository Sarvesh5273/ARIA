# ARIA locked spec — audio-pipeline

Consolidated from .kiro/specs/audio-pipeline/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## audio-pipeline — requirements.md

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


---

## audio-pipeline — design.md

# Design — Module 7: Audio Pipeline

## Overview

The Audio Pipeline (`daemon/audio_pipeline.py`) is Aria's voice, in and out. One module
(ResLog item 15, F-7a RESOLVED) carrying two directions of traffic:

- **Input chain** — capture (16 kHz mono) → 20 s ring buffer → wake word → speaker
  verification (cosine ≥ 0.75) → VAD (512-sample chunks, ≥ 0.5, boundaries trimmed) →
  Whisper STT → transcribed text handed OUT to the Daemon (`route_inbound_turn` → Appraisal
  Chain).
- **Output chain** — `speak(text)` → read PAD at generation time → prosody (v4 Layer 5) →
  cloud-TTS primary / Kokoro local fallback → playback.

The single most important property is what the Audio Pipeline does NOT do: it computes no
meaning and no feeling. It never appraises inbound text (it just transcribes), and it never
writes PAD. It READS PAD for prosody — a presentation read of substrate (v4 Layer 5;
project-rules.md) — and F4 / pause-based barge-in are audio-only stops with ZERO internal
effect (Addendum §5).

This design implements requirements.md as written, using only mechanisms already specified
there or in the supporting documents. No new mechanism, formula, or threshold is introduced.
The one genuine tuning gap — the exact prosody scaling magnitude — is carried as a flagged
`TODO(F-7-prosody)` placeholder; only the v4 Layer 5 directions are spec.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **COMPUTES NO FEELING / NEVER WRITES PAD.** The module never calls a PAD mutator
   (grep-clean: `.apply_appraisal_delta(` never appears in the source). Its only PAD
   collaborator is the read-only `PADReader` (exposes only `get_current_pad()`). PAD-purity
   (project-rules.md) is structural: there is no mutator on the seam (Req 2, Req 5).
2. **DOES NOT APPRAISE.** `capture_turn()` returns the raw STT transcript unchanged; the
   module holds no Appraisal/Graph/Needs/State collaborator and imports none of them
   (Req 2). Transcribed text flows OUT to the Daemon (Build Plan Module 7 Outputs).
3. **F4 / BARGE-IN = ZERO INTERNAL EFFECT.** `stop_playback()`'s entire body is one call
   into the playback backend — no PAD read/write, no appraisal, no graph, no needs, no state
   (Addendum §5). The removed v4 "F4 PAD effect" entry is NOT implemented (Req 6).
4. **PAD → PROSODY = READ, v4 DIRECTIONS.** Pleasure→noise_scale (warmth↑),
   Arousal→length_scale (INVERSE), Dominance→pitch_shift (lower). Applied at generation
   time; magnitudes are placeholders (Req 5).
5. **INJECTED, HOT-SWAPPABLE BACKENDS.** capture / wake / speaker / VAD / STT / TTS×2 /
   playback / PAD reader are all injected Protocols; no provider hardcoded (Req 9).
6. **SATISFIES `AudioPipelinePort`.** speak / stop_playback / play_thinking_sound /
   play_reconsideration_sound, driven by the REAL Daemon unchanged (Req 10).

## Architecture

```
                            external world
   mic frames        F4 / barge-in        validated text (Soul_Filter, via Daemon)
        │                  │                        │
        ▼                  ▼                        ▼
 ┌───────────────────────── AudioPipeline (Module 7) ──────────────────────────┐
 │ INPUT CHAIN  capture_turn():                                                 │
 │   capture.read() → RingBuffer(20s) → wake.detect → speaker.similarity≥0.75   │
 │     → VAD trim (512-chunks, ≥0.5) → stt.transcribe → return TEXT  ───────────┼──▶ Daemon.route_inbound_turn
 │                                                                              │        (→ Appraisal Chain)
 │ OUTPUT CHAIN (AudioPipelinePort):                                            │
 │   speak(text):   PADReader.get_current_pad()  ── READ (presentation) ──┐     │
 │                  map_pad_to_prosody(pad)  [v4 Layer 5 directions]       │     │
 │                  tts_primary.synthesize(text, prosody)  ── cloud ──┐    │     │
 │                     └─ on ANY failure → tts_fallback.synthesize ── Kokoro    │
 │                  playback.play(wav)                                          │
 │   stop_playback():          playback.stop()          ← ZERO else (Add §5)    │
 │   play_thinking_sound(k):   playback.play_cached(k)   (v4 Layer 5)           │
 │   play_reconsideration_sound(): playback.play_cached(RECONSIDERATION_KEY)    │
 └──────────────────────────────────────────────────────────────────────────────┘
    │          │          │          │          │          │          │        │
    ▼          ▼          ▼          ▼          ▼          ▼          ▼        ▼
 Capture     Wake     Speaker      VAD        STT     TTS cloud   TTS Kokoro Playback   PADReader
 backend    backend   backend    backend    backend   backend     backend   backend   (get_current_pad
 [injected — no provider hardcoded; real = sounddevice/Porcupine/Silero/Whisper/cloud/Kokoro]   ONLY — read-only)
```

The ONLY inward-facing collaborator is the read-only `PADReader`. There is deliberately no
Appraisal/Graph/Needs/State edge on this diagram — that absence is the structural proof that
no stop and no speak can reach a PAD write or any state mutation.

## Value types

- **`AudioSegment`** (frozen): immutable PCM samples (`samples`, `sample_rate=16000`,
  `channels=1`). `chunks(size)` yields fixed-size windows (the 512-sample VAD unit);
  `concat(segments)` rejoins trimmed speech.
- **`Prosody`** (frozen): `noise_scale`, `length_scale`, `pitch_shift` — the voice params
  read from PAD at generation time (v4 Layer 5). A presentation-only readout of substrate.
- **`TTSUnavailable`** (Exception): a TTS backend's "cannot synthesize" signal (e.g., cloud
  down) — triggers the Kokoro fallback (v4 Graceful Degradation). Carries no information
  content; never appraised.

## Injected backend Protocols (Rule 6)

Each is a `runtime_checkable` Protocol; real implementations wrap the v4-named tools, tests
inject fakes. No concrete provider is imported.

| Protocol | Method(s) | Real (v4) | Gate/threshold owner |
|---|---|---|---|
| `PADReader` | `get_current_pad()` | PAD_Engine (Module 1) | — (READ-ONLY seam) |
| `CaptureBackend` | `read()` | sounddevice, 16 kHz mono | — |
| `WakeWordBackend` | `detect(audio)` | Porcupine (~2 MB) / hotkey | pipeline |
| `SpeakerVerificationBackend` | `similarity(audio)` | Silero, voiceprint.pt | pipeline (≥ 0.75) |
| `VADBackend` | `speech_probability(chunk)` | Silero VAD (ONNX) | pipeline (≥ 0.5, 512) |
| `STTBackend` | `transcribe(audio)` | Whisper base (CPU) | — |
| `TTSBackend` | `synthesize(text, prosody)` | cloud (Sarvam/ElevenLabs) + Kokoro | pipeline (fallback) |
| `PlaybackBackend` | `play` / `play_cached` / `stop` | pw-play / PyQt6 audio | — |

The gates (0.75 cosine, 0.5 VAD probability) live in the PIPELINE, not the backends, so the
v4-cited thresholds are applied in one auditable place and backends stay dumb tools.

## Input chain — `capture_turn() -> Optional[str]`

The v4 "Daemon — Audio Flow", stage by stage:

1. `capture.read()` → append to the 20 s `RingBuffer` (v4 constants table) → `snapshot()`.
   The ring buffer is the rolling pre-roll so wake word + the utterance are both retained;
   `deque(maxlen=20s·16kHz)` auto-evicts the oldest samples.
2. `wake.detect(buffered)` — if not woken, return `None` (STT never runs).
3. `speaker.similarity(buffered)` — if `< 0.75`, return `None` (drop non-owner voice).
4. `_trim_to_speech(buffered)` — iterate 512-sample chunks; keep those with
   `speech_probability ≥ 0.5`; concat. If none, return `None` (silence).
5. `stt.transcribe(speech)` — return the transcript.

The transcript is returned to the caller VERBATIM. This module does not appraise it; the
Daemon's `route_inbound_turn` routes it into the Appraisal Chain. (Aria-initiated speech,
Addendum §7, skips this whole chain and enters at soul_filter — that path is the Daemon's,
not this module's.)

## Output chain — `speak(text)` and the port methods

- **`speak(text)`**: `_current_prosody()` reads PAD via the read-only seam and maps it (v4
  Layer 5); `_synthesize_with_fallback(text, prosody)` tries the cloud primary and, on ANY
  exception, falls back to Kokoro with the SAME prosody; `playback.play(wav)`.
  Reading PAD here is a presentation read — it shapes the voice and is never a PAD write.
- **`stop_playback()`**: `playback.stop()` — nothing else (Addendum §5).
- **`play_thinking_sound(sound)`**: `playback.play_cached(sound)` — the Daemon chose the key.
- **`play_reconsideration_sound()`**: `playback.play_cached(RECONSIDERATION_SOUND_KEY)`.

### PAD → prosody (`map_pad_to_prosody`)

A pure function of a `PADSnapshot` (no engine, no state, no write). Directions LOCKED to v4
Layer 5; magnitudes are `TODO(F-7-prosody)` placeholders anchored at the neutral midpoint 0.5
of the normalized PAD range:

```
noise_scale  = BASE_n + SPAN_n · (pleasure  − 0.5)     # pleasure ↑  ⇒ warmer  (↑)
length_scale = BASE_l − SPAN_l · (arousal   − 0.5)     # arousal  ↑  ⇒ faster  (↓, INVERSE)
pitch_shift  = BASE_p − SPAN_p · (dominance − 0.5)     # dominance↑  ⇒ grounded(↓)
```

Only the sign/direction of each term is spec (v4 Layer 5 table). The `BASE_*`/`SPAN_*`
magnitudes and the 0.5 anchor are presentation-only tuning placeholders — never fed back into
any appraised meaning, consistent with "continuous numbers exist only in PAD and Energy"
(project-rules.md) since prosody is a downstream readout, not a stored state.

## TTS fallback (Graceful Degradation)

`_synthesize_with_fallback` tries `tts_primary.synthesize`; on ANY `Exception` (network,
provider error, `TTSUnavailable`) it records `_last_fell_back`/`_last_primary_error` (for
observability only, never re-appraised) and calls `tts_fallback.synthesize` with the SAME
prosody. If the fallback also raises, the error propagates. Catching broad `Exception` here is
deliberate and correct: the whole reason Kokoro exists is to absorb arbitrary cloud failures
(v4 "Graceful Degradation"). `BaseException` (KeyboardInterrupt/SystemExit) is NOT caught.

## PAD-purity & zero-effect — the structural guarantees

- The module imports exactly one daemon symbol: `from daemon.pad_engine import PADSnapshot`
  (a read-only type). It imports NO write-capable module (graph_manager, appraisal_chain,
  needs_system, state_manager, aria_daemon).
- `stop_playback()`'s body is a single `self._playback.stop()`; it references no `_pad`,
  `_stt`, `_vad`, `_wake`, and no mutating call.
- The `PADReader` seam has no mutator, so even `speak()` (which reads PAD) cannot write it.

These are enforced by tests (source scans + a live tripwire against the REAL PADEngine).

## Testing strategy (see tests/test_audio_pipeline.py)

Plain pytest, no hypothesis. Fakes for every backend. Highlights:
- **Input chain**: happy-path text-out; wake/speaker/silence gates; VAD boundary trimming;
  the 0.75 boundary; verbatim (no-appraisal) return.
- **PAD→prosody**: the three v4 directions; pure-function; `speak()` reads live PAD at
  generation time and varies prosody; `speak()` never writes PAD (tripwire).
- **F4/barge-in tripwire**: `stop_playback()` leaves PAD byte-identical, never reads it,
  never calls a mutator; only effect is `playback.stop()`. Plus source-scan structural
  proofs (no forbidden imports/calls).
- **Fallback**: cloud used when healthy; cloud failure → Kokoro; arbitrary error → Kokoro;
  same prosody to fallback; both-fail propagates.
- **Contract**: `isinstance(pipeline, AudioPipelinePort)`; signature match; and the REAL
  `AriaDaemon` driving all four port methods end-to-end through the pipeline.

## Open Questions (flagged; not resolved by invention)

- **OQ-1 (build-time wiring):** the streaming driver loop (repeated `capture_turn()` →
  `AriaDaemon.route_inbound_turn`) is top-of-tree wiring, not this module's concern.
- **OQ-2 (prosody magnitudes):** exact Kokoro scaling is a `TODO(F-7-prosody)` build-time
  tuning placeholder; only the v4 Layer 5 directions are locked.


---

## audio-pipeline — tasks.md

# Tasks — Module 7: Audio Pipeline

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing reopens a locked item (F-7a RESOLVED by ResLog item 15).
Genuinely-undefined values are `TODO(F-7-prosody)` placeholders, never invented. No other
core module is modified (the Daemon's `AudioPipelinePort` is satisfied unchanged).

- [x] 1. Module scaffold + minimal, read-only imports.
  - Create `daemon/audio_pipeline.py` with a docstring citing the five constraints, v4
    Layer 5 / "The Daemon — Audio Flow", Addendum §5, ResLog item 15, and the F-7a/prosody
    dispositions.
  - Import ONLY `PADSnapshot` (read-only type) from `daemon.pad_engine`; import NO
    write-capable module (graph/appraisal/needs/state/daemon). No import cycle (the Daemon
    does not import this module).
  - _Requirements: 1.1, 2.3, 9.2_

- [x] 2. Constants — v4-CITED vs FLAGGED placeholders.
  - CITED: `SAMPLE_RATE_HZ=16000`, `CHANNELS=1`, `RING_BUFFER_SECONDS=20`,
    `SPEAKER_THRESHOLD=0.75`, `VAD_CHUNK_SIZE=512`, `VAD_THRESHOLD=0.5`,
    `BARGE_IN_WINDOW_SECONDS=0.75` (window owned by aria_daemon.py), `RECONSIDERATION_SOUND_KEY`.
  - FLAGGED: prosody `*_BASE`/`*_SPAN` + neutral anchor as `TODO(F-7-prosody)` placeholders.
  - _Requirements: 11.1, 11.2_

- [x] 3. Value types.
  - `AudioSegment` (frozen: samples/sample_rate/channels; `chunks(size)`; `concat`).
  - `Prosody` (frozen: noise_scale/length_scale/pitch_shift).
  - `TTSUnavailable` exception (fallback signal; no information content).
  - _Requirements: 3.4, 5.1, 7.2_

- [x] 4. Injected backend Protocols (hot-swappable; no provider hardcoded).
  - `PADReader` (get_current_pad ONLY — read-only seam), `CaptureBackend`, `WakeWordBackend`,
    `SpeakerVerificationBackend`, `VADBackend`, `STTBackend`, `TTSBackend`, `PlaybackBackend`.
    All `runtime_checkable`.
  - _Requirements: 9.1, 9.2, 2.3_

- [x] 5. `RingBuffer` — 20 s rolling pre-roll (v4).
  - `deque(maxlen=capacity_samples)` auto-evicts oldest; `append` / `snapshot` / `clear`;
    `capacity_samples` property.
  - _Requirements: 3.1_

- [x] 6. `map_pad_to_prosody(pad)` — v4 Layer 5 directions, pure read.
  - Pleasure→noise_scale (↑ warmth), Arousal→length_scale (INVERSE ↓), Dominance→pitch_shift
    (↓ grounded). Pure function; magnitudes are placeholders; no PAD write.
  - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6_

- [x] 7. `AudioPipeline.__init__` — inject all backends + read-only PAD seam.
  - Store pad_source (read-only) + capture/wake/speaker/vad/stt/tts_primary/tts_fallback/
    playback + cited thresholds (overridable) + a 20 s `RingBuffer`. Observability-only
    fields (`_last_fell_back`, `_last_primary_error`, `_last_prosody`).
  - _Requirements: 9.1, 2.2, 2.3_

- [x] 8. Input chain — `capture_turn()` and `_trim_to_speech()`.
  - capture → ring buffer → wake gate → speaker gate (≥ 0.75) → VAD trim (512-chunks, ≥ 0.5)
    → STT → return transcript verbatim (no appraisal). Gates return `None`.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 2.1_

- [x] 9. Output chain — `speak()` + `_current_prosody()` + `_synthesize_with_fallback()`.
  - `speak`: read PAD at generation time → prosody → synthesize (cloud primary, Kokoro
    fallback on ANY error, same prosody; both-fail propagates) → play. Never writes PAD.
  - _Requirements: 4.1, 4.2, 5.4, 7.1, 7.2, 7.3, 7.4_

- [x] 10. Port methods — `stop_playback` / `play_thinking_sound` / `play_reconsideration_sound`.
  - `stop_playback`: single `playback.stop()`, ZERO else (Addendum §5). Thinking/
    reconsideration: `playback.play_cached(...)` (pre-cached clips, v4 Layer 5).
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 10.1_

- [x] 11. Tests — `tests/test_audio_pipeline.py` (plain pytest, no hypothesis).
  - Input chain (text-out, gates, VAD trimming, 0.75 boundary, verbatim); v4 cited constants;
    ring-buffer eviction; PAD→prosody directions + pure-function + live generation-time read
    + speak-never-writes-PAD tripwire; F4/barge-in zero-effect tripwire + source-scan
    structural proofs; cloud→Kokoro fallback (incl. arbitrary error, same prosody,
    both-fail); thinking/reconsideration clips; `AudioPipelinePort` isinstance + signature +
    REAL-Daemon end-to-end driving all four port methods.
  - _Requirements: 1.1, 2.1, 2.2, 2.3, 3.*, 4.*, 5.*, 6.*, 7.*, 8.*, 9.*, 10.*, 11.*_

- [x] 12. Verify — module green, then full suite green (no regressions).
  - `python3 -m pytest tests/test_audio_pipeline.py -q` → 29 passed.
  - `python3 -m pytest -q` → 374 passed (prior 345 + new 29). No other module modified.
  - _Requirements: 10.3_

