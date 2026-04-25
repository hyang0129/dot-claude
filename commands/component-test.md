---
version: 1.0.0
---

# Component Test

## Purpose

Writes durable boundary tests that fail when *future, unrelated* changes break the wiring between modules. The primary value is corpus accretion — a deposit that pays out when someone else changes nearby code months from now. The tests are not primarily a check that the current PR works.

**Tier definition (no overlap):**
- **Unit test** — one module, all collaborators doubled. Tests a *decision*.
- **Component test** — two or more real modules cooperating across one named boundary. Minimal doubles (only I/O: network, filesystem, clock). Tests a *contract*.
- **Integration test** — full vertical slice, real infrastructure, real HTTP. Tests a *flow*.

A component test that doubles a same-package collaborator is a unit test wearing a costume. A component test that spins up the full stack is an integration test. Both are rejected by Hard Rules.

**Tier:** runs alongside the unit suite on every CI push. Per-test budget < 1s. Uses the project's existing test runner with no new infrastructure.

---

## Args

`/component-test <branch> [--repo <owner/repo>] [--work-dir <path>] [--interactive] [--handoff-file <path>]`

- `branch`: feature branch to analyse and write tests for.
- `--repo`: GitHub repo. Auto-detected from `git remote` if omitted.
- `--work-dir`: path to the git working tree. Defaults to `git rev-parse --show-toplevel`.
- `--interactive`: opt-in interactive mode — prints the boundary map and asks for confirmation before writing tests.
- `--handoff-file <path>`: path to the upstream Assessment HANDOFF block. Contains `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH`, `COMPONENT_TESTS`.

**Default mode is automatic**: no prompts, proceeds directly from boundary discovery to writing tests. Use `--interactive` only when invoking manually and you want to review and trim the boundary list before anything is written.

---

## Inputs (Assessment HANDOFF)

When invoked by the orchestrator, the upstream assessment provides:

```
HANDOFF
COMPONENT_TESTS=<true|false>
IMPACT_SET=<comma-separated module paths>
DIRECT_CHANGES=<comma-separated file paths>
TRANSITIVE_REACH=<comma-separated module paths>
END_HANDOFF
```

If `COMPONENT_TESTS=false`, emit `SUCCESS=true, TESTS_WRITTEN=0` immediately and stop. Skipping is a valid outcome.

In direct mode (no `--handoff-file`), compute a degraded `IMPACT_SET` from `git diff --name-only <base>..<branch>`, leave `TRANSITIVE_REACH=<empty>`, and warn the user that boundary detection will be diff-shallow.

---

## Step 0 — Setup

**Turn 1:** initialize task tracking. Call `TodoWrite` with entries for Steps 0–5 (Step 0 `in_progress`). Loads the schema early so later updates don't trigger a cache-invalidating `ToolSearch` mid-session.

### Repo and branch

- `REPO`: from `--repo`, else `gh repo view --json nameWithOwner -q .nameWithOwner`.
- `GIT_ROOT`: from `--work-dir`, else `git rev-parse --show-toplevel`. If empty, stop and tell the user `/component-test` requires a local checkout.
- Switch to `<branch>` if not already on it: `git checkout <branch>`.
- Determine `BASE_BRANCH`: prefer `gh repo view --repo "$REPO" --json defaultBranchRef -q .defaultBranchRef.name`; fall back to `main`/`dev`.

### Scratch directory

```bash
test -d "$GIT_ROOT/.agent-work" || {
  echo ".agent-work/ not found. Run:"
  echo "  mkdir -p $GIT_ROOT/.agent-work && echo '.agent-work/' >> $GIT_ROOT/.git/info/exclude"
  exit 1
}

BRANCH_SLUG="$(echo "$branch" | tr '/' '-' | tr -cd '[:alnum:]-')"
WORK_DIR="$GIT_ROOT/.agent-work/component-test-$BRANCH_SLUG"
mkdir -p "$WORK_DIR"
```

All subagent inputs and outputs live under `$WORK_DIR`.

### Parse Assessment HANDOFF (orchestrated mode)

If `--handoff-file` was given, read it and extract `COMPONENT_TESTS`, `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH`. If `COMPONENT_TESTS=false`, emit:

```
HANDOFF
SUCCESS=true
TESTS_WRITTEN=0
TEST_FILES=
SLOW_BOUNDARIES=
TEST_BOUNDARY_SUMMARY=
FAILURE_REASON=
NON_SIMPLE_BUGS
END_NON_SIMPLE_BUGS
END_HANDOFF
```

and stop.

After Step 0: mark Step 0 done, Step 1 `in_progress`.

---

## Step 1 — Framework Discovery (orchestrator only, no subagent)

Mechanical. Walks `GIT_ROOT` for framework signals and produces `FRAMEWORK` records — one per affected language subtree. Do not delegate; this must be deterministic.

### Detection

| Language | Signals to check | Resolved fields |
|---|---|---|
| Python | `pyproject.toml [tool.pytest]`, `pytest.ini`, `setup.cfg` | `runner=pytest`, marker `component`, naming `test_*.py` |
| Node/TS | `package.json scripts.test`, `jest.config.*`, `vitest.config.*` | `runner=jest`/`vitest`, marker `describe('component:'`, naming `*.test.ts` / `*.spec.ts` |
| Go | `go.mod` | `runner=go test`, marker `//go:build component` |
| Rust | `Cargo.toml` | `runner=cargo test`, marker per existing `[features]` |
| Java/Kotlin | `build.gradle[.kts]`, `pom.xml` | `runner=gradle test`/`mvn test`, marker per existing convention |

For polyglot repos, resolve one `FRAMEWORK` per affected language subtree from `IMPACT_SET`. Each handled independently. Never invent a cross-language runner.

### Convention scan

For each `FRAMEWORK`, scan 2–3 existing test files (use `Glob` then `Read`) to infer:
- `test_dir_pattern` — where tests live relative to source (`src/__tests__/`, sibling `_test.go`, etc.)
- `naming_pattern` — file naming (`*.component.test.ts`, `test_*_component.py`, etc.)
- `marker_strategy` — actual tagging mechanism in use; if none, set `marker_strategy: "none"` and tag via filename pattern only.

Do not guess. If a project has no existing tests, set `marker_strategy: "none"` and `test_dir_pattern: "tests/"` as last resort, and surface this in `FAILURE_REASON` if Step 4 fails.

### Marker registration

For pytest: if `pyproject.toml` has `[tool.pytest.ini_options] markers` and lacks `component`, add it idempotently (check before writing). For other frameworks: do not modify config.

After Step 1: mark Step 1 done, Step 2 `in_progress`.

---

## Step 2 — Boundary Mapper (subagent, single invocation)

*Delegated to:* **Boundary Mapper** subagent. Single Sonnet call. Prompt lives in [component-test/boundary-mapper-prompt.md](component-test/boundary-mapper-prompt.md).

### Inputs to the subagent

- `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH` (from HANDOFF or Step 0 fallback)
- `EXISTING_COMPONENT_TESTS` — list produced by `Grep`-ing for the marker convention from Step 1 across the test tree
- `GIT_ROOT`
- `OUTPUT_PATH`: `$WORK_DIR/boundary-map.json`

### Spawn

```
Agent({
  description: "Boundary Mapper",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: <full contents of component-test/boundary-mapper-prompt.md, with input section substituted>
})
```

### After it returns

Read `$WORK_DIR/boundary-map.json`. Filter to entries where `already_covered: false` — these go to Step 3. If filtered count is 0 and `excluded` is empty, the change is genuinely infrastructure-only or fully covered: emit `SUCCESS=true, TESTS_WRITTEN=0` with `FAILURE_REASON=` empty and an empty `NON_SIMPLE_BUGS` block. Stop.

### Interactive confirmation gate

Skip this gate unless `--interactive` was passed. In automatic mode proceed directly to Step 3.

If `--interactive`, print:

```
[component-test] Found <N> uncovered boundaries:
  1. AuthService → TokenRepo (3 call sites, service→repository)
  2. UserService → AuthService (2 call sites, service→service)
  ...

Proceed to write tests for all of these? [yes / select <ids> / no]
```

Wait for user input. `select 1,3` writes only those. `no` stops with `SUCCESS=false, TESTS_WRITTEN=0, FAILURE_REASON=USER_DECLINED` and an empty `NON_SIMPLE_BUGS` block.

After Step 2: mark Step 2 done, Step 3 `in_progress`.

---

## Step 3 — Test Writers (subagents, parallel, one per boundary)

