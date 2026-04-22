---
version: 1.0.0
---

# Resolve Epic

## Purpose

Orchestrate the end-to-end resolution of a GitHub epic issue whose children are already defined. Creates an epic branch, then autonomously resolves each child sub-issue in sequence — targeting the epic branch instead of `dev`. Produces a final epic PR with comprehensive QA documentation.

This command does **not** decompose or refine epics. It expects the child sub-issues to already exist, via one of two paths:

- **Refined epic** (primary): `/refine-epic` has already run, produced an intent document, and created child issues. `/resolve-epic` detects the refine-epic handoff and proceeds directly to resolution.
- **Collection of issues** (lightweight): the epic body contains a GitHub task-list of existing issues (e.g. `- [ ] #123`) that should be resolved together in one epic PR. Typical use: bundling 3-5 related bug fixes into a single merge.

If neither condition is met, the command stops and asks the user to clarify. It will not invoke planning agents on its own — use `/refine-epic` first for real epics.

**Once a path is chosen, this command runs autonomously until completion or a true blocker.** It does not pause for human review between sub-issues. The only human checkpoints are:

1. True blockers — a sub-issue `/resolve-issue` fails and cannot recover
2. Final epic PR — the one place where human QA and review happen

---

## Args

Format: `/resolve-epic <issue> [--worktree]`

- `issue`: required. The epic issue number or full URL.
- `--worktree`: optional. Forward to each `/resolve-issue` invocation.

---

## Step 1 — Parse Epic and Detect Repo

Read the agent team guide before doing anything else:
```
~/.claude/guides/agent-team-guide.md
```

### Repo detection

Use the same repo detection logic as `/fix-issue`:
- If `issue` is a full URL, extract `owner/repo`.
- Otherwise detect from git remotes. Confirm with the user before proceeding.

Set `REPO=<owner/repo>`.

### Fetch the epic

```bash
gh issue view <number> --repo <REPO> --json number,title,body,labels,comments,assignees
```

Verify the issue title or labels indicate it is an epic (title prefix `epic:`, label `epic`, or body contains "## Epic Summary" or similar). If not obviously an epic, ask the user to confirm.

### Setup Agent (`model: "claude-sonnet-4-6"`)

Spawn a **Setup Agent** to detect the base branch, resolve the git root, and create the epic branch. The orchestrator does not run git commands directly.

#### Setup Agent instructions

Role: repository setup only. No source file changes, no implementation.

1. Determine the development base branch (same logic as `/fix-issue` auto-detection):
   ```bash
   git fetch origin
   git ls-remote --heads origin dev develop 2>/dev/null
   ```
   - If `dev` exists → `DEV_BASE=dev`
   - Else if `develop` exists → `DEV_BASE=develop`
   - Else → `DEV_BASE=main` (or `master`)

2. Resolve `GIT_ROOT` using the same dev-container-safe logic as `/fix-issue`.

3. Verify the `.agent-work/` scratch directory exists:
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

4. Verify the working tree is clean:
   ```bash
   git status --short
   ```
   If uncommitted changes exist, report and stop.

5. Create the epic branch:
   ```bash
   EPIC_BRANCH="epic/<number>-<slug>"
   git checkout "origin/$DEV_BASE"
   git checkout -b "$EPIC_BRANCH"
   git push -u origin "$EPIC_BRANCH"
   ```
   `<slug>` is a 2-4 word kebab-case summary derived from the epic title.

6. Return the handoff block:
   ```
   HANDOFF
   GIT_ROOT=<absolute path>
   DEV_BASE=<branch name>
   EPIC_BRANCH=<branch name>
   END_HANDOFF
   ```

The orchestrator reads the handoff and sets `GIT_ROOT`, `DEV_BASE`, and `EPIC_BRANCH` for all subsequent steps.

---

## Step 1.5 — Detect Epic Type

`/resolve-epic` supports two input shapes: a refined epic (from `/refine-epic`) or a
collection of existing issues listed in the epic body. Probe for refine-epic artifacts
first; if absent, ask the user which path applies.

Spawn a **Refine Detection Agent** (`model: "claude-sonnet-4-6"`).

### Refine Detection Agent instructions

Role: state detection only. No source file changes, no git changes, no issue creation.

