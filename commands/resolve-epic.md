# Resolve Epic

## Purpose

Orchestrate the end-to-end resolution of a GitHub epic issue that decomposes into multiple sub-issues. Creates an epic branch, runs a front-loaded architecture review, then autonomously resolves each sub-issue in sequence — targeting the epic branch instead of `dev`. Produces a final epic PR with comprehensive QA documentation.

**This command runs autonomously until completion or a true blocker.** It does not pause for human review between sub-issues. The only human checkpoints are:

1. ADR approval (Step 3) — architecture decisions before any code is written
2. True blockers — a sub-issue `/resolve-issue` fails and cannot recover
3. Final epic PR — the one place where human QA and review happen

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

### Setup Agent (`model: "sonnet"`)

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

3. Set up `.claude-work/`:
   First, check if the scratch directory already exists:
   ```bash
   test -d "$GIT_ROOT/.claude-work" && echo "EXISTS" || echo "MISSING"
   ```
   If `EXISTS`, skip ahead. If `MISSING`, create it:
   ```bash
   mkdir -p "$GIT_ROOT/.claude-work" && echo '.claude-work/' >> "$GIT_ROOT/.git/info/exclude"
   ```

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

## Step 2 — Epic Planning Team

The decomposition of an epic into sub-issues is a critical decision that shapes the entire implementation. A single agent's perspective is insufficient — different concerns (architecture, testing, sequencing, risk) must be weighed against each other.

### Subagent Context Bootstrap

When spawning any subagent that reads or modifies source code (Research Agent, Planning Team agents, Synthesis Agent, Architect Agent, Documentation Agent, Integration Fixer, Fix Verifier, Verification Agent), prepend these instructions to its prompt:

> **Context bootstrap** (do this before your main task):
> 1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions) if they exist. Follow all instructions — repo instructions override global ones.
> 2. Read codebase index files if present:
>    - `.codesight/CODESIGHT.md` at `$GIT_ROOT`
>    - `docs/agent_index.md` at `$GIT_ROOT`
>    - If no agent index was found at the above path, glob for `**/agent_index.md` at `$GIT_ROOT` and read any match.

Do **not** add this bootstrap to narrow utility agents (Setup Agent, Issue Creation Agent, Merge & Sync Agent, Smoke Test Runner, Full Test Runner, Poll Agent, Mermaid Agent).

### Phase 2a — Research Agent (`model: "opus"`)

Before the planning team debates, one agent gathers the raw facts.

Role: read-only codebase research. No file writes except the research document.

1. Read the epic issue body and all comments in full.
2. Read project instructions and codebase index files:
   - Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions) if they exist. Follow all instructions — repo instructions override global ones.
   - `.codesight/CODESIGHT.md` at `$GIT_ROOT`
   - `docs/agent_index.md` at `$GIT_ROOT`
   - If no agent index was found at `docs/agent_index.md`, glob for `**/agent_index.md` at `$GIT_ROOT` and read any match.
3. Search the codebase exhaustively for all areas mentioned in the epic — grep for symbols, read affected files, map dependencies between them.
4. Produce `.claude-work/EPIC_<number>_RESEARCH.md`:
   ```markdown
   # Epic Research: <title> (#<number>)

   ## Codebase Inventory
   [For each area the epic touches: file paths, current line counts, key functions/classes,
   dependencies on other modules, and current test coverage]

   ## Dependency Map
   [Which files import/call which — enough for the planning team to judge sequencing]

   ## Existing Patterns
   [Current conventions, abstractions, or utilities that the epic should build on or replace]

   ## Risk Areas
   [Files with high fan-out, shared interfaces, complex state, or no test coverage]
   ```

### Phase 2b — Planning Team Debate (parallel, all `model: "opus"`)

Spawn 4-5 agents in parallel, each with a different perspective. All receive the epic issue body and `.claude-work/EPIC_<number>_RESEARCH.md` as input.

