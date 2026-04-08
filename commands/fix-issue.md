# Fix Issue

## Setup

Parse arguments — format is: `/fix-issue <issue> [tier] [--worktree] [--base <branch>]`
- `issue`: required. GitHub issue number (e.g. `42`) or full URL.
- `tier`: optional override: `1`, `2`, or `3`. If omitted, tier is auto-detected.
- `--worktree`: optional flag. If present, create a `git worktree` for the feature branch instead of checking it out in the main repo. The worktree is created as a sibling directory (`../repo-name-issue-<number>/`). Useful when multiple issues are being worked in parallel or when the main repo must stay on its current branch.
- `--base <branch>`: optional. Override the base branch instead of auto-detecting `dev`/`develop`/`main`. Used by `/resolve-epic` to target an epic branch. When set, the PR also targets this branch.

Strip `--worktree` and `--base <branch>` from the argument list before parsing `issue` and `tier`. Set `WORKTREE_MODE=true` if `--worktree` was present, otherwise `WORKTREE_MODE=false`. Set `BASE_OVERRIDE` to the branch name if `--base` was present, otherwise leave unset.

Examples:
- `/fix-issue 42` → fetch issue #42, auto-detect tier, normal checkout
- `/fix-issue 42 2` → force Tier 2 regardless of auto-detection
- `/fix-issue 42 --worktree` → fetch issue #42, auto-detect tier, use a git worktree
- `/fix-issue 42 2 --worktree` → force Tier 2, use a git worktree
- `/fix-issue https://github.com/org/repo/issues/42` → full URL form
- `/fix-issue 42 --base epic/601-rendering-pipeline` → branch off and PR into the epic branch

Read the agent team guide before doing anything else:
```
~/.claude/guides/agent-team-guide.md
```

### Repo detection

If `issue` is a full URL, extract `owner/repo` from the URL — no detection needed.

If `issue` is just a number, detect the repo:
```bash
git remote -v
gh repo view --json nameWithOwner
```

From those results, determine the most likely `owner/repo`:
- If the working directory has exactly one GitHub remote, use it.
- If there are multiple remotes (e.g. `origin` + `upstream`), prefer `upstream` if present
  (fork workflow), otherwise prefer `origin`.
- If there is no git remote or the directory is not a git repo, check whether the conversation
  context mentions a repo name or URL.

**Always confirm before fetching the issue.** Present your guess to the user:

```
Repo detected: <owner/repo> (from <source: git remote origin | git remote upstream | gh repo view | conversation context>)

Proceed with issue #<number> in <owner/repo>? [yes / no / different-repo]
```

Wait for the user to confirm or correct before continuing.

If no repo can be guessed at all, ask:
```
Which GitHub repo should I look up issue #<number> in? (e.g. owner/repo)
```

Once confirmed, set `REPO=<owner/repo>` for all subsequent `gh` calls.

### Base branch detection

If `BASE_OVERRIDE` is set (from `--base`), use it directly:

```bash
git fetch origin
git rev-parse --verify origin/$BASE_OVERRIDE
```

If the branch does not exist on the remote, stop and report: "Base branch `<BASE_OVERRIDE>` does not exist on origin." Set `BASE=$BASE_OVERRIDE` and skip auto-detection.

If `BASE_OVERRIDE` is **not** set, auto-detect. **Always prefer `dev` (or `develop`) over `main` for development work** — even if `main` is the GitHub default branch. `dev` is where feature branches are merged; `main` is for releases only.

```bash
git fetch origin
# Check for dev/develop branches on the remote
git ls-remote --heads origin dev develop 2>/dev/null
```

- If `dev` exists on the remote → `BASE=dev`
- Else if `develop` exists → `BASE=develop`
- Else → `BASE=main` (or `master` if `main` does not exist)

Confirm:
```bash
git rev-parse --verify origin/$BASE
```

Set `BASE` for all subsequent commands. **All references to the base branch throughout
this spec use `<BASE>` — never hardcode `main`.**

---

Fetch the issue:
```bash
gh issue view <number> --repo <owner/repo> --json number,title,body,labels,comments,assignees
```
If `gh` is unavailable, stop and tell the user to install the GitHub CLI.

