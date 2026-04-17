# Refine Epic

## Purpose

Converts a vague epic or multi-issue body of work into a decomposition plan: an ordered set of
independently shippable child issues, each with its own behavioral spec, plus an index document
recording the dependency graph, integration seams, and risk register.

The core failure this command prevents: epics that are assigned to agents (or humans) without
a clear cut of the work, producing parallel PRs that conflict at integration seams, slices that
cannot be tested independently, or child issues that duplicate each other or miss entire
subsystems the author assumed were implicit.

**This command never writes source code and never opens PRs.**
Its outputs are: an epic index document, per-slice spec files, and optionally a set of GitHub
child issues (after explicit user approval).

The natural pipeline after this command:
`/refine-epic` → user approves decomposition → child issues created → `/refine-issue` per child
(optional deepening) → `/resolve-issue` per child.

---

## Args

`/refine-epic <epic>`

- `epic`: required. One of:
  - GitHub issue number (e.g. `147`)
  - Full GitHub issue URL (e.g. `https://github.com/org/repo/issues/147`)
  - `owner/repo#number` reference (e.g. `acme/api#147`)
  - Quoted free-form description (e.g. `"migrate all storage backends to S3"`)

Input detection:
- Matches `^[\w.-]+/[\w.-]+#\d+$` → extract `owner/repo` and issue number directly.
- Matches `^\d+$` → bare issue number; repo must be detected (see Setup).
- Matches `^https?://github\.com/` → extract `owner/repo` and issue number from URL.
- Otherwise → free-form description.

---

## Setup

### Repo detection (issue reference mode only)

If `epic` is `owner/repo#number` or a full URL, extract `owner/repo` directly — no detection or
confirmation needed. Set `REPO=<owner/repo>` and proceed.

If `epic` is a bare number, detect the repo:
```bash
git remote -v
gh repo view --json nameWithOwner
```

Determine `owner/repo`:
- If exactly one GitHub remote, use it.
- If multiple remotes, prefer `upstream` (fork workflow), otherwise `origin`.
- If no remote can be found, check conversation context for a repo name.

**Confirm only when the repo was auto-detected** (i.e., `epic` was a bare number):
```
Repo detected: <owner/repo> (from <source>)

Proceed with epic #<number> in <owner/repo>? [yes / no / different-repo]
```

Wait for the user to confirm or correct. Then set `REPO=<owner/repo>`.

### Fetch the epic (issue reference mode only)

```bash
gh issue view <number> --repo <REPO> --json number,title,body,labels,comments
```

Also fetch any issues already linked as children so the Decomposer does not re-propose them:

```bash
gh issue list --repo <REPO> \
  --search "\"#<number>\" in:body" \
  --json number,title,state \
  --limit 50
```

If `gh` is unavailable, stop and tell the user to install the GitHub CLI.

