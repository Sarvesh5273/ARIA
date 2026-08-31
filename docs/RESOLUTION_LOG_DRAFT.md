# Resolution Log — DRAFT items for approval

**Status: NOT AUTHORISED. Nothing here is in force.**

`ARIA_Resolution_Log.md` is the top of the precedence chain and this pass did not
touch it — the same discipline the 2026-08-22 pass recorded for its own draft
("ResLog item 20 — drafted for approval, not written"). This file is the proposal.
Approve, amend or reject each item; whatever survives gets copied into the
Resolution Log by the architect, and this file is then deleted.

Written after wiring the inbound voice path (2026-08-29). Running code exists for
items A, B and D-as-worked-around; items C, E, F and G are questions, not
implementations.

Each item states the PROBLEM, the EVIDENCE (measured, not argued), what is
PROPOSED, the ALTERNATIVES REJECTED and their reasons, and what the item explicitly
does NOT cover. The last section matters most: an item that quietly widens is how a
precedence chain stops being one.

---

## Item A — Inbound voice driver loop: authorisation of record

**Closes:** `.kiro/specs/audio-pipeline/{requirements,design}.md` OQ-1.

### Problem

Module 7's spec names this loop and declines to design it:

> **OQ-1 (build-time wiring):** the streaming driver loop that calls
> `capture_turn()` and forwards its text to `AriaDaemon.route_inbound_turn` lives
> at the top-of-tree wiring layer, not in this module. Named, not resolved here.

No Resolution Log item resolves it. Item 19's post-approval authorisation list —
Session Buffer, `session_context`, meta-commands, BackendRouter/Track A, the
Energy<30 modifier, the Daemon distress gate, the conflict-arc absent-turn count —
does not include inbound audio, a capture loop or a voice host.

OQ-1's wording is a SCOPING statement from a `.kiro` module spec, which sits outside
the precedence chain. It says the loop is not Module 7's decision. It does not
authorise a particular loop, and it cannot: `.kiro` specs are module artifacts.

So `voice_main.py` currently exists in the same position Session Buffer occupied
before item 19 — architect-directed work that appears nowhere in the chain, which
is precisely the condition item 19 was written to end:

> None of it appeared in v4, the Addendum, or this log, which left a reviewer
> unable to distinguish architect-approved work from agent invention.

### Evidence

Verified 2026-08-29 on this machine, two consecutive turns, scratch runtime root:

| spoken | endpointed | transcribed | replied | spoke |
|---|---|---|---|---|
| "i finally shipped it today and it actually works" | 4.47 s, silence | verbatim, 0.49 s | 8.9 s | Kokoro, 0.4 s |
| "honestly i have been worried the whole project might fail" | 5.28 s, silence | verbatim, 0.49 s | 11.9 s | Kokoro, 1.0 s |

`event_nodes` 1 → 2; she referenced the first turn in the second reply, so session
context carried. Suite 902 → 938 passing, and **the soul layer did not move: 686
before, 686 after.** That figure is the argument for the one-way dependency arrow
holding a second time, exactly as the boundary phase reported it.

### Proposed

Authorise the inbound driver loop on these terms, and no wider:

- It lives at the top of the tree (`voice_main.py`), not in `daemon/`.
- It is BLOCKING and SINGLE-THREADED. This keeps it inside the host shape the log
  already reasons about: item 29A's Energy analysis assumes `route_inbound_turn`
  runs synchronously and ticks fire between turns, and item 30's self-model clobber
  is "not reachable in the synchronous REPL". A threaded host reopens both.
- It calls only existing public entry points — `capture_turn()`,
  `route_inbound_turn()`, `run_scheduler_step()`, `save_periodic()` — plus the one
  named private reach-in in item D.
- It changes no approved module. `AriaDaemon.__init__` is untouched, as is
  `AudioPipeline`. The composition pattern is the one Module 10's wiring already
  established: satisfy the Protocol and decorate (`visual_bridge.SpeakingSignalAudio`
  → here, `audio_endpoint.QueuedCapture`).
