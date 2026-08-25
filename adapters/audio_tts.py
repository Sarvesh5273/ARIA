"""Concrete `TTSBackend`s — v4: "Cloud TTS (Sarvam AI / ElevenLabs) OR Kokoro
(fallback)".

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.TTSBackend`:

    def synthesize(self, text: str, prosody: Prosody) -> bytes   # WAV, or raises

`AudioPipeline._synthesize_with_fallback` tries the PRIMARY and falls back to the
local one on ANY exception (v4 "Graceful Degradation"). So the two slots want two
different implementations, and a failure in the primary must be an exception
rather than a silent empty result.

    ElevenLabsTTS   cloud primary (v4-named). stdlib urllib, opt-in key.
    KokoroTTS       local fallback (v4-named).
    SystemSayTTS    a RECORDED SUBSTITUTION for the fallback slot — see below.

THE SUBSTITUTION, FLAGGED RATHER THAN SLIPPED IN
-----------------------------------------------
`SystemSayTTS` drives macOS `say`. v4 names Kokoro for the local slot, so this IS
a deviation from the named provider — recorded here rather than left for someone
to discover.

Why it is a legitimate one: v4 states directly that "The TTS is a hot-swappable
tool. Aria is not," and the whole reason this Protocol exists is that the renderer
is interchangeable. Nothing downstream reads which renderer spoke — `speak()`
returns None and no soul state depends on it — so this is the leaf case
`audio_noop.py` already reasons about, not the embedding-model case.

What it BUYS is the thing no other backend here has: it works on this machine
today with zero installs, so the output chain is verifiable end to end rather than
only unit-tested. What it COSTS is voice quality and two of the three prosody
dimensions, which is why it is the fallback slot and not the primary.

PROSODY — THE HONEST FINDING, AND IT IS NOT COMFORTABLE
------------------------------------------------------
v4 Layer 5 locks three DIRECTIONS (the magnitudes are `TODO(F-7-prosody)`
placeholders, not spec):

    Pleasure  -> noise_scale    warmth / resonance
    Arousal   -> length_scale   speed, INVERSE
    Dominance -> pitch_shift    lower, more grounded pitch

**Only `length_scale` can be expressed by any of the three backends below.**
ElevenLabs exposes an explicit speed control, Kokoro exposes `speed`, and `say`
exposes a words-per-minute rate — all three are the same physical quantity as
`length_scale`, so mapping it is a unit conversion rather than an invention.

`noise_scale` and `pitch_shift` have NO counterpart in any of them. Two responses
were available and one of them is wrong:

  * Map them onto whatever knobs happen to exist — ElevenLabs' `stability` or
    `style`, for instance. REJECTED. Those control something else, the mapping
    would be invented, and it would make PAD appear to reach the voice while
    doing something unrelated to what v4 specifies. An invented coefficient with
    a feeling attached to it is exactly what the protected chain forbids.
  * Map what maps, and RECORD what does not. Taken. Each backend exposes
    `unmapped_prosody`, so a reader can see that two thirds of v4's Layer 5 voice
    expression currently reaches nothing.

That is a genuine gap in the OUTPUT chain, not in this adapter, and it needs a
provider with pitch and timbre control (or a ruling that the directions may be
approximated). Flagged under Rule 1, not resolved.

ALL THREE DIRECTIONS STAY COMPUTED, AND THE PROBE IS WHAT DECIDES WIRING
------------------------------------------------------------------------
`Prosody` carries all three fields on every turn regardless of what any backend
can do with them (`daemon/audio_pipeline.py`). A direction a provider cannot
express is DORMANT — computed, passed, ignored — never dropped from the dataclass.
That distinction is the point: deleting `noise_scale` and `pitch_shift` because
today's providers lack the knobs would make v4's Layer 5 unrecoverable without
re-deriving it, and would turn a provider limitation into a spec change.

`PROSODY_DIRECTIONS` is the full locked set, and each backend declares which of
them it cannot express by FIELD NAME. From that one declaration the base class
derives both `prosody_support` (the probe: field -> bool) and `unmapped_prosody`
(the same fact for humans), so the capability report and the gap report cannot
drift apart. Categorical, because a control exists or it does not — there is no
fraction of a pitch control, so no number belongs here.

Wiring follows the probe rather than a hardcoded assumption: a backend reporting
`prosody_support["pitch_shift"] is True` is one whose `synthesize` consumes it.
Today all three backends report support for `length_scale` only, so
`_speed_from` / `_wpm_from` are the only conversions that exist. When a provider
with real pitch or timbre control arrives, it declares fewer unmapped fields and
the probe reports the difference — the dormant values are already there to use.

FORMAT MARKERS ARE STRIPPED — ON THE AUDIO PATH ONLY (Resolution Log item 25)
-----------------------------------------------------------------------------
The Output Validation Gate has no FORMAT check: Addendum §4 fixes it at four
comparisons and all four are about content, so nothing upstream stops a stage
direction reaching a speaker. Measured, so this is not hypothetical — adversarial
bait against the real model produced one on 8/16 turns with the original Field 1
wording and 3/16 after Field 1 was sharpened to name the bracket syntax
(Resolution Log item 22). Prompt mitigation cuts it by two thirds and does not
close it.

**Architect ruling (item 25): strip markers where the text becomes SPEECH, and
nowhere else.** `_ProsodyRecorder._for_speech` removes what `_FORMAT_MARKER_RE`
matches — round and square bracket narration, `*action*` lines, headings, bullets,
numbered lists, `<think>` blocks, bold emphasis — immediately before synthesis.
Every other consumer keeps the text byte-for-byte: the printed transcript, the
session buffer, the graph, the Visual Layer.

WHY THIS IS NOT THE "STRIP IT IN THE ADAPTER" OPTION THAT WAS REJECTED. That
option would have edited her RESPONSE — the artefact the rest of the system treats
as what she said. This edits a RENDERING of it. "[I lean forward]" is not
pronounceable; a speech synthesiser is a device for pronouncing words, and
deciding that bracket syntax is not words is the same class of judgment as
choosing a sample rate. The response is unchanged, so nothing downstream of the
gate disagrees about what she said, and F-9b / LLM Interface Req 5 keeps verbatim
passthrough at the TRANSPORT layer, which is a different seam and is untouched.
(That rejection formerly cited "Resolution Log item 15", which resolves gate
OWNERSHIP and does not state the passthrough rule — see item 23.)

TWO THINGS THIS DOES NOT FIX, both measured and both recorded rather than papered
over:

  1. **Unmarked narration still gets through.** "I am sitting still. My attention
     is focused entirely on the words you are saying." is a stage direction in
     plain prose. No regex reaches it, and the thing that would is content
     judgment. The 3/16 figure counts MARKED narration only.
  2. **The defect still compounds.** Item 22 measured 4/8 becoming 8/8 as her own
     bracketed replies re-entered as session context and she imitated herself.
     The session buffer holds the unstripped text BY DESIGN — it is a faithful
     record of what was said — so stripping at the speaker does not interrupt
     that loop. It stops her being HEARD narrating; it does not stop her learning
     to narrate.

`last_text_had_format_markers` still records what was present in the ORIGINAL
text, before the strip. That ordering is deliberate: the flag is the measurement
surface item 22 was decided on, and reading it after the strip would make it
permanently False and quietly destroy the evidence that the ruling rests on.
`last_text_was_only_format_markers` is new and covers the case where a reply was
narration and nothing else, which now renders as silence rather than as prose.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from daemon.audio_pipeline import Prosody, TTSUnavailable

from adapters._provider import (
    AudioBackendUnavailable,
    binary_available,
    module_available,
    require_binary,
    require_module,
)
from adapters.audio_pcm import to_wav_bytes

# ---------------------------------------------------------------------------
# ElevenLabs (v4-named cloud primary).
# ---------------------------------------------------------------------------
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_API_KEY_ENV = "ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID_ENV = "ARIA_ELEVENLABS_VOICE_ID"
ELEVENLABS_MODEL_ENV = "ARIA_ELEVENLABS_MODEL"

#: Raw 16 kHz PCM, then wrapped in a WAV header locally. Requesting PCM rather
#: than the default MP3 is what keeps this dependency-free: an MP3 would need a
#: decoder before `PlaybackBackend.play(wav)` could take it.
ELEVENLABS_PCM_FORMAT = "pcm_16000"
ELEVENLABS_PCM_RATE = 16_000

DEFAULT_TIMEOUT_SECONDS = 30.0     # TODO(build-time): TTS request timeout

# ---------------------------------------------------------------------------
# macOS `say` (the recorded substitution for the local fallback slot).
# ---------------------------------------------------------------------------
_SAY = "say"
_SAY_INSTALL = "macOS built-in; on Linux use Kokoro (v4's named local fallback)"

#: `say`'s OWN documented default speaking rate. Not a chosen number — it is the
#: provider's baseline, and `length_scale` scales it.
SAY_DEFAULT_WPM = 175

#: `say` writes AIFF unless told otherwise. LEI16 at this rate is a plain 16-bit
#: mono WAV that the stdlib `wave` module and `afplay` both read.
SAY_DATA_FORMAT = "LEI16@22050"
SAY_SAMPLE_RATE = 22_050

_KOKORO = "kokoro"
_KOKORO_INSTALL = "pip install kokoro   (v4's named local TTS fallback)"

#: Markers that mean the text is FORMATTED rather than spoken prose. Used ONLY to
#: set an observability flag — never to strip. See the module docstring.
#:
#: SCOPE IS DELIBERATE, AND IT WAS MEASURED — AFTER GETTING IT WRONG ONCE.
#:
#: The first version matched only PARENTHESES, because the case recorded in the
#: tracker was "(Aria listens, her presence steady and calm...)". Then
#: `tools/measure_format_markers.py` reported 0/16 markers on deliberately
#: adversarial bait, which looked like Field 1's anti-narration clause holding.
#:
#: It was not. Printing the replies showed four of eight opening with:
#:
#:     [I lean forward just a fraction, settling into the space between us.]
#:     [I pause, letting the silence stretch out just a moment longer...]
#:     [My posture doesn't change. I simply hold the silence...]
#:
#: SQUARE brackets. The detector's false negative had turned a clear failure into
#: an apparent pass, and would have put "prompt-level mitigation is sufficient"
#: into the Resolution Log as a measured finding. So all three bracket
#: conventions are covered now: (), [], and *action* — the three ways an
#: instruct-tuned model writes a stage direction.
#:
#: Still LINE-START only for the bracket forms, and that limit is deliberate:
#: "it costs 5 dollars (roughly) which is fine" is ordinary speech, and flagging
#: mid-sentence parentheticals would make the signal useless.
#:
#: KNOWN GAP, recorded rather than papered over: narration with no marker at all
#: gets through. Measured on the same run — "I am sitting still. My attention is
#: focused entirely on the words you are saying." is a stage direction in plain
#: prose, and no lexical pattern catches it without judging content. A regex
#: cannot close that, and pretending otherwise would make this look like a guard
#: rather than the recorder it is.
_FORMAT_MARKER_RE = re.compile(
    r"(^\s*\([^)]*\))"            # narration opening a line — round brackets
    r"|(^\s*\[[^\]]*\])"          # narration opening a line — SQUARE brackets
    r"|(^\s*\*[^*\n]+\*\s*$)"     # *action* on its own line
    r"|(^\s{0,3}#{1,6}\s)"        # markdown heading
    r"|(^\s{0,3}[-*+]\s)"         # bullet
    r"|(^\s{0,3}\d+\.\s)"         # numbered list
    r"|(</?think(ing)?>)"         # reasoning trace
    r"|(\*\*)",                   # bold emphasis
    re.MULTILINE,
)


# ===========================================================================
# v4 Layer 5's three locked directions, and the capability probe over them.
# ===========================================================================
#: `Prosody` field -> the PAD axis it reads. This is the WHOLE set: v4 Layer 5
#: locks exactly three directions, and none may be dropped because a provider
#: cannot express it. All three are computed on every turn by the Audio Pipeline
#: whether or not anything downstream consumes them (`daemon/audio_pipeline.py`
#: `Prosody`); a backend that cannot express one leaves it DORMANT, not deleted.
PROSODY_DIRECTIONS: Dict[str, str] = {
    "noise_scale": "Pleasure",      # warmth / resonance
    "length_scale": "Arousal",      # speed, INVERSE
    "pitch_shift": "Dominance",     # lower, more grounded
}


def _has_format_markers(text: str) -> bool:
    return bool(_FORMAT_MARKER_RE.search(text or ""))


def strip_format_markers(text: str) -> str:
    """Remove what `_FORMAT_MARKER_RE` matches, for SPEECH ONLY.

    Deliberately the SAME pattern as the detector rather than a second, broader
    one. Item 22's measurements are expressed in terms of that pattern, so a strip
    that removed more than it reports would make the 3/16 figure describe
    something that no longer exists — and a mismatch between what is counted and
    what is acted on is how the original 0/16 near-miss happened.

    Consequences of reusing it, both intended:

      * The narration alternatives are LINE-ANCHORED (`^\\s*\\(...\\)`), so a
        mid-sentence parenthetical in ordinary prose — "it was (mostly) fine" — is
        left alone. Only narration occupying the start of a line goes, which is
        the form every measured failure took.
      * `**` is unanchored, because bold markers are not speech anywhere they
        appear. They are removed in place, leaving the emphasised words.

    Whitespace is then collapsed so removing a leading direction does not leave
    the sentence starting with a blank line or a stray gap.
    """
    if not text:
        return ""
    stripped = _FORMAT_MARKER_RE.sub("", text)
    # Collapse the holes the removal left: blank runs between lines, and leading
    # or trailing space on each surviving line.
    lines = [ln.strip() for ln in stripped.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


class _ProsodyRecorder:
    """Shared bookkeeping for what a backend could and could not express.

    Not a base class for behaviour — it holds two facts every TTS adapter here
    has to report, so the "we recorded the gap" claim is one implementation
    rather than three.
    """

    def __init__(self, unmapped: Sequence[str]) -> None:
        # `unmapped` names `Prosody` FIELDS. An unknown name is a programming
        # error and is refused loudly rather than silently creating a fourth
        # direction v4 does not have, or silently claiming support for a
        # misspelled one — which would read as a capability the voice lacks.
        unknown = [f for f in unmapped if f not in PROSODY_DIRECTIONS]
        if unknown:
            raise ValueError(
                f"not v4 Layer 5 prosody directions: {unknown}. "
                f"Expected any of {sorted(PROSODY_DIRECTIONS)}."
            )
        #: THE PROBE. Which of v4's three directions this provider can actually
        #: express — categorical, because a control either exists or it does not
        #: (there is no "60% of a pitch control", so no number belongs here).
        #: Derived from `unmapped` rather than declared separately, so the probe
        #: and the gap report cannot disagree.
        self.prosody_support: Dict[str, bool] = {
            field: field not in unmapped for field in PROSODY_DIRECTIONS
        }
        #: v4 Layer 5 dimensions this provider has no control for, rendered for
        #: humans. GENERATED from the same source as `prosody_support`. See the
        #: module docstring: mapping them onto unrelated knobs was rejected.
        self.unmapped_prosody: List[str] = [
            f"{field} ({PROSODY_DIRECTIONS[field]})" for field in unmapped
        ]
        #: Whether the LAST text handed over carried a format marker, measured on
        #: the ORIGINAL text before the strip. This is the surface item 22's
        #: measurements were taken on, so it must keep reporting what the model
        #: produced — reading it after the strip would pin it False forever and
        #: destroy the evidence the ruling rests on.
        self.last_text_had_format_markers = False
        #: The last text was narration and NOTHING else, so speech is silence.
        #: Separated from `empty_text_requests` because the causes differ: one is
        #: "she said nothing", the other is "she said only things that are not
        #: speakable". Both render as silence, and conflating them would hide a
        #: model producing pure stage direction behind a counter that reads as an
        #: upstream empty-candidate bug (item 21's territory, a different defect).
        self.last_text_was_only_format_markers = False
        self.syntheses = 0
        #: How many times `synthesize` was asked to render NOTHING. See
        #: `silence_for_empty_text` — this counter is the visibility that stops the
        #: no-content turn from being swallowed.
        self.empty_text_requests = 0

    def _for_speech(self, text: str) -> str:
        """Record what arrived, then return what should be SPOKEN (item 25).

        Every backend calls this instead of `_note` and synthesises the RESULT.
        One call site per backend, so a new backend cannot accidentally get the
        recording without the strip or the strip without the recording.

        Order matters: the flags describe the ORIGINAL text (see the attribute
        comments), and only the return value is stripped. The caller's own
        empty-text guard then catches a reply that was pure narration, which is
        why that case needs no separate branch here.
        """
        original = text or ""
        self.last_text_had_format_markers = _has_format_markers(original)
        self.syntheses += 1
        if not original.strip():
            self.empty_text_requests += 1
            self.last_text_was_only_format_markers = False
            return original

        spoken = strip_format_markers(original)
        # Non-empty in, nothing left to say: the whole reply was narration.
        self.last_text_was_only_format_markers = not spoken
        return spoken


def silence_for_empty_text(sample_rate: int) -> bytes:
    """A valid, zero-frame WAV — the audio for no words.

    WHY NOT RAISE, WHICH WAS THE FIRST ANSWER AND WAS WRONG
    ------------------------------------------------------
    An empty response text is possible: measured on the initiative path, where the
    local model returned `""` and Soul Filter's Output Gate passed it (its four
    checks are honesty / consistency / manipulation / care, and an empty string
    violates none). The `split_prompt` fix in `transport_ollama` removes the cause
    that was found, but a model may still return nothing on any turn.

    Raising `TTSUnavailable` on empty text turns that into a CRASH IN THE SOUL
    TICK: `AudioPipeline._synthesize_with_fallback` catches the primary's failure
    and tries the fallback, the fallback raises for the same reason — the input,
    not the provider — and the exception propagates out of `speak()`, out of
    `_route_initiative`, out of `soul_tick()`. Observed exactly that way.

    `TTSUnavailable` also means the wrong thing here. It is the signal for "this
    renderer cannot render right now, try the other one", and no fallback can help
    with empty input, so it makes the pipeline try a second provider pointlessly
    before failing anyway.

    So: nothing to say produces no sound, which is the honest rendering, and
    `empty_text_requests` records it. The counter matters — the alternative to a
    crash must not be a silence nobody can see.
    """
    return to_wav_bytes((), sample_rate=sample_rate)


class ElevenLabsTTS(_ProsodyRecorder):
    """`TTSBackend` for the v4-named cloud primary. stdlib urllib, no SDK.

    NETWORK POSTURE: this sends HER WORDS — the validated response text — to a
    third party on every turn it renders. Not the prompt, not internal state, not
    the five fields: the output only. Still worth stating plainly, and it is why
    the key is an explicit opt-in and `from_env` returns None without one.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: Optional[str] = None,
        base_url: str = ELEVENLABS_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        # Pleasure and Dominance have no counterpart in this API. Recorded, not
        # approximated onto `stability` / `style`, which control other things.
        super().__init__(unmapped=["noise_scale", "pitch_shift"])
        if not api_key or not voice_id:
            raise AudioBackendUnavailable(
                "cloud TTS needs both an API key and a voice id; no voice is "
                "chosen here, because picking one would choose how she sounds."
            )
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def describe(self) -> str:
        """Startup-report line. Reports key PRESENCE, never the key."""
        return (
            f"cloud TTS: elevenlabs voice={self._voice_id} "
            f"model={self._model_id or 'provider default'} (key present)"
        )

    def synthesize(self, text: str, prosody: Prosody) -> bytes:
        """Render `text` to WAV bytes, or raise `TTSUnavailable`.

        Raises the Protocol's own exception so `_synthesize_with_fallback` degrades
        to the local backend — that is the entire reason the fallback slot exists,
        and a technical failure here carries no information content and is never
        appraised (Addendum §5 logic).
        """
        text = self._for_speech(text)
        if not text.strip():
            # No request is made. Spending a paid API call to render nothing would
            # be worse than pointless, and the reasoning is the same as for the
            # local renderers — see `silence_for_empty_text`. Reached either
            # because she said nothing, or because the reply was only narration
            # (item 25) — `last_text_was_only_format_markers` tells them apart.
            return silence_for_empty_text(ELEVENLABS_PCM_RATE)
        payload: Dict[str, object] = {
            "text": text,                      # SPEAKABLE. See module docstring.
            "voice_settings": {"speed": _speed_from(prosody)},
        }
        if self._model_id:
            payload["model_id"] = self._model_id
        url = (
            f"{self._base_url}/text-to-speech/{self._voice_id}"
            f"?output_format={ELEVENLABS_PCM_FORMAT}"
        )
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "audio/pcm",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                pcm = response.read()
        except urllib.error.HTTPError as exc:
            raise TTSUnavailable(
                f"cloud TTS returned HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TTSUnavailable(f"cloud TTS unreachable: {exc.reason}") from exc
        except OSError as exc:
            raise TTSUnavailable(f"cloud TTS I/O failure: {exc}") from exc

        if not pcm:
            raise TTSUnavailable("cloud TTS returned an empty body")
        # Raw PCM in, WAV out — the Protocol says WAV and `PlaybackBackend.play`
        # takes WAV, so the container is added here rather than downstream.
        return _wrap_pcm(pcm, sample_rate=ELEVENLABS_PCM_RATE)

    @classmethod
    def from_env(
        cls, env: Optional[Dict[str, str]] = None
    ) -> Optional["ElevenLabsTTS"]:
        """Build from the environment, or None when unkeyed / no voice chosen."""
        import os
        env = os.environ if env is None else env
        key = (env.get(ELEVENLABS_API_KEY_ENV) or "").strip()
        voice = (env.get(ELEVENLABS_VOICE_ID_ENV) or "").strip()
        if not key or not voice:
            return None
        return cls(
            api_key=key,
            voice_id=voice,
            model_id=(env.get(ELEVENLABS_MODEL_ENV) or "").strip() or None,
        )


class KokoroTTS(_ProsodyRecorder):
    """`TTSBackend` for v4's named LOCAL fallback. Lazy provider import.

    Kokoro exposes `speed`, so `length_scale` maps directly; it exposes no timbre
    or pitch control, so the other two v4 directions are recorded as unmapped.
    """

    def __init__(
        self,
        *,
        voice: str,
        lang_code: str = "a",
        sample_rate: int = 24_000,
    ) -> None:
        super().__init__(unmapped=["noise_scale", "pitch_shift"])
        provider = require_module(
            _KOKORO, purpose="local TTS", install=_KOKORO_INSTALL
        )
        try:
            self._pipeline = provider.KPipeline(lang_code=lang_code)
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not initialise Kokoro: {exc}"
            ) from exc
        self._voice = voice
        self._sample_rate = sample_rate
        self._lock = threading.Lock()

    def synthesize(self, text: str, prosody: Prosody) -> bytes:
        text = self._for_speech(text)
        if not text.strip():
            return silence_for_empty_text(self._sample_rate)
        with self._lock:
            try:
                chunks: List[float] = []
                for _graphemes, _phonemes, audio in self._pipeline(
                    text, voice=self._voice, speed=_speed_from(prosody)
                ):
                    chunks.extend(float(x) for x in audio)
            except Exception as exc:
                raise TTSUnavailable(f"Kokoro failed to render: {exc}") from exc
        if not chunks:
            raise TTSUnavailable("Kokoro produced no audio")
        return to_wav_bytes(chunks, sample_rate=self._sample_rate)


