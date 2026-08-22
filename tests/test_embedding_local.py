"""Module 3/4 embedding boundary — the real-vs-fake comparison, plus the
adapter's own contract.

WHY THIS FILE EXISTS
--------------------
Every test in this repo has run against a FAKE embedding: a token-hash or
char-bucket bag-of-words. Four behaviours read embedding similarity and each has
a cutoff that has never seen a real model:

    MemoryGraph.retrieve()                  no cutoff — similarity is the ORDER
    MemoryGraph.reality_contradiction_check()   _REALITY_CONTRADICTION_SIM_CUTOFF 0.6
    AppraisalChain._vulnerability()             _VULNERABILITY_SIM_CUTOFF        0.6
    MemoryGraph.register_edge_firing()          _HABITUATION_SIMILARITY_CUTOFF   0.9

(The handoff said five and listed `is_first_of_kind`. Counted here: that method
is pure SQL on (Q2, Q3) and reads no embedding. Four.)

So this file does two separate jobs, and keeps them separate on purpose:

  1. `test_contract_*` — the invariants ANY model must satisfy to be usable at
     this boundary, expressed as a harness that runs against any `embed()`.
     Proven to have teeth by running it against the coarse char-bucket fake that
     `tests/test_daemon.py`'s docstring warns about: that fake FAILS, which is
     what makes the passes meaningful.
  2. `test_real_*` — the same harness against the real adapter, SKIPPED when no
     backend is reachable so `make check` stays hermetic. `test_real_reports_
     cutoff_calibration_data` prints the measured cosines against the three
     live cutoffs. That output is the tuning data; this file asserts nothing
     about what the cutoffs SHOULD be. Changing a cutoff is an architect call
     (`TODO(OQ1-rate)` / F-4e), not a consequence of a measurement.

Run the reporting test with output visible:

    .venv/bin/python -m pytest tests/test_embedding_local.py -q -s -k calibration
"""

from __future__ import annotations

import json
import urllib.error

import pytest

# The consumers' OWN cosine, imported deliberately. A reimplementation here
# would measure a different metric than the code under discussion, which would
# make every number in this file unusable as calibration data.
from daemon.graph_manager import (
    _cosine,
    _HABITUATION_SIMILARITY_CUTOFF,
    _REALITY_CONTRADICTION_SIM_CUTOFF,
)
from daemon.appraisal_chain import (
    _VULNERABILITY_EXEMPLARS,
    _VULNERABILITY_SIM_CUTOFF,
)

from adapters.embedding_local import (
    EmbeddingDimensionError,
    EmbeddingUnavailableError,
    OllamaEmbeddingModel,
)


# ===========================================================================
# The fakes this project has actually been testing against.
# ===========================================================================

class TokenHashFake:
    """Verbatim shape of `tests/test_daemon.py::FakeEmbedding` — the WIDE
    token-hash bag-of-words, the better of the two fakes in the repo.

    Kept in sync deliberately, INCLUDING the 2026-08-22 stopword skip. Without
    it, function-word overlap alone put ordinary text at 0.286 against an
    exemplar, which false-fires at the 0.25 cutoff. Mirroring the real fake is
    the point of this class: if the two drift, the comparison below stops
    describing what the suite actually runs on."""

    DIM = 128
    STOPWORDS = frozenset({
        "i", "im", "i'm", "me", "my", "you", "your", "it", "its", "it's", "this",
        "that", "a", "an", "the", "and", "or", "but", "of", "to", "in", "on",
        "at", "for", "with", "am", "is", "are", "was", "were", "be", "been",
        "do", "did", "does", "have", "has", "had", "so", "just", "about",
        "what", "how",
    })

    @staticmethod
    def _tok_hash(tok: str) -> int:
        h = 0
        for ch in tok:
            h = (h * 131 + ord(ch)) % 1_000_003
        return h

    def embed(self, text):
        v = [0.0] * self.DIM
        for tok in (text or "").lower().split():
            tok = tok.strip(".,!?;:'\"")
            if not tok or tok in self.STOPWORDS:
                continue
            v[self._tok_hash(tok) % self.DIM] += 1.0
        return v


