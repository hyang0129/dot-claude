---
name: refine-issue
description: "Interview the user to capture and lock the intent behind an issue — the real outcome wanted, unstated assumptions, intolerable failure modes — so an implementation agent never has to re-ask. Pass --obvious to answer via a surrogate when the body is already detailed."
disable-model-invocation: true
---

# Refine Issue

## Purpose

Captures and locks the **intent** behind an issue — the real-world outcome the user wants, the
hidden assumptions they didn't write down, and the failure modes they won't tolerate — so that
an implementation agent can resolve every downstream decision by reference to that intent
instead of re-asking the user. The core failure this prevents: implementations that technically
close a ticket while executing against an intent that diverges from the user's actual one.

**Never writes source code, never opens PRs.** Outputs: (1) a validated intent summary,
(2) a refined spec projecting that intent onto the codebase as falsifiable acceptance
scenarios and a surface-area table, (3) optionally the spec posted to the GitHub issue.

## Args

`/refine-issue <issue> [--no-post] [--base <branch>] [--obvious]`

- `issue`: GitHub issue number, full URL, `owner/repo#N`, or a quoted free-form description.
- `--no-post`: keep the spec local (ignored in free-form mode — free-form always creates an issue).
- `--base <branch>`: base branch to scan against (default: auto-detect).
- `--obvious`: skip the interactive interview; a surrogate subagent
  (`references/surrogate-prompt.md`) answers the probe dimensions from the issue body +
  codebase + constitution, citing sources, marking ungrounded answers `[unanswered]`. The user
  gets one confirm/correct round. If the surrogate returns mostly `[unanswered]` or many
  `[ESCALATE]` entries, the issue is not actually obvious — drop the flag and run interactively.

## Setup

1. **Repo**: extract `owner/repo` from the URL/ref, or detect via `git remote -v` /
   `gh repo view` (prefer `upstream` over `origin`). Confirm with the user only when
   auto-detected from a bare number.
2. **Base branch**: `--base`, else the repo's default branch, else `dev`/`main`. Before
   switching or syncing: **refuse to proceed on a dirty working tree** (the user has
   uncommitted work — tell them to stash or commit). Fast-forward to the upstream if cleanly
   behind; if local is ahead, note it; **if diverged, stop** — the spec would describe code
   reviewers can't see. If there is no upstream and we intend to post to GitHub, stop and ask
   for tracking or `--no-post`.
3. **Git root** (dev-container safe):
   ```bash
   GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
   if [ -z "$GIT_ROOT" ]; then
     for candidate in /workspaces/* "$HOME"/repos/* "$HOME"/projects/* "$HOME"/*; do
       [ -d "$candidate/.git" ] && { GIT_ROOT="$candidate"; break; }
     done
   fi
   ```
   If still empty, proceed without codebase context (spec marks surface area `[UNVERIFIED]`;
   outputs go to `/tmp/`).
4. **Scratch dir**: require `$GIT_ROOT/.agent-work/`. If missing, stop and tell the user to run
   `mkdir -p $GIT_ROOT/.agent-work && echo '.agent-work/' >> $GIT_ROOT/.git/info/exclude`
   (info/exclude, not .gitignore — the ignore rule itself must not dirty the repo).
5. **Constitution**: if `CONSTITUTION.mini.md` or `CONSTITUTION.md` exists at the root, read it
   in full **now, in this session** — the interview must cite laws inline, and a subagent's
   findings would not be in working context. If none exists, skip every constitution rule below;
   do not infer laws from `CLAUDE.md` or general norms.
6. **Fetch the issue** (`gh issue view <n> --json number,title,body,labels,comments`).
7. **Resume check**: derive `SLUG` from the title (lowercase, hyphens, ≤40 chars). If
   `.agent-work/REFINED_${SLUG}-*.md` exists, offer resume (skip to Step 3 report) or start
   over. If only `INTENT_${SLUG}-*.md` exists, offer to resume the interview from its Q&A log
   — never re-ask answered questions — or start over.

## Step 1 — Intent Interview

`--obvious` → surrogate flow: spawn a subagent with `references/surrogate-prompt.md`, the issue
body/comments, `GIT_ROOT`, the constitution path, and the output path
`.agent-work/INTENT_<slug>-<id>.md`. Present its draft, list `[unanswered]` and `[ESCALATE]`
entries explicitly, ask "Confirm to proceed to spec, or correct anything?". A simple correction
is applied directly; a correction that opens a new dimension falls through to the interactive
flow with the corrected file as Round 1. If `GIT_ROOT` is empty and the issue body is under ~10
lines, warn that grounding is limited before spawning.