class SystemSayTTS(_ProsodyRecorder):
    """`TTSBackend` driving macOS `say`. A RECORDED SUBSTITUTION for v4's Kokoro
    slot — see the module docstring for why the substitution is legitimate and
    what it costs.

    Its one real advantage: it needs nothing installed, so the output chain is
    verifiable on this machine today rather than only in unit tests.
    """

    def __init__(
        self,
        *,
        voice: Optional[str] = None,
        base_wpm: int = SAY_DEFAULT_WPM,
        binary: str = _SAY,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(unmapped=["noise_scale", "pitch_shift"])
        self._binary = require_binary(
            binary, purpose="system TTS", install=_SAY_INSTALL
        )
        self._voice = voice
        self._base_wpm = base_wpm
        self._timeout = timeout

    def synthesize(self, text: str, prosody: Prosody) -> bytes:
        """Render to a 16-bit mono WAV via `say -o`, and read the bytes back.

        Rate is `base_wpm / length_scale`: `length_scale` is a duration
        multiplier, so dividing converts it to a speed. The base is `say`'s own
        documented default, not a chosen value, which is what keeps this a unit
        conversion rather than an invented magnitude.
        """
        text = self._for_speech(text)
        if not text.strip():
            return silence_for_empty_text(SAY_SAMPLE_RATE)
        rate = _wpm_from(prosody, base_wpm=self._base_wpm)
        with tempfile.TemporaryDirectory() as workdir:
            out = Path(workdir) / "speech.wav"
            command = [
                self._binary,
                "-o", str(out),
                "--data-format", SAY_DATA_FORMAT,
                "-r", str(rate),
            ]
            if self._voice:
                command += ["-v", self._voice]
            # `--` then the text, so a response beginning with a hyphen is not
            # parsed as a flag. Passed as an argv element, never through a shell.
            command += ["--", text]
            try:
                subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise TTSUnavailable(
                    f"system TTS did not finish within {self._timeout}s"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise TTSUnavailable(
                    f"system TTS exited {exc.returncode}: "
                    f"{(exc.stderr or '').strip()[:200]}"
                ) from exc
            if not out.is_file() or out.stat().st_size == 0:
                raise TTSUnavailable("system TTS produced no audio")
            return out.read_bytes()


# ===========================================================================
# Prosody conversion. Only `length_scale` has a counterpart in any provider —
# see the module docstring. These are unit conversions, not new magnitudes.
# ===========================================================================

def _speed_from(prosody: Prosody) -> float:
    """`length_scale` (a duration multiplier) -> a speed multiplier.

    v4 Layer 5: higher arousal = faster speech, and `map_pad_to_prosody` already
    encodes that as a SHORTER `length_scale`. Speed is its reciprocal, so this
    preserves the locked direction exactly and introduces nothing.

    Guards against a non-positive multiplier, which would be a division by zero
    or a negative speed. That is not a tuning choice — those values have no
    meaning as a duration.
    """
    length_scale = prosody.length_scale
    if length_scale <= 0:
        return 1.0
    return 1.0 / length_scale


def _wpm_from(prosody: Prosody, *, base_wpm: int) -> int:
    """The same conversion expressed in `say`'s words-per-minute units."""
    return max(1, int(round(base_wpm * _speed_from(prosody))))


def _wrap_pcm(pcm: bytes, *, sample_rate: int) -> bytes:
    """Raw little-endian int16 PCM -> WAV, using the shared conversion."""
    from adapters.audio_pcm import from_int16_bytes
    return to_wav_bytes(from_int16_bytes(pcm), sample_rate=sample_rate)


def kokoro_available() -> bool:
    return module_available(_KOKORO)


def say_available() -> bool:
    return binary_available(_SAY) is not None


def available() -> bool:
    """Is ANY local renderer present? The cloud primary is opt-in by key, so the
    question that decides whether the output chain can work is about the
    fallback."""
    return kokoro_available() or say_available()


def install_hint() -> str:
    return _KOKORO_INSTALL
