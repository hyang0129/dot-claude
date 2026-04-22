# Refine Epic

## Purpose

Captures and locks the **intent** behind an epic — the author's feared failure mode, resolved
tradeoffs, hard invariants, and rejected alternatives — so that every downstream decision
(child issue boundaries, implementation calls, agent escalations) can be resolved by reference
to that intent instead of re-asking the author.

Decomposition into independently shippable child issues is a consequence of this, not the goal.
Child issues exist to propagate intent into executable slices; the dependency graph, integration
seams, and risk register exist to keep that propagation honest. If intent capture fails, nothing
downstream can recover — conflicting PRs, duplicated slices, and missed subsystems are all
symptoms of an unvalidated WHY, not of a bad cut of the work.

The core failure this command prevents: agents (or humans) executing epic work against an
inferred intent that diverges from the author's actual one.

**This command never writes source code and never opens PRs.**
Its outputs, in priority order:
1. A validated intent document, published to the epic issue body and as a changelog comment
   (the master surface for all downstream work).
2. A compressed intent digest, embedded into every child issue so the WHY travels with the work.
3. An index document + per-slice child drafts that carry the intent forward into executable units.
4. Optionally, GitHub child issues created after decomposition.

The natural pipeline: `/refine-epic` → intent locked and published → child issues created,
each inheriting compressed intent → surrogate-driven `/refine-issue` per child (seeded from
intent, no re-asking the author) → `/resolve-issue` per child.

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

Optional flag: `--org` activates org mode (multi-team coordination protocol).

---

## Mode

Default: **solo** — assumes single-author ownership. This skill is written for solo mode.

*Org mode (`--org`): see [refine-epic-org.md](refine-epic-org.md).* It defines deltas applied
over solo mode: stakeholder matrix, borrowed-invariant confirmation gate, sign-off table,
additional required questions. Read that file only when `--org` is set.

---

## Step 0 — Setup

**Turn 1 — initialize task tracking.** Before doing anything else, call `TodoWrite` to
initialize your task list with entries for Steps 0–6 (marking Step 0 `in_progress`). This
loads the `TodoWrite` schema early so subsequent updates don't trigger a cache-invalidating
`ToolSearch` mid-session.

### Repo detection

If `epic` is `owner/repo#number` or a full URL, extract `owner/repo` directly — no detection or
confirmation needed. Set `REPO=<owner/repo>` and proceed.

If `epic` is a **free-form description**, detect the repo the same way as a bare number (below),
then confirm with the user before proceeding. The GitHub epic issue will be created by the
Publisher subagent (see Step 2 — Publish).

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

Also fetch any issues already linked as children so they can be referenced (not re-proposed):

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
test -d "$GIT_ROOT/.agent-work" && echo "EXISTS" || echo "MISSING"
```
If `MISSING`, stop and tell the user:
```
.agent-work/ not found in this repo. Please run:
  mkdir -p <GIT_ROOT>/.agent-work && echo '.agent-work/' >> <GIT_ROOT>/.git/info/exclude
Then re-run this command.
```
Do not proceed until the directory exists.

If `GIT_ROOT` is empty, all output goes to `/tmp/EPIC_<slug>-<number>/`. Mark all surface area
as `[UNVERIFIED — no codebase]`. Report this path to the user in the final summary.

### Output directory

Set `EPIC_DIR`:
- With git root: `$GIT_ROOT/.agent-work/EPIC_<slug>-<number>/`
- Without git root: `/tmp/EPIC_<slug>-<number>/`

where `<slug>` is a 3–4 word kebab-case summary of the epic title or description, and `<number>`
is the issue number (or a short hash for free-form).

After Step 0: mark Step 0 done, Step 1 in_progress.

---

## Step 1 — Resume Check

Before spawning anything, check whether a prior run's artifacts exist:

```bash
test -d "$EPIC_DIR" && echo "EXISTS" || echo "MISSING"
```

If the directory exists, list its contents and check GitHub for a prior publish:

```bash
gh issue view <number> --repo <REPO> --json comments -q '.comments[] | select(.body | startswith("<!-- INTENT_DOC -->"))' | head -1
```

Decide state:

- **Partial publish detected** — `intent.md` exists locally but no `<!-- INTENT_DOC -->` comment
  on the epic. Offer: "finish publishing" (re-spawn the Publisher) or "start over."
- **Full publish detected** — `intent.md` exists locally AND the intent comment is posted.
  Offer standard resume options below.
- **Neither** — treat as fresh start.

Resume options when full state is present:

```
Found existing epic work: .agent-work/EPIC_<slug>-<number>/
  intent.md          (present / missing)
  index.md           (present / missing)
  child-1-<slug>.md
  child-2-<slug>.md
  ...

