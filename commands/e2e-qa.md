---
version: 2.0.0
---

# E2E QA

Orchestrator only. Runs Playwright-first automated QA on a feature PR or a pre-scoped GitHub issue, logs residual human-QA debt as a GitHub issue, and gates merge on risk tier.

**This command never reads source files, never runs Playwright, and never writes code.** It sequences subagents through a **spec source** (one of two, chosen by input) and a **shared core pipeline**, then records debt.

---

## Args

```
/e2e-qa <pr-number-or-branch | issue:<n> | --scenarios <path>> [--risk high|medium|low] [--max-rounds 3] [--e2e-dir <path>]
```

- `pr-number-or-branch` — numeric, URL, or branch name → **spec-from-pr** path.
- `issue:<n>` — e.g. `issue:250` → **spec-from-issue** path.
- `--scenarios <path>` — path to an existing `scenarios.json`; skips all spec-source steps (advanced/debugging escape hatch).
- `--risk` — optional override. If omitted, Spec-Enricher classifies risk from context.
- `--max-rounds` — optional. Default 3. Validator loop cap.
- `--e2e-dir <path>` — optional. Root directory to probe for Playwright tests. Defaults to `.`. Use this when invoked from a dev-container or monorepo where the E2E tests live outside the orchestrator's cwd.

**Auto-detect logic (orchestrator runs this before spawning anything):**

1. If `--scenarios <path>` is present → skip to Step 1 (Spec-Enricher), passing the path as `SCENARIOS_PATH`.
2. Else if argument starts with `issue:` → run **Step S2 (spec-from-issue)**.
3. Else (numeric, URL, branch) → run **Step S1 (spec-from-pr)**.

---

## Premise

We generate tests with a bot and ship them as part of a PR — or backfill them when a shipped feature lacks coverage. Humans review *failures*, not test authorship. Human QA is reserved for items that genuinely require judgment (UX feel, a11y with assistive tech, visual polish) and is tracked as debt on a GitHub issue.

**What auto-QA captures:** regression-class bugs — frontend↔backend wiring, DOM events triggering API calls, rendering of API responses, cross-component side effects, state persistence. Realistically 60–75% of QA surface.

**What auto-QA does NOT capture:** happy-path UX feel, cross-browser quirks, animation jank, focus order / a11y with assistive tech, perf on slow networks, copy review, visual polish. These are tracked as residual debt.

---

## Entry conditions

1. `gh auth status` succeeds and the repo has (or will have) a `qa-debt` label (Reporter creates if missing).
2. At least one test file uses Playwright (JS or Python). Probe `${E2E_DIR:-.}` (resolve from `--e2e-dir` if passed, else `.`):
   ```bash
   grep -rl "playwright" "${E2E_DIR:-.}" \
     --include="*.spec.ts" --include="*.spec.js" \
     --include="*.e2e.ts" --include="*.e2e.js" \
     --include="*.test.ts" --include="*.test.js" \
     --include="*.py" \
     --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ \
     2>/dev/null | head -1
   ```
   If no matches, stop and tell the user this repo has no Playwright tests. Carry `E2E_DIR` forward into all subagent prompts that probe the filesystem.
3. For PR inputs: PR exists (or branch has commits — create PR first via `gh pr create`). Unit tests pass on the branch.
4. For issue inputs: the issue body contains a "Scope" or "Scenarios" heading with bullet/numbered items.

---

## Spec Source steps (mutually exclusive — only one runs)

---

## Step S1 — spec-from-pr (PR input only)

Runs two sequential subagents: **QA Reviewer** then **Auto-vs-Human Splitter**. Their combined output produces `scenarios.json`.

