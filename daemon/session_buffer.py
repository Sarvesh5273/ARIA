"""ARIA — Session Buffer (daemon/session_buffer.py).

Ephemeral working memory for the current conversation session.
NOT autobiographical memory — the graph is the only persistent self.
This is a scratchpad for conversational continuity only.

Three tiers:
  RECENT:   Full text of last N turns (~8K tokens)
  MEDIUM:   Compressed summaries of older chunks (~6K tokens)  
  OLD:      One-line topic tags of oldest material (~4K tokens)

Total budget: 18K tokens (8K+6K+4K). A SPEED cap on Mac M4, not a window cap —
so a local model's context size is not a reason to move it. All four budgets are
placeholders (see .kiro/specs/session-buffer/design.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


# Token budget constants
_RECENT_TOKEN_BUDGET = 8000
_MEDIUM_TOKEN_BUDGET = 6000
_OLD_TOKEN_BUDGET = 4000
_TOTAL_TOKEN_BUDGET = _RECENT_TOKEN_BUDGET + _MEDIUM_TOKEN_BUDGET + _OLD_TOKEN_BUDGET

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
        """Wipe all tiers. Called on 'rest'."""
        self._recent.clear()
        self._medium.clear()
        self._old.clear()

    def set_focus_mode(self, focused: bool) -> None:
        """True = drop MEDIUM and OLD from prompt (not from storage)."""
        self._focus_mode = focused

    def is_focused(self) -> bool:
        return self._focus_mode

    def fullness_state(self) -> str:
        """Cognitive load state: 'light' | 'settled' | 'heavy' | 'critical'.
        
        Based on which tiers are active, not raw tokens:
        - light: only RECENT has items
        - settled: MEDIUM has items (some conversation history compressed)
        - heavy: OLD has items (deep history archived)
        - critical: total budget exceeded (should not happen in normal operation)
        """
        total = self._total_token_estimate()
        if total >= _TOTAL_TOKEN_BUDGET:
            return "critical"
        if self._old:
            return "heavy"
        if self._medium:
            return "settled"
        return "light"

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