---
version: 3.0.0
---

# Resolve Issue

## Purpose

Orchestrator only. Sequences `/fix-issue`, an impact-aware Assessment, secondary test branches (component, integration, E2E QA), a Bug Review + automated repair loop for non-simple test failures, a suite-completeness gate, `/pr-review-cycle`, and `/pr-finalize` — each as an isolated subagent with a fresh context window.

**This command never reads files, never runs git commands, and never writes code.** Its sole job is to pass structured handoff data between phases and make sequencing decisions. Writes to disk (the assessment HANDOFF file, Bug Review HANDOFF file) are performed by subagents on the orchestrator's behalf.

The redesign is centred on **blast radius** — the long-term value of each phase is the durable test corpus and the prevention of cross-cutting regressions, not the local correctness of the current PR.

---

## Args

`/resolve-issue <issue> [tier] [--worktree] [--base <branch>] [--return-only] [--no-component-tests] [--no-integration-tests] [--no-e2e] [--no-impact-probe] [--require-artifact-tests] [--skip-suite-check] [--impl-fix-loops <n>] [--no-impl-fix]`

Forwarded verbatim to `/fix-issue`: `issue`, `tier`, `--worktree`, `--base`.

Resolve-issue-only flags (strip before forwarding to `/fix-issue`):

- `--return-only` — caller-controlled. See Entry Conditions.
- `--no-component-tests`, `--no-integration-tests`, `--no-e2e` — skip the corresponding phase regardless of assessment.
- `--no-impact-probe` — skip native code-intelligence probe; force the diff-stat fallback in Step 2.
- `--require-artifact-tests` — promote artifact-tier integration failures from informational to blocking. Use for release branches.
- `--skip-suite-check` — skip Step 2d (suite completeness). Escape hatch for repos without a runnable suite. Emits a warning.
- `--impl-fix-loops <n>` — max Coder+Tester iterations in Step 2f. Default `3`. `0` disables Step 2f entirely (Bug Review still runs and posts; Classification A/B becomes informational rather than triggering an automated fix).
- `--no-impl-fix` — alias for `--impl-fix-loops 0`.

---

## Entry Conditions

### `--return-only` absent (standalone)

Default. Run all phases, present a Final Summary, and report results to the user.

### `--return-only` present (called from `/resolve-epic`)

**Skip the rebase phase (Step 4).** The resolve-epic Merge & Sync Agent squash-merges the PR into the epic branch — a local rebase is not needed and would conflict with that flow.

---

## Step 1 — fix-issue phase

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run the fix-issue skill with the provided arguments (resolve-issue-only flags stripped).

Append to the subagent prompt:

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

Wait for the subagent to complete. Parse the `HANDOFF` block.

**Gate**: if `SUCCESS=false`, stop. Report `FAILURE_REASON` to the user.

---

## Step 2 — Impact-aware Assessment

Spawn an **Assessment Agent** (`model: "claude-sonnet-4-6"`, read-only tools only) to determine which secondary test phases are warranted, based on the *transitive reach* of the diff rather than only its surface area.

The Assessment Agent does not trust fix-issue's self-report. It reads the real diff and probes the repo for a code-intelligence tool.

Append to the subagent prompt:

> **Role:** Analyse the changes on `BRANCH` in `WORK_DIR` and determine which secondary test phases should run. Probe for an impact-analysis tool. Write the result as a HANDOFF block to `<WORK_DIR>/.agent-work/assessment-handoff-<ISSUE_NUMBER>.txt` AND emit it as the last thing in your output.
>
> **Inputs to gather:**
> 1. `git -C "$WORK_DIR" diff <BASE>...HEAD --name-only` — list of changed files (this is `DIRECT_CHANGES`).
> 2. `git -C "$WORK_DIR" diff <BASE>...HEAD --stat` and full diff — for context.
> 3. `.agent-work/ISSUE_<ISSUE_NUMBER>_PLAN.md` — the implementation plan.
> 4. `.agent-work/ISSUE_<ISSUE_NUMBER>_ADR.md` if present — architecture decisions.
>
> **Step 2.1 — Impact probe.** Unless `--no-impact-probe` was passed, attempt to discover a code-intelligence tool in this order:
>
> 1. **MCP servers**: list available MCP tools. Look for ones exposing call-graph or impact analysis (e.g. `mcp__pyscope__impact`, `mcp__pyscope__call_chain`, similar names). If found, query for the set of modules/functions transitively reachable from each file in `DIRECT_CHANGES`. The union is `IMPACT_SET`. Record `IMPACT_TOOL=<tool-name>`.
> 2. **Language servers / project tooling**: probe for `gopls`, `rust-analyzer`, TS LSP exposed via the project's tooling. Use only if a clear interface is documented in repo (e.g. a script under `tools/`). Do not invent invocations. Record `IMPACT_TOOL=<tool-name>`.
> 3. **None found**: set `IMPACT_TOOL=none`. Use the fallback below.
>
> **Step 2.2 — Diff-stat fallback** (when `IMPACT_TOOL=none` or `--no-impact-probe`): for each public exported symbol changed in the diff, count call sites in the codebase (`Grep` for the symbol). Any symbol with more than 3 call sites contributes its caller modules to a degraded `IMPACT_SET`. `TRANSITIVE_REACH` is the comma-separated list of distinct modules in `IMPACT_SET` that are not in `DIRECT_CHANGES` — i.e., modules the diff reaches but does not directly modify. May be empty.
>
> **Step 2.3 — Decisions.**
>
> - `COMPONENT_TESTS=true` if `IMPACT_SET` contains at least one module the diff does not directly modify (the change reaches across a module boundary). Otherwise `false`.
> - `INTEGRATION_TESTS=true` if `IMPACT_SET` contains any module tagged as a system-edge layer. System-edge means: HTTP handler, CLI entrypoint, MCP tool surface, scheduled job, queue consumer. Detect via path heuristics (`*/handlers/*`, `*/routes/*`, `*/cli/*`, files with `@app.route`, `gin.Engine.GET`, `mcp.tool(`, etc.) cross-referenced against the impact set. Otherwise `false`.
> - `E2E_QA=true` if the diff touches UI/routes AND Playwright infrastructure exists. Probe:
>   ```bash
>   grep -rl "playwright" "$WORK_DIR" \
>     --include="*.spec.ts" --include="*.spec.js" \
>     --include="*.e2e.ts" --include="*.e2e.js" \
>     --include="*.test.ts" --include="*.test.js" \
>     --include="*.py" \
>     --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ \
>     2>/dev/null | head -1
>   ```
>   If no match, `E2E_QA=false` regardless of UI changes.
>
> **Step 2.4 — Shared-interface flag.** Compute `SHARED_INTERFACE_HIT`:
> - Prefer a project config file at `.claude-resolve.toml` with key `shared_interfaces = ["glob", ...]`. If present, glob-match `IMPACT_SET` against it.
> - Otherwise heuristic: any module in `IMPACT_SET` imported by ≥ 5 other modules in the codebase (count via `Grep` for import lines naming the module).
> - `SHARED_INTERFACE_HIT=true|false`. List the matching modules in `SHARED_INTERFACE_MODULES`.
>
> **Output.** Write the HANDOFF block to `<WORK_DIR>/.agent-work/assessment-handoff-<ISSUE_NUMBER>.txt` (create the directory if missing) AND emit it as the last thing in your output:
>
> ```
> HANDOFF
> IMPACT_TOOL=<name|none>
> DIRECT_CHANGES=<comma-separated forward-slash paths>
> IMPACT_SET=<comma-separated module paths, may be empty>
> TRANSITIVE_REACH=<comma-separated module paths reached but not directly modified, may be empty>
> COMPONENT_TESTS=<true|false>
> COMPONENT_TESTS_REASON=<one sentence>
> INTEGRATION_TESTS=<true|false>
> INTEGRATION_TESTS_REASON=<one sentence>
> E2E_QA=<true|false>
> E2E_QA_REASON=<one sentence>
> SHARED_INTERFACE_HIT=<true|false>
> SHARED_INTERFACE_MODULES=<comma-separated, or empty>
> ADR_PATH=<path to ADR if it exists, else empty>
> END_HANDOFF
> ```

Wait for the subagent. Parse the HANDOFF.

Apply user overrides: `--no-component-tests`, `--no-integration-tests`, `--no-e2e` force the respective flag to `false`.

Set `HANDOFF_FILE=<WORK_DIR>/.agent-work/assessment-handoff-<ISSUE_NUMBER>.txt`. This path is forwarded to test phases via `--handoff-file`.

Log to the user verbatim:

```
## Assessment

Impact tool:        <IMPACT_TOOL>
Direct changes:     <N> files
Transitive reach:   <count of TRANSITIVE_REACH> modules
Shared interface:   <true|false> [<SHARED_INTERFACE_MODULES>]

Component tests:    <true|false> — <COMPONENT_TESTS_REASON>
Integration tests:  <true|false> — <INTEGRATION_TESTS_REASON>
E2E QA:             <true|false> — <E2E_QA_REASON>
```

---

## Step 2-pre — Shared-interface ADR gate

If `SHARED_INTERFACE_HIT=false`, skip this step.

If `SHARED_INTERFACE_HIT=true` AND `ADR_PATH` is empty: stop.

Report to the user:

```
Step 2-pre — ADR required

The diff transitively reaches a shared interface ([<SHARED_INTERFACE_MODULES>]),
but no ADR exists at .agent-work/ISSUE_<ISSUE_NUMBER>_ADR.md.

A shared-interface change without a recorded design decision is the modal cause of
cross-cutting incidents. Resolve one of:

  1. Re-run /fix-issue with the ADR step forced (recommended).
  2. Manually author .agent-work/ISSUE_<ISSUE_NUMBER>_ADR.md (one paragraph
     stating "no design changes; here's why this is safe" is acceptable for
     trivial changes).
  3. Re-run /resolve-issue if the ADR is already drafted on disk.

PR: <PR_URL>
```

Do not proceed.

If `ADR_PATH` is non-empty, log it and continue:

```
Step 2-pre — ADR present at <ADR_PATH>. Proceeding.
```

---

## Step 2a — Component tests (if `COMPONENT_TESTS=true`)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run:

```
/component-test <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --handoff-file <HANDOFF_FILE>
```

Append:

> Return your full HANDOFF block as the last thing in your output. The block includes a
> `NON_SIMPLE_BUGS` section the orchestrator will collect.

Parse the returned HANDOFF. Save the entire `NON_SIMPLE_BUGS` block (verbatim, including `BUG`/`END_BUG` delimiters) to the orchestrator's in-memory `BUG_BACKLOG` keyed by phase `component-test`. Record `RUN_COMMAND` as `RUN_COMMAND_COMPONENT` for use in Step 2f.ii and the Final Summary.

**Gate**: if `SUCCESS=false`, stop. Report `FAILURE_REASON` (one of `RUNNER_NOT_VERIFIED`, `NO_TESTS_COLLECTED`, `USER_DECLINED`, `NEGATIVE_CONTROL_UNVERIFIED:<id>`). Hard infrastructure/environment failures only.

`NON_SIMPLE_BUGS` non-empty does **not** block here — it routes through Step 2e after both test phases complete.

---

## Step 2b — Integration tests (if `INTEGRATION_TESTS=true`)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run:

```
/integration-test <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --handoff-file <HANDOFF_FILE>
```

If `--require-artifact-tests` was passed, also append `--tier both` and instruct the subagent that artifact-tier failures must appear as Tier 2 entries in `NON_SIMPLE_BUGS` (not informational notes).

Parse the HANDOFF. Append the `NON_SIMPLE_BUGS` block to `BUG_BACKLOG` under phase `integration-test`. Record `RUN_COMMAND_WIRING` and `RUN_COMMAND_ARTIFACT` for the Final Summary.

**Gate**: if `SUCCESS=false`, stop. Hard failures only (`INFRA_UNKNOWN`, `RUNNER_NOT_VERIFIED`, `NO_TESTS_COLLECTED`, `USER_DECLINED`). `INFRA_NOT_AVAILABLE=true` is a warning, not a hard failure — proceed.

If `--require-artifact-tests` was passed and any integration test ran with `INFRA_NOT_AVAILABLE=true`, escalate to a hard stop:

```
Step 2b — artifact-tier required but infra unavailable.
Cannot validate artifact tests without real infrastructure. Set up infra (DATABASE_URL etc.) and re-run.
```

---

## Step 2e — Bug Review (if `BUG_BACKLOG` non-empty)

Skip this step if both phase entries in `BUG_BACKLOG` are empty.

If `--impl-fix-loops 0` (or `--no-impl-fix`) was passed, the agent still runs and posts; Classification A/B does not trigger Step 2f.

Spawn a **Bug Review Agent** (`model: "claude-sonnet-4-6"`, full tool access).

Append to the subagent prompt:

> **Role:** You are the Bug Review Agent. Non-simple bugs surfaced by the secondary test phases. Your job is two-phase: spawn a Fix Planner, then classify the bug set, then post to GitHub. Write your HANDOFF to `<WORK_DIR>/.agent-work/bug-review-handoff-<ISSUE_NUMBER>.txt` AND emit it as the last thing in your output.
>
> **Inputs you have access to:**
>
> - `BUG_BACKLOG` (below) — combined `NON_SIMPLE_BUGS` from Step 2a and 2b.
> - `WORK_DIR=<WORK_DIR>`, `REPO=<REPO>`, `BRANCH=<BRANCH>`, `BASE=<BASE>`, `ISSUE_NUMBER=<ISSUE_NUMBER>`, `PR_NUMBER=<PR_NUMBER>`, `PR_URL=<PR_URL>`.
> - `DIRECT_CHANGES=<DIRECT_CHANGES>` — files the original implementation touched.
> - The implementation plan at `<WORK_DIR>/.agent-work/ISSUE_<ISSUE_NUMBER>_PLAN.md`.
> - The ADR at `<WORK_DIR>/.agent-work/ISSUE_<ISSUE_NUMBER>_ADR.md` if present.
> - The PR diff via `git -C "<WORK_DIR>" diff <BASE>...HEAD`.
> - The issue body via `gh issue view <ISSUE_NUMBER> --repo <REPO> --json title,body`.
>
> **BUG_BACKLOG:**
>
> ```
> <verbatim concatenated NON_SIMPLE_BUGS blocks from Step 2a and 2b>
> ```
>
> ---
>
> **Phase 1 — Spawn the Fix Planner.**
>
> Spawn one subagent (`model: "claude-sonnet-4-6"`, read-only tools — Read, Grep, Glob, Bash for `git diff` only). The Fix Planner produces a static plan and does not modify files.
>
> Pass it: BUG_BACKLOG, the issue body, the PR diff, the implementation plan, the ADR if present, and `DIRECT_CHANGES`.
>
> Instruct the Fix Planner to answer three questions and emit:
>
> ```
> HANDOFF
> FIX_PLAN=<numbered steps, one per line in the agent's output, then collapsed to semicolon-separated for HANDOFF encoding>
> FILES_TO_TOUCH=<comma-separated forward-slash paths — the union of files named across every FIX_PLAN step, normalized>
> BLAST_RADIUS=<CONTAINED|EXPANDED>
> EXPANDED_FILES=<comma-separated files outside DIRECT_CHANGES, or empty>
> NEW_COMPONENT_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
> NEW_INTEGRATION_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
> END_HANDOFF
> ```
>
> Definitions:
> - **FIX_PLAN**: 1–5 file-level steps. Each step names the file, what to change, and why. No code.
> - **FILES_TO_TOUCH**: deduplicated list of every file path mentioned in `FIX_PLAN`. The Coder will be constrained to this set, so any file the plan implies edits to must appear here explicitly. Forward slashes only.
> - **BLAST_RADIUS**: `CONTAINED` if every entry in `FILES_TO_TOUCH` is in `DIRECT_CHANGES`. `EXPANDED` if any entry is outside it.
> - **NEW_COMPONENT_TESTS_NEEDED**: per-boundary descriptions for new module boundaries the fix introduces that are not already covered by a component test.
> - **NEW_INTEGRATION_TESTS_NEEDED**: per-boundary descriptions for new system-edge paths or new artifact outputs the fix introduces.
>
> ---
>
> **Phase 2 — Classify.**
>
> Read the Fix Planner's HANDOFF. Classify the bug set as exactly one of:
>
> - **Classification A — Simple fix.** `BLAST_RADIUS=CONTAINED` AND both NEW_*_TESTS_NEEDED are empty AND the implementation correctly addresses the acceptance criteria.
> - **Classification B — Reasonable fix, new tests needed.** `BLAST_RADIUS=CONTAINED` AND at least one of NEW_COMPONENT_TESTS_NEEDED or NEW_INTEGRATION_TESTS_NEEDED is non-empty AND acceptance criteria remain achievable after the fix. Routes to Step 2g, which invokes `/component-test-targeted` and `/integration-test-targeted` with the scope files written in Phase 2.5.
> - **Classification C — Beyond scope.** `BLAST_RADIUS=EXPANDED` OR acceptance criteria are contradictory/underspecified OR the implementation correctly executes the spec but the spec doesn't address the revealed problem.
>
> If classification is ambiguous between B and C, prefer C. Cost asymmetry: false C means a human re-scopes unnecessarily; false B means an automated fix deepens a misunderstanding.
>
> ---
>
> **Phase 2.5 — Emit targeted scope files (Classification B only).**
>
> If `CLASSIFICATION=B`, write up to two scope files for Step 2g's `/component-test-targeted` and `/integration-test-targeted` invocations. Schema is defined once in this document — see the **Targeted scope file schema** section below.
>
> For component tests: if `NEW_COMPONENT_TESTS_NEEDED` is non-empty, write a JSON array to `<WORK_DIR>/.agent-work/targeted-component-scope-<ISSUE_NUMBER>.json`. Each entry corresponds to one description in `NEW_COMPONENT_TESTS_NEEDED`; populate `bug_ids` from any `BUG_BACKLOG` entries whose DIAGNOSIS motivates the description, and `related_files` from the matching subset of `FILES_TO_TOUCH` plus any source files named in those bugs' RUNNER_OUTPUT or DIAGNOSIS. If no obvious mapping exists, leave `bug_ids` empty and use `FILES_TO_TOUCH` as `related_files` — the resolver can still locate the boundary from the description alone.
>
> For integration tests: same procedure for `NEW_INTEGRATION_TESTS_NEEDED` → `<WORK_DIR>/.agent-work/targeted-integration-scope-<ISSUE_NUMBER>.json`.
>
> Set `TARGETED_COMPONENT_SCOPE_FILE` and `TARGETED_INTEGRATION_SCOPE_FILE` in the HANDOFF to the absolute file paths you wrote, or leave empty if you wrote nothing for that side.
>
> If `CLASSIFICATION=A` or `CLASSIFICATION=C`, do not write scope files. Leave both HANDOFF fields empty.
>
> ---
>
> **Phase 3 — Post to GitHub.**
>
> Post the same comment to both the GitHub issue and the PR, using the sentinel `<!-- bug-review-summary -->` for idempotent re-posting. Find an existing comment with that sentinel (via `gh api`) and edit it; otherwise create a new one.
>
> Comment body:
>
> ```
> <!-- bug-review-summary -->
> ## Bug Review — Classification <A|B|C>
>
> <one-paragraph rationale>
>
> ### Bugs
> - `<BUG_ID>` — <one-line diagnosis>
> - ...
>
> ### Proposed plan
> <FIX_PLAN, numbered, only for A and B>
>
> ### Next step
> <one of:
>   "Auto-fix starting — <impl-fix-loops> attempts max, no new tests required." (A)
>   "Auto-fix starting — <impl-fix-loops> attempts max. New tests will be written for: component: <NEW_COMPONENT_TESTS_NEEDED>; integration: <NEW_INTEGRATION_TESTS_NEEDED>." (B; omit either clause if empty)
>   "Scope insufficient — fix requires changes to <EXPANDED_FILES>. Human re-scoping required." (C)
>   "Auto-fix disabled (--no-impl-fix). Bug Review classified as <A|B>; classification posted as informational." (A or B with --no-impl-fix)
> >
> ```
>
> Capture the URLs of both posts.
>
> ---
>
> **Output.** Write to `<WORK_DIR>/.agent-work/bug-review-handoff-<ISSUE_NUMBER>.txt` AND emit:
>
> ```
> HANDOFF
> CLASSIFICATION=<A|B|C>
> BUG_COUNT=<int>
> BLAST_RADIUS=<CONTAINED|EXPANDED>
> NEW_COMPONENT_TESTS_NEEDED=<comma-separated, or empty>
> NEW_INTEGRATION_TESTS_NEEDED=<comma-separated, or empty>
> EXPANDED_FILES=<comma-separated, or empty>
> FIX_PLAN=<semicolon-separated steps>
> FILES_TO_TOUCH=<comma-separated forward-slash paths from the Fix Planner, or empty if Classification C>
> TARGETED_COMPONENT_SCOPE_FILE=<absolute path to component scope file written in Phase 2.5, or empty>
> TARGETED_INTEGRATION_SCOPE_FILE=<absolute path to integration scope file written in Phase 2.5, or empty>
> REASON=<one paragraph>
> ISSUE_COMMENT_URL=<url>
> PR_COMMENT_URL=<url>
> END_HANDOFF
> ```