### Step S1a — QA Reviewer (Opus 4.6, read-only)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Act as an experienced human QA engineer reviewing this PR for the first time. Produce a comprehensive checklist of everything a thorough human QA pass would need to verify — functional, visual, experiential, and edge-case. Do not think about automation yet.
>
> **Inputs to gather:**
> - `gh pr diff <pr>` — full diff
> - PR description and linked issue (`gh issue view <n>`)
> - Any existing QA notes or acceptance criteria on the issue
>
> **For each area touched by the PR**, ask: what could go wrong that a user would notice? Think across:
> - Happy-path user flows (primary, alternate)
> - Error states and edge inputs (empty, max, invalid)
> - UI appearance and layout (spacing, truncation, responsiveness)
> - Cross-browser / cross-device behavior
> - Accessibility (keyboard nav, focus order, screen reader labels)
> - Performance (slow network, large data sets)
> - Data persistence and state consistency
> - Security-relevant interactions (auth gates, permission checks)
> - Copy and user-facing strings
> - Integration points (adjacent features)
>
> **Output:** Write `.agent-work/E2E_<feature>_QA_CHECKLIST.md`:
>
> ```markdown
> # QA Checklist: <feature> — PR #<n>
>
> ## <Area 1>
> - [ ] <specific thing to check>
> ```
>
> Be specific and exhaustive. "Check that it works" is not a checklist item.
>
> Return:
>
> ```
> HANDOFF
> CHECKLIST_PATH=<absolute path>
> PR_NUMBER=<int>
> BRANCH=<branch>
> REPO=<owner/repo>
> FEATURE=<feature name>
> CHECKLIST_ITEM_COUNT=<int>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`.

### Step S1b — Auto-vs-Human Splitter (Opus 4.6, read-only)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Split the QA checklist at `CHECKLIST_PATH` into two buckets: items automatable by Playwright, and items that genuinely require a human. Apply strict criteria.
>
> **Automation bucket — item belongs here if ALL of:**
> - Deterministic, observable DOM outcomes (element visible, text matches, API called)
> - Does not require visual/aesthetic judgment
> - Cross-browser DOM correctness belongs here (Playwright runs WebKit/Firefox headlessly); only *visual judgment* is human-only
> - Does not require physical device or assistive technology
> - Does not require reading copy for tone/clarity
>
> **Human-only bucket — item belongs here if ANY of:**
> - Requires aesthetic or UX judgment
> - Requires cross-browser *visual* judgment
> - Requires physical device testing
> - Requires assistive technology or keyboard-only flow with human judgment
> - Requires performance perception on real hardware/network
> - Requires copy/content review
> - Automation would only assert current behavior, not whether behavior is *correct from a user perspective*
>
> **Output:** Write `.agent-work/E2E_<feature>_QA_SPLIT.md`:
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
> Then produce `scenarios.json` at `.agent-work/E2E_<feature>_scenarios.json` using the schema below (fill all fields except per-scenario implementation details — selectors, fixtures, exact assertions — which Spec-Enricher adds). Set `"source": "pr"`, `"source_ref": "PR #<n>"`. Derive one scenario per auto-testable item. Leave `risk_tier` as `null` if not yet determinable.
>
> **`scenarios.json` schema:**
> ```json
> {
>   "feature": "string",
>   "source": "pr",
>   "source_ref": "PR #<n>",
>   "risk_tier": "high|medium|low|null",
>   "scenarios": [
>     {
>       "id": "S1",
>       "title": "string",
>       "layer": "aiohttp|playwright|integration|static",
>       "priority": "critical|high|medium|low",
>       "behavior_under_test": "what user-visible/system behavior this asserts",
>       "preconditions": "string | null",
>       "action": "string",
>       "expected": "string",
>       "why_not_unit": "required justification"
>     }
>   ]
> }
> ```
>
> The `Human-only` section of `SPLIT_PATH` is the **authoritative QA debt checklist** for this PR. Reporter uses it verbatim.
>
> Return:
>
> ```
> HANDOFF
> SCENARIOS_PATH=<absolute path to scenarios.json>
> SPLIT_PATH=<absolute path to QA_SPLIT.md>
> AUTO_COUNT=<int>
> HUMAN_COUNT=<int>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`. Carry `SCENARIOS_PATH` and `SPLIT_PATH` into Step 1. `SPLIT_PATH` is **only used by spec-from-pr** — it feeds Reporter's debt ledger and is not produced by other sources.

