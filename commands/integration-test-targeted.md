---
version: 1.0.0
---

# Integration Test (Targeted)

## Purpose

Same goal as `/integration-test`: durable end-to-end tests covering full feature slices against real infrastructure. The difference is **how the scenario list is produced** — `/integration-test-targeted` consumes a pre-supplied scope file from Bug Review (the Class B path of `/resolve-issue` Step 2g) instead of deriving scenarios from the implementation plan's acceptance criteria.

Use this skill **only** when the Fix Planner has identified specific scenarios that need new tests. Do not invoke it for general-purpose integration-test runs — use `/integration-test` for those. The `--update-golden` flow is **not** available here; for golden updates use the regular `/integration-test --update-golden`.

This skill is a thin wrapper. Most steps reference `/integration-test` verbatim. The only meaningfully new step is **Scenario Resolution** (Step 2), which replaces Feature Scope Agent with the lighter Scenario Resolver from a scope file.

---

## Args

`/integration-test-targeted <branch> [--repo <owner/repo>] [--work-dir <path>] [--tier wiring|artifact|both] [--interactive] --scope-file <path>`

- `branch`: feature branch to write tests on.
- `--repo`: GitHub repo. Auto-detected from `git remote` if omitted.
- `--work-dir`: path to git working tree. Defaults to `git rev-parse --show-toplevel`.
- `--tier`: which tier(s) to write. Defaults to `both`.
- `--interactive`: opt-in interactive confirmation before writing tests.
- `--scope-file <path>`: **required.** Path to the targeted scope file. JSON array of `{id, description, bug_ids, related_files}` records — see `commands/resolve-issue.md` for the schema.

There is no `--handoff-file`, no `--boundaries`, and no `--update-golden` here.

---

## Inputs

The scope file alone. There is no Assessment HANDOFF — Bug Review already decided which scenarios warrant tests.

If `--scope-file` is missing or empty, emit `SUCCESS=false, FAILURE_REASON=MISSING_SCOPE_FILE` and stop.

If the scope file contains zero records, emit:

```
HANDOFF
SUCCESS=true
TESTS_WRITTEN=0
TEST_FILES=
GOLDEN_FILES=
SCENARIOS_COVERED=
UNVERIFIABLE_SCENARIOS=
UNRESOLVED_SCENARIOS=
INFRA_NOT_AVAILABLE=false
INFRA_STRATEGY=
RUN_COMMAND_WIRING=
RUN_COMMAND_ARTIFACT=
FAILURE_REASON=
NON_SIMPLE_BUGS
END_NON_SIMPLE_BUGS
END_HANDOFF
```

and stop.

---

## Step 0 — Setup

Apply `/integration-test` **Step 0 — Setup** verbatim, with three substitutions:

1. The TodoWrite seed entries are for Steps 0–6 of *this* skill.
2. **Skip the "Parse Assessment HANDOFF" subsection.** Read `--scope-file` instead and validate it parses as a JSON array.
3. `WORK_DIR` is `$GIT_ROOT/.agent-work/integration-test-targeted-$BRANCH_SLUG` (note the `-targeted` suffix).

The "Update-golden routing" subsection does not apply — this skill rejects `--update-golden`.

After Step 0: mark Step 0 done, Step 1 `in_progress`.

---

## Step 1 — Framework + Infrastructure Discovery

Apply `/integration-test` **Step 1 — Framework + Infrastructure Discovery (orchestrator only, no subagent)** verbatim. Framework detection, infrastructure recon, and marker registration are mechanical and identical.

After Step 1: mark Step 1 done, Step 2 `in_progress`.

---

## Step 2 — Scenario Resolution (subagent, single invocation, **new** in targeted)

Replaces `/integration-test` Step 2 (Feature Scope Agent).

*Delegated to:* **Scenario Resolver** subagent. Single Sonnet call. Prompt lives in [integration-test/scenario-resolver-prompt.md](integration-test/scenario-resolver-prompt.md).

### Inputs to the subagent

- `SCOPE_FILE` — absolute path passed via `--scope-file`
- `EXISTING_INTEGRATION_TESTS` — list produced by `Grep`-ing for the marker convention from Step 1
- `GIT_ROOT`
- `OUTPUT_PATH` — `$WORK_DIR/scenario-map.json`

### Spawn

```
Agent({
  description: "Scenario Resolver",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: <full contents of integration-test/scenario-resolver-prompt.md, with input section substituted>
})
```

### Step 2b — Scenario validation (orchestrator, after Scenario Resolver returns)

Apply `/integration-test` **Step 2b — Scenario validation** verbatim. The cross-validation logic (verify each `http_entry_point` exists in the source tree, verify each `layers_involved` file exists on disk, drop `unverifiable: true` scenarios) is identical and runs against the resolver's output the same way it runs against Feature Scope Agent's output. The shared `scenario-map.json` schema is what makes this step reusable.

**Do not filter by `already_covered`.** The resolver always emits `already_covered: false`. Fix Planner already considered coverage.

If the surviving scenario list is empty AND `unresolved` is empty: emit `SUCCESS=true, TESTS_WRITTEN=0` and stop.

If empty but `unresolved` is non-empty: emit `SUCCESS=true, TESTS_WRITTEN=0` with `UNRESOLVED_SCENARIOS` populated and stop.

### Interactive confirmation gate

Skip unless `--interactive` was passed. If `--interactive`, print:

```
[integration-test-targeted] Resolved <N> scenarios from scope file (<U> unresolved):
  1. scenario-1: POST /auth/login (wiring + artifact) [bugs: integration-test-auth-3]
  2. scenario-2: ...
Unresolved (will appear in HANDOFF for human review):
  - scenario-4: "user profile bulk export" — ROUTE_NOT_FOUND
Proceed to write tests for the resolved scenarios? [yes / select <ids> / no]
```

`no` stops with `SUCCESS=false, FAILURE_REASON=USER_DECLINED`.

After Step 2: mark Step 2 done, Step 3 `in_progress`.

---

## Step 3 — Infrastructure Availability Check

Apply `/integration-test` **Step 3 — Infrastructure Availability Check** verbatim. Env-var probing, `INFRA_NOT_AVAILABLE` flag handling, and the no-Docker-spinup rule are identical.

After Step 3: mark Step 3 done, Step 4 `in_progress`.

---

## Step 4 — Test Writers

Apply `/integration-test` **Step 4 — Test Writers (subagents, parallel, one per scenario)** verbatim, with one addition:

**Per-writer input addition.** When constructing each writer's input record, add an optional `BUG_CONTEXT` field — the concatenation of `bug_ids` and `source_description` from the resolved scenario. The Test Writer prompt accepts this field as optional context. It does not change writer behavior beyond an additional comment in the test header.

Static checks, `TIER_INCOMPLETE_WIRING` routing to fix loop, and NON_SIMPLE_BUGS construction are identical.

After Step 4: mark Step 4 done, Step 5 `in_progress`.

---

## Step 5 — Falsifiability Check

Apply `/integration-test` **Step 5 — Falsifiability Check** verbatim. Wiring falsifiability (route-comment-out probe), artifact falsifiability (golden-corruption probe), and result interpretation are all identical and operate on the same per-scenario records.

After Step 5: mark Step 5 done, Step 6 `in_progress`.

---

## Step 6 — Smoke Run and HANDOFF

Apply `/integration-test` **Step 6 — Smoke Run and HANDOFF** verbatim, with one addition to the HANDOFF block: include `UNRESOLVED_SCENARIOS` from Step 2 so the orchestrator's Final Summary can surface them.

### Emit HANDOFF

```
HANDOFF
SUCCESS=<true|false>
TESTS_WRITTEN=<int>
TEST_FILES=<comma-separated forward-slash paths>
GOLDEN_FILES=<comma-separated forward-slash paths, or empty>
SCENARIOS_COVERED=<comma-separated scenario IDs>
UNVERIFIABLE_SCENARIOS=<comma-separated scenario IDs dropped in Step 2b, or empty>
UNRESOLVED_SCENARIOS=<semicolon-separated "<id>: <source_description> (<reason>)" entries from scenario-map.json's unresolved[] array, or empty>
INFRA_NOT_AVAILABLE=<true|false>
INFRA_STRATEGY=<docker-compose|testcontainers|external-env|unknown>
CI_ARTIFACT_EXCLUDED=<true|false>
RUN_COMMAND_WIRING=<command to run wiring tier locally>
RUN_COMMAND_ARTIFACT=<command to run artifact tier locally>
RUN_COMMAND_UPDATE_GOLDEN=<command to regenerate golden fixtures>
FAILURE_REASON=<empty if SUCCESS=true; one of: MISSING_SCOPE_FILE | INFRA_UNKNOWN | RUNNER_NOT_VERIFIED | NO_TESTS_COLLECTED | USER_DECLINED>
NON_SIMPLE_BUGS
BUG
BUG_ID=integration-test-<scenario-id>-<n>
TEST_ID=<test identifier as reported by runner, or empty>
FAILURE_REASON=<TIER_BLEED_WIRING|TIER_BLEED_ARTIFACT|TIER_INCOMPLETE_WIRING|SLOW_TEST_DETECTED|WRITER_FAILED_STATIC|FALSIFIABILITY_FAILED|WRONG_LAYER|NO_SEAM|HARDCODED_ID_WARNING|ASSERTION_FAILURE|AMBIGUOUS>
RUNNER_OUTPUT=<trimmed to 30 lines>
DIAGNOSIS=<one paragraph>
END_BUG
END_NON_SIMPLE_BUGS
END_HANDOFF
```

`UNRESOLVED_SCENARIOS` is informational — never sets `SUCCESS=false`.

Mark Step 6 done. Stop.

---

## Hard Rules

All Hard Rules from `/integration-test` (write flow) apply unchanged. Two clarifications specific to this skill:

- **The `already_covered` filter is intentionally bypassed.** Fix Planner already considered coverage. The resolver emits `already_covered_note` informationally, but never drops a record.
- **Unresolved scenarios do not set `SUCCESS=false`.** They appear in `UNRESOLVED_SCENARIOS` for human review.

The Update Flow's hard rules do not apply here — this skill does not implement the Update Flow.

---

## Constraints

All Constraints from `/integration-test` apply unchanged.

---

## Progress output

```
[integration-test-targeted] Reading scope file: <path> (<N> records)
[integration-test-targeted] Framework: pytest detected. Infra: docker-compose. Isolation: transaction-rollback.
[integration-test-targeted] Resolved <R> scenarios, <U> unresolved
[integration-test-targeted] Scenario validation: <V> verified, <X> unverifiable
[integration-test-targeted] Writing tests for <V> scenarios × 2 tiers...
[integration-test-targeted] Falsifiability scenario-1 (wiring): PASS
[integration-test-targeted] Smoke run (wiring tier): 2 passed, 0 failed
[integration-test-targeted] HANDOFF: SUCCESS=true, TESTS_WRITTEN=4, UNRESOLVED=1
```
