"""Concrete `VADBackend` — v4: "Silero VAD (ONNX — chunk 512, threshold 0.5)".

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.VADBackend`:

    def speech_probability(self, chunk: AudioSegment) -> float

Returns a probability in [0, 1] for ONE chunk. **This adapter does not apply the
threshold.** `AudioPipeline._trim_to_speech` owns that comparison against the
cited `VAD_THRESHOLD = 0.5`, and moving the gate down here would put a spec'd
number in a swappable component — the exact split the Protocol's own docstring
describes ("the pipeline applies the 0.5 gate").

CHUNK SIZE IS AN INPUT, NOT A CHOICE
------------------------------------
`VAD_CHUNK_SIZE = 512` is a CITED v4 constant, and it is not arbitrary: Silero's
ONNX graph is exported for a fixed window at a fixed rate, and 512 samples IS
that window at 16 kHz. So this adapter validates rather than reshapes. A chunk of
the wrong length is refused with a message naming both numbers, because the
alternative — padding or truncating to fit — would hand the model a window whose
contents no longer line up with what it was trained on, and it would do so
silently.

The pipeline's own `AudioSegment.chunks()` yields a trailing PARTIAL window
as-is, so short final chunks are expected and are zero-padded rather than
refused. That is a real case in normal operation and refusing it would make the
last fragment of every utterance an error.

STATE IS REAL AND MUST BE RESET BETWEEN UTTERANCES
--------------------------------------------------
Silero VAD is recurrent: it carries hidden state across chunks, which is why it
outperforms a per-frame energy test. Two consequences the Protocol cannot express
and a caller therefore has to know:

  * chunks must be fed IN ORDER, which `_trim_to_speech` does;
  * the state must be reset between utterances, or the tail of one utterance
    biases the head of the next. `reset()` exists for that, and as of Resolution
    Log item 29 `AudioPipeline._reset_vad` CALLS IT — once per utterance, at the
    start of each scoring pass. It was a flagged seam nobody owned; the ruling
    put it in Module 7, which is where the decision belonged.

THE v5 EXPORT NEEDS A CONTEXT WINDOW, AND WITHOUT IT THIS BACKEND IS DEAF
------------------------------------------------------------------------
Silero changed the graph's input contract between exports, and the change is
SILENT: the newer model accepts a bare 512-sample frame without complaint and
returns a probability that is simply always near zero. Nothing raises. The
backend reports "no speech" for speech.

Measured on this machine, on one 2.10 s utterance of real synthesised speech
(rms 0.127, peak 0.62), scored two ways against the SAME model file and the same
cited 0.5 threshold:

    512 samples, no context   ->    0 / 65 chunks over threshold   (max 0.4187)
    512 samples + 64 context  ->   62 / 65 chunks over threshold   (max 1.0000)

So the whole inbound chain fails closed: `_trim_to_speech` finds no qualifying
chunk, returns None, and `capture_turn()` returns before Whisper — which reads
from the outside as "she stopped listening", the same failure mode
`audio_speaker.py` warns about for a missing voiceprint.

What v5 wants is the previous 64 samples (at 16 kHz; 32 at 8 kHz) PREPENDED to
each window, with the new context taken from the tail of the chunk just scored.
The model is recurrent in two ways, then — the LSTM state, which `reset()`
already handled, and this short acoustic lookback, which nothing did.

WHY THIS IS PROVIDER PLUMBING AND NOT A NEW THRESHOLD. 64 is not a tuning value
and carries no meaning: it is the input shape Silero's own wrapper computes from
the sample rate, in the same class as the `h`/`c`-versus-`state` branch below
that this adapter already handled by NAME rather than by version-guessing. The
cited spec numbers are untouched — `VAD_CHUNK_SIZE = 512` and
`VAD_THRESHOLD = 0.5` stay in `AudioPipeline`, which still owns both
comparisons, and this file still defines neither.

The context is tied to the `state` input variant because that is how Silero's
own releases pair them: the older `h`/`c` export takes bare frames and the newer
`state` export takes context. Tying the two together means a v4-era model file
keeps working unchanged.

WHY NO TEST CAUGHT IT, WHICH IS THE MORE USEFUL LESSON. Nothing ran real Silero
inference. `tests/test_audio_pipeline.py` injects fakes throughout (correctly —
Module 7's job is the chain, not the model), and `tests/test_audio_adapters.py`
touched this file exactly twice: the imports-without-providers test and an AST
scan asserting no adapter defines the thresholds. Neither can see a wrong input
shape. The model file did not exist on the dev machine until inbound audio was
wired, so there was nothing to run against — the same shape of finding as the
boundary phase's three defects, "things no test could see because nothing
downstream existed to reveal them". `tests/test_audio_vad_real_model.py` now
runs the real graph when the file is present and skips when it is not, so
`make check` stays hermetic.

WHY ONNX RUNTIME AND NOT TORCH
------------------------------
v4 says ONNX explicitly. It is also the cheaper half of the choice by a wide
margin: `onnxruntime` is tens of megabytes against torch's hundreds, and the VAD
model itself is about 2 MB. Since the VAD runs on every 512-sample window of
every utterance, "cheap and always on" is the property that matters.

NO MODEL IS DOWNLOADED BY THIS FILE. The caller supplies `model_path`. Fetching
weights at import time would make a bring-up depend on the network and would put
a silent download inside a constructor.
"""