---

## Step S2 — spec-from-issue (issue input only)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Parse a pre-enumerated scope section from a GitHub issue and produce `scenarios.json`. The issue author has already triaged what needs testing — your job is to faithfully translate their scope into the canonical schema, not to invent or expand it.
>
> **Inputs to gather:**
> - `gh issue view <n> --json body,title,labels,comments` — full issue
>
> **Parse rules:**
> - Find the heading that matches (case-insensitive) "Scope", "Scenarios", "Test Scenarios", or "Acceptance Criteria".
> - Extract every bullet or numbered item under that heading (stop at the next `##` heading).
> - If no such heading exists or the section has no items, **stop** and return an error: "Issue #<n> has no recognizable Scope/Scenarios section. Use spec-from-pr or add a Scope heading to the issue."
>
> **For each extracted item**, produce one scenario in `scenarios.json`:
> - `id`: sequential S1, S2, …
> - `title`: the item text, trimmed
> - `layer`: infer from context ("playwright" if UI/browser interaction, "aiohttp" if API/server endpoint, "integration" if both, "static" if config/markup check)
> - `priority`: infer from any priority signals in the item text or issue labels; default "medium"
> - `behavior_under_test`: expand the item text into a one-sentence behavior statement
> - `preconditions`: extract from item text if stated, else null
> - `action`: the action implied by the scenario
> - `expected`: the expected outcome implied by the scenario
> - `why_not_unit`: justify why this needs an E2E test (e.g. "requires DOM + API wiring to verify end-to-end")
>
> Set `"source": "issue"`, `"source_ref": "issue #<n>"`. Leave `risk_tier` as `null`.
>
> **Output:** Write `.agent-work/E2E_issue<n>_scenarios.json` per the schema above.
>
> Return:
>
> ```
> HANDOFF
> SCENARIOS_PATH=<absolute path>
> FEATURE=<issue title, slug form>
> SCENARIO_COUNT=<int>
> REPO=<owner/repo>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`. Note: `SPLIT_PATH` is **not set** for this source — Reporter will skip the debt checklist section (the issue author already triaged scope; no additional human-only debt list is produced).

> **Future sources note:** A `spec-from-prompt` source (inline scenario list passed directly on the command line) would slot in here as a Step S3 with the same `HANDOFF` contract. Not implemented yet.

---

## Core pipeline steps (always run, consume `scenarios.json`)

---

## Step 1 — Spec-Enricher (read-only subagent)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`, tools: read-only). Append to its prompt:

> **Role:** Ground each scenario in the actual repo. Read the SUT and test infrastructure, then attach concrete implementation details to every scenario. Do not write files. Do not invent scenarios.
>
> **Before doing anything else:** read `~/.claude/guides/e2e-qa-best-practices.md`. Apply its guidance on selector discipline, one flow per scenario, no time-based waits, avoiding unit-coverage duplication.
>
> **Phase 1 — Infrastructure recon:**
>
> Discover how E2E tests are structured. Probe `E2E_DIR` (passed from the orchestrator; defaults to `.`):
> - Find all existing E2E/Playwright test files:
>   ```bash
>   grep -rl "playwright" "$E2E_DIR" \
>     --include="*.spec.ts" --include="*.spec.js" \
>     --include="*.e2e.ts" --include="*.e2e.js" \
>     --include="*.test.ts" --include="*.test.js" \
>     --include="*.py" \
>     --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ \
>     2>/dev/null
>   ```
> - Read `playwright.config.ts` / `playwright.config.js` / `pytest.ini` / `pyproject.toml`: test runner, `testDir`, base URL, fixture locations, project names.
> - Read 1–2 representative existing test files: import style, fixture usage, page object conventions, naming patterns.
> - Identify exact directory and file naming convention for new tests.
>
> **Phase 2 — Scenario enrichment:**
>
> For each scenario in `SCENARIOS_PATH`:
> - Read the SUT (the file/handler/component the scenario exercises).
> - Attach:
>   - `target_file`: the SUT file path the scenario exercises
>   - `selector_strategy`: how to locate the element (`getByRole`, `getByLabel`, `getByTestId`, etc.)
>   - `fixture_or_stub`: existing fixture/page-object to reuse, or what stub is needed
>   - `preconditions` (refine from scenario or fill if null)
>   - `exact_assertion`: the Playwright assertion expression (e.g. `expect(page.getByRole('alert')).toBeVisible()`)
>   - `layer`: confirm or correct the source's inference
>
> **Risk tier:** if `risk_tier` in `scenarios.json` is null, classify the batch:
> - `high` = auth/payments/data-loss/public-launch path
> - `medium` = user-facing feature, no flag
> - `low` = behind flag, internal tool, or thin UI on backend change
>
> If `--risk` was passed by the user, use that value and note the override.
>
> **Output:** Write `.agent-work/E2E_<feature>_ENRICHED.json` — same schema as `scenarios.json` plus the enrichment fields above, plus top-level:
> ```json
> {
>   "risk_tier": "high|medium|low",
>   "infrastructure": {
>     "runner": "playwright-js|pytest-playwright",
>     "config_path": "...",
>     "test_directory": "...",
>     "naming_convention": "...",
>     "new_test_files": ["..."],
>     "fixtures_page_objects": ["..."]
>   },
>   "scenarios": [ ... ]
> }
> ```
>
> Return:
>
> ```
> HANDOFF
> ENRICHED_PATH=<absolute path>
> RISK_TIER=<high|medium|low>
> SCENARIO_COUNT=<int>
> TEST_RUNNER=<playwright-js|pytest-playwright>
> NEW_TEST_FILES=<comma-separated exact paths>
> END_HANDOFF
> ```

Wait for completion. Parse `HANDOFF`.

**Gate:** If `--risk` was passed, override `RISK_TIER`. If `RISK_TIER=high`, warn the user: "High-risk — human QA should run *before* merge. Auto-QA runs anyway but does not discharge QA obligation." Continue.

---

## Step 2 — Layer-Batch Splitter (orchestrator logic, no subagent needed)

Group scenarios from `ENRICHED_PATH` by `layer` field. Each layer becomes a batch for Implementer. Log the groupings:

```
Layer batches:
  playwright: S1, S3, S5
  aiohttp: S2, S4
  integration: S6
```

Pass the full `ENRICHED_PATH` to Implementer; Implementer is told which layers to handle in its invocation (or handle all layers if the count is small enough for one agent).

---

## Step 3 — Implementer

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Write Playwright test code from the enriched plan at `ENRICHED_PATH`. Implement critical + high priority scenarios. Write tests to the exact file paths in `infrastructure.new_test_files`, using the runner, naming convention, and fixture patterns in `infrastructure`.
>
> **Hard rules (not negotiable):**
> - Selectors: `getByRole`, `getByLabel`, `getByTestId` only. No CSS class or XPath selectors.
> - Waits: Playwright auto-waits. No `waitForTimeout`. Use `expect(...).toBeVisible()` etc.
> - Network: `page.route()` for stubs. Prefer over browser-side mocking.
> - Reuse: page objects / fixtures must come from existing files when available. No per-test helper duplication. If writing raw selectors in test bodies, refactor into a page object.
> - Visual / a11y: if scenario specifies `visual-snapshot` use `toHaveScreenshot()`; if `a11y-scan` use `@axe-core/playwright`.
> - Lint/format after writing. Do NOT run tests — Validator owns that.
> - After linting, commit: `git add <TEST_FILES> && git commit -m "test(e2e): add Playwright scenarios for <feature>"`.
> - Test-mode endpoints are a last resort. Prefer `page.route()` stubs.
>
> **Budget:** if ≥ 10 new scenarios, flag to the user before implementing.
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

