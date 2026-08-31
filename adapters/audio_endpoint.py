"""Utterance endpointing and a push-fed capture — the two pieces a voice host needs.

WHAT THIS IS FOR
----------------
`AudioPipeline.capture_turn()` answers "here is the audio, what was said". Nothing
in the approved layer answers "has he finished saying it". This file answers the
second question, at the wiring layer, which is where the Module 7 spec puts it:

    OQ-1 (build-time wiring): the streaming driver loop that calls
    `capture_turn()` and forwards its text to `AriaDaemon.route_inbound_turn`
    lives at the top-of-tree wiring layer, not in this module.

THE SPEC GAP, STATED PLAINLY BECAUSE IT IS NOT AN IMPLEMENTATION CHOICE
----------------------------------------------------------------------
v4's audio flow is a stateless poll: capture into a rolling 20-second ring, ask the
wake word, verify the speaker, trim to speech, transcribe. Read literally, a wake
word firing on "Aria" transcribes the ring AT THAT MOMENT — which is mid-sentence,
because the question has not been asked yet.

**v4 does not say how long to keep listening after being woken.** Searched: v4, the
Addendum, the Resolution Log, the Build Plan, HANDOFF_NOTES and every `.kiro` spec.
There is no end-of-utterance constant, no silence-hangover, no speech timeout and
no maximum utterance length anywhere. The nearest rows are all something else:

  * `Barge-in window | 0.75 seconds` is the window she opens between HER OWN
    sentences to notice being interrupted (v4 "Barge-In Architecture"). It is an
    output-chain constant. Reusing it here would be borrowing a number from a
    different mechanism to look cited.
  * `Post-speak window | 5–10s random` is the closest thing in spirit and is the
    ONLY occurrence of that phrase in the whole repository — no prose, no trigger,
    no mechanism. Using it would mean inventing the mechanism around an in-spec
    number, which is worse than an honest placeholder because it looks authorised.
  * `Idle sound min silence | 10 seconds` is a precondition on playing an ambient
    clip, not a judgment that speech ended.
  * `Ring buffer | 20 seconds` bounds how much audio EXISTS and auto-evicts.

So the two values below are BUILD-TIME TUNING CONSTANTS with no spec authority,
flagged as such, in the same category the Resolution Log already keeps under "Open
— build-time tuning constants only" and the same category as the
`TODO(F-7-prosody)` magnitudes. Both are also exposed as CLI flags, so they are
knobs an operator turns rather than numbers buried in a file.

WHY THIS IS NOT A SECOND GATE
-----------------------------
It would be easy to read an endpointer as a rival to the VAD gate. It is not, and
the distinction is the same one the project already drew for the Visual Layer:

    the 8-second gate decides whether a zone change is ALLOWED (Module 10);
    mpv's loop boundary decides when an allowed change is RENDERED.

Two mechanisms, two layers, one question each. Here:

    `AudioPipeline._trim_to_speech` decides WHICH SAMPLES ARE SPEECH — the cited
        0.5 comparison over 512-sample windows, owned by Module 7.
    `Endpointer` decides WHEN TO HAND OVER AN UTTERANCE — a timing decision,
        owned by the host.

`Endpointer` applies no cited threshold of its own: it reads `VAD_THRESHOLD` and
`VAD_CHUNK_SIZE` from the module that owns them rather than restating either, and
it never trims. The audio it hands over is UNTRIMMED — every sample it buffered,
pauses included — precisely so the pipeline's own trim is still the thing that
decides what counts as speech. Trimming here would quietly move the gate.

WHY ITS OWN VAD INSTANCE, WHICH LOOKS LIKE DUPLICATION AND IS NOT
-----------------------------------------------------------------
Silero VAD is recurrent, and Resolution Log item 29C had `AudioPipeline._reset_vad`
clear that state once per utterance. Sharing one instance between the pipeline and
an endpointer would mean the pipeline resetting state mid-stream underneath the
endpointer — the exact cross-contamination 29C exists to prevent, in the other
direction. Two instances of a 2.8 MB model that answer different questions is the
cheap, correct arrangement.
"""

from __future__ import annotations

from typing import List, Optional

from daemon.audio_pipeline import (
    RING_BUFFER_SECONDS,
    SAMPLE_RATE_HZ,
    VAD_CHUNK_SIZE,
    VAD_THRESHOLD,
    AudioSegment,
)

