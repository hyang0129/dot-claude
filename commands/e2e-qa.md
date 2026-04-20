# E2E QA

Orchestrator only. Runs Playwright-first automated QA on a feature PR, logs residual human-QA debt as a GitHub issue, and gates merge on risk tier.

**This command never reads source files, never runs Playwright, and never writes code.** It sequences five subagents (Designer → Implementer → Runner ↔ Fixer → Reporter) with fresh context windows, then records debt.

---

## Args

`/e2e-qa <pr-number-or-branch> [--risk high|medium|low] [--max-rounds 3]`

- `pr-number-or-branch`: required. GitHub PR number, URL, or branch name.
- `--risk`: optional override. If omitted, the Designer classifies risk from the diff + acceptance criteria.
- `--max-rounds`: optional. Default 3. Runner↔Fixer loop cap.

---

## Premise

We generate tests with a bot and ship them as part of the feature PR. Humans review *failures*, not test authorship. Human QA is reserved for the residual checklist (happy path walkthrough, cross-browser, a11y, perf, UX feel) and is tracked as debt on a GitHub issue.

This trades per-PR human QA cost for **batched, scheduled** human QA — cheaper per unit of coverage, but only if the debt is bounded and paid.

**What auto-QA captures:** regression-class bugs — frontend↔backend wiring, DOM events triggering API calls, rendering of API responses, cross-component side effects, state persistence. Realistically 60–75% of QA surface.

**What auto-QA does NOT capture:** happy-path UX feel, cross-browser quirks, animation jank, focus order / a11y, perf on slow networks, copy review, visual polish. These are tracked as residual debt on a GitHub issue.

---

## Entry conditions

1. PR exists (or branch has commits not yet in a PR — create one first via `gh pr create`).
2. Unit tests pass on the branch (Runner will re-verify).
3. `gh auth status` succeeds and the repo has a `qa-debt` label (Reporter will create if missing).
4. Playwright is installed in the repo. If not, stop and tell the user to add it.

---

## Step 1 — Designer (read-only subagent)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Design Playwright scenarios from the PR diff + acceptance criteria. Read-only — do not write or modify any files except the output plan.
>
> **Inputs to gather:**
> - `gh pr diff <pr>` — the actual change (not the description)
> - Acceptance criteria from the linked issue (`gh issue view <n>`)
> - Existing Playwright tests (patterns, fixtures, page objects)
> - Existing unit tests (to avoid duplication)
>
> **Critical:** diff alone is dangerous — it describes *what shipped*, not *what was asked for*. If the diff has a bug, diff-only tests assert the bug as correct. Always pair diff with spec. Disagreement between diff and spec = bug, not test material.
>
> **Output:** Write `.claude-work/E2E_<feature>_PLAN.md` with this structure:
>
> ```markdown
> # E2E Test Plan: <feature>
>
> ## PR Risk Tier: <high | medium | low>
> <one-line justification: high = auth/payments/data-loss/public-launch;
>  medium = user-facing feature no flag; low = behind flag, internal tool, or thin UI on backend change>
>
> ## Infrastructure Notes
> <page objects, route stubs, test fixtures needed>
>
> ## Scenarios
>
> ### S1: <name>
> - **Priority**: critical | high | medium | low
> - **Why not a unit test**: <must be justified — if unit test could cover it, cut the scenario>
> - **Playwright feature**: route-stub | real-backend | visual-snapshot | a11y-scan
> - **Setup**: <preconditions>
> - **Steps**: <numbered user actions, in terms of roles/labels not selectors>
> - **Expected**: <observable outcomes>
> ```
>
> **Rules:**
> - One scenario per distinct user flow, not per code change.
> - Every scenario must have a `why-not-unit` justification. No justification → cut it.
> - Risk tier classifies the PR as a whole, not individual scenarios.
> - Do not duplicate unit coverage — the `why-not-unit` field is the filter.
>
> Return this block exactly:
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

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Write Playwright test code from the plan at `PLAN_PATH`. Implement critical + high priority scenarios.
>
> **Hard rules (not negotiable):**
> - Selectors: `getByRole`, `getByLabel`, `getByTestId` only. No CSS class or XPath selectors.
> - Waits: Playwright auto-waits. No `waitForTimeout`. Use `expect(...).toBeVisible()` etc.
> - Network: `page.route()` for stubs. Prefer over browser-side mocking.
> - Reuse: page objects / fixtures must come from existing files when available. No per-test helper duplication. If writing raw selectors in test bodies, refactor into a page object — brittleness compounds.
> - Visual / a11y: if plan specifies `visual-snapshot` use `toHaveScreenshot()`; if `a11y-scan` use `@axe-core/playwright`.
> - Lint/format after writing. Do NOT run tests — that is the Runner's job.
> - Test-mode endpoints are a last resort. Prefer `page.route()` stubs. If a scenario genuinely needs server-side puppeting, gate it behind the project's test-mode flag and never expose in production.
>
> **Budget:** if the plan has ≥ 10 new scenarios, flag to the user before implementing — may indicate the feature is too large or the plan duplicates unit coverage.
>
> Return:
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

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Run tests, distinguish bugs from flakes, diagnose root causes. Round `<round>`.
>
> **Steps:**
> 1. Kill any running server/dev instances per project convention.
> 2. Run unit tests first — baseline must be green before running E2E.
> 3. Run Playwright tests at `TEST_FILES`, capturing traces on failure.
> 4. For each failing test, **re-run it 3× in isolation**:
>    - 3/3 fail deterministically → real bug. Read source, diagnose root cause.
>    - Intermittent → `flake-quarantine`. Do NOT report as a bug. Do NOT let Fixer touch it.
> 5. Classify real bugs as `app-bug` (production code is wrong) or `test-bug` (test assertion or setup is wrong). One root cause often cascades across many tests — report the cause once, not per symptom.
>
> **Output:** Write `.claude-work/E2E_BUG_REPORT_R<round>.md`:
>
> ```markdown
> # E2E Bug Report — Round <N>
>
> ## Results
> - Passed: N
> - Failed: N  (deterministic: N, quarantined flakes: N)
>
> ## Bugs
>
> ### BUG-R<N>-1: <title>
> - **Tests affected**: <test names>
> - **Type**: app-bug | test-bug
> - **Severity**: critical | high | medium
> - **Root cause**: <analysis from reading source>
> - **Fix**: <what changes where>
> - **Trace**: <path to trace.zip>
>
> ## Quarantined Flakes
> - <test name> — <observed failure> — reran 3×, passed N/3. Not fixed this round.
> ```
>
> Return:
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

