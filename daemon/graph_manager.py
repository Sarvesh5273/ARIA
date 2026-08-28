"""daemon/graph_manager.py — Module 3: Memory Graph.

Implements .kiro/specs/memory-graph/{requirements,design,tasks}.md — the only
persistent long-term memory store in ARIA. Holds four node types (Event /
Entity / Emotion / Uncertainty) and typed edges in SQLite, and provides
write paths, mood-congruent/need-preferenced retrieval, qualifying-evidence
lookups, and lazy retrieval-triggered precision decay.

Locked-spec provenance (precedence: Resolution Log > Addendum > v4):
  - Storage is SQLite (v4 "Context Window vs Graph" table: "Unlimited
    (SQLite, Phase 3+)"); this module IS graph_manager.py (v4 Key Technical
    Constants table attributes every graph mechanism to graph_manager.py).
  - Salience floors 0.85 (critical) / 0.55 (high), +0.15 negative bonus
    stacking on the floor — Resolution Log item 9 + v4 Layer 3 (Baumeister).
  - Precision decay ~72h/~14d/~60d, resistance vs BASE_salience (Resolution
    Log item 9 overrides v4's "salience" table wording — precedence),
    lazy/retrieval-triggered (Resolution Log item 8) — no decay-tick method.
  - relational_stage replaces trust_score (Addendum §2); stored here,
    transitions evaluated by DMN (Resolution Log "Resolved during build-plan
    review"). Staleness (7d/50int) evaluated by DMN Step 3; the max-5
    uncertainty cap is enforced here at creation (Addendum §4 redefines
    State_Manager as meaning-free, so graph-owned enforcement lives here).
  - "resolved" arc-closure edge weighted 3× (Resolution Log item 5); no new
    node type. Self-continuity narrative is a normal EntityNode's
    relationship_summary (Resolution Log item 2). relationship_depth is never
    touched (Resolution Log item 10; already dropped in state_manager.py).

Boundaries (Req 13): no direct PAD writes, no second memory store, no LLM
exposure. Enforced structurally (absent method surface), like Module 1.

Open Questions — architect resolutions applied (2026-07-05):
  RESOLVED (implemented, decision + rationale in the relevant method):
    OQ3 node embeddings → separate `node_embeddings` side-table, regenerate on
        model change (locked node schema untouched).
    OQ5 precision decay → total-elapsed-since-last_accessed, multi-step
        catch-up (not per-stage dwell).
    OQ4 retrieval → reorder-not-filter, MOOD-congruence PRIMARY / need
        SECONDARY, over a similarity candidate set. Pure ordering, NO score.
    OQ1 (trigger shape) → a firing is "without variation" if its
        retrieval-context embedding is similar to recent firings of the same
        edge; habituation adjusts edge salience ONLY (see register_edge_firing).
    OQ2 → Medium/Low poignancy: no base_salience floor per ResLog item 9.
        Decays/discards as already locked.
  DEFERRED (explicit placeholder + TODO — do NOT treat as final):
    OQ1-rate → habituation decrement/cutoff/window magnitudes (runtime-tuned).
  NOT THIS MODULE'S DECISION:
  RESOLVED 2026-08-26 (Resolution Log item 36) — listed because both used to sit
  under "NOT THIS MODULE'S DECISION" above and no longer do:
    OQ6 → `purpose_evidence` now implements Addendum §3's two named signals
        (credit attributed to her, or cross-session follow-through) instead of
        the any-positive-node stand-in. Item 36a.
    max-5 no-evictable-GRAPH_CONFLICT → the raise is GONE. v4 line 1313's
        maximum stays and eviction-of-a-protected-node stays refused, but the
        ceiling now DECLINES the sixth question (returns None) instead of
        killing the turn — the cognitive-ceiling option this file had itself
        flagged as probably right. Item 36c.
THE BOUNDARY (architect): salience/habituation are SUBSTRATE — they may be
numeric and adjusted, but are NEVER wired to compute a feeling. The protected
chain is memory-mechanics → retrieval ORDERING (never a weighted score) →
appraisal (categorical meaning) → PAD. Nothing here skips to "feeling = number".
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import (
    Dict, List, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable,
)

# ===========================================================================
# Task 2 — Enums (exact string domains from v4 Layer 3 / Addendum §2)
# ===========================================================================


class NodeType(Enum):
    EVENT = "event"
    ENTITY = "entity"
    EMOTION = "emotion"
    UNCERTAINTY = "uncertainty"


class Precision(Enum):  # v4 Layer 3 forgetting path
    VIVID = "vivid"
    PRESENT = "present"
    SOFTENED = "softened"
    FADED = "faded"


class PoignancyCategory(Enum):  # v4 Poignancy table
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Perspective(Enum):  # v4 Layer 3
    I_NOW = "I-Now"
    USER_NOW = "User-Now"
    WE = "We"


class RelationalStage(Enum):  # Addendum §2 — replaces the removed trust_score
    OBSERVING = "observing"
    ENGAGING = "engaging"
    INVESTED = "invested"
    BONDED = "bonded"


class UncertaintyType(Enum):  # v4 Layer 1 / Layer 3
    INPUT_UNCERTAIN = "INPUT_UNCERTAIN"
    VALENCE_UNCERTAIN = "VALENCE_UNCERTAIN"
    CAUSAL_UNCERTAIN = "CAUSAL_UNCERTAIN"
    GRAPH_CONFLICT = "GRAPH_CONFLICT"


class UncertaintyStatus(Enum):  # v4 Layer 3
    ACTIVE = "ACTIVE"
    RESOLVED_CONFIRMED = "RESOLVED_CONFIRMED"
    RESOLVED_INFERRED = "RESOLVED_INFERRED"
    ABANDONED = "ABANDONED"


class EdgeType(Enum):  # v4 Edge Schema (7-value domain)
    TRIGGERED = "triggered"
    CAUSED = "caused"
    RELATES_TO = "relates_to"
    RESOLVED = "resolved"  # arc closure, 3× salience (Resolution Log item 5)
    CONTRADICTS = "contradicts"
    CONNECTS = "connects"
    CRYSTALLIZED_INTO = "crystallized_into"


# The two uncertainty types that are always protected from force-abandon
# (v4 Layer 3: "INPUT_UNCERTAIN and VALENCE_UNCERTAIN ... cannot be
# force-abandoned").
_PROTECTED_UNCERTAINTY_TYPES = frozenset(
    {UncertaintyType.INPUT_UNCERTAIN, UncertaintyType.VALENCE_UNCERTAIN}
)

# ===========================================================================
# Constants (all locked/spec-sourced except the explicitly-flagged OQ items)
# ===========================================================================

# Salience floors by poignancy tier — Resolution Log item 9.
POIGNANCY_SALIENCE_FLOOR = {
    PoignancyCategory.CRITICAL: 0.85,
    PoignancyCategory.HIGH: 0.55,
    # Medium/Low: NO floor — Resolution Log item 9 states literally
    # "Medium/Low → no floor, decays/discards as already locked". That is a
    # positive instruction, not silence, so nothing is substituted for it.
}
# Baumeister negative-event encoding bonus — v4 Layer 3 / Key Technical
# Constants ("+0.15 base_salience for Q2 = negative EventNodes at creation").
NEGATIVE_SALIENCE_BONUS = 0.15

# Precision decay time thresholds — v4 Precision Decay Rates table.
DECAY_VIVID_TO_PRESENT = timedelta(hours=72)
DECAY_PRESENT_TO_SOFTENED = timedelta(days=14)
DECAY_SOFTENED_TO_FADED = timedelta(days=60)

# Precision decay resistance thresholds — v4 table wording says "salience",
# CORRECTED by Resolution Log item 9 to compare against base_salience
# ("Resistance checks compare against base_salience ... never against the
# fluctuating salience field"). Precedence: Resolution Log > v4.
RESIST_VIVID_TO_PRESENT = 0.8
RESIST_PRESENT_TO_SOFTENED = 0.5
RESIST_SOFTENED_TO_FADED = 0.3

# Argument-buffer resolution weight — Resolution Log item 5 / v4 Key Technical
# Constants ("Argument buffer resolution weight | 3× | graph_manager.py").
RESOLVED_EDGE_SALIENCE_MULTIPLIER = 3.0

# Max active uncertainty nodes — v4 Layer 3 ("Maximum active uncertainty
# nodes: 5").
MAX_ACTIVE_UNCERTAINTY_NODES = 5

# Retrieval result cap — v4 Graph Retrieval ("top 3–5 most relevant nodes").
RETRIEVAL_MAX_RESULTS = 5

# Need → recency-window mapping — Resolution Log item 7 (windows) + Addendum §3
# (evidence types). Reuses the three precision-decay windows; no new window.
WINDOW_CONNECTION = timedelta(hours=72)
WINDOW_GROWTH = timedelta(days=14)
WINDOW_PURPOSE = timedelta(days=14)
WINDOW_CONTINUITY = timedelta(days=60)

# Build-time tuning placeholders for REALITY_CONTRADICTION — Addendum "Open —
# build-time tuning constants only" lists the similarity cutoff and window
# duration as tuning constants (not architectural gaps). Carried as
# placeholders exactly as Module 1 carried PAD_HISTORY_LENGTH.
_REALITY_CONTRADICTION_SIM_CUTOFF = 0.6  # build-time tuning placeholder

#: How alike two of HER OWN self-observations must be to count as the same
#: pattern recurring. MEASURED 2026-08-26 against all-minilm via
#: `tools/measure_recurrence_cutoff.py` (24 pairs) — architect ruling, Resolution
#: Log item 37.
#:
#: WHY THIS IS NOT `_REALITY_CONTRADICTION_SIM_CUTOFF`. Item 36e reused that one,
#: at the architect's "reuse, do not invent" instruction, and measurement showed it
#: catches **0 of 12** genuine reworded recurrences: the producer was wired,
#: correct and inert. The cause is structural, not a badly chosen value — the two
#: constants answer DIFFERENT QUESTIONS and their pairs land in different bands:
#:
#:   "did he contradict himself?"    same subject, opposite polarity.
#:                                   "I'm happy in this job" vs "I'm not happy in
#:                                   this job" = 0.87. Sentence embeddings read
#:                                   the subject loudly and "not" barely at all,
#:                                   so these cluster HIGH (median 0.883) — which
#:                                   is exactly why contradiction detection pairs
#:                                   similarity with a SEPARATE negation check.
#:
#:   "has she noticed this before?"  same meaning, rebuilt from different words.
#:                                   "I waited through his silence" vs "There was
#:                                   a silence and I let it sit" = 0.60. Shares
#:                                   almost no vocabulary, so these cluster MID
#:                                   (median 0.455).
#:
#: The bands do not overlap, so no single value serves both: 0.6 catches
#: contradictions and no recurrences; 0.4 catches recurrences but would loosen
#: contradiction detection, and a false contradiction drives relational_stage
#: REGRESSION (Addendum §1) — trust damage, not noise.
#:
#: This is the FOURTH such cutoff, not a new kind of thing. The codebase already
#: measures one per question: `_VULNERABILITY_SIM_CUTOFF` 0.25,
#: `_HABITUATION_SIMILARITY_CUTOFF` 0.9, contradiction 0.6. Sharing one across two
#: questions is the thing this design avoids everywhere else.
#:
#: WHY 0.40 SPECIFICALLY. Measured recall/false-positive at each candidate:
#: 0.30 → 12/12 caught but 3/12 FALSE; 0.35 → 10/12 and 2/12 false; **0.40 → 9/12
#: caught, 0/12 false**; 0.45 → 6/12, 0 false. 0.40 is the lowest value with zero
#: false recurrences in the sample. The distributions OVERLAP slightly (recurrence
#: min 0.331 vs unrelated max 0.379) so nothing is perfect, and the asymmetry
#: decides it: a FALSE recurrence writes something untrue into who she is, while a
#: MISSED one only means she notices the pattern again next month.
#:
#: STILL A BUILD-TIME PLACEHOLDER. Measured on one model with 24 pairs, not
#: calibrated on her real conversations. Re-run the tool after a model change.
_RECURRENCE_SIM_CUTOFF = 0.40  # TODO(build-time) — measured 2026-08-26, item 37

#: How DMN Step 4 describes a flushed recent-learning EventNode. Defined HERE and
#: imported by `daemon/dmn.py` (which already imports from this module) rather than
#: written literally in both places: `recurring_self_observation` below MATCHES on
#: the self form, so two copies drifting apart would silently stop the
#: self-narrative producer finding anything — the same failure mode that made item
#: 31 move the format-marker regex instead of duplicating it.
LEARNING_PREFIX_FMT = "[recent-learning:{kind}] "
SELF_LEARNING_PREFIX = LEARNING_PREFIX_FMT.format(kind="self")
_REALITY_CONTRADICTION_WINDOW = timedelta(days=7)  # build-time tuning placeholder
# "basic negation detection" tokens — Addendum §1. Minimal lexical set; the
# exact criterion is a build-time tuning item.
_NEGATION_TOKENS = frozenset(
    {"not", "no", "never", "n't", "cannot", "can't", "won't", "didn't",
     "doesn't", "isn't", "wasn't", "aren't", "don't", "none", "nothing"}
)

# TODO(OQ1-rate): DEFERRED habituation tuning — placeholders only, tuned at
# runtime by watching her behave (the amount cannot be chosen well before
# then). The architect RESOLVED the OQ1 TRIGGER SHAPE — a firing is "without
# variation" if its retrieval-context embedding is similar to recent firings
# of the SAME edge — but DEFERRED the magnitudes below. salience is sanctioned
# substrate so a numeric decrement is allowed; GUARD: habituation adjusts edge
# `salience` ONLY, never PAD, never appraisal. This is the item flagged for
# HARDEST review.
_HABITUATION_SIMILARITY_CUTOFF = 0.9  # TODO(OQ1-rate) placeholder
_HABITUATION_DECREMENT = 0.05         # TODO(OQ1-rate) placeholder
_HABITUATION_RECENT_FIRINGS = 5       # TODO(OQ1-rate) placeholder (window size)


# ===========================================================================
# Embedding model dependency (injected interface — Addendum §1 "one model
# serves both" Appraisal_Chain and Memory_Graph; Rule 6). Memory_Graph never
# instantiates a concrete model and never hardcodes a model name.
# ===========================================================================


@runtime_checkable
class EmbeddingModel(Protocol):
    def embed(self, text: str) -> Sequence[float]:
        ...


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity — the standard realization of "semantic similarity"
    for sentence embeddings (v4 Layer 3 uses similarity for retrieval; no
    numeric cutoff is attached, selection is top-3–5)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ===========================================================================
# Time helpers
# ===========================================================================


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[Union[datetime, str]]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _enum_val(x):
    return x.value if isinstance(x, Enum) else x


# ===========================================================================
# Task 3 — Node and edge dataclasses (mirror v4 Layer 3 locked schema).
# NOT frozen: salience, precision, last_accessed, access_count,
# relational_stage, relationship_summary, uncertainty status are mutable over
# a node's lifetime (design.md Data Types). Mutation is confined to
# MemoryGraph methods; reads return detached copies.
# ===========================================================================


@dataclass
class EventNode:
    node_id: str
    timestamp: str
    session_id: str
    description: str
    context_excerpt_hash: str
    appraisal_q1: str  # "none"/"low"/"medium"/"high"
    appraisal_q2: str  # "positive"/"negative"/"neutral"/"VALENCE_UNCERTAIN"
    appraisal_q3: str  # "self"/"user"/"circumstance"/"CAUSAL_UNCERTAIN"
    appraisal_q4_notes: Optional[str]
    is_partial_appraisal: bool
    uncertainty_node_ref: Optional[str]
    pad_delta_p: float
    pad_delta_a: float
    pad_delta_d: float
    poignancy_category: PoignancyCategory
    base_salience: float
    salience: float
    precision: Precision
    perspective: Perspective
    entity_refs: List[str] = field(default_factory=list)
    access_count: int = 0
    last_accessed: Optional[str] = None
    node_type: NodeType = NodeType.EVENT


@dataclass
class EntityNode:
    node_id: str
    entity_type: str  # "person"/"project"/"place"/"concept"
    name: str
    first_encountered: str
    last_referenced: str
    reference_count: int
    # NOTE: NO trust_score field (removed, Addendum §2). relational_stage
    # replaces it. None until a stage is assigned; DMN evaluates transitions.
    relational_stage: Optional[RelationalStage]
    relationship_summary: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    net_valence: float = 0.0
    net_arousal: float = 0.0
    net_dominance: float = 0.0
    overall_salience: float = 0.0
    node_type: NodeType = NodeType.ENTITY


@dataclass
class EmotionNode:
    node_id: str
    emotion_label: str
    pad_p: float
    pad_a: float
    pad_d: float
    trigger_event_ref: str
    timestamp: str
    precision: Precision = Precision.VIVID
    # Always "critical" — only critical states crystallize (v4 Layer 3).
    poignancy_category: PoignancyCategory = PoignancyCategory.CRITICAL
    node_type: NodeType = NodeType.EMOTION


@dataclass
class UncertaintyNode:
    node_id: str
    uncertainty_type: UncertaintyType
    trigger_event_ref: str
    entity_ref: Optional[str]
    status: UncertaintyStatus
    created: str
    interaction_count: int = 0
    is_protected: bool = False
    resolved: Optional[str] = None
    resolution_path: Optional[str] = None
    catch_up_delta_p: Optional[float] = None
    catch_up_delta_a: Optional[float] = None
    catch_up_delta_d: Optional[float] = None
    catch_up_magnitude_factor: Optional[float] = None
    node_type: NodeType = NodeType.UNCERTAINTY


@dataclass
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    edge_type: EdgeType
    valence: float
    arousal: float
    dominance: float
    base_salience: float
    salience: float
    created: str
    perspective: Perspective = Perspective.I_NOW
    firing_count: int = 0
    last_activated: Optional[str] = None
    is_tension_pair: bool = False
    tension_partner_edge: Optional[str] = None
    is_aha_edge: bool = False


Node = Union[EventNode, EntityNode, EmotionNode, UncertaintyNode]
RetrievalItem = Union[Node, Edge]


# ===========================================================================
# MemoryGraph
# ===========================================================================


class MemoryGraph:
    """The persistent memory graph (Tasks 4–22)."""

    # -- Task 5: __init__ + injected embedding model --------------------------
    def __init__(
        self,
        connection_or_path: Union[str, sqlite3.Connection] = ":memory:",
        embedding_model: Optional[EmbeddingModel] = None,
    ) -> None:
        if isinstance(connection_or_path, sqlite3.Connection):
            self._conn = connection_or_path
        else:
            self._conn = sqlite3.connect(connection_or_path)
        self._conn.row_factory = sqlite3.Row
        # Injected dependency — NOT instantiated here, NOT hardcoded (Rule 6).
        self._embedding_model = embedding_model
        self._ready = False
        self._init_schema()
        self._ready = True

    # -- Task 4: SQLite schema ------------------------------------------------
    def _init_schema(self) -> None:
        c = self._conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS event_nodes (
                node_id TEXT PRIMARY KEY,
                timestamp TEXT, session_id TEXT, description TEXT,
                context_excerpt_hash TEXT,
                appraisal_q1 TEXT, appraisal_q2 TEXT, appraisal_q3 TEXT,
                appraisal_q4_notes TEXT, is_partial_appraisal INTEGER,
                uncertainty_node_ref TEXT,
                pad_delta_p REAL, pad_delta_a REAL, pad_delta_d REAL,
                poignancy_category TEXT,
                base_salience REAL, salience REAL,
                precision TEXT, perspective TEXT,
                entity_refs TEXT, access_count INTEGER, last_accessed TEXT
            );
            -- entity_nodes: NO trust_score column (removed, Addendum §2);
            -- HAS relational_stage column instead.
            CREATE TABLE IF NOT EXISTS entity_nodes (
                node_id TEXT PRIMARY KEY,
                entity_type TEXT, name TEXT, aliases TEXT,
                first_encountered TEXT, last_referenced TEXT,
                reference_count INTEGER,
                relationship_summary TEXT,
                relational_stage TEXT,
                net_valence REAL, net_arousal REAL, net_dominance REAL,
                overall_salience REAL
            );
            CREATE TABLE IF NOT EXISTS emotion_nodes (
                node_id TEXT PRIMARY KEY,
                emotion_label TEXT,
                pad_p REAL, pad_a REAL, pad_d REAL,
                trigger_event_ref TEXT, poignancy_category TEXT,
                precision TEXT, timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS uncertainty_nodes (
                node_id TEXT PRIMARY KEY,
                uncertainty_type TEXT, trigger_event_ref TEXT, entity_ref TEXT,
                status TEXT, created TEXT, resolved TEXT, resolution_path TEXT,
                catch_up_delta_p REAL, catch_up_delta_a REAL,
                catch_up_delta_d REAL, catch_up_magnitude_factor REAL,
                interaction_count INTEGER, is_protected INTEGER
            );
            CREATE TABLE IF NOT EXISTS edges (
                edge_id TEXT PRIMARY KEY,
                from_node TEXT, to_node TEXT, edge_type TEXT,
                valence REAL, arousal REAL, dominance REAL,
                base_salience REAL, salience REAL, firing_count INTEGER,
                perspective TEXT, created TEXT, last_activated TEXT,
                is_tension_pair INTEGER, tension_partner_edge TEXT,
                is_aha_edge INTEGER
            );
            -- OQ3 (RESOLVED — architect): node embeddings persist in this
            -- SEPARATE side-table keyed by node_id. The locked v4 node schema
            -- is NOT touched (no embedding field added to it). Regenerate this
            -- table if the embedding model changes (embeddings are only
            -- comparable within one model — Addendum §1, "one model serves
            -- both"). Pure plumbing: touches no feeling.
            CREATE TABLE IF NOT EXISTS node_embeddings (
                node_id TEXT PRIMARY KEY,
                embedding TEXT
            );
            -- OQ1 (RESOLVED trigger-shape — architect): habituation side-table.
            -- Records each edge FIRING's retrieval-context embedding so a
            -- firing can be judged "without variation" (embedding-similar to
            -- recent firings of the SAME edge — the architect's OQ1 trigger
            -- definition). Substrate/plumbing only; see register_edge_firing.
            -- GUARD: only edge salience is ever adjusted from this — never PAD,
            -- never appraisal.
            CREATE TABLE IF NOT EXISTS edge_firing_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id TEXT, embedding TEXT, fired_at TEXT
            );
            -- NOTE (Rule 7 / Req 13.2): no conversation-log, chat-vector-DB,
            -- or summary-file table exists or may be added — the graph is the
            -- only memory store.
            """
        )
        c.commit()

    def _require_ready(self) -> None:
        # Task 5 guard: methods raise if the store/deps are not wired.
        if not self._ready:
            raise RuntimeError("MemoryGraph is not initialized.")

    # -- embedding storage (OQ3-flagged) --------------------------------------
    def _store_embedding(self, node_id: str, text: Optional[str]) -> None:
        if self._embedding_model is None or not text:
            return
        try:
            vec = list(self._embedding_model.embed(text))
        except Exception:
            # A missing/failed embedding degrades similarity reachability for
            # this node (design Error Handling) — it is not fatal.
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO node_embeddings(node_id, embedding) "
            "VALUES (?, ?)",
            (node_id, json.dumps(vec)),
        )
        self._conn.commit()

    def _get_embedding(self, node_id: str) -> Optional[List[float]]:
        row = self._conn.execute(
            "SELECT embedding FROM node_embeddings WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if row is None or row["embedding"] is None:
            return None
        return json.loads(row["embedding"])

    # =======================================================================
    # Task 6 — write_event_node with base_salience floors
    # =======================================================================
    def write_event_node(
        self,
        *,
        description: str,
        session_id: str,
        appraisal_q1: str,
        appraisal_q2: str,
        appraisal_q3: str,
        poignancy_category: PoignancyCategory,
        pad_delta_p: float = 0.0,
        pad_delta_a: float = 0.0,
        pad_delta_d: float = 0.0,
        appraisal_q4_notes: Optional[str] = None,
        is_partial_appraisal: bool = False,
        uncertainty_node_ref: Optional[str] = None,
        perspective: Perspective = Perspective.I_NOW,
        entity_refs: Optional[List[str]] = None,
        context_excerpt_hash: str = "",
        timestamp: Optional[Union[datetime, str]] = None,
        now: Optional[datetime] = None,
    ) -> str:
        self._require_ready()
        now = now or _now()
        base_salience = self._compute_base_salience(poignancy_category, appraisal_q2)
        node = EventNode(
            node_id=str(uuid.uuid4()),
            timestamp=_iso(timestamp) or _iso(now),
            session_id=session_id,
            description=description,
            context_excerpt_hash=context_excerpt_hash,
            appraisal_q1=appraisal_q1,
            appraisal_q2=appraisal_q2,
            appraisal_q3=appraisal_q3,
            appraisal_q4_notes=appraisal_q4_notes,
            is_partial_appraisal=is_partial_appraisal,  # same path (Req 2.2)
            uncertainty_node_ref=uncertainty_node_ref,
            pad_delta_p=pad_delta_p,
            pad_delta_a=pad_delta_a,
            pad_delta_d=pad_delta_d,
            poignancy_category=poignancy_category,
            base_salience=base_salience,
            salience=base_salience,  # initial salience == base (design)
            precision=Precision.VIVID,  # a fresh memory is full-detail
            perspective=perspective,
            entity_refs=list(entity_refs or []),
            access_count=0,
            last_accessed=_iso(now),
        )
        self._insert_event_node(node)
        self._store_embedding(node.node_id, description)
        return node.node_id

    @staticmethod
    def _compute_base_salience(
        poignancy: PoignancyCategory, appraisal_q2: str
    ) -> float:
        """base_salience = poignancy_floor + (0.15 if Q2 negative).

        Resolution Log item 9 (floors: critical 0.85 / high 0.55) + v4
        Baumeister (+0.15 negative bonus). Medium/Low get NO floor — item 9
        says so literally ("Medium/Low → no floor, decays/discards as already
        locked"), so their floor contribution is nothing at all and they decay
        naturally against the resistance thresholds. The +0.15 negative bonus
        still stacks "on top of whichever floor applies" (item 9), which for
        medium/low means it stacks on nothing.
        Poignancy itself stays categorical; this only sets the substrate
        salience, which never directly computes a feeling.
        """
        floor = POIGNANCY_SALIENCE_FLOOR.get(poignancy, 0.0)  # medium/low: no floor
        bonus = NEGATIVE_SALIENCE_BONUS if appraisal_q2 == "negative" else 0.0
        return floor + bonus

    # =======================================================================
    # Task 7 — adjust_salience (fluctuating salience only; base immutable)
    # =======================================================================
    def adjust_salience(self, node_or_edge_id: str, new_salience: float) -> None:
        """Apply a caller-supplied salience to the fluctuating `salience`
        field only — NEVER base_salience (Req 5.5, 9.2).

        Habituation now has a defined trigger (see register_edge_firing, OQ1
        resolved); this remains the low-level setter it uses (and that DMN uses
        for consolidation salience raises/lowers). The habituation DECREMENT
        amount is a deferred placeholder — TODO(OQ1-rate).
        """
        self._require_ready()
        cur = self._conn
        # Node tables that carry a salience column: event_nodes. (Entity uses
        # overall_salience; emotion/uncertainty carry no fluctuating salience.)
        # Edges carry salience too.
        for table in ("event_nodes", "edges"):
            id_col = "node_id" if table == "event_nodes" else "edge_id"
            r = cur.execute(
                f"SELECT {id_col} FROM {table} WHERE {id_col} = ?",
                (node_or_edge_id,),
            ).fetchone()
            if r is not None:
                cur.execute(
                    f"UPDATE {table} SET salience = ? WHERE {id_col} = ?",
                    (new_salience, node_or_edge_id),
                )
                cur.commit()
                return
        raise KeyError(f"No salience-bearing node/edge with id {node_or_edge_id!r}")

    # -- OQ1 (RESOLVED trigger-shape — architect): habituation --------------
    def register_edge_firing(
        self,
        edge_id: str,
        context_embedding: Sequence[float],
        now: Optional[datetime] = None,
    ) -> bool:
        """Record an edge FIRING (a retrieval activation) with its
        retrieval-context embedding, update firing_count/last_activated, and
        apply HABITUATION iff this firing is "without variation".

        OQ1 trigger shape (architect-RESOLVED): a firing counts as "without
        variation" if its retrieval-context embedding is similar to recent
        firings of the SAME edge (reuse-before-invent: uses the existing shared
        embedding model, no new subsystem). When so, the edge's fluctuating
        `salience` is decremented so a worn-smooth, repetitive memory surfaces
        less readily.

        GUARD (architect): habituation adjusts edge `salience` ONLY. It NEVER
        produces a PAD change and NEVER feeds appraisal directly — salience is
        substrate, not feeling. (Structurally, MemoryGraph has no PAD/appraisal
        surface at all.) Returns whether habituation was applied.

        DEFERRED (TODO(OQ1-rate)): the decrement amount, the similarity cutoff,
        and the recent-firings window are placeholders tuned at runtime. This
        is the mechanism flagged for HARDEST review.
        """
        self._require_ready()
        now = now or _now()
        edge_row = self._conn.execute(
            "SELECT salience FROM edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
        if edge_row is None:
            raise KeyError(f"No edge with id {edge_id!r}")
        ctx = list(context_embedding)

        # Compare to recent prior firings of THIS edge (trigger shape).
        recent = self._conn.execute(
            "SELECT embedding FROM edge_firing_contexts WHERE edge_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (edge_id, _HABITUATION_RECENT_FIRINGS),
        ).fetchall()
        without_variation = False
        for r in recent:
            if r["embedding"] is None:
                continue
            if _cosine(ctx, json.loads(r["embedding"])) >= _HABITUATION_SIMILARITY_CUTOFF:
                without_variation = True
                break

        # Always record this firing + bump firing_count/last_activated.
        self._conn.execute(
            "INSERT INTO edge_firing_contexts(edge_id, embedding, fired_at) "
            "VALUES (?, ?, ?)",
            (edge_id, json.dumps(ctx), _iso(now)),
        )
        self._conn.execute(
            "UPDATE edges SET firing_count = firing_count + 1, last_activated = ? "
            "WHERE edge_id = ?",
            (_iso(now), edge_id),
        )

        if without_variation:
            # GUARD: salience ONLY. Decrement by the placeholder rate, floored
            # at 0.0 (salience is a magnitude, not a signed feeling).
            new_sal = max(0.0, edge_row["salience"] - _HABITUATION_DECREMENT)  # TODO(OQ1-rate)
            self._conn.execute(
                "UPDATE edges SET salience = ? WHERE edge_id = ?",
                (new_sal, edge_id),
            )
        self._conn.commit()
        return without_variation

    # =======================================================================
    # Task 8 — lazy precision-decay evaluation (retrieval-triggered)
    # =======================================================================
    def _target_precision(
        self, current: Precision, elapsed: timedelta, base_salience: float
    ) -> Precision:
        """Advance vivid→present→softened→faded through every transition whose
        TOTAL-elapsed-since-last_accessed threshold is exceeded, stopping at
        the first blocked by base_salience resistance or unmet threshold.

        Resistance compares against BASE_salience (Resolution Log item 9),
        NOT the fluctuating salience (v4 table wording, overridden).
        OQ5 (RESOLVED — architect): thresholds are TOTAL-elapsed-since-
        last_accessed checkpoints on one axis (NOT per-stage dwell) → multi-step
        catch-up in one lazy evaluation. Rationale: matches lazy,
        retrieval-triggered decay (Resolution Log item 8) and human forgetting —
        a memory nothing has touched in 60 days is `faded` now; it need not have
        "dwelt" in intermediate states unobserved. precision stays categorical;
        the durations are spec-locked, not invented.
        """
        transitions = [
            (Precision.VIVID, Precision.PRESENT,
             DECAY_VIVID_TO_PRESENT, RESIST_VIVID_TO_PRESENT),
            (Precision.PRESENT, Precision.SOFTENED,
             DECAY_PRESENT_TO_SOFTENED, RESIST_PRESENT_TO_SOFTENED),
            (Precision.SOFTENED, Precision.FADED,
             DECAY_SOFTENED_TO_FADED, RESIST_SOFTENED_TO_FADED),
        ]
        order = [Precision.VIVID, Precision.PRESENT, Precision.SOFTENED,
                 Precision.FADED]
        result = current
        for src, dst, threshold, resist in transitions:
            if order.index(result) != order.index(src):
                continue  # already past this transition
            if elapsed >= threshold and not (base_salience > resist):
                result = dst
            else:
                break  # first unmet/resisted transition halts the walk
        return result

    def _evaluate_precision(self, node: EventNode, now: datetime) -> Precision:
        """Compute the node's precision from time since its PREVIOUS access.
        Does not reset the timer (the caller/touch does that, AFTER this)."""
        last = _parse_dt(node.last_accessed) or _parse_dt(node.timestamp) or now
        elapsed = now - last
        if elapsed < timedelta(0):
            elapsed = timedelta(0)
        return self._target_precision(node.precision, elapsed, node.base_salience)

    def _touch_event_node(self, node: EventNode, now: datetime) -> None:
        """Retrieval touch: evaluate precision (from old last_accessed), THEN
        reset last_accessed/access_count (Req 4.6). faded is terminal; nodes
        are never deleted (Req 4.5)."""
        new_precision = self._evaluate_precision(node, now)
        node.precision = new_precision  # advance (never regress; never delete)
        node.last_accessed = _iso(now)
        node.access_count += 1
        self._conn.execute(
            "UPDATE event_nodes SET precision = ?, last_accessed = ?, "
            "access_count = ? WHERE node_id = ?",
            (new_precision.value, node.last_accessed, node.access_count,
             node.node_id),
        )
        self._conn.commit()

    # =======================================================================
    # Task 9 — create_uncertainty_node with the max-5 cap
    # =======================================================================
    def create_uncertainty_node(
        self,
        *,
        uncertainty_type: UncertaintyType,
        trigger_event_ref: str,
        entity_ref: Optional[str] = None,
        interaction_count: int = 0,
        created: Optional[Union[datetime, str]] = None,
        now: Optional[datetime] = None,
    ) -> Optional[str]:
        """Create an active UncertaintyNode, or return None when the cognitive
        ceiling holds.

        THE CEILING IS A REAL CEILING NOW (2026-08-26 architect ruling). v4 line
        1313 locks `Uncertainty node maximum | 5 active nodes` and that is
        unchanged — what changed is what happens on the sixth. Previously this
        RAISED `RuntimeError` when the cap was hit with no evictable
        GRAPH_CONFLICT node, which killed the turn: a traceback in the middle of
        an ordinary conversation because she was already holding five things.

        Now no node forms and the turn proceeds. That is what the code already
        flagged as the likely right answer — *"the human-like resolution may be
        that a new uncertainty simply does not FORM when she is already at her
        limit — a real cognitive ceiling — rather than raising"* — so this
        executes a flagged plan rather than inventing one.

        IT IS NOT AN EVICTION POLICY, which is the thing the architect explicitly
        refused. Nothing existing is dropped, and no protected node is touched.
        The ceiling declines the NEW question, which is what a person already
        holding a lot does; the alternative — quietly discarding something she is
        already carrying — is the invention that was rejected.

        Returns the new node_id, or **None** when the ceiling held.
        `AppraisalResult.uncertainty_node_id` is already `Optional[str]`, so None
        propagates through both call sites with no signature change downstream.

        Observability: `at_uncertainty_capacity()` reports the condition without
        consuming it, so a caller can tell the difference between "no uncertainty
        arose this turn" and "one arose and could not be held".
        """
        self._require_ready()
        now = now or _now()
        active = self._active_uncertainty_rows()
        if len(active) >= MAX_ACTIVE_UNCERTAINTY_NODES:
            if not self._force_abandon_oldest_graph_conflict(active):
                # Ceiling holds: she is at capacity and nothing may be evicted.
                return None
        is_protected = uncertainty_type in _PROTECTED_UNCERTAINTY_TYPES
        node = UncertaintyNode(
            node_id=str(uuid.uuid4()),
            uncertainty_type=uncertainty_type,
            trigger_event_ref=trigger_event_ref,
            entity_ref=entity_ref,
            status=UncertaintyStatus.ACTIVE,
            created=_iso(created) or _iso(now),
            interaction_count=interaction_count,
            is_protected=is_protected,
        )
        self._insert_uncertainty_node(node)
        return node.node_id

    def _active_uncertainty_rows(self) -> List[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM uncertainty_nodes WHERE status = ? ORDER BY created ASC",
            (UncertaintyStatus.ACTIVE.value,),
        ).fetchall()

    def at_uncertainty_capacity(self, now: Optional[datetime] = None) -> bool:
        """Is she holding the maximum number of open questions with none that may
        be evicted? DERIVED from the current rows — no stored flag, so asking does
        not consume or destroy the condition (the same reasoning as item 31's
        `all_narration_replies`).

        This is the signal behind the at-capacity behaviour: the COUNT never
        leaves this module, only the yes/no. v4's max of 5 is untouched."""
        self._require_ready()
        active = self._active_uncertainty_rows()
        if len(active) < MAX_ACTIVE_UNCERTAINTY_NODES:
            return False
        return not any(
            row["uncertainty_type"] == UncertaintyType.GRAPH_CONFLICT.value
            for row in active
        )

    def _force_abandon_oldest_graph_conflict(
        self, active_rows: List[sqlite3.Row]
    ) -> bool:
        """Evict the oldest evictable node. Returns True if one was evicted,
        False if the ceiling holds (no GRAPH_CONFLICT node to take)."""
        # Evict the OLDEST GRAPH_CONFLICT active node; never a protected node.
        for row in active_rows:  # already ordered created ASC (oldest first)
            if row["uncertainty_type"] == UncertaintyType.GRAPH_CONFLICT.value:
                # v4 specifies the force-abandon but NOT a resolution_path for
                # a capacity-forced eviction; its domain is {direct_information,
                # behavioral_inference, dmn_consolidation, staleness, null}.
                # Use null rather than inventing a new domain value (Rule 1);
                # status=ABANDONED already distinguishes it.
                self._conn.execute(
                    "UPDATE uncertainty_nodes SET status = ?, resolution_path = NULL "
                    "WHERE node_id = ?",
                    (UncertaintyStatus.ABANDONED.value, row["node_id"]),
                )
                self._conn.commit()
                return True
        # Cap hit with NO evictable GRAPH_CONFLICT node (all remaining are
        # protected INPUT/VALENCE or CAUSAL_UNCERTAIN). v4 is silent on this.
        #
        # RESOLVED 2026-08-26 (architect ruling). This RAISED `RuntimeError`,
        # which killed the turn — a traceback mid-conversation because she was
        # already holding five things. The eviction-of-a-protected-node policy the
        # architect refused is STILL refused; what happens instead is the option
        # this very comment flagged as probably right: *"a new uncertainty simply
        # does not FORM when she is already at her limit — a real cognitive
        # ceiling"*. So the ceiling declines the NEW question and nothing existing
        # is disturbed.
        return False

    # =======================================================================
    # Task 10 — update_uncertainty_status (resolution / staleness ABANDONED)
    # =======================================================================
    def update_uncertainty_status(
        self,
        node_id: str,
        status: UncertaintyStatus,
        *,
        resolution_path: Optional[str] = None,
        catch_up_delta_p: Optional[float] = None,
        catch_up_delta_a: Optional[float] = None,
        catch_up_delta_d: Optional[float] = None,
        catch_up_magnitude_factor: Optional[float] = None,
        resolved: Optional[Union[datetime, str]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Accept RESOLVED_* / ABANDONED writes. The catch_up_* fields are
        stored as DATA ONLY — Memory_Graph NEVER applies a PAD shift (Req 13.1;
        the catch-up shift is a secondary appraisal elsewhere).

        Accepts a DMN-supplied staleness ABANDONED (resolution_path=
        "staleness"). This module does NOT evaluate the 7d/50-interaction
        threshold — that is DMN Step 3's (Req 3.3). It stores/exposes
        interaction_count and created but never auto-abandons.
        """
        self._require_ready()
        now = now or _now()
        resolved_iso = None
        if status != UncertaintyStatus.ACTIVE:
            resolved_iso = _iso(resolved) or _iso(now)
        self._conn.execute(
            "UPDATE uncertainty_nodes SET status = ?, resolution_path = ?, "
            "resolved = ?, catch_up_delta_p = ?, catch_up_delta_a = ?, "
            "catch_up_delta_d = ?, catch_up_magnitude_factor = ? "
            "WHERE node_id = ?",
            (status.value, resolution_path, resolved_iso,
             catch_up_delta_p, catch_up_delta_a, catch_up_delta_d,
             catch_up_magnitude_factor, node_id),
        )
        self._conn.commit()

    def increment_uncertainty_interaction_count(self, node_id: str) -> None:
        """Increment interaction_count by 1 for an ACTIVE UncertaintyNode.
        Called by Appraisal Chain per turn for each active uncertainty ref
        (Resolution Log item 10). Memory_Graph stores and increments; DMN
        Step 3 evaluates the staleness threshold (50 interactions). This
        module never auto-abandons — that is DMN's job (Req 3.3)."""
        self._require_ready()
        r = self._conn.execute(
            "SELECT node_id FROM uncertainty_nodes WHERE node_id = ? "
            "AND status = ?",
            (node_id, UncertaintyStatus.ACTIVE.value),
        ).fetchone()
        if r is None:
            raise KeyError(
                f"No ACTIVE UncertaintyNode with id {node_id!r} — "
                "node may not exist or may already be resolved/abandoned."
            )
        self._conn.execute(
            "UPDATE uncertainty_nodes SET interaction_count = "
            "interaction_count + 1 WHERE node_id = ?",
            (node_id,),
        )
        self._conn.commit()

    # =======================================================================
    # Tasks 11–12 — write_edge (connection/aha/tension; resolved = 3× salience)
    # =======================================================================
    def write_edge(
        self,
        *,
        from_node: str,
        to_node: str,
        edge_type: EdgeType,
        valence: float = 0.0,
        arousal: float = 0.0,
        dominance: float = 0.0,
        base_salience: float = 0.0,
        perspective: Perspective = Perspective.I_NOW,
        is_tension_pair: bool = False,
        tension_partner_edge: Optional[str] = None,
        is_aha_edge: bool = False,
        created: Optional[Union[datetime, str]] = None,
        now: Optional[datetime] = None,
    ) -> str:
        self._require_ready()
        now = now or _now()
        salience = base_salience
        # Task 12: a "resolved" arc-closure edge is weighted 3× at creation
        # (Resolution Log item 5; v4 "Argument buffer resolution weight | 3×").
        # It is directed closing→opening EventNode by the caller's from/to.
        if edge_type == EdgeType.RESOLVED:
            salience = base_salience * RESOLVED_EDGE_SALIENCE_MULTIPLIER
        edge = Edge(
            edge_id=str(uuid.uuid4()),
            from_node=from_node,
            to_node=to_node,
            edge_type=edge_type,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            base_salience=base_salience,
            salience=salience,
            created=_iso(created) or _iso(now),
            perspective=perspective,
            is_tension_pair=is_tension_pair,
            tension_partner_edge=tension_partner_edge,
            is_aha_edge=is_aha_edge,
        )
        self._insert_edge(edge)
        return edge.edge_id

    # =======================================================================
    # Task 13 — crystallize_emotion_node (critical-only)
    # =======================================================================
    def crystallize_emotion_node(
        self,
        *,
        emotion_label: str,
        pad_p: float,
        pad_a: float,
        pad_d: float,
        trigger_event_ref: str,
        poignancy_category: PoignancyCategory = PoignancyCategory.CRITICAL,
        timestamp: Optional[Union[datetime, str]] = None,
        now: Optional[datetime] = None,
    ) -> str:
        self._require_ready()
        now = now or _now()
        if poignancy_category != PoignancyCategory.CRITICAL:
            # Only critical states crystallize (Req 8.1) — do not coerce.
            raise ValueError(
                "EmotionNode crystallizes only at poignancy_category=critical; "
                f"got {poignancy_category!r}."
            )
        # NOTE (Req 4.1 EmotionNode precision): EmotionNodes are ALWAYS
        # critical. Per Resolution Log item 9, a critical memory (floor 0.85 >
        # the 0.8 vivid→present resistance threshold) "resists vivid→present
        # indefinitely — stays word-for-word forever." So an EmotionNode's
        # precision never advances from VIVID; there is deliberately no decay
        # path for emotion nodes (and the v4 EmotionNode schema carries no
        # base_salience/last_accessed fields, consistent with that). This is
        # correct behavior, not a missing path — see test_emotion_node_stays_vivid.
        node = EmotionNode(
            node_id=str(uuid.uuid4()),
            emotion_label=emotion_label,
            pad_p=pad_p,
            pad_a=pad_a,
            pad_d=pad_d,
            trigger_event_ref=trigger_event_ref,
            timestamp=_iso(timestamp) or _iso(now),
            precision=Precision.VIVID,
            poignancy_category=PoignancyCategory.CRITICAL,
        )
        self._insert_emotion_node(node)
        return node.node_id

    # =======================================================================
    # Task 14 — update_relationship_summary (single path incl. self node)
    # =======================================================================
    def update_relationship_summary(
        self, entity_node_id: str, text: str, now: Optional[datetime] = None
    ) -> None:
        """One write path for EVERY EntityNode's relationship_summary,
        including the self-referential EntityNode (Resolution Log item 2: no
        new node type, no self-model-specific method). The self-continuity
        narrative lives here.

        Records the extension time on `last_referenced` — this is the design's
        stated proxy for continuity_evidence (Addendum §3 Continuity =
        "satisfied when an update extends the narrative coherently"). Without
        this, continuity_evidence would measure entity age, not
        narrative-extension recency. (If the architect prefers a dedicated
        `summary_last_updated` field over reusing last_referenced, that is a
        flagged refinement — see design Open Questions / continuity note.)
        """
        self._require_ready()
        now = now or _now()
        r = self._conn.execute(
            "SELECT node_id FROM entity_nodes WHERE node_id = ?",
            (entity_node_id,),
        ).fetchone()
        if r is None:
            raise KeyError(f"No EntityNode with id {entity_node_id!r}")
        self._conn.execute(
            "UPDATE entity_nodes SET relationship_summary = ?, "
            "last_referenced = ? WHERE node_id = ?",
            (text, _iso(now), entity_node_id),
        )
        self._conn.commit()

    # =======================================================================
    # Task 15 — set/get_relational_stage (accept only; NO gate evaluation)
    # =======================================================================
    def set_relational_stage(
        self, entity_node_id: str, stage: RelationalStage
    ) -> None:
        """Accept and persist a DMN-decided stage (advance or one-step
        regression). Performs NO gate evaluation (Req 7.5) — DMN Step 4 owns
        that. Never reads/writes aria_state.json.relationship_depth (Req 7.6)."""
        self._require_ready()
        r = self._conn.execute(
            "SELECT node_id FROM entity_nodes WHERE node_id = ?",
            (entity_node_id,),
        ).fetchone()
        if r is None:
            raise KeyError(f"No EntityNode with id {entity_node_id!r}")
        self._conn.execute(
            "UPDATE entity_nodes SET relational_stage = ? WHERE node_id = ?",
            (stage.value, entity_node_id),
        )
        self._conn.commit()

    def get_relational_stage(
        self, entity_node_id: str
    ) -> Optional[RelationalStage]:
        self._require_ready()
        r = self._conn.execute(
            "SELECT relational_stage FROM entity_nodes WHERE node_id = ?",
            (entity_node_id,),
        ).fetchone()
        if r is None:
            raise KeyError(f"No EntityNode with id {entity_node_id!r}")
        val = r["relational_stage"]
        return RelationalStage(val) if val is not None else None

    # =======================================================================
    # Task 16 — embedding-backed similarity ranking
    # =======================================================================
    def _similarity_rank(
        self, query_embedding: Sequence[float]
    ) -> List[tuple]:
        """Return [(node_id, similarity)] for embedded event nodes, ranked
        desc. Nodes lacking an embedding are excluded from similarity ranking
        (still reachable via entity_ref/other queries) — not fatal."""
        rows = self._conn.execute(
            "SELECT e.node_id AS nid, ne.embedding AS emb "
            "FROM event_nodes e JOIN node_embeddings ne ON e.node_id = ne.node_id"
        ).fetchall()
        scored = []
        for row in rows:
            if row["emb"] is None:
                continue
            vec = json.loads(row["emb"])
            scored.append((row["nid"], _cosine(query_embedding, vec)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    # =======================================================================
    # Tasks 17–18 — retrieve() with mood-congruence + need-preference
    # =======================================================================
    def retrieve(
        self,
        *,
        pad_pleasure_sign: int,
        need_prefs: Optional[dict] = None,
        entity_refs: Optional[List[str]] = None,
        query_embedding: Optional[Sequence[float]] = None,
        now: Optional[datetime] = None,
    ) -> List[RetrievalItem]:
        """Return up to 5 relevant items (Req 6.1). Candidate selection by
        similarity (Req 6.4) + entity_refs; mood-congruence (Req 6.2) and
        need-preference (Req 6.3) applied as STABLE-SORT REORDERINGS, never a
        numeric coefficient (Req 6.5).

        OQ4 (RESOLVED — architect): reorder-not-filter over a
        similarity-generated candidate set, with MOOD-CONGRUENCE PRIMARY and
        NEED-PREFERENCE SECONDARY. This is PURE ORDERING — no coefficient, no
        weighted score, no "similarity*w1 + valence*w2 + need*w3". Similarity
        gathers candidates; her current mood surfaces congruent ones first;
        need breaks the remaining ties. This is how her feeling shapes what she
        remembers — by preference, the human way (v4: "the preference IS the
        mechanism"; Addendum §3: need-preference is a secondary context-shaper),
        never by arithmetic. (Implementation: stable sorts, need applied first
        then mood applied last, so mood dominates — see below.)
        """
        self._require_ready()
        now = now or _now()
        need_prefs = need_prefs or {}
        entity_refs = entity_refs or []

        # --- candidate nodes: similarity order, plus entity_ref matches ---
        ordered_ids: List[str] = []
        if query_embedding is not None:
            ordered_ids = [nid for nid, _ in self._similarity_rank(query_embedding)]
        # entity_ref matches appended (dedup, preserve order)
        for row in self._conn.execute("SELECT node_id, entity_refs FROM event_nodes").fetchall():
            refs = json.loads(row["entity_refs"] or "[]")
            if any(er in refs for er in entity_refs) and row["node_id"] not in ordered_ids:
                ordered_ids.append(row["node_id"])

        candidate_nodes = [self._load_event_node(nid) for nid in ordered_ids]
        candidate_nodes = [n for n in candidate_nodes if n is not None]

        # --- edges incident to candidate nodes, in node-rank order ---
        candidate_edges: List[Edge] = []
        seen_edges = set()
        for n in candidate_nodes:
            for e in self._edges_incident_to(n.node_id):
                if e.edge_id not in seen_edges:
                    seen_edges.add(e.edge_id)
                    candidate_edges.append(e)

        # base candidate order: node then its edges (deterministic, tied to
        # similarity rank). Dedup edges by edge_id so an edge whose BOTH
        # endpoints are candidate nodes is not appended twice.
        candidates: List[RetrievalItem] = []
        appended_edge_ids = set()
        for n in candidate_nodes:
            candidates.append(n)
            for e in candidate_edges:
                if (e.from_node == n.node_id or e.to_node == n.node_id) \
                        and e.edge_id not in appended_edge_ids:
                    candidates.append(e)
                    appended_edge_ids.add(e.edge_id)
        # include any remaining edges (e.g. incident to lower-ranked nodes)
        for e in candidate_edges:
            if e.edge_id not in appended_edge_ids:
                candidates.append(e)
                appended_edge_ids.add(e.edge_id)

        # --- need-preference reorder (Req 6.3): need-relevant first ---
        # SECONDARY (architect OQ4): applied FIRST so the PRIMARY mood sort
        # below dominates it (stable sort → the last sort applied wins ties).
        if need_prefs:
            def need_key(item: RetrievalItem) -> int:
                return 0 if self._need_relevant(item, need_prefs) else 1
            candidates.sort(key=need_key)  # stable

        # --- mood-congruence reorder (Req 6.2): matching-sign first ---
        # PRIMARY (architect OQ4 resolution): applied LAST so it is the
        # dominant preference; need-preference (above) breaks ties among
        # equally mood-congruent items; similarity is the base order beneath
        # both. Pure ORDERING — stable-sort partition on a categorical 0/1 key,
        # NO coefficient, NO weighted score. "The preference IS the mechanism."
        def mood_key(item: RetrievalItem) -> int:
            sign = self._valence_sign(item)
            if sign == 0 or pad_pleasure_sign == 0:
                return 1  # neutral / no preference → after matches
            return 0 if sign == pad_pleasure_sign else 1

        candidates.sort(key=mood_key)  # stable — PRIMARY

        results = candidates[:RETRIEVAL_MAX_RESULTS]

        # --- Task 18: precision touch (evaluate-then-reset) on RETURNED nodes
        for item in results:
            if isinstance(item, EventNode):
                self._touch_event_node(item, now)
        # --- OQ1 (architect trigger-shape): returned edges "fire". Register
        # each firing with the retrieval-context embedding so habituation can
        # decrement salience if this firing is "without variation" (similar to
        # recent firings of the same edge). Only when a query_embedding is
        # available (no context → cannot judge variation). GUARD: touches edge
        # salience ONLY, never PAD/appraisal.
        if query_embedding is not None:
            for item in results:
                if isinstance(item, Edge):
                    self.register_edge_firing(item.edge_id, query_embedding, now)
        return results

    @staticmethod
    def _valence_sign(item: RetrievalItem) -> int:
        # Mood-congruence is defined on edge valence (v4). For EventNodes we use
        # appraisal_q2 as the node-level valence analog; others are neutral.
        if isinstance(item, Edge):
            return (item.valence > 0) - (item.valence < 0)
        if isinstance(item, EventNode):
            if item.appraisal_q2 == "positive":
                return 1
            if item.appraisal_q2 == "negative":
                return -1
        if isinstance(item, EntityNode):
            return (item.net_valence > 0) - (item.net_valence < 0)
        return 0

    @staticmethod
    def _need_relevant(item: RetrievalItem, need_prefs: dict) -> bool:
        # Need-preference is the SECONDARY ordering key (architect OQ4). What
        # counts as need-relevant for Connection is spec-grounded: Addendum §3 —
        # "When Connection is neglected, Stage 1 surfaces 'We'-perspective and
        # Connection-positive edges first." Only Connection's profile is
        # exemplified in the spec; preference profiles for Growth/Purpose/
        # Continuity would extend this per their (Needs System / Module 2)
        # definitions and are not invented here.
        #
        # CONTRACT: prefs["connection"] means "Connection is NEGLECTED" — the
        # one state §3 attaches this profile to. The caller (appraisal_chain's
        # _need_prefs) sets it for that state only; it is deliberately not set
        # for the weaker `due`.
        if not need_prefs.get("connection"):
            return False
        persp = getattr(item, "perspective", None)
        if persp == Perspective.WE:
            return True
        return MemoryGraph._valence_sign(item) > 0

    def _edges_incident_to(self, node_id: str) -> List[Edge]:
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE from_node = ? OR to_node = ?",
            (node_id, node_id),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    # =======================================================================
    # Task 19 — Needs_System qualifying-evidence queries (structural only;
    # NEVER compute a need state — Req 11.5)
    # =======================================================================
    def connection_evidence(
        self, now: Optional[datetime] = None, window: timedelta = WINDOW_CONNECTION
    ) -> bool:
        """Connection: an EventNode with appraisal_q1 in {medium, high} within
        72h (Addendum §3 evidence; Resolution Log item 7 window)."""
        self._require_ready()
        now = now or _now()
        cutoff = _iso(now - window)
        row = self._conn.execute(
            "SELECT 1 FROM event_nodes WHERE appraisal_q1 IN ('medium','high') "
            "AND timestamp >= ? LIMIT 1",
            (cutoff,),
        ).fetchone()
        return row is not None

    def growth_evidence(
        self, now: Optional[datetime] = None, window: timedelta = WINDOW_GROWTH
    ) -> bool:
        """Growth: an UncertaintyNode resolved CONFIRMED/INFERRED (not
        ABANDONED) within 14d (Addendum §3)."""
        self._require_ready()
        now = now or _now()
        cutoff = _iso(now - window)
        row = self._conn.execute(
            "SELECT 1 FROM uncertainty_nodes WHERE status IN "
            "('RESOLVED_CONFIRMED','RESOLVED_INFERRED') AND resolved >= ? LIMIT 1",
            (cutoff,),
        ).fetchone()
        return row is not None

    def purpose_evidence(
        self, now: Optional[datetime] = None, window: timedelta = WINDOW_PURPOSE
    ) -> bool:
        """Purpose: user follow-through / explicit positive feedback within 14d.

        OQ6 RESOLVED 2026-08-26 (architect ruling). This was a STAND-IN: "any
        positive-valence EventNode in-window", explicitly flagged as
        `TODO(OQ6-M2)` and awaiting a structural definition of "follow-through".

        WHY THE STAND-IN HAD TO GO. It made Purpose almost always satisfied — one
        cheerful remark in a fortnight met it — so a need that is supposed to mean
        "she had a positive effect on his life" instead meant "the last two weeks
        contained a good moment". The failure mode was FALSE POSITIVES, which is
        the quiet kind: Purpose reads healthy, so it never shapes retrieval and
        never raises an initiative, and one of her four needs is effectively
        switched off in the position that looks like health.

        WHAT IT IS NOW. Addendum §3 names two qualifying signals and this
        implements both, as an OR — either is sufficient:

        (a) **Explicit positive feedback about HER.** `appraisal_q2 = 'positive'`
            AND `appraisal_q3 = 'self'`. Q3's `self` is ARIA as the cause, not the
            user: `_SELF_ATTRIBUTION_CUES` are second-person ("you helped",
            "because of you"), and `_dominance_dir` reads `SELF + POSITIVE` as
            "agency affirmed". So this is the user crediting her, which is exactly
            §3's "explicit positive feedback".

        (b) **Follow-through.** An in-window EventNode sharing at least one
            `entity_ref` with an EARLIER node from a DIFFERENT session whose
            `appraisal_q1` was medium or high. Three existing pieces, no new one:
            entity-ref overlap is the categorical topic-continuation test DMN
            already uses (`_topic_continued`); `q1 in (medium, high)` is the
            substantiveness signal `connection_evidence` already uses, standing
            for §3's "something substantive"; and the session boundary is what
            makes it FOLLOW-through rather than still-talking-about-it — returning
            to a subject in a later session is the return, whereas mentioning it
            twice in one sitting is one conversation.

        NO NEW NUMBER, NO NEW FIELD, and the locked `WINDOW_PURPOSE` (14d, item 7)
        is untouched — only the predicate changed.

        WHAT IS STILL THIS MODULE'S BOUNDARY: it answers the query, it does not
        decide the need state. `NeedsSystem` still owns satisfied/due/neglected
        (Req 11.5).

        COST, stated rather than hidden: (b) needs `entity_refs`, which is stored
        as JSON text, so it is resolved in Python over one pass rather than in SQL
        — the same shape `retrieve` and `is_first_of_kind` already use. Bounded by
        graph size, single pass, indexed by ref.
        """
        self._require_ready()
        now = now or _now()
        cutoff = _iso(now - window)

        # (a) Explicit positive feedback attributed to HER.
        row = self._conn.execute(
            "SELECT 1 FROM event_nodes WHERE appraisal_q2 = 'positive' "
            "AND appraisal_q3 = 'self' AND timestamp >= ? LIMIT 1",
            (cutoff,),
        ).fetchone()
        if row is not None:
            return True

        # (b) Follow-through: an in-window turn returning to a substantive topic
        # from an EARLIER session.
        helped: Dict[str, List[Tuple[str, str]]] = {}   # ref -> [(timestamp, session)]
        recent: List[Tuple[str, str, List[str]]] = []   # (timestamp, session, refs)
        for r in self._conn.execute(
            "SELECT timestamp, session_id, appraisal_q1, entity_refs FROM event_nodes"
        ).fetchall():
            refs = json.loads(r["entity_refs"] or "[]")
            if not refs:
                continue
            stamp, session = r["timestamp"], r["session_id"] or ""
            if r["appraisal_q1"] in ("medium", "high"):
                for ref in refs:
                    helped.setdefault(ref, []).append((stamp, session))
            if stamp is not None and stamp >= cutoff:
                recent.append((stamp, session, refs))

        for stamp, session, refs in recent:
            for ref in refs:
                for prior_stamp, prior_session in helped.get(ref, ()):
                    if prior_stamp < stamp and prior_session != session:
                        return True
        return False

    def continuity_evidence(
        self,
        self_entity_id: str,
        now: Optional[datetime] = None,
        window: timedelta = WINDOW_CONTINUITY,
    ) -> bool:
        """Continuity: whether the self-referential EntityNode's
        relationship_summary was extended within 60d. Reuses the narrative
        update mechanism (Addendum §3). Uses last_referenced as the
        extension timestamp proxy on the self node."""
        self._require_ready()
        now = now or _now()
        cutoff = _iso(now - window)
        row = self._conn.execute(
            "SELECT 1 FROM entity_nodes WHERE node_id = ? "
            "AND relationship_summary IS NOT NULL AND last_referenced >= ? LIMIT 1",
            (self_entity_id, cutoff),
        ).fetchone()
        return row is not None

    # =======================================================================
    # The self-narrative producer's selection step (architect ruling 2026-08-26)
    # =======================================================================
    def recurring_self_observation(
        self,
        exclude_similar_to: Sequence[str] = (),
        now: Optional[datetime] = None,
    ) -> Optional[str]:
        """A self-observation she has made MORE THAN ONCE, across sessions — or
        None. This is the selection half of the self-narrative producer; DMN Step 4
        still gates and writes, and this decides nothing about meaning.

        WHAT IT READS. DMN Step 4 already flushes her self-observations to the
        graph as EventNodes described `"[recent-learning:self] <text>"`. Nothing
        ever read them back, which is why `narrative_candidate` was always None and
        the entire Step 4 pipeline had never executed once. This reads them.

        WHY "MORE THAN ONCE". v4 Step 4: single instances do not update the
        narrative. Noticing something once is a Tuesday; noticing it repeatedly is
        character. Recurrence must also cross a SESSION boundary — the same
        observation twice in one sitting is one conversation, the same reason
        `purpose_evidence`'s follow-through half requires a different session.

        HOW RECURRENCE IS DECIDED, and this is the part that needed an architect
        ruling. Two texts "saying the same thing" has no categorical answer —
        similarity is genuinely a matter of degree, so it fails the percentage test,
        which normally means stop. It is permitted here because it sits on the
        MEMORY-PLUMBING side of the protected chain: it decides what counts as a
        PATTERN, never how she feels, and appraisal is untouched. The cutoff is
        therefore MEASURED rather than picked — `_RECURRENCE_SIM_CUTOFF`, set from
        `tools/measure_recurrence_cutoff.py` and re-runnable, so it is a recorded
        observation about the embedding model and not an invented threshold.

        `is_first_of_kind` was tested for this job and REJECTED: every
        recent-learning node is written with the same Q2×Q3 profile
        (`q2="neutral"`, `q3="self"`), so it reports "seen before" for every
        observation after the very first and would write a self-narrative on day
        two from nothing.

        THE PREFIX IS STRIPPED BEFORE COMPARING, and this matters more than it
        looks. Every one of these nodes begins with the literal
        `"[recent-learning:self] "`, and the STORED embedding covers the whole
        description — so comparing stored vectors would measure a shared 22-character
        prefix as well as the content, inflating similarity between UNRELATED
        observations and manufacturing false recurrences. So the stripped text is
        embedded fresh here. Cost: one embed per candidate per idle pass, which is
        a small number on an infrequent path, and correct rather than subtly wrong.

        THE CUTOFF IS `_RECURRENCE_SIM_CUTOFF` (0.40), NOT the contradiction one
        (architect ruling 2026-08-26, Resolution Log item 37). Item 36e reused
        `_REALITY_CONTRADICTION_SIM_CUTOFF` (0.6) and measurement showed it catches
        **0 of 12** genuine reworded recurrences — this method was wired, correct
        and inert. The two constants answer different questions and their pairs land in
        different, non-overlapping bands; see `_RECURRENCE_SIM_CUTOFF` for the full
        measurement and why one value cannot serve both. Contradiction detection is
        untouched and still uses 0.6.

        `exclude_similar_to` is how the caller avoids re-appending something the
        narrative already says — compared with the same cutoff, so a reworded
        restatement is caught too, not just an exact repeat.

        Returns the NEWEST recurring observation's text (its current phrasing),
        with the prefix removed. None when the embedding model is absent, so a
        graph without one degrades to "no candidate" rather than failing.
        """
        self._require_ready()
        if self._embedding_model is None:
            return None

        rows = self._conn.execute(
            "SELECT node_id, session_id, description, timestamp FROM event_nodes "
            "WHERE description LIKE ? ORDER BY timestamp ASC",
            (SELF_LEARNING_PREFIX + "%",),
        ).fetchall()
        if len(rows) < 2:
            return None   # nothing can have recurred yet

        observations = []
        for r in rows:
            text = r["description"][len(SELF_LEARNING_PREFIX):].strip()
            if not text:
                continue
            observations.append(
                (r["session_id"] or "", text, list(self._embedding_model.embed(text)))
            )

        excluded = [
            list(self._embedding_model.embed(t)) for t in exclude_similar_to if t.strip()
        ]

        # Newest first: her current phrasing of a pattern is the one to carry.
        for i in range(len(observations) - 1, -1, -1):
            session, text, vec = observations[i]
            if any(_cosine(vec, ex) >= _RECURRENCE_SIM_CUTOFF
                   for ex in excluded):
                continue                      # the narrative already says this
            for j in range(i):                # strictly earlier observations
                prior_session, _prior_text, prior_vec = observations[j]
                if prior_session == session:
                    continue                  # same sitting is one conversation
                if _cosine(vec, prior_vec) >= _RECURRENCE_SIM_CUTOFF:
                    return text
        return None

    # =======================================================================
    # Task 20 — is_first_of_kind + resolved_edge_exists (structural only)
    # =======================================================================
    def is_first_of_kind(
        self, entity_ref: str, appraisal_q2: str, appraisal_q3: str
    ) -> bool:
        """Whether this event is "first-of-kind" for this entity — Addendum §6:
        "a yes/no check against the graph — does an edge with this appraisal
        profile (Q2 quadrant × Q3 attribution) already exist connecting any
        event to this entity? If no such edge exists, this is a first-of-kind
        event." Binary, no score. Structural only — Appraisal_Chain decides
        poignancy (Req 12.1).

        The (Q2 quadrant × Q3 attribution) profile lives on the connected
        EventNode's appraisal_q2/appraisal_q3; events link to entities via
        entity_refs. So: does any prior event referencing this entity already
        carry this exact (Q2, Q3) profile?
        """
        self._require_ready()
        rows = self._conn.execute(
            "SELECT appraisal_q2, appraisal_q3, entity_refs FROM event_nodes"
        ).fetchall()
        for r in rows:
            refs = json.loads(r["entity_refs"] or "[]")
            if (entity_ref in refs
                    and r["appraisal_q2"] == appraisal_q2
                    and r["appraisal_q3"] == appraisal_q3):
                return False  # a prior event with this profile exists → not first
        return True

    def resolved_edge_exists(
        self,
        entity_ref: str,
        window: timedelta,
        now: Optional[datetime] = None,
    ) -> bool:
        """Whether a "resolved" edge touches an EventNode referencing this
        entity within the window (DMN Invested→Bonded input; Resolution Log
        item 5). Structural only — DMN decides the gate (Req 12.3)."""
        self._require_ready()
        now = now or _now()
        cutoff = _iso(now - window)
        # event nodes referencing this entity
        node_ids = set()
        for r in self._conn.execute(
            "SELECT node_id, entity_refs FROM event_nodes"
        ).fetchall():
            refs = json.loads(r["entity_refs"] or "[]")
            if entity_ref in refs:
                node_ids.add(r["node_id"])
        if not node_ids:
            return False
        rows = self._conn.execute(
            "SELECT from_node, to_node FROM edges WHERE edge_type = ? "
            "AND created >= ?",
            (EdgeType.RESOLVED.value, cutoff),
        ).fetchall()
        for r in rows:
            if r["from_node"] in node_ids or r["to_node"] in node_ids:
                return True
        return False

    # =======================================================================
    # Module 8 additive closure — the two relational_stage-gate predicates the
    # Build Plan's Module 3 Outputs promise DMN ("relational_stage gates"
    # lookups → DMN) but that were not yet exposed publicly. DMN's GraphPort
    # marks them [FLAG]; they are added here ADDITIVELY (new methods only; no
    # existing signature/behavior changed) so DMN wires to the REAL graph.
    # STRUCTURAL / CATEGORICAL booleans ONLY — never a trust score, never a
    # count-as-magnitude (Addendum §2 "No numeric score exists anywhere";
    # percentage test holds). DMN decides the transition; the graph only reports
    # whether the qualifying evidence structurally exists.
    # =======================================================================

    #: Q2/Q3 values that are NOT a "specific behavioral pattern" (an uncertain
    #: appraisal is, by definition, not a settled pattern) — excluded from the
    #: predictability/dependability evidence below.
    _UNCERTAIN_APPRAISAL_VALUES = frozenset({"VALENCE_UNCERTAIN", "CAUSAL_UNCERTAIN"})

    def predictability_evidence(
        self, entity_ref: str, now: Optional[datetime] = None
    ) -> bool:
        """Observing → Engaging gate evidence (Addendum §2 "Predictability: a
        specific behavioral pattern has recurred — appeared more than once
        without contradiction"). Reuses the "appeared more than once" gate
        already locked elsewhere for self-continuity narrative updates.

        STRUCTURAL reading: a "specific behavioral pattern" is a concrete
        (appraisal_q2 × appraisal_q3) profile on an EventNode referencing this
        entity; the pattern "recurred without contradiction" iff the SAME
        specific profile appears on ≥2 such events (a differing/opposite profile
        would be variation, not recurrence — a contradiction is handled
        separately as a REALITY_CONTRADICTION rupture, DMN's regression path).
        Uncertain profiles are excluded (an uncertain appraisal is not a
        "specific" pattern). Categorical yes/no — the count is used ONLY for the
        ">1" gate, never as a magnitude (percentage test holds). `now` is
        accepted for interface symmetry with the other gate lookups; this gate
        is recurrence-structural, not windowed.
        """
        self._require_ready()
        profile_counts: dict = {}
        for r in self._conn.execute(
            "SELECT appraisal_q2, appraisal_q3, entity_refs FROM event_nodes"
        ).fetchall():
            if entity_ref not in json.loads(r["entity_refs"] or "[]"):
                continue
            if (r["appraisal_q2"] in self._UNCERTAIN_APPRAISAL_VALUES
                    or r["appraisal_q3"] in self._UNCERTAIN_APPRAISAL_VALUES):
                continue
            key = (r["appraisal_q2"], r["appraisal_q3"])
            profile_counts[key] = profile_counts.get(key, 0) + 1
        # "appeared more than once" — a single specific profile recurring.
        return any(count >= 2 for count in profile_counts.values())

    def dependability_evidence(
        self, entity_ref: str, now: Optional[datetime] = None
    ) -> bool:
        """Engaging → Invested gate evidence (Addendum §2 "Dependability: the
        pattern generalizes across more than one distinct kind of situation, not
        just repetition of the same one. Categorical yes/no check, no
        counting").

        STRUCTURAL reading: a consistent (appraisal_q2 × appraisal_q3) profile
        for this entity "generalizes across more than one distinct kind of
        situation" iff the SAME specific profile appears in ≥2 DISTINCT sessions
        (`session_id`) — distinct session = distinct situation/context. This is
        exactly what distinguishes it from predictability (which needs only
        recurrence, possibly within one situation): dependability needs the
        pattern to hold ACROSS situations. `session_id` as the "distinct kind of
        situation" is a structural proxy; a finer definition (distinct
        co-referenced entities / distinct topics) is a build-time refinement,
        FLAGGED, not invented. Categorical yes/no — the ≥2 test gates, it is not
        a magnitude.
        """
        self._require_ready()
        profile_sessions: dict = {}  # (q2, q3) -> set(session_id)
        for r in self._conn.execute(
            "SELECT appraisal_q2, appraisal_q3, session_id, entity_refs "
            "FROM event_nodes"
        ).fetchall():
            if entity_ref not in json.loads(r["entity_refs"] or "[]"):
                continue
            if (r["appraisal_q2"] in self._UNCERTAIN_APPRAISAL_VALUES
                    or r["appraisal_q3"] in self._UNCERTAIN_APPRAISAL_VALUES):
                continue
            key = (r["appraisal_q2"], r["appraisal_q3"])
            profile_sessions.setdefault(key, set()).add(r["session_id"])
        return any(len(sessions) >= 2 for sessions in profile_sessions.values())

    # =======================================================================
    # Module 8 additive closure — highest-salience UNCONNECTED candidate
    # selection (Build Plan Module 3 Outputs: "highest-salience unconnected
    # nodes ... to DMN"). SUBSTRATE selection only (salience is sanctioned
    # substrate) — it forms NO edge, writes nothing, and decides NO meaning;
    # DMN's Step 2 owns the categorical connection/aha decision. Returns the
    # structural facts DMN's ConnectionCandidate is built from (the Daemon maps
    # each record 1:1 to a ConnectionCandidate — pure packaging, no computation).
    # =======================================================================
    def highest_salience_unconnected_candidates(
        self, limit: int = 10, now: Optional[datetime] = None
    ) -> List[dict]:
        """Return candidate PAIRS of the highest-salience EventNodes that are
        NOT already connected by an edge, each with the structural/categorical
        facts DMN's Step 2 decides from. Never forms an edge, never writes.

        Selection substrate:
          * "high-salience" cutoff defaults to the in-spec HIGH poignancy
            base_salience floor (0.55, Resolution Log item 9) rather than an
            invented number; the exact cutoff is a build-time tuning knob
            (DMN's ConnectionCandidate marks it "TODO build-time, Module 3").
          * `limit` caps how many top-salience nodes are paired (build-time
            tuning placeholder) — pairs are O(limit²).

        Per-pair structural facts (all booleans — no score):
          * already_connected — False by construction (connected pairs are
            filtered out; the field is kept for the DMN contract).
          * shares_context   — the two events share ≥1 entity_ref OR the same
            session_id (v4 Step 2 "shared entity refs / temporal proximity /
            appraisal similarity"; structural subset).
          * both_high_salience — True by construction (both cleared the cutoff).
          * reveals_new_pattern — FLAGGED structural proxy for v4's "edge has
            high explanatory power": the pair shares an entity ACROSS DIFFERENT
            sessions (a link spanning contexts that neither node held alone).
            "Explanatory power" has no spec formalization, so this is a
            conservative structural stand-in, TODO(build-time) — never an
            invented score. DMN still makes the aha decision from it.
        """
        self._require_ready()
        high_cutoff = POIGNANCY_SALIENCE_FLOOR[PoignancyCategory.HIGH]  # 0.55, in-spec
        rows = self._conn.execute(
            "SELECT node_id, salience, session_id, entity_refs FROM event_nodes "
            "WHERE salience >= ? ORDER BY salience DESC, node_id ASC LIMIT ?",
            (high_cutoff, int(limit)),
        ).fetchall()
        nodes = [
            (r["node_id"], r["session_id"], set(json.loads(r["entity_refs"] or "[]")))
            for r in rows
        ]
        candidates: List[dict] = []
        for i in range(len(nodes)):
            a_id, a_sess, a_ents = nodes[i]
            for j in range(i + 1, len(nodes)):
                b_id, b_sess, b_ents = nodes[j]
                if self._edge_exists_between(a_id, b_id):
                    continue  # "unconnected" — connected pairs are not candidates
                shared_entities = a_ents & b_ents
                candidates.append({
                    "node_a_ref": a_id,
                    "node_b_ref": b_id,
                    "already_connected": False,
                    "shares_context": bool(shared_entities) or (a_sess == b_sess),
                    "both_high_salience": True,
                    "reveals_new_pattern": bool(shared_entities) and (a_sess != b_sess),
                })
        return candidates

    def _edge_exists_between(self, node_a: str, node_b: str) -> bool:
        """Structural: does any edge (either direction) already connect these
        two nodes? Used only by the unconnected-candidate selection above."""
        r = self._conn.execute(
            "SELECT 1 FROM edges WHERE (from_node = ? AND to_node = ?) "
            "OR (from_node = ? AND to_node = ?) LIMIT 1",
            (node_a, node_b, node_b, node_a),
        ).fetchone()
        return r is not None

    # =======================================================================
    # Task 21 — reality_contradiction_check (structural only — Req 12.4)
    # =======================================================================
    def reality_contradiction_check(
        self,
        entity_ref: str,
        candidate_text: str,
        window: timedelta = _REALITY_CONTRADICTION_WINDOW,
        now: Optional[datetime] = None,
    ) -> bool:
        """Compare candidate_text against same-entity EventNode descriptions in
        the window, using the injected embedding model + basic negation
        detection (Addendum §1). Returns a structural boolean ONLY — does not
        decide what a contradiction MEANS for trust/PAD (Req 12.4).

        The similarity cutoff and window are build-time tuning placeholders
        (Addendum "Open — build-time tuning constants").
        """
        self._require_ready()
        now = now or _now()
        if self._embedding_model is None:
            return False
        cutoff = _iso(now - window)
        cand_vec = list(self._embedding_model.embed(candidate_text))
        cand_neg = self._has_negation(candidate_text)
        rows = self._conn.execute(
            "SELECT node_id, description FROM event_nodes WHERE timestamp >= ?",
            (cutoff,),
        ).fetchall()
        for r in rows:
            refs_row = self._conn.execute(
                "SELECT entity_refs FROM event_nodes WHERE node_id = ?",
                (r["node_id"],),
            ).fetchone()
            refs = json.loads(refs_row["entity_refs"] or "[]")
            if entity_ref not in refs:
                continue
            emb = self._get_embedding(r["node_id"])
            if emb is None:
                continue
            sim = _cosine(cand_vec, emb)
            # High topical similarity + differing negation polarity → direct
            # contradiction (Addendum §1: embedding + basic negation detection).
            if sim >= _REALITY_CONTRADICTION_SIM_CUTOFF and (
                cand_neg != self._has_negation(r["description"])
            ):
                return True
        return False

    @staticmethod
    def _has_negation(text: str) -> bool:
        toks = text.lower().replace("'", "'").split()
        # also catch contracted n't
        joined = text.lower()
        if any(t.strip(".,!?;:") in _NEGATION_TOKENS for t in toks):
            return True
        return "n't" in joined

    # =======================================================================
    # Row <-> dataclass mapping and inserts
    # =======================================================================
    def _insert_event_node(self, n: EventNode) -> None:
        self._conn.execute(
            "INSERT INTO event_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (n.node_id, n.timestamp, n.session_id, n.description,
             n.context_excerpt_hash, n.appraisal_q1, n.appraisal_q2,
             n.appraisal_q3, n.appraisal_q4_notes, int(n.is_partial_appraisal),
             n.uncertainty_node_ref, n.pad_delta_p, n.pad_delta_a, n.pad_delta_d,
             n.poignancy_category.value, n.base_salience, n.salience,
             n.precision.value, n.perspective.value,
             json.dumps(n.entity_refs), n.access_count, n.last_accessed),
        )
        self._conn.commit()

    def _load_event_node(self, node_id: str) -> Optional[EventNode]:
        r = self._conn.execute(
            "SELECT * FROM event_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        return self._row_to_event_node(r) if r is not None else None

    @staticmethod
    def _row_to_event_node(r: sqlite3.Row) -> EventNode:
        return EventNode(
            node_id=r["node_id"], timestamp=r["timestamp"],
            session_id=r["session_id"], description=r["description"],
            context_excerpt_hash=r["context_excerpt_hash"],
            appraisal_q1=r["appraisal_q1"], appraisal_q2=r["appraisal_q2"],
            appraisal_q3=r["appraisal_q3"], appraisal_q4_notes=r["appraisal_q4_notes"],
            is_partial_appraisal=bool(r["is_partial_appraisal"]),
            uncertainty_node_ref=r["uncertainty_node_ref"],
            pad_delta_p=r["pad_delta_p"], pad_delta_a=r["pad_delta_a"],
            pad_delta_d=r["pad_delta_d"],
            poignancy_category=PoignancyCategory(r["poignancy_category"]),
            base_salience=r["base_salience"], salience=r["salience"],
            precision=Precision(r["precision"]),
            perspective=Perspective(r["perspective"]),
            entity_refs=json.loads(r["entity_refs"] or "[]"),
            access_count=r["access_count"], last_accessed=r["last_accessed"],
        )

    def _insert_entity_node(self, n: EntityNode) -> None:
        self._conn.execute(
            "INSERT INTO entity_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (n.node_id, n.entity_type, n.name, json.dumps(n.aliases),
             n.first_encountered, n.last_referenced, n.reference_count,
             n.relationship_summary,
             n.relational_stage.value if n.relational_stage else None,
             n.net_valence, n.net_arousal, n.net_dominance, n.overall_salience),
        )
        self._conn.commit()

    def _insert_emotion_node(self, n: EmotionNode) -> None:
        self._conn.execute(
            "INSERT INTO emotion_nodes VALUES (?,?,?,?,?,?,?,?,?)",
            (n.node_id, n.emotion_label, n.pad_p, n.pad_a, n.pad_d,
             n.trigger_event_ref, n.poignancy_category.value,
             n.precision.value, n.timestamp),
        )
        self._conn.commit()

    def _insert_uncertainty_node(self, n: UncertaintyNode) -> None:
        self._conn.execute(
            "INSERT INTO uncertainty_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (n.node_id, n.uncertainty_type.value, n.trigger_event_ref,
             n.entity_ref, n.status.value, n.created, n.resolved,
             n.resolution_path, n.catch_up_delta_p, n.catch_up_delta_a,
             n.catch_up_delta_d, n.catch_up_magnitude_factor,
             n.interaction_count, int(n.is_protected)),
        )
        self._conn.commit()

    def _insert_edge(self, e: Edge) -> None:
        self._conn.execute(
            "INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.edge_id, e.from_node, e.to_node, e.edge_type.value, e.valence,
             e.arousal, e.dominance, e.base_salience, e.salience,
             e.firing_count, e.perspective.value, e.created, e.last_activated,
             int(e.is_tension_pair), e.tension_partner_edge, int(e.is_aha_edge)),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_edge(r: sqlite3.Row) -> Edge:
        return Edge(
            edge_id=r["edge_id"], from_node=r["from_node"], to_node=r["to_node"],
            edge_type=EdgeType(r["edge_type"]), valence=r["valence"],
            arousal=r["arousal"], dominance=r["dominance"],
            base_salience=r["base_salience"], salience=r["salience"],
            created=r["created"], perspective=Perspective(r["perspective"]),
            firing_count=r["firing_count"], last_activated=r["last_activated"],
            is_tension_pair=bool(r["is_tension_pair"]),
            tension_partner_edge=r["tension_partner_edge"],
            is_aha_edge=bool(r["is_aha_edge"]),
        )

    # -- detached-copy reads (Req 13 spirit: consumers can't mutate live state)
    def get_event_node(self, node_id: str) -> Optional[EventNode]:
        self._require_ready()
        return self._load_event_node(node_id)

    def get_entity_node(self, node_id: str) -> Optional[EntityNode]:
        self._require_ready()
        r = self._conn.execute(
            "SELECT * FROM entity_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if r is None:
            return None
        return EntityNode(
            node_id=r["node_id"], entity_type=r["entity_type"], name=r["name"],
            aliases=json.loads(r["aliases"] or "[]"),
            first_encountered=r["first_encountered"],
            last_referenced=r["last_referenced"],
            reference_count=r["reference_count"],
            relationship_summary=r["relationship_summary"],
            relational_stage=(RelationalStage(r["relational_stage"])
                              if r["relational_stage"] else None),
            net_valence=r["net_valence"], net_arousal=r["net_arousal"],
            net_dominance=r["net_dominance"], overall_salience=r["overall_salience"],
        )

    def get_uncertainty_node(self, node_id: str) -> Optional[UncertaintyNode]:
        self._require_ready()
        r = self._conn.execute(
            "SELECT * FROM uncertainty_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if r is None:
            return None
        return UncertaintyNode(
            node_id=r["node_id"],
            uncertainty_type=UncertaintyType(r["uncertainty_type"]),
            trigger_event_ref=r["trigger_event_ref"], entity_ref=r["entity_ref"],
            status=UncertaintyStatus(r["status"]), created=r["created"],
            interaction_count=r["interaction_count"],
            is_protected=bool(r["is_protected"]), resolved=r["resolved"],
            resolution_path=r["resolution_path"],
            catch_up_delta_p=r["catch_up_delta_p"],
            catch_up_delta_a=r["catch_up_delta_a"],
            catch_up_delta_d=r["catch_up_delta_d"],
            catch_up_magnitude_factor=r["catch_up_magnitude_factor"],
        )

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        self._require_ready()
        r = self._conn.execute(
            "SELECT * FROM edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
        return self._row_to_edge(r) if r is not None else None

    def get_emotion_node(self, node_id: str) -> Optional[EmotionNode]:
        self._require_ready()
        r = self._conn.execute(
            "SELECT * FROM emotion_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if r is None:
            return None
        return EmotionNode(
            node_id=r["node_id"], emotion_label=r["emotion_label"],
            pad_p=r["pad_p"], pad_a=r["pad_a"], pad_d=r["pad_d"],
            trigger_event_ref=r["trigger_event_ref"],
            timestamp=r["timestamp"], precision=Precision(r["precision"]),
            poignancy_category=PoignancyCategory(r["poignancy_category"]),
        )

    def active_uncertainty_count(self) -> int:
        self._require_ready()
        return len(self._active_uncertainty_rows())

    # Convenience for entity creation (used by callers/tests; entity creation
    # itself is not a flagged behavior).
    def write_entity_node(
        self,
        *,
        entity_type: str,
        name: str,
        relational_stage: Optional[RelationalStage] = None,
        aliases: Optional[List[str]] = None,
        now: Optional[datetime] = None,
    ) -> str:
        self._require_ready()
        now = now or _now()
        node = EntityNode(
            node_id=str(uuid.uuid4()), entity_type=entity_type, name=name,
            first_encountered=_iso(now), last_referenced=_iso(now),
            reference_count=0, relational_stage=relational_stage,
            aliases=list(aliases or []),
        )
        self._insert_entity_node(node)
        return node.node_id

    def close(self) -> None:
        self._conn.close()