1. Check the epic issue body for a `## Validated Intent` section and a comment with the
   `<!-- INTENT_DOC -->` marker:
   ```bash
   gh issue view <number> --repo <REPO> --json body,comments \
     --jq '{has_intent_section: (.body | test("## Validated Intent")),
            intent_comment_url: (.comments[] | select(.body | test("<!-- INTENT_DOC -->")) | .url) // ""}'
   ```

2. Locate the refine-epic scratch directory (matches `$GIT_ROOT/.agent-work/EPIC_*-<number>/`):
   ```bash
   ls -d "$GIT_ROOT"/.agent-work/EPIC_*-<number>/ 2>/dev/null | head -1
   ```
   If found, record as `EPIC_DIR` and check for `intent.md`, `intent-compressed.md`, `index.md`,
   and `child-*.md` files.

3. Find child issues already linked to the epic (refine-epic creates these with the
   `child-issue` label and `Part of epic #<number>` in the body):
   ```bash
   gh issue list --repo <REPO> \
     --search "\"Part of epic #<number>\" in:body" \
     --json number,title,state,labels \
     --limit 50
   ```

4. If `index.md` exists, parse its Decomposition Table and dependency graph to determine the
   ordered child-issue list. Cross-reference child issue numbers from step 3 with the
   `Child N → #<child-number>` mapping recorded in `index.md` (refine-epic Step 4 writes this).

5. Return ONLY this HANDOFF block:
   ```
   HANDOFF
   REFINE_HANDOFF=<true|false>
   EPIC_DIR=<absolute path, or empty>
   INTENT_COMMENT_URL=<url, or empty>
   INDEX_PRESENT=<true|false>
   INTENT_PRESENT=<true|false>
   CHILD_ISSUES_ORDERED=<comma-delimited issue numbers in dependency order, or empty>
   CHILD_COUNT=<integer>
   UNKNOWNS_BLOCKED=<true|false — true if index.md status is UNKNOWNS_BLOCKED>
   END_HANDOFF
   ```

Set `REFINE_HANDOFF=true` only if **all** of: `INDEX_PRESENT=true`, `INTENT_PRESENT=true`,
`CHILD_COUNT>0`, `UNKNOWNS_BLOCKED=false`.

### Orchestrator branch on handoff

- **If `REFINE_HANDOFF=true`** → **Refined-epic path**. Use `CHILD_ISSUES_ORDERED` as the
  `SUB_ISSUES` list. Spawn a **Tracking Comment Agent** (`model: "claude-sonnet-4-6"`) to
  post a tracking comment on the epic issue (see format below), then jump to Step 2.
  - The intent document already captures decision priors, invariants, and feared failure modes
    — no ADR or planning step is needed.
  - Integration seams, risk register, and QA checklist already exist in `index.md`. The Step 4
    Documentation Agent reads `index.md` and `intent.md` rather than regenerating them.
  - Smoke tests for each sub-issue come from the child draft's Acceptance Scenarios. Each
    Smoke Test Runner invocation reads `$EPIC_DIR/child-<N>-<slug>.md` for the relevant child.

- **If `UNKNOWNS_BLOCKED=true`** → stop and report to the user. `/refine-epic` flagged P0
  unknowns that must be resolved before implementation.

- **If `REFINE_HANDOFF=false`** → ask the user which shape this epic is, using
  `AskUserQuestion`:

  > **Epic type** — No `/refine-epic` artifacts were found for this epic. Which path applies?
  > - **Collection of issues** — the epic body lists existing issues (e.g. a task-list of
  >   `- [ ] #123` items) that should be resolved together in one epic PR.
  > - **Real epic (needs refinement)** — this is a substantive epic that hasn't been refined
  >   yet. Stop and run `/refine-epic <number>` first.

  - **If the user chose "Collection of issues"** → spawn a **Collection Parser Agent**
    (`model: "claude-sonnet-4-6"`) with these instructions:

    Role: parse epic body for a GitHub task-list referencing existing issues. No source file
    changes, no issue creation, no git operations.

    1. Fetch the epic body:
       ```bash
       gh issue view <number> --repo <REPO> --json body --jq '.body'
       ```
    2. Extract issue references from task-list lines. Match lines of the form
       `- [ ] #<N>` or `- [x] #<N>`, optionally followed by a cross-repo reference like
       `owner/repo#<N>`. Record them in the order they appear in the body.
    3. For each extracted issue number, verify it exists and is open:
       ```bash
       gh issue view <N> --repo <REPO> --json number,state,title
       ```
       Skip any that are closed or not found (note them in the handoff).
    4. Return ONLY this HANDOFF block:
       ```
       HANDOFF
       CHILD_ISSUES_ORDERED=<comma-delimited open issue numbers in body order, or empty>
       CHILD_COUNT=<integer>
       SKIPPED=<comma-delimited numbers that were closed or missing, or empty>
       END_HANDOFF
       ```

    After the Collection Parser Agent returns:
    - **If `CHILD_COUNT=0`** → stop and report to the user: the epic body has no open-issue
      task-list entries, so there is nothing to resolve. Do not proceed.
    - **Else** → spawn a **Tracking Comment Agent** to post the tracking comment, then jump
      to Step 2 using `CHILD_ISSUES_ORDERED` as `SUB_ISSUES`.

  - **If the user chose "Real epic (needs refinement)"** → stop and tell the user to run
    `/refine-epic <number>` first, then re-run `/resolve-epic`.

