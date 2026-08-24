"""Assemble the seven audio backends into a real `AudioPipeline`, or say why not.

WHY THIS FILE EXISTS
--------------------
`AudioPipeline.__init__` takes nine injected collaborators. Constructing them in
`main.py` would put seven provider decisions in the wiring layer, where they would
sit next to the soul-module construction order and be read as equally load-bearing.
They are not: they are leaf choices, and this is the one place that makes them.

`preflight()` is the more useful half. Voice needs five providers this project does
not ship, and the honest answer to "can she talk yet" is a per-backend report — not
an ImportError from whichever one happened to be constructed first.

WHAT IS ACTUALLY AVAILABLE ON A BARE MACHINE
--------------------------------------------
Measured on the dev machine (macOS, venv with pytest only):

    capture       sounddevice        MISSING
    wake word     pvporcupine        MISSING   (hotkey fallback needs nothing)
    speaker       torch              MISSING
    VAD           onnxruntime        MISSING
    STT           faster-whisper     MISSING
    TTS           say                PRESENT   (Kokoro missing)
    playback      afplay             PRESENT

So the OUTPUT chain works today with zero installs and the INPUT chain does not.
That asymmetry is worth knowing before installing anything, because output is the
half that changes what a user experiences per turn, and it is also the half where
the format-guard ruling now has teeth (see `audio_tts.py`).

THE INPUT CHAIN IS NOT ON THE DAEMON'S PORT
-------------------------------------------
Worth restating because it decides what "half a stack" means. `AudioPipelinePort`
is OUTPUT ONLY — `speak`, `stop_playback`, `play_thinking_sound`,
`play_reconsideration_sound`. Transcribed text arrives at the Daemon as
`route_inbound_turn(user_text=...)`, so STT was never a port.

`build_output_only()` exists because of that: a pipeline whose output chain is real
and whose input backends are absent still satisfies everything the Daemon drives,
and a text REPL keeps supplying the transcription. She can SPEAK before she can
HEAR, and that is a genuinely useful intermediate state rather than a broken one.

The refusing stubs it injects for the five input backends are NOT a substitute for
those backends. Each raises if called, so `capture_turn()` fails loudly rather than
returning a plausible None that would read as "nobody spoke". Nothing in the wired
path calls them, because nothing calls `capture_turn()` yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from daemon.audio_pipeline import (
    SAMPLE_RATE_HZ,
    AudioPipeline,
    AudioSegment,
    Prosody,
    TTSUnavailable,
)

from adapters import audio_capture, audio_playback, audio_speaker, audio_stt, audio_tts, audio_vad, audio_wake
from adapters._provider import AudioBackendUnavailable
from adapters.audio_playback import CommandLinePlayback
from adapters.audio_tts import ElevenLabsTTS, KokoroTTS, SystemSayTTS
from adapters.audio_wake import HotkeyWakeWord


@dataclass(frozen=True)
class BackendStatus:
    """One backend's availability, for a report a human reads."""
    name: str
    protocol: str
    provider: str
    present: bool
    hint: str
    note: str = ""

    def line(self) -> str:
        mark = "ok     " if self.present else "MISSING"
        tail = f"  {self.note}" if self.note else ""
        return f"  {mark} {self.name:10s} {self.protocol:28s} {self.provider}{tail}"


def preflight() -> Sequence[BackendStatus]:
    """Which of the seven backends could be built right now. Never raises.

    The wake-word row reports the PRIMARY (Porcupine). `HotkeyWakeWord` needs no
    provider and is always available, which is noted rather than allowed to make
    the row read green — v4 calls the hotkey a fallback, and a report that hid the
    difference would let "wake word: ok" mean "there is a keyboard".
    """
    return (
        BackendStatus(
            "capture", "CaptureBackend", "sounddevice",
            audio_capture.available(), audio_capture.install_hint(),
        ),
        BackendStatus(
            "wake", "WakeWordBackend", "pvporcupine",
            audio_wake.available(), audio_wake.install_hint(),
            note="hotkey fallback needs no provider and is always usable",
        ),
        BackendStatus(
            "speaker", "SpeakerVerificationBackend", "torch (silero)",
            audio_speaker.available(), audio_speaker.install_hint(),
            note="gates WHO she listens to — see audio_speaker.py",
        ),
        BackendStatus(
            "vad", "VADBackend", "onnxruntime (silero)",
            audio_vad.available(), audio_vad.install_hint(),
        ),
        BackendStatus(
            "stt", "STTBackend", "faster-whisper | whisper-cli",
            audio_stt.available(), audio_stt.install_hint(),
        ),
        BackendStatus(
            "tts", "TTSBackend", "kokoro | say",
            audio_tts.available(), audio_tts.install_hint(),
            note="say is a RECORDED substitution for v4's Kokoro slot",
        ),
        BackendStatus(
            "playback", "PlaybackBackend", " | ".join(audio_playback.PLAYER_CANDIDATES),
            audio_playback.available(), audio_playback.install_hint(),
        ),
    )