Wait for the agent. Parse the HANDOFF.

**Gates:**

- `CLASSIFICATION=C` → stop. Report to user with the GitHub comment URLs. Do not proceed to Step 2f, 2g, 2c, 2d, 3, or 4.
- `CLASSIFICATION=A` and `--impl-fix-loops 0` → log informational, skip Step 2f, proceed to Step 2c.
- `CLASSIFICATION=B` and `--impl-fix-loops 0` → log informational, skip Step 2f and Step 2g, proceed to Step 2c.
- `CLASSIFICATION=A` or `B` (default) → continue to Step 2f.

---

## Step 2f — Coder+Tester loop (Classification A or B only)

Loop up to `--impl-fix-loops` iterations (default 3).

Maintain `LOOP_STATE`:
- `iteration` — 1..N
- `last_failure_output` — Tester output from previous iteration, empty on first

### 2f.i — Coder (`model: "claude-sonnet-4-6"`)

Spawn an Agent subagent. Append:

> **Role:** Coder. Implement the pre-approved fix plan from Bug Review. Do not re-derive a plan.
>
> **Constraints:**
> - Patch only the files in `FILES_TO_TOUCH=<FILES_TO_TOUCH>`. Any edit to a file outside this set is a scope violation — return `PLAN_INSUFFICIENT` rather than expanding.
> - `FILES_TO_TOUCH` is by construction a subset of `DIRECT_CHANGES=<DIRECT_CHANGES>` (the Bug Review classification gated on this); you do not need to re-check.
> - Patch source files only — never modify the test files that surfaced the failures.
> - Do not run the suite. Do not stage or commit. The Tester runs next.
>
> **Inputs:**
> - `FIX_PLAN=<FIX_PLAN>` — narrative steps for context.
> - `FILES_TO_TOUCH=<FILES_TO_TOUCH>` — the authoritative scope list.
> - `BUG_BACKLOG` (below) — each bug includes a TEST_ID and DIAGNOSIS.
> - `BRANCH=<BRANCH>`, `WORK_DIR=<WORK_DIR>`.
> - On iteration > 1: `LAST_FAILURE_OUTPUT` (below) — the Tester's previous run.
>
> **Output:** make the file edits. Then emit:
>
> ```
> HANDOFF
> ITERATION=<n>
> SUCCESS=<true|false>
> FILES_MODIFIED=<comma-separated forward-slash paths>
> PLAN_INSUFFICIENT=<true|false>
> NOTES=<one line>
> END_HANDOFF
> ```

