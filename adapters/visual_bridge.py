"""Drive the Visual Layer from signals the Daemon ALREADY emits.

THE PROBLEM THIS SOLVES, AND WHY IT IS NOT A CONSTRUCTOR CHANGE
---------------------------------------------------------------
`AriaDaemon` takes no visual parameter. Module 10 knows this and says so — its
flag disposition records the driver-loop and signal wiring as "top-of-tree
BUILD-TIME wiring, not this module's concern. The contract is exposed here; the
Daemon is unchanged."

So the tempting move is to add `visual=` to `AriaDaemon.__init__` and call
`set_speaking` around its existing `self._audio.speak(...)`. That would modify an
APPROVED module's public constructor to wire a leaf, which needs a ruling rather
than an afternoon — and it is unnecessary, because Module 10's own docstring
already names the seam:

    "the output-pending boundary around `audio.speak()` -> set_speaking(True/
     False); the LLM Interface's `serving_from_local` -> set_cloud_available(...)"

The speaking boundary IS `audio.speak()`. The Daemon already calls it, on every
path — ordinary turns, the initiative turn, and the cloud proposal prompt. So
DECORATING the audio port gets the signal for free, from the exact boundary the
spec names, with no soul module touched.

    AriaDaemon --speak()--> SpeakingSignalAudio --speak()--> AudioPipeline
                                  |
                                  +--> VisualLayer.set_speaking(True/False)

`SpeakingSignalAudio` satisfies `AudioPipelinePort` itself, so it drops into the
same constructor slot the no-op and the real pipeline use.

WHY set_speaking(False) IS IN A `finally`
----------------------------------------
If TTS raises, she is not speaking — and leaving the flag True would freeze her
mouth mid-word for the rest of the session while the zone machinery kept running.
The observed empty-text crash (see `audio_tts.silence_for_empty_text`) is exactly
the shape that would have done it.

CLOUD AVAILABILITY — AND A READOUT THAT NO LONGER MEANS WHAT IT SAYS
-------------------------------------------------------------------
Module 10 names `LLMInterface.serving_from_local` as the degradation trigger.
**Do not wire that, and this module deliberately does not.**

    @property
    def serving_from_local(self) -> bool:
        # docstring: "True while the local fallback is resident
        #             (cloud is currently down)."
        return self._local.is_loaded

That equivalence held under v4's Brain Structure, where the local model "loads on
cloud failure, unloads on restore" — so resident really did imply cloud-down. Track
A inverted it: `AriaDaemon.startup()` calls `BackendRouter.ensure_local_loaded()`,
Gemma is pinned resident from boot, and it is the DEFAULT voice rather than a
fallback. So `serving_from_local` is True during entirely healthy operation, and
`set_cloud_available(not serving_from_local)` would park her face in
INWARD_WAITING permanently.

FLAGGED, NOT PATCHED (Rule 1 / Rule 2). Two things are genuinely unresolved and
neither is an adapter's to decide:

  1. `serving_from_local`'s docstring is now stale in `daemon/llm_interface.py`.
     The property is a correct read-through of `is_loaded`; the parenthetical
     "(cloud is currently down)" is what Track A falsified.
  2. More deeply: v4's degradation state assumes CLOUD-PRIMARY, and the architect's
     current design is local-primary with cloud proposed. Under that design "cloud
     unavailable" is the ordinary resting state, not a degradation — so what should
     trigger the inward/waiting loop is an open question, not a wiring detail.

What this module wires instead is the OTHER trigger Module 10's own docstring
names, which is well-defined under either design: `LLMUnavailableError` — no
backend could answer this turn. `report_turn_failed()` / `report_turn_served()`
carry it, and `main.py`'s REPL already catches exactly those exceptions.

NOTHING HERE DECIDES ANYTHING. Both classes forward a boolean and hold no PAD,
graph, appraisal or state handle.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class SpeakingSignalTarget(Protocol):
    """The slice of `VisualLayerPort` this bridge drives. Deliberately narrower
    than the full port: a bridge that could call `refresh()` would be a second
    driver of the visual loop, and two drivers on one gate is how the 8-second
    stability rule stops being observable."""

    def set_speaking(self, is_speaking: bool) -> None:
        ...


class SpeakingSignalAudio:
    """An `AudioPipelinePort` that also reports the speaking boundary onward.

    Satisfies `daemon.aria_daemon.AudioPipelinePort` by delegation, so it goes in
    the same constructor slot as `NoOpAudioPipeline` or a real `AudioPipeline` and
    the Daemon cannot tell the difference.

    Holds the wrapped port and the visual target. No soul state.
    """

    def __init__(self, *, audio, visual: SpeakingSignalTarget) -> None:
        self._audio = audio
        self._visual = visual
        self.speaking_transitions: List[bool] = []   # observability only

    # -- AudioPipelinePort --------------------------------------------------

    def speak(self, text: str) -> None:
        """Signal TALKING, speak, then signal IDLE — whatever happens.

        The variant change is ungated by design (Module 10: a talking<->idle
        change "is NOT subject to the 8 s zone gate"), so the mouth tracks the
        voice rather than the zone timer.

        `finally` is load-bearing: a TTS failure must not leave her mouth frozen
        open for the rest of the session.
        """
        self._signal(True)
        try:
            self._audio.speak(text)
        finally:
            self._signal(False)

    def stop_playback(self) -> None:
        """F4 / barge-in. Stops the audio and closes her mouth.

        Addendum §5 makes F4 "a functional audio stop mechanism only ... No PAD
        effect, no appraisable event, no graph write, nothing." A variant signal is
        none of those: it is the face agreeing with the fact that sound stopped.
        Leaving the talking variant playing after a barge-in would show her still
        speaking, which is the one thing the stop was for.
        """
        self._audio.stop_playback()
        self._signal(False)

    def play_thinking_sound(self, sound: str) -> None:
        """Forwarded unchanged. NOT a speaking signal: a thinking sound plays
        while she is NOT talking (v4 Layer 5 covers the pause before generation),
        so raising the talking variant here would move her mouth over a breath."""
        self._audio.play_thinking_sound(sound)

    def play_reconsideration_sound(self) -> None:
        """Forwarded unchanged, for the same reason."""
        self._audio.play_reconsideration_sound()

    # -- passthrough for the wiring layer's diagnostics ---------------------

    @property
    def wrapped(self):
        """The real port underneath, so `:state`-style readouts can reach the
        pipeline's own counters without this class re-exposing each one."""
        return self._audio

    def _signal(self, is_speaking: bool) -> None:
        self.speaking_transitions.append(is_speaking)
        self._visual.set_speaking(is_speaking)