# ---------------------------------------------------------------------------
# BUILD-TIME TUNING CONSTANTS. No spec authority — see the module docstring for
# the search that establishes there is none, and for why the in-spec rows that
# look adjacent are all governing something else.
# ---------------------------------------------------------------------------

#: How much trailing non-speech means "he has finished". Long enough to sit
#: through the pause in "so... the thing is", short enough not to feel laggy.
#: Chosen by feel during bring-up and exposed as `--silence-hangover`.
DEFAULT_HANGOVER_SECONDS = 0.8          # TODO(build-time): utterance boundary

#: Ignore a burst shorter than this instead of treating it as an utterance. A
#: door closing clears the 0.5 gate for one or two windows, and without a floor
#: each such click costs a Whisper call and produces either "" or an invention.
#: Exposed as `--min-speech`.
DEFAULT_MIN_SPEECH_SECONDS = 0.20       # TODO(build-time): spurious-burst floor

#: The ceiling is DERIVED, not chosen: `AudioPipeline`'s ring buffer is v4's
#: cited 20 seconds and auto-evicts, so an utterance longer than the ring cannot
#: be represented downstream anyway. Cutting at the cap hands over what the
#: pipeline can actually hold; letting the buffer roll would silently drop the
#: START of a long utterance, which is the half that carries the wake word.
MAX_UTTERANCE_SECONDS = RING_BUFFER_SECONDS


class QueuedCapture:
    """A `CaptureBackend` fed by a caller instead of by a device.

    WHY THIS EXISTS. `CaptureBackend.read()` DRAINS — its contract is "audio since
    the last call" — so exactly one consumer may hold the microphone. A host that
    needs frames for endpointing therefore cannot also let the pipeline read the
    device: they would each get a random half of the audio, and the symptom would
    be words disappearing rather than an error.

    So the host owns the real `SoundDeviceCapture`, and the pipeline gets this. It
    satisfies the same Protocol, which is what lets `capture_turn()` run completely
    unmodified over a complete utterance. Same move as
    `visual_bridge.SpeakingSignalAudio`: satisfy the Protocol, compose at the
    wiring layer, change no approved module.

    Deliberately NOT a ring: this is a handoff slot, and dropping audio a caller
    explicitly pushed would lose part of a real utterance. `SoundDeviceCapture`'s
    bounded deque is the right shape for a DEVICE, where old audio is worth less
    than a bounded process; that reasoning does not transfer to a queue whose
    producer is a host handing over one finished utterance at a time.
    """

    def __init__(self, *, sample_rate: int = SAMPLE_RATE_HZ) -> None:
        self._sample_rate = sample_rate
        self._pending: List[float] = []
        self.pushes = 0             # observability only
        self.reads = 0

    def push(self, segment: AudioSegment) -> None:
        if segment.sample_rate != self._sample_rate:
            # Refuse rather than resample, for the same reason the STT adapter
            # does: a rate mismatch here also breaks the 512-sample VAD window
            # and the wake-word engine, and resampling would hide that.
            raise ValueError(
                f"expected {self._sample_rate} Hz (v4's capture format); got "
                f"{segment.sample_rate}"
            )
        self._pending.extend(segment.samples)
        self.pushes += 1

    # -- CaptureBackend -----------------------------------------------------

    def read(self) -> AudioSegment:
        """Drain what was pushed. Empty when nothing is waiting, which
        `capture_turn` already handles through the ordinary wake-word gate."""
        samples = tuple(self._pending)
        self._pending.clear()
        self.reads += 1
        return AudioSegment(samples, self._sample_rate, 1)

    @property
    def pending_samples(self) -> int:
        return len(self._pending)


