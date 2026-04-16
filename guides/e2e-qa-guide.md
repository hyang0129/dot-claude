# E2E QA Workflow Guide

## Overview

This guide defines how to run an automated E2E QA pipeline after a feature is implemented.
It uses a sequential chain of specialized subagents: **Designer**, **Implementer**, **Runner**,
and **Fixer**. The Runner and Fixer phases loop until tests pass or a max iteration is reached.

Run this workflow **after** `/fix-issue` or `/resolve-issue` produces a PR, and **before**
merging. It catches integration bugs that unit tests miss — especially frontend/backend wiring,
DOM interactions, and state management across page reloads.

---

## When to Use

- New user-facing feature with frontend + backend components
- Feature adds new card types, widgets, or UI flows
- Feature modifies existing E2E-covered behavior (regression risk)
- Complex API + UI integration that unit tests can't fully exercise

**Skip when:** the change is backend-only with no UI, or is purely config/docs.

---

## Phase Overview

```
Designer ──► Implementer ──► Runner ──► Fixer ──┐
                                ▲                │
                                └────────────────┘
                                  (loop until green
                                   or max 3 rounds)
                              ──► Runner (final)
```

All agents run on Opus. Each phase is a separate subagent with a fresh context window.

---

## Phase 1 — Designer (read-only)

**Role:** Design E2E test scenarios based on what was built.

**Input:**
- Issue number / description of what was implemented
- Branch name

**Instructions for the agent:**
1. Read `CLAUDE.md` for project conventions
2. Read existing E2E tests to understand patterns, fixtures, and infrastructure
3. Read new unit tests to understand what's already covered
4. Read the source files that changed (server endpoints, frontend code, config)
5. Design scenarios that exercise **frontend-backend integration** — not duplicating unit tests

**Output:** `.claude-work/E2E_<FEATURE>_PLAN.md`

```markdown
# E2E Test Plan: <feature>

## Test Infrastructure Notes
<fixtures, mocks, test-mode endpoints needed>

## Scenarios

### S1: <name>
- **Setup**: <preconditions>
- **Steps**: <numbered user actions>
- **Expected**: <observable outcomes to assert>
- **Priority**: critical / high / medium / low
```

**Key principles:**
- One scenario per distinct user flow, not per feature
- Focus on what unit tests **cannot** cover: DOM events triggering API calls, API responses
  rendering correctly, cross-component side effects, canvas persistence
- Prioritise: critical (core flow broken = feature is useless) > high (important but workaround
  exists) > medium (edge case) > low (cosmetic)

---

## Phase 2 — Implementer

**Role:** Write the E2E test code and any supporting infrastructure.

**Input:**
- The test plan from Phase 1
- Branch name

**Instructions for the agent:**
1. Read the test plan
2. Read existing E2E test files to match patterns exactly (fixtures, conftest, assertions)
3. Implement all critical and high priority scenarios; include medium/low if straightforward
4. If tests need server-side support (e.g. test puppeting endpoints to inject mock data):
   - Add them guarded by `CLAUDE_RTS_TEST_MODE` (or project-equivalent test mode flag)
   - Follow existing test endpoint patterns
5. If a dev preset is needed, create it under the appropriate directory
6. Run linter/formatter — do NOT run the tests

**Output:**
- Test file(s) in the project's E2E test directory
- Any test infrastructure changes (test endpoints, dev presets, fixtures)

**Constraints:**
- Match existing test patterns exactly — don't invent new conventions
- Test puppeting endpoints must be gated behind test mode — never exposed in production

---

## Phase 3 — Runner (repeatable)

**Role:** Execute E2E tests, diagnose failures, produce a bug report.

**Input:**
- Path to E2E test file(s)
- Branch name
- Round number (R1, R2, R3, ...)

