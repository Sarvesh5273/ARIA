"""`ModelTransport` for a cloud tier that has no adapter yet.

WHY THIS EXISTS — IT IS NOT A STUB IN THE USUAL SENSE
----------------------------------------------------
`LLMInterface.__init__` requires BOTH `cloud_transport` and `local_transport`
(no defaults), and `BackendRouter.__init__` requires all three tiers. So a
text-first bring-up cannot construct either object without something in the two
cloud slots — even though the honest state of the project is that no Groq or
Azure adapter has been written.

This class IS that honest state, expressed as code rather than as an omission:

    is_healthy() -> False        explicitly unhealthy, not UNKNOWN
    generate()   -> raises LLMTransportError

Both answers are true. The tier is not configured, so it is not reachable, and
saying so explicitly is better than the alternatives:

  * Omitting `is_healthy` entirely would make the tier UNKNOWN. FLAG B fixed
    UNKNOWN so it no longer reads as healthy, so routing would behave the same —
    but "we have not written this yet" is a definite answer, and reporting a
    definite thing as unknown throws information away.
  * Passing the local transport into the cloud slots would be worse than
    useless: `LLMInterface`'s internal path unloads `local` whenever `cloud`
    succeeds, so with one object in both slots every successful turn would evict
    the resident model.

WHAT THIS PRODUCES, AND WHY IT IS THE RIGHT SHAPE
-------------------------------------------------
With both cloud tiers explicitly unhealthy, `BackendRouter.select()`:

  * never proposes a tier-2 escalation (the branch requires `health["azure"]`),
    so the pause-and-ask never fires and the proposal state machine stays idle;
  * skips Groq (the branch requires `health["groq"]`);
  * serves every turn from Gemma.

Which is the architect's stated design — Gemma is the default voice for
conversation, Groq is a fallback reserved for future tools/search, and the
reasoning tier is proposed, never taken silently. A text-first bring-up on the
local model is therefore not a degraded mode; it is the intended one, with the
two fallbacks absent.

Replacing this is additive: write a real adapter, satisfy `ModelTransport` plus
`HealthProbe`, and pass it in the same slot. Nothing else changes. The tracker's
`needs-adapter` row ("cloud adapters still expose no is_healthy()") is about
exactly that work.
"""

from __future__ import annotations

from daemon.llm_interface import AssembledPrompt, LLMTransportError

DEFAULT_REASON = "no adapter is configured for this backend tier"


class UnconfiguredTransport:
    """A backend tier with no adapter. Explicitly unhealthy; never generates."""

    #: "I am the absence of an adapter, not a broken one." Read by
    #: `LLMInterface.last_route` (via `getattr`, so a real adapter never has to
    #: declare it) to report `no_cloud_adapter` instead of
    #: `cloud_unhealthy_fallback`. The two are indistinguishable from the
    #: exception alone — both raise `LLMTransportError` — but only one of them is
    #: degradation. A local-first bring-up with no cloud credentials is the
    #: INTENDED state, as the module docstring above argues, and it should not
    #: read as an outage.
    is_configured = False

    def __init__(self, *, tier_name: str, reason: str = DEFAULT_REASON) -> None:
        self._tier_name = tier_name
        self._reason = reason
        self.generate_attempts = 0

    @property
    def tier_name(self) -> str:
        return self._tier_name

    def generate(self, prompt: AssembledPrompt) -> str:
        """Always raises `LLMTransportError` — the one signal that means
        "this backend is unavailable".

        Reaching here is not an error in this adapter: it means a caller chose
        this tier anyway, which an explicit user override ("use cloud") is
        allowed to do — overrides win unconditionally and are deliberately not
        health-gated. The failure surfaces at generate() time by design.
        """
        self.generate_attempts += 1
        raise LLMTransportError(
            f"backend tier {self._tier_name!r} is unavailable: {self._reason}"
        )

    def is_healthy(self) -> bool:
        """False, explicitly. Not UNKNOWN — "not written yet" is an answer."""
        return False
