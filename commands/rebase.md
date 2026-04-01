# Rebase

## Purpose

Prepare a `fix-issue` PR branch for merge after `/review-fix` has completed.

Run this **after** `/review-fix`. It drives three specialized agents and terminates in exactly one of two states:

- **READY** — rebased cleanly, intent preserved, CI passing, force-pushed, PR updated
- **BLOCKER** — something requires human intervention; no further automated changes are made

---

## Setup

### Git root detection (dev container safe)

Before any git operation, resolve the git working tree root. This is required because
in dev containers the shell may start at `/workspaces` which is above the repo mount:

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  # Try common dev container mount points
  for candidate in /workspaces/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
}
```

If `GIT_ROOT` is still empty, stop and tell the user:
"Could not find a git repository. Make sure you are inside a repo or pass the repo path."

**All `git` commands in this spec must run from `GIT_ROOT`** — either `cd "$GIT_ROOT"` first,
or use `git -C "$GIT_ROOT" <command>`.

### Parse arguments

Format is: `/rebase [branch] [base-branch]`
- `branch`: optional. If omitted, use current branch.
- `base-branch`: optional. If omitted, read from PR metadata; default to `main`.

Examples:
- `/rebase` → current branch, base from PR
- `/rebase fix/issue-42-foo` → that branch, base from PR
- `/rebase fix/issue-42-foo develop` → force base to develop

```bash
git -C "$GIT_ROOT" branch --show-current
gh pr list --head <branch> --json number,title,url,baseRefName,state --limit 1
```

If no open PR is found: stop — "No open PR found for branch `<branch>`. This skill requires an open PR."

Set:
- `BRANCH = <branch>`
- `PR_NUMBER = <from gh>`
- `BASE = <baseRefName from PR, or 'main'>`

Verify the working tree is clean:
```bash
git status --short
```
If uncommitted changes exist, stop and warn the user — do not proceed.

---

## Agent Roles

### Git Operator (orchestrator, inherits session model — should be Opus)

Owns the overall flow. Responsible for all git operations: squash, rebase, push, PR updates, issue comments. Spawns and sequences the other agents. Makes the final terminal-state determination. Does **not** fix application code.

### Merge Conflict Resolver (`model: "sonnet"`)

Activated only when `git rebase` hits conflict markers. Resolves conflict markers in the working tree. Scope is strictly limited to lines between `<<<<<<<` and `>>>>>>>`. Does **not** fix logic bugs, test failures, style issues, or anything beyond the conflict markers themselves. Reports each conflict as resolved or unresolvable.

### Senior Review Engineer (`model: "opus"`)

Activated once after rebase completes (conflicts resolved or absent). Read-only — makes **no** file changes. Compares the pre-rebase diff against the post-rebase diff to verify the original fix intent is fully preserved. Reports clean or lists specific intent risks. Findings do not trigger automated fixes — they are either accepted by the Git Operator (trivial/cosmetic) or escalate to BLOCKER.

---

## Flow

```
Git Operator
  │
  ├─ Pre-flight checks
  ├─ Inventory + remove artifact files
  ├─ git rebase origin/<BASE>
  │     │
  │     ├─ conflicts? ──► Merge Conflict Resolver
  │     │                   └─ unresolvable? ──► BLOCKER
  │     │
  │     └─ clean
  │
  ├─ Senior Review Engineer (read-only)
  │     └─ intent risks found? ──► BLOCKER
  │
  ├─ Local sanity checks (compile/lint — no tests)
  │     └─ failing? ──► BLOCKER
  │
  ├─ force-push --force-with-lease
  │
  ├─ Detect CI mode (partition required checks into external vs local)
  │     │
  │     ├─ LOCAL_CHECKS? ──► Run locally + upload as commit statuses
  │     │     └─ new failure? ──► BLOCKER
  │     │
  │     ├─ EXTERNAL_CHECKS? ──► Poll gh pr checks --watch
  │     │     └─ new failure vs pre-rebase baseline? ──► BLOCKER
  │     │
  │     └─ (may be both — run local first, then wait for external)
  │
  └─ update PR, post comment ──► READY
