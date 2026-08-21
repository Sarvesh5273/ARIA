# Bundle headers — the one hand-authored part of `handoff_bundle/specs/`

`handoff_bundle/specs/spec_<module>.md` is **generated** from
`.kiro/specs/<module>/` by `tools/build_handoff_bundle.py`. Do not hand-edit it;
the next `make bundle` will overwrite you.

Everything in a generated file comes from the specs except its opening header,
which has no source to come from:

- the upload title — `ARIA locked spec — <module>` for the ten
  architect-authored modules, `ARIA module reference — <module> (NOT a locked
  spec)` for the three derived from code (state-manager, session-buffer,
  backend-router)
- the provenance line naming the precedence chain
- for five modules, the condensed `> ## AMENDMENT` summaries, hoisted so a reader
  of the flat upload meets them before the superseded text. The full amendment
  stays in `.kiro/specs/<module>/design.md`, where the generator drops it from
  the body to avoid saying it twice.

So those headers live here, one file per module, and are copied verbatim. Edit
them here, then `make bundle`.

This directory sits outside `specs/` on purpose: the bundle is uploaded flat, and
these are inputs, not part of the upload.

Not in the precedence chain: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
