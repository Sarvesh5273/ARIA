# Design Reference — Module 13: BackendRouter

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
Verified: `backend`, `Ollama`, `Groq`, `Azure`, `Kimi` return zero hits across
all four source documents. It was architect-directed after the thirteen modules
were approved; Rule 1 ends "the architect resolves it", so it is authorised, and
that authorisation is recorded in `ARIA_Resolution_Log.md` **item 19**, together
with the Track A wiring and the Daemon distress gate that now gates it.

## Responsibility

Decide WHICH language-model backend transport should serve a turn. It selects; it
never generates. Pure infrastructure — no personality, no meaning.

```
Tier 0  local      Gemma 3 12B via Ollama/MLX   on-device, the DEFAULT VOICE
Tier 1  general    Groq Llama 3.3 70B           fallback only
Tier 2  reasoning  Azure Foundry -> Kimi        proposed, never taken silently
```

```
VALID_TIERS = ('tier_0', 'tier_1', 'tier_2')
TIER_TO_KEY = {'tier_0': 'gemma', 'tier_1': 'groq', 'tier_2': 'azure'}
```

Health dicts are always keyed `gemma` / `groq` / `azure`; overrides are always a
`VALID_TIERS` string or `None`.

## Structural boundary

Touches NO PAD, graph, needs, appraisal, poignancy or relational state, and
holds no handle to any of them — the absent handle is the guarantee. Proven two
ways in tests: an AST import scan (the only daemon import is
`daemon.llm_interface`, for the transport contracts) and a `vars()` check that
instance state is exactly the three transports, the clock, the override and the
health cache.

No concrete provider is imported. All three transports are **injected**.

## Public API

```
classify(user_text) -> 'propose_tier_2' | 'tier_1_ok'
select(user_text, *, allow_tier_2_proposal=True) -> (transport|None, propose)
set_override(tier) / get_override() / clear_override()
check_health() -> {'gemma': bool, 'groq': bool, 'azure': bool}
ensure_local_loaded() -> bool
```

## Selection order

1. **Override wins unconditionally** — deliberately NOT health-gated. A user who
   says "use cloud" gets the cloud transport even if the probe says it is down;
   the failure surfaces at `generate()` time and is the Daemon's to handle.
2. **Tier-2 proposal** — only if the classifier matches AND Azure is explicitly
   healthy AND `allow_tier_2_proposal`. Returns `(None, True)`; the Daemon owns
   the pause-and-ask UX.
3. **Gemma** — if explicitly healthy and resident. This is the DEFAULT VOICE for
   all conversation, tried FIRST, not as a last resort.
4. **Groq** — only if explicitly healthy.
5. `(None, False)` — the degradation path.

`allow_tier_2_proposal=False` (added 2026-08-20) lets a caller say "this turn must
not be deferred" while the ROUTER still chooses. It exists for the Daemon's
distress gate: a distressed turn must reach the pipeline as presence, not be
answered with a routing question. It is a parameter rather than a
"give-me-the-local-transport" accessor precisely so a caller cannot bypass the
order above or duplicate the "is gemma usable" test that belongs here.

## Health probing — three states, not two

`_probe_one` returns `Optional[bool]`:

```
transport is None                   -> False
exposes is_healthy()                -> bool(is_healthy())
local tier, no probe                -> bool(is_loaded)   (residency IS an answer)
anything else, no probe             -> None = UNKNOWN
```

`check_health()` reports the HEALTHY SET: only an explicit `True` joins it, so
UNKNOWN is folded out. **No probe means no answer, and "no answer" is not "yes".**

This closed FLAG B (2026-08-20). Previously an unprobeable transport was assumed
healthy, which meant a keyword match always proposed escalation even with Azure
down, Groq was selected whenever Gemma was unavailable even if Groq was dead, and
the all-down degradation path was unreachable. Cached for
`HEALTH_CACHE_TTL_SECONDS`; returns a copy so a caller cannot corrupt the cache.

`HealthProbe` is an OPTIONAL Protocol checked structurally via `isinstance`, never
assumed. It is not part of `ModelTransport`, whose only guaranteed method is
`generate()` — and calling `generate()` to probe health would spend a real API
token every turn, which is why a transport may volunteer a cheap answer instead.

## Tier-2 classifier

Word-boundary regex over `TIER_2_KEYWORDS` (49 entries). **No neural model** —
that is the locked decision; the lexicon membership is build-time tuning.

Two things a reader will trip over:

- Strict `\b` means inflections are NOT matched implicitly. `"complexity"` does
  not match `"complex"`. Common inflections are therefore EXPLICIT entries.
- Multi-word entries are phrases. **`"explain why"` is an entry; bare
  `"explain"` is not** — so "can you explain what's wrong" does not classify as
  tier-2. This is easy to get wrong when writing tests.

`medical` / `legal` were REMOVED as too broad for a personal companion: they fired
on "my doctor said..." and "my legal paperwork...".

## Tests

`tests/test_backend_router.py`, 25 tests. Assert categorical outcomes and
properties, never the placeholder magnitudes or exact lexicon membership.

## Open

- **No real adapter implements `HealthProbe`.** In production both cloud
  transports would report UNKNOWN and neither would be selectable. That is the
  safe direction to fail, but cloud routing is inert until adapters exist. The
  simplest non-inventing fix: back `is_healthy()` with the adapter's own last
  `LLMTransportError` state.
- `TIER_2_KEYWORDS` membership and `HEALTH_CACHE_TTL_SECONDS`, both placeholders.

## What a real spec would still need

- Whether the tier vocabulary and fallback order are locked or provisional.
- Whether "override is never health-gated" is the intended permanent behaviour,
  or a convenience that should change once real adapters can report health.
- The two placeholders above.
