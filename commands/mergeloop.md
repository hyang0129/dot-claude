# Merge Loop

## Purpose

Attempt to merge a single PR, automatically resolving supported blockers and retrying until the PR merges or an unresolvable blocker is hit.

Supported blockers (automatically resolved):
- **BEHIND** — branch is behind base → invoke `/rebase`, then retry merge
- **NO_CHECKS** — required checks are not yet reported → run the `uv` checks script and upload commit statuses, then retry merge

Unsupported blockers (stop immediately):
- Merge conflicts that cannot be auto-resolved
- CI failing (non-check-upload causes)
- Branch protection rules (required reviews, admin restrictions, etc.)
- Any other state not listed above

---

## Setup

### Git root detection (dev container safe)

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  for candidate in /workspaces/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
}
```

If `GIT_ROOT` is still empty, stop: "Could not find a git repository."

**All `git` commands must run from `GIT_ROOT`.**

### Parse arguments

Format: `/mergeloop [PR_NUMBER]`

- `PR_NUMBER`: optional. If omitted, detect from current branch:
  ```bash
  BRANCH=$(git -C "$GIT_ROOT" branch --show-current)
  gh pr list --head "$BRANCH" --json number,title,url,baseRefName,state --limit 1
  ```

If no open PR is found, stop: "No open PR found. Pass a PR number or check out the PR branch."

Set:
- `PR_NUMBER = <number>`
- `BRANCH = <headRefName>`
- `BASE = <baseRefName>`
- `PR_URL = <url>`

Verify the working tree is clean:
```bash
git -C "$GIT_ROOT" status --short
```
If uncommitted changes exist, stop: "Working tree is not clean. Commit or stash changes first."

---

## Flow

```
Setup
  |
  Loop:
  |
  +-- Fetch PR merge state
  |
  +-- CLEAN / UNSTABLE ──────────────────► Attempt merge
  |                                           |
  |                                   success: DONE
  |                                   failure: check error → BLOCKER if unrecognised
  |
  +-- BEHIND ────────────────────────► /rebase <BRANCH> <BASE>
  |                                     READY  → loop (re-fetch state)
  |                                     BLOCKER → stop
  |
  +-- BLOCKED (no checks) ───────────► Run uv checks + upload statuses → loop
  |
  +-- BLOCKED (other) / CI failing ──► BLOCKER (stop)
  |
  +-- (max 10 iterations) ───────────► BLOCKER (safety limit)
```

---

## Step 1 — Fetch PR Merge State

```bash
gh pr view "$PR_NUMBER" --json mergeable,mergeStateStatus,statusCheckRollup \
  --jq '{mergeable,mergeStateStatus,checks: .statusCheckRollup}'
```

Also fetch required status checks from branch protection:
```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
REQUIRED_CHECKS=$(gh api "repos/$REPO/branches/$BASE/protection/required_status_checks" \
  --jq '.checks[].context' 2>/dev/null || echo "")
```

Classify the state:

| `mergeStateStatus` | Checks | Classification |
|--------------------|--------|----------------|
| `CLEAN` or `UNSTABLE` | — | **READY_TO_MERGE** |
| `BEHIND` | — | **BEHIND** |
| `BLOCKED` | no checks reported for required contexts | **NO_CHECKS** |
| `BLOCKED` | checks present and failing | **CI_FAILING** |
| `BLOCKED` | checks passing but other rule (review, admin) | **HARD_BLOCKED** |

**NO_CHECKS detection**: compare `REQUIRED_CHECKS` against the `statusCheckRollup` names. If one or more required check contexts have no matching entry in the rollup (i.e. no external CI has reported them), classify as **NO_CHECKS**.

---

## Step 2 — Route

### READY_TO_MERGE → Step 3

### BEHIND → Step 4

### NO_CHECKS → Step 5

### CI_FAILING → BLOCKER

```
PR #<N> is BLOCKED: required checks are failing.
Failing checks:
  - <check name>: <conclusion>

