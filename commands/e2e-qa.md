# E2E QA

Orchestrator only. Runs Playwright-first automated QA on a feature PR, logs residual human-QA debt as a GitHub issue, and gates merge on risk tier.

**This command never reads source files, never runs Playwright, and never writes code.** It sequences five subagents (Designer → Implementer → Runner ↔ Fixer → Reporter) with fresh context windows, then records debt.

Read the guide before doing anything else:

```
~/.claude/guides/e2e-qa-guide.md
```

---

## Args

`/e2e-qa <pr-number-or-branch> [--risk high|medium|low] [--max-rounds 3]`

- `pr-number-or-branch`: required. GitHub PR number, URL, or branch name.
- `--risk`: optional override. If omitted, the Designer classifies risk from the diff + acceptance criteria.
- `--max-rounds`: optional. Default 3. Runner↔Fixer loop cap.

---

## Premise

We generate tests with a bot and ship them as part of the feature PR. Humans review *failures*, not test authorship. Human QA is reserved for the residual checklist (happy path walkthrough, cross-browser, a11y, perf, UX feel) and is tracked as debt on a GitHub issue.

This trades per-PR human QA cost for **batched, scheduled** human QA — cheaper per unit of coverage, but only if the debt is bounded and paid. See guide for the four payment triggers.

---

## Entry conditions

1. PR exists (or branch has commits not yet in a PR — create one first via `gh pr create`).
2. Unit tests pass on the branch (Runner will re-verify).
3. `gh auth status` succeeds and the repo has a `qa-debt` label (Reporter will create if missing).
4. Playwright is installed in the repo. If not, stop and tell the user to add it.

---

## Step 1 — Designer (read-only subagent)

Spawn an Agent subagent (`model: "claude-opus-4-7"`, tools: read-only). Append to its prompt:

> Follow `~/.claude/guides/e2e-qa-guide.md` **Phase 1 — Designer**. Input: PR diff (`gh pr diff <pr>`), acceptance criteria from the linked issue, and existing Playwright tests. Output: `.claude-work/E2E_<feature>_PLAN.md` with one scenario per user flow, each with a `why-not-unit` justification, a `playwright-feature` field, and a `risk-tier` classification for the PR as a whole. Stop after writing the plan. Return this block:
>
> ```
> HANDOFF
> PLAN_PATH=<absolute path>
> PR_NUMBER=<int>
> BRANCH=<branch>
> REPO=<owner/repo>
> RISK_TIER=<high|medium|low>
> SCENARIO_COUNT=<int>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`.

**Gate**: if `--risk` was passed, override `RISK_TIER`. If `RISK_TIER=high`, warn the user: "High-risk PR — human QA should run *before* merge. Auto-QA runs anyway but does not discharge QA obligation." Continue.

---

## Step 2 — Implementer

Spawn an Agent subagent (`model: "claude-opus-4-7"`). Append:

> Follow `~/.claude/guides/e2e-qa-guide.md` **Phase 2 — Implementer**. Read `PLAN_PATH` and existing Playwright test files. Hard rules from the guide: `getByRole`/`getByTestId` only, no `waitForTimeout`, page-object reuse required, `page.route()` preferred over mocking. Implement critical + high scenarios. Run linter. Do NOT run tests. Return:
>
> ```
> HANDOFF
> TEST_FILES=<comma-separated absolute paths>
> SCENARIOS_IMPLEMENTED=<int>
> END_HANDOFF
> ```

Wait for completion.

---

## Step 3 — Runner ↔ Fixer loop

For `round` in 1..`--max-rounds`:

### 3a. Runner

Spawn an Agent subagent (`model: "claude-opus-4-7"`). Append:

> Follow `~/.claude/guides/e2e-qa-guide.md` **Phase 3 — Runner**, round `<round>`. Run the tests at `TEST_FILES`. For each failure, re-run the failing test 3× in isolation to distinguish deterministic bugs from flakes. Classify each finding as `app-bug`, `test-bug`, or `flake-quarantine`. Write `.claude-work/E2E_BUG_REPORT_R<round>.md`. Attach Playwright trace paths. Return:
>
> ```
> HANDOFF
> REPORT_PATH=<absolute path>
> APP_BUGS=<int>
> TEST_BUGS=<int>
> FLAKES=<int>
> ALL_PASSED=<true|false>
> END_HANDOFF
> ```

Wait. If `ALL_PASSED=true` or (`APP_BUGS=0` and `TEST_BUGS=0`), break out of the loop.

### 3b. Fixer (skipped on the final round)

If `round == --max-rounds`, skip Fixer — the final round is report-only.

Otherwise spawn an Agent subagent. Append:

> Follow `~/.claude/guides/e2e-qa-guide.md` **Phase 4 — Fixer**. Read `REPORT_PATH`. Fix `app-bug` and `test-bug` entries only — leave `flake-quarantine` items alone. **Commit app-bug fixes and test-bug fixes as separate commits** with messages `fix(app): ...` and `fix(test): ...`. Run unit tests. Do NOT run Playwright. Return:
>
> ```
> HANDOFF
> APP_COMMITS=<sha list>
> TEST_COMMITS=<sha list>
> END_HANDOFF
> ```

Wait. Continue to round `n+1`.

---

## Step 4 — Reporter & debt ledger

Spawn an Agent subagent (`model: "claude-opus-4-7"`). Append:

> Follow `~/.claude/guides/e2e-qa-guide.md` **Phase 5 — Reporter**.
>
> 1. Aggregate all round reports into a final summary table.
> 2. Post the summary as a PR comment via `gh pr comment <PR_NUMBER>`.
> 3. Ensure the `qa-debt` label exists: `gh label create qa-debt --color FBCA04 --description "Residual human QA owed for a merged auto-QA PR" || true`.
> 4. Create a GitHub issue via `gh issue create` with:
>    - Title: `qa-debt: PR #<PR_NUMBER> — <feature-title>`
>    - Label: `qa-debt`
>    - Body: the residual checklist template from the guide, filled in with this PR's specifics, risk tier, and the PR link.
> 5. Check open `qa-debt` issues via `gh issue list --label qa-debt --state open --json number,createdAt`. If count ≥ 10 or oldest > 14 days, print a THRESHOLD ALARM in the final output.
>
> Return:
>
> ```
> HANDOFF
> VERDICT=<PASS|FAIL>
> DEBT_ISSUE=<url>
> ALARM=<none|threshold|age>
> END_HANDOFF
> ```

---

## Final summary (orchestrator)

Present to user:

```
## E2E QA Complete — PR #<n>

Verdict: <PASS|FAIL>
Risk tier: <tier>
Rounds: <n>
App bugs fixed: <n>  |  Test bugs fixed: <n>  |  Flakes quarantined: <n>

Residual QA debt: <DEBT_ISSUE>
<alarm message if any>

Next steps:
- If high-risk: run residual checklist before merge.
- If medium-risk: merge OK; checklist must clear before next release cut.
- If low-risk behind a flag: checklist must clear before flag flip to 100%.
```

If `ALARM` is set, additionally tell the user: "QA debt backlog exceeds budget. Pay down open `qa-debt` issues before running `/e2e-qa` again."