Resume options:
  (r) resume decomposition — skip Step 2, go straight to Step 3 (requires intent.md)
  (i) re-run intent validation only — redo Step 2, keep existing child drafts
  (s) start over — delete everything and begin from Step 2
```

- **Resume (r)**: if `intent.md` present, skip Step 2 and proceed to Step 3. If `index.md`
  and child drafts also present, skip to Step 4.
- **Re-run intent (i)**: delete `intent.md` and `intent-compressed.md` only, re-run Step 2,
  keep all child draft files.
- **Start over (s)**: delete the directory contents and continue to Step 2.
- **Free-form mode** (no issue number and no prior publish): skip this check entirely.

After Step 1: mark Step 1 done, Step 2 in_progress.

---

## Step 2 — Intent Validation (Interactive)

**This step is the highest-leverage point in the entire workflow.** The failure mode it prevents
is not under-documentation — it is capturing an intent that diverges from the organization's
actual intent, or from the author's *considered* intent (vs. their reflexive one). Every
compounding misalignment in downstream child issues traces back to a gap here.

Before starting, tell the user:

```
Starting intent validation. I'll scan the codebase first, then ask scan-calibrated questions
(not abstract tradeoff questions). Three Challenger agents will then produce the strongest
counter-intent the evidence also supports, and you'll rebut it. The rebuttal is the most
load-bearing content in the final document.