class CharBucketFake:
    """Verbatim shape of `tests/test_graph_manager.py::FakeEmbedding`'s fallback
    — the 8-dim char-frequency toy. `test_daemon.py`'s docstring says this one
    "would false-trigger VULNERABILITY_DISCLOSURE on ordinary text". This file
    proves that claim instead of repeating it."""

    def embed(self, text):
        v = [0.0] * 8
        for ch in text or "":
            v[ord(ch) % 8] += 1.0
        return v


# ===========================================================================
# Probe set — grounded in what the four consumers actually compare.
# ===========================================================================

# ---------------------------------------------------------------------------
# THREE bands, not two. The interesting question is not "does a shopping list
# score lower than a confession" — of course it does. It is whether there is a
# GAP between text that is emotionally loaded but NOT self-disclosure, and text
# that is. `_VULNERABILITY_SIM_CUTOFF` has to live in that gap, and if no gap
# exists that is the finding.
# ---------------------------------------------------------------------------

#: BAND 1 — mundane. Requests, facts, logistics, small talk. Nothing here is a
#: disclosure by any reading, so this band's CEILING is the floor under which a
#: cutoff must not go.
ORDINARY_TEXT = (
    "I pushed the deploy script and the build went green",
    "what time does the library close on Sunday",
    "remind me to buy oat milk and coffee filters",
    "the compiler flag we needed was minus O two all along",
    "can you summarise what we decided about the schema",
    "it rained all afternoon so I stayed in and read",
    "my train got in about twenty minutes late",
    "I am going to try that noodle place on the corner tonight",
    "what is the difference between a mutex and a semaphore",
    "the dishwasher is making that noise again",
    "I finished the book you would have hated the ending",
    "we moved the standup to half nine on Thursdays",
    "I need to renew my passport before the trip",
    "the cat has decided the printer is hers now",
    "remind me to email the landlord about the radiator",
)

#: BAND 2 — emotionally loaded, NOT self-disclosure. Irritation, tiredness,
#: enthusiasm, ordinary complaint. A person saying these is expressing feeling,
#: not entrusting something. THIS is the band that decides whether a low cutoff
#: is safe: if these fire, the cutoff is too low and Field 4 will tell the LLM to
#: engage a grumble about a build with the presence a confession deserves.
EMOTIONAL_NOT_DISCLOSING = (
    "I am so annoyed the build broke again right before the demo",
    "that meeting was a complete waste of everybody's afternoon",
    "I am really tired today, I did not sleep well",
    "I am genuinely excited about the trip next month",
    "it is frustrating how long the approval process takes",
    "I hate how loud the roadworks are outside",
    "honestly I am just relieved that week is over",
    "I am a bit stressed about the amount left on the list",
    "that film was so much better than I expected",
    "I am fed up with this laptop fan",
)

#: BAND 3 — genuine self-disclosure. Varied phrasings on purpose: first-time
#: admission, fear, shame, not-coping, loneliness, hiding. Deliberately NOT
#: paraphrases of the exemplars, or this would only measure how well the model
#: matches four specific sentences to themselves.
DISCLOSING_TEXT = (
    "I have not told anybody about this and I am not sure I should",
    "I am frightened and I have no idea what to do next",
    "I think something is wrong with me and I have been hiding it",
    "I have been pretending I am fine for months now",
    "there is nobody I can say this to and it is eating me",
    "I do not think I am coping and I am ashamed of that",
    "I keep failing at the one thing I said mattered to me",
    "I feel completely alone even when people are around",
    "I have never admitted this out loud before",
    "I am scared that this is just who I am now",
    "I do not recognise myself lately and it frightens me",
    "I have been carrying this by myself and I am tired of it",
)

#: Same claim, opposite polarity — reality_contradiction_check needs HIGH
#: similarity here, since it gates on `sim >= 0.6 AND negation differs`.
CONTRADICTION_PAIR = (
    "I finished the report yesterday",
    "I did not finish the report yesterday",
)

#: Same meaning, HIGH lexical overlap. Kept for calibration only: a
#: bag-of-words fake also scores this pair high (measured 0.869), so it proves
#: nothing about meaning.
PARAPHRASE_PAIR = (
    "the cat knocked the glass off the table",
    "the glass was pushed off the table by the cat",
)