### Tracking Comment Agent instructions

Role: post the sub-issue tracking comment on the epic. No source file changes, no issue
creation, no git operations.

Input from orchestrator: `SUB_ISSUES` list, `EPIC_BRANCH`, and for each sub-issue: number
and title (fetch titles via `gh issue view <N> --repo <REPO> --json title`).

1. Check whether a tracking comment already exists (resume case):
   ```bash
   gh issue view <epic_number> --repo <REPO> --json comments \
     --jq '[.comments[] | select(.body | test("## Sub-Issues to Resolve"))] | length'
   ```
   If the count is > 0, skip posting a new comment and jump to step 3.
2. Post a tracking comment on the epic:
   ```bash
   gh issue comment <epic_number> --repo <REPO> --body "$(cat <<'EOF'
   ## Sub-Issues to Resolve

   Epic branch: `<EPIC_BRANCH>`
   Path: <refined-epic | collection-of-issues>

   | # | Issue | Title | Status |
   |---|-------|-------|--------|
   | 1 | #<num1> | <title> | pending |
   | 2 | #<num2> | <title> | pending |
   | ... | | | |

   Implementation will proceed autonomously. Updates will be posted as each sub-issue completes.
   EOF
   )"
   ```
3. Return:
   ```
   HANDOFF
   SUB_ISSUES=<num1>,<num2>,...
   END_HANDOFF
   ```

---

## Subagent Output Rule

**Every subagent must return ONLY its HANDOFF block — nothing else.** Write all verbose output, summaries, and analysis to `.agent-work/` files. The orchestrator parses HANDOFF blocks only; free-form agent output is never read by the orchestrator. Violating this rule bloats the orchestrator's context window and degrades performance across long epics.

## Subagent Context Bootstrap

When spawning any subagent that reads or modifies source code (Documentation Agent, Integration Fixer, Fix Verifier, Verification Agent), prepend these instructions to its prompt:

> **Context bootstrap** (do this before your main task):
> 1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions) if they exist. Follow all instructions — repo instructions override global ones.
> 2. Read codebase index files if present:
>    - `.codesight/CODESIGHT.md` at `$GIT_ROOT`
>    - `docs/agent_index.md` at `$GIT_ROOT`
>    - If no agent index was found at the above path, glob for `**/agent_index.md` at `$GIT_ROOT` and read any match.

Do **not** add this bootstrap to narrow utility agents (Setup Agent, Refine Detection Agent, Collection Parser Agent, Tracking Comment Agent, Merge & Sync Agent, Smoke Test Runner, Full Test Runner, Poll Agent, Mermaid Agent).

---

## Step 2 — Sequential Sub-Issue Resolution

### 2a — Resume Check

Before starting the loop, spawn a **Resume Agent** (`model: "claude-sonnet-4-6"`) to determine where to start.

#### Resume Agent instructions

Role: state detection only. No source file changes, no git changes.

1. Read the epic issue's tracking comment to get the ordered sub-issue list. The tracking comment was posted in Step 1.5 and contains a table with issue numbers and titles.
   ```bash
   gh issue view <epic_number> --repo <REPO> --json comments --jq '.comments[].body' | grep -A 50 "Sub-Issues to Resolve"
   ```