### Git root detection

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$GIT_ROOT" ]; then
  for candidate in /workspaces/* "$HOME"/repos/* "$HOME"/repo/* "$HOME"/projects/* "$HOME"/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
fi
```

If `GIT_ROOT` is set, verify the scratch directory exists before spawning anything:
```bash
test -d "$GIT_ROOT/.claude-work" && echo "EXISTS" || echo "MISSING"
```
If `MISSING`, stop and tell the user:
```
.claude-work/ not found in this repo. Please run:
  mkdir -p <GIT_ROOT>/.claude-work && echo '.claude-work/' >> <GIT_ROOT>/.git/info/exclude
Then re-run this command.
```
Do not proceed until the directory exists.

If `GIT_ROOT` is empty, all output goes to `/tmp/EPIC_<slug>-<number>/`. Mark all surface area
as `[UNVERIFIED — no codebase]`. Report this path to the user in the final summary.

### Output directory

Set `EPIC_DIR`:
- With git root: `$GIT_ROOT/.claude-work/EPIC_<slug>-<number>/`
- Without git root: `/tmp/EPIC_<slug>-<number>/`

where `<slug>` is a 3–4 word kebab-case summary of the epic title or description, and `<number>`
is the issue number (or a short hash for free-form).

---

## Step 1 — Resume Check

Before spawning anything, check whether a prior decomposition exists:

```bash
test -d "$EPIC_DIR" && echo "EXISTS" || echo "MISSING"
```

If the directory exists, list its contents and ask:
```
Found existing epic work: .claude-work/EPIC_<slug>-<number>/
  intent.md          (present / missing)
  index.md           (present / missing)
  child-1-<slug>.md
  child-2-<slug>.md
  ...

Resume options:
  (r) resume decomposition — skip Clarifier, go straight to Decomposer (requires intent.md)
  (i) re-run intent validation only — redo Clarifier, keep existing child drafts
  (s) start over — delete everything and begin from Step 2
```

- **Resume (r)**: if `intent.md` is present, skip Step 2 (Clarifier) and spawn the Decomposer
  directly. If `intent.md` is missing, treat as start-over and warn the user.
  If `index.md` is also present, skip to Step 4 (present decomposition) — do not re-spawn
  the Decomposer agent.
- **Re-run intent (i)**: delete `intent.md` only, re-run Step 2, keep all child draft files.
- **Start over (s)**: delete the directory contents and continue to Step 2.
- **Free-form mode** (no issue number): skip this check entirely.

---

## Step 2 — Intent Validation (Interactive)

**This step is the highest-leverage point in the entire workflow. A missed intent signal here
creates compounding misalignment across every child issue. Over-clarification is always
preferable to under-clarification — there is no such thing as too much WHY.**

Before spawning the Clarifier, tell the user:

```
Starting intent validation. The Clarifier will ask 2–3 rounds of questions about the WHY
behind this epic. There are no wrong answers — the goal is to surface your reasoning so
that agents can resolve implementation decisions on child issues without escalating back
to you.

This step is intentionally interactive. Expect 2–3 back-and-forth rounds before the
intent document is written. Your answers here become the source of truth for every child
issue that follows.
```

**Run the Clarifier process directly in this session** — do NOT spawn a subagent for this step.
The Clarifier requires multiple interactive Q&A rounds with the real user; a subagent cannot
do that (it returns a single result). You are the Clarifier for Step 2.

### Clarifier process

Role: elicit intent, scan for calibration signals, produce the epic intent document. No source
file writes. No branch, commit, or PR creation. One output file: `EPIC_DIR/intent.md`.

**Over-clarification principle:** When in doubt about whether to ask a follow-up question,
ask it. A question that turns out obvious is cheap. A missed intent signal that surfaces as
a child-issue implementation disagreement is not. The caps (4 batch-1 questions, 3 batch-2
questions) are maximums for any single round, not caps on total questions across rounds. If
batch-2 answers raise new questions, ask another round. If the user's answer to any question
partially resolves the ambiguity but leaves a residual, probe the residual. The exit condition
for the Clarifier is not "questions asked" — it is "epic intent is fully validated." Do not
treat the user seeming busy or terse as a reason to skip questions or stop early.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions)
   if they exist.
2. If `GIT_ROOT` is unavailable, skip Sub-phase 2 entirely. Mark the Inferences From Existing
   Code section `SKIPPED — no codebase` and proceed to Sub-phase 3 with batch-2 questions omitted.

---

**Sub-phase 1 — Pre-scan Elicitation**

Before asking any questions, read the epic body in full and determine which of the four
batch-1 questions are already answered. A question is answered only if the epic contains
both a stated position AND the reasoning behind it. If only a position is present with no
reasoning, ask the question anyway — the reasoning is what matters, not the stance.
Question 1 (feared failure) is never skipped regardless of what the epic body contains.

Ask up to four questions, in this order. Each question targets reasoning, not choices —
phrase them to surface the WHY, not to confirm a what.

**Q1 (never skip):** "If every line of code described in this epic shipped and worked
correctly, what outcome would still make this a failure? Describe the scenario that would
make you say 'we built the wrong thing.'"

**Q2:** "What is the primary tradeoff you've already resolved in your head while writing
this? For example: speed vs. correctness, isolation vs. sharing, flexibility vs. simplicity.
Name the axis and tell me which side you're on and why."

**Q3:** "What are the hard constraints that every slice of this work must respect — things
that, if violated, would require undoing the work rather than patching it?"

**Q4:** "What did you consider and rule out before writing this epic? Name the alternatives
and the reason each was rejected."

Present all applicable questions together in a single block — do not send them one at a time.
Wait for the user's response before proceeding. If the answers introduce new ambiguity or
partially resolve a question, ask a follow-up round. Continue until intent is unambiguous —
there is no fixed number of rounds.

**P0 blocker detection:** While reading the epic body and while processing the user's
batch-1 answers, watch for signals that indicate a P0 blocker: a dependency on an unresolved
external decision, a stated constraint that contradicts the epic's stated goal, or an explicit
"we haven't decided" on a question that gates the entire decomposition. If a P0 blocker is
found at any point during Sub-phase 1, halt immediately and surface it:

```
HALT — P0 blocker detected before decomposition can proceed:

<state the blocker in one sentence>

This must be resolved before the Clarifier can produce an intent document.
Please resolve it and re-run /refine-epic.
```

Do not proceed to Sub-phase 2 until the blocker is cleared.

---

**Sub-phase 2 — Lightweight Codebase Scan**

Scan the codebase for exactly three things. Do not perform any other research — full
architecture analysis, test coverage gaps, and inter-module dependency graphs are deferred
to the Decomposer's Phase B.

**Scan target 1 — Existing domain implementations.** Search for files that already implement
the epic's primary capability. Use the key nouns and verbs from the epic title and body as
search terms. The question you are answering: does this capability partially exist, and if so,
is this epic extending it or replacing it? A migration-vs-greenfield ambiguity that isn't
surfaced here will corrupt every child issue slice.

**Scan target 2 — Rejection signals.** Search for commented-out code, FIXME/TODO notes that
name alternative approaches, and dependency manifests that show a library was added then
removed. These populate the Anti-Choices section of the intent doc and the Inferences list.
Do not interpret them — surface them as evidence.

**Scan target 3 — Coarse module boundaries.** Identify which top-level packages or
directories the epic's work will touch. List them by name only — do not read their internals.
This calibrates the batch-2 questions about per-module invariants.

From the scan, produce a list of named inferences. Hard cap: 5. Prioritize inferences that
would change the shape of at least one child issue if wrong — omit cosmetic observations.
Format each inference as:

```
[INFER] <one-sentence statement of what the code evidence implies>. Confirm or correct.
```

Example: `[INFER] You are not migrating to OpenTelemetry — no collector config exists anywhere
in the repo. Confirm or correct.`

---

**Sub-phase 3 — Calibrated Ratification**

Present the inferences from Sub-phase 2 and ask 2–3 follow-up questions calibrated to what
the scan found. Do not ask questions whose answers are already unambiguous from Sub-phase 1
responses. Present everything in a single block — inferences first, then questions.

Each batch-2 question uses this template:
"I found [pattern in the code]. My inference is [interpretation of what that means for this
epic]. Is that right — and if not, what should I understand instead?"

Ask as many batch-2 questions as the scan warrants. Present them in a single block per round.
One question per round must probe the biggest architectural call visible in the scan —
specifically whether the decision is reversible: "Is this a commitment you'd need to undo
wholesale if it turned out wrong, or something you could change incrementally?" If any answer
introduces new ambiguity, continue with another round. Stop only when all inferences are
ratified and no material ambiguity remains.

**P0 contradiction detection:** If a batch-2 answer directly contradicts a batch-1 answer —
for example, the user stated in Q2 that isolation is the priority, but the codebase scan
reveals tight shared state the user is now defending — halt and surface the contradiction:

```
HALT — contradictory intent detected:

Batch-1 stated: <quote>
Codebase / batch-2 reveals: <finding>

These cannot both be true as stated. Please clarify which reflects the actual intent,
or describe how both can coexist, before the intent document is written.
```

Do not write `intent.md` until the contradiction is resolved.

---

**Produce `EPIC_DIR/intent.md`**

Write the intent document only after all three sub-phases are complete and no P0 blockers
or contradictions are outstanding. The document has eight sections. Write each section as
causal prose — no keyword bullet lists. A downstream agent reading this document must be
able to simulate the author's answer to an implementation decision that was never explicitly
raised in the epic.

```markdown
# Epic Intent: <Title>

**Epic Issue:** <org/repo>#<number> — <URL>  (omit if free-form)
**Captured:** <YYYY-MM-DD>

---

## 1. Trigger and Pain

<What is broken or missing today, written as observable symptoms. Why is this work
happening now rather than later? What will still hurt if the work is delayed?>

## 2. Feared Failure Mode

<The outcome that would make this epic a failure even if every line of code shipped
correctly. Written as a concrete scenario, not an abstract concern. This is the single
most important signal for resolving ambiguous implementation decisions.>

## 3. Decision Priors

<One paragraph per major tradeoff axis the author has already resolved. Write each
paragraph as: "We chose X over Y because Z." Include the reasoning, not just the choice.
This is the section a downstream agent reads first when facing an unasked question.>

## 4. Value Function

<A ranked list of what matters, derived from the Decision Priors and Q&A. List at most
five items. After the ranked list, write one paragraph of causal prose explaining the
dominant priority and why it outweighs the others in this specific context. The prose
handles edge cases the ranked list cannot resolve.>

## 5. Invariants

<Hard constraints that must survive every child issue. Each invariant is one sentence.
Tag each as: ABSOLUTE (violation requires undoing the work) or STRONG (violation requires
an explicit override with documented justification). Do not include preferences here —
only constraints.>

## 6. Anti-Choices

<Alternatives the author considered and rejected, with reasoning. Format each as:
"We considered <X> and rejected it because <Y>." If the rejection is conditional
(e.g., "not now, but revisit if Z"), state the condition explicitly.>

## 7. Non-Goals

<What this epic explicitly does not do. Written as falsifiable statements.
"This epic does not X" — not "we might consider X later.">

## 8. Open Questions (Author-Deferred)

<Decisions that are genuinely unresolved at the time of decomposition. For each entry:
name the decision, one sentence on why it is unresolved, and a flag:
ESCALATE — the downstream agent must surface this to the user before proceeding, or
TIMEBOX — the agent may make a reasonable call within 24h but must document its reasoning.
Leave this section empty (with the heading present) if no genuine deferrals exist.>

---

## Inferences From Existing Code

<Agent-constructed inferences from the Sub-phase 2 scan, author-ratified in Sub-phase 3.
Each entry: the [INFER] statement, then the author's response on the same line.
Example: [INFER] No OTEL collector config found — migration is not in scope here. → Confirmed.>
```

After writing `intent.md`, print the full document to the user.

If all three sub-phases completed without halting (no P0 blockers, no unresolved contradictions,
all inferences ratified), the clarification process has already verified the intent — proceed
directly to publishing and Step 3 without asking the user to review or confirm.

Only pause for a single-pass review if there are residual open questions the Clarifier could not
resolve — for example, TIMEBOX items the user did not fully address. In that case, surface the
specific gaps:

```
Intent document written. One unresolved item before I proceed:

<state the specific gap>

Clarify this and I'll post the document and start decomposition.
```

**Publish `intent.md` to GitHub** (skip only if no issue exists, i.e. free-form with no issue yet):

```bash
gh issue comment <number> --repo <REPO> --body "$(cat <<'EOF'
## Epic Intent Document (generated by /refine-epic)

<full contents of EPIC_DIR/intent.md>

---
*This document captures the author's intent before decomposition. If anything is wrong or
missing, reply with corrections before the decomposition is reviewed.*
EOF
)"
```

Report the comment URL to the user. If the input is free-form with no issue yet, skip
the GitHub post — the local file is the only copy until an issue exists.

**The GitHub epic issue is the master version of `intent.md`.** The local `EPIC_DIR/intent.md`
is a working copy only. If the user requests changes after this point, update both the local
file and post a follow-up comment on the epic issue.

The Clarifier process is now complete. Proceed to Step 3 and spawn the Decomposer.

---

## Step 3 — Decomposition (Autonomous)

**Intent is now locked. Tell the user they can step away:**

```
Intent document is finalized and posted to GitHub. Spawning the Decomposer now — this
will run autonomously and may take several minutes. Come back when you see the
decomposition summary. You don't need to stay.
```

The Decomposer runs to completion without requiring user input. Do not interrupt it with
questions, progress checks, or confirmations. The user reviews the full output in Step 4.

Spawn a **Decomposer agent** (`model: "claude-opus-4-6"`).

Pass it:
- The full epic body + comments (if issue reference mode), or the free-form description.
- The list of already-existing child issues (if any were found during Setup).
- `GIT_ROOT` (or note that codebase context is unavailable).
- `EPIC_DIR` as the output directory.
- `EPIC_DIR/intent.md` as the source of truth for author intent. The Decomposer must read
  this document before Phase A and treat it as authoritative. When any implementation
  decision conflicts with the codebase evidence found in Phase B, the Decomposer resolves
  the conflict using the reasoning in `intent.md` — specifically sections 3 (Decision Priors),
  5 (Invariants), and 2 (Feared Failure Mode) — rather than escalating.

### Decomposer agent instructions

Role: read-only research + produce decomposition plan. No file writes except documents inside
`EPIC_DIR`. No source file modifications. No branch or PR creation.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions)
   if they exist.
2. If `.codesight/CODESIGHT.md` exists at `$GIT_ROOT`, read it in full.
3. If `docs/agent_index.md` exists at `$GIT_ROOT`, read it in full.
   If not found there, glob for `**/agent_index.md` and read any match.
4. If `GIT_ROOT` is unavailable, Phase B degrades to vocabulary-only analysis — no file paths,
   no call-site counts. Mark every surface area row as `UNVERIFIED — codebase not available`
   and continue.

---

**Phase A — Understand the Epic's Scope and Decomposition Goal**

Read the epic issue body and all comments in full. Produce a private working note (not an output
file) covering:

**A1. Stated scope.** What the author literally described. Quote the key phrases.

**A2. Decomposition goal.** What the author actually needs: independently shippable slices that
each move the system toward the epic's end state. Distinguish between:
- Slices the author named explicitly
- Slices implied by the work but not mentioned
- Work mentioned that is NOT a slice (cross-cutting concerns, one-time migrations, infra
  prerequisites)

**A3. Dependency identification.** For each candidate slice, ask:
- Can this ship and deliver value without any other slice being complete?
- If no: which slice must precede it, and why?

A slice that cannot answer "yes" to the first question is not independently shippable. It must
either be merged with its dependency or flagged as a prerequisite block.

**A4. Workstream seams.** Group slices by the primary system boundary they cross (e.g. data
layer, API layer, CLI, frontend, background jobs, infra). Seams are where the decomposition
cuts — slices within a workstream are sequential; slices across workstreams may be parallel.

Do not include existing child issues (passed in from Setup) as proposed slices. Reference them
in the index doc under a "Existing Children" section.

---

**Phase B — Codebase Research (run per workstream, not per epic)**

For each workstream identified in Phase A, perform independent surface area research. Do not
collapse multiple workstreams into a single search pass.

**Required search checklist per workstream — do not skip steps:**

1. **Vocabulary grep.** Grep for the primary noun and verb from the workstream's concern.
   Record every file that matches.

2. **Entry point enumeration.** Search for all user-facing entry points relevant to this
   workstream: `**/cli*`, `**/commands*`, `**/handlers*`, `**/routes*`, `**/views*`,
   `**/server*`, `**/app*`, `**/jobs*`, `**/tasks*`, `**/workers*`, `**/settings*`,
   `**/config*`. List every match — do not filter yet.

3. **Dead integration check.** For each function or class that implements the workstream's core
   behavior: grep for its name and count call sites. If call sites ≤ 1 (defined but not called,
   or only self-referential), flag it as a suspected unwired integration — file and line number.
   Do not conclude whether it is truly dead; surface the evidence for the implementer.

4. **Integration seam detection.** Identify any file or component that multiple workstreams
   will need to modify. Flag these explicitly — they require sequencing or coordination across
   slices and must appear in the Risk Register.

5. **Test coverage probe.** Grep for the workstream's primary symbols in `**/test*` and
   `**/spec*` directories. Record which entry points have no corresponding test file match —
   these are coverage gaps the slice spec must address.

After completing all workstream searches, state explicitly:
```
Decomposition research: examined N files across M workstreams.
Integration seams identified: <list>
Coverage confidence: [high / medium / low — explain if medium or low]
```

---

**Phase C — Produce Output Artifacts**

Write two artifact types into `EPIC_DIR`.

**C1. Epic index document** — `EPIC_DIR/index.md`

```markdown
# Epic: <Title>