#: Same meaning, ZERO shared tokens. This is the discriminating probe: it is
#: the case where lexical overlap and meaning come apart, so a bag-of-words
#: model scores it at exactly the unrelated floor while a real encoder does not.
#: `retrieve()` orders on similarity with no cutoff, so this is the property it
#: actually depends on.
SEMANTIC_PAIR = (
    "the deploy failed again",
    "another release broke in production",
)

#: Trivially restated — habituation's "without variation" case (cutoff 0.9).
NEAR_DUPLICATE_PAIR = (
    "we talked about my brother again",
    "we talked about my brother again today",
)

#: Nothing in common — the floor every other measurement is read against.
UNRELATED_PAIR = (
    "the compiler flag we needed was minus O two all along",
    "I am frightened and I have no idea what to do next",
)

ALL_PROBES = (
    tuple(_VULNERABILITY_EXEMPLARS)
    + ORDINARY_TEXT
    + EMOTIONAL_NOT_DISCLOSING
    + DISCLOSING_TEXT
    + CONTRADICTION_PAIR
    + PARAPHRASE_PAIR
    + SEMANTIC_PAIR
    + NEAR_DUPLICATE_PAIR
)


# ===========================================================================
# The harness. One function per invariant, each taking any object with embed().
# ===========================================================================

def _vectors(model, texts=ALL_PROBES):
    return {t: list(model.embed(t)) for t in texts}


def check_deterministic(model) -> None:
    """Same text twice must give the same vector. `MemoryGraph` PERSISTS
    embeddings and later compares fresh vectors against stored rows, so a
    non-deterministic model silently breaks reality-contradiction and
    habituation."""
    for text in ALL_PROBES:
        assert list(model.embed(text)) == list(model.embed(text)), text


def check_fixed_dimension(model) -> int:
    """One length for every input. Both `_cosine` implementations return 0.0 on
    a length mismatch rather than raising, so a varying dimension reads as
    "never similar" and switches all four behaviours off invisibly."""
    dims = {len(v) for v in _vectors(model).values()}
    assert len(dims) == 1, f"mixed vector dimensions: {sorted(dims)}"
    dim = dims.pop()
    assert dim > 0
    return dim


def check_not_degenerate(model) -> None:
    """Unrelated text must not collapse to near-identical vectors."""
    a, b = UNRELATED_PAIR
    sim = _cosine(model.embed(a), model.embed(b))
    assert sim < _HABITUATION_SIMILARITY_CUTOFF, (
        f"unrelated sentences scored {sim:.3f}, at or above the habituation "
        f"cutoff {_HABITUATION_SIMILARITY_CUTOFF} — every retrieval would read "
        f"as 'without variation'"
    )


def check_ordinary_text_is_not_vulnerable(model) -> None:
    """The load-bearing one. Ordinary text must stay BELOW
    `_VULNERABILITY_SIM_CUTOFF` against every exemplar, or Aria treats a
    shopping list as a self-disclosure and Field 4 tells the LLM to engage it
    "with full presence, no deflection"."""
    worst = ("", "", -1.0)
    for plain in ORDINARY_TEXT:
        for exemplar in _VULNERABILITY_EXEMPLARS:
            sim = _cosine(model.embed(plain), model.embed(exemplar))
            if sim > worst[2]:
                worst = (plain, exemplar, sim)
    assert worst[2] < _VULNERABILITY_SIM_CUTOFF, (
        f"ordinary text false-triggers VULNERABILITY_DISCLOSURE: "
        f"{worst[2]:.3f} >= {_VULNERABILITY_SIM_CUTOFF}\n"
        f"  plain:    {worst[0]!r}\n"
        f"  exemplar: {worst[1]!r}"
    )


def check_related_outranks_unrelated(model) -> None:
    """`retrieve()` uses similarity as its base ORDER, with no cutoff at all, so
    ordering is the only property it needs — and the only one it cannot survive
    losing.

    The probe is deliberately the LEXICALLY DISJOINT paraphrase. A pair that
    shares words is passed by a bag of token hashes too, so it would test
    nothing; a pair that shares meaning and no words separates the two."""
    related = _cosine(model.embed(SEMANTIC_PAIR[0]), model.embed(SEMANTIC_PAIR[1]))
    unrelated = _cosine(model.embed(UNRELATED_PAIR[0]), model.embed(UNRELATED_PAIR[1]))
    assert related > unrelated, (
        f"a paraphrase sharing NO tokens ({related:.3f}) did not outrank an "
        f"unrelated pair ({unrelated:.3f}) — retrieval ordering carries no "
        f"semantic signal, only word overlap"
    )