2. For each sub-issue in the list, check whether it has a merged PR targeting the epic branch:
   ```bash
   gh pr list --repo <REPO> --state merged --base "$EPIC_BRANCH" --json number,title,headRefName
   ```
   A sub-issue is **complete** if a merged PR targeting the epic branch exists for it.

3. Find any open PRs targeting the epic branch and close them:
   ```bash
   gh pr list --repo <REPO> --state open --base "$EPIC_BRANCH" --json number,headRefName
   ```
   For each open PR found:
   ```bash
   gh pr close <pr_number> --repo <REPO> --comment "Epic workflow interrupted — closing this PR for clean resume. The sub-issue will be re-worked from the current epic branch state."
   ```

4. Return ONLY this HANDOFF block:
   ```
   HANDOFF
   COMPLETED_SUB_ISSUES=<comma-delimited issue numbers that are done, empty if none>
   FIRST_PENDING_SUB_ISSUE=<issue number of first incomplete sub-issue, or empty if all done>
   OPEN_PRS_CLOSED=<comma-delimited PR numbers that were closed, empty if none>
   END_HANDOFF
   ```

The orchestrator reads the Resume Agent HANDOFF and:
- Skips all sub-issues in `COMPLETED_SUB_ISSUES`
- Starts the loop from `FIRST_PENDING_SUB_ISSUE`
- If `FIRST_PENDING_SUB_ISSUE` is empty, all sub-issues are done — skip to Step 3
- If any `OPEN_PRS_CLOSED` were found, note them in the resume log

### 2b — Resolution Loop

For each sub-issue in order (starting from `FIRST_PENDING_SUB_ISSUE`), spawn a `/resolve-issue` Agent subagent (`model: "claude-opus-4-6"`):

```
/resolve-issue <sub_issue_number> --base <EPIC_BRANCH> --return-only
```

If `WORKTREE_MODE` was set, also pass `--worktree`.

`--return-only` activates resolve-issue's orchestrator mode: skips the rebase phase and returns the HANDOFF block as the final output.

Append these instructions to the subagent prompt to specify the expected HANDOFF format:

> Return ONLY the following HANDOFF block and nothing else:
>
> ```
> HANDOFF
> WORK_DIR=<absolute path>
> BRANCH=<branch name>
> PR_URL=<full GitHub PR URL, or empty if PR creation failed>
> PR_NUMBER=<integer, or empty>
> REPO=<owner/repo>
> SUCCESS=<true|false>
> FAILURE_REASON=<empty if SUCCESS=true, otherwise a one-line description>
> END_HANDOFF
> ```

Wait for the subagent to complete. Parse the `HANDOFF` block.

### On success

1. Record the sub-issue PR URL and number.
2. Spawn a **Merge & Sync Agent** (`model: "claude-sonnet-4-6"`) to merge the sub-issue and update tracking.

   #### Merge & Sync Agent instructions

   Role: merge PR, update tracking, sync local branch. No source file changes.

   1. Merge the sub-issue PR into the epic branch (squash merge):
      ```bash
      gh pr merge <PR_NUMBER> --repo <REPO> --squash --delete-branch
      ```
      If merge fails (e.g. checks not passing), wait up to 5 minutes for CI, then retry once. If still failing, return `SUCCESS=false`.
   2. Update the epic tracking comment — change this sub-issue's status to `done ✓ (#<PR_NUMBER>)`.
   3. Post a progress comment on the epic:
      ```bash
      gh issue comment <epic_number> --repo <REPO> --body "Sub-issue <N>/<total> complete: #<sub_issue_number> → PR #<PR_NUMBER> merged into \`<EPIC_BRANCH>\`."
      ```
   4. Pull the latest epic branch:
      ```bash
      git fetch origin
      git checkout "$EPIC_BRANCH"
      git reset --hard "origin/$EPIC_BRANCH"
      ```
   5. Return handoff:
      ```
      HANDOFF
      SUCCESS=<true|false>
      FAILURE_REASON=<empty if true, otherwise description>
      END_HANDOFF
      ```

   If the Merge & Sync Agent returns `SUCCESS=false`, treat as a blocker.