Otherwise spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Apply fixes from `REPORT_PATH` with strict separation of concerns.
>
> **Rules:**
> - Fix `app-bug` and `test-bug` entries only. Leave `flake-quarantine` items completely alone.
> - **Separate commits required.** `fix(app): ...` commits and `fix(test): ...` commits must never be combined. This makes bad fixes revertable without losing the other category.
> - Minimal changes only. No refactoring, no "while I'm here" cleanup.
> - Do not weaken test assertions to make a test pass. If an assertion is wrong, the Runner classified it as `test-bug` with a root cause — fix the root cause.
> - Run lint + unit tests after fixing. Do NOT run Playwright — the Runner owns that.
>
> Return:
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

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Post PR summary, file debt issue, check thresholds.
>
> **5a. Post PR summary comment** via `gh pr comment <PR_NUMBER>`:
>
> ```markdown
> ## E2E QA: <PASS | FAIL>
>
> | Round | Passed | Failed | App Bugs | Test Bugs | Flakes |
> |-------|--------|--------|----------|-----------|--------|
> | R1    | N/M    | N      | N        | N         | N      |
>
> **App bugs fixed:** <list>
> **Test bugs fixed:** <list>
> **Quarantined flakes:** <list — need human triage>
> **Outstanding:** <any bugs remaining after max rounds>
>
> Residual human-QA debt tracked: <issue url>
> ```
>
> **5b. Create debt issue.** First ensure label exists:
> ```bash
> gh label create qa-debt --color FBCA04 \
>   --description "Residual human QA owed for a merged auto-QA PR" 2>/dev/null || true
> ```
>
> Then create the issue:
> ```bash
> gh issue create --label qa-debt \
>   --title "qa-debt: PR #<n> — <feature>" \
>   --body "$(cat <<'EOF'
> **PR:** #<n> — <link>
> **Merged:** <date, or "pending merge">
> **Risk tier:** <tier>
>
> ## Auto-covered
> <short bullet list of regression areas exercised by Playwright>
>
> ## Residual human-QA checklist
> - [ ] Happy-path walkthrough in dev against real backend
> - [ ] Cross-browser smoke (Safari, Firefox) for any user-visible UI changes
> - [ ] Keyboard-only navigation / a11y for new interactive elements
> - [ ] Perf on throttled network for pages that load new data
> - [ ] Copy / UX review for any new user-facing strings
> - [ ] <any scenario-specific residual items>
>
> ## Payment rules
> - High-risk: clear BEFORE merge.
> - Medium-risk: clear before next release cut.
> - Low-risk (flag-gated): clear before flag flip to 100%.
> EOF
> )"
> ```
>
> **5c. Threshold alarm.** Run:
> ```bash
> gh issue list --label qa-debt --state open --json number,createdAt
> ```
> Alarm if open count ≥ 10 OR oldest open issue > 14 days. If alarm triggers, print THRESHOLD ALARM in the output.
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
