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
