---
name: fix-issue
description: "Implement a GitHub issue end-to-end: assess tier, plan, optionally draft an ADR for approval, code in tier-shaped waves, validate, and leave a draft PR with full documentation. Accepts --tier, --require-adr, --worktree, --base. Run /pr-review-cycle afterwards."
disable-model-invocation: true
---

# Fix Issue

## Args

`/fix-issue <issue> [--tier <N>] [--require-adr] [--worktree] [--base <branch>]`

- `issue`: issue number or full URL.
- `--tier <N>`: force tier 1/2/3, skipping assessment (also positional: `/fix-issue 42 2`).
- `--require-adr`: force ADR drafting regardless of tier.
- `--worktree`: build on a git worktree in a sibling directory instead of checking out in the
  main repo — for parallel issue work or when the repo must stay on its current branch.
- `--base <branch>`: override base-branch detection (e.g. an epic branch; the PR targets it too).

## Setup

1. **Repo**: from the URL, or detect (`git remote -v`, prefer `upstream` over `origin`).
   **Always confirm the detected repo with the user before fetching the issue.**
2. **Base branch**: `--base` must exist on origin (verify, else stop). Otherwise auto-detect —
   **always prefer `dev`/`develop` over `main`**, even when `main` is the GitHub default:
   `dev` is where feature branches merge; `main` is for releases. Never hardcode `main`.
3. **Fetch the issue** (`gh issue view <n> --json number,title,body,labels,comments,assignees`).
   If unassigned, self-assign (`--add-assignee @me`); if that fails, stop — do not work an
   issue that cannot be assigned.
4. **Git root** (mount-layout safe):
   ```bash
   GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
   if [ -z "$GIT_ROOT" ]; then
     for candidate in /workspaces/* "$HOME"/repos/* "$HOME"/projects/* "$HOME"/*; do
       [ -d "$candidate/.git" ] && { GIT_ROOT="$candidate"; break; }
     done
   fi
   ```
   All git commands run from `GIT_ROOT` (later: from `WORK_DIR`).
5. **Scratch dir**: require `$GIT_ROOT/.agent-work/`; if missing, stop and tell the user to
   create it and add it to `.git/info/exclude`. All artifacts go there; never committed.
6. **Clean tree required**: uncommitted changes → stop and warn. Never mix pre-existing
   changes with issue work.
7. **Branch before research** — always from fresh `origin/<BASE>`, never from whatever branch
   was active:
   ```bash
   git -C "$GIT_ROOT" fetch origin
   # normal:   checkout origin/<BASE>; checkout -b fix/issue-<n>-<slug>; WORK_DIR=$GIT_ROOT
   # worktree: WORKTREE_PATH="$(dirname "$GIT_ROOT")/$(basename "$GIT_ROOT")-issue-<n>"
   #           git worktree add "$WORKTREE_PATH" -b fix/issue-<n>-<slug> origin/<BASE>
   #           WORK_DIR=$WORKTREE_PATH
   ```
   Branch-level git ops use `WORK_DIR`; artifacts always go to `$GIT_ROOT/.agent-work/`
   (the shared backing store in both modes).
8. **Open a draft PR immediately** (`git push -u`, `gh pr create --draft`, body
   "Closes #<n> — work in progress"). Capture `PR_URL`/`PR_NUMBER` for every status post.
   **The PR stays in draft for the whole session** — review and the ready-flip happen
   separately via `/pr-review-cycle` and the user.

## Scope Creep (user interjections)

**The issue is the single source of truth for what this session implements.**

- **Early** (before the Planner is spawned): pause. Identify the delta from the issue as
  written. Offer to help update the issue on GitHub, then stop and have the user start a
  fresh session from the complete spec. If it's clarifying context, not new scope, proceed.
- **Late** (during/after planning): do not incorporate. Push back: the plan is in progress;
  new requirements mid-flight break the validation/review/documentation pipeline. Complete
  the current scope; note deferred items in the final summary for a follow-up issue. If the
  user insists, still finish the current plan first.
- Why: mid-process scope changes give downstream steps (Documentation Agent, PR body) an
  inconsistent view of planned-vs-implemented, producing missing or wrong artifacts.

## Step 1 — Tier Assessment

`--tier` given → use it (`TIER_RATIONALE="user-supplied override"`, `ADR_REQUIRED` from
`--require-adr`). Otherwise spawn a small assessment agent with the fetched issue:

**Tier signals** — Tier 1: one module; bug fix / small feature / config / docs; requirements
fully described; diff < ~200 lines. Tier 2: 2–4 loosely coupled areas or layers (frontend +
backend, API + tests); clear requirements across multiple domains; diff 200–800. Tier 3:
multiple subsystems; open questions / "TBD" / "we need to decide" in the issue; changes to
shared interfaces, data models, or config; diff > 800 or significant unknowns.

**ADR_REQUIRED=true** when Tier ≥ 2, or the issue mentions changing shared config, public
APIs, or data models (`SHARED_INTERFACE_SUSPECTED`). Rationale: anything spanning multiple
domains has enough cross-cutting reach that a one-paragraph ADR is cheap insurance; Tier 1
is self-contained enough to skip. Also collect `OPEN_QUESTIONS` — decisions not resolvable
from the issue text. The agent returns `{tier, rationale, adrRequired, adrReason,
openQuestions}` as structured output.

## Step 2 — Planning

