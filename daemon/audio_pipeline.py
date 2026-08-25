"""Module 7 — Audio Pipeline (inbound STT + outbound TTS, one module).

Locked spec: see .kiro/specs/audio-pipeline/{requirements,design,tasks}.md.

Responsibility (`ARIA_Module_Build_Plan.md`, Module 7): capture/process inbound
audio (wake word → speaker verification → VAD → Whisper STT) into transcribed
text, and render outbound speech (TTS with PAD→prosody; cloud primary, Kokoro
local fallback) to audio — handling pause-based barge-in and the F4 interrupt as
audio-only stops. Dependencies = Daemon; PAD Engine.

Single module (input chain + output chain together) — `ARIA_Resolution_Log.md`
item 15 RESOLVES flag F-7a: "Audio Pipeline is a single module (input chain +
output chain together), per v4's own file layout." v4's file layout names one
`audio_pipeline.py`; this is it.

===========================================================================
HARD PHILOSOPHY CONSTRAINTS (a violation is WRONG even if tests pass)
===========================================================================

1. F4 AND PAUSE-BASED BARGE-IN PRODUCE ZERO INTERNAL EFFECT — AUDIO STOP ONLY
   (`ARIA_Soul_Spec_v4_Addendum.md` §5). `stop_playback()`'s ENTIRE body is one
   call into the playback backend. There is NO path from it to a PAD write, an
   appraisal, a graph write, a need change, a persisted-state write, or any
   state mutation. F4 is "a functional audio stop mechanism only … No PAD
   effect, no appraisable event, no graph write, nothing" (Addendum §5). The v4
   constants-table entry "F4 PAD effect: Arousal +0.1, Dominance -0.1" is
   REMOVED by Addendum §5 (precedence: Addendum > v4) and is NOT implemented
   here. Barge-in "stops and listens with zero internal effect … the same shape
   as F4" (Addendum §5). Whatever the user says AFTER the stop enters appraisal
   normally, via the Daemon — never through this module.

2. PAD→PROSODY IS A READ OF PAD (SUBSTRATE), APPLIED AT TTS-GENERATION TIME
   (v4 Layer 5 "Voice Expression"; steering/project-rules.md "reading PAD for
   prosody is a presentation read of substrate, NOT a feeling computation and
   NOT a PAD write"). This module NEVER writes PAD and NEVER computes a feeling.
   It reads the current PAD via the injected read-only `PADReader`
   (`get_current_pad()` — the same accessor every consumer uses; PAD_Engine
   Task 17) and shapes the voice. PAD-purity (project-rules.md): "PAD changes
   only via an Appraisal Chain PAD delta or EMA decay. Nothing else … writes to
   PAD directly, ever." The prosody MAPPING DIRECTIONS are the v4 Layer 5 table,
   locked and not invented:
     - Pleasure  → noise_scale   : higher pleasure = warmer/more resonant voice
     - Arousal   → length_scale  : INVERSE — higher arousal = faster speech
     - Dominance → pitch_shift   : higher dominance = lower, more grounded pitch
   The exact numeric parameter scaling is a BUILD-TIME TUNING PLACEHOLDER
   (flagged `TODO(F-7-prosody)`), NOT a spec number — only the directions are
   locked. Continuous numbers exist only in PAD/Energy (project-rules.md "No
   invented numbers"); prosody values are a presentation-only readout of PAD,
   never fed back into any appraised meaning.

3. THE PIPELINE TRANSCRIBES AND SPEAKS — IT DOES NOT APPRAISE OR JUDGE.
   Transcribed user text flows OUT (`capture_turn()` returns it) to the Daemon,
   which routes it into the Appraisal Chain (`ARIA_Module_Build_Plan.md` Module
   7 Outputs: "Transcribed user text → Daemon (→ Appraisal Chain)"). This module
   holds NO reference to the Appraisal Chain, the graph, the Needs System, or any
   PAD mutator. Inbound STT is deliberately NOT part of the Daemon's
   `AudioPipelinePort` — transcribed text arrives at the Daemon's
   `route_inbound_turn` (the Daemon is the callee).

4. REAL AUDIO / WHISPER / KOKORO / CLOUD-TTS ARE ABSTRACTED BEHIND INJECTED,
   HOT-SWAPPABLE BACKENDS (Rule 6; v4 "The TTS is a hot-swappable tool. Aria is
   not."). No provider is hardcoded: capture, wake word, speaker verification,
   VAD, STT, and TTS are all injected Protocols. v4 names reference
   implementations (sounddevice, Porcupine, Silero, Whisper base, Sarvam
   AI/ElevenLabs cloud, Kokoro) — cited in the spec, never imported here.

5. THIS MODULE SATISFIES THE DAEMON'S `AudioPipelinePort` (Module 8) unchanged:
   `speak` / `stop_playback` / `play_thinking_sound` / `play_reconsideration_sound`.
   The Daemon uses it by that documented contract (structural conformance —
   `isinstance(pipeline, AudioPipelinePort)` holds).

Build-time constants below are v4 constants-table values (cited) or clearly
flagged placeholders — none invented (Rule 1 "Do not invent"; Rule 4 "No
invented numbers").
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterator, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from daemon.pad_engine import PADSnapshot


# ===========================================================================
# Build-time constants.
#   CITED   = value fixed in v4's constants table / audio flow (source noted).
#   TODO(F-7-prosody) = presentation-only tuning placeholder; only the v4
#                       Layer 5 DIRECTION is locked, the magnitude is not spec.
# ===========================================================================

# --- Inbound capture format (v4 "Microphone (sounddevice 16kHz mono)"). ---
SAMPLE_RATE_HZ = 16_000            # CITED v4 audio flow — 16 kHz.
CHANNELS = 1                       # CITED v4 audio flow — mono.

# --- Ring buffer (v4 constants table: "Ring buffer | 20 seconds |
#     audio_pipeline.py"). Rolling pre-roll capture so wake word + the
#     utterance are both retained. ---
RING_BUFFER_SECONDS = 20           # CITED v4 constants table.

# --- Speaker verification (v4 constants table: "Speaker threshold | 0.75
#     cosine | audio_pipeline.py"; audio flow: "Silero Speaker Verification
#     … cosine >= 0.75"). Gate compares the backend's cosine similarity. ---
SPEAKER_THRESHOLD = 0.75           # CITED v4 constants table.

# --- VAD (v4 constants table: "VAD chunk size | 512 samples"; "VAD threshold |
#     0.5 probability"; audio flow: "Silero VAD (ONNX — chunk 512, threshold
#     0.5)"). ---
VAD_CHUNK_SIZE = 512               # CITED v4 constants table.
VAD_THRESHOLD = 0.5                # CITED v4 constants table.

# --- Pause-based barge-in window (v4 "Barge-In Architecture": a 0.75s
#     inter-sentence window; constants table: "Barge-in window | 0.75 seconds |
#     aria_daemon.py"). The TIMER/window is OWNED BY THE DAEMON (aria_daemon.py)
#     — this module's barge-in role is ONLY stop_playback() (Addendum §5). The
#     constant is documented here for reference, not driven here. ---
BARGE_IN_WINDOW_SECONDS = 0.75     # CITED v4 (window owned by aria_daemon.py).

# --- Pre-cached self-correction clip (v4 Layer 5 "Self-Correction Sound":
#     "a short reconsideration sound (a breath, a pause)"). ---
RECONSIDERATION_SOUND_KEY = "reconsideration"   # v4 Layer 5.

# --- PAD → prosody scaling. DIRECTIONS are v4 Layer 5 (LOCKED). Magnitudes are
#     build-time tuning placeholders (TODO(F-7-prosody)) — presentation-only,
#     NOT spec numbers. Anchored at the neutral midpoint 0.5 of the normalized
#     [0,1] PAD range (also a placeholder anchor). ---
_PAD_NEUTRAL_ANCHOR = 0.5          # TODO(F-7-prosody) placeholder anchor.
_NOISE_SCALE_BASE = 1.0            # TODO(F-7-prosody) placeholder.
_NOISE_SCALE_SPAN = 0.4            # TODO(F-7-prosody) placeholder magnitude.
_LENGTH_SCALE_BASE = 1.0           # TODO(F-7-prosody) placeholder.
_LENGTH_SCALE_SPAN = 0.4           # TODO(F-7-prosody) placeholder magnitude.
_PITCH_SHIFT_BASE = 0.0            # TODO(F-7-prosody) placeholder (semitones).
_PITCH_SHIFT_SPAN = 2.0            # TODO(F-7-prosody) placeholder magnitude.


# ===========================================================================
# Value types.
# ===========================================================================
@dataclass(frozen=True)
class AudioSegment:
    """An immutable block of PCM audio samples (mono, 16 kHz by default).

    `samples` is an opaque sequence of floats — real backends may use numpy;
    tests use tuples. The abstraction only requires a sequence that can be
    sliced into fixed-size chunks for the VAD stage.
    """
    samples: Tuple[float, ...] = ()
    sample_rate: int = SAMPLE_RATE_HZ
    channels: int = CHANNELS

    def __len__(self) -> int:
        return len(self.samples)

    def chunks(self, size: int) -> Iterator["AudioSegment"]:
        """Yield consecutive `size`-sample windows (the VAD chunk unit — 512
        samples per v4). A trailing partial window is yielded as-is."""
        if size <= 0:
            raise ValueError("chunk size must be positive")
        for start in range(0, len(self.samples), size):
            yield AudioSegment(
                samples=tuple(self.samples[start:start + size]),
                sample_rate=self.sample_rate,
                channels=self.channels,
            )

    @staticmethod
    def concat(segments: Sequence["AudioSegment"]) -> "AudioSegment":
        merged: List[float] = []
        rate = SAMPLE_RATE_HZ
        chans = CHANNELS
        for seg in segments:
            merged.extend(seg.samples)
            rate = seg.sample_rate
            chans = seg.channels
        return AudioSegment(tuple(merged), rate, chans)


@dataclass(frozen=True)
class Prosody:
    """The voice-shaping parameters read from PAD at TTS-generation time
    (v4 Layer 5). A presentation-only readout of PAD substrate — NEVER a PAD
    write and NEVER a feeling computation. Passed to whichever TTS backend
    renders the sentence; the exact parameter names mirror Kokoro's, but any
    injected backend may map them as it wishes (hot-swappable)."""
    noise_scale: float      # Pleasure  → warmth/resonance (higher pleasure ↑).
    length_scale: float     # Arousal   → speed, INVERSE (higher arousal ↓).
    pitch_shift: float      # Dominance → pitch (higher dominance ↓, grounded).


class TTSUnavailable(Exception):
    """Raised by a TTS backend that cannot synthesize (e.g., the cloud provider
    is unreachable). Signals the pipeline to fall back cloud→Kokoro (v4
    "Graceful Degradation"). Carries NO information content and is NEVER an
    appraisable event (Addendum §5 logic: a technical failure is not an
    interpersonal event)."""


# ===========================================================================
# Injected, hot-swappable backend Protocols (Rule 6). No provider is hardcoded.
# Real implementations wrap sounddevice / Porcupine / Silero / Whisper / cloud
# TTS / Kokoro (v4); tests inject fakes.
# ===========================================================================
@runtime_checkable
class PADReader(Protocol):
    """The READ-ONLY slice of PAD_Engine this module uses for prosody. It
    exposes ONLY `get_current_pad()` — there is no mutator on this seam, so the
    Audio Pipeline structurally cannot write PAD (project-rules.md PAD-purity)."""
    def get_current_pad(self) -> PADSnapshot: ...


@runtime_checkable
class CaptureBackend(Protocol):
    """Microphone capture (v4: sounddevice, 16 kHz mono). `read()` returns the
    most recent captured audio to feed the ring buffer."""
    def read(self) -> AudioSegment: ...


@runtime_checkable
class WakeWordBackend(Protocol):
    """Wake-word detection (v4: Porcupine ~2 MB, or hotkey fallback)."""
    def detect(self, audio: AudioSegment) -> bool: ...


@runtime_checkable
class SpeakerVerificationBackend(Protocol):
    """Speaker verification / voiceprint (v4: Silero, voiceprint.pt). Returns a
    cosine similarity in [-1, 1]; the pipeline applies the 0.75 gate."""
    def similarity(self, audio: AudioSegment) -> float: ...


@runtime_checkable
class VADBackend(Protocol):
    """Voice-activity detection (v4: Silero VAD, ONNX). Returns a speech
    probability in [0, 1] for a single chunk; the pipeline applies the 0.5
    gate and trims non-speech chunks.

    ONE METHOD, deliberately. A RECURRENT backend may additionally expose
    `reset()` to clear its hidden state; `AudioPipeline._reset_vad` probes for
    that and calls it once per utterance (Resolution Log item 29). It is not
    declared here because a stateless backend has nothing to reset and should
    not have to pretend otherwise."""
    def speech_probability(self, chunk: AudioSegment) -> float: ...


@runtime_checkable
class STTBackend(Protocol):
    """Speech-to-text (v4: Whisper base, CPU). Returns transcribed text."""
    def transcribe(self, audio: AudioSegment) -> str: ...


@runtime_checkable
class TTSBackend(Protocol):
    """Text-to-speech (v4: cloud Sarvam AI / ElevenLabs primary; Kokoro local
    fallback). `synthesize` returns rendered audio bytes (WAV) or raises
    `TTSUnavailable` when it cannot render."""
    def synthesize(self, text: str, prosody: Prosody) -> bytes: ...


@runtime_checkable
class PlaybackBackend(Protocol):
    """Audio output (v4: pw-play / PyQt6 audio). `play` renders a WAV,
    `play_cached` plays a pre-cached clip by key (thinking / reconsideration
    sounds), `stop` halts current playback (F4 / barge-in)."""
    def play(self, wav: bytes) -> None: ...
    def play_cached(self, key: str) -> None: ...
    def stop(self) -> None: ...


# ===========================================================================
# Ring buffer (v4 "Ring buffer | 20 seconds | audio_pipeline.py").
# ===========================================================================
class RingBuffer:
    """A fixed-capacity rolling buffer of the most recent audio samples. When
    full, appending drops the oldest samples (v4's 20-second pre-roll)."""

    def __init__(self, capacity_samples: int, sample_rate: int = SAMPLE_RATE_HZ,
                 channels: int = CHANNELS) -> None:
        if capacity_samples <= 0:
            raise ValueError("ring-buffer capacity must be positive")
        self._capacity = capacity_samples
        self._sample_rate = sample_rate
        self._channels = channels
        self._samples: Deque[float] = deque(maxlen=capacity_samples)

    @property
    def capacity_samples(self) -> int:
        return self._capacity

    def append(self, segment: AudioSegment) -> None:
        # deque(maxlen=...) auto-evicts from the left past capacity.
        self._samples.extend(segment.samples)

    def snapshot(self) -> AudioSegment:
        return AudioSegment(tuple(self._samples), self._sample_rate, self._channels)

    def clear(self) -> None:
        self._samples.clear()


# ===========================================================================
# PAD → prosody (v4 Layer 5). A pure READ of PAD → voice parameters. No PAD
# write. Directions LOCKED to v4; magnitudes are placeholders (TODO(F-7-prosody)).
# ===========================================================================
def map_pad_to_prosody(pad: PADSnapshot) -> Prosody:
    """Map a PAD reading to voice-shaping parameters at TTS-generation time
    (v4 Layer 5 "PAD → Prosody Mapping"). PURE FUNCTION of a PAD snapshot — it
    reads PAD, it never writes it, and it computes no feeling.

    Directions (v4 Layer 5, LOCKED — not invented):
      * Pleasure  → noise_scale     : "Higher pleasure = slightly warmer, more
                                       resonant voice"  → noise_scale INCREASES
                                       with pleasure.
      * Arousal   → length_scale    : "(inverse) … Higher arousal = faster
                                       speech; lower = slower"  → length_scale
                                       DECREASES as arousal increases (faster =
                                       shorter length_scale).
      * Dominance → pitch_shift     : "Higher dominance = slightly lower, more
                                       grounded pitch"  → pitch_shift DECREASES
                                       as dominance increases.

    The magnitudes (`*_BASE`, `*_SPAN`) are build-time tuning placeholders
    (TODO(F-7-prosody)); only the directions above are spec.
    """
    noise_scale = _NOISE_SCALE_BASE + _NOISE_SCALE_SPAN * (pad.pleasure - _PAD_NEUTRAL_ANCHOR)
    # INVERSE: subtract, so higher arousal → shorter length_scale → faster speech.
    length_scale = _LENGTH_SCALE_BASE - _LENGTH_SCALE_SPAN * (pad.arousal - _PAD_NEUTRAL_ANCHOR)
    # Higher dominance → lower (more negative / grounded) pitch shift.
    pitch_shift = _PITCH_SHIFT_BASE - _PITCH_SHIFT_SPAN * (pad.dominance - _PAD_NEUTRAL_ANCHOR)
    return Prosody(noise_scale=noise_scale, length_scale=length_scale, pitch_shift=pitch_shift)


# ===========================================================================
# The Audio Pipeline (Module 7). One module: input chain + output chain.
# ===========================================================================
class AudioPipeline:
    """Module 7 — inbound STT + outbound TTS behind injected backends.

    Satisfies the Daemon's `AudioPipelinePort` (speak / stop_playback /
    play_thinking_sound / play_reconsideration_sound). Reads PAD at TTS time for
    prosody (presentation read; NEVER a PAD write). F4 / barge-in are audio-only
    stops with ZERO internal effect (Addendum §5). Transcribes user speech to
    text and hands it OUT; it does NOT appraise (constraint 3).

    All dependencies are INJECTED (Rule 6). The only PAD collaborator is the
    read-only `PADReader` — there is deliberately no reference to the Appraisal
    Chain, the graph, the Needs System, the State Manager, or any PAD mutator, so
    there is no structural path from this module (or from a stop) to a PAD write
    or any state mutation.
    """

    def __init__(
        self,
        *,
        pad_source: PADReader,
        capture: CaptureBackend,
        wake_word: WakeWordBackend,
        speaker_verification: SpeakerVerificationBackend,
        vad: VADBackend,
        stt: STTBackend,
        tts_primary: TTSBackend,
        tts_fallback: TTSBackend,
        playback: PlaybackBackend,
        speaker_threshold: float = SPEAKER_THRESHOLD,
        vad_threshold: float = VAD_THRESHOLD,
        vad_chunk_size: int = VAD_CHUNK_SIZE,
        ring_buffer_seconds: int = RING_BUFFER_SECONDS,
        sample_rate: int = SAMPLE_RATE_HZ,
    ) -> None:
        # --- read-only PAD seam (prosody). NO mutator is held. ---
        self._pad = pad_source
        # --- injected input-chain backends ---
        self._capture = capture
        self._wake = wake_word
        self._speaker = speaker_verification
        self._vad = vad
        self._stt = stt
        # --- injected output-chain backends (cloud primary, Kokoro fallback) --
        self._tts_primary = tts_primary
        self._tts_fallback = tts_fallback
        self._playback = playback
        # --- cited thresholds (overridable for tuning, defaults are v4) ---
        self._speaker_threshold = speaker_threshold
        self._vad_threshold = vad_threshold
        self._vad_chunk_size = vad_chunk_size
        self._sample_rate = sample_rate
        # --- 20s ring buffer (v4) ---
        self._ring = RingBuffer(
            capacity_samples=ring_buffer_seconds * sample_rate,
            sample_rate=sample_rate,
            channels=CHANNELS,
        )
        # --- observability only (never fed back into meaning) ---
        self._last_fell_back = False
        self._last_primary_error: Optional[BaseException] = None
        self._last_prosody: Optional[Prosody] = None

    # =======================================================================
    # INPUT CHAIN — wake → verify → VAD → STT → transcribed text OUT.
    # Produces text for the Daemon (→ Appraisal Chain). It does NOT appraise.
    # =======================================================================
    def capture_turn(self) -> Optional[str]:
        """Run one inbound capture cycle and return transcribed text, or None if
        a gate does not pass (not woken / not the verified speaker / no speech).

        Chain (v4 "The Daemon — Audio Flow"): capture (16 kHz mono) → 20s ring
        buffer → wake word → speaker verification (cosine ≥ 0.75) → VAD (512-
        sample chunks, ≥ 0.5, boundaries trimmed) → Whisper STT → text.

        The returned text flows OUT to the Daemon's `route_inbound_turn`, which
        routes it into the Appraisal Chain. This module performs NO appraisal,
        NO judgement, NO PAD write, NO graph write — it only transcribes."""
        # Capture and accumulate into the rolling 20s pre-roll (v4).
        frame = self._capture.read()
        self._ring.append(frame)
        buffered = self._ring.snapshot()

        # Wake-word gate — nothing transcribes until Aria is addressed (v4).
        if not self._wake.detect(buffered):
            return None

        # Speaker verification gate — only the enrolled voice proceeds
        # (v4: cosine ≥ 0.75).
        if self._speaker.similarity(buffered) < self._speaker_threshold:
            return None

        # VAD — trim to the speech region (v4: chunk 512, threshold 0.5).
        speech = self._trim_to_speech(buffered)
        if speech is None or len(speech) == 0:
            return None

        # Whisper STT — transcribe. The text is handed OUT; not interpreted here.
        return self._stt.transcribe(speech)

    def _trim_to_speech(self, audio: AudioSegment) -> Optional[AudioSegment]:
        """Keep only the chunks whose speech probability meets the VAD threshold
        (v4: 512-sample chunks, ≥ 0.5) — trimming leading/trailing non-speech.
        Returns None if no chunk qualifies (silence only).

        Each call is ONE utterance's scoring pass and starts the VAD from a clean
        recurrent state (Resolution Log item 29) — see `_reset_vad`."""
        self._reset_vad()
        speech_chunks: List[AudioSegment] = []
        for chunk in audio.chunks(self._vad_chunk_size):
            if self._vad.speech_probability(chunk) >= self._vad_threshold:
                speech_chunks.append(chunk)
        if not speech_chunks:
            return None
        return AudioSegment.concat(speech_chunks)

    def _reset_vad(self) -> None:
        """Clear the VAD's recurrent state before scoring a new utterance, if the
        active backend has any (Resolution Log item 29).

        Silero VAD is recurrent — that is why it beats a per-frame energy test —
        and it therefore carries hidden state from chunk to chunk. This pipeline
        re-scores the WHOLE 20-second ring snapshot on every capture cycle, so
        without this call the head of each utterance is read in the context of the
        tail of the last one. `adapters/audio_vad.py` has flagged that seam since
        it was written: the capability was exposed and the decision deferred here,
        to Module 7, because whether to reset per snapshot is a pipeline question.
        This is the ruling.

        CAPABILITY PROBE, NOT A PROTOCOL METHOD. `VADBackend` stays at the single
        `speech_probability` it has always declared. Two of the three backends
        that occupy the `vad=` slot have no recurrent state and so no `reset` —
        `audio_stack._Absent`, whose entire contract is that every method it
        declares REFUSES, and the test fakes. Widening the Protocol would make
        `isinstance(_Absent(...), VADBackend)` false and force a silently-passing
        method into a class built to raise. A probe says the true thing instead:
        reset what has state to reset, and no-op for what does not.
        """
        reset = getattr(self._vad, "reset", None)
        if callable(reset):
            reset()

    # =======================================================================
    # OUTPUT CHAIN — AudioPipelinePort. speak() reads PAD for prosody at
    # generation time (presentation read; NEVER a PAD write).
    # =======================================================================
    def speak(self, text: str) -> None:
        """Render outbound validated text to speech (Daemon `AudioPipelinePort`).

        Reads current PAD (presentation read) → prosody (v4 Layer 5 directions)
        → synthesize with the cloud primary, falling back to Kokoro on failure
        (v4 "Cloud TTS … OR Kokoro (fallback)") → play. Reading PAD here is a
        presentation read of substrate — it shapes the voice and is NEVER a PAD
        write (constraint 2)."""
        prosody = self._current_prosody()          # PAD read → voice params.
        wav = self._synthesize_with_fallback(text, prosody)
        self._playback.play(wav)

    def stop_playback(self) -> None:
        """Stop current audio playback and return to listening (F4 / barge-in).

        ZERO INTERNAL EFFECT (Addendum §5): audio stop ONLY. This method's
        ENTIRE body is one call into the playback backend — there is NO PAD
        read or write, NO appraisal, NO graph write, NO need change, NO
        persisted-state write. F4 is a stop button, not an interpersonal
        event."""
        self._playback.stop()

    def play_thinking_sound(self, sound: str) -> None:
        """Play a PRE-CACHED thinking-sound clip by key (v4 Layer 5 "Thinking
        Sounds"). The Daemon selects WHICH clip (reading PAD+text); this module
        only plays the pre-cached audio."""
        self._playback.play_cached(sound)

    def play_reconsideration_sound(self) -> None:
        """Play the pre-cached self-correction clip during a Soul_Filter retry
        (v4 Layer 5 "Self-Correction Sound")."""
        self._playback.play_cached(RECONSIDERATION_SOUND_KEY)

    # =======================================================================
    # Prosody + TTS-with-fallback internals.
    # =======================================================================
    def _current_prosody(self) -> Prosody:
        """Read current PAD (presentation read) and map it to prosody at
        generation time (v4 Layer 5). NEVER writes PAD."""
        pad = self._pad.get_current_pad()          # read-only accessor.
        prosody = map_pad_to_prosody(pad)
        self._last_prosody = prosody               # observability only.
        return prosody

    def _synthesize_with_fallback(self, text: str, prosody: Prosody) -> bytes:
        """Cloud primary, Kokoro fallback (v4 "Graceful Degradation"). If the
        primary backend fails for ANY reason (network, provider error,
        TTSUnavailable), fall back to the local Kokoro backend — that is the
        entire reason the fallback exists. If the fallback ALSO fails, the error
        propagates (nothing left to try). No provider is hardcoded; both are
        injected."""
        self._last_fell_back = False
        self._last_primary_error = None
        try:
            return self._tts_primary.synthesize(text, prosody)
        except Exception as exc:  # noqa: BLE001 — graceful degradation is the point.
            # Cloud failed → degrade to local Kokoro (v4). The failure carries no
            # information content and is NEVER appraised (Addendum §5 logic).
            self._last_fell_back = True
            self._last_primary_error = exc
            return self._tts_fallback.synthesize(text, prosody)