**Epic Issue:** <org/repo>#<number> — <URL>
**Status:** DRAFT | UNKNOWNS_BLOCKED | READY_TO_EXECUTE
**Last Updated:** <YYYY-MM-DD>

---

## Problem Statement

<One paragraph. What user experience or system property is broken or missing today?
Written from the outside in — observable symptoms, not internal state.>

## Goals

<Bulleted outcome statements. Each must be falsifiable at the epic level.
Format: "Users/operators/systems can <observable outcome> without <current friction>."
Do NOT write Given/When/Then here — that belongs in child issues.>

-
-

## Non-Goals

<Explicit. If it came up in discussion and was ruled out, it belongs here.>

-

## Constraints

<Technical, organizational, or contractual limits that shape the solution space.>

-

---

## Open Questions / Unknowns

| ID | Question | Priority | Resolution Owner | Deadline | Status |
|----|----------|----------|-----------------|----------|--------|
| U1 | | P0/P1/P2 | | YYYY-MM-DD | OPEN |

**Gate rule:** No child issues move to implementation until all P0 unknowns are RESOLVED.
If any P0 unknown is OPEN, epic status MUST be `UNKNOWNS_BLOCKED`.

---

## Dependency Graph

<ASCII or prose. Describes sequencing constraints across slices.
If all slices are parallelizable, state that explicitly.>

