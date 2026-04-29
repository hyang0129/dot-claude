---
version: 1.1.0
---

# PR Review Cycle

## Setup

### Git root detection (dev container safe)

Before any git operation, resolve the git working tree root. This is required because
in dev containers the shell may start at `/workspaces` which is above the repo mount:

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$GIT_ROOT" ]; then
  # Try common locations: dev container mount points (1 and 2 levels deep), home repos dir, home itself
  for candidate in /workspaces/* /workspaces/*/* "$HOME"/repos/* "$HOME"/repo/* "$HOME"/projects/* "$HOME"/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
fi
```

If `GIT_ROOT` is still empty, stop and tell the user:
"Could not find a git repository. Make sure you are inside a repo or pass the repo path as the first argument: `/pr-review-cycle <repo-path> [branch] [cycles]`"

If a repo path is passed as an argument (a path starting with `/` or `~`), use it directly as `GIT_ROOT` and shift the remaining arguments for branch/cycles parsing.

**All `git` commands in this spec must run from `GIT_ROOT`** — either `cd "$GIT_ROOT"` first,
or use `git -C "$GIT_ROOT" <command>`.

Verify the `.agent-work/` scratch directory exists:
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

All artifact files produced during this session are written to `$GIT_ROOT/.agent-work/`.
They are gitignored via `.git/info/exclude` and are never committed or pushed.

### Parse arguments

Format is: `/pr-review-cycle [repo-path] [branch] [cycles]`
- `repo-path`: optional absolute path to the repo root (starting with `/` or `~`). Use this when the working directory is not inside the repo (e.g. `/workspaces/hub_6` when the repo is at `~/repos/video_agent_long`). If provided, set `GIT_ROOT` to this path.
- `branch`: optional branch name. If omitted, use: `git -C "$GIT_ROOT" branch --show-current` (only after `GIT_ROOT` is confirmed non-empty)
- `cycles`: optional integer, default `2`. Must be ≥ 1.

Examples:
- `/pr-review-cycle` → current branch, 2 cycles
- `/pr-review-cycle ~/repos/video_agent_long` → that repo, current branch, 2 cycles
- `/pr-review-cycle feature/xyz` → that branch, 2 cycles
- `/pr-review-cycle feature/xyz 3` → that branch, 3 cycles
- `/pr-review-cycle 3` → if the first argument is a plain integer, treat it as cycles on the current branch
- `/pr-review-cycle ~/repos/video_agent_long feature/xyz 3` → that repo, that branch, 3 cycles

This means the Reviewer runs `cycles + 1` times total: once before each fix cycle, plus a final read-only review at the end. The last review never triggers fixes.

### Parse named flags

After positional argument parsing, scan the remaining argv for named flags.

**`--reviewer-model=<model-id>`** (default: `claude-opus-4-7`)
- Accept the flag anywhere in argv — before, between, or after positional args.
- Match with a regex like `^--reviewer-model=(.+)$` against each remaining token; on match, set `REVIEWER_MODEL` and remove the token from argv.
- Validate against this allow-list:
  - `claude-opus-4-7` (default)
  - `claude-opus-4-6`
  - `claude-sonnet-4-6`
  - `claude-haiku-4-5`
- If the value is not in the allow-list, stop and tell the user:
  > Unknown `--reviewer-model=<value>`. Allowed: `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`.
- If the flag is absent, set `REVIEWER_MODEL=claude-opus-4-7`.
- `REVIEWER_MODEL` is bound for the entire invocation — all cycles run with the same model. It is NOT re-parsed per cycle.

This flag is exclusively for A/B testing Reviewer quality vs. cost. The Fixer and Intent Validator models are not configurable at this time.

Find the associated PR:
```
gh pr list --head <branch> --json number,title,url,state --limit 1
```
If no PR is found, stop and tell the user: "No open PR found for branch `<branch>`. Create one first or pass a branch name explicitly: `/pr-review-cycle <branch>`"

Fetch full PR context:
```
gh pr view <pr-number> --json number,title,body,baseRefName,headRefName,files,additions,deletions
gh pr diff <pr-number>
```

Check for existing reviews:
```
gh pr view <pr-number> --json reviews --jq '.reviews | length'
```
If the result is `0` (no reviews), set `NEEDS_INITIAL_REVIEW = true`. Otherwise set it to `false`.


### Capture pre-loop HEAD

Before any Fixer commits anything, record the current branch tip so the Intent Validator can later diff pre-loop vs post-loop state:

```bash
git -C "$GIT_ROOT" rev-parse HEAD > "$GIT_ROOT/.agent-work/PRE_LOOP_HEAD.sha"
```

This SHA is the boundary between "what the PR author wrote" and "what the automated fix-loop added".

### Assemble review bundle

Write `.agent-work/REVIEW_BUNDLE.md` before the first Reviewer spawn. The bundle is reused across all Reviewer invocations in this run (Initial, Cycle N, Final).

```bash
PR_NUM=<pr-number>
BUNDLE="$GIT_ROOT/.agent-work/REVIEW_BUNDLE.md"

{
  echo "# Review bundle for PR #$PR_NUM"
  echo
  echo '## PR metadata'
  gh pr view "$PR_NUM" \
    --json number,title,body,baseRefName,headRefName,additions,deletions \
    --jq '"- Title: " + .title + "\n- Base: " + .baseRefName
          + "\n- Head: " + .headRefName
          + "\n- +" + (.additions|tostring) + " / -" + (.deletions|tostring)
          + "\n\n### Body\n" + .body'
  echo
  echo '## PR diff'
  echo '```diff'
  gh pr diff "$PR_NUM"
  echo '```'
  echo
  echo '## Repo context'
  [ -f "$GIT_ROOT/CLAUDE.md" ]      && { echo '### $GIT_ROOT/CLAUDE.md';   cat "$GIT_ROOT/CLAUDE.md"; }
  [ -f "$HOME/.claude/CLAUDE.md" ]  && { echo '### ~/.claude/CLAUDE.md';    cat "$HOME/.claude/CLAUDE.md"; }
  INDEX="$GIT_ROOT/docs/agent_index.md"
  [ -f "$INDEX" ]                    && { echo '### docs/agent_index.md (first 200 lines)'; head -n 200 "$INDEX"; }
  [ -f "$GIT_ROOT/.codesight/CODESIGHT.md" ] && { echo '### .codesight/CODESIGHT.md'; cat "$GIT_ROOT/.codesight/CODESIGHT.md"; }
} > "$BUNDLE"
```

Track state:
- `CURRENT_CYCLE = 1`
- `MAX_CYCLES = <cycles>`

---

## Subagent Context Bootstrap

When spawning the **Fixer**, prepend these instructions to its prompt:

> **Context bootstrap** (do this before your main task):
> 1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions) if they exist. Follow all instructions — repo instructions override global ones.
> 2. Read codebase index files if present:
>    - `.codesight/CODESIGHT.md` at `$GIT_ROOT`
>    - `docs/agent_index.md` at `$GIT_ROOT`
>    - If no agent index was found at the above path, glob for `**/agent_index.md` at `$GIT_ROOT` and read any match.

The **Reviewer** and **Intent Validator** do NOT receive this preamble — their respective bundles (`REVIEW_BUNDLE.md`, `INTENT_BUNDLE.md`) already contain the repo + global `CLAUDE.md` and the codebase index excerpt inline.

---

## Agent Roles

### Agent 1 — Reviewer (`model: $REVIEWER_MODEL`, default `claude-opus-4-7`)

**Role**: Read-only analysis. Do NOT make any changes to files.

**Context bundle (already in your prompt)**:

The review bundle below contains:
- PR metadata (title, body, base, head, +/- counts)
- The full PR diff
- Repo `CLAUDE.md`, global `~/.claude/CLAUDE.md`, and the codebase index excerpt

Use `Read`/`Grep` freely to fetch full file contents, callers of touched functions, or analogous patterns elsewhere in the codebase whenever the diff alone is insufficient context.

When spawning, the skill inlines `$(cat $GIT_ROOT/.agent-work/REVIEW_BUNDLE.md)` into the `<BUNDLE>` slot below:

```
<BUNDLE>
```

**Instructions**:
1. Understand the intent from the PR title and description (in the bundle metadata). Also extract **documented intent signals**: docstrings containing phrases like "by design", "intentionally", "permissive", "do not enforce", "not an error", or equivalent; explicit design statements in the PR body; and any linked issue if the PR body includes a `Closes #N` / `Fixes #N` reference. Collect these signals before reading the diff.