def preflight_report() -> str:
    rows = preflight()
    lines = [status.line() for status in rows]
    missing = [s for s in rows if not s.present]
    if missing:
        lines.append("")
        lines.append("  to fill the gaps:")
        for status in missing:
            lines.append(f"    {status.name:10s} {status.hint}")
    return "\n".join(lines)


def output_chain_ready() -> bool:
    """Can she SPEAK? The only question `AudioPipelinePort` actually asks."""
    return audio_tts.available() and audio_playback.available()


def input_chain_ready() -> bool:
    """Can she HEAR? Needs capture, VAD and STT at minimum. The wake word can fall
    back to a hotkey (v4's own alternative) and speaker verification is separate —
    see `build_input_backends` on why its absence is not silently tolerated."""
    return (
        audio_capture.available()
        and audio_vad.available()
        and audio_stt.available()
    )


# ===========================================================================
# Refusing stubs for the input slots. NOT substitutes — see the module docstring.
# ===========================================================================

class _Absent:
    """Raises whatever it is asked. One class for all five input Protocols.

    The alternative — returning a neutral value — is what makes an absent backend
    dangerous: a capture that returns silence, a VAD that returns 0.0 and a speaker
    check that returns 1.0 all look like ordinary operation, and `capture_turn()`
    would return None as if nobody had spoken. Raising means an absent backend can
    only ever be a visible error.
    """

    def __init__(self, slot: str, hint: str) -> None:
        self._slot = slot
        self._hint = hint

    def _refuse(self):
        raise AudioBackendUnavailable(
            f"the {self._slot} backend is not installed, so inbound audio cannot "
            f"run. This is not a stub standing in for it — nothing downstream may "
            f"treat its absence as silence. Install it with:  {self._hint}"
        )

    # CaptureBackend / WakeWordBackend / SpeakerVerificationBackend /
    # VADBackend / STTBackend — every method refuses.
    def read(self) -> AudioSegment: self._refuse()
    def detect(self, audio: AudioSegment) -> bool: self._refuse()
    def similarity(self, audio: AudioSegment) -> float: self._refuse()
    def speech_probability(self, chunk: AudioSegment) -> float: self._refuse()
    def transcribe(self, audio: AudioSegment) -> str: self._refuse()


# ===========================================================================
# Builders.
# ===========================================================================

def build_tts_pair(
    *,
    env: Optional[Dict[str, str]] = None,
    voice: Optional[str] = None,
    kokoro_voice: Optional[str] = None,
):
    """Return `(primary, fallback)` for the output chain.

    v4's shape is cloud primary, local fallback. Resolved by what exists:

      * primary  = ElevenLabs when keyed, else the local renderer. Putting the
        local one in BOTH slots is deliberate rather than lazy: `AudioPipeline`
        requires both, its fallback path catches any exception from the primary,
        and a single renderer failing twice is honest — it does not pretend a
        second provider was tried.
      * fallback = Kokoro (v4's named local) when installed, else `say` (a
        recorded substitution; see `audio_tts.py`).
    """
    if kokoro_voice and audio_tts.kokoro_available():
        local = KokoroTTS(voice=kokoro_voice)
    elif audio_tts.say_available():
        local = SystemSayTTS(voice=voice)
    else:
        raise AudioBackendUnavailable(
            f"no local TTS renderer. {audio_tts.install_hint()}"
        )
    cloud = ElevenLabsTTS.from_env(env)
    return (cloud or local), local


