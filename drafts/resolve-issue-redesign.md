# Plan: `/resolve-issue` redesign — blast-radius-aware test orchestration

## Purpose

The current `/resolve-issue` chain (`/fix-issue` → `/pr-review-cycle` → `/pr-finalize`) optimises for *local correctness*: did this PR build the thing the issue describes? As codebases grow, the dominant failure mode shifts from local correctness to **blast radius** — a change in one place silently breaks something it doesn't appear to touch. Test-first development is a local-correctness lever and does not address this. This redesign focuses the orchestrator on the levers that actually shrink blast radius:

1. **Compounding test corpus** — every issue should leave behind durable component and integration tests that fail when *future, unrelated* changes break the wiring. This is the long-term value of `/component-test` and `/integration-test`; their value to the *current* PR is secondary.
2. **Impact-aware scoping** — instead of asking "did the diff cross a module boundary?", ask "what does the diff transitively reach?" and require coverage at those reached boundaries. For projects with a code-intelligence tool (e.g. pyscope-mcp's `impact`, `call_chain`), use it.
3. **Honest test tiering** — split integration tests into a per-push wiring tier and a nightly/pre-release artifact tier, tagged so each runs independently. Mirrors industry practice (Google small/medium/large, Fowler narrow/broad).
4. **Suite completeness gate** — before declaring done, run the *full* relevant tier, not just the tests the implementation agent knows about. Skipping "unrelated" tests is a classic blast-radius failure.
5. **Architecture-first for high-blast issues** — most blast-radius incidents trace back to a design choice that didn't anticipate a coupling. The existing ADR gate is the right lever; the redesign should make it harder to bypass on issues that touch shared interfaces.

This plan is scoped to the orchestrator and the two stubbed test skills. It does not redesign `/fix-issue`, `/pr-review-cycle`, or `/pr-finalize` beyond the handoff data they already produce.

## Related skills

| Skill | Role in the redesign | Status |
|---|---|---|
| [`/resolve-issue`](../commands/resolve-issue.md) | Orchestrator. Adds impact assessment, suite-completeness gate, and tier routing. | Existing — modify |
| [`/fix-issue`](../commands/fix-issue.md) | Implementation. No changes; consumed via existing HANDOFF block. | Existing — unchanged |
| [`/component-test`](../commands/component-test.md) | Writes durable boundary tests after implementation. Purpose section to be rewritten (see below). | Stub — implement |
| [`/integration-test`](../commands/integration-test.md) | Writes wiring + artifact tests, tagged by tier. Purpose section to be rewritten (see below). | Stub — implement |
| [`/e2e-qa`](../commands/e2e-qa.md) | Browser-driven full-stack check. Already in the orchestrator. | Existing — unchanged |
| [`/pr-review-cycle`](../commands/pr-review-cycle.md) | Post-test review. Unchanged but runs after the new gates. | Existing — unchanged |

## Design

### 1. Light/heavy integration split

`/integration-test` produces two tiers, both as part of the same skill invocation:

- **Wiring tier** (fast, every CI push). Verifies that the feature slice's plumbing is correct: routes resolve, handlers are registered, dependency injection wires up, schemas validate, the service starts. Uses real infrastructure for the closest collaborator (real DB) and stubs the rest. Time budget: per-test < 5s, suite total < 60s. Tag: `@integration:wiring` (pytest marker / Jest project / Go build tag, per project conventions).
- **Artifact tier** (slow, nightly / pre-release / on label). Verifies the feature slice produces the *correct output* against committed test fixtures — golden JSON, golden files, golden DB state. Real infra, no stubs. Tag: `@integration:artifact`. Excluded from PR CI by default; runnable on demand via label or manual trigger.

The skill emits a `TIER_BREAKDOWN` block in its HANDOFF so the orchestrator can record what was written:

```
TIER_BREAKDOWN
WIRING_TESTS=<int>
ARTIFACT_TESTS=<int>
WIRING_RUN_COMMAND=<command>
ARTIFACT_RUN_COMMAND=<command>
```

Naming: `integration:wiring` and `integration:artifact` describe purpose, not speed. Speed is a consequence — a wiring test that takes 30s is a smell, an artifact test that takes 30s is fine.

### 2. Impact-aware assessment

Replace the current Assessment Agent's "did the diff cross a module boundary?" heuristic with a two-step probe:

1. **Native impact analysis if available.** Probe `WORK_DIR` for known code-intelligence tools (pyscope-mcp MCP server, language servers exposing call graphs, etc.). If found, ask which modules / functions are *transitively reachable* from the changed files. This is the impact set.
2. **Fallback to diff-stat heuristic.** If no impact tool is available, use the current diff-based logic but tighten it: any change to a public exported symbol with > 3 call sites in the codebase requires component tests by default.

The impact set replaces the boundary heuristic for `COMPONENT_TESTS` and `INTEGRATION_TESTS` decisions:

- `COMPONENT_TESTS=true` if the impact set includes ≥ 1 module the diff does not directly modify (i.e., the change reaches across a boundary).
- `INTEGRATION_TESTS=true` if the impact set includes any module tagged as a system-edge layer (HTTP handlers, CLI entrypoints, MCP tool surfaces, scheduled jobs).

The Assessment HANDOFF gains:

```
IMPACT_TOOL=<name|"none">
IMPACT_SET=<comma-separated modules, may be empty>
DIRECT_CHANGES=<comma-separated modules>
TRANSITIVE_REACH=<int>
```

These are logged to the user verbatim — the assessment becomes auditable.

### 3. Suite-completeness gate

Add a new step between integration tests and `/pr-review-cycle`: **run the full suite the project considers blocking**, not just the tests written this session.

- Discover the suite via the project's CI config (`.github/workflows/*.yml`, `pyproject.toml` `[tool.pytest.ini_options]`, `package.json` `scripts.test`, etc.).
- Run it inside `WORK_DIR` against the head commit.
- If anything fails that's *not* a test written this session, that's a blast-radius hit — stop and report. Do not proceed to PR review.

This is the highest-leverage single change in this plan. It's also the one most likely to surface flaky tests in projects without test hygiene; the plan should accept that as a forcing function rather than route around it.

The new HANDOFF:

```
HANDOFF
SUCCESS=<true|false>
SUITE_COMMAND=<the command run>
NEW_FAILURES=<comma-separated test ids that failed and were not modified by this branch>
PRE_EXISTING_FAILURES=<comma-separated test ids that fail on BASE too>
END_HANDOFF
```

Pre-existing failures are noted but do not block; new failures block.

### 5. Two-tier test failure handling

Secondary test phases (`/component-test`, `/integration-test`) surface two qualitatively different kinds of failure. Treating them the same — either auto-fixing everything or hard-stopping on anything — is wrong in both directions.

---

#### Tier 1 — Simple bugs (intra-skill fix loop)

Simple bugs are mechanically wrong test code that don't require understanding business logic to fix: wrong import path, bad mock wiring, missing `await`, assertion comparing the wrong type, file-naming mismatch. 

Each test skill runs an internal fix loop for these — the orchestrator is not involved:

- Cap at **2 attempts** per failing test file
- The fixer may only edit test files, never source files
- Hard Rules 1–6 from `/component-test` still apply — weakening an assertion to force a pass is not a fix
- If still failing after 2 attempts, the bug is reclassified as non-simple and emitted in the HANDOFF for Tier 2

Criteria distinguishing simple from non-simple (the fixer applies this before touching anything):
- **Simple**: the test code is mechanically wrong independent of what the implementation does. Fixing it doesn't require reading business logic.
- **Non-simple**: the test correctly describes a contract but the implementation doesn't meet it, OR the fixer cannot confidently classify the failure. When in doubt, treat as non-simple.

---

#### Tier 2 — Non-simple bugs (collected, reviewed after all test phases)

Non-simple bugs are failures that implicate the implementation or the issue scope, not just the test code. Each test skill collects them and includes them in its HANDOFF:

```
NON_SIMPLE_BUGS
BUG
BUG_ID=<skill>-<boundary-id>-<n>
TEST_ID=<test identifier>
FAILURE_REASON=<NEGATIVE_CONTROL_FAILED|WRONG_LAYER|ASSERTION_FAILURE|AMBIGUOUS|...>
RUNNER_OUTPUT=<trimmed to 30 lines>
DIAGNOSIS=<one paragraph: what the test expects, what the implementation does, why it's non-trivial>
END_BUG
END_NON_SIMPLE_BUGS
```

An empty block (zero `BUG` entries) is valid and expected for clean runs.

---

#### Bug Review Agent (Step 2e)

After all test phases complete (2a and 2b), if the combined `NON_SIMPLE_BUGS` set across all phases is non-empty, the orchestrator spawns a **Bug Review Agent** (`model: "sonnet"`).

The Bug Review Agent does two things in sequence: first it spawns a **Fix Planner** subagent to understand what a fix would require, then it uses that plan to classify the bug set and decide whether automated repair is appropriate.

---

**Phase 1 — Fix Planner subagent** (`model: "sonnet"`)

Inputs passed to the Fix Planner:
- All `NON_SIMPLE_BUGS` entries from all test phases
- The GitHub issue (body, acceptance criteria)
- The PR diff (`git diff <BASE>...HEAD`)
- The implementation plan (`.agent-work/ISSUE_<n>_PLAN.md`)
- The ADR if present (`.agent-work/ISSUE_<n>_ADR.md`)
- `DIRECT_CHANGES` — the set of files the original implementation touched

The Fix Planner answers three questions without touching any files:

1. **What is the proposed fix?** Produce a concrete implementation plan (1–5 steps, file-level, no code). Each step names the file to change, what to change, and why.

2. **What is the blast radius?** For each step in the plan, state whether it touches a file inside `DIRECT_CHANGES` (contained) or outside it (expanded). Compute: `BLAST_RADIUS=CONTAINED` if all steps are within `DIRECT_CHANGES`; `BLAST_RADIUS=EXPANDED` if any step touches a file outside it.

3. **Are new tests needed?** For each step that introduces a new code path or a new module boundary, assess two things independently:
   - Does the new path cross a module boundary that isn't already covered by a component test? → `NEW_COMPONENT_TESTS_NEEDED`
   - Does the new path reach a system-edge layer (HTTP handler, CLI entrypoint, MCP tool surface, scheduled job) or produce new artifact output (new DB state, new response shape)? → `NEW_INTEGRATION_TESTS_NEEDED`

   Both lists are per-boundary descriptions. Either or both may be empty.

Fix Planner HANDOFF:

```
HANDOFF
FIX_PLAN=<numbered steps, one per line, semicolon-separated for HANDOFF encoding>
BLAST_RADIUS=<CONTAINED|EXPANDED>
EXPANDED_FILES=<comma-separated files outside DIRECT_CHANGES, or empty>
NEW_COMPONENT_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
NEW_INTEGRATION_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
END_HANDOFF
```

---

**Phase 2 — Classification**

The Bug Review Agent reads the Fix Planner's HANDOFF and classifies the bug set as exactly one of A, B, or C.

**Classification A — Simple fix**

The proposed fix is contained within `DIRECT_CHANGES`, no new tests are needed, and the implementation correctly addresses the acceptance criteria. This is the minimal repair case.

Criteria:
- `BLAST_RADIUS=CONTAINED`
- `NEW_TESTS_NEEDED=empty`

**Classification B — Reasonable fix, new tests needed**

The proposed fix is within the same scope — it doesn't require expanding the blast radius — but it introduces new code paths or boundaries that need additional test coverage. This includes both new module boundaries (component tests) and new system-edge paths or artifact outputs (integration tests). The issue spec is still valid and achievable; the original implementation just didn't handle enough of it.

Criteria:
- `BLAST_RADIUS=CONTAINED`
- `NEW_COMPONENT_TESTS_NEEDED` or `NEW_INTEGRATION_TESTS_NEEDED` (or both) is non-empty
- Acceptance criteria remain achievable after the fix

**Classification C — Beyond scope**

The proposed fix requires expanding the blast radius, or the acceptance criteria are insufficient to describe a solvable problem given what testing revealed. The spec must be re-written before automated repair is attempted.

Criteria (any one sufficient):
- `BLAST_RADIUS=EXPANDED`
- Acceptance criteria are contradictory or underspecified in a way only the spec author can resolve
- The implementation correctly executes the spec, but the spec doesn't address the revealed problem

If classification is ambiguous between B and C, prefer C — the cost of a false C (human re-scopes unnecessarily) is lower than a false B (automated fix deepens a misunderstanding).

---

**GitHub posts (all classifications)**

The Bug Review Agent posts to both the **GitHub issue** and the **PR** before returning. Both posts use the sentinel `<!-- bug-review-summary -->` for idempotent re-posting.

Post content:
- Classification (A/B/C) and one-paragraph rationale
- Bug IDs and one-line diagnosis per bug
- The Fix Planner's proposed plan (for A and B)
- For A: "auto-fix starting — 3 attempts max, no new tests required"
- For B: "auto-fix starting — 3 attempts max, new tests will be written for: component: `<NEW_COMPONENT_TESTS_NEEDED>`; integration: `<NEW_INTEGRATION_TESTS_NEEDED>`" (omit either clause if empty)
- For C: "scope insufficient — fix requires `<EXPANDED_FILES>` — human intervention required"

The Bug Review Agent's HANDOFF:

```
HANDOFF
CLASSIFICATION=<A|B|C>
BUG_COUNT=<int>
BLAST_RADIUS=<CONTAINED|EXPANDED>
NEW_COMPONENT_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
NEW_INTEGRATION_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
FIX_PLAN=<semicolon-separated steps>
REASON=<one paragraph>
ISSUE_COMMENT_URL=<url>
PR_COMMENT_URL=<url>
END_HANDOFF
```

---

#### Implementation failure path (Step 2f) — Coder+Tester loop

Runs only for Classification A or B. The Coder follows the Fix Planner's pre-approved plan — it does not re-derive a plan from scratch.

Spawn a **Coder+Tester loop**, max **3 iterations**:

**Coder** (`model: "sonnet"`) per iteration:
- Receives the Fix Planner's plan (from the Bug Review Agent HANDOFF)
- Patches only the files named in the plan — no ad-hoc exploration
- May not touch files outside `DIRECT_CHANGES` (the plan already guarantees this; if the Coder finds it cannot execute the plan without doing so, it returns `PLAN_INSUFFICIENT` rather than expanding scope unilaterally)
- Patches source files only — the tests define the contract and are never modified here

**Tester** (`model: "sonnet"`) per iteration:
- Re-runs the originally failing tests (targeted, not the full suite) against the patched code
- Reports pass/fail with runner output

**If `PLAN_INSUFFICIENT` is returned:**
- Reclassify as C
- Amend the GitHub posts (posted in Step 2e)
- Stop and request human intervention

**After a passing Tester run:**
- Run intent validation against the original issue acceptance criteria
- If intent passes → for Classification B, continue to Step 2g (new tests); for Classification A, proceed directly to Step 2c (E2E QA)

**If 3 iterations are exhausted:**
- Reclassify as C
- Amend the GitHub issue comment and PR comment to reflect reclassification and summarise what the 3 attempts tried
- Stop and request human intervention

---

#### New tests path (Step 2g) — Classification B only

After the Coder+Tester loop succeeds for a Classification B bug set, spawn targeted test phases for whatever the Fix Planner identified. Both may run; either may be absent.

**If `NEW_COMPONENT_TESTS_NEEDED` is non-empty:**

```
/component-test <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --boundaries "<NEW_COMPONENT_TESTS_NEEDED>"
```

**If `NEW_INTEGRATION_TESTS_NEEDED` is non-empty:**

```
/integration-test <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --boundaries "<NEW_INTEGRATION_TESTS_NEEDED>"
```

Both are focused invocations — the boundary list is pre-supplied by the Fix Planner, not re-derived from the full diff. The same Tier 1/Tier 2 failure rules apply to each. If either returns `SUCCESS=false` (hard failure), stop and report. Non-simple bugs from these targeted runs are noted in the final report but do not re-enter the Bug Review loop — this is not a recursive structure.

After Step 2g completes → proceed to Step 2c (E2E QA).

---

#### Scope failure path (Step 2e terminal)

After posting to GitHub, stop. Do not proceed to Step 2d, Step 3, or Step 4. The user must re-scope the issue and re-run from the beginning.

---

#### What this flow does NOT apply to

- **Step 2c (E2E QA)**: browser/app failures implicate the full stack, not a single boundary — hard-stop as before
- **Step 2d (suite completeness)**: failures in pre-existing tests are not for this loop to fix
- **Step 1 (`/fix-issue`) failures**: implementation never started — different scope entirely
- **`RUNNER_NOT_VERIFIED`, `NO_TESTS_COLLECTED`, `USER_DECLINED`**: infrastructure/environment failures hard-stop immediately without entering either tier

### 4. ADR gate hardening for shared-interface changes

Currently the ADR gate triggers on Tier 2/3 with open questions. Strengthen it: if the impact set (from §2) reaches any module flagged as a shared interface (heuristic: imported by ≥ 5 other modules, OR matches a project-defined `shared_interfaces` glob in repo config), require an ADR even on Tier 1 / Tier 2 with no surfaced open questions. The ADR can be a one-paragraph "no design changes, here's why this is safe" — but it must exist and be approved.

This is the cheapest blast-radius lever per dollar: most cross-cutting incidents are diagnosable as a missing design conversation.

## Step-by-step orchestrator changes

The new `/resolve-issue` flow:

1. **Step 1 — fix-issue** — unchanged.
2. **Step 2 — Assessment** — extended with impact probe (§2). Emits richer HANDOFF.
3. **Step 2-pre — Shared-interface ADR check** — *new*. If the impact set hits a shared interface and no ADR exists, stop and require the user to run `/fix-issue` again with the ADR step forced (or escalate to the user with a one-paragraph design note).
4. **Step 2a — Component tests** — unchanged invocation; skill itself sharpened (see component-test purpose update). Skill runs its own Tier 1 fix loop internally. Collects non-simple bugs in HANDOFF. On `SUCCESS=false` for hard failures (runner missing, no tests collected), stop immediately.
5. **Step 2b — Integration tests (wiring)** — unchanged invocation; skill writes both tiers (§1). Same Tier 1 / non-simple collection pattern as 2a. Orchestrator only gates on wiring-tier failures; artifact-tier results are informational unless `--require-artifact-tests` is passed.
6. **Step 2e — Bug Review** — *new*. Runs only if combined `NON_SIMPLE_BUGS` from 2a+2b is non-empty. Spawns Bug Review Agent which first runs Fix Planner, then classifies A/B/C (§5). Posts to GitHub. C → stop. A or B → continue to Step 2f.
7. **Step 2f — Coder+Tester loop** — *new*. Runs for Classification A or B. Coder follows the Fix Planner's pre-approved plan. Max 3 iterations. Success → A goes to Step 2c; B goes to Step 2g. Exhausted or `PLAN_INSUFFICIENT` → reclassify C, amend GitHub posts, stop.
8. **Step 2g — Targeted component tests** — *new*. Runs only for Classification B after Step 2f succeeds. Invokes `/component-test` targeted at `NEW_TESTS_NEEDED` boundaries. Hard failure → stop. Then proceed to Step 2c.
9. **Step 2c — E2E QA** — unchanged. Runs after test phases (and after 2f/2g if they ran). Hard-stop on `VERDICT=FAIL`.
9. **Step 2d — Suite completeness** — *new*. Runs after E2E QA. Full blocking test command. Gates on new failures (§3).
10. **Step 3 — pr-review-cycle** — unchanged.
11. **Step 4 — pr-finalize** — unchanged.

New flags:

- `--no-impact-probe` — fall back to diff-stat heuristic even if an impact tool is available.
- `--require-artifact-tests` — promote artifact-tier failures from informational to blocking. Use for release branches.
- `--skip-suite-check` — skip Step 2d. Escape hatch for repos without a runnable suite; emits a loud warning.
- `--impl-fix-loops <n>` — max Coder+Tester iterations in Step 2f. Default: 3. Pass 0 to disable Step 2f entirely (Bug Review Agent still runs and posts; Classification 1 becomes an informational result, not a fix trigger).
- `--no-impl-fix` — alias for `--impl-fix-loops 0`.

## Open questions

1. **Simple vs non-simple classification inside test skills** — the Tier 1 fixer inside each skill classifies failures before touching anything. A misclassification that promotes a non-simple bug to Tier 1 (and silently weakens an assertion to force a pass) is the worst case. The guard is the "may not weaken assertions" constraint, but should skills also emit a post-fix diff for the orchestrator to audit? Adds overhead; worth it if we see this failure mode in practice.
2. **Fix Planner accuracy** — the Fix Planner reasons about blast radius and new tests needed from a static read of the diff and bug diagnoses, without running code. A planner that misidentifies `BLAST_RADIUS=CONTAINED` when it's actually expanded would hand the Coder a bad plan. The Coder's "files named in the plan only" constraint provides a backstop — but if the plan itself names the wrong files, it won't catch it. Should the orchestrator do a post-Coder diff check as a verification layer? Probably yes for classification B (where new tests are expected), where an unexpected file change is a strong signal.
3. **Classification B loop — are targeted component tests also subject to Bug Review?** Step 2g runs `/component-test` on new boundaries introduced by the fix. If those new tests produce non-simple bugs, the current design says "note in final report, don't re-enter the loop." This is correct — a recursive Bug Review loop is not a viable architecture. But it means Classification B fixes that surface deeper issues are reported but not auto-resolved. Is that acceptable? Leaning yes — one level of automated repair is enough; anything deeper is a scope re-conversation.
4. **Discovery of the project's "blocking suite"** is fragile across project shapes. Is a heuristic enough, or do we need a per-repo config file (e.g. `.claude-resolve.toml`) declaring `blocking_suite_command` and `shared_interfaces` globs? Leaning toward optional config with sensible defaults.
2. **Impact tool interface** — pyscope-mcp exposes `impact` directly. For other languages (Go's `gopls`, Rust's `rust-analyzer`, TS LSP) the call shape differs. Worth defining a thin adapter contract the Assessment Agent can probe for, rather than hard-coding pyscope-mcp.
3. **Heavy/artifact tier execution** — should `/resolve-issue` ever run the artifact tier itself, or only ensure tests *exist* and rely on nightly CI to actually run them? Leaning toward "exist only" — running 30+ minute suites in the orchestrator is a poor fit.
4. **Coverage of unmodified files** — the corpus argument says "every PR adds durable tests." Do we enforce a minimum (e.g. at least one test added per non-trivial PR) or just recommend? Hard rules tend to produce trivial tests for compliance. Recommend tracking it as a metric, not a gate.

## Non-goals

- This plan does **not** introduce test-first / TDD as a gate. Acceptance test scaffolding can be added later as a `/fix-issue` enhancement; it's orthogonal to blast-radius.
- This plan does **not** redesign `/fix-issue` internally. Implementation tier logic, Coder/Tester/Integrator structure, and the ADR step inside `/fix-issue` are unchanged.
- This plan does **not** define new test frameworks or runners. All tests use the project's existing tooling, with tags for tier separation.

## Validation criteria

The redesign is successful if:

- A change that breaks an unrelated module is caught by the suite-completeness gate, not by humans during review.
- The artifact tier has fixtures committed and runs against a real backing store, without flaking on retry.
- Skipping the impact probe (`--no-impact-probe`) produces a strictly less precise assessment, never a stricter one — i.e. the probe never *removes* required tests.
- ADR gate fires on shared-interface PRs that previously slipped through, and the rate of false positives (ADRs demanded for trivial changes) stays below ~10%.