2. **Tier every finding.** Before writing a finding, classify it into exactly one tier. The tier controls downstream handling:

   - **Tier `fix`** — Orchestrator will auto-apply via a Fixer. Only assign `fix` when **all three** hold:
     - *Unique resolution*: there is exactly one correct answer. Not "change the code" vs. "change the spec."
     - *Local blast radius*: the change lives inside a single function or narrow seam; no public API, persisted data shape, or cross-cutting pattern changes.
     - *No design commitment*: applying the fix doesn't commit the project to a pattern, abstraction, structure, or convention that reasonable engineers could disagree about.

   - **Tier `propose`** — Surfaced as a review comment with a proposed diff; not applied. Use when the finding is a genuine improvement but the resolution involves a judgment call: pattern divergence, refactoring suggestions, naming, clarity, minor structural reshuffles, performance tradeoffs, tests for non-critical paths.

   - **Tier `escalate`** — Surfaced as a proposed follow-up issue; no Fixer runs. Use when **any** of these hold:
     - Resolution would require **new modules, new abstractions, new public types, or new schemas**.
     - Resolution would require **new test surface** (writing tests for newly-introduced behavior, not just fixing a broken existing test).
     - The diff needed would exceed roughly **20% of the PR's own diff size**.
     - Resolution would **change the PR's acceptance criteria** (narrowing or expanding what the PR commits to).
     - The finding is **off-topic** — unrelated to the PR's stated purpose (former "scope creep" bucket).
     - Resolution requires **author context** the bundle doesn't provide (unknown downstream consumers, unstated invariants, unclear data flow).
     - The finding is a **spec-vs-implementation mismatch** — the code doesn't match the PR body's acceptance criteria. Resolution direction (change code vs. update spec) is always an author decision.

   **Language sniff test** — if the finding's `Problem` field leans on *"missed"*, *"should be"*, *"consider"*, *"appears to"*, *"seems like"*, *"probably meant"*, *"could be clearer"*, *"doesn't match"*, it is not tier `fix`. Tier `fix` reads like *"will crash"*, *"will fail"*, *"will return wrong value"*, *"is vulnerable to"*, *"asserts the wrong value"*, *"patches an unused symbol"*.

   **When in doubt, downgrade** (`fix` → `propose`, `propose` → `escalate`). The Orchestrator will never upgrade a tier; humans can.