Otherwise, interview directly in this session — no subagent. This is the most important step.
Dialogue only: no file writes beyond checkpoints, no spec production.

**You are a requirements interviewer, not a spec writer.** Your job is to understand the user's
intent so completely that a different agent — who has never spoken to the user — could produce a
spec the user would sign off on without a single correction.

Start by reading the issue carefully. Then immediately begin probing — do not summarize or
restate the issue back to the user.

**Probe dimensions (cover all, across as many rounds as needed):**

1. **The real outcome**
   - What does success look like from the user's perspective — not a code change, a *lived experience*?
   - What would change about their day if this were done right?
   - If the feature disappeared tomorrow, what would they miss?
2. **Hidden scope**
   - Are there places where this behavior should apply that the issue doesn't mention?
   - Has the user ever been surprised that something "worked" in one place but not another?
   - Is there anything they assumed was obvious that they didn't bother writing down?
3. **Acceptance conditions**
   - How will they know it's working? What will they check?
   - What's the simplest thing that would count as "not done"?
   - Is there a failure mode they've seen before that they definitely don't want to repeat?
4. **Constraints and non-goals**
   - What should explicitly NOT change as part of this?
   - Is there anything that would be tempting to add but is out of scope for now?
   - Are there performance, backward-compatibility, or API-stability concerns?
5. **Priority and motivation**
   - Why is this important now? What triggered the request?
   - Is there a deadline, a downstream dependency, or a user complaint that drove this?
6. **Constitution fit** (only when a constitution was detected)
   - Which law does this work touch hardest? Name any question that would answer "unclear"
     under the current scope.
   - Does any scope carve-out leave another surface in violation of a law in the interim — and
     is that acceptable, a tracked follow-up, or something the user hadn't considered?
   - Is the author deliberately stricter than the constitution requires, or stopping at the
     law's minimum? Either is valid, but it must be explicit so implementers don't quietly
     relax or tighten it.

**Conversation rules:**
- **Ask all relevant questions per round** — do not artificially limit to one or two. Group by
  dimension so the user answers in one pass. Six related questions at once beats six rounds.
- **Bundle conditional follow-ups into the same message**: "Will this need to work offline? If
  yes — queue and replay when reconnected, or silently skip?" Do not wait for the first half
  when the branching is simple.
- **Verify the user actually answered what you asked** before the next round. Re-ask skipped or
  incomplete answers explicitly — never silently drop them.
- **Before asking anything the codebase could answer** ("does X exist?", "is Y wired?"), spawn
  a quick Explore subagent and present the finding inline instead:
  "I was going to ask: <question>. Looking at the code, I found: <finding>. Stop me if that's
  wrong — <next question>." Questions about intent, priority, and lived experience always go to
  the user — code cannot answer those.
- **When a constitution is loaded, check it before each planned question.** If a law's stance,
  anti-pattern, Why clause, or rejected alternative constrains the answer, present the
  inference inline: "Per Law N (<name>): I infer <answer> because <specific clause, tightly
  quoted>. Stop me if that's wrong — <next question>." Rules: the constitution never reduces
  the question count — it pre-fills proposed answers the user must still confirm; cite the
  specific clause, never the law number alone; if an inference collides with what the user
  wants, that tension is data — surface it, don't swallow it; only clauses in the loaded
  constitution grant inference authority.
- Synthesize what you learned before each next round. If an answer opens a new dimension,
  follow it.
- Do not declare understanding complete until you can articulate: the job statement
  (when / want / so I can) with a real-world outcome; at least one hidden assumption the issue
  didn't surface; what "done" looks like from the user's perspective; what's explicitly out of
  scope.
- **Final constitution check** (constitution only): with the complete picture in view, scan for
  tensions visible only in the *aggregate* — a combination of answers that collectively leaves
  a surface non-compliant even though each passed its per-question check. Include any as a
  `**Constitution tension:**` bullet in the completion summary; omit the bullet if none.
- Signal completion:
  ```
  I think I have a complete picture of your intent. Here's what I'll hand off to the spec:

  **Job statement:** When I <situation>, I want to <motivation>, so I can <real-world outcome>.
  **Core behavioral intent:** <2–3 sentences on observable change>
  **Key hidden assumptions:** <bullets>
  **Done looks like:** <what the user will check>
  **Out of scope:** <explicit exclusions>
  **Constitution tension:** <only if found — cite the clause and the choice creating it>

  Does this capture it accurately, or is there anything to correct?
  ```
  Wait for confirm or correct before concluding.

