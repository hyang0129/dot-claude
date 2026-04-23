# Constitution Guide

A project constitution is a short document of load-bearing invariants — principles
whose *reasoning* must survive into every refinement pass, every PR review, and every
agent-assisted decomposition.

This guide defines what makes a constitution good, what makes one fail, and the
generative process for producing one from scratch or auditing an existing one.

---

## What a constitution is for

Downstream tools (`refine-epic`, `refine-issue`) need something to check proposed
work against that is more authoritative than general engineering taste and more
concise than the full codebase history. A constitution fills that slot. It does
*not* replace:

- `CLAUDE.md` — coding conventions, tooling preferences, repo-specific hygiene
- ADRs — one-off decisions with context and date
- Epic intent docs — per-feature rationale

A constitution entry is an invariant that must hold across *all* work, always, not
just in the context of one decision. If you cannot imagine a future PR that would
need to check against it, it belongs somewhere else.

---

## The load-bearing test

**A law is load-bearing if and only if the opposite stance is also defensible for a
different project with different priorities.**

This is the central test. Apply it to every proposed invariant before admitting it.

If no reasonable project would take the opposite stance, the invariant is a
convention — obvious to anyone doing this kind of work, not requiring articulation.
Belongs in `CLAUDE.md`, not here.

If a different team, with different constraints, could *reasonably* pick the opposite
stance, then your invariant resolves a live tradeoff. The Why is forced to explain
*why this project picks this side*, not just what the code happens to do. That
reasoning is what lets a future agent judge edge cases the invariant didn't explicitly
cover.

### Worked example

**Candidate invariant:** Only surface definite edges in the call graph; never surface
uncertain ones.

Opposite stance: surface uncertain edges with a confidence score, because approximate
information is still useful and callers can weight it.

Is the opposite defensible? Yes — Sourcegraph, semgrep at certain confidence
thresholds, and most "find usages" IDE features work exactly this way. Different
project, different tradeoff.

Therefore this is load-bearing. The Why must explain why *this* project picks
definite-only. Here is a Why that passes:

> An agent that trusts a wrong edge wastes more time than one that falls back to grep.
> Agents round 0.7 to 1.0 in practice — they don't calibrate to edge confidence.
> A graph of definite edges with silent false negatives is strictly more trustworthy
> for agent consumption than a graph of scored edges the agent will treat as certain.

Now compare to this candidate invariant: "Unit tests must be deterministic."

Opposite stance: non-deterministic unit tests are acceptable.

Is the opposite defensible? No serious project takes that stance. This is a
convention, not a law. It fails the test.

---

## Opposite-stance counter-constitution sketch

To make the test visceral: here is a valid constitution that takes the *opposite*
stance on call-graph edges:

> **Law 1 (counter): Surface all reachable edges, including uncertain ones, at scored
> confidence. Callers own the threshold.**
>
> Why: This project's users are IDE integrators doing "find all usages across
> frameworks" — missing a real edge (false negative) is worse than surfacing a
> spurious one. Callers know their threshold; we supply the raw signal. Silent false
> negatives here are silent data loss from the user's perspective.
>
> Anti-pattern: dropping a `getattr`-dispatched call from the graph because we
> couldn't statically resolve it, without recording it in any form.

Both constitutions are internally consistent. Both have valid Whys. The difference
is the project's theory of who gets hurt more: the agent that trusts wrong edges
(definite-only wins) vs. the developer whose usage goes undetected (scored wins).
The constitution must state which theory applies here and why.

---

## Anatomy of a good law

A law needs five things:

**1. Stance** — one imperative sentence, present tense, specific. Not "good state
management." Not "handle errors properly." "All mutable state lives on the server;
clients are read-only projections."

**2. Why** — 1–3 sentences. Describes *failure in the world* if the law is
violated, not failure in the code. The failure mode must be concrete enough that a
future agent can apply it to a situation the law didn't explicitly cover.

Bad Why (describes the code): "Ensures consistent locking behavior across all
callers."

Good Why (describes the world): "When two clients hold divergent state, any
action taken by one produces a conflict the other can't detect until the next
sync — resulting in silent data loss that only surfaces at export time."

**3. Rejected alternative — why it lost** — the specific other design the author
considered and why this project doesn't take it. This is the second hardest thing
to elicit and the thing most likely to be missing. It is also what makes the Why
non-obvious: without naming what was rejected, the Why reads as describing the
chosen approach, not defending it.