**Check assignment:** inspect the `assignees` field from the response.
- If the issue is already assigned, note who it is assigned to and proceed.
- If unassigned, attempt to self-assign:
  ```bash
  gh issue edit <number> --repo <owner/repo> --add-assignee @me
  ```
  If the command fails, stop and report the error to the user — do not proceed until the issue is assigned.

### Git root detection (dev container safe)

Before any git operation, resolve the git working tree root. This is required because
in dev containers the shell may start at `/workspaces` which is above the repo mount:

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$GIT_ROOT" ]; then
  # Try common locations: dev container mount points, home repos dir, home itself
  for candidate in /workspaces/* "$HOME"/repos/* "$HOME"/repo/* "$HOME"/projects/* "$HOME"/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
fi
```

If `GIT_ROOT` is still empty, stop and tell the user:
"Could not find a git repository. Make sure you are inside a repo or pass the repo path."

**All `git` commands in this spec must run from `GIT_ROOT`** — either `cd "$GIT_ROOT"` first,
or use `git -C "$GIT_ROOT" <command>`.

Set up the `.claude-work/` scratch directory for all planning and review artifacts:

```bash
mkdir -p "$GIT_ROOT/.claude-work"
grep -qxF '.claude-work/' "$GIT_ROOT/.git/info/exclude" \
  || echo '.claude-work/' >> "$GIT_ROOT/.git/info/exclude"
```

All artifact files produced during this session are written to `$GIT_ROOT/.claude-work/`.
They are gitignored via `.git/info/exclude` and are never committed or pushed.

Get current repo context:
```bash
git -C "$GIT_ROOT" branch --show-current
git -C "$GIT_ROOT" log --oneline -10
```

Verify the working tree is clean:
```bash
git status --short
```
If there are uncommitted changes, stop and warn the user — do not mix pre-existing changes with issue work.

Sync to the base branch and create the feature branch now, before any codebase research.

`<slug>` is a 2–4 word kebab-case summary of the issue title.

**Normal mode** (`WORKTREE_MODE=false`):
```bash
git -C "$GIT_ROOT" fetch origin
git -C "$GIT_ROOT" checkout origin/<BASE>
git -C "$GIT_ROOT" checkout -b fix/issue-<number>-<slug>
WORK_DIR="$GIT_ROOT"
```

**Worktree mode** (`WORKTREE_MODE=true`):
```bash
git -C "$GIT_ROOT" fetch origin
WORKTREE_PATH="$(dirname "$GIT_ROOT")/$(basename "$GIT_ROOT")-issue-<number>"
git -C "$GIT_ROOT" worktree add "$WORKTREE_PATH" \
  -b fix/issue-<number>-<slug> origin/<BASE>
WORK_DIR="$WORKTREE_PATH"
```

In both modes, `WORK_DIR` is the directory agents and all subsequent `git` commands operate from. After this point, use `git -C "$WORK_DIR"` (not `$GIT_ROOT`) for all branch-level operations (diff, add, commit, push). Artifacts always go to `$GIT_ROOT/.claude-work/` regardless of mode — this is the shared backing store.

All Planner codebase research happens from this branch (= latest `origin/<BASE>`), never from whatever branch was active before.

---

## Handling User Interjections (Scope Creep)

During execution, the user may send follow-up messages that add requirements, change direction,
or expand the scope beyond what the GitHub issue describes. **The issue is the single source of
truth for what this session implements.** Handle interjections based on timing:

### Early interjection (before planning begins — still reading/fetching the issue)

If the user adds new requirements or context before the Planner agent has been spawned:

1. **Pause** — do not start planning yet.
2. Acknowledge what the user said and identify the delta from the issue as written.
3. Ask:
   ```
   It sounds like you want to expand the scope beyond what's currently in issue #<number>.

   The best workflow is:
   1. Update the issue on GitHub with the additional requirements.
   2. Start a new /fix-issue session so the Planner works from the complete spec.

   Would you like to update the issue now? I can help draft the additions. Or if this
   is just clarifying context (not new scope), let me know and I'll proceed as-is.
   ```
4. If the user confirms they want to update the issue, help them draft the update and post it
   via `gh issue edit` or `gh issue comment`. Then **stop** — do not continue with implementation.
   Tell the user to start a fresh `/fix-issue` session.
5. If the user says it is just clarification (not new scope), proceed normally.

### Late interjection (during or after planning)

If the user sends new requirements after the Planner has been spawned or after planning is
complete (during Steps 2–6):

1. **Do not incorporate the new scope.** The plan is already set and agents may already be running.
2. Push back clearly:
   ```
   The plan for issue #<number> is already in progress. Adding new requirements mid-flight
   risks breaking the structured workflow (validation, review, documentation).

   I'll complete the current scope as planned. For the additional requirements, please either:
   - Update the issue and run /fix-issue again after this PR lands, or
   - Open a new issue for the extra work.
   ```
3. Continue executing the original plan to completion.
4. If the user insists, note their request but **still complete the current plan first** — then
   mention the deferred items in the PR's "Outstanding items" section.

### Why this matters

Incorporating ad-hoc scope changes mid-process causes downstream steps (Documentation Agent,
Reviewer, PR body generation) to receive an inconsistent view of what was planned vs. what was
implemented. This leads to missing or incomplete artifacts — the structured pipeline depends on
the plan being stable from Step 2 onward.

---

## Subagent Context Bootstrap

When spawning any subagent that reads or modifies source code (Planner, Architect, Coder, Tester, Integrator, Reviewer, Documentation Agent), prepend these instructions to its prompt:

> **Context bootstrap** (do this before your main task):
> 1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions) if they exist. Follow all instructions — repo instructions override global ones.
> 2. Read codebase index files if present:
>    - `.codesight/CODESIGHT.md` at `$GIT_ROOT`
>    - `docs/agent_index.md` at `$GIT_ROOT`
>    - If no agent index was found at the above path, glob for `**/agent_index.md` at `$GIT_ROOT` and read any match.

Do **not** add this bootstrap to narrow utility agents (Mermaid Agent).

---

## Step 1 — Assess Complexity

Read the issue title, body, and comments in full. Then assess:

**Signals for Tier 1 (simple):**
- Touches one module or area
- Bug fix, small feature, config or docs change
- Requirements fully described in the issue
- Estimated diff < ~200 lines

**Signals for Tier 2 (medium):**
- Touches 2–4 loosely coupled areas or layers (e.g. frontend + backend, API + tests)
- Requirements clear but spans multiple files/domains
- Estimated diff 200–800 lines
- May still warrant an Architect if the Planner surfaces open questions (see Step 2b)

**Signals for Tier 3 (complex):**
- Spans multiple subsystems or teams
- Issue contains open questions, "TBD", or phrases like "we need to decide"
- Requires changes to shared interfaces, data models, or config
- Estimated diff > 800 lines, or significant unknowns

If a `tier` argument was passed, use that. Otherwise state your assessment and the signals that drove it, then proceed.

---

## Step 2 — Planning

Regardless of tier, spawn a **Planner agent** first (`model: "opus"`).

### Planner agent instructions

Role: read-only research. No file writes except the plan document.

1. Read the issue (already fetched above — pass it in full).
2. Read project instructions and codebase index files:
   - Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions) if they exist. Follow all instructions — repo instructions override global ones.
   - If `.codesight/CODESIGHT.md` exists at `$GIT_ROOT`, read it in full. It provides a high-level map of the codebase architecture and module responsibilities — use it to orient all subsequent file searches.
   - If `docs/agent_index.md` exists at `$GIT_ROOT`, read it in full. Use it to identify existing capabilities relevant to the issue — if a match is found, the plan must use that capability rather than reimplementing it.
   - If no agent index was found at `docs/agent_index.md`, glob for `**/agent_index.md` at `$GIT_ROOT` and read any match.
3. Search the codebase for all affected files:
   - Grep for symbols, function names, patterns mentioned in the issue
   - Read the files most likely involved
3. Produce `.claude-work/ISSUE_<number>_PLAN.md` containing:
   ```markdown
   # Plan: <issue title> (#<number>)

   ## Summary
   [2–3 sentences: what needs to change and why]

   ## Affected Files
   | File | Change type | Owned by |
   |---|---|---|
   | path/to/file | modify / create / delete | Coder A / Integrator |

   ## File Ownership Table
   | Agent | Files |
   |---|---|
   | Coder A | ... |
   | Coder B | ... |
   | Tester | test files |
   | Integrator | shared/wiring files |

   ## Task List
   ### Wave 1 (parallel)
   - Task 1.1: [objective] — Coder A — files: [list]
   - Task 1.2: [objective] — Coder B — files: [list]
   - Task 1.3: [objective] — Tester — files: [list]

   ### Wave 2 (sequential, depends on Wave 1)
   - Task 2.1: [objective] — Integrator

   ## Acceptance Criteria
   - [ ] <binary, verifiable criterion>
   - [ ] <binary, verifiable criterion>

   ## Open Questions
   [List any decisions or ambiguities not resolvable from the issue alone]
   ```
4. For **Tier 1**: the plan may show a single wave with one Coder. That is correct — do not add agents for the sake of it.
5. For **Tier 2 or Tier 3**: list open questions but do not make architecture decisions — those are deferred to the Architect if questions exist.

After the Planner finishes, read `.claude-work/ISSUE_<number>_PLAN.md`.

**Post pre-implementation status to the issue:**
```bash
gh issue comment <number> --repo <owner/repo> --body "$(cat <<'EOF'
## Pre-implementation check

