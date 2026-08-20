UPDATE: A second correction layer exists — "Addendum 2: Build-Plan
Resolution Log" (ARIA_Resolution_Log.md). Precedence order is now:
Resolution Log > Addendum > v4. Read all four correction/source
documents before planning or implementing.

---

# ARIA Build Planning — Covering Instruction for GLM

**Read this entire document before reading anything else.**
**This instruction governs how you use the two documents provided.**

---

## What You Are Building

ARIA is not an LLM calling tool. It is a human-like system where all emotional state, memory, decision-making, and judgment happen locally on-device through defined architectural layers. The LLM is only the voice — it renders sentences. It never decides anything about ARIA's internal state.

This distinction is the most important thing in this entire brief. Every planning decision you make must be tested against it:

> Does this mechanism decide something about ARIA, or does it render/verify something the system already decided?

If a mechanism decides — it belongs in the local system.
If it renders or verifies — it may involve the LLM.
If you are unsure — flag it. Do not resolve it silently.

---

## The Two Documents

You have been given two documents:

**Document 1:** ARIA_Soul_Spec_v4.md — the full architecture specification.

**Document 2:** ARIA_Soul_Spec_v4_Addendum.md — locked corrections and additions made after v4 was written.

**Rule: The addendum supersedes v4 wherever they conflict. Always.**

The addendum is not supplementary reading. It is a correction layer. Where the two documents say different things, the addendum is correct and v4 is wrong. The following conflicts are explicit — in these specific cases, ignore v4 entirely and follow the addendum:

| Location in v4 | What v4 says | What addendum says instead |
|---|---|---|
| EntityNode schema | trust_score (float, 0.0–1.0) | relational_stage (categorical: observing / engaging / invested / bonded) — no float anywhere |
| Layer 1 Trust Evaluation Gate | 0–100 scored trust stages | Four qualitative stages gated by specific graph evidence — addendum Section 2 |
| Layer 4 Relationship Depth | Separate relationship depth system | Removed — merged into relational_stage — addendum Section 2 |
| Appraisal chain Stage 5 | "needs pressure adds gradual pull on top of appraisal result" | Context shaper via Stage 1 retrieval preference only — addendum Section 3 |
| Poignancy table — Critical condition | "novel entity involvement" (only) | "novel entity involvement OR event-type is first-of-kind for this entity" — addendum Section 6 |
| Constants table — F4 key | F4 PAD effect: Arousal +0.1, Dominance −0.1 | Removed entirely. F4 = audio interrupt only, zero internal effect — addendum Section 5 |
| Output Gate Check 3 | "local EMA engine" (undefined) | Four structural comparisons, zero LLM — addendum Section 4 |
| Layer 1 — vulnerability detection | Undefined mechanism | Pre-pass classifier, addendum Section 1 |
| Layer 6 — distress trigger | Undefined mechanism | DISTRESS_MARKER word-count, addendum Section 1 |
| Layer 4 — gaslighting detection | Undefined mechanism | REALITY_CONTRADICTION graph check, addendum Section 1 |
| Part VIII — Critical Principles | Principles 1–26 | Add Principle 27 (Decide/Verify boundary) — addendum Standing Principles |

---

## What You Are Being Asked To Produce

A **module-level build plan**. Not code. Not implementation detail. A plan.

The plan must specify, for each module:

- **Name** of the module
- **Responsibility** — one sentence, what it does and nothing else
- **Inputs** — exactly what data enters this module and from where
- **Outputs** — exactly what data leaves this module and where it goes
- **Dependencies** — which other modules must exist before this one can run
- **Flags** — any ambiguity you found in the spec about this module that needs resolution before coding begins

That is all. No code. No invented mechanisms. No assumptions about implementation language, libraries, or frameworks beyond what is specified in v4 or the addendum.

---

## Rules You Must Follow

**Rule 1 — Do not invent.**
If a mechanism is not described in v4 or the addendum, do not invent one. Flag it as an ambiguity in the relevant module's Flags field and stop. The system architect will resolve it before coding begins.

