"""Concrete `SpeakerVerificationBackend` — v4: "Silero speaker verification,
voiceprint.pt", the gate at cosine >= 0.75.

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.SpeakerVerificationBackend`:

    def similarity(self, audio: AudioSegment) -> float

Returns a cosine similarity in [-1, 1] between the audio's speaker embedding and
the enrolled voiceprint. **This adapter does not apply the 0.75 gate.**
`SPEAKER_THRESHOLD = 0.75` is a CITED v4 constant and `AudioPipeline.capture_turn`
owns the comparison — same split as the VAD, and for the same reason: a spec'd
threshold must not live inside a swappable component.

WHY THIS BACKEND MATTERS MORE THAN THE OTHER SIX
------------------------------------------------
It is the only audio backend whose answer is about IDENTITY, and identity is the
one thing this project treats as unrecoverable if it goes wrong. The tracker's
primary-entity ruling says so directly: `EntityNode` carries an `aliases` field by
design, so names are explicitly not identity, and "this is the one place where
getting identity wrong is unrecoverable."

That ruling also names the forward path this adapter is the missing half of.
`StateManager.load/save_primary_entity_id` exists and is described as
"forward-compatible with [enrolment]: enrolment should SET this key rather than
replace the mechanism, since binding a voiceprint to an EntityNode id is exactly
what these methods store." v4's own `aria_state.json` listing already contains
`voiceprint_enrolled`.

So: `enrol()` here produces the voiceprint. Binding it to an entity id is the
WIRING layer's job and is deliberately not done here — an adapter that wrote a
StateManager key would be an audio backend deciding who she is talking to.

A FAILED VERIFICATION IS NOT AN EVENT
-------------------------------------
When this returns below the gate, `capture_turn()` returns None and the turn never
happens. Nothing is appraised, no EventNode is written, PAD does not move. That is
correct and worth stating, because "someone else spoke to her" is intuitively an
event — and treating it as one would mean an unrecognised voice could move her
emotional state, which is precisely the door speaker verification exists to close.

THE VOICEPRINT IS A FILE THE CALLER OWNS
----------------------------------------
`voiceprint_path` is required. Nothing here downloads weights or invents a
default location: an adapter that silently created a voiceprint from the first
voice it heard would enrol whoever spoke first.

WHY torch, RELUCTANTLY
----------------------
v4 names Silero and a `.pt` file, and Silero's speaker models ship as torch
checkpoints — so unlike the VAD (which v4 puts in ONNX explicitly, ~2 MB) there is
no light path stated for this one. torch is hundreds of megabytes, and that cost
is real. It is accepted rather than worked around because the alternative is
substituting a different speaker model, which is a decision about identity
verification and therefore an architect call, not an adapter's (Rule 1).

Unlike the VAD this runs ONCE per capture cycle, not per 512-sample window, so
the weight is paid at a much lower rate.
"""

from __future__ import annotations

import threading
from typing import Optional, Sequence

from daemon.audio_pipeline import SAMPLE_RATE_HZ, AudioSegment

from adapters._provider import AudioBackendUnavailable, module_available, require_module

_TORCH = "torch"
_INSTALL = "pip install torch torchaudio   (hundreds of MB; v4 names Silero + voiceprint.pt)"

#: Below this many samples an embedding is not worth computing — too short to
#: characterise a voice. Provider plumbing, flagged: v4 states the 0.75 COSINE
#: gate but no minimum duration, so this is a floor on "is there enough audio to
#: ask the question", not a second identity threshold.
MIN_SAMPLES_FOR_EMBEDDING = SAMPLE_RATE_HZ // 2   # TODO(build-time): 0.5 s


