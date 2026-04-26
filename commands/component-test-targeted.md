---
version: 1.0.0
---

# Component Test (Targeted)

## Purpose

Same goal as `/component-test`: durable boundary tests that fail when *future, unrelated* changes break wiring between modules. The difference is **how the boundary list is produced** — `/component-test-targeted` consumes a pre-supplied scope file from Bug Review (the Class B path of `/resolve-issue` Step 2g) instead of deriving boundaries from the diff.

Use this skill **only** when the Fix Planner has identified specific boundaries that need new tests. Do not invoke it for general-purpose component-test runs — use `/component-test` for those.

This skill is a thin wrapper. Most steps reference `/component-test` verbatim. The only meaningfully new step is **Boundary Resolution** (Step 2), which replaces Boundary Mapper with the lighter Boundary Resolver from a scope file.

---

## Args

`/component-test-targeted <branch> [--repo <owner/repo>] [--work-dir <path>] [--interactive] --scope-file <path>`

- `branch`: feature branch to write tests on.
- `--repo`: GitHub repo. Auto-detected from `git remote` if omitted.
- `--work-dir`: path to git working tree. Defaults to `git rev-parse --show-toplevel`.
- `--interactive`: opt-in interactive mode — prints the resolved boundary map and asks for confirmation before writing tests.
- `--scope-file <path>`: **required.** Path to the targeted scope file. JSON array of `{id, description, bug_ids, related_files}` records — see `commands/resolve-issue.md` for the schema.

`--scope-file` is the only mandatory new flag. There is no `--handoff-file` — the scope file carries everything the targeted run needs. There is no `--boundaries` flag — that interface is the previous design and is not used here.

**Default mode is automatic.** Use `--interactive` to review the resolved boundary list before writing.

---

## Inputs

The scope file alone. There is no Assessment HANDOFF — Bug Review already decided which boundaries warrant tests.

If `--scope-file` is missing or empty, emit `SUCCESS=false, FAILURE_REASON=MISSING_SCOPE_FILE` and stop.

If the scope file is present but contains zero records, emit:

```
HANDOFF
SUCCESS=true
TESTS_WRITTEN=0
TEST_FILES=
RUN_COMMAND=
SLOW_BOUNDARIES=
TEST_BOUNDARY_SUMMARY=
FAILURE_REASON=
UNRESOLVED_BOUNDARIES=
NON_SIMPLE_BUGS
END_NON_SIMPLE_BUGS
END_HANDOFF
```

and stop. An empty scope file is a valid no-op.

---

## Step 0 — Setup

Apply `/component-test` **Step 0 — Setup** verbatim, with three substitutions:

1. The TodoWrite seed entries are for Steps 0–5 of *this* skill (Boundary Resolution replaces Boundary Mapper at Step 2).
2. **Skip the "Parse Assessment HANDOFF" subsection.** This skill does not consume an Assessment HANDOFF. Read `--scope-file` instead and validate it parses as a JSON array.
3. `WORK_DIR` is `$GIT_ROOT/.agent-work/component-test-targeted-$BRANCH_SLUG` (note the `-targeted` suffix — kept distinct from regular `/component-test` work dirs to avoid colliding with a parallel run).

After Step 0: mark Step 0 done, Step 1 `in_progress`.

---

## Step 1 — Framework Discovery

Apply `/component-test` **Step 1 — Framework Discovery (orchestrator only, no subagent)** verbatim. This step is mechanical and unchanged from the regular skill — the language detection, convention scan, and marker registration logic are all identical.

After Step 1: mark Step 1 done, Step 2 `in_progress`.

---

## Step 2 — Boundary Resolution (subagent, single invocation, **new** in targeted)

Replaces `/component-test` Step 2 (Boundary Mapper).

*Delegated to:* **Boundary Resolver** subagent. Single Sonnet call. Prompt lives in [component-test/boundary-resolver-prompt.md](component-test/boundary-resolver-prompt.md).

### Inputs to the subagent

- `SCOPE_FILE` — absolute path passed via `--scope-file`
- `EXISTING_COMPONENT_TESTS` — list produced by `Grep`-ing for the marker convention from Step 1 across the test tree
- `GIT_ROOT`
- `OUTPUT_PATH` — `$WORK_DIR/boundary-map.json`

### Spawn

```
Agent({
  description: "Boundary Resolver",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: <full contents of component-test/boundary-resolver-prompt.md, with input section substituted>
})
```

### After it returns