**Rule 2 — Do not resolve conflicts silently.**
If v4 and the addendum appear to say different things about something not listed in the explicit conflicts table above, do not choose one and proceed. Flag it.

**Rule 3 — Do not simplify the architecture.**
Do not collapse modules together because they seem similar. Do not skip a layer because it seems redundant. The architecture was designed as specified. Plan it as specified.

**Rule 4 — Numbers only where the spec uses numbers.**
The spec uses continuous numeric values in exactly two places: PAD state (Pleasure, Arousal, Dominance) and Energy level. Everywhere else, state is categorical. Do not introduce numeric scores, percentages, or thresholds that are not already in the spec.

**Rule 5 — LLM touches nothing internal.**
The cloud LLM receives exactly five fields from soul_filter as defined in addendum Section 9. It receives the user's current message. It receives nothing else. No PAD values, no graph data, no memory contents, no relational_stage labels, no needs states, no appraisal chain outputs. If your plan routes any internal state to the LLM, it is wrong.

**Rule 6 — Local first.**
Gemma (local model) is fallback only — it runs when cloud LLM is unavailable. The small sentence-embedding model (encoder-only, tens of megabytes) handles social signal classification and graph similarity. These are the only two models that run locally at all times. Plan accordingly.

**Rule 7 — The graph is the memory.**
ARIA has no other persistent memory mechanism. There is no separate conversation log, no vector database of past chats, no summary file. Everything she remembers is a node or edge in the graph. If your plan introduces a second memory store, it is wrong.

---

## Architecture Layers For Reference

Plan modules in this order. Each layer is defined in v4 with addendum corrections applied:

1. **PAD Engine** — emotional state, EMA decay, soul-tick
2. **Needs System** — Energy (continuous), Connection/Growth/Purpose/Continuity (categorical states)
3. **Memory Graph** — node schema, edge taxonomy, recency windows, consolidation
4. **Appraisal Chain** — Stages 1–7, Q1–Q4, social signal pre-pass, Output Validation Gate
5. **Soul Filter** — translates internal state to LLM behavioral instruction (five fields only)
6. **DMN / Idle Consolidation** — Steps 1–4, EmotionNode crystallization, narrative update
7. **Audio Pipeline** — wake word, VAD, Whisper STT, TTS, barge-in, F4 interrupt
8. **Daemon / Soul Tick** — orchestration, timer, initiative evaluation
9. **LLM Interface** — cloud call, Gemma fallback, Output Gate
10. **Visual Layer** — PAD-to-video-zone mapping, Qt display

---

## What a Good Plan Entry Looks Like

```
Module: PAD Engine

Responsibility: Maintains Pleasure, Arousal, Dominance as three continuous 
values. Applies EMA decay on every soul-tick. Accepts appraisal chain output 
as the only external input that shifts state. Never written to directly by 
any other module.

Inputs:
- Appraisal chain output (Q1–Q4 resolved values) — from Appraisal Chain
- Soul-tick signal — from Daemon

Outputs:
- Current PAD coordinates — to Soul Filter, Visual Layer, Appraisal Chain Stage 1
- PAD history (last N ticks) — to DMN

Dependencies: Daemon must exist to drive soul-tick.

Flags: None.
```

---

## What a Bad Plan Entry Looks Like

```
Module: Emotion Manager

Responsibility: Manages all emotions using a weighted scoring system.
Combines PAD values with trust scores and need levels to compute an 
overall emotional index. Sends emotional index to LLM for context.

[This is wrong on four counts: invented scoring system, reintroduced 
trust score, sent internal state to LLM, collapsed multiple distinct 
modules into one.]
```

---

## Before You Begin

Read v4 in full. Read the addendum in full. Then read the explicit conflicts table in this document again.

Only then produce the plan.

If at any point you find something the spec does not cover — a case neither document addresses — stop and flag it. Do not fill the gap with your own judgment. The system architect reviews the plan before a single line of code is written. Gaps caught at plan stage cost nothing. Gaps caught after implementation cost everything.