3. For each problem found, write a structured finding:
   ```
   ### [Tier: fix|propose|escalate] [Severity: critical|major|minor] <short title>
   **ID**: F-<number>
   **File**: path/to/file.ts:line
   **Problem**: What is wrong and why it matters
   **Tier rationale**: Which tier rule placed this here (e.g. "unique resolution + local" → fix; "schema shape change" → escalate)
   **Suggested fix / proposed diff / issue draft**: (see per-tier requirements below)
   **Decision required**: [yes/no] If yes, describe the tradeoff
   **Parallelizable**: [yes/no] Can this be fixed independently of other findings? (only meaningful for tier `fix`)
   **Conflicts with**: [list of finding IDs that touch the same lines/functions, or "none"]
   ```

   Per-tier content requirements for the middle field:
   - `fix`: concrete one- or two-line recommendation describing the exact change.
   - `propose`: a fenced ```diff``` block with the proposed change, plus a one-line rationale.
   - `escalate`: a short issue draft with sub-fields `Problem`, `Constraints this PR already commits to`, `Open design questions`.

   Before writing any finding: if the flagged behavior is covered by a documented intent signal (step 1), set **Decision required**: yes, tier must be `propose` or `escalate` (never `fix`), and state *which signal* it conflicts with. Do not treat undocumented-ness as evidence of a bug — only flag absence of documentation as a finding if documentation is explicitly required by the repo's conventions.

4. Categories to check: bugs, logic errors, security issues, missing error handling, missing tests, naming/style, off-topic scope, breaking changes.

5. Pattern consistency: for any new code that parallels an existing function, endpoint, or migration, identify the closest analogue and confirm the new code replicates its correctness properties — guards, operation ordering, conditional field population, idempotency. Unexplained divergence from an established pattern is a finding. Tier it `propose` by default; only tier it `fix` if the divergence will cause a concrete runtime bug (not just stylistic inconsistency).

6. Test coverage validity: for new or modified tests, confirm (a) any patched/stubbed symbols are actually imported by the module under test, and (b) behavioral invariants ("X must NOT happen") have explicit negative assertions. A patch on an unused symbol is a tier `fix` finding (unique resolution — remove or correct the patch). A missing negative assertion for an invariant is tier `propose` if the assertion is a small addition, tier `escalate` if it would require building new test scaffolding.

7. Output `.agent-work/REVIEW_FINDINGS.md` with all findings organized **first by tier** (`fix` → `propose` → `escalate`), then by severity within each tier.

### Agent 2 — Orchestrator (inherits session model — should be Opus)

**Role**: Plan and manage the fix execution. Does NOT write code directly — only delegates to Fixer agents and commits results.

**Instructions**:

#### Step 1: Partition findings into fix groups

Read `.agent-work/REVIEW_FINDINGS.md`. **Only tier `fix` findings are eligible for Fixer execution.** Tier `propose` findings are surfaced as review comments with proposed diffs but never applied. Tier `escalate` findings are surfaced as follow-up issue drafts and never applied.

For the tier `fix` findings only, build a dependency graph:
- Findings are **independent** if they touch different files, or touch the same file but non-overlapping, non-interdependent sections, AND neither finding's fix could invalidate the other.
- Findings are **dependent** if: they touch the same function/class, one fix changes the signature/interface that another fix relies on, or the logical correctness of one fix depends on the state after another.

Produce a `.agent-work/FIX_PLAN.md`:
```
## Fix Plan

### Parallel Batch 1 (run simultaneously)
- F-1: <title> — <file(s)>
- F-4: <title> — <file(s)>
- F-7: <title> — <file(s)>

### Serial Batch 2 (depends on Batch 1)
- F-2: <title> — reason: depends on F-1 (same interface)

### Serial Batch 3
- F-5: <title> — reason: architectural decision, needs F-2 result first

### Proposed (not applied — surfaced as review comments)
- F-3: <title> — tier propose, pattern divergence
- F-6: <title> — tier propose, clarity refactor

### Escalated (not applied — surfaced as follow-up issue drafts)
- F-8: <title> — tier escalate, spec mismatch (change-code vs. update-spec decision)
- F-9: <title> — tier escalate, would introduce new module
```