- Transcribed text enters at `route_inbound_turn(user_text=...)` and nowhere else.
  The five-field boundary is untouched: no audio, no VAD probability, no confidence
  score and no endpointer state reaches Soul Filter or any transport.

### Alternatives rejected

- **Fold voice into `main.py`.** Every text bring-up would then require five
  providers and two model files, and `main.py`'s text path is the verified one that
  `make preflight` and the tracker describe.
- **Poll `capture_turn()` and stop when a transcript appears.** This is what the
  literal reading of v4's stateless-poll flow gives, and it truncates: it returns as
  soon as ANY speech is in the ring, i.e. mid-sentence. It also re-runs Whisper over
  a growing buffer on every poll. See item B.
- **A threaded host driving the clocks continuously.** Correct eventually, and out
  of scope here — it reopens item 29A's flagged per-turn Energy question.

### Does NOT cover

Barge-in or F4 (item E). Speaker verification (item C). A threaded or async host.
Idle sounds. The Visual Layer. Any change to what crosses to the LLM.

---

## Item B — Utterance boundary: a genuine spec gap, and two build-time constants

### Problem

v4's audio flow, read literally, is a stateless poll: capture into the 20-second
ring, ask the wake word, verify the speaker, trim to speech, transcribe. Under that
reading a wake word firing on "Aria" transcribes the ring AT THAT MOMENT — before
the question has been asked.

**Nothing in the precedence chain says how long to keep listening.** Searched v4,
the Addendum, this log, the Build Plan, HANDOFF_NOTES and every `.kiro` spec for
end-of-utterance, silence hangover, speech timeout, utterance boundary, maximum
utterance length and listen-after-wake. There is no such constant.

The adjacent rows are each governing something else, and using one would be worse
than an honest placeholder because it would look authorised:

| row | what it actually governs |
|---|---|
| `Barge-in window \| 0.75 seconds` | the window she opens between HER OWN sentences to notice being interrupted — output chain |
| `Post-speak window \| 5–10s random` | closest in spirit; **the only occurrence of the phrase in the repository**, with no prose, no trigger and no mechanism |
| `Idle sound min silence \| 10 seconds` | a precondition on playing an ambient clip |
| `Ring buffer \| 20 seconds` | how much audio EXISTS; auto-evicts |
| `VAD threshold \| 0.5` / `chunk \| 512` | which SAMPLES are speech — a per-window filter, not a timer |

### Proposed

Confirm that utterance endpointing is a HOST concern and that its two values are
build-time tuning constants, to be added to this log's closing "Open — build-time
tuning constants only" list:

- **silence hangover** — `0.8 s` (`--silence-hangover`)
- **minimum speech** — `0.20 s` (`--min-speech`)

Both are exposed as CLI flags rather than buried, so they are knobs an operator
turns. The utterance ceiling is NOT a new constant: it is derived from v4's cited
20-second ring, on the reasoning that an utterance longer than the ring cannot be
represented downstream anyway.

Confirm also that the endpointer is not a second gate. It reads `VAD_THRESHOLD` and
`VAD_CHUNK_SIZE` from the module that owns them, defines neither, and returns
**untrimmed** audio so `AudioPipeline._trim_to_speech` remains the only thing that
decides what counts as speech. The layering is the one already established for the
Visual Layer: the 8-second gate decides whether a zone change is ALLOWED, mpv's
loop boundary decides when an allowed change is RENDERED — two mechanisms, two
layers, one question each.

### Alternatives rejected

- **Reuse 0.75 s from barge-in.** Borrowing an output-chain number to look cited.
- **Use `Post-speak window 5–10s random`.** Inventing the mechanism around an
  in-spec number. Available if the architect states the mechanism.
- **A fixed listening window** (the shape the previous `voice_main.py` had, with an
  uncited hardcoded 4.0 s). Cuts off long sentences and waits pointlessly after
  short ones.

### Does NOT cover

