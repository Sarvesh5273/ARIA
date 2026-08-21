"""Tests for BackendRouter (`daemon/backend_router.py`).

Plain pytest, NO hypothesis (matches Modules 1-10 house style). Fakes, not
mocks. Assert PROPERTIES and CATEGORICAL OUTCOMES, never the placeholder
magnitudes (`HEALTH_CACHE_TTL_SECONDS`) or exact lexicon membership.

These prove:
  * classify() is a pure, word-boundary-anchored keyword match — categorical
    ("propose_tier_2" / "tier_1_ok"), never a score.
  * set_override() is session-scoped, validated against VALID_TIERS, and
    (per select()) WINS UNCONDITIONALLY over both the classifier and health.
  * check_health() is CACHED for HEALTH_CACHE_TTL_SECONDS and returns a copy
    each time (mutating the returned dict cannot corrupt the cache), and it
    reports the HEALTHY SET: _probe_one's UNKNOWN (a non-local transport with
    no HealthProbe) is NOT healthy, so nothing routes optimistically (FLAG B).
  * select() implements the exact fallback chain: override -> propose (if
    tier-2-shaped AND azure healthy) -> gemma (only if loaded; the DEFAULT
    VOICE for conversation) -> groq (fallback only) -> None.
  * BackendRouter is structurally INFRASTRUCTURE: it holds no Soul-state
    handle (vars() scan) and imports no Soul module (AST import scan), mirroring
    tests/test_visual_layer.py::test_module_imports_no_write_capable_or_gui_module.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone

import pytest

import daemon.backend_router as br_mod
from daemon.backend_router import (
    BackendRouter,
    HEALTH_CACHE_TTL_SECONDS,
    TIER_2_KEYWORDS,
    VALID_TIERS,
)

T0 = datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# Test doubles — fakes, not mocks.
# ===========================================================================

class FakeCloudTransport:
    """Satisfies ModelTransport + the optional HealthProbe. `healthy` is
    settable so tests can drive the selection chain."""

    def __init__(self, name, healthy=True):
        self.name = name
        self.healthy = healthy
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return f"{self.name} reply"

    def is_healthy(self):
        return self.healthy


class FakeLocalTransport:
    """Satisfies LocalModelTransport + HealthProbe. Note is_loaded is a
    PROPERTY, mirroring the real Protocol."""

    def __init__(self, healthy=True, loaded=True):
        self.healthy = healthy
        self._loaded = loaded
        self.prompts = []
        self.load_calls = 0

    @property
    def is_loaded(self):
        return self._loaded

    def load(self):
        self._loaded = True
        self.load_calls += 1

    def unload(self):
        self._loaded = False

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "gemma reply"

    def is_healthy(self):
        return self.healthy


class ProbelessCloudTransport:
    """Satisfies ModelTransport but NOT HealthProbe — no is_healthy() at all.
    This is what a real Groq/Azure adapter looks like before anyone writes a
    cheap reachability probe for it, and it is the FLAG B case: the router
    cannot know whether it is up, so it must not assume it is."""

    def __init__(self, name):
        self.name = name
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return f"{self.name} reply"


class ProbelessLocalTransport:
    """LocalModelTransport with no HealthProbe: residency IS a real answer, so
    the local tier is never UNKNOWN."""

    def __init__(self, loaded=True):
        self._loaded = loaded
        self.prompts = []

    @property
    def is_loaded(self):
        return self._loaded

    def load(self):
        self._loaded = True

    def unload(self):
        self._loaded = False

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "gemma reply"


class FakeClock:
    """Deterministic clock so the cache test needs no sleep()."""

    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t = self.t + timedelta(seconds=seconds)


def make_router(*, gemma=None, groq=None, azure=None, clock=None):
    """Builder mirroring make_daemon / make_pipeline: returns the router plus
    its three fakes for direct assertions."""
    gemma = gemma if gemma is not None else FakeLocalTransport()
    groq = groq if groq is not None else FakeCloudTransport("groq")
    azure = azure if azure is not None else FakeCloudTransport("azure")
    clock = clock if clock is not None else FakeClock(T0)
    router = BackendRouter(
        gemma_transport=gemma,
        groq_transport=groq,
        azure_transport=azure,
        clock=clock,
    )
    return router, gemma, groq, azure, clock


# ===========================================================================
# 1) classify() — pure, categorical, word-boundary keyword match.
# ===========================================================================

def test_classify_detects_tier_2_keywords():
    router, *_ = make_router()

    assert router.classify("debug this traceback for me") == "propose_tier_2"

    # At least three more distinct keywords, including one multi-word phrase.
    assert router.classify("there is an error here") == "propose_tier_2"
    assert router.classify("optimize my algorithm please") == "propose_tier_2"
    assert router.classify("can you compare these two options") == "propose_tier_2"
    assert router.classify("can you explain why this happens") == "propose_tier_2"
    assert router.classify("lets do a deep dive on this topic") == "propose_tier_2"


def test_classify_ignores_normal_chat():
    router, *_ = make_router()

    assert router.classify("how are you") == "tier_1_ok"
    assert router.classify("what time is it") == "tier_1_ok"
    assert router.classify("thanks, that helped") == "tier_1_ok"
    assert router.classify("") == "tier_1_ok"
    assert router.classify("   ") == "tier_1_ok"
    assert router.classify(None) == "tier_1_ok"


def test_classify_word_boundary():
    router, *_ = make_router()

    # Real collisions with the actual lexicon (not "restaurant"/"rest", which
    # is vacuous since "rest" is not in TIER_2_KEYWORDS at all).
    assert router.classify("the terror was immense") == "tier_1_ok"      # not "error"
    assert router.classify("please proofread this") == "tier_1_ok"       # not "proof"

    # Positive control: the real keyword still fires.
    assert router.classify("there is an error here") == "propose_tier_2"


def test_classify_matches_inflected_forms():
    """Strict \\b anchoring excludes inflected forms, so the common ones are
    explicit entries in TIER_2_KEYWORDS (a build-time tuning constant). This
    proves the tuning took effect and guards against it silently regressing:
    natural phrasing like "debugging" must route to tier 2, while ordinary
    chat and the known boundary collisions must still not."""
    router, _gemma, _groq, _azure, _clock = make_router()

    # The headline case: "debugging" is natural phrasing and must match.
    assert router.classify("help me debugging this") == "propose_tier_2"

    # A representative spread of other inflected forms.
    for text in (
        "there are errors in the output",
        "the complexity here is high",
        "optimizing this loop",
        "refactoring the module",
        "analyzing the results",
        "run an analysis on this",
        "comparing the two options",
        "lets do some deep dives",
    ):
        assert router.classify(text) == "propose_tier_2", text

    # The base forms still match (nothing was removed).
    for text in ("debug this", "there is an error here", "this is complex"):
        assert router.classify(text) == "propose_tier_2", text

    # Ordinary chat is still unaffected -- no new false positives.
    for text in (
        "how are you",
        "what time is it",
        "thanks, that helped",
        "lets get dinner later",
    ):
        assert router.classify(text) == "tier_1_ok", text

    # The known boundary collisions must STILL not match: no added entry may
    # accidentally make these fire.
    for text in ("the terror was immense", "please proofread this"):
        assert router.classify(text) == "tier_1_ok", text


# ===========================================================================
# 2) set_override() / get_override() / clear_override()
# ===========================================================================

def test_set_override_valid_tiers():
    router, *_ = make_router()

    for tier in VALID_TIERS:
        router.set_override(tier)
        assert router.get_override() == tier

    router.set_override(None)
    assert router.get_override() is None


def test_set_override_invalid_tier():
    router, *_ = make_router()

    for bad in ("tier_3", "TIER_0", "cloud", "gemma", "", 0):
        with pytest.raises(ValueError):
            router.set_override(bad)


def test_clear_override_resets():
    router, gemma, groq, azure, clock = make_router()

    router.set_override("tier_2")
    assert router.get_override() == "tier_2"

    router.clear_override()
    assert router.get_override() is None

    # Classifier is active again: plain text -> gemma (the default voice
    # under the new fallback order, Change 1); tier-2 text -> propose.
    # JUDGMENT CALL: this assertion was `is groq` before Change 1's fallback
    # swap; not explicitly named in the task's "update these three" list, but
    # left as-is it would fail for the same reason (c) was called out for —
    # another instance the task's own enumeration missed. Updated for
    # consistency rather than left as a spurious failure.
    transport, propose = router.select("how are you")
    assert transport is gemma and propose is False

    transport, propose = router.select("there is an error here")
    assert transport is None and propose is True


# ===========================================================================
# 3) select() — override / propose / groq / gemma / all-down chain.
# ===========================================================================

def test_override_takes_precedence():
    router, gemma, groq, azure, clock = make_router()

    router.set_override("tier_2")
    transport, propose = router.select("how are you")
    assert transport is azure
    assert propose is False

    router.set_override("tier_0")
    transport, propose = router.select("how are you")
    assert transport is gemma
    assert propose is False

    # Override bypasses the classifier AND is not health-gated.
    router.set_override("tier_2")
    azure.healthy = False
    transport, propose = router.select("how are you")
    assert transport is azure
    assert propose is False


def test_select_returns_propose_when_classifier_matches():
    router, gemma, groq, azure, clock = make_router()

    transport, propose = router.select("there is an error here")
    assert transport is None
    assert propose is True

    # Propose branch still requires LIVE azure health; when azure is
    # unhealthy the fall-through now lands on the DEFAULT VOICE (gemma), not
    # groq, under the new fallback order (Change 1: gemma before groq).
    # JUDGMENT CALL: select() reads health via the CACHED check_health()
    # (Part 6's own contract, proven by test_health_check_caches), so the
    # clock must advance past HEALTH_CACHE_TTL_SECONDS for this mutation to
    # be re-probed — otherwise the first call's cached azure=True would still
    # be in effect and this assertion would be testing stale data instead of
    # the "propose requires live azure health" behavior it is meant to prove.
    azure.healthy = False
    clock.advance(HEALTH_CACHE_TTL_SECONDS + 1)
    transport, propose = router.select("there is an error here")
    assert transport is gemma
    assert propose is False


def test_select_defaults_to_gemma_for_conversation():
    # Gemma is the default voice for all conversation (architect decision);
    # Groq is NOT the default — it is reserved for future tools/search and
    # only serves as the fallback when Gemma is unavailable or not resident.
    router, gemma, groq, azure, clock = make_router()

    transport, propose = router.select("how are you")
    assert transport is gemma
    assert propose is False


def test_select_falls_back_to_groq_when_gemma_unavailable():
    # Proves the NEW fallback order (gemma -> groq) in BOTH of gemma's
    # failure modes: healthy-but-not-resident, and unhealthy.
    router, gemma, groq, azure, clock = make_router()

    # Failure mode 1: gemma is healthy (per its own is_healthy/is_loaded
    # read) but NOT resident (unloaded) -> not selectable -> falls to groq.
    gemma.unload()
    transport, propose = router.select("how are you")
    assert transport is groq
    assert propose is False

    # Failure mode 2: fresh router, gemma reports unhealthy outright -> falls
    # to groq.
    router2, gemma2, groq2, azure2, clock2 = make_router()
    gemma2.healthy = False
    transport, propose = router2.select("how are you")
    assert transport is groq2
    assert propose is False


def test_allow_tier_2_proposal_false_never_proposes():
    # The caller supplies a constraint ("this turn must not be deferred"); the
    # ROUTER still chooses. So the tier-2 branch is skipped and the normal
    # gemma -> groq chain decides, rather than the caller getting (None, True)
    # and having to discard it.
    router, gemma, groq, azure, clock = make_router()

    transport, propose = router.select("there is an error here")
    assert (transport, propose) == (None, True)          # default unchanged

    transport, propose = router.select(
        "there is an error here", allow_tier_2_proposal=False)
    assert propose is False
    assert transport is gemma        # a REAL transport, not None


def test_allow_tier_2_proposal_false_still_honours_the_fallback_chain():
    # Suppressing the proposal must not bypass the router's own ordering.
    router, gemma, groq, azure, clock = make_router()
    gemma.unload()                                       # gemma not resident
    transport, propose = router.select(
        "debug this traceback", allow_tier_2_proposal=False)
    assert transport is groq and propose is False

    # And it still reaches the degradation path when nothing is available.
    r2, g2, q2, a2, _c2 = make_router()
    g2.healthy = False
    q2.healthy = False
    assert r2.select("debug this traceback", allow_tier_2_proposal=False) == (None, False)


def test_allow_tier_2_proposal_false_does_not_override_an_override():
    # An explicit user override still wins unconditionally — the suppression
    # only gates the CLASSIFIER's proposal branch.
    router, gemma, groq, azure, clock = make_router()
    router.set_override("tier_2")
    transport, propose = router.select(
        "there is an error here", allow_tier_2_proposal=False)
    assert transport is azure and propose is False


def test_select_all_down():
    router, gemma, groq, azure, clock = make_router()

    groq.healthy = False
    azure.healthy = False
    gemma.healthy = False
    transport, propose = router.select("how are you")
    assert transport is None
    assert propose is False


# ===========================================================================
# 3b) ensure_local_loaded() — startup lifecycle (Change 1).
# ===========================================================================

def test_ensure_local_loaded():
    # Gemma starts unloaded.
    gemma = FakeLocalTransport(loaded=False)
    router, gemma, groq, azure, clock = make_router(gemma=gemma)
    assert gemma.is_loaded is False

    result = router.ensure_local_loaded()
    assert result is True
    assert gemma.is_loaded is True
    assert gemma.load_calls == 1

    # Idempotent: calling it again does not reload.
    result2 = router.ensure_local_loaded()
    assert result2 is True
    assert gemma.load_calls == 1

    # select() with plain chat text now returns gemma (the default voice).
    transport, propose = router.select("how are you")
    assert transport is gemma
    assert propose is False


# ===========================================================================
# 4) check_health() — cached, per-backend probe order, copy-on-return.
# ===========================================================================

def test_health_check_caches():
    router, gemma, groq, azure, clock = make_router()

    first = router.check_health()
    assert first == {"gemma": True, "groq": True, "azure": True}

    # Mutate WITHOUT advancing the clock: still cached.
    groq.healthy = False
    second = router.check_health()
    assert second["groq"] is True  # stale cache, not re-probed yet

    # Advance past the TTL: re-probes.
    clock.advance(HEALTH_CACHE_TTL_SECONDS + 1)
    third = router.check_health()
    assert third["groq"] is False

    # Mutating the returned dict does not corrupt the cache.
    fourth = router.check_health()
    fourth["azure"] = False
    fifth = router.check_health()
    assert fifth["azure"] is True


# ===========================================================================
# 4b) FLAG B — UNKNOWN health is not optimistic health.
# ===========================================================================

def test_probe_one_returns_unknown_without_health_probe():
    # The three-state contract: True / False / None(UNKNOWN). A non-local
    # transport with no is_healthy() cannot answer, so the answer is UNKNOWN —
    # never an optimistic True (FLAG B).
    probe_yes = FakeCloudTransport("groq", healthy=True)
    probe_no = FakeCloudTransport("groq", healthy=False)
    probeless = ProbelessCloudTransport("groq")

    assert BackendRouter._probe_one(probe_yes, is_local=False) is True
    assert BackendRouter._probe_one(probe_no, is_local=False) is False
    assert BackendRouter._probe_one(probeless, is_local=False) is None
    assert BackendRouter._probe_one(None, is_local=False) is False

    # The local tier is never UNKNOWN: residency is a real answer.
    assert BackendRouter._probe_one(ProbelessLocalTransport(loaded=True),
                                    is_local=True) is True
    assert BackendRouter._probe_one(ProbelessLocalTransport(loaded=False),
                                    is_local=True) is False


def test_transport_without_health_probe_is_not_reported_healthy():
    # check_health() reports the HEALTHY SET. UNKNOWN is not in it.
    router, gemma, groq, azure, clock = make_router(
        groq=ProbelessCloudTransport("groq"),
        azure=ProbelessCloudTransport("azure"),
    )
    health = router.check_health()
    assert health["groq"] is False
    assert health["azure"] is False
    assert health["gemma"] is True  # this one CAN answer
    # And an explicit probe still reports honestly, both ways.
    up, _g2, _q2, _a2, _c2 = make_router(groq=FakeCloudTransport("groq", healthy=True))
    assert up.check_health()["groq"] is True
    down, _g3, _q3, _a3, _c3 = make_router(groq=FakeCloudTransport("groq", healthy=False))
    assert down.check_health()["groq"] is False


def test_unknown_azure_does_not_propose_escalation():
    # The tier-2 propose branch is gated on EXPLICIT azure health. With an
    # unprobeable azure, a keyword match must NOT propose escalation; the turn
    # falls through to the default voice instead.
    router, gemma, groq, azure, clock = make_router(
        azure=ProbelessCloudTransport("azure"))
    transport, propose = router.select("there is an error here")
    assert propose is False
    assert transport is gemma


def test_select_falls_back_to_gemma_when_cloud_transports_are_unknown():
    router, gemma, groq, azure, clock = make_router(
        groq=ProbelessCloudTransport("groq"),
        azure=ProbelessCloudTransport("azure"),
    )
    transport, propose = router.select("how are you")
    assert transport is gemma
    assert propose is False


def test_unknown_groq_is_not_selected_when_gemma_unavailable():
    # Groq is the fallback ONLY when explicitly healthy. Unprobeable groq plus
    # unavailable gemma must degrade, not silently route to a dead backend.
    router, gemma, groq, azure, clock = make_router(
        groq=ProbelessCloudTransport("groq"),
        azure=ProbelessCloudTransport("azure"),
    )
    gemma.unload()
    transport, propose = router.select("how are you")
    assert transport is None
    assert propose is False


def test_degradation_path_reachable_when_everything_is_unknown_or_down():
    # The all-down return (None, False) used to be unreachable because every
    # probeless cloud transport reported healthy. It is now reachable.
    router, gemma, groq, azure, clock = make_router(
        gemma=ProbelessLocalTransport(loaded=False),
        groq=ProbelessCloudTransport("groq"),
        azure=ProbelessCloudTransport("azure"),
    )
    assert router.check_health() == {"gemma": False, "groq": False, "azure": False}
    assert router.select("how are you") == (None, False)
    assert router.select("there is an error here") == (None, False)

    # Same outcome via explicit unhealthy probes, for parity.
    router2, gemma2, groq2, azure2, clock2 = make_router()
    gemma2.healthy = False
    groq2.healthy = False
    azure2.healthy = False
    assert router2.select("how are you") == (None, False)


# ===========================================================================
# 5) Structural boundary proofs (house convention).
# ===========================================================================

def test_router_holds_no_soul_state():
    router, *_ = make_router()
    attr_names = set(vars(router))
    assert attr_names == {
        "_gemma", "_groq", "_azure", "_clock",
        "_override", "_health_cache", "_health_cached_at",
    }


def test_module_imports_no_soul_modules():
    tree = ast.parse(inspect.getsource(br_mod))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)

    forbidden = {
        "daemon.pad_engine", "daemon.graph_manager", "daemon.needs_system",
        "daemon.appraisal_chain", "daemon.soul_filter", "daemon.dmn",
        "daemon.state_manager", "daemon.aria_daemon", "daemon.session_buffer",
    }
    assert not (names & forbidden), f"forbidden imports present: {names & forbidden}"

    daemon_imports = {n for n in names if n and n.startswith("daemon")}
    assert daemon_imports == {"daemon.llm_interface"}