Expect: 1–3 interactive rounds depending on epic tier (Lite / Standard / Heavy).
```

**Run the Q&A rounds directly in this session — do NOT delegate Sub-phases 3–5 to a subagent.**
The Clarifier requires multiple interactive Q&A rounds with the real user; a subagent cannot do
that. You are the Clarifier for Step 2. However, the Sub-phase 1 codebase scan **SHOULD** be
delegated to a Sonnet subagent to keep tool-result volume out of ROOT's cache.

### Clarifier process

Role: elicit intent via evidence-grounded questions, detect anchoring and bluffing, force
disconfirmation via a Challenger pass, produce a tier-appropriate intent artifact. No source
file writes. No branch, commit, or PR creation.

**Context bootstrap:**
1. Read `~/.claude/CLAUDE.md` and `$GIT_ROOT/CLAUDE.md` if they exist.
2. If `GIT_ROOT` is unavailable, Sub-phase 1 degrades to vocabulary-only. Mark scan outputs
   `SKIPPED — no codebase` and proceed. Lite tier becomes unavailable; default to Standard.

---

**Sub-phase 1 — Evidence First: Codebase Scan**

Delegate to a Sonnet subagent (`model: "claude-sonnet-4-6"`) so tool-result volume stays off
ROOT's cache. Pass it the epic body + these scan targets:

- **Scan target 1 — Existing domain implementations.** Grep key nouns and verbs from epic
  title/body. Does this capability partially exist? Is the epic extending or replacing?
- **Scan target 2 — Rejection signals.** Commented-out code, FIXME/TODO notes naming
  alternatives, dependency manifests showing added-then-removed libraries. Surface evidence.
- **Scan target 3 — Coarse module boundaries.** Top-level packages/directories the epic will
  touch. Name only.
- **Scan target 4 — Coupling map.** For every symbol or file the epic will modify, grep for
  call sites *outside* the defining module. Produce: `<module> → N external call sites`.
- **Scan target 5 — Borrowed invariants.** Contracts the epic will load-bear on: schemas, SLOs
  in code/config, rate limits, auth boundaries, retention policies. In solo mode, flag only
  invariants owned by **external** systems (third-party APIs, vendor contracts, platform
  SLOs). Internally-owned invariants are treated as confirmed — the author is the owner.

Scan subagent returns two working artifacts (not files yet — surfaced inline during Sub-phase 3):

1. **Inferences list.** Up to 5 named inferences, prioritized by "would change the shape of
   at least one child issue if wrong." Format: `[INFER] <claim>. Confirm or correct.`
2. **Coupling summary + external borrowed invariants.**

*Org mode:* see [refine-epic-org.md](refine-epic-org.md) for CODEOWNERS lookup and stakeholder
matrix additions.

---

**Sub-phase 2 — Tier Decision**

From the scan, assess epic size and pick a tier. State the choice to the user with reasoning
drawn from the scan; allow one override.

- **Lite** — touches ≤1 module, <1 week of work, ≤2 child issues.
- **Standard** — 2–3 modules, 1–4 weeks, 3–6 child issues.
- **Heavy** — >3 modules, OR >4 weeks, OR >6 child issues, OR Sub-phase 1 found a rejection
  signal against a library currently in production.

Output per tier:
- **Lite** — Kill-Criterion Card (~150 words). No full intent doc, no compressed derivative, no changelog comment.
- **Standard** — full `intent.md` + extractive compression + GitHub publishing.
- **Heavy** — Standard + required ADR links for ONE-WAY-DOOR priors.

*Org mode:* see [refine-epic-org.md](refine-epic-org.md) for adjacent-team thresholds and
Heavy-tier confirmation gate.

Present:
```
Tier: <chosen> — because <reasoning from scan>.
Override to {Lite|Standard|Heavy}? Otherwise proceed with <chosen>.
```

---

**Sub-phase 3 — Premortem + Scan-Calibrated Questions**

Replace abstract tradeoff questions with one narrative-forcing prompt plus scan-grounded
follow-ups. Do not pre-name tradeoff axes — that anchors the user onto a framing the
Clarifier already has.

**Premortem (always asked, verbatim):**

> "It is six months from now. This epic shipped on schedule and every line of code works as
> designed. Despite that, someone is writing a blameless postmortem about why this was the
> wrong thing to build — or the right thing built the wrong way. Write the first paragraph
> of that postmortem. Be specific: name the cohort affected, the observable symptom, and the
> decision that looks wrong in hindsight."

Do not accept a one-line answer. If the response is <4 sentences or abstract ("it didn't solve
the problem"), push back: "Too abstract — give me the specific scenario. Who is angry, what
did they try to do, what happened instead?"

**Scan-calibrated follow-ups (Standard + Heavy).** Generate 3–5 questions grounded in
Sub-phase 1 evidence. Do not ask abstract tradeoff questions. Templates:

- *"I found [specific code pattern]. My inference is [interpretation]. Is that right — and
  if not, what should I understand instead?"*
- *"Here are two inferences I could draw from the same evidence: A or B. Which is closer, or
  is it neither?"* (use this disconfirming frame for at least one follow-up)

**Required questions (Standard + Heavy, solo mode):**

- Premortem (always)
- Scan-calibrated follow-ups (above)
- **Q-success:** "What measurable signal in production proves this worked? Give a specific
  metric and a threshold. If you cannot name one, state why this is unfalsifiable."
- **Q-borrowed** (only if Sub-phase 1 found external invariants): "Have you confirmed with the
  owner, or are you assuming stability? If assuming, state the blast radius if it breaks."

Dropped in solo mode: Q-commitment and shape are covered by the Challenger pass (Sub-phase 5);
Q-kill and Q-portfolio are assumed (invoking `/refine-epic` signals intent to build now;
abandonment needs no formal criterion when you're the whole team); Q-stakeholders is org-only.

*Org mode:* see [refine-epic-org.md](refine-epic-org.md) for the full question set.

**Lite tier:** premortem + Q-success only. Skip the rest.

Present all questions for a round together in a single block — do not serialize.

---

**Sub-phase 4 — Bluffing and Anchoring Detection**

Score every answer against these detectors. Any two firing triggers a **probe round** —
reject the abstract answer and force a concrete anchor before continuing.

**Bluffing signals:**
- Answer arrives in <15 seconds and echoes the epic body phrasing verbatim.
- Certainty markers without reasoning ("obviously", "clearly", "we all know").
- Tradeoff answers that name both sides without committing ("fast *and* correct").
- Invariants phrased as preferences ("should be", "ideally", "would be nice").
- No named alternative in decision priors or in Q-kill ("nothing really", "we just knew").
- Feared-failure mode that's a restatement of the goal inverted ("failure = it doesn't work").

**Considered-position signals (do not probe further):**
- Names the alternative and its strongest argument *before* rejecting it.
- Cites a concrete past incident, PR, or observed behavior.
- Qualifies ("usually X, except when Y").

**Probe round prompts:** "Name one specific user who would be angry." / "Describe the
incident that made you conclude this." / "Walk me through the last time you saw this
failure." / "Steelman the opposite position — what would someone who disagreed argue?"
Continue probing until answers carry concrete anchors.

---

**Sub-phase 5 — Multi-Angle Challenger Pass (Standard + Heavy only)**

Spawn three Challenger subagents **in parallel** in a single response
(`model: "claude-sonnet-4-6"`). Running them in parallel prevents Challengers from anchoring
on each other's arguments. In solo mode, where no team exists to push back, this is the only
external voice in the room.

Prompts live in [refine-epic/challenger-prompts.md](refine-epic/challenger-prompts.md). Read
that file once, then pass each Challenger's prompt inline alongside the identical inputs:

- Sub-phase 1 scan outputs (inferences list, coupling summary, borrowed invariants).
- Q&A transcript from Sub-phase 3, verbatim.
- **Do NOT pass the epic body text.** Each Challenger reasons from scan + transcript only.

Present the three outputs to the user and capture the rebuttal verbatim (presentation
template is in challenger-prompts.md). A rebuttal that concedes one or more points triggers
a revision round on the sections it affects.

---

**P0 blocker / contradiction detection (runs throughout Sub-phases 3–5).**

Watch for:
- Dependency on an unresolved external decision.
- A stated constraint that contradicts the epic's stated goal.
- An explicit "we haven't decided" gating the entire decomposition.
- An answer that directly contradicts another answer or scan evidence.

If found, halt and surface it specifically:

```
HALT — <P0 blocker | contradictory intent>:

