---
version: 2.0.0
---

# Resolve Issue

## Purpose

Orchestrator only. Sequences `/fix-issue`, secondary test branches (component, integration, E2E QA), `/pr-review-cycle`, and `/pr-finalize` as isolated subagents with fresh context windows.

**This command never reads files, never runs git commands, and never writes code.**
Its sole job is to pass structured handoff data between phases and make sequencing decisions.

Running each phase in a separate subagent prevents the context accumulation that causes poor
handoff adherence when all phases run in a single growing conversation.

---

## Args

`/resolve-issue <issue> [tier] [--worktree] [--base <branch>] [--return-only] [--no-component-tests] [--no-integration-tests] [--no-e2e]`

- `issue`, `tier`, `--worktree`, `--base`: forwarded verbatim to the fix-issue subagent.
- `--return-only`: caller-controlled flag — see Entry Conditions below.
- `--no-component-tests`: skip the component test phase regardless of assessment.
- `--no-integration-tests`: skip the integration test phase regardless of assessment.
- `--no-e2e`: skip the E2E QA phase regardless of assessment.

Strip the resolve-issue-only flags (`--return-only`, `--no-component-tests`, `--no-integration-tests`, `--no-e2e`) before forwarding args to fix-issue.

---

## Entry Conditions

### `--return-only` absent (standalone)

Default behavior. Run all phases, present a Final Summary, and report results to the user.

### `--return-only` present (called from `/resolve-epic`)

**Skip the rebase phase (Step 4).** The resolve-epic Merge & Sync Agent squash-merges the PR into the epic branch — a local rebase is not needed and would conflict with that flow.

---

## Step 1 — fix-issue phase

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the fix-issue skill with the provided arguments (excluding resolve-issue-only flags).

Append these instructions to the subagent prompt:

> After presenting the Final Summary, **stop immediately**. Do not invoke `/pr-review-cycle` or any
> other command — the orchestrator handles sequencing. Return the following block as the very
> last thing in your output:
>
> ```
> HANDOFF
> WORK_DIR=<absolute path — WORK_DIR value set during branch creation>
> BRANCH=<branch name, e.g. fix/issue-42-short-slug>
> PR_URL=<full GitHub PR URL, or empty if PR creation failed>
> PR_NUMBER=<integer, or empty if PR creation failed>
> REPO=<owner/repo>
> ISSUE_NUMBER=<integer>
> BASE=<base branch name>
> SUCCESS=<true|false>
> FAILURE_REASON=<empty if SUCCESS=true, otherwise a one-line description>
> END_HANDOFF
> ```

Wait for the subagent to complete. Parse the `HANDOFF` block from its output.

**Gate**: if `SUCCESS=false`, stop here. Report `FAILURE_REASON` to the user. Do not proceed to Step 2.

---

## Step 2 — Assessment

Spawn an **Assessment Agent** (`model: "claude-sonnet-4-6"`, read-only tools only) to independently determine which secondary test branches are warranted based on what was actually implemented.

**This agent does not trust fix-issue's self-report.** It reads the real diff and artefacts.

Append to the subagent prompt:

> **Role:** Analyse the changes on `BRANCH` in `WORK_DIR` and determine which secondary test phases should run. Read the actual implementation — do not rely on what fix-issue reported.
>
> **Inputs to gather:**
> 1. `git -C "$WORK_DIR" diff <BASE>...HEAD --stat` — which files changed and by how much
> 2. `git -C "$WORK_DIR" diff <BASE>...HEAD` — full diff
> 3. `.agent-work/ISSUE_<ISSUE_NUMBER>_PLAN.md` — the implementation plan, for acceptance criteria and module ownership table
> 4. `.agent-work/ISSUE_<ISSUE_NUMBER>_ADR.md` if present — architecture decisions that affect test boundaries
>
> **Assessment questions:**
>
> **Component tests warranted?**
> - Does the diff introduce or modify interactions at a module boundary? (A module boundary is a call from one package/module/layer to another — e.g. controller→service, service→repository, UI component→state store.)
> - Are those interactions non-trivial enough that a unit test of either side alone would not catch a wiring bug?
> - If yes → `COMPONENT_TESTS=true`
>
> **Integration tests warranted?**
> - Does the diff add or significantly change a user-visible feature slice that crosses multiple layers end-to-end (HTTP → service → storage)?
> - Would a bug in the full-stack wiring be invisible to unit and component tests?
> - If yes → `INTEGRATION_TESTS=true`
>
> **E2E QA warranted?**
> - Does the diff touch UI, routes, or any code that a browser user interacts with?
> - Probe `WORK_DIR` for Playwright test infrastructure:
>   ```bash
>   grep -rl "playwright" "$WORK_DIR" \
>     --include="*.spec.ts" --include="*.spec.js" \
>     --include="*.e2e.ts" --include="*.e2e.js" \
>     --include="*.test.ts" --include="*.test.js" \
>     --include="*.py" \
>     --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ \
>     2>/dev/null | head -1
>   ```
> - If the probe returns a match AND the diff touches UI/routes → `E2E_QA=true`
> - If no Playwright infrastructure exists → `E2E_QA=false` regardless of UI changes
>
> **Output:** Return the following block as the very last thing in your output:
>
> ```
> HANDOFF
> COMPONENT_TESTS=<true|false>
> COMPONENT_TESTS_REASON=<one sentence>
> INTEGRATION_TESTS=<true|false>
> INTEGRATION_TESTS_REASON=<one sentence>
> E2E_QA=<true|false>
> E2E_QA_REASON=<one sentence>
> END_HANDOFF
> ```

