# Design Reference — Module 11: State Manager

> ## STATUS: DERIVED FROM CODE. NOT A SOURCE OF SCOPE.
>
> The other ten `.kiro/specs/` folders were authored BEFORE their module and
> drove the implementation. This one was written afterwards, from the shipped
> code, on 2026-08-20 — because three modules had no spec folder at all (ten
> folders for thirteen modules) and a reviewer could not tell whether they had
> ever been specified.
>
> **Read it as documentation, not as a contract.** A spec that restates what the
> code does provides no drift detection: diffing code against it can only ever
> succeed. Where this file and the code disagree, the CODE is what shipped and
> this file is stale — the opposite of how the other ten folders work.
>
> Precedence is unchanged and this file is not in it:
> `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
> `ARIA_Soul_Spec_v4.md`. There is deliberately no `requirements.md` here; see
> "What a real spec would still need" at the end.

## Authority

`ARIA_Module_Build_Plan.md` Module 11, plus `ARIA_Resolution_Log.md` **item 4**
(*"Module 11 — State Manager"*), **item 2** (self-model split: the narrative is
graph-owned, not persisted here), **item 10** (`relationship_depth` removed),
and **item 18** (restore-boundary clamping, 2026-08-20).

## Responsibility

Persist and restore the non-graph operational working state. Owns NO meaning:
it does not compute PAD, decay Energy, or interpret the self-model. The live
owners — Module 1 (PAD Engine), Module 2 (Needs System), Module 6 (DMN) — hold
the authoritative in-memory state; this module snapshots it to disk and reads it
back.

It depends on no other daemon module. That independence is deliberate and is
worth preserving: it is why the module can be tested and reasoned about alone.

## What it persists

```
aria_state.json   pad {pleasure, arousal, dominance}, energy,
                  last_applied_valence (opaque string or null),
                  self_entity_id (opaque graph node id)
self_model.json   quality_record, consistency_flags,
                  recent_learning_user, recent_learning_self
```

Explicitly NOT persisted: the self-continuity narrative (graph-owned, on the
self-referential EntityNode's `relationship_summary` — ResLog item 2);
`relationship_depth` (removed, ResLog item 10); the four categorical need states
(derived from graph evidence at runtime — Addendum §3). Only Energy is
persisted as a continuous value.

`load_last_applied_valence` and `load_self_entity_id` return **opaque strings**.
This module does not import Module 1's `Valence` enum and does not validate what
a valid valence looks like — conversion happens at the wiring call site.

## Public API

```
load_pad / save_pad                       load_energy / save_energy
load_last_applied_valence / save_...      load_self_entity_id / save_...
load_self_model / save_self_model         load_all / save_all
```

Twelve methods, every one a `load_*` or `save_*`. A test asserts that property,
along with the absence of any `decay` / `appraise` / `prompt` / `graph` name on
the public surface — the structural form of "owns no meaning".

## Invariants

**Spec-backed:**

- `PAD_BASELINE = (0.55, 0.45, 0.58)` — v4 Layer 1, returned when no state file
  exists or the entry is unusable.
- `PAD_MIN / PAD_MAX = 0.0 / 1.0` — the locked v4 Layer 1 PAD range, enforced on
  restore (ResLog item 18).
- `QUALITY_RECORD_MAX = 20` — v4 self-model field 1, "last 20 self-assessments".
  Clamped on BOTH read and write.
- Superseded keys `relationship_depth` and `needs` are dropped on every write so
  they are not perpetuated.

**Build-time / not spec-locked:**

- `DEFAULT_ENERGY = 100.0` and `ENERGY_MIN / ENERGY_MAX = 0.0 / 100.0`. The docs
  pin only the 30 and 20 operational gates, not the scale. The bounds mirror
  Module 2's `ENERGY_MIN` / `ENERGY_BASELINE` **by value, deliberately not by
  import**, to keep this module dependency-free.
- `SAVE_CADENCE_SECONDS = 30.0` — a tuning flag the Daemon reads to schedule
  saves (ResLog item 4). Not an architectural decision.

**Behavioural:**

- **Atomic writes.** Temp file in the same directory, then `os.replace`. A crash
  mid-write leaves either the old complete file or the new one, never a torn
  one. On failure the temp file is unlinked and the error re-raised. Tested by
  making the temp-file write fail and asserting the previous file is
  byte-identical with no `.tmp` left behind.
- **Sibling-key preservation.** Other modules share `aria_state.json`; every
  write is read-modify-write so keys this module does not own survive.
- **Reads never raise.** A missing file yields `{}`; corrupt JSON logs a warning
  and falls back to defaults.
- **Restore clamps, save does not** (ResLog item 18). Non-finite input is
  treated as corrupt rather than clamped — NaN has no position on a scale and
  survives a naive clamp as the upper bound, which would restore a corrupt
  Energy entry as "fully rested". The asymmetry is intended and tested.
- **Every load returns an independent object.** Mutating what a caller got back
  cannot affect the file or a later load.

## Tests

`tests/test_state_manager.py`, 31 tests, added 2026-08-20 — the module was
approved with no test file, its only verification a `__main__` smoke block that
pytest never ran. `tmp_path`-based: this module's job IS the filesystem, so
fakes would test nothing. Nothing touches the real `~/.local/aria/state`.

## Known issue

`python daemon/state_manager.py` fails: running by path puts `daemon/` on
`sys.path`, where `daemon/types.py` shadows the stdlib `types` module. Use
`python -m daemon.state_manager`. Pre-existing, confirmed against an earlier
commit, unrelated to this module's logic.

## What a real spec would still need

Deliberately absent from this file, because inventing it here would be inventing
scope rather than recording it. An architect-authored spec would have to settle:

- Whether the 0–100 Energy scale is locked or remains a tuning flag, and whether
  `ENERGY_MIN`/`MAX` should be imported from Module 2 rather than duplicated by
  value (which would end this module's independence).
- `SAVE_CADENCE_SECONDS`, still a placeholder.
- Whether the by-path invocation failure is worth fixing (renaming
  `daemon/types.py`) or is acceptable as a documented invocation constraint.