[If Open Questions section is non-empty:]
The following decisions need to be resolved before implementation begins:

<paste Open Questions from the plan>

Proceeding to architecture review (Tier 3) / awaiting decisions before coding starts.

[If Open Questions section is empty:]
No open questions. Plan is complete — proceeding directly to implementation.
EOF
)"
```

**For Tier 2 or Tier 3:** if the plan lists open architecture questions, proceed to Step 2b before spawning any implementation agents. Tier 2 issues with clear requirements and no open questions skip Step 2b entirely.

---

## Step 2b — Architecture (Tier 2 with open questions, or Tier 3)

Spawn an **Architect agent** (`model: "opus"`).

### Architect agent instructions

Role: read-only research + produce ADR. No implementation file writes.

1. Read `.claude-work/ISSUE_<number>_PLAN.md` and the full issue.
2. For each open question, research options by reading relevant code, docs, and existing patterns.
3. Produce `.claude-work/ISSUE_<number>_ADR.md`:
   ```markdown
   # ADR: <issue title> (#<number>)

   ## Status: PROPOSED

   ## Context
   [What problem is being solved and what constraints apply]

   ## Decision 1: <topic>
   **Options:**
   - Option A: <description> — pros / cons
   - Option B: <description> — pros / cons
   **Recommendation:** Option X because ...

   ## Consequences
   [Impact on files, APIs, data models, tests, performance]

   ## Updated Acceptance Criteria
   - [ ] ...
   ```

**STOP after the Architect completes.** Post the ADR decisions as checkboxes directly on the GitHub issue so the user can review and select options there:

```bash
gh issue comment <number> --repo <owner/repo> --body "$(cat <<'EOF'
## Architecture Decision Record — Review Required

