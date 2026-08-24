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
    biases the head of the next. `reset()` exists for that, and
    `AudioPipeline` never calls it — that is a real seam nobody owns yet, flagged
    below rather than papered over.

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
        self._state = None
        self.reset()
        self.chunks_scored = 0        # observability only

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

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
            inputs = {"input": frame}
            # The exported graph has changed shape across Silero releases: older
            # exports take separate `h`/`c` tensors, newer ones a single `state`.
            # Both are supported by NAME rather than by version-guessing, because
            # a wrong guess produces an unhelpful ONNX shape error at the first
            # chunk of the first utterance.
            if "sr" in self._input_names:
                inputs["sr"] = self._np.array(self._sample_rate, dtype=self._np.int64)
            if "state" in self._input_names:
                inputs["state"] = self._state
            else:
                inputs["h"], inputs["c"] = self._state
            outputs = self._session.run(None, inputs)
            probability = float(self._np.asarray(outputs[0]).reshape(-1)[0])
            if "state" in self._input_names:
                self._state = outputs[1]
            else:
                self._state = (outputs[1], outputs[2])

        self.chunks_scored += 1
        # Clamp to the Protocol's declared [0, 1]. The model does not exceed it;
        # the clamp is here so a consumer comparing against the cited 0.5 can rely
        # on the range the Protocol promises, whatever a future export does.
        return min(1.0, max(0.0, probability))

    def reset(self) -> None:
        """Clear the recurrent state — call BETWEEN utterances.

        FLAGGED SEAM: `AudioPipeline` never calls this. Each `capture_turn()`
        re-scores the whole ring-buffer snapshot with whatever state the previous
        cycle left behind, so the first chunks of an utterance are read in the
        context of the last one. Whether the pipeline should reset per snapshot is
        a Module 7 question, not an adapter's to answer, so this exposes the
        capability and leaves the decision alone (Rule 1).
        """
        zeros = self._np.zeros(
            (_STATE_LAYERS, _STATE_BATCH, _STATE_WIDTH), dtype=self._np.float32
        )
        if "state" in self._input_names:
            self._state = zeros
        else:
            self._state = (zeros, zeros.copy())


def available() -> bool:
    return module_available(_ONNXRUNTIME)


def install_hint() -> str:
    return _INSTALL
