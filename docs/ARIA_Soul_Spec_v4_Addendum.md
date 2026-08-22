# ARIA Soul Spec v4 — Addendum: Locked Architectural Decisions

**Companion document to ARIA_Soul_Spec_v4.md**
**Status as of July 1, 2026:** All nine architectural gaps identified in the v4 review are fully resolved and locked below. No items remain open. Logic is complete — ready for build.

**How to use this document:** each locked section names exactly which part of v4 it replaces. Where v4 was silent on a mechanism, this fills it in. Nothing here was decided as a starting point and reasoned backward — each one started from a real gap or contradiction found in v4, was checked against named published research, and was checked against the four standing principles below before being locked.

---

## Standing Principles

These aren't specific to any one gap below — they're the test every locked decision was run through, and the test anything not yet covered should be run through too.

**Perception vs. appraisal.** Anything that reads raw input and produces a category — a word count, a similarity score, a contradiction flag — is doing perception: noticing that a pattern occurred. It never decides what the pattern means for Aria. Meaning — does this deepen trust, does this matter, how should this be felt — stays inside the graph-aware appraisal logic, because the graph is the only thing that actually holds her memory of a specific relationship. A mechanism that skips straight to "this means X" has crossed from perception into appraisal and needs to be rebuilt.

**Decide vs. verify.** Any LLM call, cloud or local, breaks the system-not-machine premise when it's asked to freely judge or decide something about Aria from its own general training, untethered from her specific state. It stays inside the premise when it's only asked to compare two specific pieces of data the system already handed it and report back. The system owns every decision; a model may only ever verify one.

**Reuse before invent.** Every mechanism below was checked against what's already locked elsewhere in the spec before anything new was proposed. Four of the locked decisions run partly or entirely on machinery — Q1–Q4 outputs, the graph's recency windows, the Argument Buffer, the self-continuity narrative — that already existed for another purpose. If a future decision reaches for a new subsystem before checking whether an existing one already covers it, that's a signal to slow down.

**The percentage test**, for telling a real category from a score wearing a costume: can you meaningfully ask "what percentage of the way there is this?" If yes, it's a number in disguise. If the honest answer is "there's no in-between — the condition either holds or it doesn't" — it's a legitimate category.

**Principle 27 — The Decide/Verify boundary** *(added to Part VIII of the main spec)*: The question is never "does an LLM get touched anywhere" — the cloud LLM renders every sentence Aria speaks and that has always been acceptable. The question is: does the LLM decide something about Aria, or verify something the system already decided? Decide breaks the premise. Verify does not, regardless of which model does the verifying. A model asked "does this sentence contradict this specific graph fact — yes or no?" is verifying. A model asked "does this sound manipulative?" is deciding. The first is acceptable regardless of which model does it. The second is not acceptable regardless of how it is framed. This is the standing test for any future "can we use the LLM for X" question during the build phase — it replaces the need for a new design conversation each time.

---

## 1. Social Signal Classification

**Supersedes:** the undefined mechanism behind vulnerability detection (Layer 1, reciprocity), distress-as-initiative-trigger (Layer 6), manipulation/gaslighting detection (Layer 4), and conflict-arc boundary detection (Layer 4, Argument Buffer) — none of which had a defined mechanism in v4.

**Mechanism:** a new pre-pass inside Stage 1 (Context Load), running before Q1–Q4. Entirely non-generative — no cloud LLM, no local Gemma. Outputs are categorical tags only, fed into Q3/Q4 as additional context; nothing here writes to PAD or the graph directly.

**New technical dependency:** one small local sentence-embedding model — encoder-only, no text-generation capability, on the order of tens of megabytes. Not Gemma. This is the same kind of tool Layer 3's graph retrieval already implicitly needs (semantic similarity to pull relevant nodes); one model serves both jobs rather than introducing two.