Please select one option per decision by checking the box, then comment "APPROVED" (or "REJECT" to stop).

---

### Decision 1: <topic>
> <context sentence from ADR>

- [ ] **Option A** — <one-line description> _(recommended)_
- [ ] **Option B** — <one-line description>
- [ ] **Option C** — <one-line description> _(if applicable)_
- [ ] **Other** — describe in a follow-up comment

---

### Decision 2: <topic>  _(repeat block for each decision)_
...

---

_Check one box per decision. Add a comment if you chose "Other" or want to override. Comment **APPROVED** when done, or **REJECT** to stop and reopen._
EOF
)"
```

Then inform the user in chat:

```
Architecture decisions have been posted to issue #<number> as checkboxes.
Please review and select your preferred options directly on the issue, then comment APPROVED or REJECT.
```

**Do not spawn any implementation agents until the user has responded on the issue.**

Poll for the user's response by checking issue comments. When a comment containing "APPROVED" or "REJECT" is found:
- **APPROVED**: read the checkbox states from the ADR comment to determine which options were selected. Update `.claude-work/ISSUE_<number>_ADR.md` status to `ACCEPTED` and revise per any overrides or "Other" comments.
- **REJECT**: stop and report to the user in chat. Do not proceed with implementation.

**Post approved decisions to the issue:**
```bash
gh issue comment <number> --repo <owner/repo> --body "$(cat <<'EOF'
## Architecture decisions approved

The following decisions were reviewed and approved before implementation:

<paste Decision sections from the ADR, including chosen option and rationale>