Wait for the subagent to complete. Parse the `HANDOFF` block.

Apply user overrides: if `--no-component-tests` was passed, force `COMPONENT_TESTS=false`. Same for `--no-integration-tests` and `--no-e2e`.

Log the assessment to the user:

```
## Secondary branch assessment

Component tests:    <true|false> — <COMPONENT_TESTS_REASON>
Integration tests:  <true|false> — <INTEGRATION_TESTS_REASON>
E2E QA:             <true|false> — <E2E_QA_REASON>
```

---

## Step 2a — Component tests (if `COMPONENT_TESTS=true`)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the component-test skill:

```
/component-test <BRANCH> --repo <REPO> --work-dir <WORK_DIR>
```

Wait for the subagent to complete. Parse the `HANDOFF` block.

**Gate**: if `SUCCESS=false`, stop here. Report the failure to the user. Do not proceed to Step 2b.

---

## Step 2b — Integration tests (if `INTEGRATION_TESTS=true`)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the integration-test skill:

```
/integration-test <BRANCH> --repo <REPO> --work-dir <WORK_DIR>
```

Wait for the subagent to complete. Parse the `HANDOFF` block.

**Gate**: if `SUCCESS=false`, stop here. Report the failure to the user. Do not proceed to Step 2c.

---

## Step 2c — E2E QA (if `E2E_QA=true`)

Push the current commits before invoking E2E QA:

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the e2e-qa skill:

```
/e2e-qa <PR_NUMBER>
```

Append to the subagent prompt:

> After presenting the final summary, return the following block as the very last thing in your output:
>
> ```
> HANDOFF
> VERDICT=<PASS|FAIL>
> FAILURE_REASON=<empty if PASS>
> END_HANDOFF
> ```

Wait for the subagent to complete. Parse the `HANDOFF` block.

**Gate**: if `VERDICT=FAIL`, stop here. Report to the user:

```
E2E QA failed for PR #<PR_NUMBER>. Fix the failing tests or app bugs reported by /e2e-qa,
then re-run /resolve-issue (or run /e2e-qa <PR_NUMBER> manually and then /pr-review-cycle).
PR: <PR_URL>
```

Do not proceed to Step 3 until E2E QA passes.

---

## Step 3 — pr-review-cycle phase

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the pr-review-cycle skill:

```
/pr-review-cycle <WORK_DIR> <BRANCH>
```

Append these instructions to the subagent prompt:

> After presenting the Human Review Summary and posting the PR comment with the
> `<!-- review-fix-summary -->` sentinel, **stop immediately**. Do not invoke `/pr-finalize` —
> the orchestrator handles sequencing. Return the following block as the very last thing
> in your output:
>
> ```
> HANDOFF
> SUCCESS=<true|false>
> BLOCKERS=<"none" | brief one-line description of each blocker, semicolon-separated>
> FAILURE_REASON=<empty if SUCCESS=true, otherwise a one-line description>
> END_HANDOFF
> ```
>
> Blockers that prevent /pr-finalize from running:
> - Any batch failed its tests and was not committed
> - The final push failed
> - The intent validator found high-risk findings that were not resolved

Wait for the subagent to complete. Parse the `HANDOFF` block.

**Gate**: if `SUCCESS=false` or `BLOCKERS` is not `none`, stop here. Report the blockers to
the user. Do not proceed to Step 4.

---

## Step 4 — pr-finalize phase

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the pr-finalize skill:

```
/pr-finalize <BRANCH>
```

No additional instructions needed — pr-finalize runs to its own terminal state (READY or BLOCKER)
and reports to the user directly.

Wait for the subagent to complete. Relay its terminal state to the user.

---

## Final report

Present to the user:

```
## resolve-issue complete: #<number> <title>

Phase 1 — fix-issue:          ✓ PR #<PR_NUMBER> created (<PR_URL>)
Phase 2a — component tests:   <✓ <N> tests written | — skipped (<reason>)>
Phase 2b — integration tests: <✓ <N> tests written | — skipped (<reason>)>
Phase 2c — E2E QA:            <✓ PASS | — skipped (<reason>)>
Phase 3 — pr-review-cycle:    ✓ <N> findings addressed, <N> cycles
Phase 4 — pr-finalize:        <READY ✓ | BLOCKER ✗ — see above>

Branch: <BRANCH>
PR: <PR_URL>
```

---

## Constraints

- This orchestrator never touches files, git, or GitHub directly.
- Each subagent runs in an isolated context — do not summarize or repeat the subagents' internal work beyond what is needed for the final report.
- If any phase fails, stop immediately and report to the user. Do not attempt to continue or retry automatically.
- The subagents handle all error reporting within their phases. Only the `HANDOFF` gate conditions (SUCCESS, BLOCKERS, VERDICT) determine whether to proceed.
- Never pass `--admin` or bypass branch protection at any phase.
- The Assessment Agent's decisions are final unless overridden by the user's flags. Do not second-guess them in subsequent steps.