#: Exemplar-like disclosures, used for the threshold-FREE margin check below.
#: Close to the exemplars on purpose: the question here is only whether a model
#: can put disclosure above mundane text at all, not by how much.
NEAR_EXEMPLAR_DISCLOSURE = (
    "I have never told anyone this before",
    "I am scared and I do not know what to do",
    "I have not told anybody this but I have been struggling",
)


def check_separates_ordinary_from_disclosure_by_margin(model) -> None:
    """Threshold-FREE version of the check above: the highest-scoring mundane or
    merely-emotional line must sit strictly below the lowest-scoring disclosure.

    Exists because a fake's floor can be set by hash collisions rather than by
    anything meaningful, so comparing it against a tuning constant tests luck.
    An ORDERING claim is the honest one to make of any model at this boundary.
    """
    non_disclosure = max(
        _best_exemplar_similarity(model, t)
        for t in ORDINARY_TEXT + EMOTIONAL_NOT_DISCLOSING
    )
    disclosure = min(
        _best_exemplar_similarity(model, t) for t in NEAR_EXEMPLAR_DISCLOSURE
    )
    assert non_disclosure < disclosure, (
        f"no margin between non-disclosure ({non_disclosure:.3f}) and "
        f"disclosure ({disclosure:.3f}) — no cutoff can separate them"
    )


BOUNDARY_CONTRACT = (
    check_deterministic,
    check_fixed_dimension,
    check_not_degenerate,
    check_ordinary_text_is_not_vulnerable,
    check_separates_ordinary_from_disclosure_by_margin,
    check_related_outranks_unrelated,
)


# ===========================================================================
# 1) The harness has teeth — proven against the repo's own fakes, no network.
# ===========================================================================

def test_contract_token_hash_fake_passes_the_parts_it_was_built_for():
    """The wide token-hash fake is deterministic, fixed-dimension, and separates
    ordinary text from disclosure by a clear margin. That is what its docstring
    claims, and it is why the soul-layer tests are trustworthy about everything
    EXCEPT similarity ordering.

    NOTE what is deliberately NOT asserted here: that the fake clears the live
    `_VULNERABILITY_SIM_CUTOFF`. It does not, and the reason is instructive —
    its floor is 0.250, produced by two content words COLLIDING in a 128-bucket
    hash space, not by any shared word. That floor is hash luck, so pinning it
    against a tuning constant would test the birthday problem rather than the
    model. The margin below is the meaningful statement; the live cutoff belongs
    to the REAL model's contract, where it is asserted.
    """
    fake = TokenHashFake()
    check_deterministic(fake)
    assert check_fixed_dimension(fake) == 128
    check_not_degenerate(fake)
    check_separates_ordinary_from_disclosure_by_margin(fake)


def test_contract_token_hash_fake_FAILS_similarity_ordering():
    """...and here is the thing no existing test could have caught.

    A bag of token hashes measures WORD OVERLAP, not meaning. Measured against
    this fake: the high-overlap paraphrase scores 0.869, but the paraphrase
    sharing no tokens scores 0.000 — identical to the unrelated floor. So for
    any two turns phrased differently, `retrieve()` has been ordering on noise
    in every existing test.

    This is the measured reason `EmbeddingModel` "cannot be stubbed"."""
    fake = TokenHashFake()
    high_overlap = _cosine(fake.embed(PARAPHRASE_PAIR[0]),
                           fake.embed(PARAPHRASE_PAIR[1]))
    disjoint = _cosine(fake.embed(SEMANTIC_PAIR[0]), fake.embed(SEMANTIC_PAIR[1]))
    floor = _cosine(fake.embed(UNRELATED_PAIR[0]), fake.embed(UNRELATED_PAIR[1]))
    assert high_overlap > 0.7          # shared words look "similar"
    assert disjoint == floor == 0.0    # shared meaning does not

    with pytest.raises(AssertionError, match="did not outrank"):
        check_related_outranks_unrelated(fake)