Implementation is now proceeding.
EOF
)"
```

---

## Step 3 — Implementation

Use the task list from `.claude-work/ISSUE_<number>_PLAN.md` (updated with ADR outcomes if Tier 3).

For each task, spawn the assigned agent with the full task spec. Use `model: "sonnet"` for Coder, Tester, and Integrator agents; use `model: "opus"` for Reviewer agents:

```
Issue: #<number> — <title>
Plan: .claude-work/ISSUE_<number>_PLAN.md
ADR: .claude-work/ISSUE_<number>_ADR.md (Tier 3 only, else N/A)

Objective: [from plan task list]

Input:
  - Files to read: [from file ownership table]
  - Prior artifacts: [outputs from dependency tasks, if any]

Output:
  - Deliverable: [files to produce or modify]

Scope (files you may edit):
  - [from file ownership table — this agent's row only]

Out of scope (do not touch):
  - All files not in your Scope list above

Acceptance criteria:
  - [from plan acceptance criteria relevant to this task]

Tools allowed: Read, Edit, Write, Bash, Grep, Glob

Do not:
  - Edit files outside your Scope list
  - Make architecture decisions not covered by the plan/ADR
  - Open PRs or push branches
  - Refactor code unrelated to this task
```

### Tier 1 — single Coder, then Reviewer

Spawn agents sequentially:
```
Coder → [binary checks] → Reviewer
```

### Tier 2 — parallel Coders + Tester, then Integrator

Spawn Wave 1 agents in parallel. Wait for all to finish.
Run binary checks (compile, lint, typecheck, tests).
If checks pass, spawn Integrator. After integration, spawn Reviewer.

### Tier 3 — task queue with waves

For each wave in order:
1. Spawn all agents in the wave in parallel.
2. Wait for all to finish.
3. Run binary checks. If checks fail, stop: re-assign failing files to the same agent with the error as context (max 1 retry). If still failing, stop and report to user.
4. Only advance to the next wave after all checks pass.
After all waves: Integrator, then Reviewers in parallel (correctness / security / performance — one lens per invocation).

---

## Step 4 — Validation

After all implementation agents complete:

**Binary checks (run in order, stop on failure):**
```bash
# adapt commands to the project's actual toolchain
<compile command if applicable>
<typecheck command if applicable>
<lint command if applicable>
<test command>
```

If any check fails: identify the failing file(s), re-assign to the responsible agent with the error output. Max 3 retries per failure. If still failing after 3 retries, stop and report to user — do not commit broken code.

**Maker-checker (if a Coder's output is uncertain):**
- Spawn a separate Checker agent with: the produced code, the task spec, and the acceptance criteria
- Checker returns: pass / fail + specific failure description
- Max 3 rounds. On 3rd failure, escalate to orchestrator.

---

## Step 5 — Reviewer

After all checks pass, spawn the **Reviewer agent** (`model: "opus"`).

### Reviewer agent instructions

Role: read-only. Do NOT make any file changes.

1. Read all files changed in this branch:
   ```bash
   git diff <BASE>...HEAD --name-only
   git diff <BASE>...HEAD
   ```
2. Read the original issue and acceptance criteria from the plan.
3. For each finding, write:
   ```
   ### [SEVERITY: critical|major|minor] <short title>
   **File**: path/to/file:line
   **Problem**: what is wrong and why it matters
   **Fix**: concrete recommendation
   ```
4. Categories to check: correctness, missing tests, security, edge cases, scope creep (changes beyond the issue), breaking changes.
5. Output `.claude-work/ISSUE_<number>_REVIEW.md`.

After the Reviewer finishes:
- **Critical or major findings**: apply targeted fixes, re-run binary checks, then re-run Reviewer (max 2 review iterations).
- **Minor findings only**: apply at discretion; do not re-run Reviewer.
- If after 2 review iterations critical/major findings remain, include them in the PR description as known outstanding items.

---

## Step 6 — Commit and Open PR

Commit all changes:
```bash
git add <only the files changed for this issue — never git add -A>
git commit -m "$(cat <<'EOF'
fix(#<number>): <concise description of what was done>

Closes #<number>

[one-line summary of each logical change if multiple areas touched]

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

Verify PR checklist before pushing:
- [ ] All binary checks pass
- [ ] All acceptance criteria from the plan are met
- [ ] Reviewer findings addressed or documented
- [ ] Only files in-scope for this issue were modified (`git diff <BASE>...HEAD --name-only`)

Push and open PR:
```bash
git push -u origin fix/issue-<number>-<slug>
gh pr create --repo <owner/repo> \
  --base <BASE> \
  --title "fix(#<number>): <title>" \
  --body "$(cat <<'EOF'
Closes #<number>

## What changed
[bullet summary of implementation approach]

## Tier / approach
Tier <N> — [Planner → Coder → Reviewer | parallel Coders + Integrator | DAG with N waves]

## Acceptance criteria
- [ ] <criterion>
- [ ] <criterion>

## Outstanding items
[any minor review findings deferred, or "None"]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Step 6b — PR Documentation Agent

After the PR is open, spawn a **Documentation Agent** (`model: "sonnet"`) to update the PR body with a detailed human-readable report. This runs before `/review-fix` so reviewers have full context when they open the PR.

### Documentation Agent instructions

Role: read-only research + agent doc updates + PR update. Do not modify any source files.

> **Intermediate artifacts:** Writing intermediate files before committing to git is not preferred. If the agent does need to stage notes or drafts, it must write them under `.claude-work/` (e.g. `.claude-work/ISSUE_<number>_doc_draft.md`). Never write scratch files outside `.claude-work/`.

1. Read every file changed in this branch:
   ```bash
   git diff <BASE>...HEAD --name-only
   git diff <BASE>...HEAD
   ```
2. Read the original issue body and comments in full.
3. Read `.claude-work/ISSUE_<number>_PLAN.md` and (if present) `.claude-work/ISSUE_<number>_ADR.md`.
4. Read the surrounding context for every changed file — not just the diff lines, but the full function or class that was modified, and any callers or dependents one level up.

**Agent-facing documentation (do this before the PR update):**

If `docs/agent_index.md` does not exist at `$GIT_ROOT`, skip this section entirely.

If it exists:
- For any new reusable capability introduced by this PR, add an entry to `docs/agent_index.md`:
  ```markdown
  ## <Capability Name>
  Path: `<path to main file or directory>`
  Doc: `docs/modules/<name>.md`
  Tags: <comma-separated terms a future agent would search for>
  ```
- For any existing capability that was modified, updated, or superseded: edit the existing entry in place — update the path, tags, or doc pointer as needed. Do not append a duplicate.
- Create or update `docs/modules/<name>.md` for each affected capability. Contents: non-obvious usage, extension pattern, constraints, what not to do. Do not summarise what the code already shows.
- Commit these changes before updating the PR body:
  ```bash
  git add docs/agent_index.md docs/modules/
  git commit -m "docs: update agent index for issue #<number>"
  ```

Produce a PR description that is **up to 2 pages** of flowing technical prose. Update the PR:

```bash
gh pr edit <PR_NUMBER> --body "$(cat <<'EOF'
Closes #<number>

## What changed

<2–4 sentence executive summary: what the issue was, what the fix does, and why this approach was chosen.>

## Implementation walkthrough

### New / modified functions

For each new or significantly changed function or class, write a paragraph:
- **`function_name(params)` in `path/to/file.py`** — what it does, what invariant it
  establishes, what it returns, and any non-obvious design decisions.
- Include its relationship to callers and callees.

### How components interact

If multiple functions or modules were added or changed, describe how they wire together.
**Do not write Mermaid diagrams yourself.** Instead, write a plain-English description of the
interaction (nodes, edges, and annotations) and delegate diagram generation to the Mermaid Agent
(see below). Insert a placeholder where the diagram should go:

```
<!-- MERMAID: description of the diagram to generate -->
```

The Mermaid Agent will replace each placeholder with a validated ```` ```mermaid ```` block.

### Default execution path

Describe how the "happy path" changed. Use a before/after format:

**Before**: `A → B → C` — explain what each step was doing and why it was insufficient.

**After**: `A → B → C → D → E` — explain what the new steps add and what invariant is
now satisfied that wasn't before. If the path branched or shortened, describe that too.

### Edge cases and error handling

List any error conditions that are now explicitly handled that weren't before, and what
behaviour the caller can expect in those cases.

### What was intentionally not changed

If the issue touched an area where a change was considered but rejected (e.g. per ADR),
note it briefly so reviewers don't wonder.

## Tier / approach

Tier <N> — <Planner → Coder → Reviewer | parallel Coders + Integrator | DAG with N waves>

## Acceptance criteria

<from .claude-work/ISSUE_<number>_PLAN.md>
- [x] <criterion>
- [x] <criterion>

## Outstanding items

<any minor review findings deferred, or "None">

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Guidelines for the Documentation Agent:**
- Write for a senior engineer who has not read the issue. They should understand the full change from the PR body alone.
- **Never write Mermaid syntax directly.** Use `<!-- MERMAID: ... -->` placeholders and let the Mermaid Agent handle diagram generation. Request a diagram when a call graph, data flow, or state transition is being described — not for trivial single-function changes.
- Do not reproduce raw diff. Explain intent and behaviour in prose.
- Do not pad with boilerplate. If a section does not apply (e.g. no new functions), omit it.
- Length target: 1–2 pages. Shorter is fine if the change is genuinely simple; do not inflate.
- The "Default execution path" section is required whenever a pipeline, middleware chain, request handler, or multi-step process was modified.

### Mermaid Agent

After the Documentation Agent produces the PR body (with `<!-- MERMAID: ... -->` placeholders),
spawn a **Mermaid Agent** (`model: "haiku"`) for each placeholder.

#### Mermaid Agent instructions

Role: generate a single valid Mermaid diagram. No file writes, no source code reads.

Input: the plain-English description from the placeholder.

Rules:
1. Use `graph TD` (top-down) or `graph LR` (left-right) — pick whichever fits the flow better.
2. **Node labels must be plain text only.** No quotes, no parentheses, no special characters
   inside `[]` labels. Use short descriptive names:
   - Good: `A[Generate questions]`
   - Bad: `A["_generate_questions() — Sonnet: what would a viewer ask?"]`
3. If a node needs detail (function name, annotation), put it on a separate line using a
   subgraph label or an annotation comment — not inside the node bracket.
4. Use `-->` for normal edges and `-.->` for optional/fallback edges. Add edge labels with
   `-->|label|` when the relationship is not obvious.
5. Keep diagrams under 15 nodes. If the flow is larger, split into multiple diagrams or
   simplify by grouping related steps.
6. **Validate the output**: paste the generated Mermaid into a fenced code block and
   mentally parse it node-by-node. Every `[` must close with `]`, every `(` with `)`.
   No unmatched brackets. No backslash escapes.

Output: return **only** the fenced Mermaid code block (` ```mermaid ... ``` `), nothing else.

#### Assembly

After all Mermaid Agents return, replace each `<!-- MERMAID: ... -->` placeholder in the PR body
with the corresponding diagram. Then run the `gh pr edit` command to update the PR.

If a Mermaid Agent fails or returns invalid syntax, omit that diagram and leave a note:
`*(Diagram omitted — see implementation walkthrough prose above.)*`

---

## Final Summary

Present to the user:

```
## fix-issue complete: #<number> <title>

Branch: fix/issue-<number>-<slug>
Tier: <1|2|3> — <rationale>
PR: <url>
[Worktree: <WORKTREE_PATH> — remove after merge: git -C "$GIT_ROOT" worktree remove <WORKTREE_PATH>]

### Agents used
- Planner
- [Architect — Tier 3 only]
- Coder A/B/C (list actual tasks)
- Tester
- Integrator (Tier 2/3)
- Reviewer

### Acceptance criteria
- [x] <met criterion>
- [x] <met criterion>
- [ ] <any unmet — with note>

### Review findings
- Critical: <count fixed> fixed, <count deferred> deferred
- Major: <count fixed> fixed, <count deferred> deferred
- Minor: <count fixed> fixed, <count deferred> deferred

### Outstanding items
[anything not resolved, or "None"]
```

---

## Constraints (all agents)

- Follow `~/.claude/guides/pr-guide.md` for all PR and commit interactions.
- One PR per session. One issue per PR unless issues are tightly coupled.
- Never touch files outside the assigned scope.
- Never make architecture decisions without an approved ADR (Tier 3).
- Never merge. Never force-push. Never commit to main/master.
- Prefer minimal, targeted changes — do not refactor surrounding code unless it is the direct cause of the issue.
- Never skip binary checks before committing.
- If blocked or uncertain, stop and report to the user rather than guessing.
- When handing off to a human (blockers, errors, confirmation prompts), always include the PR URL so the user can navigate to it directly.