6. **Integration smoke test gate.** Spawn a **Smoke Test Runner** agent (`model: "claude-sonnet-4-6"`) to execute and evaluate the tests.

   #### Smoke Test Runner instructions

   Role: execute smoke tests, evaluate results, report pass/fail. No source file changes.

   1. Determine sub-issue-specific smoke test commands based on the epic path:
      - **Refined-epic path**: read `$EPIC_DIR/child-<N>-<slug>.md` and derive smoke commands from its Acceptance Scenarios.
      - **Collection-of-issues path**: no custom smoke tests — skip step 3a and rely on the cumulative checks (3b and 3c) alone.
   2. Read the list of all files changed on the epic branch so far:
      ```bash
      git diff "origin/$DEV_BASE"..."$EPIC_BRANCH" --name-only
      ```
   3. Execute tests in order, capturing all output:
      ```bash
      # a) Sub-issue-specific smoke tests (refined-epic path only; skip for collection path)
      <smoke test commands for this sub-issue>

      # b) Cumulative: full compile/typecheck/lint (fast checks only)
      <compile command if applicable>
      <typecheck command if applicable>
      <lint command if applicable>

      # c) Cumulative: run tests for all areas touched by the epic so far
      #    (not the full suite — just modules affected by completed sub-issues)
      <targeted test command covering files changed on the epic branch>
      ```
   4. Produce `.agent-work/EPIC_<number>_SMOKE_<N>.md`:
      ```markdown
      ## Smoke Test Results — after sub-issue <N> (#<sub_issue_number>)

      ### Overall: PASS | FAIL

      ### Sub-issue-specific tests
      | Test | Result | Notes |
      |------|--------|-------|
      | <command> | pass/fail | <output summary if failed> |

      ### Cumulative checks
      | Check | Result | Notes |
      |-------|--------|-------|
      | compile | pass/fail | ... |
      | typecheck | pass/fail | ... |
      | lint | pass/fail | ... |
      | targeted tests | pass/fail | <failing test names if any> |

      ### Full output (failures only)
      <raw output for any failed check — needed by Diagnostician if activated>
      ```

   5. If overall PASS, post a confirmation comment:
      ```bash
      gh issue comment <epic_number> --repo <REPO> --body "Integration smoke tests passed after sub-issue <N>/<total> (#<sub_issue_number>). Proceeding to sub-issue <N+1>."
      ```
   6. Return handoff:
      ```
      HANDOFF
      OVERALL=<PASS|FAIL>
      END_HANDOFF
      ```

   The orchestrator reads the handoff. **If PASS**: proceed to the next sub-issue. **If FAIL**: activate the **Integration Fix Team**.

   ### Integration Fix Team

   This team diagnoses and resolves integration failures on the epic branch after a sub-issue merge. Max 2 fix cycles before escalating to blocker.

   **Set `FIX_CYCLE = 1`, `MAX_FIX_CYCLES = 2`.**

   #### Agent 1 — Diagnostician (`model: "claude-opus-4-6"`)

   Role: read-only root-cause analysis. No file changes.

   1. Read `.agent-work/EPIC_<number>_SMOKE_<N>.md` (the Smoke Test Runner's report) in full.
   2. Read the diff of the most recently merged sub-issue:
      ```bash
      git log --oneline -5  # identify the squash-merge commit
      git show <merge-commit> --stat --patch
      ```
   3. Read the files that failed and their callers/dependencies.
   4. Read the previous sub-issues' changes if the failure might be a cross-sub-issue interaction:
      ```bash
      git diff "origin/$DEV_BASE"..."$EPIC_BRANCH"
      ```
   5. Produce `.agent-work/EPIC_<number>_SMOKE_DIAG_<N>.md`:
      ```markdown
      ## Integration Failure Diagnosis — after sub-issue <N>

      ### Failing tests
      - <test name>: <one-line failure description>

      ### Root cause
      [Which sub-issue introduced the break, what the interaction is,
      and why it wasn't caught by the sub-issue's own tests]

      ### Affected files
      | File | Problem | Fix approach |
      |------|---------|-------------|
      | ... | ... | ... |

      ### Recommended fix scope
      [Minimal set of changes needed — should not exceed ~50 lines]

      ### Risk assessment
      [Could this fix break something else? What to re-test after.]
      ```

   #### Agent 2 — Integration Fixer (`model: "claude-sonnet-4-6"`)

   Role: apply the targeted fix. Scope-limited.

   1. Read `.agent-work/EPIC_<number>_SMOKE_DIAG_<N>.md`.
   2. Apply the recommended fix. **Scope**: only files listed in the diagnosis.
   3. Do not refactor, do not fix unrelated issues, do not modify test expectations unless the test itself is wrong.
   4. Produce `.agent-work/EPIC_<number>_SMOKE_FIX_<N>.md`:
      ```markdown
      ## Integration Fix — cycle <FIX_CYCLE>

      ### Changes made
      | File | Change |
      |------|--------|
      | ... | ... |

      ### Rationale
      [Why this fix addresses the root cause without side effects]
      ```

   #### Agent 3 — Fix Verifier (`model: "claude-opus-4-6"`)

   Role: read-only verification. No file changes.

   1. Read the fix diff and the original diagnosis.
   2. Read callers and dependents of changed functions.
   3. Verify:
      - The fix addresses the diagnosed root cause
      - The fix does not contradict any Decision Priors / Invariants in `$EPIC_DIR/intent.md` (refined-epic path only)
      - The fix does not revert or weaken any sub-issue's intent
      - No new issues are introduced in the surrounding code
   4. Output: `VERIFIED` or `CONCERNS: <list>`.
      - If `CONCERNS` are raised, the Fixer applies corrections (still within the same cycle).

   #### After the fix team completes

   The **Integration Fixer** (Agent 2) is responsible for committing and pushing its own fix as its final action:
   ```bash
   git add <only fixed files>
   git commit -m "fix(epic-<number>): integration fix after sub-issue <N> (#<sub_issue_number>)

   Root cause: <one-line from diagnosis>

   Co-Authored-By: Claude Code <noreply@anthropic.com>"
   git push origin "$EPIC_BRANCH"
   ```

   Then re-spawn the **Smoke Test Runner** agent to re-run all smoke tests.

   If smoke tests pass → post confirmation, proceed to next sub-issue.

   If still failing and `FIX_CYCLE < MAX_FIX_CYCLES` → increment `FIX_CYCLE`, re-run the Integration Fix Team with the new Smoke Test Runner report.

   If still failing after `MAX_FIX_CYCLES` → **BLOCKER**:
   ```
   ## resolve-epic BLOCKED — integration failure after sub-issue <N>/<total>

   Epic: #<number> — <title>
   Epic branch: <EPIC_BRANCH>
   Last merged: #<sub_issue_number> — <sub_issue_title>

   ### Failing smoke tests
   <test output>

   ### Diagnosis
   <summary from .agent-work/EPIC_<number>_SMOKE_DIAG_<N>.md>

   ### Fix attempts (<MAX_FIX_CYCLES> cycles)
   <summary of what each cycle tried and why it didn't fully resolve>

   Action required: fix the integration issue on `<EPIC_BRANCH>`, then re-run:
   /resolve-epic <epic_number>
   ```
7. **Proceed to the next sub-issue.** No human checkpoint.

### On failure

1. Update the epic tracking comment — change this sub-issue's status to `BLOCKED ✗ — <FAILURE_REASON>`.
2. Post a blocker comment on the epic.
3. **Stop the entire pipeline.** Report to the user:

```
## resolve-epic BLOCKED at sub-issue <N>/<total>

Epic: #<number> — <title>
Epic branch: <EPIC_BRANCH>
Blocked at: #<sub_issue_number> — <sub_issue_title>
Reason: <FAILURE_REASON>

### Completed sub-issues
- #<num1> — <title> ✓ (PR #<pr>)
- ...

### Remaining sub-issues (not started)
- #<numN> — <title>
- ...

Action required: resolve the blocker on #<sub_issue_number>, then re-run:
/resolve-epic <epic_number>
(The command will detect existing sub-issues and resume from where it left off.)
```

---

## Step 3 — Epic Validation

After all sub-issues are resolved and merged into the epic branch, run two validation agents.

### 3a — Full Test Runner (`model: "claude-sonnet-4-6"`)

Spawn a **Full Test Runner** agent to execute the complete validation suite on the epic branch.

#### Full Test Runner instructions

Role: execute tests and report results. No source file changes.

1. Sync to the latest epic branch:
   ```bash
   git fetch origin
   git checkout "$EPIC_BRANCH"
   git reset --hard "origin/$EPIC_BRANCH"
   ```
2. Run the project's full test suite and binary checks:
   ```bash
   <compile command if applicable>
   <typecheck command if applicable>
   <lint command if applicable>
   <test command — full suite, not just unit>
   ```
3. Produce `.agent-work/EPIC_<number>_FULL_TEST.md`:
   ```markdown
   ## Full Validation Results — epic branch

   ### Overall: PASS | FAIL

   ### Results
   | Check | Result | Notes |
   |-------|--------|-------|
   | compile | pass/fail | ... |
   | typecheck | pass/fail | ... |
   | lint | pass/fail | ... |
   | full test suite | pass/fail | <failing test names if any> |

   ### Full output (failures only)
   <raw output for any failed check>
   ```

The Full Test Runner must return ONLY this HANDOFF block (all detail goes to the report file):
```
HANDOFF
OVERALL=<PASS|FAIL>
FAILING_CHECKS=<comma-delimited list of failing check names, empty if PASS>
END_HANDOFF
```

The orchestrator parses the HANDOFF. If `OVERALL=FAIL`, report as a blocker — do not attempt automated fixes at the epic level. Include `FAILING_CHECKS` so the user can diagnose.

### 3b — Verification Agent (`model: "claude-opus-4-6"`)

Spawn only if the Full Test Runner HANDOFF returned `OVERALL=PASS`.

#### Verification Agent instructions

Role: read-only acceptance criteria verification. No file changes.

1. Read the original epic issue acceptance criteria.
2. Read the full diff of the epic branch against `<DEV_BASE>`:
   ```bash
   git diff "origin/$DEV_BASE"..."$EPIC_BRANCH"
   ```
3. For each acceptance criterion, verify it is met by the implementation. Produce a checklist with evidence (file paths, function names, test names).
4. Output `.agent-work/EPIC_<number>_VERIFICATION.md`.
5. Return ONLY this HANDOFF block (all detail goes to the verification file):
   ```
   HANDOFF
   ALL_CRITERIA_MET=<true|false>
   UNMET_CRITERIA=<pipe-delimited list of unmet criterion titles, empty if all met>
   END_HANDOFF
   ```

The orchestrator parses the HANDOFF. If `ALL_CRITERIA_MET=false`, report which criteria are unmet (from `UNMET_CRITERIA`) and stop as a blocker.

---

## Step 4 — Epic PR

Create the final PR from the epic branch into `<DEV_BASE>`:

Spawn a **Documentation Agent** (`model: "claude-opus-4-6"`) to produce the epic PR body.

### Documentation Agent instructions

Role: read-only research + PR body creation. No source file modifications.

1. Read the full epic diff:
   ```bash
   git diff "origin/$DEV_BASE"..."origin/$EPIC_BRANCH" --stat
   git diff "origin/$DEV_BASE"..."origin/$EPIC_BRANCH"
   ```
2. Read the original epic issue, all sub-issues, and their PRs.
3. Read context artifacts:
   - Always: `.agent-work/EPIC_<number>_VERIFICATION.md`.
   - Refined-epic path: `$EPIC_DIR/intent.md` and `$EPIC_DIR/index.md` (decision priors, integration seams, risk register, QA checklist).
   - Collection-of-issues path: no planning artifacts exist — derive summary from the epic body and each child issue directly.
4. Collect all sub-issue numbers from the tracking comment on the epic issue. You will need them to emit `Closes` keywords for each one.
5. Produce the PR body.

```bash
gh pr create --repo <REPO> \
  --base "$DEV_BASE" \
  --head "$EPIC_BRANCH" \
  --title "epic(#<number>): <title>" \
  --body "$(cat <<'EOF'
Closes #<number>
Closes #<sub_num1>
Closes #<sub_num2>
[one Closes line per sub-issue — include all sub-issue numbers from the decomposition]

## Epic Summary

<2-4 sentence executive summary: what the epic achieved, why this approach was chosen, and the key architectural decisions made.>

## Sub-Issues Resolved

| # | Issue | PR | Title | Summary |
|---|-------|----|-------|---------|
| 1 | #<num1> | #<pr1> | <title> | <one-line summary of changes> |
| 2 | #<num2> | #<pr2> | <title> | <one-line summary of changes> |
| ... | | | | |

## Architecture Decisions

<If refined-epic path: summarize the key Decision Priors from `intent.md` and any cross-cutting choices they drove.>
<If collection-of-issues path: "No cross-cutting architecture decisions — this epic bundled independent issues.">

## Implementation Walkthrough

<For each major area of change, write a paragraph explaining what changed, why, and how the components interact. Follow the same guidelines as the /fix-issue Documentation Agent — prose, not raw diff. Use `<!-- MERMAID: ... -->` placeholders for diagrams.>

## QA Checklist

**These checks should be performed by a human reviewer before merging into `<DEV_BASE>`:**

<From the decomposition's QA checklist, plus any additional checks identified during implementation>

- [ ] <check — specific, actionable, with instructions on how to verify>
- [ ] <check>
- [ ] All existing tests pass
- [ ] Visual regression: <specific visual outputs to compare>
- [ ] Integration: <specific integration points to test>
- [ ] Performance: <any performance-sensitive paths to benchmark>

## Acceptance Criteria

<From .agent-work/EPIC_<number>_VERIFICATION.md>
- [x] <criterion — with evidence>
- [x] <criterion — with evidence>

## Outstanding Items

<Any deferred work, known limitations, or follow-up issues. "None" if clean.>

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Mermaid Agent

Same as `/fix-issue` — after the Documentation Agent produces the PR body with `<!-- MERMAID: ... -->` placeholders, spawn Mermaid Agents (`model: "haiku"`) to replace them with validated diagrams.

---

## Step 5 — Resume Support

Resume is handled automatically by Step 2a (Resume Check). When `/resolve-epic` is re-run on an epic that already has an epic branch and sub-issues:

1. Detect existing epic branch:
   ```bash
   git ls-remote --heads origin "epic/<number>-*"
   ```
   If the branch exists, skip Step 1's branch creation (Setup Agent still runs to establish `GIT_ROOT`, `DEV_BASE`, and `EPIC_BRANCH`).

2. Step 1.5 still runs — the Refine Detection Agent probes for artifacts, and if a tracking comment already exists on the epic, the branching logic picks the same path as before (refined or collection). No duplicate tracking comment is posted if one already exists.

3. Step 2a (Resume Check) handles the rest: detecting completed sub-issues, closing any stale open PRs, and finding the first pending sub-issue.

---

## Final Report

```
## resolve-epic complete: #<number> <title>

Epic branch: <EPIC_BRANCH>
PR: <epic_pr_url>
Sub-issues: <completed>/<total>

### Sub-Issues
- #<num1> — <title> ✓ (PR #<pr1>)
- #<num2> — <title> ✓ (PR #<pr2>)
- ...

### Path
<refined-epic | collection-of-issues>

### Epic Acceptance Criteria
- [x] <criterion>
- [x] <criterion>

### QA Checklist
See PR for full checklist — human review required before merge into <DEV_BASE>.

### Next Steps
1. Review the epic PR: <epic_pr_url>
2. Run QA checks listed in the PR
3. Merge via squash merge when satisfied
```

---

## Constraints

- **The orchestrator only delegates and reads HANDOFF blocks.** It never runs git commands, gh commands, bash commands, or modifies any files. All actions (branch creation, issue creation, merging, testing, committing, pushing, posting comments) are performed by spawned subagents. The orchestrator's job is to: (1) spawn agents with the right instructions and context, (2) parse their HANDOFF blocks, (3) decide what to do next based on those results.
- **Subagents must return ONLY their HANDOFF block and nothing else.** All summaries, explanations, and verbose output must go to `.agent-work/` files. The orchestrator never reads full artifact files — it only parses compact HANDOFF blocks. This is critical for keeping the orchestrator's context window clean across a long multi-sub-issue run.
- One epic branch per epic. One epic PR into `<DEV_BASE>`.
- Sub-issue PRs target the epic branch, not `<DEV_BASE>`.
- Sub-issue PRs are squash-merged into the epic branch automatically after `/resolve-issue` succeeds.
- The only human checkpoints are: epic-type disambiguation (Step 1.5, only when no refine-epic artifacts exist) and final epic PR review (Step 4).
- `/resolve-epic` does not decompose epics. Decomposition is `/refine-epic`'s job. If neither a refine-epic handoff nor an existing issue task-list is available, the command stops rather than inferring structure.
- If blocked, stop immediately and report. Do not attempt to skip sub-issues or work around failures.
- Never merge the epic branch into `<DEV_BASE>` — only create the PR. Human merges it.
- Never use `--admin` or bypass branch protection.
- Follow `~/.claude/guides/pr-guide.md` for all PR interactions.
- When handing off to a human (blockers, epic PR), always include the PR URL.