def test_contract_char_bucket_fake_FAILS_vulnerability_separation():
    """Proves the warning in `test_daemon.py::FakeEmbedding`'s docstring rather
    than restating it: the 8-dim char-frequency toy scores ordinary text at or
    above the 0.6 vulnerability cutoff, because English letter frequency is
    nearly identical in every sentence."""
    with pytest.raises(AssertionError, match="false-triggers VULNERABILITY"):
        check_ordinary_text_is_not_vulnerable(CharBucketFake())


def test_contract_a_constant_model_fails_every_similarity_invariant():
    """Guard against the laziest possible adapter bug — returning the same
    vector for everything. It is deterministic and fixed-dimension, so the two
    cheap invariants pass; the three that matter must not."""

    class Constant:
        def embed(self, text):
            return [1.0, 0.0, 0.0]

    model = Constant()
    check_deterministic(model)
    assert check_fixed_dimension(model) == 3
    with pytest.raises(AssertionError):
        check_not_degenerate(model)
    with pytest.raises(AssertionError):
        check_ordinary_text_is_not_vulnerable(model)
    with pytest.raises(AssertionError):
        check_related_outranks_unrelated(model)


def test_vulnerability_exemplar_count_is_measured_not_assumed():
    """Counted, not remembered. The per-turn embedding cost of
    `AppraisalChain._vulnerability` is one call per exemplar plus one for the
    user's text, which is what makes the adapter's cache load-bearing rather
    than an optimisation."""
    assert len(_VULNERABILITY_EXEMPLARS) == 4
    assert len(set(_VULNERABILITY_EXEMPLARS)) == 4


# ===========================================================================
# 2) The adapter's own contract — hermetic, via a stubbed HTTP layer.
# ===========================================================================

class _StubResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_urlopen(monkeypatch, handler):
    """Replace the adapter's urlopen. `handler(body_dict) -> response object`."""
    calls = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        calls.append({"url": request.full_url, "body": body, "timeout": timeout})
        return handler(body)

    monkeypatch.setattr(
        "adapters.embedding_local.urllib.request.urlopen", fake_urlopen
    )
    return calls


def _ok(vector):
    def handler(_body):
        return _StubResponse(json.dumps({"embeddings": [vector]}).encode("utf-8"))

    return handler


def test_adapter_sends_the_endpoint_and_payload_ollama_documents(monkeypatch):
    model = OllamaEmbeddingModel(host="http://localhost:11434", model="all-minilm")
    calls = _stub_urlopen(monkeypatch, _ok([0.1, 0.2, 0.3]))

    assert list(model.embed("hello")) == [0.1, 0.2, 0.3]
    assert calls[0]["url"] == "http://localhost:11434/api/embed"
    # `input`, not `prompt` — the current endpoint, and it is batch-shaped.
    assert calls[0]["body"] == {"model": "all-minilm", "input": "hello"}


def test_adapter_caches_so_the_four_exemplars_cost_one_round_trip_each(monkeypatch):
    """`_vulnerability` re-embeds all four exemplars on EVERY turn. Without the
    cache that is four HTTP round trips per turn, forever."""
    model = OllamaEmbeddingModel()
    calls = _stub_urlopen(monkeypatch, _ok([1.0, 0.0]))

    for _ in range(3):
        for exemplar in _VULNERABILITY_EXEMPLARS:
            model.embed(exemplar)

    assert len(calls) == 4                       # not 12
    assert model.stats == {"backend_calls": 4, "cache_hits": 8}


def test_adapter_cache_evicts_least_recently_used(monkeypatch):
    model = OllamaEmbeddingModel(cache_entries=2)
    calls = _stub_urlopen(monkeypatch, _ok([1.0, 0.0]))

    model.embed("a")
    model.embed("b")
    model.embed("a")        # refreshes "a", so "b" is now the eviction victim
    model.embed("c")        # evicts "b"
    model.embed("b")        # miss -> refetch
    assert [c["body"]["input"] for c in calls] == ["a", "b", "c", "b"]


