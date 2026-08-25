# ARIA locked spec — llm-interface
Consolidated from .kiro/specs/llm-interface/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.

> **AMENDMENT 2026-08-24 — the public surface is `{generate, last_route}`.**
> Resolution Log **item 26**. `serving_from_local` is GONE. Statements below that
> name it, or give the surface as `{generate, serving_from_local}`, predate the
> ruling and are left in place so the change is legible; where they disagree with
> this, this wins.
>
> It returned `self._local.is_loaded` under a docstring reading "cloud is
> currently down". Those were one fact under v4's cloud-primary lifecycle and
> stopped being one under Track A, which pins the local voice resident from
> startup and makes it the default — so it read True during entirely healthy
> operation. `last_route` records where the last candidate actually came from and
> consults no residency: `no_turn_yet`, `cloud_chosen`,
> `cloud_unhealthy_fallback`, `local_chosen`, `no_cloud_adapter`.
>
> One behaviour is a rule rather than a rename: an unconfigured cloud tier raises
> `LLMTransportError` identically to a real outage, so `no_cloud_adapter`
> OUTRANKS `cloud_unhealthy_fallback` — a local-first bring-up is the intended
> state, not degradation. The seam is a duck-typed `is_configured` marker read
> with `getattr(..., True)`, so `daemon/` still imports nothing from `adapters/`.
>
> The module gains ONE attribute, `_last_route`: a record, never an input. The
> structural guarantee this spec rests on is untouched — the constructor still
> takes transports only, so no graph, PAD, needs, appraisal or state handle can
> reach a prompt through it.