| Agent | Perspective | Key question |
|-------|-------------|-------------|
| **Decomposition Architect** | System boundaries, module coupling, interface design | How should this epic be sliced so each sub-issue has clean boundaries and doesn't require rework when the next sub-issue lands? |
| **Sequencing Strategist** | Build order, incremental value, merge safety | What implementation order minimizes risk of integration failures? Which sub-issue should land first to de-risk the rest? |
| **Testing & QA Advocate** | Testability, regression risk, validation strategy | How do we ensure each sub-issue leaves the system in a testable state? What visual/integration/regression checks are needed? |
| **Risk & Rollback Analyst** | Failure modes, reversibility, blast radius | What can go wrong at each stage? If a sub-issue fails, can we roll back cleanly? Where are the points of no return? |
| **Scope Guardian** | Scope creep, minimal viable slicing, YAGNI | Is every proposed sub-issue necessary for the epic's acceptance criteria? Are we over-engineering the decomposition? |

Each agent produces a **200-300 word position paper** (`model: "opus"`) addressing:
1. Their proposed sub-issue decomposition (ordered list with titles and 1-line scopes)
2. Architecture questions they believe must be resolved before implementation
3. One risk or concern the other perspectives might miss
4. Their recommended QA checks for the final epic PR

Output: `.claude-work/EPIC_<number>_POSITION_<role>.md` for each agent.

### Phase 2c — Synthesis Agent (`model: "opus"`)

After all position papers are complete, spawn a **Synthesis Agent** that reads all of them and produces the final decomposition.

Role: read all position papers, resolve disagreements, produce the canonical plan.

1. Read all `.claude-work/EPIC_<number>_POSITION_*.md` files.
2. Identify areas of agreement and disagreement across the planning team.
3. For disagreements, choose the approach that best balances:
   - Clean sub-issue boundaries (Decomposition Architect)
   - Safe sequencing (Sequencing Strategist)
   - Testability at each stage (Testing Advocate)
   - Minimal blast radius (Risk Analyst)
   - Scope discipline (Scope Guardian)
4. Document why dissenting views were not adopted (briefly).

Produce `.claude-work/EPIC_<number>_DECOMPOSITION.md`:

```markdown
# Epic Decomposition: <title> (#<number>)

## Overview
[2-3 sentences: what the epic achieves and the decomposition strategy]

## Planning Team Consensus
[Brief summary of where agents agreed and where they diverged.
For disagreements: which approach was chosen and why.]

## Architecture Questions (for front-loaded ADR)
[Questions that span multiple sub-issues and must be decided before implementation.
Aggregated from all position papers — deduplicated and prioritized.
If none: "No cross-cutting architecture questions — proceed directly to implementation."]
- Q1: <question> — raised by: <agent(s)>
- Q2: <question> — raised by: <agent(s)>

## Sub-Issues (implementation order)

### Sub-Issue 1: <title>
**Depends on**: none (first in sequence)
**Estimated tier**: 1 | 2
**Scope**:
- [bullet list of what this sub-issue implements]
**Files likely affected**:
- [file paths]
**Acceptance criteria**:
- [ ] <criterion>
**Testable state after merge**: [what should work / pass after this sub-issue lands]
**Smoke tests**: [specific commands or checks to run after merging this sub-issue into the epic branch — e.g. `pytest tests/test_thumbnail.py`, `python -c "from module import X"`, `ruff check src/`]

### Sub-Issue 2: <title>
**Depends on**: Sub-Issue 1
**Estimated tier**: 1 | 2
...

## Epic-Level Acceptance Criteria
[From the original epic issue — these are verified at the end against the full epic branch]
- [ ] <criterion>

## QA Checklist (for final epic PR)
[Aggregated from all position papers + synthesis agent's judgment.
What a human reviewer should verify when reviewing the epic branch → dev PR.]
- [ ] <check>

## Risk Register
[Key risks identified by the planning team, with mitigations]
| Risk | Severity | Mitigation | Raised by |
|------|----------|------------|-----------|
| ... | high/medium/low | ... | <agent> |
```