class SileroSpeakerVerification:
    """`SpeakerVerificationBackend` backed by a torch speaker-embedding model.

    Holds the model, the enrolled voiceprint tensor and a lock. No soul state, no
    StateManager handle, no graph — so it can report a similarity and cannot
    record who anyone is.
    """

    def __init__(
        self,
        *,
        model_path: str,
        voiceprint_path: Optional[str] = None,
        sample_rate: int = SAMPLE_RATE_HZ,
        min_samples: int = MIN_SAMPLES_FOR_EMBEDDING,
    ) -> None:
        self._torch = require_module(
            _TORCH, purpose="speaker verification", install=_INSTALL
        )
        try:
            # `torch.jit.load` for a scripted checkpoint; `torch.load` for a
            # plain state dict is deliberately NOT attempted, because that path
            # needs the model CLASS and guessing an architecture to match a file
            # is how a voiceprint silently compares against the wrong embedding
            # space.
            self._model = self._torch.jit.load(model_path, map_location="cpu")
            self._model.eval()
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not load the speaker-verification model at "
                f"{model_path!r}: {exc}. v4 names Silero's scripted model; a "
                f"bare state dict needs its class and is not guessed at here."
            ) from exc

        self._sample_rate = sample_rate
        self._min_samples = min_samples
        self._lock = threading.Lock()
        self._voiceprint = None
        if voiceprint_path:
            self.load_voiceprint(voiceprint_path)
        self.comparisons = 0        # observability only

    @property
    def enrolled(self) -> bool:
        """Is a voiceprint loaded? The one question a wiring layer must ask before
        trusting `similarity()`."""
        return self._voiceprint is not None

    # -- enrolment ----------------------------------------------------------

    def enrol(self, audio: AudioSegment, *, save_to: Optional[str] = None):
        """Compute a voiceprint from audio and hold it as the enrolled speaker.

        Returns the embedding. Optionally writes it to `save_to` (v4's
        `voiceprint.pt`).

        BINDING IT TO AN IDENTITY IS NOT DONE HERE. The tracker's ruling is that
        enrolment should SET `StateManager.save_primary_entity_id`, and that is
        the wiring layer's call — this adapter has no state handle, which is what
        makes "an audio backend decided who you are" structurally impossible.
        """
        embedding = self._embed(audio)
        with self._lock:
            self._voiceprint = embedding
        if save_to:
            self._torch.save(embedding, save_to)
        return embedding

    def load_voiceprint(self, path: str) -> None:
        """Load an enrolled voiceprint (v4: `voiceprint.pt`)."""
        try:
            loaded = self._torch.load(path, map_location="cpu")
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not load the voiceprint at {path!r}: {exc}"
            ) from exc
        with self._lock:
            self._voiceprint = self._as_vector(loaded)

    # -- SpeakerVerificationBackend -----------------------------------------

    def similarity(self, audio: AudioSegment) -> float:
        """Cosine similarity in [-1, 1] against the enrolled voiceprint.

        Returns -1.0 — the FLOOR, i.e. "as unlike the enrolled speaker as the
        scale allows" — when there is no voiceprint or too little audio. That
        direction is deliberate: the pipeline compares against 0.75 and lets the
        turn through only above it, so the floor means "no turn". Returning 0.0
        would be equally rejected today but reads as "no information", and if the
        cited threshold were ever moved below zero the meaning would flip. -1.0
        cannot become a pass.

        Note that the similarity can genuinely be negative — the same property
        the tracker recorded for text embeddings ("cosine can be NEGATIVE", real
        model measured -0.075). Nothing here assumes a 0..1 range.
        """
        if not self.enrolled or len(audio) < self._min_samples:
            return -1.0
        candidate = self._embed(audio)
        with self._lock:
            reference = self._voiceprint
        self.comparisons += 1
        return self._cosine(candidate, reference)

    # -- provider plumbing --------------------------------------------------

    def _embed(self, audio: AudioSegment):
        """One speaker embedding. Runs under `no_grad` — there is no training
        here, and gradients would allocate for nothing on a per-turn path."""
        waveform = self._torch.tensor(
            [list(audio.samples)], dtype=self._torch.float32
        )
        with self._torch.no_grad():
            output = self._model(waveform)
        return self._as_vector(output)

    def _as_vector(self, value):
        """Flatten whatever the model or checkpoint hands back to a 1-D tensor.

        Silero's speaker models return a batch; a saved voiceprint may be stored
        either way. Reshaping rather than indexing means both load, and a
        mismatch surfaces as a length error in `_cosine` instead of a wrong-axis
        comparison that silently returns a plausible number.
        """
        tensor = value if hasattr(value, "reshape") else self._torch.tensor(value)
        return tensor.detach().reshape(-1).float()

    def _cosine(self, a, b) -> float:
        if a.shape != b.shape:
            raise ValueError(
                f"voiceprint dimension {tuple(b.shape)} does not match the "
                f"model's embedding {tuple(a.shape)} — the voiceprint was "
                f"enrolled with a different model. Re-enrol rather than compare "
                f"across embedding spaces."
            )
        denominator = float(a.norm()) * float(b.norm())
        if denominator == 0.0:
            return -1.0
        return float(self._torch.dot(a, b)) / denominator


def available() -> bool:
    return module_available(_TORCH)


def install_hint() -> str:
    return _INSTALL