Rules for grouping:
- **Default to serial** unless there are 5 or more actionable tier `fix` findings in this cycle. Below that threshold the overhead of coordination outweighs the benefit.
- When parallelizing: only findings that are provably independent (different files, non-overlapping sections, no shared interfaces) go into the same parallel batch. When in doubt, keep serial.
- If a tier `fix` finding requires a human decision, promote it to tier `propose` — do not run it as a Fixer step. A finding that needs a decision is definitionally not tier `fix`.
- Critical findings always run before minor ones within the same dependency chain.

#### Step 1a: Surface tier `propose` and tier `escalate` findings

Before running any Fixer, post the non-`fix` findings to the PR as a single review comment so the author sees them alongside the auto-applied changes:

```bash
{
  echo "<!-- review-fix-proposals -->"
  echo "## Proposed changes (not auto-applied) and escalations"
  echo
  echo "These findings were identified by the Reviewer but fall outside the auto-fix scope. The fix loop will not apply them. Please review and decide."
  echo
  echo "### Proposed changes — diffs for your consideration"
  # For each tier `propose` finding in REVIEW_FINDINGS.md, emit its title,
  # file, rationale, and the proposed diff block.
  echo
  echo "### Escalated — candidates for follow-up issues"
  # For each tier `escalate` finding, emit its title, why-escalated reason,
  # and the issue draft (Problem / Constraints / Open design questions).
  echo
  echo "<!-- review-fix-proposals-end -->"
} > .agent-work/REVIEW_PROPOSALS.md

gh pr comment <pr-number> --body "$(cat .agent-work/REVIEW_PROPOSALS.md)"
```

Post this comment once per cycle only if that cycle produced new tier `propose` or `escalate` findings not already in an earlier cycle's proposals comment. De-dupe by finding title + file.

#### Step 2: Execute batches

For each batch in order:
- **Parallel batch**: Spawn one Fixer agent per finding simultaneously. Wait for all to complete before proceeding.
- **Serial batch**: Spawn one Fixer agent, wait for completion, then proceed.

After each batch completes:
- Verify no fix in the batch broke another (re-read touched files, run tests if detectable).
- For every Critical or Major finding, confirm its `.agent-work/FIX_RESULT_*.md` contains an `## Impact Trace` section. If missing, return that finding to the Fixer queue before committing.
- **Fixture-edit check**: if any fix in the batch touches both production code *and* a test fixture, `conftest.py`, or test-setup function (autouse fixture, `setUp`, `@pytest.fixture`), require a `## Fixture Change Justification` block in the FIX_RESULT file before committing. The justification must state: (a) which behavior contract changed, and (b) whether a new test was added to pin the new behavior. If neither condition is met, return the finding to the Fixer with instructions to either revert the production change or add a dedicated test for the new behavior — do not commit a fixture patch alone.
- If a conflict is found, resolve it before proceeding to the next batch.

#### Step 3: Commit after each completed batch

After verifying a batch, commit the changes to the PR branch:

```bash
git add <only the files changed by this batch>
git commit -m "fix(<scope>): <summary of batch findings addressed>

Findings addressed: F-X, F-Y, F-Z
Auto-fixed by review-fix loop.

Decisions made:
- <decision title>: chose <option> — <reason>"
```

Rules:
- Commit only files changed in that batch — never `git add .` or `git add -A`
- One commit per batch (not per finding) to keep history readable
- Never merge. Never push to main/master. Only commit to the PR branch.
- If tests fail after a batch, do NOT commit — note the failure and continue to next batch, flagging this batch as needing manual review.

#### Step 4: Final push

After all batches are committed locally, push the branch:
```bash
git push origin <branch>
```

---

### Agent 4 — Intent Validator (`model: "claude-opus-4-6"`, runs once, after Final Review)

**Role**: Senior engineer/architect cross-check. Read-only. Do NOT make any changes to files.

**Purpose**: Verify that the automated review-fix cycle did not accidentally revert, weaken, or contradict the *original intent* of the PR — the problem the author set out to solve. Reviewers optimise for code quality signals (style, ordering, patterns); this agent optimises for functional correctness of the original fix.

**Context bundle (already in your prompt)**:

The intent bundle below contains:
- The **pre-loop HEAD SHA** (captured before any Fixer committed)
- The **PR metadata** (title, body) — the stated intent
- The **fix-loop commits** — what the automated cycles added
- The **fix-loop diff** (`PRE_LOOP..HEAD`) — exactly what the fixers changed, with `-`/`+` lines showing pre- and post-loop state for every touched line
- Repo + global `CLAUDE.md`, codebase index excerpt

The `-`/`+` lines in the fix-loop diff are your primary evidence. For surrounding context (callers, invariants, lines not in the diff), use `Read`/`Grep` freely.

