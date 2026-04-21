# E2E QA Workflow Guide

## Overview

Playwright-first automated QA for feature PRs. A five-phase pipeline (Designer → Implementer → Runner ↔ Fixer → Reporter) generates and runs E2E tests, then records residual human QA as a GitHub issue.

Orchestrated by `/e2e-qa`. Runs after `/resolve-issue` and before merge.

---

## Premise & honest scope

**What this captures:** regression-class bugs — frontend↔backend wiring, DOM events triggering API calls, rendering of API responses, cross-component side effects, state persistence. Realistically 60–75% of QA surface.

**What this does NOT capture:** happy-path UX feel, cross-browser quirks, animation jank, focus order / a11y, perf on slow networks, copy review, visual polish. These are tracked as **residual debt** on a GitHub issue and paid by a human on a scheduled cadence — never eliminated, only deferred and batched.

This workflow is net-positive only if debt is bounded. See **Debt ledger** below.

---

## When to use

- New user-facing feature with frontend + backend integration
- Feature adds card types, widgets, or UI flows
- Feature modifies existing E2E-covered behavior (regression risk)

**Skip when:** backend-only with no UI, or purely config/docs.

---

## Phase 1 — Designer (read-only)

**Role:** design Playwright scenarios from the PR diff + acceptance criteria.

**Before designing:** read `~/.claude/guides/e2e-qa-best-practices.md`. The scenarios you produce will be implemented directly — flakiness and scope problems introduced at design time are harder to fix later.

**Input:**
- `gh pr diff <pr>` — the actual change (not the description)
- Acceptance criteria from the linked issue (`gh issue view <n>`)
- Existing Playwright tests (patterns, fixtures, page objects)
- Existing unit tests (to avoid duplication)

Diff alone is dangerous: it describes *what shipped*, not *what was asked for*. If the diff has a bug, diff-only tests assert the bug as correct. Always pair with spec.

**Output:** `.claude-work/E2E_<feature>_PLAN.md`

```markdown
# E2E Test Plan: <feature>

## PR Risk Tier: <high | medium | low>
<one-line justification: high = auth/payments/data-loss/public-launch;
 medium = user-facing feature no flag; low = behind flag, internal tool, or thin UI on backend change>

## Infrastructure Notes
<page objects, route stubs, test fixtures needed>

## Scenarios

### S1: <name>
- **Priority**: critical | high | medium | low
- **Why not a unit test**: <must be justified — if unit test could cover it, cut the scenario>
- **Playwright feature**: route-stub | real-backend | visual-snapshot | a11y-scan
- **Setup**: <preconditions>
- **Steps**: <numbered user actions, in terms of roles/labels not selectors>
- **Expected**: <observable outcomes>
```

**Rules:**
- One scenario per distinct user flow, not per code change.
- Every scenario must have a `why-not-unit` justification. No justification → cut it.
- Risk tier classifies the PR as a whole, not individual scenarios.

---

## Phase 2 — Implementer

**Role:** write Playwright test code.

**Hard rules (not negotiable):**
- Selectors: `getByRole`, `getByLabel`, `getByTestId` only. No CSS class or XPath selectors.
- Waits: Playwright auto-waits. No `waitForTimeout`. Use `expect(...).toBeVisible()` etc.
- Network: `page.route()` for stubs. Prefer over browser-side mocking.
- Reuse: page objects / fixtures must come from existing files when available. No per-test helper duplication.
- Visual / a11y: if plan specifies `visual-snapshot` use `toHaveScreenshot()`; if `a11y-scan` use `@axe-core/playwright`.
- Lint/format after writing. Do NOT run tests — that's Phase 3.

**Budget:** if the plan exceeds a reasonable scenario count (≥ 10 new tests), flag to the user before implementing — may indicate the feature is too large or the plan duplicates unit coverage.

**Test-mode endpoints:** if a scenario genuinely needs server-side puppeting, gate it behind the project's test-mode flag. Never expose in production. Prefer `page.route()` stubbing when feasible.

---

## Phase 3 — Runner (repeatable)

**Role:** run tests, distinguish bugs from flakes, diagnose root causes.

**Steps:**
1. Kill any running server/dev instances per project convention.
2. Run unit tests first — baseline must be green.
3. Run Playwright tests, capturing traces on failure.
4. For each failing test, **re-run it 3× in isolation**:
   - 3/3 fail deterministically → real bug. Read source, diagnose.
   - Intermittent → `flake-quarantine`. Do NOT report as a bug. Do NOT let Fixer touch it.
5. For real bugs: read the source, classify `app-bug` vs `test-bug`, identify root cause. One root cause can cascade across many tests — report the cause, not each symptom.

**Output:** `.claude-work/E2E_BUG_REPORT_R<N>.md`

```markdown
# E2E Bug Report — Round <N>

## Results
- Passed: N
- Failed: N  (deterministic: N, quarantined flakes: N)

## Bugs

### BUG-R<N>-1: <title>
- **Tests affected**: <test names>
- **Type**: app-bug | test-bug
- **Severity**: critical | high | medium
- **Root cause**: <analysis from reading source>
- **Fix**: <what changes where>
- **Trace**: <path to trace.zip>

## Quarantined Flakes
- <test name> — <observed failure> — reran 3×, passed N/3. Not fixed this round.
```