**4. Anti-pattern** — a concrete thing the code would do if the law were violated.
"Client holds mutable state that diverges from server on optimistic update" is an
anti-pattern. "Bad state management" is not. The anti-pattern is what makes the
law *checkable* during a PR review or agent refinement pass rather than merely
quotable.

**5. Scope** — what subsystems or boundaries this law governs. Omit if it is
truly repo-wide and no carve-outs will ever apply.

The **Detector** (a grep pattern or file glob that matches candidate violations) is
optional. A law without a detector is still valid — some laws can only be checked by
reasoning about intent, not by pattern matching.

---

## Anatomy of a good constitution

### Purpose / thesis (required at top)

One paragraph stating what this project *is* as a positioning claim, not a
description. "An MCP graph server that lets Claude answer code-structure questions
faster and more reliably than repeated grep + read. The graph is the product; MCP
is just the delivery surface."

This is harder than it sounds. "A graph server that exposes a call graph via MCP"
is a description. The good version takes a side — it says what *matters* (the graph,
not the protocol). The thesis determines which laws are load-bearing: a law that
protects the graph at the cost of the protocol is correct; a law that does the
opposite needs to justify why.

### Laws (3–7, hard cap 10)

The hard cap is not arbitrary. If every invariant is worth enforcing absolutely,
then having 15 means 5 will be skipped in practice. The cap forces the
prioritization conversation: when law 11 is proposed, one existing law must be
demoted to convention.

Laws are ordered by precedence. When two laws conflict, the earlier one wins. The
ordering is a statement of what matters more — it should be intentional, not
chronological.

### Rejected alternatives (required)

A section listing designs the project *explicitly does not do*, with one sentence
per item explaining why. This is not the same as the anti-patterns inside each law.
This section covers whole design choices that were evaluated and rejected:
confidence-scored edges, lazy rebuild, filesystem watchers, pickle caches. It
prevents thrash from well-meaning contributors who propose something the author
already considered.

### Corollaries (derived, not independent)

Consequences of the laws that are worth stating explicitly because they catch common
mistakes, but which don't require separate justification. They follow logically from
the laws. Labeling them corollaries keeps the law count honest and signals that
their authority derives from the law they follow from, not from being independently
load-bearing.

### Review heuristic (optional but high-value)

An ordered checklist for PR review, framed as questions. "Does this keep law 1?
Does it keep law 2?" with the instruction: if any answer is "no or unclear, the
feature needs redesign, not a carve-out." The ordered heuristic makes the
constitution actionable in review, not just in planning.

---

## Anti-patterns in constitutions

### Posthoc mechanical-description Why

The most common failure. The Why describes what the code does, not what breaks in
the world if you stop doing it.

> [C-1] All LLM calls must route through `call_llm`.
> Why: uniform retry/sleep, parse-error recovery, and token accounting.

That Why is a docstring for the wrapper function. It passes the smell test at first
read but fails the edge-case test: if someone proposes a new LLM call that has its
own retry logic, this Why doesn't tell you whether to allow it. The real Why would
explain why a second retry implementation produces the world-level failure
(split accounting, retry storms during incidents, inability to hot-swap providers).
That reasoning is what a reviewer needs. And crucially: that reasoning does *not*
come from reading the code. It lives in the author's head.

This is the posthoc failure mode. Scanning the codebase for the wrapper and
inferring the Why from its features produces a mechanical-description Why every
time. The invariant *looks* constituted but it's hollow.

### Laws that are conventions in disguise

A law that fails the opposite-stance test. "All imports are explicit, no star
imports." Nobody takes the opposite stance in a serious project. This is a
convention. Put it in `CLAUDE.md`, or a linter config, not the constitution.

### Missing rejected alternative

A law with a Why but no statement of what was considered and rejected. The Why then
reads as justifying the chosen approach in a vacuum, not as resolving a tradeoff.
This makes it hard for a future agent to judge whether a novel proposal violates the
spirit of the law or just its letter.

### Scope creep above the cap

A 14-invariant constitution means nobody has internalized all 14. Enforcement becomes
selective in practice — the laws that get enforced are the ones team members happen
to remember. The cap (10 at most) exists so the author is forced to decide what is
*actually* load-bearing vs. what is just useful. The decision is valuable independent
of what it produces.

---

## Why the interview is irreducible

An agent can scan a codebase and surface candidates. It cannot produce a good
constitution without the author, for three reasons:

**Rejected alternatives are not in the code.** The code only shows what was built.
The designs that were evaluated and dropped exist only in the author's memory, old
conversations, or incident postmortems — and often nowhere at all. "Confidence-scored
edges explicitly rejected for v1" is not in `analyzer.py`.

**Scope/ownership decisions are political.** "Deciding *when* verify runs… that's
the hosting project's problem, not ours" is a decision about what the author refuses
to own. It's a stance about responsibility boundaries that no amount of file-reading
can reconstruct.

**The thesis is a positioning claim, not a description.** "The graph is the product;
MCP is just the delivery surface" — a scanner reading the repo would likely invert
this, since the MCP interface is what's exposed. The thesis comes from the author's
theory of value, not from the code.

The interview is not just eliciting what the author knows. It is *forcing articulation
of things the author has never articulated*. The Why for a good law often does not
exist until the interview makes the author produce it. This is irreducible. A fully
automated pass produces the posthoc mechanical-description flavor above every time —
it generates descriptions dressed as principles.

---

## Process — how to produce a good constitution

Work backwards from what the good example required. Each step is a question to ask
the author.

### Step 0 — Extract the thesis

"What is this project, stated as a positioning claim? Not what it does — what is the
product, and what is the delivery surface?"

The author should name what matters and what is instrumental. If they can't
distinguish the two, start there — the laws won't cohere until the thesis is clear.

### Step 1 — Elicit settled debates, not rules

"What did you almost do but rejected? What designs did you evaluate seriously and
decide against?"

This is the primary source of laws. Every rejected alternative is a potential law
stated from the other side. Collect a list of settled debates before drafting any
law. The format for each: what was the choice, what was the alternative, why did
this project pick this side?

Do not start with "what are your rules." Rules-first produces conventions.
Debates-first produces laws.

### Step 2 — Apply the opposite-stance test to each debate

For each settled debate, verify the opposite stance is defensible for some other
project. If it's not, the debate was not a real tradeoff — discard it or move it to
`CLAUDE.md`.

If the opposite is defensible, the debate yields a law. The Why must explicitly name
the opposing stance and explain why this project rejected it.

### Step 3 — Write the Why as a failure-in-the-world

For each law, ask: "What breaks in the world — not in the code — if this law is
violated?"

Reject any Why that describes a code mechanism rather than a world-level failure.
Push: "What would a user or downstream consumer observe? What incident would be filed?
What kind of bug is this?" A Why that cannot answer that is describing code, not
reasoning.

### Step 4 — Name the anti-patterns

"Give me the specific thing the code would do if this law were violated. Not 'bad X'
— the concrete shape of the violation."

At least one anti-pattern per law is required. The anti-pattern is the hook for
downstream checking. If the author can only produce vague anti-patterns, the law is
not specific enough to be checkable — revise the invariant statement.

### Step 5 — Draw the out-of-scope boundary

"What is explicitly not this project's job? What are you refusing to own?"

This is the rejected-alternatives section. Collect all designs that were considered
and rejected, plus all responsibilities the author has decided to push to callers or
downstream systems. Write them as one sentence each: what + why it was rejected or
delegated.

### Step 6 — Derive corollaries last

After the laws are written, ask: "What must be true for these laws to hold, even
if it doesn't follow from any single law?"

Corollaries emerge naturally when laws interact. Write them after the laws, label
them as derived, and do not let them dilute the law count.

### Step 7 — Order by precedence and write the review heuristic

Order the laws from most to least fundamental. Ask the author to resolve any
conflicts. Write the review heuristic as ordered questions, with the instruction
that "no or unclear" means redesign, not carve-out.

---

## Bluffing detection

At every Why, watch for:

- The Why echoes the invariant statement in declarative voice ("ensures that all
  calls are routed" as the Why for "all calls must be routed").
- The Why uses certainty markers without reasoning ("obviously", "we all know",
  "it's just good practice").
- The Why arrives in one short sentence for a law that governs a major subsystem.
  One sentence usually means the author hasn't actually thought through the failure
  mode.

On any of these, push: "What breaks in the world if this law is violated? Can you
name a specific incident, or describe the class of bugs this prevents?" If the author
cannot produce a concrete failure mode after one probe, reject the law for this
session. The reasoning does not exist yet. Tell the author to come back after the
next incident or design review that makes the principle concrete.

Do not admit a law with a weak Why and tag it `[WEAK]`. A weak law is worse than
no law — it occupies one of the 10 slots and gives future agents the impression of
a justified constraint when none exists.