Parse. If `PLAN_INSUFFICIENT=true`, exit the loop with reason `PLAN_INSUFFICIENT`. Reclassify as C (see "Loop exit" below).

If any file in `FILES_MODIFIED` is outside `FILES_TO_TOUCH`, exit the loop with reason `SCOPE_VIOLATION`. Reclassify as C. (`FILES_TO_TOUCH ⊆ DIRECT_CHANGES`, so this check subsumes the broader DIRECT_CHANGES guard.)

### 2f.ii — Tester (`model: "claude-sonnet-4-6"`)

Spawn an Agent subagent. Append:

> **Role:** Tester. Re-run only the failing tests from BUG_BACKLOG against the patched code. Targeted run, not the full suite.
>
> **Inputs:**
> - `BUG_BACKLOG` — each bug includes TEST_ID.
> - `WORK_DIR=<WORK_DIR>`, `BRANCH=<BRANCH>`.
> - `RUN_COMMAND_WIRING=<RUN_COMMAND_WIRING>`, `RUN_COMMAND_COMPONENT=<command from Step 2a HANDOFF>` — base commands; you select the test files corresponding to the failing TEST_IDs.
>
> **Output:** run the targeted tests. Then emit:
>
> ```
> HANDOFF
> ITERATION=<n>
> ALL_PASS=<true|false>
> STILL_FAILING=<comma-separated TEST_IDs, or empty>
> RUNNER_OUTPUT=<trimmed to 50 lines>
> END_HANDOFF
> ```

Parse.

### 2f.iii — Loop control

- `ALL_PASS=true` → exit loop, success.
- `ALL_PASS=false` AND iteration < `--impl-fix-loops` → set `LAST_FAILURE_OUTPUT=<RUNNER_OUTPUT>`, increment iteration, repeat from 2f.i.
- `ALL_PASS=false` AND iteration == `--impl-fix-loops` → exit loop with reason `EXHAUSTED`. Reclassify as C.

### 2f.iv — On loop success — intent validation

Spawn an Intent Validator subagent (`model: "claude-sonnet-4-6"`, read-only). Append:

> **Role:** Verify the patched implementation still meets the acceptance criteria from the issue. Read the issue body and the current diff.
>
> **Inputs:** `BRANCH=<BRANCH>`, `BASE=<BASE>`, `WORK_DIR=<WORK_DIR>`, `REPO=<REPO>`, `ISSUE_NUMBER=<ISSUE_NUMBER>`.
>
> **Output:**
>
> ```
> HANDOFF
> INTENT_PASSES=<true|false>
> CRITERIA_MISSED=<comma-separated, or empty>
> END_HANDOFF
> ```

If `INTENT_PASSES=false`, exit loop with reason `INTENT_REGRESSION`. Reclassify as C.

If `INTENT_PASSES=true`:
- Classification A → proceed to Step 2c.
- Classification B → proceed to Step 2g.

### 2f.v — Loop exit (reclassified as C)

For all reclassification reasons (`PLAN_INSUFFICIENT`, `SCOPE_VIOLATION`, `EXHAUSTED`, `INTENT_REGRESSION`):