Spawn a **Planner** (sonnet, read-only research; only file write is the plan). Context
bootstrap first: global + repo `CLAUDE.md`, `docs/agent_index.md` if present (**if the index
lists an existing capability that matches, the plan must reuse it, never reimplement**). Grep
symbols from the issue; for files > 300 lines read only the sections Grep identified.

Output `.agent-work/ISSUE_<n>_PLAN.md`: summary; affected-files table (file / change type /
owner); **file ownership table** (every file has exactly one owning agent — Coders, Tester,
Integrator for shared/wiring files); task list in waves (Wave 1 parallel, Wave 2+ sequential);
binary, verifiable acceptance criteria; open questions. Tier 1 plans may be one wave with one
Coder — **do not add agents for the sake of it**. Tier 2/3 Planners list open questions but
never make architecture decisions — those belong to the Architect.

**Post the pre-implementation comment to the issue** — the durable record of the tier choice
and the ADR-or-skip decision. Both fields are required every time, even Tier 1: draft PR URL,
`Tier: <n>` + rationale, `Architecture review: Skipping (ADR_REQUIRED=false…)` or
`Required (<reason>)`, and open questions if any.

## Step 2b — ADR gate (when ADR_REQUIRED)

Spawn an **Architect** (opus, read-only + ADR). It reads the plan + issue, researches each
open question in the code, and writes `.agent-work/ISSUE_<n>_ADR.md`: context; per decision
the options with pros/cons and a recommendation; consequences; updated acceptance criteria.

**STOP.** Post the decisions to the issue as checkbox options (one block per decision,
recommended option marked, "Other" always offered) and tell the user to pick options and
comment `APPROVED` or `REJECT`. **No implementation agent is spawned until the user responds
on the issue.** On APPROVED: verify every decision has exactly one box checked — partial
approval is not approval; post what's unresolved and wait again. Then mark the ADR ACCEPTED,
apply overrides, and post the approved decisions back to the issue. On REJECT: stop.

## Step 3 — Implementation

Each task from the plan spawns its assigned agent (sonnet) with the context bootstrap plus a
task spec: objective, files to read, prior artifacts, deliverable, **scope = its ownership
row only**, out of scope = everything else, acceptance criteria. Agents never edit outside
their scope, never make undocumented architecture decisions, never push or open PRs, never
refactor unrelated code.

- **Tier 1**: one Coder → binary checks → commit.
- **Tier 2**: Wave 1 (Coders + Tester) in parallel → checks pass → commit → Integrator →
  checks → commit.
- **Tier 3**: per wave: spawn parallel, wait, run checks — on failure re-assign the failing
  files to the same agent with the error (max 1 retry, then stop and report) — commit, only
  then advance. Integrator last.

Commit after each wave — only that wave's files, **never `git add -A`** (artifacts live in
`.agent-work/`). Message: `fix(#<n>): <what this wave did>`.

## Step 4 — Validation

Binary checks in order, stop on failure: compile, typecheck, lint, tests (adapt to the
project's toolchain). On failure re-assign to the responsible agent with the error output —
max 3 retries, then stop and report; **never commit broken code**. If a Coder's output is
uncertain, spawn a Checker with the code + task spec + criteria (pass/fail, max 3 rounds).

## Step 5 — Push + PR body

Commit any straggler changes (specific files). Checklist before pushing: all binary checks
pass; all plan acceptance criteria met; `git diff <BASE>...HEAD --name-only` shows only
in-scope files. Push; update the PR title/body (What changed / Tier & approach / acceptance
criteria checked off). PR remains draft.

**Documentation Agent** (sonnet, read-only on source): reads the full branch diff *and the
surrounding context of every changed file* (the whole function/class plus callers one level
up), the issue, plan, and ADR. If `docs/agent_index.md` exists: add entries for new reusable
capabilities, edit existing entries in place (never append duplicates), update
`docs/modules/<name>.md` with non-obvious usage/constraints only, and commit that separately
(`docs: update agent index for issue #<n>`). Then rewrite the PR body as up to 2 pages of
flowing prose for a senior engineer who has not read the issue: executive summary; per-function
walkthrough with invariants; component interaction; **default execution path as before/after**
(required whenever a pipeline, handler chain, or multi-step process changed); edge cases now
handled; what was intentionally not changed (per ADR) so reviewers don't wonder. No raw diff,
no boilerplate padding; omit sections that don't apply.

Diagrams: the Documentation Agent never writes Mermaid — it leaves
`<!-- MERMAID: plain-English description -->` placeholders; a small agent (haiku) renders
each: `graph TD`/`LR`, plain-text node labels (no quotes/parens/specials inside `[]`),
`-->` / `-.->` edges, under 15 nodes, brackets balanced. Invalid output → omit the diagram
and note *(Diagram omitted — see prose above.)*

## Final Summary

Branch, tier + rationale, PR URL (and worktree removal command if used), agents used,
acceptance criteria with any unmet flagged, next step: PR is in draft — run
`/pr-review-cycle <PR_NUMBER>`, then mark ready manually when satisfied.

## Constraints (all agents)

- One PR per session; one issue per PR unless tightly coupled.
- Never touch files outside assigned scope; never make architecture decisions without an
  approved ADR; never skip binary checks before committing.
- Never merge, never force-push, never commit to main/master.
- Minimal targeted changes only — no refactoring beyond the issue's direct cause.
- If blocked or uncertain, stop and report rather than guess; always include the PR URL when
  handing to a human.
- Every subagent's final message is a status report: `DONE` or `BLOCKED(reason)` plus what
  changed — never a question when unblocked.