**Checkpoints — do not wait until the end.** Before the first question, write a stub
`.agent-work/INTENT_<slug>-<id>.md` and post a draft to GitHub (issue-ref mode: a comment,
capture its ID; free-form mode: create the issue now, its number becomes `<id>`). After each
round, append the round's Q&A to both. If the session is interrupted, the work is recoverable
from either source. On confirmation, finalize both (drop the DRAFT marker).

**Final intent summary** (`.agent-work/INTENT_<slug>-<id>.md`): sections — Job Statement;
Behavioral Intent (the experience, not the implementation); Hidden Assumptions Surfaced;
Acceptance Conditions (user-stated, natural language); Out of Scope; Motivation Context;
Constitution Alignment (only when one exists: laws touched, inferences carried forward with
source clauses, carve-outs/tensions with the accepted stance, stance vs. minimum per law);
Clarifying Q&A Log (only rounds that changed understanding).

## Step 2 — Spec Agent

Spawn a Spec agent (general-purpose, read-only research). Pass it: issue body + comments, the
intent summary path, `GIT_ROOT`, constitution path, `REPO`, output path
`.agent-work/REFINED_<slug>-<id>.md`, and publish mode: `comment` (issue-ref default),
`create` (free-form), or `none` (`--no-post`).

Spec agent instructions — no dialogue; the intent summary is authoritative:

**Bootstrap**: read global + repo CLAUDE.md, `docs/agent_index.md` if present, the intent
summary in full, and the constitution if given (the spec must cite clause wording, not law
numbers).

**Phase A — Surface-area research.** Enumerate every place the intended behavior must be
present. Required checklist before declaring completeness: (1) the user-facing verb from the
title, (2) the object noun, (3) any existing symbol already doing a fraction of the behavior,
(4) entry-point globs `**/cli*`, `**/commands*`, `**/handlers*`, `**/routes*`, `**/pipeline*`,
`**/server*`, (5) config/hooks/scripts invoking the behavior. Then state:
`Surface area search: examined N files, found M candidates. Coverage confidence: high/medium/low`.
**Dead-code check**: any symbol implementing the behavior with ≤1 call site gets flagged —
"defined at <path:line> but no call sites found — may be unwired." List evidence; let the
implementer verify.

**Phase B — Write the spec** with these sections:
- **Job Statement** — the outcome must be a real-world consequence, not the motivation
  restated. (Bad: "…so I can have reading level checked." Good: "…so I can confidently publish
  material any 6th grader reads without friction.")
- **Behavioral Intent** — what is *observably different*, from the user's perspective.
- **Hidden Assumptions Surfaced**
- **Acceptance Scenarios** — one per **entry point** (not per feature):
  Given / When / Then / **Falsifiability** (the test that would have caught "wired but
  disconnected") / **Upholds** (constitution only: the specific clause enforced).
- **Surface Area** — table: component | file:line | change required | scenario(s) satisfied.
  The definitive list: what's not on it will not be touched; implementers flag gaps before
  writing code.
- **Out of Scope** — explicit, including any carve-out that tensions with a law and the
  accepted stance.
- **Constitution Alignment** (only when one exists) — laws touched, inference log with source
  clauses, carve-outs/tensions, stance vs. minimum.
- **Clarifying Questions** — or "None — proceed directly to implementation."

**Quality gate before publishing**: every scenario is a distinct entry point; every surface-area
row traces to a scenario; behavioral intent describes what the user observes; the coverage
statement is present and honest; suspicious dead-code is flagged; everything grounds in the
intent summary — flag gaps rather than guess; with a constitution, every scenario has an
`Upholds:` clause citation and every touched law appears in at least one.

**Phase C — Publish.** `comment`: if a prior comment starting
`## Refined Spec (generated by /refine-issue)` exists, PATCH it in place — re-runs must never
append a duplicate, so downstream tooling always sees exactly one authoritative spec.
Otherwise post it. `create`: new issue titled from the Job Statement. `none`: skip.

Return only: `ISSUE_URL`, `SPEC_PATH`, `ENTRY_POINTS`, `SURFACE_AREA`, `SEARCH_COVERAGE`.
Your final message is a status report: `DONE` or `BLOCKED(reason)`, plus what changed. If you
are not blocked, do not ask questions — proceed and report.

## Step 3 — Report

Print, from the Spec agent's returned fields only (do not re-read the spec):
input, intent-summary path, spec URL, search coverage, entry-point and surface-area counts,
and "Review the spec on GitHub and approve or request changes there."

## Constraints

- Never write or modify source files; never open branches, commits, or PRs.
- Never assume the issue author has named all the components that need to change.
- The spec is a recommendation, not a binding contract — the user reviews before `/fix-issue`.
- The interview must not produce a spec; the Spec agent must not conduct dialogue.
- If blocked or uncertain about repo structure, stop and report rather than guessing.