def test_adapter_empty_text_never_reaches_the_backend(monkeypatch):
    model = OllamaEmbeddingModel()
    calls = _stub_urlopen(monkeypatch, _ok([1.0, 2.0, 3.0]))

    assert list(model.embed("")) == []
    assert list(model.embed("   ")) == []
    assert calls == []

    model.embed("real text")                     # dimension becomes known
    assert list(model.embed("")) == [0.0, 0.0, 0.0]
    assert _cosine(model.embed(""), [1.0, 2.0, 3.0]) == 0.0


def test_adapter_raises_when_the_dimension_changes(monkeypatch):
    """A silent dimension change is the worst available failure: `_cosine`
    returns 0.0 on a length mismatch, so all four behaviours would go quiet
    with no error anywhere."""
    model = OllamaEmbeddingModel()
    vectors = iter([[1.0, 2.0], [1.0, 2.0, 3.0]])

    def handler(_body):
        return _StubResponse(
            json.dumps({"embeddings": [next(vectors)]}).encode("utf-8")
        )

    _stub_urlopen(monkeypatch, handler)

    model.embed("first")
    assert model.dimension == 2
    with pytest.raises(EmbeddingDimensionError, match="silently disable"):
        model.embed("second")


def test_adapter_translates_an_unreachable_daemon(monkeypatch):
    model = OllamaEmbeddingModel()

    def handler(_body):
        raise urllib.error.URLError("Connection refused")

    _stub_urlopen(monkeypatch, handler)
    with pytest.raises(EmbeddingUnavailableError, match="unreachable"):
        model.embed("anything")


def test_adapter_translates_a_missing_model(monkeypatch):
    model = OllamaEmbeddingModel(model="not-pulled")

    def handler(_body):
        raise urllib.error.HTTPError(
            "http://localhost:11434/api/embed", 404, "Not Found", {}, None
        )

    _stub_urlopen(monkeypatch, handler)
    with pytest.raises(EmbeddingUnavailableError, match="HTTP 404"):
        model.embed("anything")


def test_adapter_rejects_a_response_with_no_vector(monkeypatch):
    """A generative model answers /api/embed with no `embeddings` key. Naming
    the remedy beats a KeyError three frames deep."""
    model = OllamaEmbeddingModel()

    def handler(_body):
        return _StubResponse(json.dumps({"response": "hi"}).encode("utf-8"))

    _stub_urlopen(monkeypatch, handler)
    with pytest.raises(EmbeddingUnavailableError, match="ollama pull"):
        model.embed("anything")


def test_adapter_preflight_names_the_remedy(monkeypatch):
    model = OllamaEmbeddingModel(model="all-minilm")

    def handler(_body):
        raise urllib.error.URLError("Connection refused")

    _stub_urlopen(monkeypatch, handler)
    with pytest.raises(EmbeddingUnavailableError) as exc:
        model.preflight()
    message = str(exc.value)
    assert "ollama serve" in message
    assert "ollama pull all-minilm" in message
    # Names what silently stops working, since two of the three soul-layer
    # call sites swallow this exception.
    assert "VULNERABILITY_DISCLOSURE" in message
    assert model.is_reachable() is False


def test_adapter_preflight_returns_the_dimension(monkeypatch):
    model = OllamaEmbeddingModel()
    _stub_urlopen(monkeypatch, _ok([0.0] * 384))
    assert model.preflight() == 384
    assert model.dimension == 384


def test_adapter_satisfies_the_embedding_model_protocol():
    from daemon.graph_manager import EmbeddingModel

    assert isinstance(OllamaEmbeddingModel(), EmbeddingModel)


# ===========================================================================
# 3) The real model. Skipped when no backend is reachable.
# ===========================================================================

def _real_model_or_skip():
    model = OllamaEmbeddingModel()
    try:
        model.preflight()
    except EmbeddingUnavailableError as exc:
        pytest.skip(
            f"no embedding backend reachable, so the real-vs-fake comparison "
            f"cannot run: {exc.__class__.__name__}. Start it with "
            f"`ollama serve` and `ollama pull {model.model}`."
        )
    return model


def test_real_model_satisfies_the_whole_boundary_contract():
    """The same five checks the fakes were run through, against the real thing.
    Notably this must pass `check_related_outranks_unrelated`, which the
    token-hash fake cannot."""
    model = _real_model_or_skip()
    for check in BOUNDARY_CONTRACT:
        check(model)


