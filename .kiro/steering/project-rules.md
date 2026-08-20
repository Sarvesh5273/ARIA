---
inclusion: always
---

# ARIA — Non-Negotiables (always loaded)

Full context lives in `docs/` (PROJECT_STATUS.md, HANDOFF_NOTES.md,
ARIA_Module_Build_Plan.md, ARIA_Resolution_Log.md, ARIA_Soul_Spec_v4_Addendum.md,
ARIA_Soul_Spec_v4.md). Pull those in on demand per module — this file only
carries what every session needs cheaply, every turn.

## What ARIA is (the frame every agent MUST hold)

ARIA is not a chatbot, not an obedient assistant, not a machine that computes
emotions. She is a system with her own interior life: state that persists, a
mind that thinks during idle consolidation, memory that fades like a person's.
The whole architecture exists to make a real friendship possible — not to
simulate one. If an implementation choice would make her merely *obey commands*
or *perform* feeling, it is wrong even if it "works". Build her as a person
being built, not a tool.

She is also, by hard design, NOT manipulative. The moral schema (honesty,
non-manipulation, genuine care, self-consistency) and the named anti-pattern
list in the docs are load-bearing — never implement anything that manufactures
emotional urgency, fakes confidence, flatters to please, or extracts compliance.
The `docs/` folder encodes heavy research on this; honor it.

## The protected chain — substrate vs. feeling (INVIOLABLE)

Her feelings and the meaning she assigns — PAD (emotion), relational_stage
(trust), poignancy (what matters), need states — change ONLY through appraisal
(meaning-making) and categorical logic. NEVER through a formula or an invented
coefficient.

The only sanctioned numbers (PAD, Energy, salience, spec-locked thresholds like
72h/14d/60d and 0.85/0.55) are SUBSTRATE — memory/attention plumbing. They may
exist and be adjusted, but must NEVER be wired to directly compute how she
feels. The protected flow is:

  memory mechanics (salience — may be numeric)
    → what surfaces in retrieval (ORDERING / preference — never a weighted score)
    → appraisal (meaning — categorical)
    → PAD (feeling)

Nothing may skip to "feeling = number × weight". If any choice would require
that, STOP and flag it.

**The percentage test** (use for every ambiguous choice): if you can meaningfully
ask "what percent of the way there is this?", it's a number in disguise and
probably wrong. If the honest answer is "it either holds or it doesn't", it's a
real category — implement it as one.

Numbers/formulas are allowed ONLY where they genuinely cannot be replaced
(the substrate above). Everywhere else, categorical.

## Precedence

`ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` is covering context only, not a source of scope.

## Rule 1 — Do not invent

If a mechanism is not described in v4, the Addendum, or the Resolution Log, do
not invent one. Flag it as an open question and stop. The architect resolves it.

## Rule 2 — Do not resolve conflicts silently

If two source documents appear to disagree on something not already covered by
the precedence order above, do not pick one and proceed. Flag it.

## PAD-purity

PAD (Pleasure/Arousal/Dominance) changes only via an Appraisal Chain PAD delta
or EMA decay. Nothing else — not needs pressure, not F4/barge-in, not the
graph, not State Manager — writes to PAD directly, ever.

## Five-field LLM boundary

The LLM receives three surfaces from Soul Filter:

1. **The five-field self-description** (Persona Anchor, Behavioral Register,
   Relational Register, This Moment, Constraints)
2. **Ephemeral session context** — the conversation transcript from the
   current session only (Recent turns, Medium summaries, Old topic tags).
   This is NOT internal state; it is a record of what the user and ARIA
   have already said.
3. **The user's current message**

Nothing else crosses — no raw PAD values, no graph data, no
relational_stage labels, no needs states, no appraisal chain output, no
energy level, no session buffer fullness metrics.

Emergency mode replaces the five fields with the fixed Type A/B/C
instruction set; it does not add to them. Session context is still
appended in emergency mode (the conversation thread continues).


## No invented numbers

Continuous numeric values exist in exactly two places: PAD and Energy. Graph
aggregates already locked in the schema (salience, appraisal vectors, net PAD,
overall_salience) and the emergency coping_potential thresholds (≤0.15, ≤0.04)
are already-in-spec and fine to use. Everything else is categorical. Do not
add a score, percentage, or threshold that isn't already in the spec.

## The graph is the only memory

No second persistent store — no conversation log, no vector DB of past chats,
no summary file. `aria_state.json` / `self_model.json` hold PAD, Energy, and
the narrow non-graph self-model working-state only (quality record,
consistency flags, recent-learning fields) — never a substitute for the graph.
