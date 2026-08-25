"""ARIA — Session Buffer (daemon/session_buffer.py).

Ephemeral working memory for the current conversation session.
NOT autobiographical memory — the graph is the only persistent self.
This is a scratchpad for conversational continuity only.

Three tiers:
  RECENT:   Full text of last N turns (~12K tokens)
  MEDIUM:   Compressed summaries of older chunks (~8K tokens)
  OLD:      One-line topic tags of oldest material (~4K tokens)

Total budget: 24K total (12K+8K+4K). A SPEED cap on Mac M4, not a window cap —
`qwen3.5:9b-mlx` reports a 262144-token window, so the window has never been the
binding constraint and is still not the reason for this number. All four budgets
are placeholders (see .kiro/specs/session-buffer/design.md).

TOKEN COUNTING — ESTIMATE, THEN THE REAL NUMBER WHEN A PROVIDER REPORTS ONE
--------------------------------------------------------------------------
`_*_token_estimate()` is `chars // 4`. That is a guess, and it is the only thing
available BEFORE a turn is served: nothing in `daemon/` may import a tokenizer
(the soul layer has zero external dependencies, and adding one to count a
scratchpad would be a poor trade).

But after a turn IS served, the provider has already counted, exactly, for
billing or for its own bookkeeping — Ollama returns `prompt_eval_count` /
`eval_count` / `eval_duration`, and an OpenAI-compatible endpoint returns
`usage.prompt_tokens` / `usage.completion_tokens`. `record_actual_tokens()` is
where that measured number arrives, via the Daemon reading the transport's
`last_turn_metadata()` side-channel. No tokenizer, no dependency, no second
estimate — just the count the thing that did the work already made.

The measured number is for the WHOLE prompt (five fields + this buffer's context
+ the user's message), not for this buffer's content alone, so it reads slightly
higher than `_total_token_estimate()` on the same turn. That is the intended
comparison: the budget exists to bound what the model is actually asked to hold.

WHAT IS SUBSTRATE HERE AND WHAT IS NOT
-------------------------------------
Token counts, the budgets, the band fractions and the generation-speed floor are
all SUBSTRATE — attention/memory plumbing. `fullness_state()` collapses them into
a CATEGORICAL band, and only the band leaves this module: the Daemon hands it to
`AppraisalChain.submit_cognitive_load()`, which is where meaning is made and
where the PAD byproduct comes from. No number reaches PAD, and this module never
touches PAD itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


# Token budget constants. Build-time tuning values; no source document states
# them (see .kiro/specs/session-buffer/design.md).
_RECENT_TOKEN_BUDGET = 12000
_MEDIUM_TOKEN_BUDGET = 8000
_OLD_TOKEN_BUDGET = 4000
_TOTAL_TOKEN_BUDGET = _RECENT_TOKEN_BUDGET + _MEDIUM_TOKEN_BUDGET + _OLD_TOKEN_BUDGET

#: Band boundaries as a FRACTION of `_TOTAL_TOKEN_BUDGET`, not as absolute token
#: counts — so re-tuning a budget above moves the bands with it instead of
#: silently leaving them where the old budget put them. Build-time tuning, same
#: category as the budgets themselves.
_SETTLED_FRACTION = 0.25              # TODO(build-time): band boundary
_HEAVY_FRACTION = 0.50                # TODO(build-time): band boundary
_CRITICAL_FRACTION = 0.75             # TODO(build-time): band boundary

#: Generation speed below which the band is bumped one step. Context pressure
#: shows up as slowdown before it shows up as a token count that has crossed a
#: line, because prompt-eval cost grows with the prompt while the band boundary
#: does not move — so a turn can be well inside a band and already be labouring.
#:
#: 10.0 tok/s is a floor set below the qwen3.5:9b-mlx baseline the architect
#: reports (~13-14 tok/s). HONEST CAVEAT, same one Resolution Log item 24 records
#: about that baseline: it is architect-supplied and has not been reproduced by a
#: harness run in this project. `tools/compare_local_models.py` is what would.
_SLOW_GENERATION_TOK_S = 10.0         # TODO(build-time): speed floor

#: Ordered light → critical. `fullness_state()`'s bump walks this and cannot run
#: off the end, so "critical, but slow" stays critical rather than inventing a
#: fifth band.
_FULLNESS_LADDER = ("light", "settled", "heavy", "critical")

#: Field-5-shaped behavioural instructions for the two loaded bands. See
#: `express_pressure()` — including why this is NOT yet wired to the LLM.
_HEAVY_PRESSURE_INSTRUCTION = "You have a lot on your mind right now. Be brief."
_CRITICAL_PRESSURE_INSTRUCTION = (
    "This is a lot to hold. Keep your response very short."
)

# Fuzzy meta-command triggers
_REST_TRIGGERS = ("rest", "take a break", "clear your head", "reset your memory")
_FOCUS_TRIGGERS = ("focus", "be here now", "just us", "only now")
_UNFOCUS_TRIGGERS = ("unfocus", "full memory", "remember everything", "the whole picture")


@dataclass
class _Turn:
    user_text: str
    aria_text: str


@dataclass
class _Summary:
    text: str
    turn_count: int

def _phrase_in_text(text: str, phrase: str) -> bool:
    """Check if phrase appears as a complete phrase in text (not as a substring
    of a larger word). Uses word-boundary regex: 'rest' matches 'I need to rest'
    but NOT 'restaurant'."""
    escaped = re.escape(phrase)
    pattern = r'(?:^|\W)' + escaped + r'(?:$|\W)'
    return re.search(pattern, text, re.IGNORECASE) is not None


class SessionBuffer:
    """Ephemeral three-tier conversation buffer."""

    def __init__(self) -> None:
        self._recent: List[_Turn] = []
        self._medium: List[_Summary] = []
        self._old: List[str] = []
        self._focus_mode = False

        # --- measured, not estimated. Set by record_actual_tokens() from the
        # provider's own count for the LAST served turn; None until a turn has
        # been served by a transport that reports one. ----------------------
        self._actual_prompt_tokens: Optional[int] = None
        self._actual_gen_tokens: Optional[int] = None
        self._last_gen_speed_tok_s: Optional[float] = None

        # One-shot latch: heaviness is worth SAYING once, not every turn.
        self._heavy_pressure_expressed = False

    # -- public API ---------------------------------------------------------

    def append_turn(self, user_text: str, aria_text: str) -> None:
        """Add one turn to RECENT. Promote tiers if budget exceeded."""
        self._recent.append(_Turn(user_text=user_text, aria_text=aria_text))
        self._maybe_promote_recent_to_medium()
        self._maybe_promote_medium_to_old()

    def get_context(self) -> str:
        """Render the session context for the LLM prompt.
        In focus_mode, only RECENT is returned."""
        parts: List[str] = []
        
        if self._old and not self._focus_mode:
            parts.append("[Earlier today]")
            for tag in self._old:
                parts.append(f"- {tag}")
        
        if self._medium and not self._focus_mode:
            parts.append("\n[Earlier in this conversation]")
            for summary in self._medium:
                parts.append(summary.text)
        
        if self._recent:
            parts.append("\n[Recent]")
            for turn in self._recent:
                parts.append(f"User: {turn.user_text}")
                parts.append(f"Aria: {turn.aria_text}")
        
        return "\n".join(parts)

    def clear(self) -> None:
        """Wipe all tiers. Called on 'rest'.

        The measured token record goes too. It described a prompt assembled from
        content that no longer exists, so keeping it would have `fullness_state()`
        report "critical" for an empty buffer until the next turn overwrote it —
        the buffer answering about a conversation it has just forgotten.

        The heavy-pressure LATCH deliberately does NOT reset here. It is scoped to
        the session (this instance), and "rest" does not start a new session. That
        is the literal reading of "first heavy this session"; the alternative
        (re-arm on rest, so a second arrival at heaviness may be mentioned again)
        is a live choice for the architect, not one this module should make.
        """
        self._recent.clear()
        self._medium.clear()
        self._old.clear()
        self._actual_prompt_tokens = None
        self._actual_gen_tokens = None
        self._last_gen_speed_tok_s = None

    def set_focus_mode(self, focused: bool) -> None:
        """True = drop MEDIUM and OLD from prompt (not from storage)."""
        self._focus_mode = focused

    def is_focused(self) -> bool:
        return self._focus_mode

    def record_actual_tokens(
        self,
        *,
        prompt_tokens: Optional[int] = None,
        gen_tokens: Optional[int] = None,
        gen_duration_ms: Optional[int] = None,
    ) -> None:
        """Record the provider's OWN count for the turn just served.

        Called by the Daemon after `SoulFilter.respond()`, from whatever the
        serving transport's `last_turn_metadata()` reported. Every field is
        optional because a provider may report some and not others — an
        OpenAI-compatible endpoint returns token counts but no generation
        duration, so speed stays unknown there and only the count is used.

        ASSIGNS WHAT IT IS GIVEN, INCLUDING None. A turn that reported nothing
        drops `fullness_state()` back to the `chars // 4` estimate rather than
        answering from the PREVIOUS turn's number, which described a different
        prompt. Stale precision is worse than admitted estimation.

        Speed is `gen_tokens / seconds` — arithmetic on two reported quantities,
        not a coefficient. Unknown (None) when either is missing or the duration
        is non-positive, because dividing by it would manufacture a number.
        """
        self._actual_prompt_tokens = prompt_tokens
        self._actual_gen_tokens = gen_tokens
        if gen_tokens is not None and gen_duration_ms is not None and gen_duration_ms > 0:
            self._last_gen_speed_tok_s = gen_tokens / (gen_duration_ms / 1000.0)
        else:
            self._last_gen_speed_tok_s = None

    def fullness_state(self) -> str:
        """Cognitive load state: 'light' | 'settled' | 'heavy' | 'critical'.

        How much of `_TOTAL_TOKEN_BUDGET` the last prompt actually occupied,
        collapsed into a band:

            light     < 25% of budget
            settled    25-50%
            heavy      50-75%
            critical  >= 75%

        MEASURED FIRST, ESTIMATED ONLY AS A FALLBACK. When a transport has
        reported `prompt_eval_count` (or `usage.prompt_tokens`) for the last
        turn, that is the real total. With no report — no router wired, a
        provider that omits usage, or the first turn of a session — it falls back
        to `_total_token_estimate()`'s `chars // 4`.

        Tier occupancy is NO LONGER the signal. It was a proxy for size, and a
        poor one: promotion RECENT→MEDIUM compresses, so acquiring a MEDIUM tier
        can leave the prompt smaller than it was a turn earlier while the old
        logic reported it as fuller. Size is now read directly.

        SPEED DEGRADATION IS CONTEXT PRESSURE, so a slow last generation
        (< `_SLOW_GENERATION_TOK_S`) bumps the band one step. Two reasons it is
        not a separate signal: the thing being reported is how loaded she is, and
        a prompt that has begun to cost visibly more per token is loaded whatever
        side of a boundary its count fell on. The bump saturates at "critical" —
        it does not invent a fifth band.
        """
        total = self._actual_prompt_tokens
        if total is None:
            total = self._total_token_estimate()
        fraction = total / _TOTAL_TOKEN_BUDGET

        if fraction >= _CRITICAL_FRACTION:
            band = "critical"
        elif fraction >= _HEAVY_FRACTION:
            band = "heavy"
        elif fraction >= _SETTLED_FRACTION:
            band = "settled"
        else:
            band = "light"

        speed = self._last_gen_speed_tok_s
        if speed is not None and speed < _SLOW_GENERATION_TOK_S:
            band = _FULLNESS_LADDER[
                min(_FULLNESS_LADDER.index(band) + 1, len(_FULLNESS_LADDER) - 1)
            ]
        return band

    def express_pressure(self) -> Optional[str]:
        """The loaded bands, as an INSTRUCTION she can act on — or None.

            heavy     "You have a lot on your mind right now. Be brief."
                      once per session, on first arrival
            critical  "This is a lot to hold. Keep your response very short."
                      every turn it holds

        Returns a Field-5-SHAPED sentence: a specific behavioural instruction for
        this turn, in the same form `SoulFilter._derive_constraints` produces. No
        number, no band label, no tier count — the pressure is expressed as what
        to do about it, which is how the Energy gate already crosses ("the NUMBER
        never crosses — only the instruction").

        Heaviness latches because saying it every turn would be performance
        rather than expression. Criticality does not latch: it is the band where
        the instruction has to keep applying, and it is bounded by being rare.

        *** NOT WIRED TO THE LLM. Nothing calls this yet. *** Two questions have
        to be answered by the architect first, and both are recorded in the
        Resolution Log entry for this change:

        1. WHO PUTS IT IN FIELD 5. Field 5 is assembled inside
           `SoulFilter._derive_constraints`, from the appraisal and `need_states`.
           The Daemon holds no instruction to append to, so wiring this needs
           Soul Filter to accept it — which the change request that added this
           method explicitly forbids ("Do NOT change SoulFilter"). Also Addendum
           §9 caps Field 5 at MAX 3, so a fourth entry either breaks the cap or
           is silently dropped, and which of those it should be is a ruling.
        2. THE FIRST SENTENCE OF EACH STRING IS STATE RENDERED AS A CLAIM.
           `_derive_constraints` faced exactly this shape for Energy and decided
           it the other way: v4's "You are running low. Acknowledge it if it
           comes up naturally." was carried across as the instruction half ONLY,
           because "state never crosses (Addendum §9)". "You have a lot on your
           mind right now" is the same shape as "You are running low". The
           instruction halves — "Be brief.", "Keep your response very short." —
           raise no such question.

        The strings are the architect's wording, kept verbatim rather than
        quietly trimmed to the instruction halves, so the ruling is theirs to
        make on what they actually wrote.
        """
        state = self.fullness_state()
        if state == "critical":
            return _CRITICAL_PRESSURE_INSTRUCTION
        if state == "heavy":
            if self._heavy_pressure_expressed:
                return None
            self._heavy_pressure_expressed = True
            return _HEAVY_PRESSURE_INSTRUCTION
        return None

    def is_meta_command(self, text: str) -> Optional[str]:
        low = text.lower().strip()
        if any(_phrase_in_text(low, t) for t in _REST_TRIGGERS):
            return "rest"
        if any(_phrase_in_text(low, t) for t in _UNFOCUS_TRIGGERS):
            return "unfocus"
        if any(_phrase_in_text(low, t) for t in _FOCUS_TRIGGERS):
            return "focus"
        return None

    # -- internal: tier promotion -------------------------------------------

    def _maybe_promote_recent_to_medium(self) -> None:
        while self._recent and self._recent_token_estimate() > _RECENT_TOKEN_BUDGET:
            chunk_size = min(10, max(1, len(self._recent) // 2))
            chunk = self._recent[:chunk_size]
            self._recent = self._recent[chunk_size:]
            summary = self._summarize_turns(chunk)
            self._medium.append(_Summary(text=summary, turn_count=len(chunk)))
            self._maybe_promote_medium_to_old()

    def _maybe_promote_medium_to_old(self) -> None:
        while self._medium and self._medium_token_estimate() > _MEDIUM_TOKEN_BUDGET:
            oldest = self._medium.pop(0)
            tag = self._compress_summary(oldest)
            self._old.append(tag)

    # -- internal: rule-based summarization ----------------------------------

    def _summarize_turns(self, turns: List[_Turn]) -> str:
        if not turns:
            return ""
        topic = turns[0].user_text[:80]
        if len(topic) == 80:
            topic += "..."
        emotional_words = (
            "frustrated", "excited", "worried", "angry", "happy", "sad",
            "scared", "hopeless", "relieved", "grateful", "anxious", "overwhelmed",
            "proud", "disappointed", "confused", "hurt", "lonely", "loved",
        )
        found = []
        for turn in turns:
            low = (turn.user_text + " " + turn.aria_text).lower()
            for word in emotional_words:
                if word in low and word not in found:
                    found.append(word)
        emotion_str = ""
        if found:
            emotion_str = f" Emotions: {', '.join(found[:3])}."
        return f'"{topic}"{emotion_str} ({len(turns)} turns)'

    def _compress_summary(self, summary: _Summary) -> str:
        text = summary.text
        if '"' in text:
            topic = text.split('"')[1].split('"')[0]
            return topic[:60]
        return text[:60]

    # -- internal: token estimation (~4 chars = 1 token) ---------------------

    def _recent_token_estimate(self) -> int:
        chars = sum(len(t.user_text) + len(t.aria_text) + 20 for t in self._recent)
        return chars // 4

    def _medium_token_estimate(self) -> int:
        chars = sum(len(s.text) + 20 for s in self._medium)
        return chars // 4

    def _old_token_estimate(self) -> int:
        chars = sum(len(t) + 10 for t in self._old)
        return chars // 4

    def _total_token_estimate(self) -> int:
        return (
            self._recent_token_estimate()
            + self._medium_token_estimate()
            + self._old_token_estimate()
        )