If the bundle is missing or the pre-loop SHA is absent, the session was interrupted — do not proceed; report the issue to the user.

When spawning, the skill inlines `$(cat $GIT_ROOT/.agent-work/INTENT_BUNDLE.md)` into the `<BUNDLE>` slot below:

```
<BUNDLE>
```

**Instructions**:

1. Re-read the PR metadata in the bundle to extract the **stated intent**: what bug was being fixed, what invariant was being established, or what feature was being added.

2. For every file touched by both the *original* diff and the *automated fix* commits, compare:
   - What the original author changed (and *why*, inferred from the PR description).
   - What the automated fixes changed in that same file.
   - Whether the net result still preserves the original author's intent.

3. Classic failure patterns to check explicitly:
   - **Ordering reversals**: A fix that reorders statements to satisfy a style/lint rule (e.g. imports-before-side-effects) that inadvertently undoes an order-dependent correctness fix (e.g. `load_dotenv()` must run before any import that reads env vars).
   - **Guard removal**: A defensive check added by the author was judged "unnecessary" by a reviewer and removed.
   - **Guard addition**: A guard, validation gate, enforcement constraint, or error promotion added by a fixer that was not present in the original code and was not specified in the PR description or linked issue. Pay particular attention to fixture or test-setup changes that accompanied the production change — these are often the masking signal that a behavior contract was silently altered.
   - **Logic inversion**: A condition was refactored for clarity but its polarity was silently flipped.
   - **Dead code**: The original fix's code path is now unreachable due to a structural change made elsewhere by a fixer.
   - **Config/env neutralisation**: A value set by the original fix (env var, flag, constant) was overwritten or defaulted away by another change.
   - **Tier overreach**: A change committed under tier `fix` that, by its footprint, should have been tier `propose` or `escalate` — e.g. it introduced a new module, expanded a public data shape, added new test surface for newly-introduced behavior, or exceeded ~20% of the pre-loop PR's own diff size. Flag as high risk: the Reviewer/Fixer smuggled design work through the auto-apply path without author sign-off.

4. For each concern found, write a structured finding:
   ```
   ### [INTENT-RISK: high|medium|low] <short title>
   **ID**: IV-<number>
   **File**: path/to/file:line
   **Original intent**: What the PR author was trying to achieve here
   **Pre-loop state**: What the code looked like before automated fixes (quote the relevant lines)
   **Post-loop state**: What the code looks like now (quote the relevant lines)
   **Risk**: Why this change may undermine the original fix
   **Recommended action**: Revert specific automated change | Manual review needed | Acceptable tradeoff
   ```

5. If no concerns are found, output: `No intent risks detected — all automated fixes are consistent with the original PR intent.`

6. Output findings to `.agent-work/INTENT_VALIDATION.md`.

---

### Agent 3+ — Fixer (`model: "claude-sonnet-4-6"`, one instance per finding)

**Role**: Apply exactly one tier `fix` finding. Do NOT review. Do NOT fix other things noticed along the way.

**Instructions**:
1. Receive a single finding (ID, tier, file, problem, suggested fix).
2. **Tier gate**: if the finding's tier is anything other than `fix`, stop immediately. Write `Status: refused — tier <X>, not auto-fixable` to `.agent-work/FIX_RESULT_<finding-id>.md` and exit without modifying any file. The Orchestrator is responsible for routing non-`fix` findings to the proposals comment; you never apply them.
3. **Scope gate**: before editing, ask yourself *"would applying this fix introduce a new module, a new public type, a new schema field, or more than ~20% of the PR's own diff size in additional lines?"* If yes, stop and write `Status: refused — scope too large, should have been tier escalate`. Do not apply.
4. **Tightening override**: if the fix would add any of the following, treat it as **decision required** regardless of the finding's `Decision required` field and refuse to silently apply it — write `Status: refused — requires decision, should have been tier propose` and exit:
   - A guard, validation gate, enforcement constraint, or error promotion (e.g. from `isError` to a JSON-RPC error code) that was absent from the original code.
   - **Shape expansion** of a public data structure: adding fields to a returned dict/object, converting a flat mapping to a nested one, widening an API payload, changing an artifact's on-disk schema.
   - A new abstraction layer (class, protocol, interface, base class, decorator) introduced to satisfy the fix.
   - A change to a persisted format (config key, file layout, database schema, migration).
5. If no decision required and none of the refusal gates trip: apply the fix directly.
6. If decision required (and the finding legitimately belongs in tier `fix` — a narrow case, e.g. two equivalent spellings of the same bug-fix): choose the option that best preserves the closest-preceding documented intent (PR body, linked issue, docstrings). If documented intent is absent or ambiguous, default to the loosening variant and record why. Document the decision:
   ```
   ### Decision: <finding ID> — <title>
   **Options considered**:
   - Option A: <description> — <tradeoff>
   - Option B: <description> — <tradeoff>
   **Chose**: Option A
   **Reason**: <brief rationale>
   **Documented intent consulted**: <source — PR body / linked issue / docstring / none>
   ```
