# E2E QA

Orchestrator only. Runs Playwright-first automated QA on a feature PR, logs residual human-QA debt as a GitHub issue, and gates merge on risk tier.

**This command never reads source files, never runs Playwright, and never writes code.** It sequences seven subagents (QA Reviewer → QA Splitter → Designer → Implementer → Runner ↔ Fixer → Reporter) with fresh context windows, then records debt.

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
4. At least one test file uses Playwright (JS or Python). Verify:
   ```bash
   grep -rl "playwright" . \
     --include="*.spec.ts" --include="*.spec.js" \
     --include="*.e2e.ts" --include="*.e2e.js" \
     --include="*.test.ts" --include="*.test.js" \
     --include="*.py" \
     --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ \
     2>/dev/null | head -1
   ```
   If no matches, stop and tell the user this repo has no Playwright tests.

---

## Step 0a — QA Reviewer (Opus 4.6, read-only)

Spawn an Agent subagent (`model: "claude-opus-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Act as an experienced human QA engineer reviewing this PR for the first time. Your job is to produce a comprehensive checklist of everything a thorough human QA pass would need to verify — functional, visual, experiential, and edge-case. Do not think about automation yet; think only about what a careful human would check.
>
> **Inputs to gather:**
> - `gh pr diff <pr>` — full diff
> - PR description and linked issue (`gh issue view <n>`)
> - Any existing QA notes or acceptance criteria on the issue
>
> **For each area touched by the PR**, ask yourself: what could go wrong that a user would notice? Think across:
> - Happy-path user flows (primary, alternate)
> - Error states and edge inputs (empty, max, invalid)
> - UI appearance and layout (spacing, truncation, responsiveness)
> - Cross-browser / cross-device behavior
> - Accessibility (keyboard nav, focus order, screen reader labels)
> - Performance (slow network, large data sets)
> - Data persistence and state consistency
> - Security-relevant interactions (auth gates, permission checks)
> - Copy and user-facing strings
> - Integration points (does this feature interact correctly with adjacent features?)
>
> **Output:** Write `.claude-work/E2E_<feature>_QA_CHECKLIST.md`:
>
> ```markdown
> # QA Checklist: <feature> — PR #<n>
>
> ## <Area 1: e.g. "Form submission flow">
> - [ ] <specific thing to check>
> - [ ] <specific thing to check>
>
> ## <Area 2: e.g. "Error handling">
> - [ ] ...
> ```
>
> Be specific and exhaustive. "Check that it works" is not a checklist item. "Verify that submitting with an empty email field shows the inline validation message and does not call the API" is a checklist item.
>
> Return:
>
> ```
> HANDOFF
> CHECKLIST_PATH=<absolute path>
> PR_NUMBER=<int>
> BRANCH=<branch>
> REPO=<owner/repo>
> CHECKLIST_ITEM_COUNT=<int>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`.

---

## Step 0b — QA Splitter (Opus 4.6, read-only)

Spawn an Agent subagent (`model: "claude-opus-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Split the QA checklist at `CHECKLIST_PATH` into two buckets: items that can be fully verified by automated Playwright tests, and items that genuinely require a human. Apply strict criteria — do not put items in the automation bucket just because they *could* be scripted; only items where automation is *reliable and sufficient*.
>
> **Automation bucket — an item belongs here if ALL of:**
> - It has deterministic, observable DOM outcomes (element visible, text matches, API called)
> - It does not require visual/aesthetic judgment ("looks right", "feels smooth", "spacing is off")
> - Cross-browser DOM correctness (e.g. "button is focusable on WebKit") belongs here — Playwright runs WebKit and Firefox headlessly; only *visual judgment* on those browsers is human-only
> - It does not require physical device or assistive technology (screen reader, keyboard-only with human judgment)
> - It does not require reading copy for tone, clarity, or correctness
>
> **Human-only bucket — an item belongs here if ANY of:**
> - Requires aesthetic or UX judgment
> - Requires cross-browser *visual* judgment (Playwright can run WebKit/Firefox headlessly and verify DOM — human is only needed when the question is "does it look right on Safari", not "does it render")
> - Requires physical device testing (mobile Safari on iOS, real touch interactions)
> - Requires assistive technology or keyboard-only flow with human judgment
> - Requires performance perception on real hardware/network
> - Requires copy/content review
> - Automation would only assert the current behavior, not whether the behavior is *correct from a user perspective*
>
> **Output:** Write `.claude-work/E2E_<feature>_QA_SPLIT.md`:
>
> ```markdown
> # QA Split: <feature> — PR #<n>
>
> ## Auto-testable (Playwright)
> - [ ] <checklist item> — *why automatable: <one-line reason>*
>
> ## Human-only (QA debt)
> - [ ] <checklist item> — *why human: <one-line reason>*
> ```
>
> Return:
>
> ```
> HANDOFF
> SPLIT_PATH=<absolute path>
> AUTO_COUNT=<int>
> HUMAN_COUNT=<int>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`.

The `Human-only` section of `SPLIT_PATH` is the **authoritative QA debt checklist** for this PR. The Reporter (Step 4) will use it verbatim instead of a generic template.

The `Auto-testable` section seeds the Designer (Step 1) alongside the diff and spec.

---

## Step 1 — Designer / Planner (read-only subagent)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Survey the repo's E2E test infrastructure, then design scenarios and a concrete placement plan for the Implementer. Read-only — do not write or modify any files except the output plan.
>
> **Before doing anything else:** read `~/.claude/guides/e2e-qa-best-practices.md`. Apply its guidance when scoping scenarios (one flow per scenario, no time-based waits, selector discipline, avoid duplicating unit coverage). The scenarios you produce go directly to the Implementer — flakiness and scope problems introduced here are harder to fix later.
>
> **Phase 1 — Recon (do this first, before designing anything):**
>
> Discover how E2E tests are structured in this repo:
> - Find all existing E2E/Playwright test files:
>   ```bash
>   grep -rl "playwright" . \
>     --include="*.spec.ts" --include="*.spec.js" \
>     --include="*.e2e.ts" --include="*.e2e.js" \
>     --include="*.test.ts" --include="*.test.js" \
>     --include="*.py" \
>     --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ \
>     2>/dev/null
>   ```
> - Read `playwright.config.ts` / `playwright.config.js` / `pytest.ini` / `pyproject.toml` to identify: test runner (Playwright JS vs pytest-playwright), `testDir`, base URL, fixture locations, project names.
> - Read 1–2 representative existing test files to extract: import style, fixture usage, page object conventions, naming patterns, helper locations.
> - Identify where new tests should be added (exact directory and file naming convention).
>
> Record your findings as **Infrastructure Notes** (runner, config path, test directory, fixture pattern, page object locations, naming convention, and the exact path where new test file(s) should be created).
>
> **Phase 2 — Scenario design:**
>
> Design scenarios from the QA split + PR diff + acceptance criteria.
>
> **Inputs to gather:**
> - `SPLIT_PATH` (auto-testable items from the QA Splitter) — primary scenario seed
> - `gh pr diff <pr>` — the actual change (not the description)
> - Acceptance criteria from the linked issue (`gh issue view <n>`)
> - Existing unit tests (to avoid duplication)
>
> **Critical:** the auto-testable items from the QA split are your primary input — design one scenario per item. Do not invent scenarios beyond the split. Diff alone is dangerous — it describes *what shipped*, not *what was asked for*. If the diff has a bug, diff-only tests assert the bug as correct. Always pair diff with spec. Disagreement between diff and spec = bug, not test material.
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
> - **Runner**: <e.g. Playwright JS (npm test) | pytest-playwright (pytest)>
> - **Config**: <path to playwright.config.ts or pytest.ini>
> - **Test directory**: <e.g. tests/e2e/>
> - **Naming convention**: <e.g. <feature>.spec.ts | test_<feature>.py>
> - **New file(s) to create**: <exact path(s) the Implementer should write>
> - **Fixtures / page objects**: <existing files to import/reuse>
> - **Route stubs / test fixtures needed**: <any new infra required>
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
> TEST_RUNNER=<playwright-js|pytest-playwright>
> NEW_TEST_FILES=<comma-separated exact paths for Implementer to create>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`. Carry `SPLIT_PATH`, `NEW_TEST_FILES`, and `TEST_RUNNER` forward into subsequent steps.

**Gate**: if `--risk` was passed, override `RISK_TIER`. If `RISK_TIER=high`, warn the user: "High-risk PR — human QA should run *before* merge. Auto-QA runs anyway but does not discharge QA obligation." Continue.

---

## Step 2 — Implementer

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Write Playwright test code from the plan at `PLAN_PATH`. Implement critical + high priority scenarios. Write tests to the exact file paths specified in `NEW_TEST_FILES` using the runner, naming convention, and fixture patterns documented in the plan's Infrastructure Notes.
>
> **Hard rules (not negotiable):**
> - Selectors: `getByRole`, `getByLabel`, `getByTestId` only. No CSS class or XPath selectors.
> - Waits: Playwright auto-waits. No `waitForTimeout`. Use `expect(...).toBeVisible()` etc.
> - Network: `page.route()` for stubs. Prefer over browser-side mocking.
> - Reuse: page objects / fixtures must come from existing files when available. No per-test helper duplication. If writing raw selectors in test bodies, refactor into a page object — brittleness compounds.
> - Visual / a11y: if plan specifies `visual-snapshot` use `toHaveScreenshot()`; if `a11y-scan` use `@axe-core/playwright`.
> - Lint/format after writing. Do NOT run tests — that is the Runner's job.
> - After linting, commit the test files to the branch: `git add <TEST_FILES> && git commit -m "test(e2e): add Playwright scenarios for <feature>"`. This ensures tests ship with the PR.
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
> TEST_COMMIT=<sha>
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

If `round == --max-rounds` and (`APP_BUGS > 0` or `TEST_BUGS > 0`), **stop execution entirely**. Do not spawn Reporter. Tell the user:

> "E2E QA halted: max rounds (3) exhausted with N outstanding bug(s). Review `.claude-work/E2E_BUG_REPORT_R<round>.md`, fix the bugs manually, then re-run `/e2e-qa`."

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

> **Role:** Post PR summary, update consolidated debt issue, check thresholds.
>
> **Inputs:** `PR_NUMBER`, `REPO`, `RISK_TIER`, `SPLIT_PATH`, all round report paths.
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
> **5b. Consolidated debt issue.** First ensure label exists:
> ```bash
> gh label create qa-debt --color FBCA04 \
>   --description "Residual human QA owed for a merged auto-QA PR" 2>/dev/null || true
> ```
>
> Check whether a consolidated debt issue already exists:
> ```bash
> gh issue list --label qa-debt --state open --json number,title,url \
>   | jq '.[] | select(.title | startswith("qa-debt: backlog"))'
> ```
>
> **If a backlog issue exists:** append this PR's debt to it via a comment:
> ```bash
> gh issue comment <existing-issue-number> --body "$(cat <<'EOF'
> ## PR #<n> — <feature> (<risk-tier> risk)
> **PR:** <link>  |  **Date:** <today>
>
> ### Auto-covered by Playwright
> <bullet list from SPLIT_PATH auto-testable section>
>
> ### Human-only checklist
> <checklist items verbatim from SPLIT_PATH human-only section, as - [ ] items>
>
> **Payment:** <High: clear BEFORE merge | Medium: before next release cut | Low: before flag flip>
> EOF
> )"
> ```
>
> **If no backlog issue exists:** create one:
> ```bash
> gh issue create --label qa-debt \
>   --title "qa-debt: backlog" \
>   --body "$(cat <<'EOF'
> Consolidated QA debt backlog. Each section below is one PR's residual human-QA checklist, appended by /e2e-qa. Close this issue when all sections are checked off.
>
> ---
>
> ## PR #<n> — <feature> (<risk-tier> risk)
> **PR:** <link>  |  **Date:** <today>
>
> ### Auto-covered by Playwright
> <bullet list from SPLIT_PATH auto-testable section>
>
> ### Human-only checklist
> <checklist items verbatim from SPLIT_PATH human-only section, as - [ ] items>
>
> **Payment:** <High: clear BEFORE merge | Medium: before next release cut | Low: before flag flip>
> EOF
> )"
> ```
>
> **5c. Threshold alarm.** Fetch the consolidated backlog issue's comments to count total unchecked items:
> ```bash
> gh issue list --label qa-debt --state open --json number,createdAt,title
> ```
> Count comments on the backlog issue to approximate pending PR sections:
> ```bash
> gh issue view <backlog-issue-number> --json comments --jq '.comments | length'
> ```
> Alarm if unchecked PR sections ≥ 10 OR backlog issue created > 30 days ago without being closed. If alarm triggers, print THRESHOLD ALARM in the output.
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