class CloudAvailabilityReporter:
    """Turns "a backend answered / did not answer" into Module 10's degradation
    signal.

    The trigger is `LLMUnavailableError`, not `serving_from_local` — see the module
    docstring for why that readout is stale under Track A and why the alternative
    is the well-defined one.

    Deliberately EDGE-TRIGGERED. `set_cloud_available` already ignores a repeated
    value, but filtering here as well means the reporter can be called on every
    turn without the wiring layer needing to track state — which is what makes it
    safe to drop into a REPL's success and failure paths without conditionals.
    """

    def __init__(self, *, visual) -> None:
        self._visual = visual
        self._available: Optional[bool] = None
        self.transitions: List[bool] = []      # observability only

    def report_turn_served(self) -> None:
        """A backend answered. Resume PAD-driven zones — with no announcement
        (v4: "Full voice returns naturally, no announcement")."""
        self._set(True)

    def report_turn_failed(self) -> None:
        """No backend could answer (`LLMUnavailableError`, or the transport error
        that reached the caller). The inward/waiting loop plays: "not sleeping ...
        but withdrawn. Present but quiet"."""
        self._set(False)

    @property
    def available(self) -> Optional[bool]:
        """Last reported state, or None before the first report."""
        return self._available

    def _set(self, available: bool) -> None:
        if available == self._available:
            return
        self._available = available
        self.transitions.append(available)
        self._visual.set_cloud_available(available)