After the Synthesis Agent finishes, read `.claude-work/EPIC_<number>_DECOMPOSITION.md`.

---

## Step 3 — Front-Loaded ADR (if architecture questions exist)

If the decomposition lists architecture questions, spawn an **Architect Agent** (`model: "opus"`).

### Architect Agent instructions

Same role and output format as the `/fix-issue` Step 2b Architect, but scoped to the entire epic:

1. Read `.claude-work/EPIC_<number>_DECOMPOSITION.md` and the full epic issue.
2. For each architecture question, research options by reading relevant code, docs, and existing patterns.
3. Produce `.claude-work/EPIC_<number>_ADR.md` (same ADR format as `/fix-issue`).
4. Post the ADR as checkboxes on the epic issue (same format as `/fix-issue` Step 2b) using `gh issue comment`.
5. Return handoff:
   ```
   HANDOFF
   ADR_POSTED=true
   END_HANDOFF
   ```

**STOP after the Architect completes.** The orchestrator waits for APPROVED/REJECT on the epic issue. Poll for comments containing "APPROVED" or "REJECT" using `gh` via a **Poll Agent** (`model: "haiku"`) that checks every 60 seconds and returns the result.

If the decomposition has **no** architecture questions, skip this step entirely and proceed to Step 4.

---

## Step 4 — Create Sub-Issues on GitHub

Spawn an **Issue Creation Agent** (`model: "sonnet"`) to create the sub-issues and post the tracking comment.

### Issue Creation Agent instructions

Role: create GitHub issues and post comments. No source file changes, no git operations.

1. Read `.claude-work/EPIC_<number>_DECOMPOSITION.md` for the sub-issue list.
2. Read `.claude-work/EPIC_<number>_ADR.md` if it exists.
3. For each sub-issue in the decomposition, create a GitHub issue:
   ```bash
   gh issue create --repo <REPO> \
     --title "<sub-issue title>" \
     --body "$(cat <<'EOF'
   Part of epic #<number>

   ## Context
   This is sub-issue <N> of <total> for the rendering pipeline epic.
   Parent epic: #<number>
   Epic branch: `<EPIC_BRANCH>`
   <If ADR exists: Architecture decisions: see epic #<number> ADR comment>

   ## Scope
   <scope bullets from decomposition>

   ## Files likely affected
   <file list from decomposition>

   ## Acceptance criteria
   <criteria from decomposition>

   ## Constraints
   - Branch off and PR into `<EPIC_BRANCH>` (not dev)
   - Follow architecture decisions from epic ADR
   - Do not modify files outside the scope listed above
   EOF
   )"
   ```
4. Collect the created issue numbers into an ordered list.
5. Post a tracking comment on the epic:
   ```bash
   gh issue comment <number> --repo <REPO> --body "$(cat <<'EOF'
   ## Sub-Issues Created

   Epic branch: `<EPIC_BRANCH>`

   | # | Issue | Title | Status |
   |---|-------|-------|--------|
   | 1 | #<num1> | <title> | pending |
   | 2 | #<num2> | <title> | pending |
   | 3 | #<num3> | <title> | pending |
   | ... | | | |

   Implementation will proceed autonomously. Updates will be posted as each sub-issue completes.
   EOF
   )"
   ```
6. Return the handoff block:
   ```
   HANDOFF
   SUB_ISSUES=<num1>,<num2>,<num3>,...
   END_HANDOFF
   ```

The orchestrator reads the `SUB_ISSUES` list for Step 5.

---

## Step 5 — Sequential Sub-Issue Resolution

For each sub-issue in order, spawn a `/resolve-issue` Agent subagent (`model: "opus"`):

```
/resolve-issue <sub_issue_number> --base <EPIC_BRANCH>
```

If `WORKTREE_MODE` was set, also pass `--worktree`.

