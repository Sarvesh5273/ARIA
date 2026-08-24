"""Concrete `STTBackend` — v4: "Whisper base, CPU".

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.STTBackend`:

    def transcribe(self, audio: AudioSegment) -> str

TWO IMPLEMENTATIONS OF v4's ONE NAMED MODEL
-------------------------------------------
    FasterWhisperSTT   `faster-whisper` (CTranslate2). Same Whisper weights,
                       markedly faster on CPU, no torch.
    WhisperCliSTT      a `whisper.cpp` binary already on the machine.

Both are Whisper base on CPU, which is what v4 names; they differ only in how the
same model is executed. `faster-whisper` is preferred because the alternative that
would have been the "obvious" choice — `openai-whisper` — pulls torch, and the
speaker-verification backend is already the one place this project accepts that
cost. Paying it twice for a model that has a torch-free runtime would be careless.

THIS IS WHERE TEXT ENTERS THE SYSTEM, AND THAT IS THE WHOLE POINT
----------------------------------------------------------------
What `transcribe()` returns becomes `route_inbound_turn(user_text=...)`, which is
appraised, written to the graph as an EventNode, and read by the vulnerability
check. So a transcription error does not just mis-hear a word: it can change the
meaning she appraises and the memory she keeps.

Two consequences shape this adapter:

  * **The text is returned VERBATIM.** No punctuation repair, no capitalisation
    fixes, no filler removal, no profanity filter, no "cleanup". Every one of
    those is an edit to what the user said, made by the component with the least
    context and no authority. F-9b / LLM Interface Req 5 put verbatim passthrough
    at the transport layer, and this is the inbound transport. (Formerly cited as
    "Resolution Log item 15" — see Resolution Log item 23.)
  * **No prompt / initial_prompt is passed.** Whisper accepts a text prompt that
    biases decoding, and it is tempting to prime it with her name or recent
    conversation. That would make the transcription depend on internal state,
    which is a §9 boundary question dressed as an accuracy tweak — and it can
    make the model hallucinate the primed words into silence. Flagged, not done.

WHISPER HALLUCINATES ON SILENCE — AND THE PIPELINE ALREADY HANDLES IT
---------------------------------------------------------------------
Fed near-silence, Whisper reliably invents text (subtitle boilerplate, "thank
you", a repeated phrase). That would be an appraisable event she never heard.

The defence is already in place upstream and needs no help here:
`AudioPipeline._trim_to_speech` returns None when no 512-sample chunk clears the
cited VAD threshold, and `capture_turn` returns before reaching STT. So silence
never arrives at this adapter in the wired path. What this adapter adds is
`no_speech_threshold` passthrough to the provider's own detector and nothing else
— it does not invent a second silence gate, because the pipeline's is the cited
one.

LANGUAGE IS NOT GUESSED PER UTTERANCE BY DEFAULT
------------------------------------------------
`AriaDaemon` sets `self._language = "en"` ("v4: default English"). Whisper's
autodetect on a short utterance is unreliable and will occasionally decide a
sentence is Welsh, then transcribe accordingly. So the default here is `"en"`,
matching the Daemon, with autodetect available by passing `language=None`.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

from daemon.audio_pipeline import SAMPLE_RATE_HZ, AudioSegment

from adapters._provider import (
    AudioBackendUnavailable,
    binary_available,
    module_available,
    require_binary,
    require_module,
)
from adapters.audio_pcm import to_wav_bytes

_FASTER_WHISPER = "faster_whisper"
_INSTALL = "pip install faster-whisper   (Whisper base on CPU, no torch)"

_WHISPER_CLI = "whisper-cli"
_CLI_INSTALL = "brew install whisper-cpp   (provides whisper-cli)"

#: v4 names "Whisper base". Not a tunable — a different size is a different
#: accuracy/latency trade and should be chosen deliberately, not drifted into.
SPEC_MODEL_SIZE = "base"

#: v4: default English (mirrors `AriaDaemon._language`). Pass None to autodetect.
DEFAULT_LANGUAGE = "en"

#: int8 on CPU is what makes `base` comfortably real-time on a laptop. Provider
#: plumbing; the WEIGHTS are v4's, the execution precision is not a spec value.
DEFAULT_COMPUTE_TYPE = "int8"     # TODO(build-time): CPU compute type


class FasterWhisperSTT:
    """`STTBackend` backed by `faster-whisper` (Whisper base, CPU — v4).

    Holds a model handle, decode settings and a lock. No soul state.
    """

    def __init__(
        self,
        *,
        model_size: str = SPEC_MODEL_SIZE,
        language: Optional[str] = DEFAULT_LANGUAGE,
        device: str = "cpu",
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        download_root: Optional[str] = None,
        no_speech_threshold: Optional[float] = None,
    ) -> None:
        provider = require_module(
            _FASTER_WHISPER, purpose="speech-to-text", install=_INSTALL
        )
        try:
            self._model = provider.WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root,
            )
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not load Whisper {model_size!r} on {device}: {exc}"
            ) from exc
        self._model_size = model_size
        self._language = language
        self._no_speech_threshold = no_speech_threshold
        self._lock = threading.Lock()
        self.transcriptions = 0        # observability only
        self.last_language: Optional[str] = None

    @property
    def model_size(self) -> str:
        return self._model_size

    # -- STTBackend ---------------------------------------------------------

    def transcribe(self, audio: AudioSegment) -> str:
        """Transcribe one segment and return the text VERBATIM.

        Segment texts are joined with a single space and the result is stripped of
        surrounding whitespace ONLY. Whisper emits each segment with a leading
        space, so joining raw yields doubled spaces; that is a container artefact
        of the segmentation, not something the user said. Nothing INSIDE the text
        is touched.

        An empty transcription returns `""`. It is not turned into None and not
        replaced with a placeholder: `capture_turn` returns whatever this gives,
        and inventing text is the one thing an inbound transport must never do.
        """
        if len(audio) == 0:
            return ""
        samples = self._as_provider_input(audio)
        options = {"language": self._language}
        if self._no_speech_threshold is not None:
            options["no_speech_threshold"] = self._no_speech_threshold
        with self._lock:
            try:
                segments, info = self._model.transcribe(samples, **options)
                parts = [segment.text for segment in segments]
            except Exception as exc:
                raise AudioBackendUnavailable(
                    f"Whisper {self._model_size!r} failed to transcribe: {exc}"
                ) from exc
        self.last_language = getattr(info, "language", None)
        self.transcriptions += 1
        return " ".join(part.strip() for part in parts if part.strip()).strip()

    def _as_provider_input(self, audio: AudioSegment):
        """faster-whisper takes a float32 numpy array at 16 kHz, which is exactly
        the pipeline's cited format — so this is a container change and never a
        resample. numpy arrives with the provider, so it costs no new dependency.

        A segment at another rate is REFUSED rather than resampled: resampling
        here would hide a capture misconfiguration that also affects the VAD's
        512-sample window and the wake-word engine.
        """
        if audio.sample_rate != SAMPLE_RATE_HZ:
            raise ValueError(
                f"Whisper expects {SAMPLE_RATE_HZ} Hz (v4's capture format); got "
                f"{audio.sample_rate}. Resampling here would mask a capture "
                f"misconfiguration that also breaks the VAD window."
            )
        numpy = require_module("numpy", purpose="speech-to-text", install=_INSTALL)
        return numpy.asarray(audio.samples, dtype=numpy.float32)


class WhisperCliSTT:
    """`STTBackend` backed by a `whisper.cpp` binary already on the machine.

    Exists because the heaviest thing about STT is usually the Python packaging,
    not the model — someone with `whisper-cpp` installed already has Whisper base
    on CPU, which is what v4 names, and should not need a second copy of it.

    Writes a temporary WAV (stdlib `wave`, via `audio_pcm`) and reads the text
    back. The temp file is always removed, including on failure.
    """

    def __init__(
        self,
        *,
        model_path: str,
        binary: str = _WHISPER_CLI,
        language: Optional[str] = DEFAULT_LANGUAGE,
        timeout: float = 120.0,
    ) -> None:
        self._binary = require_binary(
            binary, purpose="speech-to-text", install=_CLI_INSTALL
        )
        if not Path(model_path).is_file():
            raise AudioBackendUnavailable(
                f"whisper model file not found at {model_path!r}. v4 names "
                f"Whisper base; download ggml-base.bin and point at it."
            )
        self._model_path = model_path
        self._language = language
        self._timeout = timeout
        self.transcriptions = 0

    def transcribe(self, audio: AudioSegment) -> str:
        if len(audio) == 0:
            return ""
        wav = to_wav_bytes(audio.samples, sample_rate=audio.sample_rate)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as handle:
            handle.write(wav)
            handle.flush()
            command = [
                self._binary,
                "-m", self._model_path,
                "-f", handle.name,
                "--no-timestamps",
                "--no-prints",
            ]
            if self._language:
                command += ["-l", self._language]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise AudioBackendUnavailable(
                    f"whisper.cpp did not finish within {self._timeout}s"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise AudioBackendUnavailable(
                    f"whisper.cpp exited {exc.returncode}: "
                    f"{(exc.stderr or '').strip()[:300]}"
                ) from exc
        self.transcriptions += 1
        # Only surrounding whitespace and blank lines are dropped — the CLI emits
        # a trailing newline per line of output. Nothing inside a line is touched.
        return "\n".join(
            line.strip() for line in completed.stdout.splitlines() if line.strip()
        ).strip()


def available() -> bool:
    """Is any Whisper runtime present? Either counts — both are v4's model."""
    return module_available(_FASTER_WHISPER) or binary_available(_WHISPER_CLI) is not None


def install_hint() -> str:
    return f"{_INSTALL}   OR   {_CLI_INSTALL}"