def build_output_only(
    *,
    pad_source,
    env: Optional[Dict[str, str]] = None,
    voice: Optional[str] = None,
    kokoro_voice: Optional[str] = None,
    clip_dir: Optional[str] = None,
    player: Optional[str] = None,
) -> AudioPipeline:
    """A real `AudioPipeline` whose OUTPUT chain works and whose input backends
    refuse. Satisfies everything `AudioPipelinePort` drives.

    `pad_source` must be the PAD engine — the pipeline reads it at TTS time for
    prosody (v4 Layer 5, a presentation read, never a write; the seam exposes only
    `get_current_pad()` so a write is not expressible).
    """
    primary, fallback = build_tts_pair(
        env=env, voice=voice, kokoro_voice=kokoro_voice
    )
    playback = CommandLinePlayback(player=player, clip_dir=clip_dir)
    return AudioPipeline(
        pad_source=pad_source,
        capture=_Absent("capture", audio_capture.install_hint()),
        wake_word=_Absent("wake word", audio_wake.install_hint()),
        speaker_verification=_Absent("speaker verification", audio_speaker.install_hint()),
        vad=_Absent("VAD", audio_vad.install_hint()),
        stt=_Absent("STT", audio_stt.install_hint()),
        tts_primary=primary,
        tts_fallback=fallback,
        playback=playback,
    )


def build_full(
    *,
    pad_source,
    porcupine_access_key: Optional[str] = None,
    porcupine_keyword_paths: Optional[Sequence[str]] = None,
    vad_model_path: Optional[str] = None,
    speaker_model_path: Optional[str] = None,
    voiceprint_path: Optional[str] = None,
    whisper_model_size: str = audio_stt.SPEC_MODEL_SIZE,
    env: Optional[Dict[str, str]] = None,
    voice: Optional[str] = None,
    kokoro_voice: Optional[str] = None,
    clip_dir: Optional[str] = None,
    player: Optional[str] = None,
    device: Optional[object] = None,
) -> AudioPipeline:
    """The complete seven-backend pipeline, input chain included.

    Every model path is a REQUIRED argument when its backend is used. Nothing here
    downloads weights, invents a path, or picks a wake word — those are the
    decisions an adapter must not make on the operator's behalf.

    SPEAKER VERIFICATION IS NOT OPTIONAL-BY-OMISSION. Without a voiceprint the
    real backend returns -1.0 for everyone and no turn ever passes the 0.75 gate,
    which reads as "she stopped hearing me". So a missing voiceprint is refused
    here with that consequence named, rather than producing a system that runs and
    ignores you.
    """
    if not vad_model_path:
        raise AudioBackendUnavailable(
            "inbound audio needs a Silero VAD model path (v4: ONNX, ~2 MB). "
            "Nothing is downloaded here."
        )
    if not speaker_model_path or not voiceprint_path:
        raise AudioBackendUnavailable(
            "inbound audio needs both a speaker-verification model and an "
            "enrolled voiceprint (v4: voiceprint.pt). Without a voiceprint the "
            "0.75 cosine gate rejects every speaker, so she would appear to have "
            "stopped listening rather than to be misconfigured."
        )

    wake = (
        audio_wake.PorcupineWakeWord(
            access_key=porcupine_access_key,
            keyword_paths=porcupine_keyword_paths,
        )
        if porcupine_access_key and porcupine_keyword_paths
        else HotkeyWakeWord()
    )
    primary, fallback = build_tts_pair(
        env=env, voice=voice, kokoro_voice=kokoro_voice
    )
    return AudioPipeline(
        pad_source=pad_source,
        capture=audio_capture.SoundDeviceCapture(device=device),
        wake_word=wake,
        speaker_verification=audio_speaker.SileroSpeakerVerification(
            model_path=speaker_model_path, voiceprint_path=voiceprint_path
        ),
        vad=audio_vad.SileroVAD(model_path=vad_model_path),
        stt=audio_stt.FasterWhisperSTT(model_size=whisper_model_size),
        tts_primary=primary,
        tts_fallback=fallback,
        playback=CommandLinePlayback(player=player, clip_dir=clip_dir),
    )