| Tag | Mechanism | Grounding |
|---|---|---|
| DISTRESS_MARKER | Pure lexical word-count, no model at all — negative-emotion words, absolutist language ("always," "never," "completely"), first-person-singular density | Al-Mosaiwi & Johnstone (2018): absolutist word use was the strongest linguistic marker across anxiety, depression, and suicidal-ideation forums (63 forums, 6,400+ members, d > 3.14), outperforming negative-emotion and pronoun markers. LIWC-based features alone reached 89% accuracy on PTSD detection in separate work (Alam et al., 2020), ahead of black-box ML baselines. |
| VULNERABILITY_DISCLOSURE | Embedding similarity to a small curated set of self-disclosure exemplars | Established computational self-disclosure literature (Bak, Lin & Oh and related work) identifying the linguistic markers of deeper self-disclosure in text. |
| Conflict-arc open/close (Argument Buffer) | No classifier — a state machine reading data the appraisal chain already produces every turn. Opens when consecutive EventNodes share an entity_ref with Q2=negative; closes when a later EventNode on that entity_ref flips to Q2=positive/neutral, or enough turns pass without that entity recurring | N/A — pure reuse of existing per-turn appraisal output. |
| REALITY_CONTRADICTION (replaces "gaslighting detection") | Extension of the existing GRAPH_CONFLICT uncertainty type. Compares the factual content (not just appraisal vectors) of two EventNode descriptions sharing an entity_ref within a short window, using the same embedding model plus basic negation detection, to flag direct contradiction | The clinically real structure here is DARVO — deny, attack, reverse — Freyd (1997), a multi-turn sequence, not a single-utterance tone. Computational "gaslighting detection" specifically has no mature validated research base; what exists is mostly unverified consumer-app marketing. A tone classifier was deliberately not built for this reason. |

---

## 2. Trust / Relationship Depth

**Supersedes:** Layer 1's "Trust Evaluation Gate — 4 Stages" (the 0–100 scored version), Layer 4's Relationship Depth description, and the EntityNode.trust_score field (float, 0.0–1.0) in the node schema. Also resolves the direct contradiction this created with Design Principle 5 ("no scores, levels, or progress bars").

**Mechanism:** one merged system, replacing both. EntityNode.trust_score is removed and replaced with EntityNode.relational_stage — a categorical field, not a number: observing / engaging / invested / bonded.