7. After applying, re-read the surrounding code to confirm no new issues introduced.
8. Impact trace (required for Critical and Major findings): list (a) every caller of the changed function and whether the fix invalidates any assumption it holds, and (b) any callees added or removed and whether their side-effects are still correctly handled. Record this in `.agent-work/FIX_RESULT_<finding-id>.md` under `## Impact Trace`.
9. Output a brief `.agent-work/FIX_RESULT_<finding-id>.md`:
   - Status: fixed | skipped | blocked | refused
   - Files changed: list
   - Decision made (if any)
   - Impact Trace (step 8)
   - Notes

---

## Coordination Flow

When spawning the Reviewer at any of the three spawn sites below (Initial Review, per-cycle Reviewer in the fix loop, Final Review):
- Pass `model: $REVIEWER_MODEL` in the Agent tool call.
- Inline the review bundle into the Reviewer's prompt by substituting `$(cat $GIT_ROOT/.agent-work/REVIEW_BUNDLE.md)` into the `<BUNDLE>` slot of the Reviewer agent spec.

The bundle is assembled once in Setup and is reused across all Reviewer spawns in this invocation.

### Initial Review (if no existing review)

If `NEEDS_INITIAL_REVIEW = true`, run the Reviewer agent now (before any fix cycle) and post its findings to GitHub as a PR review comment:

```bash
gh pr review <pr-number> --comment --body "$(cat .agent-work/REVIEW_FINDINGS_0.md)"
```

- Save findings to `.agent-work/REVIEW_FINDINGS_0.md` (cycle 0), organized by tier (`fix` → `propose` → `escalate`).
- This is read-only — do NOT fix anything yet.
- The review comment must make the tier clear at the top: something like "X fix-tier findings will be auto-applied in subsequent cycles; Y proposals and Z escalations are surfaced for author decision and will NOT be auto-applied."
- Then proceed to the fix loop starting at `CURRENT_CYCLE = 1`. The cycle-1 Reviewer still runs as normal (it may find fewer issues after the initial review is posted, which is fine).

If `NEEDS_INITIAL_REVIEW = false`, skip this step and start the loop directly.

---

The overall loop runs `MAX_CYCLES` fix cycles, followed by one final review:

```
CURRENT_CYCLE = 1

┌─── Repeat while CURRENT_CYCLE ≤ MAX_CYCLES ───────────────────────┐
│                                                                     │
│   Reviewer (cycle N) → .agent-work/REVIEW_FINDINGS_<N>.md                      │
│        ↓                                                            │
│   Orchestrator posts tier `propose` + `escalate` findings as PR comment │
│        ↓                                                            │
│   If no tier `fix` findings of severity critical or major → exit loop early │
│        ↓                                                            │
│   Orchestrator reads findings, builds .agent-work/FIX_PLAN_<N>.md              │
│        ↓                                                            │
│   ┌── Parallel Batch ──┐     ← spawn N Fixers simultaneously       │
│   Fixer-1  Fixer-2  Fixer-3                                        │
│   └────────────────────┘                                            │
│        ↓ all complete                                               │
│   Orchestrator verifies + runs tests                                │
│        ↓ pass                                                       │
│   Orchestrator commits batch to PR branch                           │
│        ↓                                                            │
│   Serial Fixer (dependent finding)                                  │
│        ↓                                                            │
│   Orchestrator verifies + runs tests                                │
│        ↓ pass                                                       │
│   Orchestrator commits batch → push branch                         │
│        ↓                                                            │
│   CURRENT_CYCLE += 1                                                │
└─────────────────────────────────────────────────────────────────────┘

Final Review (always runs, no fixes):
   Reviewer → .agent-work/REVIEW_FINDINGS_FINAL.md
        ↓
Intent Validation (always runs, no fixes):
   Intent Validator → .agent-work/INTENT_VALIDATION.md
        ↓
   Human Review Summary presented
```

**Early exit**: If the Reviewer finds zero critical or major **tier `fix`** findings at the start of any cycle, skip that cycle's fix phase and jump straight to the Final Review. Tier `propose` and `escalate` findings never trigger fix cycles — they are surfaced as PR comments and carried into the summary regardless of count. Note in the summary that the loop exited early at cycle N.

**Post-rebase validation**: If the branch was rebased since the last review cycle, run the full test suite and diff the pre/post-rebase state of changed files before the Reviewer starts. Any test regression or missing logic is treated as a Critical finding and assigned to a Fixer before other findings in that cycle.

**Cycle limit reached**: If `CURRENT_CYCLE > MAX_CYCLES`, stop fix cycles and proceed to Final Review regardless of remaining findings. Any unresolved findings from the last cycle's review are carried into the Outstanding Issues section of the summary.

### Assemble intent bundle

Before spawning the Intent Validator, write `.agent-work/INTENT_BUNDLE.md`:

```bash
PR_NUM=<pr-number>
BUNDLE="$GIT_ROOT/.agent-work/INTENT_BUNDLE.md"
PRE_LOOP="$(cat "$GIT_ROOT/.agent-work/PRE_LOOP_HEAD.sha")"

# Verify the pre-loop SHA is still reachable. A mid-loop rebase rewrites
# commits and orphans the saved SHA, making the fixer diff untrustworthy.
if ! git -C "$GIT_ROOT" cat-file -e "$PRE_LOOP^{commit}" 2>/dev/null; then
  echo "ERROR: pre-loop HEAD $PRE_LOOP is no longer reachable — the branch was rebased during the review cycle."
  echo "The fix-loop diff cannot be reconstructed reliably. Stop the review cycle and re-run /pr-review-cycle from scratch on the rebased branch."
  exit 1
fi

{
  echo "# Intent validation bundle for PR #$PR_NUM"
  echo
  echo "- Pre-loop HEAD SHA: \`$PRE_LOOP\`"
  echo
  echo '## PR metadata'
  gh pr view "$PR_NUM" \
    --json number,title,body,baseRefName,headRefName,additions,deletions \
    --jq '"- Title: " + .title + "\n- Base: " + .baseRefName
          + "\n- Head: " + .headRefName
          + "\n- +" + (.additions|tostring) + " / -" + (.deletions|tostring)
          + "\n\n### Body\n" + .body'
  echo
  echo '## Fix-loop commits'
  git -C "$GIT_ROOT" log --oneline "$PRE_LOOP..HEAD"
  echo
  echo '## Fix-loop diff (automated changes only)'
  echo '```diff'
  git -C "$GIT_ROOT" diff "$PRE_LOOP..HEAD"
  echo '```'
  echo
  echo '## Repo context'
  [ -f "$GIT_ROOT/CLAUDE.md" ]      && { echo '### $GIT_ROOT/CLAUDE.md'; cat "$GIT_ROOT/CLAUDE.md"; }
  [ -f "$HOME/.claude/CLAUDE.md" ]  && { echo '### ~/.claude/CLAUDE.md'; cat "$HOME/.claude/CLAUDE.md"; }
  INDEX="$GIT_ROOT/docs/agent_index.md"
  [ -f "$INDEX" ]                    && { echo '### docs/agent_index.md (first 200 lines)'; head -n 200 "$INDEX"; }
} > "$BUNDLE"
```

When spawning the Intent Validator, inline the intent bundle into its prompt by substituting `$(cat $GIT_ROOT/.agent-work/INTENT_BUNDLE.md)` into the `<BUNDLE>` slot of the Intent Validator agent spec.

---

## Final Commit & Push

After the Final Review and Intent Validation complete, commit any remaining changes
produced during the review-fix process (artifact files, residual edits, etc.) and push:

```bash
# Add only tracked (source) file changes — artifact files in .agent-work/ are
# gitignored via .git/info/exclude and are intentionally excluded.
git -C "$GIT_ROOT" add -u
git -C "$GIT_ROOT" diff --cached --quiet || git -C "$GIT_ROOT" commit -m "chore: review-fix final adjustments

Auto-generated by review-fix loop."
git -C "$GIT_ROOT" push origin <branch>
```

Rules:
- Only commit if there are staged changes (`git diff --cached --quiet` exits non-zero).
- Use `git add -u` (tracked files only), never `git add -A` — artifact files live in
  `.agent-work/` and must not be committed.
- This ensures nothing is left uncommitted/unpushed before handing off to `/pr-finalize`.
- If the push fails, report the error to the user and do NOT proceed to `/pr-finalize`.

---

## Human Review Summary

After the final commit and push, present in the conversation:

```
## PR Review-Fix Complete: <PR title> (#<number>)
Branch: <branch> — <N> commits added
Cycles run: <X> of <MAX_CYCLES> [+ final review] | or: exited early at cycle <N> (no critical/major findings)
Reviewer model: <$REVIEWER_MODEL><append " (default)" if REVIEWER_MODEL == claude-opus-4-7>

### Per-Cycle Summary
#### Cycle 1
- Findings: <count> critical, <count> major, <count> minor
- Fixed: <count> | Skipped: <count>
- Commits: <hash> <message>

#### Cycle 2
...

#### Final Review
- Remaining findings: <count> critical, <count> major, <count> minor
- Clean: [yes/no]

### All Fixes Applied (<total count>)
- [critical] F-1-1: <title> — <one-line summary> (cycle 1, commit abc1234)
- [major]    F-1-4: <title> — <one-line summary> (cycle 1, commit abc1234)
- [minor]    F-2-1: <title> — <one-line summary> (cycle 2, commit def5678)

### Decisions Made — Please Review
- **F-1-2: <title>**
  - Options: A) ... B) ...
  - Chose: A — <reason>
  - [CONFIRM / OVERRIDE?]

### Proposed Changes (not auto-applied) — <count>
- F-1-3: <title> — <why tier propose>; see PR comment for diff
- F-2-2: <title> — <why tier propose>