```
[Slice 1] ──► [Slice 3] ──► [Slice 5]
[Slice 2] ──► [Slice 3]
[Slice 4] (independent — parallel with Slice 1 and 2)
```

## Integration Seams

<Shared components that multiple slices modify. For each seam: which slices touch it and
what coordination is required.>

## Decomposition Table

| Child # | Title | Behavioral Question | Depends On | DRI / Team | Rough Effort | Status |
|---------|-------|---------------------|------------|------------|--------------|--------|
| 1 | | | — | TBD | XS/S/M/L/XL | DRAFT |
| 2 | | | Child #1 | TBD | | DRAFT |

**Behavioral Question:** The specific observable behavior this child issue must produce.
One sentence. If you cannot write it from available context, mark the cell `NEEDS HUMAN INPUT`
and do not create a draft file for that child.

## Risk Register

| Risk | Affected Slices | Likelihood | Mitigation |
|------|----------------|------------|------------|
| <e.g. shared DB migration conflicts> | Slice 2, Slice 4 | Medium | Land Slice 2 first |
| <e.g. API contract change breaks callers> | Slice 3 | Low | Version the endpoint |

## Out of Scope for This Epic

<Anything explicitly excluded. If unspecified, implementers will over-reach or under-reach.>

## Existing Children

<Child issues that already exist at the time of refinement. Do not re-propose these.>