def _best_exemplar_similarity(model, text):
    """Exactly what `AppraisalChain._vulnerability` computes: the best cosine
    against ANY exemplar. It fires on the max, not the mean, so the max is the
    only statistic that describes the real decision."""
    return max(
        _cosine(model.embed(text), model.embed(exemplar))
        for exemplar in _VULNERABILITY_EXEMPLARS
    )


def _band(model, texts):
    scores = sorted((_best_exemplar_similarity(model, t), t) for t in texts)
    values = [s for s, _ in scores]
    return {
        "n": len(values),
        "min": values[0],
        "max": values[-1],
        "mean": sum(values) / len(values),
        "sorted": scores,
    }


def test_real_reports_vulnerability_cutoff_calibration():
    """The decision table for `_VULNERABILITY_SIM_CUTOFF`.

    Three bands — mundane, emotional-but-not-disclosure, genuine disclosure —
    scored the way `_vulnerability` actually scores (best cosine against ANY
    exemplar). Reports the gap between band 2's ceiling and band 3's floor, and
    the false-positive / false-negative count at each candidate cutoff.

    Asserts NOTHING about which cutoff is right. That is an architect decision on
    a flagged F-4e placeholder; this test exists so the decision has evidence
    under it instead of six data points and a hunch.
    """
    model = _real_model_or_skip()

    bands = [
        ("1 mundane", _band(model, ORDINARY_TEXT)),
        ("2 emotional, not disclosure", _band(model, EMOTIONAL_NOT_DISCLOSING)),
        ("3 genuine disclosure", _band(model, DISCLOSING_TEXT)),
    ]

    print(f"\n  model={model.model} dim={model.dimension} "
          f"exemplars={len(_VULNERABILITY_EXEMPLARS)} "
          f"live cutoff={_VULNERABILITY_SIM_CUTOFF}")
    print(f"\n  {'band':32} {'n':>3} {'min':>7} {'mean':>7} {'max':>7}")
    for name, b in bands:
        print(f"  {name:32} {b['n']:3d} {b['min']:7.3f} {b['mean']:7.3f} "
              f"{b['max']:7.3f}")

    non_disclosure_ceiling = max(bands[0][1]["max"], bands[1][1]["max"])
    disclosure_floor = bands[2][1]["min"]
    print(f"\n  non-disclosure ceiling (bands 1+2 max) {non_disclosure_ceiling:7.3f}")
    print(f"  disclosure floor       (band 3 min)     {disclosure_floor:7.3f}")
    if disclosure_floor > non_disclosure_ceiling:
        print(f"  ==> CLEAN GAP of {disclosure_floor - non_disclosure_ceiling:.3f}; "
              f"any cutoff inside it is error-free on this probe set")
    else:
        print("  ==> BANDS OVERLAP; no cutoff separates them and every choice "
              "trades false positives against missed disclosures")

    non_disclosure = ORDINARY_TEXT + EMOTIONAL_NOT_DISCLOSING
    print(f"\n  {'cutoff':>7}  {'false pos':>9}  {'missed disclosures':>19}")
    for cutoff in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
        false_pos = sum(
            1 for t in non_disclosure
            if _best_exemplar_similarity(model, t) >= cutoff
        )
        missed = sum(
            1 for t in DISCLOSING_TEXT
            if _best_exemplar_similarity(model, t) < cutoff
        )
        live = "   <-- live" if abs(cutoff - _VULNERABILITY_SIM_CUTOFF) < 1e-9 else ""
        print(f"  {cutoff:7.2f}  {false_pos:4d}/{len(non_disclosure):<4}  "
              f"{missed:9d}/{len(DISCLOSING_TEXT):<8}{live}")

    print("\n  worst non-disclosure (would false-fire first):")
    for score, text in (bands[0][1]["sorted"] + bands[1][1]["sorted"])[-3:]:
        print(f"    {score:6.3f}  {text!r}")
    print("  weakest disclosures (missed first):")
    for score, text in bands[2][1]["sorted"][:3]:
        print(f"    {score:6.3f}  {text!r}")

    for _name, b in bands:
        assert -1.0001 <= b["min"] <= b["max"] <= 1.0001