This blocker is not automatically resolvable. Human intervention required.
PR: <PR_URL>
```

### HARD_BLOCKED → BLOCKER

```
PR #<N> is BLOCKED: <reason — required reviews, admin restriction, etc.>
This blocker is not automatically resolvable. Human intervention required.
PR: <PR_URL>
```

---

## Step 3 — Attempt Merge

```bash
gh pr merge "$PR_NUMBER" --squash --delete-branch
```

**If merge succeeds**: report DONE (see Terminal States).

**If merge fails**: inspect the error message.
- If the error indicates the branch fell behind (race condition): re-classify as **BEHIND**, loop.
- If the error indicates checks are now pending: wait 30 seconds, loop.
- Any other error: → BLOCKER, report the raw error.

---

## Step 4 — Rebase (BEHIND)

The branch is behind `BASE`. Invoke `/rebase`:

```
/rebase <BRANCH> <BASE>
```

Wait for `/rebase` to complete. It terminates in one of two states:

**READY**: `/rebase` has force-pushed and confirmed CI passing. Loop back to Step 1.

**BLOCKER**: `/rebase` could not complete. `/rebase` has already posted a BLOCKER comment on the PR. Stop here:

```
PR #<N>: /rebase hit a BLOCKER. Merge loop stopping.
See the BLOCKER comment on the PR for details.
PR: <PR_URL>
```

Do not attempt any further automated action.

---

## Step 5 — Run Checks (NO_CHECKS)

Required checks are not being reported by external CI. Upload them as commit statuses by running checks locally.

### Setup

```bash
SHA=$(git -C "$GIT_ROOT" rev-parse HEAD)
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
```

Make sure we are on the PR branch and it is up to date:
```bash
git -C "$GIT_ROOT" checkout "$BRANCH"
git -C "$GIT_ROOT" fetch origin "$BRANCH"
git -C "$GIT_ROOT" reset --hard "origin/$BRANCH"
```

### Discover the check upload script

Search the repo's `CLAUDE.md` for a documented command or script for uploading CI checks. Look for sections mentioning "CI", "checks", "status upload", or "local checks" and extract the command or script path.

**If a documented script or command is found**: run it as written — do not modify it. Treat its exit code as the overall check result. Document which script was used in the terminal state output.

**If no documented script is found**: → BLOCKER

```
PR #<N>: required checks are not being reported and no check-upload script is documented in CLAUDE.md.

To resolve: add a section to CLAUDE.md documenting the command or script used to run and upload CI checks, then re-run /mergeloop.
PR: <PR_URL>
```

**Constraints (strictly enforced)**:
- Run the script **as-is**. Do **not** modify any source file, test file, or configuration file to make a check pass.
- Do **not** add `# noqa` comments, skip markers, or any inline suppression.
- Do **not** change test files under any circumstances.
- If the script fails: stop → BLOCKER (see below).
- The only permitted output of this step is running the documented script.

### After running the script

If the script **succeeded**: loop back to Step 1 (the PR should now see checks and may be mergeable).

If the script **failed**: → BLOCKER

```
PR #<N>: check script failed.

Script: <path or command that was run>
Output:
<first 40 lines of output>

No source files were modified. Human intervention required to fix the failing check.
PR: <PR_URL>
```

---

## Safety limit

If the loop has iterated 10 times without reaching a terminal state, stop:

```
Merge loop safety limit reached (10 iterations) without merging PR #<N>.
Last state: <classification>
PR: <PR_URL>

Stopping to avoid an infinite loop. Investigate manually.
```

---

## Terminal States

### DONE

```
## Merge loop complete — DONE

PR #<PR_NUMBER> merged successfully.

Branch:     <BRANCH>
Base:       <BASE>
Iterations: <N>
Actions taken:
  <bulleted list: "rebase (iteration N)", "uploaded uv checks (iteration N)", "merged">

PR: <PR_URL>
```

### BLOCKER

```
## Merge loop stopped — BLOCKER

PR #<PR_NUMBER> could not be merged automatically.

Branch:     <BRANCH>
Base:       <BASE>
Iterations: <N>
Last state: <classification>
Reason:     <one-line summary>

<detail block from the failing step>

Action required: resolve the blocker manually, then re-run /mergeloop.
PR: <PR_URL>
```

---

## Constraints

- **Never push to `main`, `master`, or any protected branch.**
- **Never modify source files or test files** — this command only orchestrates merges, rebases, and check uploads.
- **Never use `--admin`** to force through a merge. If branch protection blocks the merge, report BLOCKER.
- **Only use `/rebase` for behind-branch resolution.** Do not run `git merge`, `git rebase` directly, or attempt conflict resolution here.
- **uv checks step is read-only except for uploading commit statuses.** No file edits of any kind.
- **One PR per invocation.** This command does not process a queue; see `/merge-queue` for that.
- Always include `PR_URL` in every terminal state and blocker message so the user can navigate directly.