## Step 4 — Validator loop

For `round` in 1..`--max-rounds`:

### 4a. Validator

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Verify that each implemented test actually *bites* — that it catches real regressions and is not a toothless green test. Round `<round>`.
>
> **For each test in `TEST_FILES`:**
>
> **Step A — baseline run:** run the test; it must pass cleanly. If it fails, classify as `test-bug` (the test itself is broken) and skip steps B/C for this test.
>
> **Step B — negative control (mutation):** apply one obviously-relevant mutation to the SUT — pick exactly ONE of:
> - Comment out the handler/function the test exercises (e.g. `# return response` on the handler's return statement)
> - Invert a boolean condition in the assertion path (e.g. `if condition:` → `if not condition:`)
>
> Re-run the test against the mutated SUT. **It must fail.** If it passes with the mutation applied, the test is toothless — record as `toothless` and kick back to Implementer.
>
> **Step C — revert:** revert the mutation immediately after step B (do not commit the mutation).
>
> **Classification per test:**
> - `pass` — baseline passes, mutation detected (test bites)
> - `test-bug` — baseline fails (broken test)
> - `toothless` — baseline passes but mutation not detected (test does not assert the right thing)
>
> **Re-run flake check:** for `test-bug` results, re-run 3× in isolation. If intermittent → `flake-quarantine` instead of `test-bug`.
>
> **Output:** Write `.agent-work/E2E_VALIDATOR_R<round>.md`:
>
> ```markdown
> # Validator Report — Round <N>
>
> ## Results
> - Pass (bites): N
> - Test-bug: N  (flakes quarantined: N)
> - Toothless: N
>
> ## Test-bugs
>
> ### BUG-R<N>-1: <test name>
> - **Type**: test-bug | app-bug
> - **Root cause**: <analysis>
> - **Fix**: <what changes where>
> - **Trace**: <path to trace.zip if available>
>
> ## Toothless tests
>
> ### TOOTHLESS-R<N>-1: <test name>
> - **Mutation applied**: <description of mutation>
> - **Observation**: test passed despite mutation — assertion does not catch the failure
> - **Suggested fix**: <what the test should assert instead>
>
> ## Quarantined Flakes
> - <test name> — <observed failure> — reran 3×, passed N/3.
>
> ## Negative-control results (for Reporter)
> | Test | Mutation applied | Detected? |
> |------|-----------------|-----------|
> | <name> | <mutation desc> | yes/no |
> ```
>
> Return:
>
> ```
> HANDOFF
> REPORT_PATH=<absolute path>
> PASS_COUNT=<int>
> TEST_BUGS=<int>
> TOOTHLESS_COUNT=<int>
> FLAKES=<int>
> ALL_PASSED=<true|false>
> END_HANDOFF
> ```

Wait. If `ALL_PASSED=true` (all tests pass baseline and all bite), break out of loop.

If `round == --max-rounds` and (`TEST_BUGS > 0` or `TOOTHLESS_COUNT > 0`), **stop execution entirely**. Do not spawn Reporter. Tell the user:

> "E2E QA halted: max rounds (`--max-rounds`) exhausted with N test-bug(s) and N toothless test(s). Review `.agent-work/E2E_VALIDATOR_R<round>.md`, fix the tests manually, then re-run `/e2e-qa`."

### 4b. Fixer (skipped on final round)

If `round == --max-rounds`, skip — the final round is report-only.

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Fix `test-bug` and `toothless` entries from `REPORT_PATH`. Do not touch `flake-quarantine` items.
>
> **Rules:**
> - `test-bug` fixes: correct the broken test assertion or setup. Use `fix(test): ...` commits.
> - `toothless` fixes: strengthen the assertion so it would catch the mutation. Use `fix(test): ...` commits.
> - `app-bug` (rare — if Validator finds the SUT itself is broken): use `fix(app): ...` commits. **Separate commits required** — never mix `fix(app)` and `fix(test)` in one commit.
> - Minimal changes only. No refactoring, no "while I'm here" cleanup.
> - Do not weaken assertions to make a test pass.
> - Run lint + unit tests after fixing. Do NOT run Playwright — Validator owns that.
>
> Return:
>
> ```
> HANDOFF
> TEST_COMMITS=<sha list>
> APP_COMMITS=<sha list>
> END_HANDOFF
> ```

Wait. Continue to round `n+1`.

---

## Step 5 — Reporter & debt ledger

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Post PR summary, update consolidated debt issue, check thresholds, include negative-control results.
>
> **Inputs:** `PR_NUMBER` (if from PR source), `REPO`, `RISK_TIER`, `SPLIT_PATH` (if set — only for spec-from-pr), all round validator report paths, `ENRICHED_PATH`.
>
> **5a. Post PR summary comment** via `gh pr comment <PR_NUMBER>` (skip if no PR — e.g. issue-source with no linked PR):
>
> ```markdown
> ## E2E QA: <PASS | FAIL>
>
> | Round | Pass (bites) | Test-bugs | Toothless | Flakes |
> |-------|-------------|-----------|-----------|--------|
> | R1    | N/M         | N         | N         | N      |
>
> **Test bugs fixed:** <list>
> **Toothless tests fixed:** <list>
> **Quarantined flakes:** <list — need human triage>
> **Outstanding:** <any remaining after max rounds>
>
> ### Negative-control results
> <paste the Negative-control results table from the final Validator report>
>
> Residual human-QA debt tracked: <issue url or "N/A — spec-from-issue source">
> ```
>
> **5b. Consolidated debt issue.** If `SPLIT_PATH` is set (spec-from-pr only), run the full debt ledger flow. If `SPLIT_PATH` is not set (spec-from-issue), skip debt creation — the issue author already triaged scope and no additional human-only debt is produced.
>
> When debt flow runs, first ensure label exists:
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
> **If a backlog issue exists:** append this PR's debt via a comment:
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
> **5c. Threshold alarm.** Count unchecked PR sections in the consolidated backlog:
> ```bash
> gh issue list --label qa-debt --state open --json number,createdAt,title
> gh issue view <backlog-issue-number> --json comments --jq '.comments | length'
> ```
> Alarm if unchecked PR sections ≥ 10 OR backlog issue created > 30 days ago without being closed. If alarm triggers, print `THRESHOLD ALARM`.
>
> Return:
>
> ```
> HANDOFF
> VERDICT=<PASS|FAIL>
> DEBT_ISSUE=<url or "N/A">
> ALARM=<none|threshold|age>
> END_HANDOFF
> ```

---

## Final summary (orchestrator)

Present to user:

```
## E2E QA Complete

Source: <spec-from-pr PR #<n> | spec-from-issue issue #<n> | --scenarios <path>>
Verdict: <PASS|FAIL>
Risk tier: <tier>
Rounds: <n>
Tests passing and biting: <n>  |  Test-bugs fixed: <n>  |  Toothless fixed: <n>  |  Flakes quarantined: <n>

Residual QA debt: <DEBT_ISSUE>
<alarm message if any>

Next steps:
- If high-risk: run residual checklist before merge.
- If medium-risk: merge OK; checklist must clear before next release cut.
- If low-risk behind a flag: checklist must clear before flag flip to 100%.
```

If `ALARM` is set, additionally: "QA debt backlog exceeds budget. Pay down open `qa-debt` issues before running `/e2e-qa` again."
