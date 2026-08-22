"""No-op `AudioPipelinePort` — the text-first stand-in for Module 7.

WHAT THIS SATISFIES
-------------------
`daemon.aria_daemon.AudioPipelinePort`: `speak`, `stop_playback`,
`play_thinking_sound`, `play_reconsideration_sound`.

WHY A STUB IS CORRECT HERE, WHEN IT IS NOT FOR THE EMBEDDING MODEL
------------------------------------------------------------------
Audio is a LEAF. Nothing downstream reads what it did: `speak()` returns None,
the Daemon ignores the return, and no soul state depends on the result. The
seven real audio backends behind Module 7 change what the user HEARS, not what
Aria computes or remembers. Substituting a no-op therefore changes no behaviour
inside the system.

That is exactly the property `EmbeddingModel` lacks — four behaviours read its
output and every one of them changes when the vectors change. "Can this be
stubbed?" is answered by whether anything downstream reads the result, not by
how easy the stub is to write.

INBOUND AUDIO IS NOT ON THIS PORT. `AudioPipelinePort` is output-side only —
speech-to-text arrives as the `user_text` argument of `route_inbound_turn`. So a
text REPL needs no inbound substitute at all; it simply IS the transcription.

This class does not print. The REPL owns the terminal and prints the response it
already holds; a `speak()` that also printed would double every line.
"""

from __future__ import annotations

from typing import List


class NoOpAudioPipeline:
    """Satisfies `AudioPipelinePort` and does nothing but record.

    The counters exist so a bring-up can confirm the Daemon really is driving
    the port (thinking sound before generation, one `speak` per turn, a
    reconsideration sound on a Soul Filter retry) without a speaker attached.
    """

    def __init__(self) -> None:
        self.spoken: List[str] = []
        self.thinking_sounds: List[str] = []
        self.stops = 0
        self.reconsiderations = 0

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop_playback(self) -> None:
        # F4 / barge-in is exactly one stop and nothing else — it carries no
        # information content (Addendum §5) and must not touch PAD, the graph,
        # or appraisal. With no playback to stop, counting is all there is.
        self.stops += 1

    def play_thinking_sound(self, sound: str) -> None:
        self.thinking_sounds.append(sound)

    def play_reconsideration_sound(self) -> None:
        self.reconsiderations += 1