**Instructions for the agent:**
1. Kill any running server instances (follow project's server rule)
2. Run unit tests first to verify baseline is clean
3. Run E2E tests
4. For each failure:
   - Read the error message and traceback
   - Read the relevant source code to understand the root cause
   - Classify as **app-bug** (source code wrong) or **test-bug** (test code wrong)
   - Determine severity: critical / high / medium

**Output:** `.claude-work/E2E_BUG_REPORT_R<N>.md`

```markdown
# E2E Bug Report — Round <N>

## Test Results Summary
- Passed: N
- Failed: N
- Errors: N

## Bugs Found

### BUG-R<N>-1: <title>
- **Test**: <test class/method>
- **Type**: app-bug | test-bug
- **Error**: <brief error message>
- **Root cause**: <analysis after reading source>
- **Fix**: <what needs to change and where>
- **Severity**: critical | high | medium
```

**Key principles:**
- Don't just report errors — **diagnose root causes** by reading source code
- A single root cause can cascade across many tests (especially with module-scoped fixtures);
  identify the root cause, don't list each test separately
- Distinguish app bugs (ship-blocking) from test bugs (test code needs fixing)

---

## Phase 4 — Fixer

**Role:** Apply fixes from the bug report.

**Input:**
- Bug report from Phase 3
- Branch name

**Instructions for the agent:**
1. Read the bug report
2. Read the relevant source files before making changes
3. Fix all bugs (both app-bugs and test-bugs)
4. Run linter/formatter on modified files
5. Run unit tests to verify nothing broke
6. Do NOT run E2E tests — that's the Runner's job

**Constraints:**
- Fix only what the bug report identifies — don't refactor or improve unrelated code
- For app-bugs: make the minimal fix. If the fix is non-trivial, explain the approach
  in the bug report update
- For test-bugs: fix the test to correctly exercise the behavior, don't weaken assertions

---

## Loop Protocol

```
Round 1: Runner → Fixer
Round 2: Runner → Fixer (if needed)
Round 3: Runner (final — report only, no more fixes)
```

**Rules:**
- Max 3 rounds. If tests still fail after round 3, report outstanding issues to the user
  for manual triage
- After each Fixer phase, the next Runner phase starts fresh (new context, re-reads everything)
- If a round finds 0 bugs, skip remaining rounds and report success
- Track cumulative bug counts across rounds for the final report

---

## Final Report

After the last Runner phase completes, the orchestrator presents:

```markdown
## E2E QA Complete: <feature>

| Round | Passed | Failed | App Bugs | Test Bugs |
|-------|--------|--------|----------|-----------|
| R1    | N/14   | N      | N        | N         |
| R2    | N/14   | N      | N        | N         |
| R3    | N/14   | N      | N        | N         |

### App Bugs Found & Fixed
- <bug title> — <one-line description of fix>

### Test Bugs Found & Fixed
- <bug title> — <one-line description of fix>

### Outstanding Issues
<any remaining failures after max rounds>

### Verdict: PASS | FAIL
```

---

## Orchestration Checklist

For the orchestrator (the top-level agent coordinating the pipeline):

- [ ] Feature PR exists and unit tests pass before starting
- [ ] Phase 1 (Designer) completed — test plan reviewed
- [ ] Phase 2 (Implementer) completed — test code written, lint clean
- [ ] Phase 3+4 loop executed (max 3 rounds)
- [ ] Final report presented to user
- [ ] All app-bug fixes committed to the feature branch
- [ ] Existing E2E / smoke tests still pass (regression check in final round)
- [ ] Full unit test suite still passes

---

## Integration with Other Workflows

This QA workflow slots into the broader issue resolution pipeline:

```
/refine-issue  →  /resolve-issue  →  E2E QA pipeline  →  merge
                   (fix + review      (this guide)
                    + rebase)
```

- Run E2E QA **after** `/resolve-issue` produces a clean PR
- If E2E QA finds app bugs, fixes are committed to the same branch/PR
- After E2E QA passes, the PR is ready for human review and merge

---

## Tips

- **Module-scoped fixtures cause cascade failures.** If one test modifies shared state (e.g.
  removes a card), all subsequent tests in the module are affected. The Designer should note
  this risk; the Implementer should add cleanup helpers.

- **Viewport and layout matter.** UI elements that overflow the viewport, get overlapped by
  other cards, or render off-screen will cause Playwright actionability failures. Tests should
  clean up spawned cards and use coordinates that leave room for menus/dialogs.

- **CSS selector normalization.** Browsers normalize inline styles (e.g. `z-index:100` becomes
  `z-index: 100` with a space). Use normalized forms in selectors.

- **Test puppeting > mocking.** Prefer server-side test endpoints that inject mock data over
  monkey-patching or stubbing in the browser. Test endpoints exercise the real server code path;
  stubs skip it.

- **Don't duplicate unit test coverage.** E2E tests should exercise integration paths. If a
  unit test already verifies that an API parses JSON correctly, the E2E test doesn't need to
  re-test that — it tests that the UI calls the API and renders the result.