Spawn a small Agent subagent to amend the GitHub comment posted in Step 2e (same `<!-- bug-review-summary -->` sentinel; edit, don't re-create). Append a section:

```
### Update — Reclassified as C

Reason: <PLAN_INSUFFICIENT|SCOPE_VIOLATION|EXHAUSTED|INTENT_REGRESSION>
Iterations attempted: <n>
Summary: <one paragraph: what the attempts tried, what blocked them>

Human intervention required.
```

Then stop. Report to the user with the comment URLs. Do not proceed.

---

## Step 2g — Targeted new tests (Classification B only)

Runs only after Step 2f succeeded for Classification B.

These are **focused invocations** — the scope was pre-decided by the Fix Planner in Step 2e and persisted as a JSON scope file (see **Targeted scope file schema** below). The targeted skills resolve each free-text description to a concrete boundary or scenario record, then write tests with the same downstream pipeline as the regular skills.

If `TARGETED_COMPONENT_SCOPE_FILE` is non-empty, spawn an Agent subagent for:

```
/component-test-targeted <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --scope-file <TARGETED_COMPONENT_SCOPE_FILE>
```

If `TARGETED_INTEGRATION_SCOPE_FILE` is non-empty, spawn an Agent subagent for:

```
/integration-test-targeted <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --scope-file <TARGETED_INTEGRATION_SCOPE_FILE>
```

Skip a sub-call when its scope file path is empty. Skipping both is valid (Classification B with `NEW_*_TESTS_NEEDED` both empty would have been Classification A — but if Bug Review wrote no scope files for any reason, the step is a no-op).

For each:
- `SUCCESS=false` (hard failure) → stop. Report to the user.
- Non-simple bugs from these targeted runs → record in the Final Summary as informational. They do not re-enter the Bug Review loop. One level of automated repair only.
- `UNRESOLVED_BOUNDARIES` / `UNRESOLVED_SCENARIOS` from these runs → record in the Final Summary as informational. The Fix Planner described a boundary the resolver couldn't locate; that's a finding for human review, not a hard stop.

After Step 2g, proceed to Step 2c.

---

## Targeted scope file schema

The Bug Review Agent writes one scope file per side (component / integration) in Step 2e Phase 2.5 when `CLASSIFICATION=B`. The targeted skills consume them in Step 2g.

Path convention:

```
<WORK_DIR>/.agent-work/targeted-component-scope-<ISSUE_NUMBER>.json
<WORK_DIR>/.agent-work/targeted-integration-scope-<ISSUE_NUMBER>.json
```

Schema — JSON array of records:

```json
[
  {
    "id": "boundary-1",
    "description": "auth → token-rotator",
    "bug_ids": ["component-test-auth-1"],
    "related_files": ["src/auth/login.py", "src/auth/tokens.py"]
  }
]
```

Field semantics:

- `id` — unique within the file. Propagates to the resolver's output and through to per-test HANDOFF entries so a human reviewer can trace each test back to its motivating bug.
- `description` — free-text from the Fix Planner. For component scope: name caller and callee (`"<caller> → <callee>"`). For integration scope: name the entry point or feature (`"POST /auth/login expired token rejection"`). The resolver parses this; precision pays off downstream.
- `bug_ids` — IDs from the BUG_BACKLOG in Step 2e that motivated this scope entry. May be empty.
- `related_files` — files the resolver should consult first when locating the boundary / route. Hint, not a hard constraint.

Versioning: this is a contract between Bug Review (producer) and the resolvers (consumers). Adding fields is safe; renaming or removing is not. Update the resolver prompts and the Bug Review Phase 2.5 instructions together if the schema changes.

---

## Step 2c — E2E QA (if `E2E_QA=true`)

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`) to run:

```
/e2e-qa <PR_NUMBER>
```

Append:

> Return the following as the last thing in your output:
>
> ```
> HANDOFF
> VERDICT=<PASS|FAIL>
> FAILURE_REASON=<empty if PASS>
> END_HANDOFF
> ```

**Gate**: `VERDICT=FAIL` → stop. Report:

```
E2E QA failed for PR #<PR_NUMBER>. Fix the failing tests or app bugs reported by /e2e-qa,
then re-run /resolve-issue (or run /e2e-qa <PR_NUMBER> manually and then /pr-review-cycle).
PR: <PR_URL>
```

Browser/app failures implicate the full stack and do not enter the Bug Review loop.

---

## Step 2d — Suite completeness gate

Skip if `--skip-suite-check` was passed (emit a warning).

Spawn a **Suite Runner Agent** (`model: "claude-sonnet-4-6"`). Append:

> **Role:** Discover and run the project's full blocking test suite. Compare new failures to pre-existing failures.
>
> **Discovery order:**
> 1. `.github/workflows/*.yml` — find the job that runs on push/PR and extract the test command(s).
> 2. `pyproject.toml` `[tool.pytest.ini_options]` `addopts` + project default markers.
> 3. `package.json` `scripts.test`.
> 4. `Makefile` target `test` or `check`.
> 5. `.claude-resolve.toml` key `blocking_suite_command` if present (overrides all above).
>
> If none found, emit `SUCCESS=false, FAILURE_REASON=NO_SUITE_DISCOVERED`. Do not invent a command.
>
> **Run order:**
> 1. Compute a per-issue worktree path: `BASE_SUITE_DIR="<WORK_DIR>/.agent-work/base-suite-<ISSUE_NUMBER>"`. The `.agent-work/` parent is the established scratch root and avoids both relative-cwd surprises and collisions with other concurrent resolve-issue runs.
> 2. Check out `<BASE>` there: `git -C "<WORK_DIR>" worktree add "$BASE_SUITE_DIR" <BASE>`. Run the suite from `$BASE_SUITE_DIR`. Capture the set of failing test IDs as `PRE_EXISTING_FAILURES`.
> 3. From `<WORK_DIR>` on `<BRANCH>`, run the suite. Capture the set of failing test IDs as `HEAD_FAILURES`.
> 4. `NEW_FAILURES = HEAD_FAILURES \ PRE_EXISTING_FAILURES`.
> 5. Tear down the temp worktree: `git -C "<WORK_DIR>" worktree remove "$BASE_SUITE_DIR"`. If removal fails (locked, dirty), record a warning in HANDOFF notes — do not fail the gate on cleanup.
>
> **Output:**
>
> ```
> HANDOFF
> SUCCESS=<true|false>
> SUITE_COMMAND=<the command run>
> NEW_FAILURES=<comma-separated test ids, or empty>
> PRE_EXISTING_FAILURES=<comma-separated test ids, or empty>
> FAILURE_REASON=<empty | NO_SUITE_DISCOVERED | SUITE_TIMEOUT | NEW_FAILURES_DETECTED>
> END_HANDOFF
> ```
>
> Set `SUCCESS=false, FAILURE_REASON=NEW_FAILURES_DETECTED` if `NEW_FAILURES` is non-empty.

Parse.

**Gate**: `SUCCESS=false` → stop. Report `NEW_FAILURES` to the user as candidate blast-radius regressions. Pre-existing failures are noted in the Final Summary but never block.

If `--skip-suite-check`:

```
Step 2d — SKIPPED (--skip-suite-check).
WARNING: blast-radius regressions in unrelated tests will not be caught by this run.
```

---

## Step 3 — pr-review-cycle phase

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`):

```
/pr-review-cycle <WORK_DIR> <BRANCH>
```

Append:

> After presenting the Human Review Summary and posting the PR comment with the
> `<!-- review-fix-summary -->` sentinel, **stop immediately**. Do not invoke `/pr-finalize` —
> the orchestrator handles sequencing. Return:
>
> ```
> HANDOFF
> SUCCESS=<true|false>
> BLOCKERS=<"none" | brief one-line description of each blocker, semicolon-separated>
> FAILURE_REASON=<empty if SUCCESS=true, otherwise a one-line description>
> END_HANDOFF
> ```
>
> Blockers that prevent /pr-finalize:
> - Any batch failed its tests and was not committed
> - The final push failed
> - The intent validator found high-risk findings that were not resolved

**Gate**: `SUCCESS=false` or `BLOCKERS != none` → stop. Report blockers.

---

## Step 4 — pr-finalize phase

Skip if `--return-only` is set.

Spawn an Agent subagent (`model: "claude-sonnet-4-6"`):

```
/pr-finalize <BRANCH>
```

No additional instructions. Relay the terminal state (READY or BLOCKER) to the user.

---

## Final report

Present:

```
## resolve-issue complete: #<number> <title>

Phase 1 — fix-issue:           ✓ PR #<PR_NUMBER> created (<PR_URL>)
Phase 2 — assessment:          impact tool=<IMPACT_TOOL>, transitive reach=<count of TRANSITIVE_REACH> modules
Phase 2-pre — ADR gate:        <✓ present | — n/a (no shared interface hit)>
Phase 2a — component tests:    <✓ <N> tests written | — skipped (<reason>)>
Phase 2b — integration tests:  <✓ <N> tests written (wiring=<W>, artifact=<A>) | — skipped (<reason>)>
Phase 2e — bug review:         <✓ Classification <A|B|C> (<bug count> bugs) | — n/a (no non-simple bugs)>
Phase 2f — coder+tester loop:  <✓ resolved in <n> iterations | — n/a | reclassified C (<reason>)>
Phase 2g — new tests:          <✓ component=<n>, integration=<n> | — n/a>
Phase 2c — E2E QA:             <✓ PASS | — skipped (<reason>)>
Phase 2d — suite completeness: <✓ no new failures | — SKIPPED | ✗ <NEW_FAILURES>>
Phase 3 — pr-review-cycle:     ✓ <N> findings addressed, <N> cycles
Phase 4 — pr-finalize:         <READY ✓ | BLOCKER ✗ — see above | — return-only>

Branch: <BRANCH>
PR: <PR_URL>

Run commands (for reference):
  Component:  <RUN_COMMAND_COMPONENT>
  Integration (wiring):    <RUN_COMMAND_WIRING>
  Integration (artifact):  <RUN_COMMAND_ARTIFACT>
  Suite:                   <SUITE_COMMAND>

Pre-existing suite failures (informational): <PRE_EXISTING_FAILURES or "none">
```

---

## Constraints

- This orchestrator never touches files, git, or GitHub directly. Subagents do all reads, writes, runs, and posts.
- Each subagent runs in an isolated context. Do not summarize or repeat subagents' internal work beyond what is needed for the Final Summary.
- If any phase fails, stop immediately and report to the user. Do not retry automatically.
- The Assessment Agent's decisions are final unless overridden by the user's flags. Do not second-guess them in subsequent steps.
- Bug Review is the only phase that may *recover* from a failure — and only via the pre-approved Fix Planner plan, not ad-hoc.
- The Coder+Tester loop runs at most `--impl-fix-loops` iterations. There is no recursive Bug Review on tests written in Step 2g.
- Never pass `--admin` or bypass branch protection at any phase.
- `NON_SIMPLE_BUGS` from any phase is data the orchestrator routes — it is never silently dropped.
