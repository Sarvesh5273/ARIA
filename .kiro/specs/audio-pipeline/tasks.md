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
