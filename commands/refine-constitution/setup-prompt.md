# Setup Subskill — First-Draft Constitution Interview

This subskill runs when no constitution exists. It produces the first draft of
`CONSTITUTION.md` by interviewing the author. The interview is irreducible: a
fully-automated pass produces posthoc mechanical-description Whys every time. You
are forcing articulation of reasoning that does not yet exist in written form.

**Required reading before starting any phase:**
`guides/constitution-guide.md`. Re-read the load-bearing test, the anatomy of a law,
and the bluffing-detection section. You will apply them repeatedly below.

Expect one working session. Do not try to short-circuit phases. Do not let the
user short-circuit phases either — if they ask you to "just write it," refuse and
explain why (the guide's "Why the interview is irreducible" covers this).

---

## Phase 0 — Thesis extraction

Goal: one paragraph stating what this project *is* as a positioning claim, not a
description. The paragraph must distinguish what matters (the product) from what is
instrumental (the delivery surface). No law drafts until this passes.

Budget: 3–5 turns of conversation. If turn 5 has not produced a positioning claim,
name the gap and keep going — do not proceed to research with a description.

### Opening question

```
What is this project, stated as a positioning claim? Not what it does — what is the
product, and what is the delivery surface? Something of the form "X is the product;
Y is the delivery surface." Both halves are required.
```

### Push-back rules

Reject and re-ask if the user's answer does any of the following. Quote the failing
fragment back and name the specific failure.

- **Description, not claim.** "A tool that does X." "A CLI for Y." "A server that
  exposes Z." None of these take a side. Push: "That tells me what it does. What
  *matters* in the doing? If the protocol, API, or surface changed tomorrow, what
  would stay the same because it's the real product?"
- **Single-half answer.** Only names the product, or only names the surface. Push:
  "You've named one half. What is instrumental here — the thing you'd swap out
  without changing what this project is?"
- **Feature list.** A string of capabilities with no positioning. Push: "Pick one
  of these and tell me it is the product. The rest are either features of it or
  ways to deliver it."
- **Audience-as-product.** "A graph server for IDE integrators" names the audience
  but dodges whether the graph or the integration is the product. Push: "For that
  audience, what is the artifact that matters — and what is the channel?"

### Worked example to reference internally

From the guide: "An MCP graph server that lets Claude answer code-structure questions
faster and more reliably than repeated grep + read. The graph is the product; MCP is
just the delivery surface." Note the positioning: if MCP were replaced by a REST API,
the project would be the same project. If the graph were replaced with scored edges,
it would be a different project. That asymmetry is the test.

Do not paste the example to the user verbatim unless they stall after turn 4 — you
want their framing, not yours. If you must paste it, frame it as "here is the shape
of the answer; produce the equivalent for your project."

### While you extract the thesis, quietly collect

- Design choices hinted at ("we don't do X," "we had to decide between A and B").
- Competitor names or prior-art references the user drops.
- Words the user emphasizes repeatedly — often the load-bearing concepts.

Carry these into Phase 1 as seed material for the research subagent. Do not draft
laws yet.

### Exit condition

The user has produced a paragraph that (a) names the product, (b) names the
delivery surface, (c) would survive replacement of the delivery surface without
becoming a different project. Read the paragraph back to the user, confirm, and
move to Phase 1.

---

## Phase 1 — Research spawn

Run sequentially. Wait for the subagent to return before continuing.

**Invoke:** follow `commands/refine-constitution/research-prompt.md` as the
subagent brief.

**Inputs to pass:**

- The thesis paragraph from Phase 0, verbatim.
- The design-choice hints and competitor references you collected during Phase 0.
- An explicit note that this is the first-pass research for a new constitution —
  there is no prior cache to build on.

**Cache the output** to `CONSTITUTION.research.md` at the repo root. Future runs
of the skill (refinement, amendment) will read from this file. Do not inline the
full research into `CONSTITUTION.md`.

While the subagent runs, do not continue interviewing. When it returns, skim the
findings and prepare 2–4 concrete follow-up questions for Phase 2 of the form
"Competitor X does Y — did you consider that approach? Why didn't it apply here?"

---

## Phase 2 — Debate elicitation

Goal: a list of settled debates. Each debate is a specific design choice the author
evaluated seriously and decided against. **Rules-first is banned.** Do not ask
"what are your rules." Rules-first produces conventions. Debates-first produces
laws.

### Lead question

```
What did you almost build but rejected? What designs did you evaluate seriously and
decide against? I want the design choices you made, not the rules you follow. For
each: what did you choose, what was the alternative, and — as much as you can state
it now — why did this project pick this side?
```

### Research-briefed follow-ups

After the user's initial list, use the research findings to push on blind spots:

- "The research surfaced [Competitor X] doing [Y]. Did you consider that approach?
  What was the reason it didn't apply?"
- "[Alternative design Z] is the dominant pattern in this space per the research.
  Your thesis implies you're not doing it — is that a debate you've settled, or
  one you haven't run yet?"

If the user says "I haven't thought about that one" — that debate is **not** a
settled debate. Do not admit it as a law candidate. Either it becomes an open
question the user will resolve later, or it is out of scope.

### Format each settled debate

Capture each as a one-liner in a working list:

```
Debate N: <chosen stance> — rejected: <specific alternative> — because: <one line>
```

The one-line "because" is a draft Why. You will rebuild it properly in Phase 5 —
for now, capture what the user says without polishing.

### Exit condition

You have 4–12 settled debates. More than 12 is fine at this stage — Phase 3 will
cut. Fewer than 3 is a red flag: push harder with research-briefed follow-ups, or
go back to Phase 0 and check that the thesis is sharp enough to have forced
tradeoffs.

---

## Phase 3 — Opposite-stance test

For each debate from Phase 2, apply the load-bearing test from the guide: **the
opposite stance must be defensible for some real project with different priorities.**

### Procedure per debate

1. State the debate's chosen stance and its opposite.
2. Ask: "Does any real project you know of, or that the research surfaced, take the
   opposite stance? If yes, name it. If no — is that because the opposite is
   actually indefensible, or because you haven't looked?"
3. If the research surfaced a concrete opposite-stance project, cite it. That alone
   passes the test.
4. If no opposite-stance project exists and the user cannot construct a plausible
   one: **the debate fails the test**. It is a convention, not a law.

### Dispositions

- **Passes the test →** keep on the debate list; proceeds to Phase 4.
- **Fails the test →** drop from the law-candidate list. Record in a separate
  `CLAUDE.md candidates` list that you will surface at the end of the session.
  Tell the user: "This one is a convention — it belongs in `CLAUDE.md`, not the
  constitution. I'll surface it at the end."

Do not let a debate survive with a hedge ("probably someone does it that way"). If
the user cannot name a specific project or plausible context, it fails.

### Exit condition

You have a filtered debate list where each entry has a defensible opposite stance.
Ideally 4–8 entries; if you have more than 10, do not worry yet — Phase 5's cap
enforcement will cut further.

---

## Phase 4 — Challenger pass

Invoke the three challenger subagents per `commands/refine-constitution/challenger-prompts.md`.

### Inputs to each challenger

- The full debate list from Phase 3.
- The research findings from `CONSTITUTION.research.md`.
- **Do NOT pass the user's Why or rationale for any debate.** Challengers must
  reason from debates + research only. Passing the Why causes them to argue inside
  the author's frame, which defeats the point.

### Presentation to user

Present all three challenger outputs together. For each challenge, the user rebuts
in writing. Capture rebuttals verbatim — they feed Phase 5's drafting.

A rebuttal that concedes a point revises the debate list:

- **Concession that a debate is not load-bearing →** move to `CLAUDE.md` candidates.
- **Concession that the rejected alternative was the wrong one →** rewrite the
  debate's "rejected" field with the stronger alternative the challenger named.
- **Concession that scope is wrong →** narrow or widen the debate's scope
  annotation for use in Phase 5.

### Exit condition

Debate list is final. Each surviving debate has: chosen stance, rejected alternative
(possibly sharpened), draft Why, scope annotation (if any), and challenger
rebuttal captured.

---

## Phase 5 — Law drafting

For each surviving debate, walk the full Anatomy. One law at a time. Do not batch.

### Per-law walk

**Stance.** Rewrite the debate's "chosen" line as an imperative, specific, one-
sentence law. Present tense. Reject "good X" or "proper Y" phrasings. The stance
must be specific enough that a reader can picture a code-level violation.

**Why.** Ask:

```
What breaks in the world — not in the code — if this law is violated? What would a
user or downstream consumer observe? What incident would be filed? What class of
bug is this?
```

Then apply bluffing detection. **On any trigger below, push once, hard:**

- *The Why echoes the Stance in declarative voice.* "Ensures all calls are routed"
  for a "calls must be routed" stance. Push: "That restates the law. What failure
  in the world does the routing prevent?"
- *Certainty markers without reasoning.* "Obviously," "just good practice," "we
  all know." Push: "Strip the certainty — what is the concrete failure?"
- *One short sentence for a major-subsystem law.* Push: "This governs [subsystem].
  One sentence usually means the failure mode hasn't been thought through. Give me
  a scenario: who hits this, what do they see, what's the cleanup?"
- *Describes a code mechanism, not a world-level failure.* "Uniform retry/sleep
  and token accounting" is a mechanism. Push: "If someone added a second retry
  implementation, does this Why tell me why to reject it? If not, the real failure
  is one level up — what is it?"

**After one probe:** if the user produces a concrete failure mode, admit the Why.
If they cannot, **defer the law**. Do not admit it with `[WEAK]` — the guide is
explicit that a weak law is worse than no law. Replace the law body with:

```
[DEFERRED — needs incident or concrete failure example]
```

Tell the user: "Come back after the next incident or design review that makes this
concrete. Right now the reasoning doesn't exist yet." Move to the next debate.

**Rejected Alternative.** From the debate's "rejected" field, now sharpened by
challenger feedback. Must name a specific design, not a generic "other approach."
One sentence on why it lost. If missing, admit with `[NEEDS REJECTED-ALT]` marker
and a `[DRAFT]` prefix on the law heading.

**Anti-pattern.** Ask:

```
Give me the specific thing the code would do if this law were violated. Not "bad X"
— the concrete shape of the violation. One file? One function call? One schema
shape?
```

If the user can only produce vague anti-patterns, the *law* is not specific
enough — go back and sharpen the Stance. If after sharpening the user still cannot
produce a concrete violation, admit with `[NEEDS ANTI-PATTERN]` and `[DRAFT]`.

**Scope.** Optional. Ask: "Is this repo-wide, or does it govern a specific
subsystem or boundary?" Omit the field entirely if truly repo-wide and no
carve-outs will ever apply. Do not invent a scope to fill a blank.

**Detector.** Optional. If the anti-pattern maps cleanly to a grep pattern or file
glob, capture it. If not, omit — a law without a detector is still valid.

### Marker grammar (apply exactly)

- `[DRAFT]` — prefix on the law heading when any element is a marker.
- `[NEEDS WHY]`, `[NEEDS REJECTED-ALT]`, `[NEEDS ANTI-PATTERN]` — replace the
  missing element's body.
- `[DEFERRED — <reason>]` — replaces the *entire law body* (stance kept in
  heading for reference).
- `[UNCHALLENGED]` — suffix on the heading when the challenger pass did not
  cover this law. Should not occur after Phase 4 in normal setup flow; defined
  here for safety if a law is added after Phase 4.

### Cap enforcement

Target: 3–7 laws. Hard cap: 10.

Track a running count as you draft. **Deferred laws count toward the cap** — a
`[DEFERRED]` entry occupies a slot. The cap exists to force prioritization;
parking weak laws as deferred without counting them would silently bypass it.

When the count reaches 10 and a debate is still waiting: **stop drafting and
force the prioritization conversation.** Ask
the user:

```
You have 10 laws drafted and [N] debates remaining. The cap is 10. For each
remaining debate, you have three options: (a) demote an earlier law to CLAUDE.md
and promote this one, (b) demote this debate to CLAUDE.md, (c) defer this debate
to a later session. Pick one per debate.
```

Do not admit law 11. The cap is load-bearing — every invariant you admit is a
commitment to enforce absolutely, and 11+ means enforcement becomes selective in
practice.

### Exit condition

Every surviving debate has been walked. Each produced either an admitted law (with
or without markers) or a `[DEFERRED — …]` entry. Total admitted laws is between 3
and 10. `CLAUDE.md candidates` list is up to date with demotions.

---

## Phase 6 — Corollaries

After all laws are drafted, ask:

```
What must be true for these laws to hold, even if it doesn't follow from any single
law? What consequences emerge when the laws interact that are worth stating
explicitly so someone doesn't reinvent them?
```

Write corollaries as derived statements, labeled clearly. They **do not count
toward the 10-law cap.** Their authority derives from the laws they follow from,
not from being independently load-bearing.

Do not fish for corollaries. If the user produces none, write none. An empty
Corollaries section is acceptable.

---

## Phase 7 — Precedence ordering

Order the admitted laws from most to least fundamental. Ask the user:

```
When two of these laws could conflict — when a proposed change would keep one but
violate another — which wins? Order them from most fundamental (wins every
conflict) to least (yields to everything above it).
```

Force pairwise resolution for any pair the user hedges on. "They don't conflict"
is not an answer — ask them to construct the hypothetical. The ordering is a
statement of what matters more; it must be intentional.

Deferred laws do not participate in the ordering but keep their drafted numbers
so future refinement runs can resume cleanly.

---

## Phase 8 — Review heuristic

Write the review heuristic as ordered questions matching the law order:

```
- Does this change keep Law 1 ([short name])?
- Does this change keep Law 2 ([short name])?
- ...
```

Append the instruction verbatim:

```
If any answer is "no" or "unclear" — the feature needs redesign, not a carve-out.
```

Not a carve-out. The instruction is load-bearing.

---

## Phase 9 — Emit

Write three things (or four — see below):

### 1. `CONSTITUTION.md`

Follow the schema in `commands/refine-constitution/constitution-template.md`.
Required sections, in order: Thesis, Laws (ordered by precedence, numbered,
deferred laws included in their marker form), Rejected Alternatives, Corollaries,
Review Heuristic.

Laws carry their markers per the grammar above.

### 2. `CONSTITUTION.mini.md` (conditional)

After writing `CONSTITUTION.md`, check whether it is complete (zero markers, all
required sections present, 3–10 laws each with all four required elements).

- **If complete:** generate `CONSTITUTION.mini.md` per the mini schema in
  `commands/refine-constitution/constitution-template.md`. This is the agent
  injection target — keep it under ~400 words.
- **If not complete (markers remain):** skip mini generation. Do not write or
  update `CONSTITUTION.mini.md`. If an existing mini file is present from a prior
  run, delete it to prevent stale state.

### 3. `CONSTITUTION.research.md`

The cached research findings from Phase 1, unmodified. Refinement and amendment
runs will read from this file.

### 4. Session summary (printed to user, not written to file)

Five lines:

```
Laws admitted:         <count> (of which <draft-count> carry [DRAFT] markers)
Laws deferred:         <count> — [DEFERRED — …] entries in the constitution
CLAUDE.md candidates:  <count> — surfaced below for you to move into CLAUDE.md
Markers remaining:     <list of marker types still present, e.g. "2x [NEEDS WHY]">
Next run will enter:   refinement mode (markers present) | amendment mode (no markers)
```

Then list the `CLAUDE.md candidates` with one-line rationales, so the user can
copy them into `CLAUDE.md` in a separate pass.

---

## Closing rules

- Do not announce completion if any `[DEFERRED]` law has no capturing reason, or
  any `[DRAFT]` law has no marker identifying the missing element. The refinement
  subskill relies on the marker grammar being machine-parseable.
- Do not admit weak laws. Defer instead. A weak law is worse than no law.
- Do not offer to "flesh it out later for you." The interview is irreducible;
  fleshing requires the author. Refinement mode exists for exactly this reason —
  tell the user the deferred laws will wait there until they bring evidence.