*Delegated to:* **Test Writer** subagents. Prompt lives in [component-test/test-writer-prompt.md](component-test/test-writer-prompt.md).

### Concurrency

Cap parallel writers at **4** to avoid runner/IDE contention. If there are more than 4 boundaries, run in batches of 4. **Do not tell writers about each other** — each writer's context is its own boundary plus the framework conventions only.

### Per-writer inputs

For each boundary `B`:
- `BOUNDARY` — the JSON entry from `boundary-map.json`
- `FRAMEWORK` — the resolved framework record for `B`'s caller language
- `EXAMPLE_TEST_PATH` — pick one existing test file from the same subtree as the caller (any non-trivial file with at least one assertion). Use the same example for all writers in the same language subtree.
- `OUTPUT_TEST_PATH` — derive from `FRAMEWORK.test_dir_pattern` + `FRAMEWORK.naming_pattern`. Example for TS+jest: `src/__tests__/<caller-dir>/<CallerClass>.component.test.ts`. **Check for collision** before passing the path: if a file already exists, append `-2`, `-3`, etc.
- `OUTPUT_RECORD_PATH` — `$WORK_DIR/writer-record-<B.id>.json`
- `GIT_ROOT`

**Critical:** writers do not see each other's outputs. They do not know a Sabotage Planner runs after them.

### Spawn (parallel)

In a single response, emit one `Agent` call per boundary in the current batch. All `model: "sonnet"`.

### After all writers return

Read each `writer-record-<B.id>.json`. Categorize:
- `slow_boundary: true` → add `B.id` to `SLOW_BOUNDARIES` list. Do not run negative control on these (no test was written).
- `error: "FILE_EXISTS"` → orchestrator-side bug; rename and re-spawn that single writer.
- Otherwise → add `(B.id, test_file)` to the active list for Step 4.

### Static checks (orchestrator, before Step 4)

For each written test file, `Grep` the file for hard prohibitions:

```bash
forbidden_patterns="time\.Sleep|asyncio\.sleep|setTimeout|fetch\(|http\.Get\(|requests\.|subprocess|exec\.Command|toBeDefined\(\)|assert\s+True\s*$"
```

Plus tautology scan:
- Python: `assert\s+(\w+)\s*==\s*\1\s*$`
- JS/TS: `expect\((\w+)\)\.toBe\(\1\)`

Plus assertion presence — at least one of: `assert`, `expect(`, `should`, `t.` (Go testing.T method), `assert_eq!`/`assert!` per language.

Triage hits as follows — do not use a single-outcome "any hit → drop" rule:

- **Tautological assertion only** (`expect(x).toBe(x)` pattern): flag the boundary as `NEEDS_FIX:<id>`. Do NOT drop it from the active list. Do NOT add a NON_SIMPLE_BUGS entry yet — this routes to the Tier 1 fix loop in Step 5a. Quarantine a copy of the file for inspection.
- **Forbidden I/O patterns** (`time.Sleep`, `asyncio.sleep`, `setTimeout`, `fetch(`, `http.Get(`, `requests.`, `subprocess`, `exec.Command`): drop from the active list, quarantine the file, and add a NON_SIMPLE_BUGS entry immediately with `FAILURE_REASON=SLOW_BOUNDARY_DETECTED`.
- **Caller mocked** (`mock(<caller>)`, `jest.mock('<caller-path>')`): drop from the active list, quarantine the file, and add a NON_SIMPLE_BUGS entry with `FAILURE_REASON=CALLER_MOCKED`.
- **No assertion present**: drop from the active list, quarantine the file, and add a NON_SIMPLE_BUGS entry with `FAILURE_REASON=WRITER_FAILED_STATIC`. (Cannot be Tier 1 because adding any assertion requires knowing the contract.)

`WRITER_FAILED:<id>` is no longer used as a FAILURE_REASON tag — these cases now live exclusively in NON_SIMPLE_BUGS.

After Step 3: mark Step 3 done, Step 4 `in_progress`.

---

## Step 4 — Negative Control (subagents + orchestrator scaffolding)

*Delegated to:* **Sabotage Planner** subagents (parallel, one per active boundary). Prompt lives in [component-test/sabotage-planner-prompt.md](component-test/sabotage-planner-prompt.md). The orchestrator (not the subagent) applies the patch, runs the suite, and reverts.