The follow-up window after a wake word — whether one wake word should open a
multi-turn conversation. Currently the wake word is required per utterance, which
is v4's flow diagram read literally. If `Post-speak window` was meant to be that
mechanism, it needs stating.

---

## Item C — Speaker verification: NEEDS A DECISION, not an implementation

**This is the one item that cannot be resolved by reading the spec more carefully.**

### Problem

v4 names "Silero Speaker Verification (voiceprint.pt — cosine ≥ 0.75)".
**Silero does not publish a speaker-verification or speaker-embedding model.** Its
released models are STT, TTS, VAD and text enhancement. Checked against the
upstream repository, 2026-08-29.

`adapters/audio_speaker.py` is written, correct, and will work the moment it is
handed a scripted model and an enrolled voiceprint. What is missing is the DECISION
about which model substitutes — and that adapter already declines to make it:

> the alternative is substituting a different speaker model, which is a decision
> about identity verification and therefore an architect call, not an adapter's
> (Rule 1).

The gate cannot simply be skipped: `capture_turn()` applies the cited 0.75
comparison unconditionally, and `audio_stack._Absent` raises from every method, so
something must occupy the slot. Addendum §7's bypass is outbound-only.

### What runs today, and what it costs

`voice_main.DeferredSpeakerVerification` returns 1.0 for every voice. It requires
`--i-accept-no-speaker-verification` to construct, refuses with the consequence
spelled out otherwise, and the startup report states it every run.

The cost, stated plainly: anyone audible becomes her primary entity for that turn.
Their words are appraised, move PAD, and are written to the graph against an id
that means "the person I know". That is the door speaker verification exists to
close — `audio_speaker.py`'s own words, that treating an unrecognised voice as an
event "would mean an unrecognised voice could move her emotional state".

It deliberately lives in the voice host rather than in `adapters/`, on the
precedent HANDOFF_NOTES records for refusing an always-awake wake backend: such a
thing "must not be something a wiring layer can pick by accident". With identity
that argument is stronger, not weaker.

### Options, for the architect to choose between

1. **Substitute a model.** WeSpeaker ResNet34 and ECAPA-TDNN are the realistic
   candidates; both produce a cosine-comparable embedding, so `audio_speaker.py`
   needs no change beyond being given a path. Requires accepting a named deviation
   from v4's provider.
2. **Re-scope the gate.** State that on a single-user private machine the wake word
   is the access control and speaker verification is Phase 2+. The `0.75` constant
   stays in the spec, unused, rather than being deleted.
3. **Leave it deferred** and keep the explicit acknowledgement flag as the record.

### Enrolment, if option 1

Unspecified everywhere. v4's `aria_state.json` listing carries a
`voiceprint_enrolled` key and its build state says "Voiceprint enrollment ❌ Not
run"; no document says who performs it, how, or what it writes. `enrol()` exists on
the adapter and nothing calls it.

The forward path already on record: HANDOFF_NOTES states enrolment "should SET
`save_primary_entity_id` rather than replace the mechanism, since binding a
voiceprint to an EntityNode id is exactly what these methods store." Binding
remains the wiring layer's job — the adapter holds no StateManager handle, which is
what makes "an audio backend decided who you are" structurally impossible.

### Does NOT cover

Multi-speaker support. Anything about what happens to a rejected speaker beyond
v4's existing "no transcript" (which is already correct: no appraisal, no
EventNode, no PAD movement).

---

## Item D — `AudioPipeline.reset_input()`: removing the one private reach-in

### Problem

`capture_turn()` appends to the ring and then trims **the whole ring**. A host that
hands over one complete utterance per turn must therefore clear the ring between
turns, or turn two re-transcribes turn one alongside the new speech — she would
hear the previous sentence again, appraise it again, and write a second EventNode
for something said once.

`RingBuffer.clear()` is public, but `AudioPipeline` keeps the buffer private and
exposes no input reset. So `voice_main._clear_pipeline_ring` reaches
`pipeline._ring.clear()`.