<specifics>

Resolve before the intent document can be written.
```

---

**Produce intent artifact**

Schemas live in [refine-epic/intent-templates.md](refine-epic/intent-templates.md). Read that
file only when you reach this point.

ROOT assembles the full `intent.md` text **in-memory** from the Q&A transcript and Challenger
rebuttal. Do NOT print the full document to the user — write it to
`$EPIC_DIR/intent.md` via a single `Write` call (file I/O, not output tokens).

Tell the user:
```
Intent document written to .agent-work/EPIC_<slug>-<number>/intent.md. Posting to GitHub now...
```

If TIMEBOX items remain unaddressed, pause:
```
Intent document written. One unresolved item before I proceed:

<specific gap>

Clarify this and I'll post the document and start decomposition.
```

---

**Publish via Publisher subagent**

Load the Publisher prompt from [refine-epic/publisher-prompt.md](refine-epic/publisher-prompt.md)
and spawn it (`model: "claude-sonnet-4-6"`). Pass inline:

- The full contents of publisher-prompt.md
- `EPIC_DIR` (absolute path — Publisher reads `intent.md` from here)
- `REPO`
- `EPIC_NUMBER` (integer, or `null` for free-form mode)
- `TIER`
- `BODY_SECTIONS` — ordered list of section headings (from intent-templates.md, per tier)
- `COMPRESSED_SCHEMA` — ordered list of section headings for compression
- `FREE_FORM_TITLE` — epic title, only in free-form mode

The Publisher:
1. Creates the epic issue (free-form mode only), capturing `EPIC_NUMBER`.
2. Reads `intent.md`.
3. Writes `intent-compressed.md` by verbatim extraction (no LLM paraphrase).
4. Posts the full intent as a `<!-- INTENT_DOC -->` changelog comment.
5. Rewrites the epic body to prepend a `## Validated Intent` section (idempotent — strips
   any prior Validated Intent block).