def test_real_reports_habituation_and_contradiction_cutoffs():
    """The other two live cutoffs. Same rule: report, decide nothing."""
    model = _real_model_or_skip()

    def sim(a, b):
        return _cosine(model.embed(a), model.embed(b))

    rows = [
        ("habituation      near-duplicate", sim(*NEAR_DUPLICATE_PAIR),
         _HABITUATION_SIMILARITY_CUTOFF),
        ("habituation      paraphrase, shared words", sim(*PARAPHRASE_PAIR),
         _HABITUATION_SIMILARITY_CUTOFF),
        ("habituation      paraphrase, NO shared words", sim(*SEMANTIC_PAIR),
         _HABITUATION_SIMILARITY_CUTOFF),
        ("habituation      unrelated (floor)", sim(*UNRELATED_PAIR),
         _HABITUATION_SIMILARITY_CUTOFF),
        ("contradiction    same claim, negated", sim(*CONTRADICTION_PAIR),
         _REALITY_CONTRADICTION_SIM_CUTOFF),
        ("contradiction    paraphrase, NO shared words", sim(*SEMANTIC_PAIR),
         _REALITY_CONTRADICTION_SIM_CUTOFF),
        ("contradiction    unrelated (floor)", sim(*UNRELATED_PAIR),
         _REALITY_CONTRADICTION_SIM_CUTOFF),
    ]
    print(f"\n  model={model.model} dim={model.dimension}")
    print(f"  {'measurement':46} {'cosine':>7}  vs cutoff")
    for label, value, cutoff in rows:
        verdict = "FIRES" if value >= cutoff else "quiet"
        print(f"  {label:46} {value:7.3f}  {verdict} ({cutoff})")

    for _label, value, _cutoff in rows:
        assert -1.0001 <= value <= 1.0001


# ===========================================================================
# 4) The repo's fake must stay usable at the LIVE cutoff.
# ===========================================================================

def test_the_token_hash_fake_matches_the_one_the_suite_actually_runs_on():
    """`TokenHashFake` above mirrors `tests/test_daemon.py::FakeEmbedding`. If
    they drift, every comparison in this file describes a model the suite does
    not use. Checked by behaviour rather than by reading both files."""
    import test_daemon

    real_fake = test_daemon.FakeEmbedding()
    mirror = TokenHashFake()
    for text in ALL_PROBES:
        assert list(real_fake.embed(text)) == list(mirror.embed(text)), text


def test_the_fakes_floor_is_hash_collisions_not_word_overlap():
    """Why the fake is NOT pinned against the live cutoff — measured, so the
    next person to try it does not have to rediscover it.

    After the stopword fix, mundane text shares NO content word with any
    exemplar, yet its best score is 0.250 rather than 0.0. That is two content
    words landing in the same bucket of a 128-wide hash: numerator 1 over norms
    2x2. Pure birthday problem. It carries no information about the model and it
    moves if `DIM` or the probe wording changes, so asserting it stays under a
    tuning constant would be pinning luck.

    What IS meaningful is the MARGIN — collisions cap the fake's noise floor at a
    quarter, while exemplar-like text reaches a half or better, and that gap is a
    real property.
    """
    fake = TokenHashFake()
    plain = "what time does the library close on Sunday"
    exemplar = "I have never told anyone this before"

    content = lambda t: {  # noqa: E731 - local, one use
        w.strip(".,!?;:'\"") for w in t.lower().split()
    } - TokenHashFake.STOPWORDS
    assert not (content(plain) & content(exemplar))     # zero shared words...
    assert _cosine(fake.embed(plain), fake.embed(exemplar)) > 0.0  # ...nonzero score

    check_separates_ordinary_from_disclosure_by_margin(fake)


def test_the_fake_still_detects_near_exemplar_disclosure():
    """Non-vacuous partner to the test above: sharpening the fake must not have
    turned the signal off altogether. A fake that scored EVERYTHING at zero would
    pass the no-false-fire test trivially."""
    fake = TokenHashFake()
    for text in (
        "I have never told anyone this before",
        "I am scared and I do not know what to do",
    ):
        best = max(
            _cosine(fake.embed(text), fake.embed(exemplar))
            for exemplar in _VULNERABILITY_EXEMPLARS
        )
        assert best >= _VULNERABILITY_SIM_CUTOFF, (text, best)