Append these instructions to the subagent prompt:

> After presenting the Final Summary, **stop immediately**. Return the following block as the very last thing in your output:
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
2. Spawn a **Merge & Sync Agent** (`model: "sonnet"`) to merge the sub-issue and update tracking.

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
6. **Integration smoke test gate.** Spawn a **Smoke Test Runner** agent (`model: "sonnet"`) to execute and evaluate the tests.

   #### Smoke Test Runner instructions

   Role: execute smoke tests, evaluate results, report pass/fail. No source file changes.

   1. Read `.claude-work/EPIC_<number>_DECOMPOSITION.md` to find the smoke test commands for this sub-issue.
   2. Read the list of all files changed on the epic branch so far:
      ```bash
      git diff "origin/$DEV_BASE"..."$EPIC_BRANCH" --name-only
      ```
   3. Execute tests in order, capturing all output:
      ```bash
      # a) Sub-issue-specific smoke tests from the decomposition plan
      <smoke test commands for this sub-issue>

      # b) Cumulative: full compile/typecheck/lint (fast checks only)
      <compile command if applicable>
      <typecheck command if applicable>
      <lint command if applicable>

      # c) Cumulative: run tests for all areas touched by the epic so far
      #    (not the full suite — just modules affected by completed sub-issues)
      <targeted test command covering files changed on the epic branch>
      ```
   4. Produce `.claude-work/EPIC_<number>_SMOKE_<N>.md`:
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

   #### Agent 1 — Diagnostician (`model: "opus"`)

   Role: read-only root-cause analysis. No file changes.

   1. Read `.claude-work/EPIC_<number>_SMOKE_<N>.md` (the Smoke Test Runner's report) in full.
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
   5. Produce `.claude-work/EPIC_<number>_SMOKE_DIAG_<N>.md`:
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

   #### Agent 2 — Integration Fixer (`model: "sonnet"`)

   Role: apply the targeted fix. Scope-limited.

   1. Read `.claude-work/EPIC_<number>_SMOKE_DIAG_<N>.md`.
   2. Apply the recommended fix. **Scope**: only files listed in the diagnosis.
   3. Do not refactor, do not fix unrelated issues, do not modify test expectations unless the test itself is wrong.
   4. Produce `.claude-work/EPIC_<number>_SMOKE_FIX_<N>.md`:
      ```markdown
      ## Integration Fix — cycle <FIX_CYCLE>

      ### Changes made
      | File | Change |
      |------|--------|
      | ... | ... |

      ### Rationale
      [Why this fix addresses the root cause without side effects]
      ```

   #### Agent 3 — Fix Verifier (`model: "opus"`)

   Role: read-only verification. No file changes.

   1. Read the fix diff and the original diagnosis.
   2. Read callers and dependents of changed functions.
   3. Verify:
      - The fix addresses the diagnosed root cause
      - The fix does not contradict any ADR decisions
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
   <summary from .claude-work/EPIC_<number>_SMOKE_DIAG_<N>.md>

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

## Step 6 — Epic Validation

After all sub-issues are resolved and merged into the epic branch, run two validation agents.

### 6a — Full Test Runner (`model: "sonnet"`)

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
3. Produce `.claude-work/EPIC_<number>_FULL_TEST.md`:
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

The orchestrator reads the report. If overall FAIL, report as a blocker — do not attempt automated fixes at the epic level. Include which tests failed so the user can diagnose.

### 6b — Verification Agent (`model: "opus"`)

Spawn only if the Full Test Runner reports PASS.

#### Verification Agent instructions

Role: read-only acceptance criteria verification. No file changes.

1. Read the original epic issue acceptance criteria.
2. Read the full diff of the epic branch against `<DEV_BASE>`:
   ```bash
   git diff "origin/$DEV_BASE"..."$EPIC_BRANCH"
   ```
3. For each acceptance criterion, verify it is met by the implementation. Produce a checklist with evidence (file paths, function names, test names).
4. Output `.claude-work/EPIC_<number>_VERIFICATION.md`.

The orchestrator reads the verification report. If any acceptance criteria are not met, report which ones and stop as a blocker.

---

## Step 7 — Epic PR

Create the final PR from the epic branch into `<DEV_BASE>`:

Spawn a **Documentation Agent** (`model: "opus"`) to produce the epic PR body.

### Documentation Agent instructions

Role: read-only research + PR body creation. No source file modifications.

1. Read the full epic diff:
   ```bash
   git diff "origin/$DEV_BASE"..."origin/$EPIC_BRANCH" --stat
   git diff "origin/$DEV_BASE"..."origin/$EPIC_BRANCH"
   ```
2. Read the original epic issue, all sub-issues, and their PRs.
3. Read `.claude-work/EPIC_<number>_DECOMPOSITION.md`, `.claude-work/EPIC_<number>_ADR.md` (if exists), and `.claude-work/EPIC_<number>_VERIFICATION.md`.
4. Produce the PR body.

```bash
gh pr create --repo <REPO> \
  --base "$DEV_BASE" \
  --head "$EPIC_BRANCH" \
  --title "epic(#<number>): <title>" \
  --body "$(cat <<'EOF'
Closes #<number>

## Epic Summary

<2-4 sentence executive summary: what the epic achieved, why this approach was chosen, and the key architectural decisions made.>

## Sub-Issues Resolved

| # | Issue | PR | Title | Summary |
|---|-------|----|-------|---------|
| 1 | #<num1> | #<pr1> | <title> | <one-line summary of changes> |
| 2 | #<num2> | #<pr2> | <title> | <one-line summary of changes> |
| ... | | | | |

## Architecture Decisions

<If ADR exists: summarize the key decisions and their rationale from the ADR.>
<If no ADR: "No cross-cutting architecture decisions were needed.">

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

<From .claude-work/EPIC_<number>_VERIFICATION.md>
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

## Step 8 — Resume Support

If `/resolve-epic` is re-run on an epic that already has sub-issues and an epic branch:

1. Detect existing epic branch:
   ```bash
   git ls-remote --heads origin "epic/<number>-*"
   ```
2. Detect existing sub-issues by searching for issues that reference the epic:
   ```bash
   gh issue list --repo <REPO> --search "epic #<number>" --json number,title,state
   ```
3. For each sub-issue, check if it has a merged PR targeting the epic branch:
   ```bash
   gh pr list --repo <REPO> --head "fix/issue-<sub_number>-*" --state merged --base "$EPIC_BRANCH" --json number
   ```
4. Skip completed sub-issues. Resume from the first incomplete one.
5. If the ADR was already approved (check for "APPROVED" comment on the epic), skip Step 3.

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

### Architecture Decisions
<summary or "None">

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

- **The orchestrator only delegates and reads.** It never runs git commands, gh commands, bash commands, or modifies any files. All actions (branch creation, issue creation, merging, testing, committing, pushing, posting comments) are performed by spawned subagents. The orchestrator's job is to: (1) spawn agents with the right instructions and context, (2) read their handoff blocks and artifact files, (3) decide what to do next based on those results.
- One epic branch per epic. One epic PR into `<DEV_BASE>`.
- Sub-issue PRs target the epic branch, not `<DEV_BASE>`.
- Sub-issue PRs are squash-merged into the epic branch automatically after `/resolve-issue` succeeds.
- The only human checkpoints are: ADR approval (Step 3) and final epic PR review (Step 7).
- If blocked, stop immediately and report. Do not attempt to skip sub-issues or work around failures.
- Never merge the epic branch into `<DEV_BASE>` — only create the PR. Human merges it.
- Never use `--admin` or bypass branch protection.
- Follow `~/.claude/guides/pr-guide.md` for all PR interactions.
- When handing off to a human (blockers, epic PR), always include the PR URL.