6. Returns `INTENT_COMMENT_URL` (and `EPIC_NUMBER` in free-form mode).

Once Publisher returns, tell the user:
```
Intent posted: <INTENT_COMMENT_URL>
```

For **Lite tier**, skip the Publisher spawn entirely — the Kill-Criterion Card is the whole
artifact; there is no compressed derivative and no changelog comment. Post it inline as the
epic body Validated Intent section via a single `gh issue edit` call.

After Step 2: mark Step 2 done, Step 3 in_progress. Proceed directly to Step 3 — do not
pause for user approval.

---

## Step 3 — Decomposition

Intent is locked. Decomposition is ROOT-driven: ROOT reasons about scope and workstream
seams, spawns parallel Sonnet Researchers for per-workstream codebase investigation, then
merges their outputs and writes artifacts. There is no Decomposer agent.

### Phase A — ROOT working note

Private reasoning step. No tool calls. No file writes. Using `intent.md` + Sub-phase 1 scan +
epic body, produce an in-memory note covering:

**A1. Stated scope.** Key phrases from the author quoted.

**A2. Decomposition goal.** Distinguish:
- Slices the author named explicitly
- Slices implied by the work but not mentioned
- Work mentioned that is NOT a slice (cross-cutting concerns, one-time migrations,
  infra prerequisites)

**A3. Dependency identification.** For each candidate slice: can it ship and deliver value
without another slice completing? If no, which slice must precede it, and why? A slice that
fails this must be merged with its dependency or flagged as a prerequisite block.

**A4. Workstream seams.** Group slices by primary system boundary — data, API, CLI, frontend,
jobs, infra. 3–6 workstreams max. Slices within a workstream are sequential; slices across
workstreams may be parallel.

Do not include existing child issues as proposed slices — reference them under "Existing
Children" in the index.

Output (in-memory only): workstream list with `(name, concern, candidate_slices[])` per entry.

### Phase B — Parallel Sonnet Researchers

Load the Researcher prompt from [refine-epic/researcher-prompt.md](refine-epic/researcher-prompt.md)
once. Then, **in a single response**, emit one `Agent` tool call per workstream
(`model: "claude-sonnet-4-6"`). All Researchers run concurrently.

Per-Researcher inputs (substituted into the prompt):
- `WORKSTREAM_NAME`, `WORKSTREAM_CONCERN`, `CANDIDATE_SLICES`
- `INTENT_COMPRESSED` — verbatim contents of `intent-compressed.md`
- `GIT_ROOT`

Each Researcher runs the 5-step research checklist (vocab grep, entry-point enum,
dead-integration check, integration-seam detection, test coverage probe) and returns a
JSON object with `files_touched`, `entry_points`, `suspected_unwired`, `integration_seams`,
`coverage_gaps`, `notes`. No file writes.

### Phase C — ROOT synthesis + artifact write

After all Researchers return, ROOT:

1. **Intersect `files_touched` across Researchers.** Any file in ≥2 outputs is a seam
   candidate. Add to Integration Seams list. Add each cross-workstream Researcher-reported
   seam (from `integration_seams`) as well.