**This step is an exit condition, not a guideline.** No `SUCCESS=true` without verified negative control on every active boundary.

### 4a — Build TEST_SIGNATURE per boundary

For each active boundary, the orchestrator extracts a structural signature from the test file `Grep`-style. **Do not pass the test file directly to the Planner** — that leaks assertions.

Extract:
- Imports (lines starting with `import`, `from`, `require(`, `use`)
- The single `Act` line (the entry-point call) — heuristic: the line directly after the `[Act]` comment in the test, or the line whose left-hand side is `result =` / `let result =` / similar
- Names of fakes/substitutions (any identifier matching `Fake*`, `InMemory*`, `Stub*`, `Mock*` used in `Arrange`)

Write each `$WORK_DIR/test-signature-<B.id>.json`.

### 4b — Spawn Sabotage Planners (parallel, batches of 4)

Per-planner inputs:
- `BOUNDARY`
- `CALLEE_SOURCE_PATHS` — `BOUNDARY.callee_files`
- `TEST_SIGNATURE` — full contents of `test-signature-<B.id>.json`
- `OUTPUT_PATH` — `$WORK_DIR/sabotage-<B.id>.json`

All `model: "haiku"`. Small focused task; Haiku is sufficient and cheaper.

### 4c — Apply patch, run, revert (orchestrator, per boundary)

For each `sabotage-<B.id>.json`:

```bash
SABOTAGE_FILE="$(jq -r .patch.file "$WORK_DIR/sabotage-$BID.json")"
LINE="$(jq -r .patch.line "$WORK_DIR/sabotage-$BID.json")"
ORIGINAL="$(jq -r .patch.original "$WORK_DIR/sabotage-$BID.json")"
REPLACEMENT="$(jq -r .patch.replacement "$WORK_DIR/sabotage-$BID.json")"

cp "$SABOTAGE_FILE" "$WORK_DIR/backup-$BID-$(basename $SABOTAGE_FILE)"
trap 'cp "$WORK_DIR/backup-$BID-$(basename $SABOTAGE_FILE)" "$SABOTAGE_FILE"' EXIT INT TERM

# Apply mutation by exact-line replacement
awk -v ln="$LINE" -v rep="$REPLACEMENT" 'NR==ln{print rep; next}{print}' \
  "$SABOTAGE_FILE" > "$SABOTAGE_FILE.tmp" && mv "$SABOTAGE_FILE.tmp" "$SABOTAGE_FILE"

# Run only the new test file for this boundary
TEST_FILE="$(jq -r .test_file "$WORK_DIR/writer-record-$BID.json")"
case "$FRAMEWORK_RUNNER" in
  pytest)  pytest "$TEST_FILE" -v ;;
  jest)    npx jest "$TEST_FILE" ;;
  vitest)  npx vitest run "$TEST_FILE" ;;
  "go test") go test -tags=component "$(dirname $TEST_FILE)" -run "$(basename $TEST_FILE .go)" ;;
  "cargo test") cargo test --features component-tests --test "$(basename $TEST_FILE .rs)" ;;
esac
RUN_EXIT=$?

# Restore IMMEDIATELY, before any further logic
cp "$WORK_DIR/backup-$BID-$(basename $SABOTAGE_FILE)" "$SABOTAGE_FILE"
trap - EXIT INT TERM
```

### 4d — Interpret the result

- `RUN_EXIT != 0` AND output contains an assertion-failure signature (`AssertionError`, `Expected`, `expected`, `FAIL`) → **PASS** (the test caught the broken wiring). Record `negative_control: "verified"`. Proceed, no change.
- `RUN_EXIT != 0` but the output is a crash (`NullPointerException`, `TypeError`, `panic:`, `unwrap on None`) → **Tier 2**: mark `negative_control: "wrong-layer"`. Construct a NON_SIMPLE_BUGS entry using `sabotage-<B.id>.json`'s `rationale` field as the DIAGNOSIS basis. Do NOT drop the boundary from TESTS_WRITTEN. Do NOT set SUCCESS=false.
- `RUN_EXIT == 0` → **Tier 2**: mark `negative_control: "failed"`. Construct a NON_SIMPLE_BUGS entry using `sabotage-<B.id>.json`'s `rationale` field as the DIAGNOSIS basis. Do NOT drop the boundary from TESTS_WRITTEN. Do NOT set SUCCESS=false.
- Sabotage spec was `unverifiable: true` → **hard stop**: emit `SUCCESS=false`, `FAILURE_REASON=NEGATIVE_CONTROL_UNVERIFIED:<B.id>`.