```

---

## Step 1 — Pre-flight (Git Operator)

### Check `/review-fix` completeness

Locate the review-fix summary posted to the PR by `/review-fix`. It is identified by the
`<!-- review-fix-summary -->` sentinel in a PR comment body.

```bash
gh pr view <PR_NUMBER> --json comments --jq '
  .comments[]
  | select(.body | contains("<!-- review-fix-summary -->"))
  | .body'
```

**If no matching comment is found:**
Warn the user — "No `/review-fix` summary found on PR #<PR_NUMBER>. Consider running
`/review-fix` before rebasing. Continue anyway? [yes/no]"
Wait for user reply. If no, stop.

**If the comment is found**, parse it for the following signals:

1. **Critical or major findings remaining** — look for non-zero counts in the
   "Final review state" table or entries in "Outstanding findings" with severity
   `critical` or `major`.
   If found: warn — "Unresolved critical/major findings in the review-fix summary.
   Continue anyway? [yes/no]" Wait for user reply. If no, stop.

2. **Intent validation risks** — look for `high` risk entries under "Intent validation".
   If found: warn — "High intent risks flagged in the review-fix summary.
   Continue anyway? [yes/no]" Wait for user reply. If no, stop.

3. **Overall status** — extract for use in the final PR comment and READY/BLOCKER output.

Store the full comment body as `REVIEW_FIX_SUMMARY` for reference in Step 8 and
Terminal States output.

### Capture pre-rebase CI baseline from the PR

```bash
gh pr checks <PR_NUMBER> --json name,status,conclusion
```

Note which checks are currently failing or pending. This is the baseline — after the
force push, any check that was already failing before the rebase is not a rebase
regression. Store results as `PRE_REBASE_CI`.

If the command returns no checks at all, the PR may not have CI configured yet (e.g.
the branch was just pushed). That is acceptable — record `PRE_REBASE_CI = none` and
proceed. CI will be evaluated after the force push in Step 7b.

---

## Step 2 — Inventory + Remove Artifacts (Git Operator)

### List artifact files

```bash
git diff <BASE>...HEAD --name-only
```

Identify files matching these patterns — they are planning/review artifacts that must not land on the base branch:
- `ISSUE_*_PLAN.md`, `ISSUE_*_ADR.md`, `ISSUE_*_REVIEW.md`
- `REVIEW_FINDINGS*.md`, `FIX_PLAN*.md`, `FIX_RESULT_*.md`
- `INTENT_VALIDATION.md`, `REBASE_INTENT_REVIEW.md`, `CONFLICT_RESOLUTION.md`

### Present inventory to the user

```
## Rebase preparation: <BRANCH> → <BASE>