2. **Run Quality Checks inline:**
   - DAG-ness: no cycles in the dependency graph
   - Slice Independence: every slice has a one-sentence independence statement
   - Every risk has a mitigation
   - Every child has a Behavioral Question or is marked `NEEDS HUMAN INPUT`
   - Every child draft's Inherited Intent block is populated (see C2 below)

3. **Write `EPIC_DIR/index.md`** (schema below) and **one `EPIC_DIR/child-<N>-<slug>.md`
   per slice** (schema below).

4. **Populate Inherited Intent blocks** by filtering `intent-compressed.md` for
   slice-relevance: include an invariant or prior only if this slice's surface area could
   plausibly violate it. When uncertain, include it — under-inclusion here is the failure
   mode the block exists to prevent.

The Researchers' outputs and ROOT's written artifacts are **authoritative**. Do not re-read
`index.md` or sample child drafts to "verify" before Step 4 — Quality Checks already ran
inline as part of Phase C. Proceed directly to Step 4.

After Step 3: mark Step 3 done, Step 4 in_progress.

### C1. Index document schema — `EPIC_DIR/index.md`

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

<Populated mechanically from ROOT's Researcher-output intersection. For each seam: which
slices touch it and what coordination is required.>

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
| | | | |

## Out of Scope for This Epic

<Anything explicitly excluded. If unspecified, implementers will over-reach or under-reach.>

## Existing Children

<Child issues that already exist at the time of refinement. Do not re-propose these.>
```

*Org mode:* append Sign-Off Gate table — see [refine-epic-org.md](refine-epic-org.md).

### C2. Per-slice child draft schema — `EPIC_DIR/child-<N>-<slug>.md`

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

## Inherited Intent (from epic #<epic-number>)

*Compressed from the validated intent document. Full version: <INTENT_COMMENT_URL>*

**Feared Failure Mode:** <verbatim from intent-compressed.md — do not paraphrase>

**Invariants that apply to this slice:**
- <ABSOLUTE invariant 1 relevant to this slice's surface area>
- <ABSOLUTE invariant 2 relevant to this slice's surface area>

**Relevant Decision Priors:** <1–2 priors from intent-compressed.md whose tradeoff axis
this slice is most likely to touch. One sentence each. If none apply, write "None — this
slice does not cross any resolved tradeoff axis" and link to the full intent comment.>

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
<one concrete reason>

If this statement cannot be written, do not create this child draft — merge the slice with
its dependency and document the merge in the epic index.

## Out of Scope

<Anything explicitly excluded from THIS child even if related to the epic.>

## Open Questions

| ID | Question | Priority | Owner | Deadline |
|----|----------|----------|-------|----------|
```

---

## Step 4 — Create Child GitHub Issues

Trigger: Phase C completed with no P0 unknowns blocking.

Create all child issues in one pass via a single bash script that derives titles from child
drafts' first-line headers and issues them in dependency order (leaves of the DAG first):

```bash
cd "$EPIC_DIR"
for draft in $(ls child-*.md | sort); do
  title="$(head -1 "$draft" | sed -e 's/^# Child Issue Draft: //')"
  url="$(gh issue create --repo "$REPO" \
    --title "$title" \
    --body "$(printf 'Part of epic #%s.\n\n' "<number>"; cat "$draft"; printf '\n\n---\n*Generated by /refine-epic. Review before running /resolve-issue on this child issue.*\n')" \
    --label "child-issue")"
  echo "$draft -> $url"
done
```

After each issue is created, update `EPIC_DIR/index.md` to record the mapping
`Child N → #<child-number> <url>`.

Print:
```
Child issues created:
  Child 1: #<n> <title> — <url>
  Child 2: #<n> <title> — <url>
  ...

Starting surrogate-driven refinement for each child. No questions will be asked —
the epic intent document provides the surrogate's knowledge base.
```

After Step 4: mark Step 4 done, Step 5 in_progress. Do not pause for user approval between
creating child issues and spawning the first Surrogate.

---

## Step 5 — Surrogate-Driven Child Refinement

Run immediately after Step 4, processing children in dependency order.

