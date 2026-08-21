#!/usr/bin/env python3
"""Generate handoff_bundle/specs/spec_<module>.md from .kiro/specs/<module>/.

WHY THIS EXISTS
---------------
`.kiro/specs/<module>/{requirements,design,tasks}.md` and
`handoff_bundle/specs/spec_<module>.md` held the same content in two places, kept
in step BY HAND. On 2026-08-20 they were hand-synced four times in one session and
the `tasks.md` checkbox ticks were still missed until someone asked. Duplication
maintained by memory is a defect waiting for a deadline.

So the bundle is now DERIVED. `.kiro/specs/` is the source of truth; every
`spec_*.md` is output. Never hand-edit a `spec_*.md` again — edit the source and
regenerate.

    make bundle          regenerate, report what changed
    make check-bundle    verify in sync, non-zero exit if stale (no writes)

THE ONE HAND-AUTHORED INPUT
---------------------------
Each bundle file opens with a header that is NOT derived from any spec: the
upload title, the provenance line, and — for the five modules that have them —
the condensed `> ## AMENDMENT` summaries hoisted to the top so a reader of the
flat upload meets them first. Those headers live in
`handoff_bundle/spec_headers/<module>.md` and are copied verbatim. They are
inputs, like the specs. Edit them there.

THE ASSEMBLY RULES
------------------
Reproduced from the files as committed at 6782a65; `--check` was green against
all thirteen before this script was committed, so the layout below is measured,
not invented.

1. Ten modules have requirements + design + tasks and are titled "locked spec".
   Output is the header, then each part in that fixed order, joined by a
   `---` rule and a `## <module> — <part>.md` marker.

2. Three modules (state-manager, session-buffer, backend-router) have design.md
   only and are titled "module reference (NOT a locked spec)". Output is the
   header followed by design.md verbatim, no rule and no marker — there is
   nothing to separate it from.

3. A leading `> ## AMENDMENT` blockquote is dropped from the design BODY,
   because the header already carries its condensed form and the bundle would
   otherwise say it twice. The rule keys on the AMENDMENT heading, so the
   `> ## STATUS: DERIVED FROM CODE` banner the three derived designs open with
   is left alone — that banner is the whole point of those files.

Part bodies are otherwise copied byte-for-byte. This script paraphrases,
reorders and decides NOTHING about spec content. It is not in the precedence
chain: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md >
ARIA_Soul_Spec_v4.md.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / ".kiro" / "specs"
BUNDLE_DIR = ROOT / "handoff_bundle" / "specs"
HEADER_DIR = ROOT / "handoff_bundle" / "spec_headers"

# Fixed order. requirements before design before tasks — what a reader needs first.
PART_ORDER = ("requirements", "design", "tasks")

# Between the header and each part, and between parts.
JOIN = "\n\n\n---\n\n"


def strip_hoisted_amendments(text: str) -> str:
    """Drop leading `> ## AMENDMENT` blockquote blocks, keep everything else.

    Only blocks at the TOP of the file, and only AMENDMENT ones. A `> ## STATUS:`
    banner or any other blockquote stops the scan and survives untouched, as does
    an amendment further down the body.
    """
    lines = text.split("\n")
    i = 0
    # Step over the H1 and the blank line under it.
    while i < len(lines) and not lines[i].startswith(">"):
        if lines[i].strip() and not lines[i].startswith("#"):
            # Real prose before any blockquote: nothing is hoisted here.
            return text
        i += 1
    head = lines[:i]
    while i < len(lines) and lines[i].startswith("> ## AMENDMENT"):
        # Consume the contiguous blockquote run. Blank lines inside an amendment
        # are written as a bare ">", so the run really is contiguous.
        while i < len(lines) and lines[i].startswith(">"):
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    if i == len(head):
        return text
    return "\n".join(head + lines[i:])


def parts_for(module: str) -> list[str]:
    return [p for p in PART_ORDER if (SPEC_DIR / module / f"{p}.md").exists()]


def render(module: str) -> str:
    header_file = HEADER_DIR / f"{module}.md"
    if not header_file.exists():
        raise SystemExit(
            f"missing header input: {header_file.relative_to(ROOT)}\n"
            f"  Every module needs one. Copy an existing header and edit the title."
        )
    header = header_file.read_text().rstrip("\n")
    present = parts_for(module)
    if not present:
        raise SystemExit(f"{module}: no spec files under {SPEC_DIR / module}")

    if present == ["design"]:
        # Rule 2: design-only module reference. Verbatim, no marker.
        body = (SPEC_DIR / module / "design.md").read_text()
        return header + "\n\n" + body

    segments = [header]
    for part in present:
        body = (SPEC_DIR / module / f"{part}.md").read_text()
        if part == "design":
            body = strip_hoisted_amendments(body)
        segments.append(f"## {module} — {part}.md\n\n" + body.rstrip("\n"))
    return JOIN.join(segments) + "\n\n"


def modules() -> list[str]:
    return sorted(p.name for p in SPEC_DIR.iterdir() if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="verify the bundle matches the specs; write nothing, exit 1 if stale",
    )
    args = ap.parse_args()

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    written: list[str] = []
    mods = modules()

    for module in mods:
        target = BUNDLE_DIR / f"spec_{module}.md"
        want = render(module)
        have = target.read_text() if target.exists() else None
        if have == want:
            continue
        if args.check:
            reason = "missing" if have is None else "stale"
            stale.append(f"{target.relative_to(ROOT)} ({reason})")
        else:
            target.write_text(want)
            written.append(str(target.relative_to(ROOT)))

    # An orphan is a bundle file with no module behind it — a rename left behind.
    expected = {f"spec_{m}.md" for m in mods}
    orphans = sorted(p.name for p in BUNDLE_DIR.glob("spec_*.md") if p.name not in expected)

    if args.check:
        if stale or orphans:
            print("handoff bundle is OUT OF SYNC with .kiro/specs/:", file=sys.stderr)
            for s in stale:
                print(f"  {s}", file=sys.stderr)
            for o in orphans:
                print(f"  handoff_bundle/specs/{o} (orphan: no such module)", file=sys.stderr)
            print("\nrun: make bundle", file=sys.stderr)
            return 1
        print(f"handoff bundle in sync ({len(mods)} modules)")
        return 0

    if written:
        print(f"regenerated {len(written)} of {len(mods)}:")
        for w in written:
            print(f"  {w}")
    else:
        print(f"handoff bundle already in sync ({len(mods)} modules)")
    for o in orphans:
        print(f"  WARNING orphan, delete by hand: handoff_bundle/specs/{o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