### Commits on branch (<N> total)
  abc1234  fix(#42): implement feature X
  def5678  fix(#42): add tests
  111aaaa  fix(review): address F-1-1, F-1-2
  222bbbb  fix(review): address F-2-1

### Artifact files to remove (<N>)
  ISSUE_42_PLAN.md
  REVIEW_FINDINGS_1.md
  FIX_RESULT_F-1-1.md
  INTENT_VALIDATION.md
  ...

Proceeding — no user input required.
```

Branch will be squash-merged — individual commit history is discarded at merge time.

### Remove artifact files

```bash
git rm <artifact-file> [...]
```

If any artifact was never git-tracked, delete it from disk only.

Commit the removals:
```bash
git add -u
git commit -m "chore: remove fix-issue planning artifacts"
```

---

## Step 3 — Rebase (Git Operator)

```bash
git fetch origin
git rebase origin/<BASE>
```

If the rebase exits cleanly (no conflicts): proceed directly to Step 4.

If conflicts are reported: pause all other work and spawn the **Merge Conflict Resolver**.

---

## Merge Conflict Resolver — Instructions

**Scope**: conflict markers only. Do not touch any line that is not inside a conflict block.

For each conflicted file:

1. Read the file. Locate every block delimited by `<<<<<<<`, `=======`, `>>>>>>>`.

2. For each block:
   - `ours` (between `<<<<<<<` and `=======`) = the fix-branch version
   - `theirs` (between `=======` and `>>>>>>>`) = the base branch version
   - Default rule: **preserve the fix-branch intent**. When in doubt, keep `ours`.
   - If both sides changed genuinely independent lines (e.g. a function the base moved and a different function the fix changed), produce a merge that includes both.
   - If the same logic was changed on both sides and the changes are semantically incompatible, **do not guess** — mark as unresolvable.

3. After resolving a file: `git add <file>`

4. For each conflict report:
   ```
   ### Resolved: <filename>
   **Block**: line <N>–<M>
   **Ours**: <quoted lines>
   **Theirs**: <quoted lines>
   **Resolution**: kept ours / merged both / [explanation]

   ### Unresolvable: <filename>
   **Block**: line <N>–<M>
   **Ours**: <quoted lines>
   **Theirs**: <quoted lines>
   **Why unresolvable**: <explanation of incompatibility>
   ```

5. Output `CONFLICT_RESOLUTION.md` with all findings.

6. If all conflicts resolved: `git rebase --continue`
   If any unresolvable: `git rebase --abort` and return UNRESOLVABLE status to Git Operator.

**Do not** fix logic bugs discovered while reading. **Do not** improve code noticed along the way. **Do not** modify test files. Conflict markers only.

---

### Git Operator: handle Conflict Resolver result

- **All resolved**: read `CONFLICT_RESOLUTION.md`, confirm no unresolvable entries, proceed to Step 4.
- **Any unresolvable**: → **BLOCKER** (see Terminal States).

---

## Step 4 — Intent Validation (Senior Review Engineer)

Spawn the **Senior Review Engineer** after the rebase is clean.

### Senior Review Engineer — Instructions

**Role**: Read-only. Make no file changes.

**Goal**: Verify the rebase + squash did not accidentally drop, invert, or neutralise any part of the original fix.

1. Fetch the PR's original intent:
   ```bash
   gh pr view <PR_NUMBER> --json title,body,number
   gh issue view <issue-number> --json title,body,comments
   ```
   Extract: what bug/feature was being addressed, what invariants the fix established.

2. Reconstruct the pre-rebase diff. Use the commit inventory from Step 2 to identify which commits were authored by fix-issue:
   ```bash
   # pre-rebase state: what the implementation commits actually changed
   git show <impl-commit-sha> --stat --patch
   ```
   If strategy A was used, the pre-rebase content is available in the reflog:
   ```bash
   git reflog | head -20
   git diff <pre-squash-sha>...HEAD
   ```

3. Compare pre-rebase vs post-rebase diff for every file in the PR:
   ```bash
   git diff origin/<BASE>...HEAD
   ```

4. Check explicitly for these failure patterns:
   - **Ordering reversals**: statements reordered by squash/rebase that change runtime behaviour
   - **Guard removal**: a defensive check added by the fix is no longer present
   - **Logic inversion**: a condition's polarity flipped
   - **Dead code path**: the fix's code path is now unreachable
   - **Config neutralisation**: a value set by the fix was overwritten

5. For each concern:
   ```
   ### [INTENT-RISK: high|medium|low] <short title>
   **File**: path/to/file:line
   **Original intent**: what the fix was establishing here
   **Pre-rebase**: <quoted lines>
   **Post-rebase**: <quoted lines>
   **Risk**: why this may undermine the fix
   **Recommended action**: revert automated change | manual review needed
   ```

6. If no concerns: output `No intent risks detected.`

7. Write `REBASE_INTENT_REVIEW.md`.

---

### Git Operator: handle Senior Review Engineer result

Read `REBASE_INTENT_REVIEW.md`.

- **No findings / low-risk only**: accept and proceed to Step 5. Note low-risk findings in the PR comment.
- **Medium-risk findings**: present to the user with recommended actions. Wait for user reply — user may accept or declare BLOCKER.
- **Any high-risk finding**: → **BLOCKER** (see Terminal States).

---

## Step 5 — Local Sanity Checks (Git Operator)

Run any fast local checks to catch obvious breaks before wasting a CI run:

```bash
<compile command if applicable>
<typecheck command if applicable>
<lint command if applicable>
```

Do **not** run the full test suite here — that is the job of Step 7b (PR CI).

**Rules**:
- If local checks pass (or no local toolchain is configured): proceed to Step 7.
- If local checks fail: → **BLOCKER**. Do not push broken code.
- **Do not modify any source files to fix failures.**
- **Do not modify any test files under any circumstances.**
- The Merge Conflict Resolver's scope ended at Step 4. No agent fixes code after rebase.

---

## Step 7 — Force Push (Git Operator)

Local checks pass and intent is validated. Push now so CI can run on the PR.

### Force push

```bash
git push --force-with-lease origin <BRANCH>
```

Rules:
- Always `--force-with-lease`, never bare `--force`.
- Never push to `main`, `master`, or any protected branch.
- If `--force-with-lease` fails (someone else pushed): fetch, re-examine, report to user before retrying.

---

## Step 7a — Detect CI Mode (Git Operator)

After force-push, determine which required checks are handled by external CI and
which must be run locally and uploaded as commit statuses. A repo may use external
CI for some checks and local upload for others.

### Fetch required status checks from branch protection

```bash
gh api repos/{owner}/{repo}/branches/<BASE>/protection/required_status_checks \
  --jq '.checks[].context' 2>/dev/null
```

Store the list as `REQUIRED_CHECKS`. If the endpoint returns 404 or an empty list,
there are no specific gated checks — skip to Step 7b and just poll whatever CI
reports.

### Wait for external CI to claim checks

```bash
sleep 60
SHA=$(git rev-parse HEAD)
gh api repos/{owner}/{repo}/commits/$SHA/status --jq '.statuses[].context'
gh api repos/{owner}/{repo}/commits/$SHA/check-runs --jq '.check_runs[].name'
```

Combine both lists into `REPORTED_CHECKS` (commit statuses + check runs).

### Partition into external vs local

Compare `REQUIRED_CHECKS` against `REPORTED_CHECKS`:

- `EXTERNAL_CHECKS` = required checks that **do** appear in `REPORTED_CHECKS`
  (any state — pending, in_progress, success, failure). External CI has claimed these.
- `LOCAL_CHECKS` = required checks that are **not** in `REPORTED_CHECKS`.
  No external system is reporting these — the agent must run and upload them.

Possible outcomes:
- All required checks are external → run Step 7b only
- All required checks are local → run Step 7b-local only
- Mixed → run Step 7b-local for `LOCAL_CHECKS` first, then Step 7b to wait for
  `EXTERNAL_CHECKS` to complete

---

## Step 7b — Wait for External CI (Git Operator)

_Runs when `EXTERNAL_CHECKS` is non-empty (or when no specific checks are gated)._

External CI (GitHub Actions or similar) is handling these checks. Poll until all
external checks reach a terminal state:

```bash
# Poll every 30 seconds, up to 20 minutes
gh pr checks <PR_NUMBER> --watch
```

If `gh pr checks --watch` is unavailable, poll manually:
```bash
gh pr checks <PR_NUMBER> --json name,status,conclusion
```
Repeat until all entries show `status: completed`. Wait up to 20 minutes total.
If checks have not completed after 20 minutes, stop and report to the user —
do not proceed to READY while checks are still pending.

**Evaluate results** once all checks complete:

For each check, compare against `PRE_REBASE_CI` captured in Step 1:

| Scenario | Action |
|---|---|
| Check was passing before and is passing now | OK |
| Check was failing before and is still failing | Pre-existing failure — note it, do not block |
| Check was passing before and is now failing | **Rebase regression → BLOCKER** |
| Check was absent before (new check triggered by push) and passes | OK |
| Check was absent before and fails | Treat as rebase regression → **BLOCKER** |

If any **BLOCKER** condition is found:
- Do **not** update the PR description or post the merge-ready comment.
- Proceed directly to the BLOCKER terminal state.
- Report the failing check name, its log URL, and whether it was passing before the rebase.
- **Do not modify any source files or test files.**

If all checks pass (or only pre-existing failures remain): proceed to Step 8.

---

## Step 7b-local — Run Checks and Upload Statuses (Git Operator)

_Runs when `LOCAL_CHECKS` is non-empty._

Some or all required branch-protection checks are not provided by external CI. The
agent must run them locally and post results as GitHub commit statuses so the PR
can merge. Only run checks listed in `LOCAL_CHECKS` — external checks are handled
by Step 7b.

### Setup

```bash
SHA=$(git rev-parse HEAD)
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
```

### Run each required check and upload its status

For each check context in `REQUIRED_CHECKS`, map the context name to a local command
and execute it. Use the repo's toolchain to determine the correct commands. Common
mappings:

| Context | Typical command |
|---|---|
| `ruff-lint` | `ruff check .` |
| `ruff-format` | `ruff format --check .` |
| `pytest` | `pytest --ignore=tests/integration -x` (or equivalent non-integration test run) |
| `mypy` | `mypy .` |
| _other_ | Infer from toolchain config (`pyproject.toml`, `package.json`, `Makefile`, etc.) |

If you cannot determine the command for a required check, do **not** guess — report
it as a blocker: "Cannot determine local command for required check `<context>`.
Configure the check mapping or run it manually."

For each check, run and upload immediately:

```bash
# Example for a single check — repeat for each REQUIRED_CHECK
CONTEXT="<check-context-name>"
DESCRIPTION="<short description of what ran>"

<local-command> 2>&1 | tee /tmp/check-${CONTEXT}.log
if [ $? -eq 0 ]; then
  CHECK_STATE=success
else
  CHECK_STATE=failure
fi

gh api repos/$REPO/statuses/$SHA \
  -f state="$CHECK_STATE" \
  -f context="$CONTEXT" \
  -f description="$DESCRIPTION"
```

### Evaluate results

After all checks are uploaded, evaluate:

| Scenario | Action |
|---|---|
| All uploaded checks passed | Proceed to Step 8 |
| A check failed that was also failing in `PRE_REBASE_CI` | Pre-existing — note it, do not block |
| A check failed that was passing in `PRE_REBASE_CI` or is new | **Rebase regression → BLOCKER** |

**Rules** (same as external CI):
- **Do not modify any source files or test files** to fix failures.
- On BLOCKER, do not update the PR description or post the merge-ready comment.
- Report the failing check name and relevant log output.

---

### Update PR description

```bash
gh pr view <PR_NUMBER> --json body --jq '.body'
```

Rewrite, preserving the original "What changed" and "Tier / approach" sections:

```bash
gh pr edit <PR_NUMBER> --body "$(cat <<'EOF'
Closes #<number>

## What changed
<preserved from original PR description>

## Tier / approach
<preserved from original PR description>

## Acceptance criteria
<from ISSUE_<number>_PLAN.md — all checked if final review was clean>
- [x] <criterion>
- [x] <criterion>

## Review summary
- Cycles run: <N>
- Findings fixed: <total>
- Intent validation: clean / <N> low-risk notes
- Outstanding: <deferred minor findings, or "None">

## History
Squash: <A: single commit | B: impl + review-fix | C: kept as-is>
Rebased onto `<BASE>` — PR CI passing.

## Merge instructions
Merge via **squash merge** (not merge commit or rebase merge).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Post merge-ready comment

```bash
gh pr comment <PR_NUMBER> --body "$(cat <<'EOF'
## Ready for merge

Branch `<BRANCH>` has been rebased onto `<BASE>`.

**Squash strategy**: <description>
**Conflicts**: <N resolved, or "none">
**Intent validation**: <clean | N low-risk notes — see REBASE_INTENT_REVIEW.md>
**PR CI**: all checks passing

Merge via **squash merge** when ready. No further automated changes will be made to this branch.
EOF
)"
```

---

## Terminal States

### READY

Reached when: rebase clean, no unresolved conflicts, intent validated, CI passing, force-pushed.

```bash
gh pr comment <PR_NUMBER> --body "$(cat <<'EOF'
## READY — terminal state reached

All automated rebase steps completed successfully. This PR requires no further automated work.

Next step: human approval, then merge via **squash merge**.
EOF
)"
```

Present final summary to user:

```
## rebase complete — READY

Branch:   <BRANCH>
Base:     <BASE>
Squash:   <A / B / C>
Commits:  <N before> → <N after>
Artifacts removed: <N files>
Conflicts resolved: <N, or "none">
Intent validation: <clean / N low-risk notes>
PR CI: all checks passing
Push: force-with-lease ✓

PR: <url>
Status: READY — awaiting human review, then squash merge
```

---

### BLOCKER

Reached when any of the following occur:
- Unresolvable merge conflict (Conflict Resolver returned UNRESOLVABLE)
- High-risk intent finding (Senior Review Engineer)
- New test/CI failure after rebase (Step 6)
- User declined to proceed at any confirmation prompt

**Immediately abort further automated steps.**

Do not push. Do not modify any files beyond what has already been staged/committed.

Post a blocker comment to the PR:

```bash
gh pr comment <PR_NUMBER> --body "$(cat <<'EOF'
## BLOCKER — human intervention required

Automated rebase could not complete. No push has been made.

**Reason**: <one of the below>

### Unresolvable conflict
File: <file>
Block: lines <N>–<M>
Ours:   <quoted>
Theirs: <quoted>
Why: <explanation>

### Intent risk (high)
<paste finding from REBASE_INTENT_REVIEW.md>

### CI regression after rebase
Failed check: <name>
Error output:
```
<error>
```
Note: test files were not modified. This regression requires human investigation.

---

Branch is at: <current SHA — safe to inspect>
To continue: resolve the blocker manually, then re-run `/rebase`.
EOF
)"
```

Present to user:

```
## rebase terminated — BLOCKER

Branch: <BRANCH> (not pushed)
Reason: <unresolvable conflict | intent risk | CI regression>

Details:
<paste the relevant section from the blocker comment above>

Action required: resolve manually, then re-run `/rebase`.
```

---

## Constraints (all agents)

- Follow `~/.claude/guides/pr-guide.md` for all PR and commit interactions.
- **Never push to main, master, or any protected branch.**
- **Always use `--force-with-lease`**, never bare `--force`.
- **Never merge** — only prepare for merge.
- **Never modify test files** — under any circumstances, in any agent.
- **Merge Conflict Resolver scope**: conflict markers only. No other code changes.
- **Senior Review Engineer**: read-only. No file changes.
- **Git Operator**: git operations and PR metadata only. No application code fixes.
- If any agent is uncertain whether a change is within scope, the answer is no — stop and report to the Git Operator, which escalates to BLOCKER if needed.
- One terminal state per run. Once BLOCKER or READY is declared, no further automated changes are made.
- When handing off to a human (blockers, errors, confirmation prompts), always include the PR URL so the user can navigate to it directly.