Read `$WORK_DIR/boundary-map.json`. The output schema matches what regular Boundary Mapper produces (so Test Writers don't change), with two extra fields per entry — `bug_ids` and `source_description` — for HANDOFF traceability, plus an `unresolved[]` array.

**Do not filter by `already_covered`.** The resolver always emits `already_covered: false`. Fix Planner already considered coverage.

If `boundaries` is empty AND `unresolved` is empty: vacuous scope file. Emit:

```
HANDOFF
SUCCESS=true
TESTS_WRITTEN=0
TEST_FILES=
RUN_COMMAND=
SLOW_BOUNDARIES=
TEST_BOUNDARY_SUMMARY=
FAILURE_REASON=
UNRESOLVED_BOUNDARIES=
NON_SIMPLE_BUGS
END_NON_SIMPLE_BUGS
END_HANDOFF
```

and stop.

If `boundaries` is empty but `unresolved` is non-empty: nothing to test, but the human reviewer needs to see the unresolved list. Emit `SUCCESS=true, TESTS_WRITTEN=0` with `UNRESOLVED_BOUNDARIES` populated and stop.

### Interactive confirmation gate

Skip unless `--interactive` was passed. If `--interactive`, print:

```
[component-test-targeted] Resolved <N> boundaries from scope file (<U> unresolved):
  1. boundary-1: AuthService → TokenRotator (2 call sites, service→service) [bugs: component-test-auth-1]
  2. boundary-2: ...
Unresolved (will appear in HANDOFF for human review):
  - boundary-3: "session manager → cache" — OVERRIDE_NOT_FOUND
Proceed to write tests for the resolved boundaries? [yes / select <ids> / no]
```

`no` stops with `SUCCESS=false, FAILURE_REASON=USER_DECLINED`.

After Step 2: mark Step 2 done, Step 3 `in_progress`.

---

## Step 3 — Test Writers

Apply `/component-test` **Step 3 — Test Writers (subagents, parallel, one per boundary)** verbatim, with one addition:

**Per-writer input addition.** When constructing each writer's input record, add an optional `BUG_CONTEXT` field — the concatenation of `bug_ids` and `source_description` from the resolved boundary. The Test Writer prompt accepts this field as optional context for the test header comment. It does not change writer behavior.

Static checks, NEEDS_FIX routing, and NON_SIMPLE_BUGS construction are identical to the regular skill.

After Step 3: mark Step 3 done, Step 4 `in_progress`.

---

## Step 4 — Negative Control

Apply `/component-test` **Step 4 — Negative Control (subagents + orchestrator scaffolding)** verbatim. Sabotage Planner inputs, patch-apply-revert mechanics, and tier classification are identical.

After Step 4: mark Step 4 done, Step 5 `in_progress`.

---

## Step 5 — Suite Run and HANDOFF

Apply `/component-test` **Step 5 — Suite Run and HANDOFF** verbatim, with one addition to the HANDOFF block: include `UNRESOLVED_BOUNDARIES` from Step 2 so the orchestrator's Final Summary can surface them.

### Emit HANDOFF

```
HANDOFF
SUCCESS=<true|false>
TESTS_WRITTEN=<int>
TEST_FILES=<comma-separated forward-slash paths>
RUN_COMMAND=<command to re-run the targeted boundary tests locally>
SLOW_BOUNDARIES=<comma-separated B.id where no seam existed, or empty>
TEST_BOUNDARY_SUMMARY=<one line per boundary, semicolon-separated; include bug_ids>
FAILURE_REASON=<empty if SUCCESS=true; one of: MISSING_SCOPE_FILE | RUNNER_NOT_VERIFIED | NO_TESTS_COLLECTED | USER_DECLINED | NEGATIVE_CONTROL_UNVERIFIED:<id>>
UNRESOLVED_BOUNDARIES=<semicolon-separated "<id>: <source_description> (<reason>)" entries from boundary-map.json's unresolved[] array, or empty>
NON_SIMPLE_BUGS
BUG
BUG_ID=component-test-<boundary-id>-<n>
TEST_ID=<test identifier as reported by runner>
FAILURE_REASON=<ASSERTION_FAILURE|NEGATIVE_CONTROL_FAILED|WRONG_LAYER|SLOW_BOUNDARY_DETECTED|CALLER_MOCKED|WRITER_FAILED_STATIC|AMBIGUOUS>
RUNNER_OUTPUT=<trimmed to 30 lines>
DIAGNOSIS=<one paragraph>
END_BUG
END_NON_SIMPLE_BUGS
END_HANDOFF
```

`UNRESOLVED_BOUNDARIES` is informational — it never sets `SUCCESS=false`. The Fix Planner described a boundary the resolver couldn't locate; that's a finding for the human reading the bug report, not a hard stop.

Mark Step 5 done. Stop.

---

## Hard Rules

All Hard Rules from `/component-test` apply unchanged. Two clarifications specific to this skill:

- **The `already_covered` filter is intentionally bypassed.** Fix Planner already considered coverage. The resolver emits `already_covered_note` informationally, but never drops a record.
- **Unresolved boundaries do not set `SUCCESS=false`.** They appear in `UNRESOLVED_BOUNDARIES` for human review.

---

## Constraints

All Constraints from `/component-test` apply unchanged.

---

## Progress output

```
[component-test-targeted] Reading scope file: <path> (<N> records)
[component-test-targeted] Resolved <R> boundaries, <U> unresolved
[component-test-targeted] Writing tests for <R> boundaries (4 parallel writers)...
[component-test-targeted] Negative control on boundary-1... PASS
[component-test-targeted] Suite run: 4 passed, 0 failed
[component-test-targeted] HANDOFF: SUCCESS=true, TESTS_WRITTEN=4, UNRESOLVED=1
```