The premise: Step 2 captured enough author reasoning that a Surrogate seeded from
`intent-compressed.md` can answer all questions `/refine-issue`'s Intent agent would ask —
without escalating to the real user.

Load the Surrogate prompt from [refine-epic/surrogate-prompt.md](refine-epic/surrogate-prompt.md)
once, then reuse for every Surrogate spawn.

### Per-child: one `Agent` call per child

For each child issue, emit one `Agent` tool call (`model: "claude-sonnet-4-6"`). **Do NOT
batch multiple children into one agent** — each Surrogate must start with a fresh context.
With N children, ROOT emits N separate `Agent` calls, waiting for each to complete before
emitting the next.

> **Constraint:** Do not describe a single subagent as a "multi-way" or "N-way" surrogate.
> One subagent = one child issue. A subagent that processes multiple children in sequence is
> a correctness bug: escalations from child N pollute child N+1's context, and the quadratic
> cache-growth penalty makes it 3–5× more expensive than intended.

Pass each Surrogate:
- Full contents of `EPIC_DIR/intent-compressed.md`
- Full contents of the assigned child's draft: `EPIC_DIR/child-<N>-<slug>.md`
- The absolute path to `EPIC_DIR/intent.md` (for on-demand deeper reads)
- Full contents of all OTHER child drafts (for understanding what is NOT this child's scope)
- The epic issue body and comments
- The child issue number and GitHub URL

The Surrogate runs `/refine-issue <child-number>`, acting as the author by answering from
`intent-compressed.md` first and citing the relevant section. It returns
`{child_number, spec_comment_url, escalations[]}`.

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

After Step 5: mark Step 5 done, Step 6 in_progress.

---

## Step 6 — Post Decomposition Summary

Assemble the summary markdown in-memory:

```markdown
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
```

Spawn the Publisher in **summary mode** (`model: "claude-sonnet-4-6"`). Pass the prompt from
[refine-epic/publisher-prompt.md](refine-epic/publisher-prompt.md) plus:
- `REPO`
- `EPIC_NUMBER`
- `SUMMARY_MD_CONTENT` — the assembled summary above

The Publisher posts the comment and returns `summary_comment_url`. Then tell the user:
```
Done. Decomposition posted to <epic issue url>.
Next step: /resolve-issue <child-number> for each child, in dependency order.
```

Mark Step 6 done. Stop.

---

## Process Gates

**Gate 1 — Unknowns Gate** (blocks all child issue drafting)
Condition: Any P0 unknown in the Open Questions table is OPEN.
Action: Set epic status to `UNKNOWNS_BLOCKED`. Output the index doc with the unknowns table
populated. Stop. Do not write any child draft files. Prompt the user to resolve P0 unknowns
and re-run.

**Gate 2 — Behavioral Question Gate** (blocks individual child drafting)
Condition: ROOT cannot produce a one-sentence Behavioral Question for a child from
Researcher outputs + intent.
Action: Add the child row to the decomposition table with Behavioral Question =
`NEEDS HUMAN INPUT` and Effort = `?`. Do not create a draft file. Continue drafting other
children where the question is answerable.

*Org mode:* Gate 3 (Sign-Off Gate) — see [refine-epic-org.md](refine-epic-org.md).

---

## Constraints

- Never write or modify source files.
- Never open branches, commits, or PRs.
- Child issues are created automatically after decomposition. Do not hold issue creation
  waiting for user input unless a P0 unknown blocks it (Gate 1).
- Rough effort uses T-shirt sizing only (XS/S/M/L/XL). No story points, no hours.
- Never invent a DRI or team assignment. Use `TBD`.
- If the codebase cannot be scanned (no git root, access denied, too large), mark all surface
  area rows as `UNVERIFIED` and state scan coverage explicitly.
- The output is a recommendation, not a binding contract. The user should review the
  decomposition before any child issue is handed to `/resolve-issue`.
- If blocked or uncertain about the repo structure, stop and report rather than guessing.