It is named and documented rather than hidden, on the precedent `main.py` set for
`graph._conn` ("One private read remains, named rather than hidden ... Module 3
exposes no count API and inventing public API on the graph for a debug readout is
the wrong trade"). Unlike that one, this is a WRITE on the wired path, which is a
weaker position to defend.

### Evidence

`tests/test_voice_host_inbound.py::test_two_utterances_in_a_row_do_not_bleed_into_each_other`
fails without the clear: the first utterance's words appear in the second
transcript.

### Proposed

Add one method to Module 7:

```python
def reset_input(self) -> None:
    """Discard buffered inbound audio. Output chain untouched."""
    self._ring.clear()
    self._reset_vad()
```

Module 7 is APPROVED, so this needs a ruling rather than an edit — which is why it
is here and not in the code. It is additive, touches no cited threshold, changes no
existing behaviour, and `stop_playback()`'s zero-effect guarantee is unaffected
(this method touches neither playback nor PAD).

### Alternatives rejected

- **Keep the reach-in.** Works; a private write on the wired path is a worse thing
  to leave than a private read in a debug readout.
- **Push 20 s of silence to evict the ring.** Public API only, and dishonest:
  fabricated audio through a real VAD to achieve a side effect.
- **Construct a fresh pipeline per utterance.** Reloads Whisper every turn.

---

## Item E — Barge-in and F4: an unflagged gap, not an unbuilt feature

### Problem

v4 specifies the mechanism's OWNER and its EFFECT but never its MECHANISM.

Owner: `Barge-in window | 0.75 seconds | aria_daemon.py`. Effect: Addendum §5 —
audio stop only, "No PAD effect, no appraisable event, no graph write, nothing" —
and the Daemon implements both handlers as exactly that, one line each.

Unspecified: who segments her reply into sentences, who opens the 0.75 s window,
who listens during it, who calls `on_barge_in()`, and where the F4 listener lives.
v4 names `interrupt_handler.py`; no such file exists and no document describes it.

Unlike the capture loop, **this is not carried as a flagged OQ anywhere** — the
Daemon spec's own OQ list is about thinking-sound precedence, initiative-on-`due`,
pressure tie-breaks and tick cadences. It is an absence rather than a named
question, which is the harder kind to notice.

### Consequence today

`voice_main.py` does not feed the microphone while she speaks, and waits for
playback to finish before listening again. So **she cannot currently be
interrupted.** The startup report says so every run.

This is not a preference. Without the wait she captures her own voice through the
microphone, transcribes it, and answers herself — appraising her own words as the
user's and writing them to the graph. `CommandLinePlayback.wait()` exists for
exactly this and its own docstring anticipates the trade: "NOT used on the wired
path — `speak()` is fire-and-forget so a barge-in can interrupt it — but a bring-up
that wants to hear a clip end needs it."

### What a ruling would need to settle

1. Sentence segmentation: who splits her reply, and on what.
2. Who listens during the 0.75 s window, given that the mic is otherwise the
   endpointer's, and how self-hearing is prevented if the mic stays live while she
   speaks (acoustic echo cancellation is a real dependency, not a detail).
3. Where the F4 listener lives. v4's `interrupt_handler.py` does not exist; a global
   hotkey on macOS needs Accessibility permission, which is a deployment fact.

### Does NOT cover

Any change to Addendum §5. Both handlers are correct as written and this item does
not reopen them — it asks who calls them.

---

## Item F — `DEFAULT_MODEL` cannot serve a conversational turn (measured)

### Problem

`transport_ollama.DEFAULT_MODEL` is `qwen3.5:9b-mlx`, set by item 24. It cannot
answer a turn inside the adapter's 120 s ceiling on this machine.

### Evidence

Measured 2026-08-29, prompt "Say hello in one short sentence.", same daemon:

| model | wall time | tokens generated | reply |
|---|---|---|---|
| `qwen3.5:9b-mlx` | **163.4 s** | **2510** | "Hello, how are you today?" |
| `gemma4:e2b-it-qat` | **3.7 s** | 3 | "Hello!" |

The token count is the finding, not the speed: 2510 tokens to produce a
seven-word reply. `qwen3.5` advertises a `thinking` capability and the reasoning is
unbounded, so latency scales with how much it decides to deliberate rather than
with the answer's length.

This reproduces, with a different model, the pattern item 24's own A/B already
found — "12b tripped the adapter's 120 s ceiling mid-A/B. That ceiling was
deliberately NOT raised: a model that cannot answer inside a conversational timeout
has told you something." And it reproduces the reasoning HANDOFF_NOTES records for
why the 12B recommendation failed: the five-field boundary makes the local task
short and narrow, so extra capacity goes into reasoning depth the architecture
deliberately routes to cloud.

**In voice this matters more than in text.** A silent pause is the only feedback
channel while she generates, and 163 s of it is indistinguishable from a crash.

### Proposed

Revert `DEFAULT_MODEL` to v4's own named model, `gemma4:e2b-it-qat` — which is
already present in the adapter as `SPEC_MODEL` and as rung 2 of `resolve_model`'s
ladder.

**Not done in code.** HANDOFF_NOTES records the standing instruction: "`DEFAULT_MODEL`
was left at `gemma4:12b-it-qat` as directed. Reverting it reverses an explicit
instruction on new evidence, so it waits for a word rather than being done
quietly." The same discipline applies here. Until then, `--local-model
gemma4:e2b-it-qat` is the documented workaround and is what the verified voice turns
above used.

### Also worth settling

Whether a thinking model should be admissible in the local-voice slot at all. The
reasoning block is not merely slow — item 15 keeps transports verbatim and item 25
strips format markers only at the speech boundary, so a `<think>` block that
reaches the Output Gate is judged on content and could be spoken. `--local-model`
is currently the only thing standing between that and a speaker.

---

## Item G — PAD did not move across two real turns (observation, not a proposal)

Recorded because it is the kind of thing that stops being findable later, and
because the honest answer is "I do not know yet".

### What was observed

Across both verified voice turns, PAD stayed at baseline `0.550 / 0.450 / 0.580`
and Energy at `100.0`, while `event_nodes` went 1 → 2 and her replies were
contextually correct.

Energy is EXPECTED and already explained: item 29A establishes that under a
synchronous host Energy only ever holds or recovers, and at baseline recovery is a
no-op.

PAD is the open part. A direct `AppraisalChain.appraise()` probe on the two
transcripts showed the chain DISCRIMINATING correctly — poignancy `LOW` for "I
finally shipped it today and it actually works", `HIGH` for "Honestly I have been
worried the whole project might fail" — and yet a `+0.000` PAD delta on both.

`PROJECT_STATUS.md` records PAD moving 0.550 → 0.580 on a positive turn on
2026-08-22, so the path is live.

### Why nothing was changed

PAD purity: PAD moves only through an Appraisal Chain delta or EMA decay, and the
Appraisal Chain and PAD Engine are approved modules with 65 and 53 tests over them.
Adjusting either to make PAD move would be exactly the invented-coefficient move
Rule 1 exists to prevent.

### What would settle it

The probe was not equivalent to the Daemon's call — it omitted the needs states and
uncertainty refs the Daemon passes — so it is suggestive rather than conclusive.
Two turns on a graph with no history is also a thin basis; the appraisal chain reads
context, and there was none. Worth re-checking against a graph with real history
before treating it as a defect.

---

## Summary — what needs a word from the architect

| item | kind | blocking? |
|---|---|---|
| A — driver loop authorisation | record a decision already acted on | no; legibility |
| B — endpointer constants | confirm build-time category | no |
| C — speaker verification | **a real decision, no spec answer exists** | yes, for trustworthy voice |
| D — `reset_input()` on Module 7 | approve an additive method | no; removes a private write |
| E — barge-in / F4 | specify an unspecified mechanism | yes, to be interruptible |
| F — `DEFAULT_MODEL` | reverse a prior instruction on new evidence | yes, for usable latency |
| G — PAD on real turns | observation to investigate | unknown |
