---
version: 1.0.0
---

# Refine Constitution

## Purpose

Produce and maintain a repo-root `constitution.md` holding the project's **load-bearing
invariants** — principles whose *reasoning* must survive into every future refinement
pass so that `refine-epic` and `refine-issue` can delegate a slice of intent verification
to the constitution instead of re-eliciting it from the author each time.

A constitution entry is not:
- a coding convention (those go in `CLAUDE.md`),
- a one-off architectural decision (those are ADRs or epic intent docs),
- an aspirational principle without teeth,
- or a rule without a *why* (rules without reasoning cannot guide novel judgment).

A constitution entry **is**: a named invariant + the reasoning behind it + at least one
concrete anti-pattern that would violate it. The anti-pattern is what makes the
invariant *checkable* during downstream refinement rather than only quotable.

**The constitution is forward-looking as well as backward-looking.** Invariants can be
declared proactively at project start ("server owns all state — I'm building it that way
from day one"), extracted from existing code and history, or added after an incident
reveals an unwritten principle. All three entry paths use the same schema and the same
admission test.

The core failure this skill prevents: agents (and humans) shipping work that violates
a load-bearing principle because no document existed for the refinement pass to check
against.

**This skill never writes source code and never opens PRs.** Its only output is
`constitution.md` at repo root. It does not edit `refine-epic.md` or `refine-issue.md` —
wiring those to read `constitution.md` is a separate one-time manual change, described
under "Wiring" below.

---

## Args

`/refine-constitution [seed]`

- `seed`: optional. One of:
  - A quoted free-form invariant description (`"all state lives on the server"`) —
    skips evidence/drift passes and goes straight to interview for the one proposed
    invariant.
  - Omitted — full flow: evidence pass (if codebase available) + drift pass (if
    history available) + interview.

Mode is auto-detected, not passed as a flag:
- `constitution.md` absent at repo root → **init** (building from scratch).
- `constitution.md` present at repo root → **amend** (add/revise/retire invariants).

There is no separate `audit` mode. Git log is the history. Staleness is surfaced
passively by downstream skills (`refine-epic` / `refine-issue` print a nudge when an
invariant's cited evidence has moved or been deleted).

---

## Setup

### Repo detection

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
```

If `GIT_ROOT` is empty, fall back to interview-only mode: no evidence or drift pass,
every invariant tagged `[UNVERIFIED — no codebase]`. Output goes to
`/tmp/constitution.md` and the user is told to copy it into the repo root.

### Existing constitution

```bash
test -f "$GIT_ROOT/constitution.md" && echo "EXISTS" || echo "MISSING"
```

If `EXISTS`, read it in full. Mode is **amend**. Display the current invariant
titles and ask:

```
Found constitution.md with N active invariants:
  I-1: <title>
  I-2: <title>
  ...

What are we doing?
  (a) add a new invariant
  (r) revise an existing invariant — specify which
  (x) retire an existing invariant — specify which
  (f) full re-interview (rare — you want to re-examine all invariants)
```

Branch into the appropriate phase. For (a) and (f), proceed through Steps 1–3. For
(r) and (x), skip to Step 2 scoped to the named invariant.

If `MISSING`, mode is **init**. Tell the user:

```
No constitution.md found. Starting init flow.

You can declare invariants proactively, or I can propose candidates from the codebase
and recent refinement history. I'll do both unless you passed a seed argument —
then I'll skip straight to interviewing about that one invariant.
```

---

## Step 1 — Candidate Generation (init and amend-add only)

Skip this step entirely if a `seed` argument was passed — the user already named the
invariant. Skip for amend-revise and amend-retire — scope is fixed to the named entry.

### 1a. Evidence pass (optional — requires codebase)

Scan the codebase for recurring patterns that suggest invariants. This pass produces
**candidates**, not conclusions. The interview confirms or rejects them.

Search targets:
- **Boundary consistency.** Do all API handlers go through one layer? Does all state
  mutation pass through one module? Grep for the obvious ingress/egress points and
  count exceptions — a pattern with few exceptions is a candidate invariant.
- **Load-bearing weirdness.** Non-obvious patterns applied consistently (e.g.,
  `async` wrappers around every DB call, custom auth middleware on every route).
  These often encode an invariant nobody wrote down.
- **Contradictions.** Where the same responsibility is implemented two different
  ways in two places, flag both — the interview must resolve which is the intended
  pattern (or admit the codebase is mid-migration and no invariant applies yet).

Cap: surface at most **15 raw candidates**. If the scan produces more, triage by
coverage (how many files match) and distinctiveness (does this already live in
`CLAUDE.md`?). A candidate duplicating something in `CLAUDE.md` is not surfaced —
conventions belong there, invariants here.

### 1b. Drift pass (optional — requires history)

Read recent refinement artifacts for moments where the author corrected an agent or
rejected a proposed approach. Each correction-with-reasoning is a candidate invariant.

Sources, in order of signal-to-noise:
1. `.agent-work/EPIC_*/intent.md` — Section 10 (Challenger Rebuttal) is especially
   high-signal. A rebuttal that pushed back on an architectural angle often encodes
   a principle.
2. `.agent-work/INTENT_*.md` — look for Hidden Assumptions the author explicitly
   volunteered.
3. Recent closed issues in the repo where the body mentions a fix that reverses an
   approach (anti-pattern retrospective).

Filter: only surface corrections with **≥2 sentences of author reasoning**. Short
corrections are usually style/scope, not principle. Do not grep PR review comments —
too noisy.

Cap: surface at most **10 drift candidates**.

### 1c. Triage

Merge evidence candidates and drift candidates. Deduplicate (two candidates pointing
at the same principle become one). Cluster by subsystem. Reject candidates that
restate a `CLAUDE.md` rule. Present to the user **at most 8–12 candidates**, each
formatted:

```
[C-3] Proposed invariant: <one-sentence imperative>
  Evidence: <file paths, or "drift from <artifact>">
  Apparent anti-pattern: <concrete violation the evidence suggests>
  Why I think this is load-bearing: <one sentence>
```

Then ask:
```
For each candidate, tell me: keep / reject / rewrite. I'll interview each "keep"
next. You can also add invariants I didn't propose.
```

If mode is init with no codebase and no history, skip this step and go straight to
Step 2 with the user declaring invariants from scratch.

---

## Step 2 — Interview (per invariant)

Run this step once per invariant being admitted, revised, or retired. Do not
parallelize across invariants — depth per entry matters more than breadth.

**For each invariant, elicit four fields:**

### Invariant statement
One imperative sentence, present tense, specific.

Prompt:
```
State the invariant in one sentence. Imperative voice. Specific about what it
governs — "all state lives on the server" is better than "good state management."
```

### Why
1–3 sentences. The reasoning that lets a future agent judge an edge case this
invariant didn't explicitly cover.

Prompt (forward-looking invariants):
```
Why is this invariant load-bearing? What's the failure mode you're preventing, or
the property you're preserving? A future agent will use this reasoning to judge
edge cases the invariant doesn't explicitly cover — so give me enough that someone
who didn't write it can apply it to a novel situation.
```

Prompt (backward-looking invariants — evidence or drift surfaced them):
```
The codebase/history suggests this principle is already in force. Why? If you can
name a concrete PR, issue, or incident where violating it cost you, cite it — that
makes this invariant bulletproof. If there's no specific incident and it's a
principle you've held from the start, describe the feared failure mode instead.
```

**Bluffing detection** (adapted from refine-epic Sub-phase 4): if the Why arrives
in under 15 seconds, echoes the invariant statement verbatim, or contains certainty
markers without reasoning ("obviously", "we all know"), push back:

```
That's too close to restating the invariant. Give me the reasoning — what's the
specific failure mode, or the tradeoff this resolves? If you cannot name one, this
invariant is not load-bearing yet and I'll skip admitting it.
```

If the author still cannot produce a concrete Why after one probe, **reject the
invariant**. Do not admit with a `[WEAK]` tag. Tell the author to come back when a
concrete reason surfaces — often the next incident provides it.

### Anti-patterns (at least one, concrete)
The shape of violation. This is what makes the invariant checkable.

Prompt:
```
Give me at least one concrete anti-pattern — a specific thing the code would do if
it violated this invariant. "Client holds mutable state that diverges from server
on optimistic update" is a good anti-pattern. "Bad state management" is not.

If you can, name more than one. Each anti-pattern is a hook refine-issue can
check against.
```

No anti-patterns → reject the invariant. This is the hardest filter and the most
important — anti-patterns are what separates a principle from a vibe.

### Detector (optional, per anti-pattern)
A hint that downstream skills can use to mechanically flag candidate violations
before the user confirms them.

Prompt:
```
(Optional) For each anti-pattern, is there a grep pattern, file glob, or AST
signature that would match code exhibiting it? Something rough is fine — the goal
is to give refine-issue a starting point for flagging suspect changes, not to
write a linter.

If it's genuinely not grep-able (requires human judgment to detect), say so and
I'll mark it "interview-only."
```

Detectors are optional. An invariant with no detectors is still admitted — it's
just checked via reasoning-in-interview rather than pre-flagged by pattern match.

---

## Step 3 — Write `constitution.md`

Write to `$GIT_ROOT/constitution.md` (or `/tmp/constitution.md` with a warning if no
git root).

### Schema

```markdown
# Project Constitution

*Load-bearing invariants. Each entry has a Why and at least one concrete
anti-pattern — entries without both are not admitted. Cap: 10 active invariants.*

*Downstream skills (`refine-epic`, `refine-issue`) read this file and surface
invariants that apply to proposed work. When in conflict, earlier-numbered
invariants take precedence over later ones.*

---

## I-1: <Short imperative title>

**Invariant:** <One sentence. Imperative. Specific.>

**Severity:** ABSOLUTE | STRONG
<!-- ABSOLUTE = violation requires undoing the work. STRONG = violation requires
     a documented override in the epic/issue intent doc. -->

**Why:** <1–3 sentences. Reasoning that lets an agent judge novel edge cases.
Cite an incident, PR, or issue if one exists.>

**Anti-patterns:**
- <Concrete violation 1.>
  - *Detector:* `<grep pattern or glob>` | `interview-only`
- <Concrete violation 2, if any.>
  - *Detector:* `<...>` | `interview-only`

**Scope:** <Subsystems or file globs this governs. Omit if repo-wide.>

---

## I-2: <...>

[...]

---

## Retired

<!-- Retired invariants are removed from the Active section above. The retirement
     itself is tracked via git log — this section only exists if the author wants
     a human-readable note about a specific retirement ("I-4 retired 2026-03-15
     when we migrated off Postgres"). Omit the section entirely if unused. -->
```

### Cap enforcement

If admitting a new invariant would push the active count above 10, stop and
prompt:

```
Admitting this would make 11 active invariants. The cap is 10 — the goal is that
every invariant is memorable and load-bearing enough to be worth enforcing.

Which existing invariant should be retired to make room? Or reconsider whether
this new one is truly load-bearing vs. a convention that belongs in CLAUDE.md.
```

Do not admit above the cap.

### Conflict resolution

Earlier-numbered invariants beat later ones in a conflict. This is stated in the
preamble of the output file. The author orders them. Renumbering on amendment is
allowed and expected.

### Git commit

After writing, tell the user:

```
constitution.md written with N active invariants.

Commit with:
  git add constitution.md && git commit -m "<describe the change>"

I have not committed for you — review the diff first, especially if this is an
amendment.
```

Do not auto-commit. The author reviews the diff before anything ships.

---

## Wiring (one-time, manual)

**This skill does not edit `refine-epic.md` or `refine-issue.md`.** Cross-skill
editing is fragile and inverts the ownership model.

On the first run in init mode, after writing `constitution.md`, print this
reminder to the user:

```
constitution.md is now at your repo root, but downstream skills don't read it yet.
One-time wiring — edit these two files manually:

1. commands/refine-epic.md — context bootstrap (around line 217):
   Add: "If constitution.md exists at $GIT_ROOT, read it in full. Its invariants
   are load-bearing; Challenger 3 (Shape / Architecture) must cite any invariant
   the proposed epic appears to violate and name the specific anti-pattern."

2. commands/refine-issue.md — Spec agent context bootstrap (around line 395):
   Add: "If constitution.md exists at $GIT_ROOT, read it in full. Before
   finalizing the refined spec, check the proposed surface area against each
   invariant's anti-patterns (including any grep/glob detectors) and flag
   candidate violations in the spec's Hidden Assumptions section."

After wiring, re-copy those two files into ~/.claude/commands/ per
CLAUDE.md's 'Modifying Global Config' instruction.
```

On amend runs, skip this reminder — wiring already exists.

---

## Staleness (passive, no audit mode)

This skill does not run audits. Staleness surfaces through downstream work:

- When `refine-epic` reads `constitution.md` during its Sub-phase 1 scan, it
  cross-checks any file paths cited in invariants (in Scope fields or Why
  citations). If a cited path no longer exists or has moved, the epic's intent
  doc flags it as `[CONSTITUTION-DRIFT]` and prompts the author to reaffirm,
  revise, or retire the invariant before decomposition proceeds.
- `git log constitution.md` is the authoritative history. No `Added` or
  `Last reaffirmed` timestamps in the file itself — the git log is richer and
  cannot silently fall out of sync.

If the author wants to re-examine an invariant proactively, they run
`/refine-constitution` and pick (r) revise or (x) retire from the existing-file
menu.

---

## Constraints

- Never write or modify source files other than `$GIT_ROOT/constitution.md`.
- Never edit `refine-epic.md`, `refine-issue.md`, or any other skill file.
- Never open branches, commits, or PRs. The author commits `constitution.md`
  themselves after reviewing the diff.
- An invariant without both a concrete Why and at least one concrete anti-pattern
  is rejected, not admitted. No `[WEAK]` or `[TBD]` tags.
- Hard cap of 10 active invariants. The 11th requires demoting one first — this
  forces the prioritization conversation rather than letting the document bloat.
- When there is no codebase and no history, the skill still runs in
  interview-only mode. Forward-looking invariants are first-class — the admission
  test (Why + anti-pattern) does not require a past incident, only concrete
  reasoning about a feared failure mode.
- If the author cannot produce a concrete Why or anti-pattern after one probe,
  the invariant is rejected for this session. Tell the author to come back when
  the reasoning is concrete.