### Escalated (follow-up issue drafts) — <count>
- F-1-8: <title> — <why tier escalate>; see PR comment for issue draft
- F-2-4: <title> — <why tier escalate>

### Skipped / Off-topic (<count>)
- F-1-3: <title> — <reason>

### Test Results
- Cycle 1: <pass/fail per batch>
- Cycle 2: <pass/fail per batch>

### Failed Batches (not committed — needs manual attention)
<any batch where tests failed>

### Outstanding Issues (from Final Review)
Findings still present after all cycles: requires human context, architectural decision, or hit cycle limit.

### Intent Validation
- Status: clean | <N> risk(s) found
- [high] IV-1: <title> — <one-line summary of risk>
- [medium] IV-2: <title> — <one-line summary of risk>
(List all findings from .agent-work/INTENT_VALIDATION.md, or "No intent risks detected." if clean.)
```

Finding IDs use the format `F-<cycle>-<number>` (e.g. `F-1-3` = cycle 1, finding 3).

---

## Post Final Summary to PR

After presenting the Human Review Summary in the conversation, post a summarized version
to the PR as a comment. This comment serves as the authoritative record of the review-fix
run and is what `/pr-finalize` reads during its pre-flight — it does not rely on local artifact
files being present.

Compose the summary from `.agent-work/REVIEW_FINDINGS_FINAL.md` and `.agent-work/INTENT_VALIDATION.md`:

```bash
gh pr comment <pr-number> --body "$(cat <<'EOF'
<!-- review-fix-summary -->
## Automated Review-Fix Summary

**Cycles run**: <X> of <MAX_CYCLES> [exited early at cycle N | completed all cycles]
**Commits added**: <N>
**Reviewer model**: <$REVIEWER_MODEL><append " (default)" if REVIEWER_MODEL == claude-opus-4-7>

### Final review state
- Critical tier `fix` findings remaining: <count>
- Major tier `fix` findings remaining: <count>
- Minor tier `fix` findings remaining: <count>
- Tier `propose` findings surfaced: <count> (see proposals comment)
- Tier `escalate` findings surfaced: <count> (see proposals comment)
- Overall: <CLEAN — no critical/major tier `fix` remaining | FIX-TIER FINDINGS REMAIN — see below>

### Tier `fix` findings applied (<total fixed count>)
| ID | Severity | Title | Status |
|---|---|---|---|
| F-1-1 | critical | <title> | fixed (cycle 1) |
| F-1-4 | major | <title> | fixed (cycle 1) |
| F-2-1 | minor | <title> | fixed (cycle 2) |
| F-1-3 | minor | <title> | refused — tier mismatch |

### Tier `propose` findings (not auto-applied — author decides)
<For each tier `propose` finding across all cycles, list ID, severity, title, and a link/reference
to the proposed-changes PR comment. If none: "None.">

### Tier `escalate` findings (candidates for follow-up issues)
<For each tier `escalate` finding across all cycles, list ID, title, and the one-line
"why escalated" reason. If none: "None.">

### Outstanding tier `fix` findings (not applied)
<List any critical/major/minor tier `fix` findings still present in .agent-work/REVIEW_FINDINGS_FINAL.md.
If none: "None — all tier `fix` findings resolved.">

### Decisions made during fixes
<For each decision recorded in .agent-work/FIX_RESULT_*.md — list the finding ID, the options
considered, and the choice made. If none: omit this section.>

### Intent validation
<Paste the full content of .agent-work/INTENT_VALIDATION.md, or "No intent risks detected." if clean.>

---
<!-- review-fix-summary-end -->
EOF
)"
```

Rules:
- The `<!-- review-fix-summary -->` and `<!-- review-fix-summary-end -->` HTML comment tags are required — `/pr-finalize` uses them to locate this comment via `gh pr view`.
- Post this comment even if the final review is clean — `/pr-finalize` needs the sentinel to confirm `/pr-review-cycle` ran.
- Do not truncate the intent validation section — paste it in full.
- If `.agent-work/INTENT_VALIDATION.md` does not exist, write "Intent validation: not run."

---

---

## Constraints (all agents)

- Follow `~/.claude/guides/pr-guide.md` for all PR interactions.
- Never squash unrelated changes into fixes.
- Prefer minimal, targeted fixes — do not refactor surrounding code unless it is the direct cause of a finding.
- **Respect the three-tier split**: only tier `fix` findings are auto-applied. Tier `propose` findings are surfaced as PR comments with proposed diffs; tier `escalate` findings are surfaced as issue drafts. Never upgrade a tier (`propose` → `fix`) to work around the auto-apply gate; downgrade freely when in doubt.
- Never merge. Never force-push.
- If `gh` is unavailable, stop and tell the user to install the GitHub CLI.
- If the working tree has uncommitted changes before starting, stop and warn the user — do not mix pre-existing changes with review fixes.
- When handing off to a human (blockers, errors, confirmation prompts), always include the PR URL so the user can navigate to it directly.