For the `wrong-layer` and `failed` cases, the orchestrator constructs the DIAGNOSIS by combining: the sabotage rationale (what mutation was applied), the runner output (what actually happened), and a one-sentence classification (e.g. "Test failed on a crash rather than a contract assertion, indicating the test is asserting the wrong layer").

### 4e — Path-alias warning

If the test file imports via path aliases (`@/...`, `~/...`, TypeScript `paths` mappings), record a one-line note in `$WORK_DIR/notes.txt`. Aliases resolve to the original source via the runner's resolver — they are not affected by the temp-copy approach (which we do not use), so the in-place patch + restore approach is correct here.

After Step 4: mark Step 4 done, Step 5 `in_progress`.

---

## Step 5 — Suite Run and HANDOFF (orchestrator only)

Run the full new-test suite using the project's existing command (one invocation per language subtree):

```bash
case "$FRAMEWORK_RUNNER" in
  pytest)  pytest -m component "$WORK_DIR/test-files.txt" ;;
  jest)    npx jest --testNamePattern '^component:' $(cat "$WORK_DIR/test-files.txt") ;;
  ...
esac
```

Verify:
- Runner exit code 0
- `--passWithNoTests` not in effect; assert at least 1 test was collected (parse runner output for collected count). If 0 collected, emit `SUCCESS=false, FAILURE_REASON=NO_TESTS_COLLECTED`.

If the runner cannot be located on PATH, emit `SUCCESS=false, FAILURE_REASON=RUNNER_NOT_VERIFIED`. Do not emit `SUCCESS=true` if the runner did not actually execute.

### 5a — Tier 1 Fix Loop

If the suite run has any failures:

1. Spawn a **Test Fixer** subagent (prompt: `component-test/test-fixer-prompt.md`).
2. Pass it: the runner failure output, all test file paths from TEST_FILES, the FRAMEWORK record, GIT_ROOT, and the `NEEDS_FIX` list (boundary IDs flagged from tautological assertion checks in Step 3).
3. The fixer classifies each failing test as simple or non-simple, attempts fixes on simple ones (cap 2 per file), and returns a record at `$WORK_DIR/fixer-record.json`.
4. After the fixer returns, re-run the suite.
5. Collect remaining failures into NON_SIMPLE_BUGS entries using the fixer's diagnoses from `fixer-record.json`.
6. If all failures resolved: `SUCCESS=true`, `NON_SIMPLE_BUGS` empty.
7. If non-simple failures remain: `SUCCESS=true`, `NON_SIMPLE_BUGS` non-empty.
8. Hard failures (runner not found, 0 collected): `SUCCESS=false` unchanged.

Hard rule for the fixer: may not weaken assertions (no replacing specific-value assertions with `.toBeDefined()`, no removing assertions, no changing expected values). Weakening = reclassify as non-simple.

### Stage files (do not commit)

```bash
git add $(cat "$WORK_DIR/test-files.txt")
```

Leave files staged; do not commit. The calling orchestrator (or the user, if invoked directly) decides when to commit. If `--interactive`, print a summary before staging:

```
[component-test] <N> tests written, all green, negative control verified.
Staging files — commit when ready.
```

### Emit HANDOFF

```
HANDOFF
SUCCESS=<true|false>
TESTS_WRITTEN=<int>
TEST_FILES=<comma-separated forward-slash paths>
SLOW_BOUNDARIES=<comma-separated B.id where no seam existed, or empty>
TEST_BOUNDARY_SUMMARY=<one line per boundary, semicolon-separated>
FAILURE_REASON=<empty if SUCCESS=true; one of: RUNNER_NOT_VERIFIED | NO_TESTS_COLLECTED | USER_DECLINED | NEGATIVE_CONTROL_UNVERIFIED:<id>>
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

Path normalization: always forward slashes, even on Windows. Multi-line values are not supported in HANDOFF — collapse `TEST_BOUNDARY_SUMMARY` to one line, with `; ` between entries.

Mark Step 5 done. Stop.

---

## HANDOFF Schema (reference)

```
HANDOFF
SUCCESS=<true|false>
TESTS_WRITTEN=<int>
TEST_FILES=<comma-separated forward-slash paths>
SLOW_BOUNDARIES=<comma-separated B.id where no seam existed, or empty>
TEST_BOUNDARY_SUMMARY=<one line per boundary, semicolon-separated>
FAILURE_REASON=<empty if SUCCESS=true; one of: RUNNER_NOT_VERIFIED | NO_TESTS_COLLECTED | USER_DECLINED | NEGATIVE_CONTROL_UNVERIFIED:<id>>
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