from __future__ import annotations

import threading
from typing import Optional

from daemon.audio_pipeline import SAMPLE_RATE_HZ, VAD_CHUNK_SIZE, AudioSegment

from adapters._provider import AudioBackendUnavailable, module_available, require_module

_ONNXRUNTIME = "onnxruntime"
_INSTALL = "pip install onnxruntime   (the Silero VAD model is ~2 MB, fetched separately)"

#: Silero VAD's recurrent state shape. A property of the exported graph, not a
#: tunable — it is stated here so the zero-initialisation below is readable
#: rather than magic.
_STATE_LAYERS = 2
_STATE_BATCH = 1
_STATE_WIDTH = 128

#: THE CONTEXT WINDOW — a property of the v5 exported graph, not a tunable and
#: not a threshold. See "THE v5 EXPORT NEEDS A CONTEXT WINDOW" in the module
#: docstring for the measurement that made this necessary.
#:
#: Silero's own wrapper derives it from the rate exactly this way (64 at 16 kHz,
#: 32 at 8 kHz), so these are the provider's numbers rather than chosen ones.
_CONTEXT_SAMPLES_16K = 64
_CONTEXT_SAMPLES_8K = 32


def _context_samples(sample_rate: int) -> int:
    """How many samples of lookback the v5 graph expects, per Silero's rule."""
    return _CONTEXT_SAMPLES_16K if sample_rate == 16_000 else _CONTEXT_SAMPLES_8K