---

## Sign-Off Gate

| Role | Name | Status | Date |
|------|------|--------|------|
| Engineering DRI | | PENDING | |
| Affected Team Lead(s) | | PENDING | |

**Gate rule:** Epic must reach APPROVED from all required roles before any child issue is
handed to `/resolve-issue`. Partial sign-off does not unblock execution. The Decomposer
cannot enforce this mechanically — it states it explicitly and sets status accordingly.
```

**C2. Per-slice child issue draft** — `EPIC_DIR/child-<N>-<slug>.md`, one file per slice

```markdown
# Child Issue Draft: <Title>

**Parent Epic:** <org/repo>#<epic-number>
**Child Index:** <N> of <total>
**DRI / Team:** <name or TBD>
**Rough Effort:** XS | S | M | L | XL
**Depends On:** Child #<N> | none

---

## Behavioral Question

<One sentence. The observable behavior this issue must produce when complete.>

## Background

<Context from the epic scoping this child. 2–4 sentences max. References epic index.>

## Acceptance Scenarios

<One Given/When/Then block per affected entry point — same schema as /refine-issue.>

### Scenario 1 — <Entry Point Name>
**Given** <precondition>
**When** <user action at this entry point>
**Then** <observable outcome>
**Falsifiability:** <the test that would have caught "wired but disconnected">