- `NON_SIMPLE_BUGS` block is always present, even when empty (zero BUG entries).
- `TESTS_WRITTEN` counts all written and staged test files, including those with non-simple bugs — the test exists as a contract document.
- `FAILURE_REASON` at the top level now only contains hard-stop codes. `WRITER_FAILED`, `WRONG_LAYER`, `NEGATIVE_CONTROL_FAILED` have been moved to `NON_SIMPLE_BUGS[n].FAILURE_REASON` and no longer appear at top level.
- `TESTS_WRITTEN=0` with `SUCCESS=true` is valid when `COMPONENT_TESTS=false` or when all boundaries are already covered. Emit `FAILURE_REASON=` empty in those cases.
- A crash (no HANDOFF block at all) is distinguishable from an intentional skip (`TESTS_WRITTEN=0, SUCCESS=true`) by the orchestrator.
- Do not add `COVERAGE_DELTA` or `ASSERTIONS_PER_FILE`. The orchestrator cannot act on them and they invite gaming.

---

## Hard Rules

1. **No assertion-free tests.** Detected in Step 3 static checks → **Tier 2** (`WRITER_FAILED_STATIC`). The file is quarantined and a NON_SIMPLE_BUGS entry is emitted. Does not set `SUCCESS=false`.
2. **No tautological assertions.** Detected in Step 3 static checks → **Tier 1** candidate (`NEEDS_FIX`). Routes to the fix loop in Step 5a. Does not set `SUCCESS=false`.
3. **No tests that mock the module under test.** Detected in Step 3 static checks (`mock(<caller>)`, `jest.mock('<caller-path>')`) → **Tier 2** (`CALLER_MOCKED`). The file is quarantined and a NON_SIMPLE_BUGS entry is emitted. Does not set `SUCCESS=false`.
4. **No tests that duplicate existing component coverage.** Verified by Boundary Mapper's `already_covered` filter.
5. **Negative control must demonstrate at least one test fails on broken wiring.** Verified per-boundary in Step 4. `unverifiable` → `SUCCESS=false` (hard stop). `wrong-layer` and `failed` → Tier 2 (NON_SIMPLE_BUGS entry, not a hard stop). `SUCCESS=false` is triggered only when the sabotage spec is `unverifiable: true`.
6. **Runner must be invoked and verified.** Verified in Step 5. `SUCCESS=true` without runner invocation is a lie. Failure sets `SUCCESS=false`.

---

## Constraints

- Never write or modify source files. Test files only.
- Tests must use the project's existing framework — no new test library.
- Never commit to `main`/`master`. Stage; commit only on the feature branch.
- If blocked or uncertain about framework conventions, emit `SUCCESS=false` with a specific `FAILURE_REASON` rather than guessing.
- Subagents communicate only via `$WORK_DIR/*.json` files. No subagent receives another subagent's transcript.
- The Sabotage Planner must never receive test assertions — only the structural signature from Step 4a.

---

## Progress output

Emit one line per decision (not per activity), prefixed `[component-test]`:

```
[component-test] Discovering test surface from impact set (12 modules)...
[component-test] 3 uncovered boundaries identified: AuthService→TokenRepo, UserService→AuthService, ...
[component-test] Skipping PaymentService→Logger: infrastructure-only boundary
[component-test] Writing tests for 3 boundaries (4 parallel writers)...
[component-test] Running negative control on AuthService→TokenRepo... PASS (1 test failed as expected)
[component-test] Negative control on UserService→AuthService... PASS
[component-test] Suite run: 4 passed, 2 failed — running Tier 1 fix loop...
[component-test] Tier 1: fixed 1 test (wrong import path). 1 non-simple failure collected.
[component-test] HANDOFF: SUCCESS=true, TESTS_WRITTEN=6, NON_SIMPLE_BUGS=1
```

Skips are named explicitly. A silent skip is a bug.