class SileroVAD:
    """`VADBackend` backed by Silero VAD via ONNX Runtime (v4's named tool).

    Holds a session, the recurrent state and a lock. No soul state — and note
    there is no PAD handle and no threshold, so this component structurally
    cannot decide whether audio counts as speech. It reports a probability.
    """

    def __init__(
        self,
        *,
        model_path: str,
        sample_rate: int = SAMPLE_RATE_HZ,
        chunk_size: int = VAD_CHUNK_SIZE,
        providers: Optional[list] = None,
    ) -> None:
        onnxruntime = require_module(
            _ONNXRUNTIME, purpose="voice-activity detection", install=_INSTALL
        )
        # numpy comes with onnxruntime, so this adds no dependency of its own —
        # it is imported here rather than at module scope for the same reason
        # everything else in this package is.
        self._np = require_module(
            "numpy", purpose="voice-activity detection", install=_INSTALL
        )
        try:
            options = onnxruntime.SessionOptions()
            # One thread each. This runs per 512-sample window inside a turn that
            # is already latency-sensitive; thread pool churn costs more than it
            # saves on a graph this small.
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            self._session = onnxruntime.InferenceSession(
                model_path,
                sess_options=options,
                providers=providers or ["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not load the Silero VAD model at {model_path!r}: {exc}"
            ) from exc

        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._lock = threading.Lock()
        self._input_names = {i.name for i in self._session.get_inputs()}
        # The v5 export ("state") wants an acoustic lookback prepended to every
        # window; the older one ("h"/"c") does not. See the module docstring.
        self._wants_context = "state" in self._input_names
        self._context_size = (
            _context_samples(sample_rate) if self._wants_context else 0
        )
        self._state = None
        self._context = None
        self.reset()
        self.chunks_scored = 0        # observability only

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    @property
    def context_size(self) -> int:
        """Samples of lookback prepended per window — 0 for a pre-v5 export.

        Exposed so a bring-up can SEE which graph it loaded. The two exports are
        indistinguishable from their output (both return a plausible probability),
        and the wrong one is silently deaf, so "which contract is in force" has to
        be observable rather than inferred."""
        return self._context_size

    # -- VADBackend ---------------------------------------------------------

    def speech_probability(self, chunk: AudioSegment) -> float:
        """Speech probability in [0, 1] for one chunk. Applies NO threshold.

        A chunk LONGER than the expected window is refused: it would mean the
        caller is not chunking at the cited size, and quietly using a prefix
        would hide that. A SHORTER one is zero-padded, because
        `AudioSegment.chunks()` legitimately yields a partial trailing window.
        """
        samples = chunk.samples
        if len(samples) > self._chunk_size:
            raise ValueError(
                f"VAD expects {self._chunk_size}-sample chunks at "
                f"{self._sample_rate} Hz (v4 constants table); got "
                f"{len(samples)}. Silero's exported graph is fixed to that "
                f"window, so trimming here would silently change what the model "
                f"sees."
            )
        padded = tuple(samples) + (0.0,) * (self._chunk_size - len(samples))
        frame = self._np.array([padded], dtype=self._np.float32)

        with self._lock:
            # The v5 graph scores [previous 64 samples | this 512-sample window].
            # Without the lookback it returns near-zero on real speech and raises
            # nothing — the measurement is in the module docstring. A pre-v5
            # export gets the bare frame, which is its own contract.
            if self._wants_context:
                model_input = self._np.concatenate(
                    (self._context, frame), axis=1
                )
            else:
                model_input = frame

            inputs = {"input": model_input}
            # The exported graph has changed shape across Silero releases: older
            # exports take separate `h`/`c` tensors, newer ones a single `state`.
            # Both are supported by NAME rather than by version-guessing, because
            # a wrong guess produces an unhelpful ONNX shape error at the first
            # chunk of the first utterance.
            if "sr" in self._input_names:
                inputs["sr"] = self._np.array(self._sample_rate, dtype=self._np.int64)
            if self._wants_context:
                inputs["state"] = self._state
            else:
                inputs["h"], inputs["c"] = self._state
            outputs = self._session.run(None, inputs)
            probability = float(self._np.asarray(outputs[0]).reshape(-1)[0])
            if self._wants_context:
                self._state = outputs[1]
                # Next window's lookback is the tail of THIS window. Taken from
                # `frame` rather than from `model_input` so a short trailing chunk
                # cannot carry stale context forward: both slice to the same bytes
                # for a full window, and for a partial one this is the honest half.
                self._context = frame[:, -self._context_size:]
            else:
                self._state = (outputs[1], outputs[2])

        self.chunks_scored += 1
        # Clamp to the Protocol's declared [0, 1]. The model does not exceed it;
        # the clamp is here so a consumer comparing against the cited 0.5 can rely
        # on the range the Protocol promises, whatever a future export does.
        return min(1.0, max(0.0, probability))

    def reset(self) -> None:
        """Clear the recurrent state — called BETWEEN utterances.

        SEAM NOW OWNED (Resolution Log item 29). `AudioPipeline._reset_vad` calls
        this once per utterance, at the start of each `_trim_to_speech` scoring
        pass. Before that ruling nothing called it, so each `capture_turn()`
        re-scored the whole ring-buffer snapshot with whatever state the previous
        cycle left behind and the first chunks of an utterance were read in the
        context of the last one. The pipeline probes for this method rather than
        the Protocol declaring it, so a stateless VAD needs no equivalent.

        Takes the same lock `speech_probability` does — cheap, non-reentrant (no
        nesting between the two), and it means a reset can never land halfway
        through a scored chunk now that a caller actually exists.

        The ACOUSTIC LOOKBACK is cleared here too, for the same reason as the LSTM
        state: it is 64 samples of the previous utterance's tail, and a new
        utterance must not be read in its shadow. Zeroing it is what Silero's own
        wrapper does on a fresh stream.
        """
        zeros = self._np.zeros(
            (_STATE_LAYERS, _STATE_BATCH, _STATE_WIDTH), dtype=self._np.float32
        )
        with self._lock:
            if self._wants_context:
                self._state = zeros
                self._context = self._np.zeros(
                    (_STATE_BATCH, self._context_size), dtype=self._np.float32
                )
            else:
                self._state = (zeros, zeros.copy())
                self._context = None


def available() -> bool:
    return module_available(_ONNXRUNTIME)


def install_hint() -> str:
    return _INSTALL
