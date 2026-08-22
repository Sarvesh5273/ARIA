"""Concrete `EmbeddingModel` adapter — the local sentence-embedding model.

WHAT THIS SATISFIES
-------------------
`daemon.graph_manager.EmbeddingModel`, a one-method Protocol:

    def embed(self, text: str) -> Sequence[float]

One instance is shared by `MemoryGraph` and `AppraisalChain` — Addendum §1,
"one model serves both jobs rather than introducing two". Construct it once at
wiring time and pass the SAME object to both.

WHY THIS ADAPTER CANNOT BE STUBBED
----------------------------------
Four behaviours read this model's similarity output, and every one of them
changes when the vectors change:

    MemoryGraph.retrieve()              similarity is the base candidate ORDER
    MemoryGraph.reality_contradiction_check()   fires at cosine >= 0.6
    AppraisalChain._vulnerability()             fires at cosine >= 0.6
    MemoryGraph.register_edge_firing()          habituation at cosine >= 0.9

(The handoff listed `is_first_of_kind` as a fifth. It is not: that method is a
pure SQL check on (Q2, Q3) profiles and touches no embedding. Corrected here
rather than carried forward.)

None of those cutoffs has ever seen a real embedding — they are
`TODO(OQ1-rate)` / build-time placeholders. `tests/test_embedding_local.py`
carries the real-vs-fake comparison harness that produces the first genuine
tuning data for them. This adapter does NOT touch them.

MODEL CHOICE
------------
The precedence chain constrains the KIND of model and names no specific one:

    Addendum §1  "one small local sentence-embedding model — encoder-only, no
                 text-generation capability, on the order of tens of megabytes.
                 Not Gemma."
    Build Plan   "Local sentence-embedding model (encoder-only, tens of MB,
                 non-generative)"

`all-minilm` (all-MiniLM-L6-v2, 384-dim, tens of MB, encoder-only,
non-generative) satisfies every stated constraint, and is served by the same
Ollama daemon the local LLM transport already needs — so the whole bring-up
adds ZERO pip dependencies (stdlib `urllib` only). The model name is a
constructor parameter; nothing here hardcodes a choice into the soul layer,
which is the Rule 6 property this adapter exists to preserve.

DETERMINISM IS A HARD REQUIREMENT, NOT A NICETY
-----------------------------------------------
`MemoryGraph` PERSISTS embeddings (the `node_embeddings` and
`edge_firing_contexts` tables) and later compares freshly-computed vectors
against those stored rows. If `embed()` is not stable across process restarts,
`reality_contradiction_check` and habituation both silently degrade to "never
similar". Changing `model` invalidates every stored vector —
`graph_manager._init_schema` already says so in a comment; regenerate rather
than mix.

FAILURE MODE — READ THIS BEFORE CHANGING IT
-------------------------------------------
`embed()` raises `EmbeddingUnavailableError` when the backend cannot answer. It
deliberately does NOT return zeros on failure: a zero vector scores cosine 0.0
against everything, which reads as "nothing is similar" and would disable all
four behaviours above INVISIBLY.

Where that raise lands is uneven, and the wiring layer has to know it:

  * SWALLOWED — `MemoryGraph._store_embedding` wraps `embed()` in
    `except Exception` (a write-path degradation, non-fatal), and
    `AppraisalChain._vulnerability` returns False on any exception.
  * PROPAGATES — `MemoryGraph.reality_contradiction_check` calls `embed()`
    unguarded, so a failure there surfaces as a failed turn.

Because two of the three sites swallow, a down backend is partly invisible at
turn time. That is what `preflight()` is for: call it ONCE at startup, before
any turn, and fail loudly there instead. `main.py` does exactly that.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Dict, List, Optional, Sequence

# --- Build-time tuning knobs. Same category as every other TODO(build-time)
# placeholder in this project: the MECHANISM is fixed, the VALUE is not, and
# none of these is a soul number — they are transport plumbing. ---------------
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "all-minilm"          # encoder-only, tens of MB (Addendum §1)
DEFAULT_TIMEOUT_SECONDS = 30.0        # TODO(build-time)
DEFAULT_CACHE_ENTRIES = 512           # TODO(build-time)


class EmbeddingUnavailableError(RuntimeError):
    """The embedding backend could not answer this request.

    Raised for every provider failure — daemon unreachable, HTTP error, model
    not pulled, malformed response. Named and loud on purpose; see the module
    docstring on why returning zeros instead would be worse.
    """


class EmbeddingDimensionError(RuntimeError):
    """The backend returned a vector of a different length than it did before.

    Fatal rather than tolerated, because `graph_manager._cosine` and
    `appraisal_chain._cosine` both return 0.0 on a length mismatch instead of
    raising. A dimension change would therefore read as "nothing is ever
    similar" and quietly switch off retrieval ordering, reality-contradiction
    detection, vulnerability detection and habituation all at once.
    """


class OllamaEmbeddingModel:
    """`EmbeddingModel` backed by a local Ollama daemon's `/api/embed`.

    Holds no soul state: a host, a model name, an LRU cache of vectors, and the
    dimension it first observed. Computes no meaning and reads nothing from the
    graph.
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cache_entries: int = DEFAULT_CACHE_ENTRIES,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._cache_entries = max(0, int(cache_entries))
        # Insertion-ordered LRU. AppraisalChain._vulnerability re-embeds all
        # three VULNERABILITY exemplars on EVERY turn, so without a cache the
        # per-turn cost is 4+ round trips instead of 1.
        self._cache: "OrderedDict[str, List[float]]" = OrderedDict()
        self._dimension: Optional[int] = None
        self._calls = 0
        self._cache_hits = 0

    # -- read-only observability (not a decision surface) -------------------

    @property
    def model(self) -> str:
        return self._model

    @property
    def host(self) -> str:
        return self._host

    @property
    def dimension(self) -> Optional[int]:
        """Vector length observed so far, or None before the first success."""
        return self._dimension

    @property
    def stats(self) -> Dict[str, int]:
        """Backend calls vs cache hits. Diagnostics only."""
        return {"backend_calls": self._calls, "cache_hits": self._cache_hits}

    # -- the Protocol -------------------------------------------------------

    def embed(self, text: str) -> Sequence[float]:
        """Return the embedding of `text`.

        Empty or whitespace-only input never reaches the backend: it returns a
        zero vector (or `[]` before the dimension is known), both of which the
        callers' `_cosine` already maps to 0.0 — "similar to nothing". That is
        the honest answer for empty text and costs no round trip.
        """
        key = text or ""
        if not key.strip():
            return [0.0] * self._dimension if self._dimension else []

        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            self._cache_hits += 1
            return list(cached)

        vector = self._fetch(key)

        if self._dimension is None:
            self._dimension = len(vector)
        elif len(vector) != self._dimension:
            raise EmbeddingDimensionError(
                f"{self._model!r} returned a {len(vector)}-dim vector after "
                f"previously returning {self._dimension}-dim vectors. Mixed "
                f"dimensions silently disable every similarity behaviour "
                f"(cosine returns 0.0 on a length mismatch). Regenerate the "
                f"node_embeddings and edge_firing_contexts tables against one "
                f"model rather than mixing."
            )

        if self._cache_entries:
            self._cache[key] = list(vector)
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return list(vector)

    # -- startup check ------------------------------------------------------

    def preflight(self) -> int:
        """Prove the backend answers, and return the vector dimension.

        Call this ONCE at wiring time. Two of the three `embed()` call sites in
        the soul layer swallow exceptions, so a backend that is down is only
        partly visible during a turn. This is where it becomes fully visible.

        Raises `EmbeddingUnavailableError` with a remedy in the message.
        """
        try:
            vector = self._fetch("preflight")
        except EmbeddingUnavailableError as exc:
            raise EmbeddingUnavailableError(
                f"{exc}\n"
                f"  Embedding backend: {self._host} model={self._model!r}\n"
                f"  Start the daemon:  ollama serve\n"
                f"  Pull the model:    ollama pull {self._model}\n"
                f"  Without it, retrieval ordering, REALITY_CONTRADICTION, "
                f"VULNERABILITY_DISCLOSURE and habituation are all inert."
            ) from exc
        if self._dimension is None:
            self._dimension = len(vector)
        return self._dimension

    def is_reachable(self) -> bool:
        """Non-raising form of `preflight()`, for diagnostics only."""
        try:
            self.preflight()
        except EmbeddingUnavailableError:
            return False
        return True

    # -- provider plumbing --------------------------------------------------

    def _fetch(self, text: str) -> List[float]:
        """POST one string to `/api/embed` and return the vector.

        Ollama's current embedding endpoint takes `{"model", "input"}` and
        answers `{"embeddings": [[...]]}` — a list of vectors, one per input,
        because the endpoint is batch-capable. We send one string, so we read
        the first row. Every provider failure is translated to
        `EmbeddingUnavailableError`; nothing else is caught, so a genuine bug
        in this adapter still propagates as itself.
        """
        payload = json.dumps({"model": self._model, "input": text}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._host}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self._calls += 1
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # pragma: no cover - best-effort detail only
                pass
            raise EmbeddingUnavailableError(
                f"embedding backend returned HTTP {exc.code} for model "
                f"{self._model!r}{': ' + detail if detail else ''}"
            ) from exc
        except urllib.error.URLError as exc:
            raise EmbeddingUnavailableError(
                f"embedding backend unreachable at {self._host}: {exc.reason}"
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EmbeddingUnavailableError(
                f"embedding backend at {self._host} returned a non-JSON body"
            ) from exc
        except OSError as exc:
            raise EmbeddingUnavailableError(
                f"embedding backend I/O failure at {self._host}: {exc}"
            ) from exc

        return self._vector_from(body)

    def _vector_from(self, body: object) -> List[float]:
        """Pull the single vector out of an `/api/embed` response body."""
        if not isinstance(body, dict):
            raise EmbeddingUnavailableError(
                f"embedding response was {type(body).__name__}, expected an object"
            )
        rows = body.get("embeddings")
        if not isinstance(rows, list) or not rows:
            raise EmbeddingUnavailableError(
                f"embedding response carried no 'embeddings' array — is "
                f"{self._model!r} pulled, and is it an embedding model? "
                f"(`ollama pull {self._model}`)"
            )
        vector = rows[0]
        if not isinstance(vector, list) or not vector:
            raise EmbeddingUnavailableError(
                "embedding response carried an empty vector"
            )
        try:
            return [float(x) for x in vector]
        except (TypeError, ValueError) as exc:
            raise EmbeddingUnavailableError(
                "embedding response carried a non-numeric vector"
            ) from exc
