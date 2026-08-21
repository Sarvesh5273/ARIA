# ARIA module reference — session-buffer (NOT a locked spec)

Mirror of `.kiro/specs/session-buffer/design.md`. Unlike the other consolidated
`spec_*.md` files in this folder, this module has no architect-authored
requirements or tasks — only the design reference below, derived from code. The
title differs from the others deliberately: calling this a "locked spec" would
claim authority it does not have.

# Design Reference — Module 12: Session Buffer

> ## STATUS: DERIVED FROM CODE. NOT A SOURCE OF SCOPE.
>
> Written from the shipped code on 2026-08-20, not before it. **Read it as
> documentation, not as a contract** — a spec that restates the code cannot
> detect drift from it. Where this file and the code disagree, the CODE is what
> shipped.
>
> Precedence is unchanged and this file is not in it:
> `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
> `ARIA_Soul_Spec_v4.md`. There is deliberately no `requirements.md`; see the
> end of this file.

## Authority — and the honest caveat

**This module appears in NONE of v4, the Addendum, or the original Build Plan.**
It was architect-directed after the thirteen modules were approved. Rule 1 ends
"the architect resolves it", so it is authorised, not invented — and that
authorisation is now recorded in `ARIA_Resolution_Log.md` **item 19**
("Post-approval work — authorisation of record").

**One tension inside it is explicitly NOT resolved.** Addendum §9 says "Five
fields, fixed order, nothing else" and lists *"historical conversation
summaries"* among what never crosses to the LLM. This module's Medium tier passes
exactly that, and its Old tier passes topic tags. The prohibition's wording
targets *past sessions* ("anything Aria remembers about the user from past
sessions") and session context is current-session only, so it may fall outside
its scope — but "nothing else" is unqualified. ResLog item 19 authorises the
module while naming this as still open. Do not treat it as settled.

## Responsibility

Ephemeral three-tier working memory for the CURRENT session only. It is a record
of what was already said in this conversation — **not** memory in the
architectural sense. The graph remains the only memory; nothing here is
persisted, and a restart loses all of it by design.

## Tiers

```
_RECENT_TOKEN_BUDGET = 8000    verbatim recent turns
_MEDIUM_TOKEN_BUDGET = 6000    rule-based summaries
_OLD_TOKEN_BUDGET    = 4000    topic tags only
_TOTAL_TOKEN_BUDGET  = 18000
```

Summarisation is **rule-based**, not generative — no LLM call, so the buffer
cannot editorialise what was said.

All four budgets are build-time tuning values. No source document states them.

## Public API

```
append_turn(user_text, response_text)   record a completed exchange
get_context() -> str                    the assembled three-tier context
fullness_state() -> str                 'settled' | 'light' | 'heavy' | 'critical'
is_meta_command(text)                   'rest' | 'focus' | 'unfocus' | None
set_focus_mode(...) / is_focused()      focus-mode toggle
clear()                                 drop everything
```

## Meta-commands

Fuzzy, word-boundary matched. Trigger lexicons (build-time placeholders, no
source document states them):

```
rest     : rest, take a break, clear your head, reset your memory
focus    : focus, be here now, just us, only now
unfocus  : unfocus, full memory, remember everything, the whole picture
```

Meta-commands are intercepted by the Daemon at `route_inbound_turn` STEP 2,
BEFORE appraisal. They bypass appraisal, Soul Filter, the LLM and the Output
Gate, and write **no EventNode** — a request to manage the buffer is not an
appraisable event. `"rest"` additionally triggers a DMN consolidation pass.

## Cognitive load

`fullness_state()` returns a categorical band. The Daemon feeds `heavy` and
`critical` into `AppraisalChain.submit_cognitive_load()`, which emits a small
second-order PAD delta through the sanctioned appraisal path — this module never
touches PAD itself.

Since 2026-08-20 that entry point has a **second** caller: Energy below the
in-spec 30 gate (ResLog item 19). Both can fire in one turn, so two PAD deltas
can land. That stacking is measured and recorded as open in `PROJECT_STATUS.md`;
collapsing it would need an invented precedence rule.

## Boundary

Holds no PAD, no graph handle, no appraisal handle, no needs handle. It stores
strings and counts. The Daemon reads `get_context()` and passes the result to
`SoulFilter.respond(session_context=...)`, which forwards it opaquely to the LLM
Interface — Soul Filter does not inspect it.

## Tests

`tests/test_session_buffer.py`, 13 tests.

## What a real spec would still need

- The four token budgets and the three trigger lexicons, all placeholders.
- **The §9 tension above** — the one item here that is genuinely architectural
  rather than tuning. It needs an explicit Addendum or Resolution Log amendment
  saying whether current-session summaries are inside or outside "nothing else".
- Whether `fullness_state()`'s four bands are the right granularity, given only
  two of them (`heavy`, `critical`) have a consumer.