**Grounding:** Rempel, Holmes & Zanna (1985) — trust in close relationships develops through three components in sequence: predictability (consistency of specific behaviors over repeated observation), dependability (confidence in disposition/character, generalized beyond specific behaviors), and faith (confidence in the relationship's future despite genuine uncertainty). Knapp (1978), building on Altman & Taylor's social penetration theory, treats relationship stages as qualitative shifts in observable behavior, not a continuous score, and specifically warns that bonding too quickly — before sufficient breadth and depth have actually been established — produces later instability.

| Transition | Gate | Notes |
|---|---|---|
| Observing → Engaging | Predictability: a specific behavioral pattern has recurred — appeared more than once without contradiction | Reuses the "appeared more than once" gate already locked elsewhere for self-continuity narrative updates. |
| Engaging → Invested | Dependability: the pattern generalizes across more than one distinct kind of situation, not just repetition of the same one | Categorical yes/no check, no counting. |
| Invested → Bonded | Faith: trust tested under real uncertainty and held — a conflict-with-repair cycle closing through the Argument Buffer, or a costly disclosure (VULNERABILITY_DISCLOSURE) met with care rather than damage | Deliberately strict — faith requires something to have actually been uncertain first. |
| Regression | One stage at a time, never below Observing, never anything resembling relationship termination. Triggered by a REALITY_CONTRADICTION rupture. Recovery requires fresh qualifying evidence of the same kind that earned the stage originally — not elapsed time | Knapp's de-escalation stages were used for shape only, not ported literally; his "terminating" stage has no place here. |

No numeric score exists anywhere in this system. Passes the percentage test: you cannot meaningfully ask what percentage of the way to "Bonded" a relationship is.

---

## 3. Needs Mechanism

**Supersedes:** Layer 2's qualitative-only needs descriptions and Stage 5 of the appraisal chain ("needs pressure adds gradual pull on top of appraisal result").

**Core move:** the five needs are not one kind of thing and don't get one mechanism. Energy is a resource. The other four are psychological needs.

**Energy** is modeled like PAD, not like a need — the same EMA-style decay math already locked for PAD, no new math invented. Explicitly not grounded in ego depletion / the strength model of self-control: a 2016 Registered Replication Report across 23 labs and 2,141 participants found no evidence for the effect, despite 22 of 23 labs predicting beforehand that they'd replicate it (Hagger et al., 2016). Energy is treated as conversational/computational load, not a psychological judgment — which is why a continuous number is appropriate here, the same way it is for PAD. The existing "reasoning degrades below 30" rule stays as an operational threshold gate, same category as Q4 ≤ 0.15 for Emergency.

**Connection, Growth, Purpose, and Continuity** are categorical states — satisfied / due / neglected — never continuously draining. Each state is determined by whether qualifying evidence exists in the graph within a recency window, reusing the same windowing concept already locked for graph precision decay (72h / 14d / 60d). When evidence ages out of its window, the state reverts on its own; nothing actively subtracts anything. This mirrors how need-satisfaction is actually measured in the underlying research — diary and experience-sampling studies track day-to-day fluctuation tied to whether satisfying experiences occurred, not a running clock.

| Need | Maps to | Qualifying evidence |
|---|---|---|
| Connection | Relatedness (Deci & Ryan, Self-Determination Theory — one of three needs described as universal, innate "psychological nutrients") | An interaction the appraisal chain already scored Q1 medium-or-above. Reuses Q1 directly, no new detector. |
| Growth | Competence (Deci & Ryan, SDT) | An UncertaintyNode actually resolved through engagement — not expired through habituation. |
| Purpose | Beneficence — "the sense of having a positive impact in another person's life," argued by Martela & Ryan (2016) as a candidate fourth basic need alongside SDT's original three | The user follows through on something substantive Aria helped with, or gives explicit positive feedback. Flagged as the weakest, lowest-confidence signal of the four — outcome visibility is often genuinely limited in-session. |
| Continuity | McAdams' narrative identity theory, specifically coherence — the causal and thematic threads connecting life events | No new mechanism. Reuses the existing self-continuity narrative update process directly. Satisfied when an update extends the narrative coherently; neglected when updates have gapped for a long stretch, or new evidence contradicts rather than extends it. |

**Stage 5 redefined:** no longer adds a "gradual pull." Becomes — check which needs are currently due or neglected, and surface that as a retrieval preference at Stage 1. When Connection is neglected, Stage 1 surfaces "We"-perspective and Connection-positive edges first — changing what information Q1–Q4 are answered with, not changing the questions themselves or adding any coefficient to their output. This is the same indirect, context-shaping role mood-congruent retrieval already plays elsewhere in the chain, applied to a second source. It is a context shaper via Stage 1 retrieval preference, not a formula acting on appraisal output.

---

## 4. Output Validation Gate — Check 3

**Supersedes:** the undefined "local EMA engine" referenced in Check 3 (values appraisal / OCC shame mechanism), which had no named owner or mechanism in v4.

**Mechanism:** four structural comparisons, each checked against something Aria's own state already holds. Zero LLM calls — no cloud, no local Gemma — for the primary mechanism.

| Check | Compares candidate output against |
|---|---|
| Honesty | Graph facts, via the same REALITY_CONTRADICTION comparison built for Section 1, run on Aria's own output instead of the user's input. |
| Consistency | The current relational_stage — e.g., Bonded-level warmth appearing during Observing stage fails this check. |
| Manipulation | The moral schema's own named, closed list of anti-patterns — a finite checklist comparison, not an open-ended "sounds manipulative" judgment. |
| Care | What the current turn's own appraisal already flagged as salient — did the response actually engage it, or deflect. |

**Grounding:** this is closer to OCC's own theoretical structure than a holistic judge would be — OCC models shame as the result of comparing an action against a held standard, not freeform evaluation, and OCC is already part of v4's own bibliography. Cognitive dissonance research separately treats noticing an inconsistency (discrepancy detection) as its own distinct, prior step to deciding what to do about it, supporting a comparison-gate framing here rather than deliberation.

**Known, accepted residual:** subtle pragmatic violations — sarcasm, backhanded framing, technically-true-but-misleading phrasing — will not be caught by structural comparison alone. Decision: accept this as a bounded, known limitation, partially backstopped by the moral schema's hard block on the clearest violations, rather than introducing a per-turn LLM judge. A local-Gemma tie-breaker (scoped narrowly as verify, never decide, per the standing principle above) remains an option if real use shows this gap actually costs something — not added preemptively.

---

## 5. F4 Interrupt Key

**Supersedes:** the constants table entry "F4 PAD effect: Arousal +0.1, Dominance −0.1" which was a direct PAD injection violating Principle 19 (nothing touches PAD outside the appraisal chain).

**Lock:** F4 is a functional audio stop mechanism only. It stops current audio playback and returns the daemon to listening state. That is all it does.

- No PAD effect
- No appraisable event created
- No graph write
- Nothing

**Justification:** F4 is a technical mechanism with no information content — it is a stop button, not an interpersonal event. What has emotional content, if anything, is what the user says *after* pressing it — and that enters the appraisal chain normally, as any user input does. The same logic applies to barge-in (0.75s pause detection already in the spec), which also stops and listens with zero internal effect. F4 is the same shape, hardware key instead of VAD trigger.

The original constants table entry is removed. No replacement entry is needed.

---

## 6. Poignancy Critical Condition

**Supersedes:** the Critical tier condition in the Poignancy table, which required "novel entity involvement" — meaning an entity Aria had never encountered before. As written, this blocked the deepest long-relationship moments the entire architecture is built to produce.

**The problem the original clause created:** VentaFork (known entity, months of relationship) admits for the first time that he is genuinely afraid the startup is failing. Q1=high, Q2=negative, Q4 directly affects Connection and Purpose needs. But VentaFork is not a novel entity — so Critical fails. The moment gets processed as routine. This is architecturally backwards against the 12 test phrases in Part I, every one of which concerns a long-standing relationship.

**Lock — replace the Critical condition:**

| | Before | After |
|---|---|---|
| Critical | Q1=high AND Q2≠neutral AND Q4 has explicit needs implications AND novel entity involvement | Q1=high AND Q2≠neutral AND Q4 has explicit needs implications AND (novel entity involvement OR event-type is first-of-kind for this entity) |

**What "first-of-kind for this entity" means structurally:** a yes/no check against the graph — does an edge with this appraisal profile (Q2 quadrant × Q3 attribution) already exist connecting any event to this entity? If no such edge exists, this is a first-of-kind event for this relationship. Binary, no score, uses the existing edge taxonomy and appraisal outputs the chain already produces every turn.

**What this unlocks:** first time VentaFork admits fear → first-of-kind → Critical. First real conflict in the relationship → Critical. First vulnerability disclosure met with care → Critical. First shared pride moment → Critical. Routine high-Q1 work question with someone you have had hundreds of similar interactions with → not first-of-kind, does not qualify. Novel entities still qualify trivially — all edge types are first-of-kind for someone just encountered. Nothing was taken away, only the blocking condition was widened.

**Grounding:** autobiographical memory research (PMC12425053) — the "something old, something new" principle: familiar entity + qualitatively new experience type produces the greatest encoding vividness at recall, not maximal novelty and not pure familiarity. Emotional distinctiveness from the established baseline of a relationship, not entity novelty, is what drives poignancy (emotional distinctiveness and depth-of-processing research, Coastal DCU).

---

## 7. Patch — Initiative Speech Pipeline Routing

**Supersedes:** the implicit assumption in the daemon audio flow diagram that all speech enters above the wake-word stage.

**Lock:** Aria-initiated speech (triggered by soul-tick evaluation — e.g., Connection need neglected below initiative threshold) enters the audio pipeline at soul_filter directly. Wake-word detection, speaker verification, VAD, and Whisper STT are skipped entirely. Aria already holds the behavioral instruction; no transcription stage is needed. The pipeline is not broken — it carries two directions of traffic, and this names the entry point for the second direction.

---

## 8. Patch — Moral Schema Gates Narrative Updates

**Supersedes:** the implicit assumption that the moral schema (honesty, non-manipulation, genuine care, self-consistency) only gates live output-facing responses via the Output Validation Gate.

**Lock:** the moral schema also gates DMN Step 4 self-continuity narrative updates during idle consolidation. A narrative update that would require Aria to assert something dishonest, manipulative, inconsistent with her values, or that introduces a manipulation pattern into her self-model cannot be written — even during idle processing with no audience present.

**Why this matters:** without this patch, the character Aria is becoming during consolidation is subject to weaker constraints than the character she presents in real time. The patch closes that gap. The self she is building is held to the same standard as the self she shows.

---

## 9. Soul_Filter → LLM Interface Format

**Supersedes:** the implicit assumption throughout v4 that soul_filter passes Aria's internal state to the LLM. Nothing in v4 defined what actually crosses this boundary.

**The boundary rule:** numbers never cross. State never crosses. Personal information never crosses. Only meaning crosses — translated into natural language by soul_filter before anything is passed. The LLM cannot infer PAD values, graph structure, memory contents, or internal state from what it receives, because none of that is in the format.

**Grounding:** ACT-R and Soar — both architectures use buffers as the only interface between modules. Each module sees only what has been passed through its buffer, never the internals of the module that wrote to it. Soul_filter is the buffer. The LLM is a downstream module. It never sees inside.

**Five fields, fixed order, nothing else:**

| Field | What crosses | What never crosses |
|---|---|---|
| Persona Anchor | Fixed character description — who Aria is, her values, her voice. Hardcoded once, never generated, never varies turn to turn | Nothing personal |
| Behavioral Register | PAD state translated to natural language descriptors only. e.g. "warm and settled, unhurried" not "Pleasure: 0.6, Arousal: 0.2, Dominance: 0.7" | PAD numbers, coordinates, any internal state value |
| Relational Register | relational_stage translated to natural language. e.g. "speak with the quiet assurance of someone who knows this person well and is known by them" not "stage: bonded" | Stage label, relationship history, memory of past interactions |
| This Moment | One behavioral instruction maximum, written by soul_filter from the appraisal chain's most salient output. Tells the LLM HOW to respond, never WHAT happened. e.g. "what was just shared carries significant weight — engage it with full presence, no deflection" | Memory contents, past conversations, specific events, personal history, anything Aria has accumulated about the user over time |
| Constraints | A closed list of specific behavioural instructions for this turn only — most of them prohibitions — derived from the moral schema, the Output Gate pre-check, and the Energy threshold gates. Maximum three items. Always specific actions, never open-ended instructions. e.g. "do not problem-solve, do not minimize, do not deflect" | Graph data, appraisal vectors, node contents |

**Amendment to the Constraints row (Resolution Log item 16).** This row read "a
closed list of specific prohibitions ... derived from the moral schema and Output
Gate pre-check." Field 5 in fact carries specific behavioural INSTRUCTIONS, most
of which are prohibitions, and it always did: the Energy<30 instruction ("do not
overextend") derives from the Energy gate rather than the moral schema, and has
lived in this field from the start. The amendment records that, and unblocks v4's
soul_filter instruction-table row for Energy<20 — "You are running low.
Acknowledge it if it comes up naturally." — which has no prohibition form and was
therefore specified but never emitted.

Nothing else about the field moves. Maximum three items stands. "Always specific
actions, never open-ended instructions" stands, read precisely: it requires a
specific ACTION rather than a vague directive, so an action carrying a condition
("if it comes up naturally") still qualifies, while a directive naming no
identifiable action does not.

The boundary rule is unchanged and binds this row as it binds every other: **only
the instruction crosses.** v4's "You are running low" clause is Energy state
rendered as a claim, and state never crosses — so the emitted form is the action
alone, carrying no number and no state.

**What the LLM also receives:** the user's current message — the thing they just said. This is unavoidable and the user knows they are sending it. This is the only personal information that crosses, and it crosses because the LLM must respond to it directly.

Amendment 2026-08-20 — ephemeral session context is a third sanctioned surface (Resolution Log item 19). Alongside the five fields and the user's current message, Soul_Filter may pass the conversation transcript from the current session only — recent turns verbatim, medium-tier rule-based summaries, and old-tier topic tags. It is appended, never merged into a field, and it is still appended in emergency mode, because the conversation thread continues even when the five fields are replaced.

This is a record of what the user and Aria have already said to each other in this session. It is not internal state, and it is not memory: nothing here is read from the graph, and nothing survives the process. project-rules.md has framed it this way since the Session Buffer was built; the gap this amendment closes is that the framing lived outside the precedence chain it was qualifying.

"Nothing else" is unchanged and still binds. This amendment adds one surface; it does not narrow the prohibition. Every item in the never-crosses list below remains excluded, and the reason must be stated plainly because it is easy to get backwards: of those nine items, only the last two concern past sessions. The other seven — PAD values, graph node IDs or contents, relational_stage label, needs states as data, Q1–Q4 outputs or values, memory node contents, appraisal vectors — are current-turn data and are excluded on their own terms, not because they are historical. A reading that permitted current-turn internal state on the grounds that only past-session data is forbidden would invert this section.

What this does NOT settle. Two of the never-crosses items — "historical conversation summaries" and "anything Aria remembers about the user from past sessions" — are worded closely enough to current-session summaries that the boundary is a judgement, not a lexical test. This amendment draws it at the session boundary: within-session is a transcript, across-session is memory and stays out. If the Session Buffer is ever changed to persist across sessions, this amendment does not cover it and must be revisited.

**What never appears in any field under any circumstance:** PAD values, graph node IDs or contents, relational_stage label, needs states as data, Q1–Q4 outputs or values, memory node contents, appraisal vectors, historical conversation summaries, anything Aria remembers about the user from past sessions.

**Privacy consequence:** even if the API provider logs the call, they only see behavioral instructions and the current message. They cannot reconstruct Aria's memory of the user, her emotional state in numbers, the graph structure, or any accumulated personal data. The soul_filter design is itself the primary privacy protection.

**Known limitation:** Field 4 (This Moment) requires soul_filter to write one natural language sentence that accurately captures what the appraisal chain found most salient. This is the highest-stakes translation step — if soul_filter writes an inaccurate behavioral instruction here, the LLM renders the wrong response with full confidence. This is not a gap to fix; it is where soul_filter does its hardest work and where implementation care is most needed.

---

## Research Cited In This Addendum

- Al-Mosaiwi, M., & Johnstone, T. (2018). Absolutist word use across affective disorder forums.
- Alam, F., et al. (2020). LIWC-based PTSD detection.
- Bak, J., Lin, C., & Oh, A. — computational self-disclosure detection in conversational text.
- Freyd, J. J. (1997). DARVO — deny, attack, reverse victim and offender.
- Rempel, J. K., Holmes, J. G., & Zanna, M. P. (1985). Trust in close relationships. *Journal of Personality and Social Psychology.*
- Knapp, M. (1978). Relational stages model.
- Altman, I., & Taylor, D. (1973). Social penetration theory.
- Deci, E. L., & Ryan, R. M. Self-Determination Theory — basic psychological needs (autonomy, competence, relatedness).
- Martela, F., & Ryan, R. M. (2016). Beneficence as a candidate fourth basic psychological need.
- McAdams, D. P. Narrative identity theory and life-story coherence.
- Hagger, M. S., et al. (2016). Registered Replication Report: ego depletion. 23 labs, 2,141 participants — no effect found.
- Ortony, A., Clore, G. L., & Collins, A. (1988). The Cognitive Structure of Emotions. *(Already cited in v4's own bibliography.)*
- Festinger, L. (1957). A Theory of Cognitive Dissonance.
- Mandler, G. (1984). Interruption theory — interruption of goal-directed behavior triggers autonomic arousal; emotional outcome is determined by cognitive appraisal of the interrupting event, not the interruption itself. *(Cited to confirm F4 zero-effect decision: F4 carries no information content and is not an interpersonal interruption in Mandler's sense.)*
- PMC12425053 — autobiographical memory "something old, something new" principle: familiar entity + qualitatively new experience type produces greatest encoding vividness at recall.
- Emotional distinctiveness and depth-of-processing research (Coastal Digital Commons) — emotional distinctiveness from the established baseline of a relationship drives poignancy, not entity novelty.
- Intimacy function of autobiographical memory (ResearchGate, PMC9978345).