---

## Phase 4 — Fixer

**Role:** apply fixes with separation of concerns.

**Rules:**
- Fix `app-bug` and `test-bug` entries. Leave `flake-quarantine` alone.
- **Separate commits.** `fix(app): ...` and `fix(test): ...` — never combined. This makes it possible to revert a bad "fix" without losing the other category.
- Minimal changes only. No refactoring, no "while I'm here" cleanup. Edit budget enforced by orchestrator.
- Do not weaken test assertions to pass. If a test assertion is wrong, the Runner should have classified it as `test-bug` with a root cause — fix that, don't relax it.
- Run lint + unit tests. Do NOT run Playwright — Runner owns that.

---

## Loop protocol

- Max 3 rounds by default.
- If a round finds 0 bugs, exit loop early.
- Final round is **report-only** — no Fixer invocation.
- After 3 rounds with remaining bugs: final report surfaces them for human triage. The PR is not blocked automatically — the human decides.

---

## Phase 5 — Reporter & debt ledger

**Role:** post PR summary, file debt issue, check thresholds.

### 5a. PR summary comment

```markdown
## E2E QA: <PASS | FAIL>

| Round | Passed | Failed | App Bugs | Test Bugs | Flakes |
|-------|--------|--------|----------|-----------|--------|
| R1    | N/M    | N      | N        | N         | N      |
| R2    | ...    |        |          |           |        |

**App bugs fixed:** <list>
**Test bugs fixed:** <list>
**Quarantined flakes:** <list — need human triage>
**Outstanding:** <any bugs remaining after max rounds>

Residual human-QA debt tracked: <issue url>
```

### 5b. Debt issue

Ensure label exists:
```bash
gh label create qa-debt --color FBCA04 \
  --description "Residual human QA owed for a merged auto-QA PR" 2>/dev/null || true
```

Create the issue:
```bash
gh issue create --label qa-debt --title "qa-debt: PR #<n> — <feature>" --body "$(cat <<'EOF'
**PR:** #<n> — <link>
**Merged:** <date, or "pending merge">
**Risk tier:** <tier>

## Auto-covered
<short bullet list of regression areas exercised by Playwright>

## Residual human-QA checklist
- [ ] Happy-path walkthrough in dev against real backend
- [ ] Cross-browser smoke (Safari, Firefox) for any user-visible UI changes
- [ ] Keyboard-only navigation / a11y for new interactive elements
- [ ] Perf on throttled network for pages that load new data
- [ ] Copy / UX review for any new user-facing strings
- [ ] <any scenario-specific residual items — e.g. "visual check of animation">

## Payment rules
- High-risk: clear BEFORE merge.
- Medium-risk: clear before next release cut.
- Low-risk (flag-gated): clear before flag flip to 100%.
EOF
)"
```

### 5c. Threshold alarm

```bash
gh issue list --label qa-debt --state open --json number,createdAt
```

Alarm if:
- Open count ≥ 10, OR
- Oldest open issue > 14 days

On alarm: print a THRESHOLD ALARM in the final summary. The orchestrator tells the user to pay down debt before running `/e2e-qa` again.

---

## Debt payment workflow

Four triggers. Use all of them.

1. **Risk gate at merge time.** `high` risk PRs: human runs the checklist before merge. `medium`/`low`: merge, accumulate.
2. **Release-cut drain.** Before any user-facing deploy: all open `qa-debt` issues touching shipped code must be closed (checklist complete).
3. **Threshold alarm.** ≥ 10 open or oldest > 14 days: block new `/e2e-qa` runs until the backlog shrinks.
4. **Flag-flip gate.** For low-risk flag-gated PRs: debt must clear before flag flips to 100% rollout.

Humans close the issue by checking off the list and commenting with findings (or filing a follow-up bug if the checklist surfaces problems).

---

## Integration with other workflows

```
/refine-issue → /resolve-issue → /e2e-qa → merge
                                   ↓
                                 qa-debt issue
                                   ↓
                         paid at release / flag flip / alarm
```

---

## Tips

- **Diffs lie, specs don't.** Designer must read both. Diff shows what shipped; spec shows what was asked for. Disagreement = bug, not test material.
- **Cascade failures.** One root cause often breaks many tests. Report the cause once, not per symptom.
- **Quarantine > fix-on-sight for flakes.** Fixing a flaky test by "making it more robust" usually means weakening assertions or adding sleeps. Quarantine, triage later with humans.
- **Page objects > inline selectors.** If Implementer is writing raw selectors in test bodies, force a page-object refactor — brittleness compounds.
- **Don't duplicate unit coverage.** If a unit test verifies JSON parsing, the E2E doesn't. The `why-not-unit` field in the plan is the filter.
- **Test-mode endpoints are a last resort.** Prefer `page.route()` stubs. Real server code paths catch more bugs than mock injection points.