class Endpointer:
    """Decides when an utterance has ended. Applies no cited threshold, trims
    nothing, and holds no soul state.

    Feed it audio as it arrives; it returns `None` while an utterance is still in
    progress and the COMPLETE UNTRIMMED utterance on the cycle it ends.
    """

    def __init__(
        self,
        *,
        vad,
        sample_rate: int = SAMPLE_RATE_HZ,
        hangover_seconds: float = DEFAULT_HANGOVER_SECONDS,
        min_speech_seconds: float = DEFAULT_MIN_SPEECH_SECONDS,
        max_utterance_seconds: float = MAX_UTTERANCE_SECONDS,
    ) -> None:
        self._vad = vad
        self._rate = sample_rate
        # Read from the owning module rather than restated, so this cannot drift
        # from the pipeline's gate and cannot be mistaken for a second one.
        self._chunk = VAD_CHUNK_SIZE
        self._threshold = VAD_THRESHOLD
        self._hangover_samples = int(hangover_seconds * sample_rate)
        self._min_speech_samples = int(min_speech_seconds * sample_rate)
        self._max_samples = int(max_utterance_seconds * sample_rate)

        self._buffer: List[float] = []      # everything since the last utterance
        self._carry: List[float] = []       # a partial window awaiting its rest
        self._speech_samples = 0            # speech seen in the current utterance
        self._silence_samples = 0           # trailing non-speech run
        self._in_speech = False
        self.utterances = 0                 # observability only
        self.last_end_reason: Optional[str] = None
        self._reset_vad()

    # -- lifecycle ----------------------------------------------------------

    def _reset_vad(self) -> None:
        """Clear the VAD's recurrent state, matching ResLog 29C's per-utterance
        rule. Probed rather than assumed, exactly as `AudioPipeline._reset_vad`
        does it, so a stateless VAD needs no equivalent."""
        reset = getattr(self._vad, "reset", None)
        if callable(reset):
            reset()

    def reset(self) -> None:
        """Drop everything and start listening fresh."""
        self._buffer.clear()
        self._carry.clear()
        self._speech_samples = 0
        self._silence_samples = 0
        self._in_speech = False
        self._reset_vad()

    @property
    def in_speech(self) -> bool:
        """True while an utterance is being accumulated. For a host that wants to
        show the operator that she is hearing something."""
        return self._in_speech

    @property
    def buffered_seconds(self) -> float:
        return len(self._buffer) / self._rate

    # -- the one real method ------------------------------------------------

    def feed(self, segment: AudioSegment) -> Optional[AudioSegment]:
        """Absorb newly captured audio; return a finished utterance or `None`.

        The returned audio is everything buffered since the previous utterance —
        UNTRIMMED, pauses and leading silence included. That is deliberate twice
        over: the pipeline's cited VAD trim stays the thing that decides what
        counts as speech, and the wake-word engine still gets to see the moment
        the wake word was spoken, which a trim could remove.
        """
        if segment.sample_rate != self._rate:
            raise ValueError(
                f"expected {self._rate} Hz (v4's capture format); got "
                f"{segment.sample_rate}"
            )
        if not segment.samples:
            return None

        self._buffer.extend(segment.samples)

        # Score in whole windows only. A partial window is CARRIED to the next
        # call rather than zero-padded: padding would hand the model a window
        # whose tail is invented, and at 32 ms a window this happens on most
        # calls, so the invention would be continuous rather than occasional.
        self._carry.extend(segment.samples)
        while len(self._carry) >= self._chunk:
            window = tuple(self._carry[:self._chunk])
            del self._carry[:self._chunk]
            self._observe(window)

        if self._in_speech:
            if self._silence_samples >= self._hangover_samples:
                return self._finish("silence")
            if len(self._buffer) >= self._max_samples:
                # v4's ring cannot hold more than this, so hand over what fits.
                return self._finish("max_length")
        else:
            # Not in an utterance: keep only what the ring could hold anyway, so a
            # host left running overnight does not grow without bound.
            excess = len(self._buffer) - self._max_samples
            if excess > 0:
                del self._buffer[:excess]
        return None

    def _observe(self, window) -> None:
        probability = self._vad.speech_probability(
            AudioSegment(window, self._rate, 1)
        )
        if probability >= self._threshold:
            self._speech_samples += self._chunk
            self._silence_samples = 0
            if not self._in_speech and self._speech_samples >= self._min_speech_samples:
                self._in_speech = True
        else:
            self._silence_samples += self._chunk
            if not self._in_speech:
                # A burst too short to count decays, so two unrelated clicks a
                # minute apart never add up to an utterance.
                if self._silence_samples >= self._hangover_samples:
                    self._speech_samples = 0

    def _finish(self, reason: str) -> AudioSegment:
        utterance = AudioSegment(tuple(self._buffer), self._rate, 1)
        self.utterances += 1
        self.last_end_reason = reason
        self.reset()
        return utterance