## Surface Area

| Component | File / path (with line numbers) | Change required | Scenario(s) it satisfies |
|-----------|--------------------------------|-----------------|--------------------------|
| | `src/example.py:42` | | |

## Integration Seams

<Any files this slice shares with adjacent slices. Coordination required.>

## Slice Independence Statement

This slice can ship without any other slice in this epic being complete because:
<one concrete reason — e.g. "it adds a new column with a default value and no existing code
path reads it until child #3 wires the API.">

If this statement cannot be written, do not create this child draft — merge the slice with
its dependency and document the merge in the epic index.

## Out of Scope

<Anything explicitly excluded from THIS child even if related to the epic.>

## Open Questions

| ID | Question | Priority | Owner | Deadline |
|----|----------|----------|-------|----------|
```

---

**Quality checks before finishing:**

- [ ] Every slice has a written Slice Independence Statement. Any slice that failed the
  independence test is merged with its dependency or converted to a prerequisite.
- [ ] No file path appears in two different slice surface area tables without an explicit
  Integration Seam entry in the index and in both affected child drafts.
- [ ] The dependency graph is a DAG — no cycles.
- [ ] Every risk in the Risk Register maps to at least one named mitigation.
- [ ] The dead integration check ran for every workstream. Every suspicious symbol appears in
  the relevant child's surface area table with a "verify wiring" note.
- [ ] Every child with a missing Behavioral Question is marked `NEEDS HUMAN INPUT` in the
  decomposition table, and no draft file was created for it.
- [ ] Coverage confidence statement is present. Any workstream rated "low" is flagged in the
  index for human review before implementation begins.
- [ ] If any P0 unknown exists, epic status is set to `UNKNOWNS_BLOCKED` and no child drafts
  are written — only the index with the unknowns table.

---

## Step 4 — Create Child GitHub Issues

Trigger: Decomposer completes Step 3 with no P0 unknowns blocking.

For each slice with a complete Behavioral Question, in dependency order (leaves of
the DAG first):

```bash
gh issue create --repo <REPO> \
  --title "<proposed child issue title from index.md>" \
  --body "$(cat <<'EOF'
Part of epic #<number>.

<full contents of EPIC_DIR/child-<N>-<slug>.md>

---
*Generated by /refine-epic. Review before running /resolve-issue on this child issue.*
EOF
)" \
  --label "child-issue"
```

After each issue is created, capture its number and URL. Update `EPIC_DIR/index.md` to record
the mapping: `Child N → #<child-number> <url>`.

After all child issues are created, print:
```
Child issues created:
  Child 1: #<n> <title> — <url>
  Child 2: #<n> <title> — <url>
  ...

Starting surrogate-driven refinement for each child. No questions will be asked —
the epic intent document provides the surrogate's knowledge base.
```

---

## Step 5 — Surrogate-Driven Child Refinement

Run immediately after Step 4, processing children in dependency order (serial).

The premise: Step 2 captured enough author reasoning that a surrogate seeded from
`intent.md` can answer all questions the `/refine-issue` Intent agent would ask —
without escalating to the real user.

### Per-child: spawn a Surrogate agent (model: "claude-sonnet-4-6")

For each child issue, spawn a dedicated Surrogate agent. Do not start the next child
until the current one completes.

Pass each Surrogate:
- Full contents of `EPIC_DIR/intent.md`
- Full contents of the assigned child's draft: `EPIC_DIR/child-<N>-<slug>.md`
- Full contents of all other child drafts (for understanding what is NOT this child's scope)
- The epic issue body and comments
- The child issue number and GitHub URL

**Surrogate agent instructions:**

You are the product owner for this epic, acting as a surrogate. Your knowledge base is
`intent.md` and the child drafts. You have no opinions beyond what those documents state
— you do not guess or invent intent.

Your job: run `/refine-issue <child-number>` and act as the human respondent throughout
its Intent agent dialogue. When the Intent agent asks you questions, answer from
`intent.md`, citing the relevant section (e.g., "Per Decision Priors §3: ...").

If a question cannot be answered from `intent.md` or the child draft, respond:
`[ESCALATE] <question> — not resolved by the intent document.`
Log all escalations. Do not block on them — let `/refine-issue` continue and note the
open question in the intent summary's Open Questions section.

All other `/refine-issue` behavior is unchanged: complete the Intent agent dialogue,
confirm the intent summary, and let the Spec agent run its full codebase research and
produce the refined spec. The spec will be posted to the child's GitHub issue by
`/refine-issue` as normal.

After the Surrogate completes, collect any escalations and report them.

---

After all children complete, surface escalations to the user:

```
Surrogate refinement complete:
  Child 1: #<n> <title> — spec posted <url>
  Child 2: #<n> <title> — spec posted <url>
  ...

Escalations requiring human input:
  Child 1 (#<n>): <question>   ← or "None"
```

If there are escalations, wait for the user to answer, then update the relevant child's
spec comment on GitHub with the resolved intent.

Then proceed immediately to Step 6.

---

## Step 6 — Post Decomposition Summary

Post a summary comment on the GitHub epic issue:

```bash
gh issue comment <number> --repo <REPO> --body "$(cat <<'EOF'
## refine-epic: decomposition complete

Child issues and refined specs:
  Child 1: #<n> <title> — <url>
    Spec: <one-line behavioral intent>
  Child 2: #<n> <title> — <url>
    Spec: <one-line behavioral intent>
  ...

Dependency order: <list>
Integration seams: <N>
Open escalations: <N> (review before /resolve-issue)

Ready for /resolve-issue per child, in dependency order.
EOF
)"
```

Then tell the user in-chat:
```
Done. Decomposition posted to <epic issue url>.
Next step: /resolve-issue <child-number> for each child, in dependency order.
```

Stop.

---

## Process Gates

**Gate 1 — Unknowns Gate** (blocks all child issue drafting)
Condition: Any P0 unknown in the Open Questions table is OPEN.
Action: Set epic status to `UNKNOWNS_BLOCKED`. Output the index doc with the unknowns table
populated. Stop. Do not write any child draft files. Prompt the user to resolve P0 unknowns
and re-run.

**Gate 2 — Behavioral Question Gate** (blocks individual child drafting)
Condition: The Decomposer cannot produce a one-sentence Behavioral Question for a child from
available context.
Action: Add the child row to the decomposition table with Behavioral Question =
`NEEDS HUMAN INPUT` and Effort = `?`. Do not create a draft file for that child. Continue
drafting other children where the question is answerable.

**Gate 3 — Sign-Off Gate** (advisory — blocks handoff to `/resolve-issue`)
Condition: Any required role in the Sign-Off table is PENDING.
Action: Epic index status must read `DRAFT` or `UNKNOWNS_BLOCKED`, never `READY_TO_EXECUTE`.
State explicitly in output: *"This epic is not cleared for implementation. Obtain sign-off
from: <list>."* The Decomposer cannot enforce this mechanically beyond stating it.

---

## Constraints

- Never write or modify source files.
- Never open branches, commits, or PRs.
- Child issues are created automatically after decomposition. Do not hold issue creation
  waiting for user input unless a P0 unknown blocks it (Gate 1).
- Rough effort uses T-shirt sizing only (XS/S/M/L/XL). No story points, no hours. Precision
  is false at epic definition time.
- Never invent a DRI or team assignment. Use `TBD` and flag it as requiring human input before
  the Sign-Off Gate clears.
- If the codebase cannot be scanned (no git root, access denied, too large), mark all surface
  area rows as `UNVERIFIED` and state scan coverage explicitly.
- The output is a recommendation, not a binding contract. The user should review the
  decomposition before any child issue is handed to `/resolve-issue`.
- If blocked or uncertain about the repo structure, stop and report rather than guessing.
