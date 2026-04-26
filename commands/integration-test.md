---
version: 1.0.0
---

# Integration Test

> **Cross-referenced by `/integration-test-targeted`.** Steps 0, 1, 2b, 3, 4, 5, and 6 of this file are referenced verbatim by `commands/integration-test-targeted.md` (the Class B / `/resolve-issue` Step 2g path). Do not rename those step headings without updating the targeted skill — references pin to step *names*. Step 2 (Feature Scope Agent) is the only step the targeted skill replaces wholesale. The `--update-golden` flow is not exposed by the targeted skill.

## Purpose

Writes durable integration tests covering full feature slices end-to-end. Tests exercise real infrastructure — real database, real HTTP stack, real message queues — and verify that the plumbing of the entire vertical slice is correct and that it produces the right output.

**Tier definition (no overlap):**
- **Unit test** — one module, all collaborators doubled. Tests a *decision*.
- **Component test** — two or more real modules cooperating across one named boundary. Minimal doubles (only I/O). Tests a *contract*.
- **Integration test** — full vertical slice, real infrastructure, real HTTP. Tests a *flow*.

Integration tests have **two tiers**, written to **separate files per scenario per tier**:

- **Wiring tier** (`@integration:wiring` or project equivalent) — verifies structural correctness: routes resolve, handlers register, DI wires up, schemas validate, the service starts and responds. Real infra for the primary collaborator (real DB), stubs for remote third-party services only. Per-test budget < 5s, suite total < 60s. **Runs on every CI push.** Assertions: status code, Content-Type, response schema structure. No exact value comparison.
- **Artifact tier** (`@integration:artifact`) — verifies output correctness against committed golden fixtures: exact response body, DB row set, emitted events. Real infra, no stubs. No tight time budget. **Runs nightly or on label.** Assertions: exact value match against committed `.golden.json` files.

Like component tests, integration tests are written for the corpus. The wiring tier's job is to fail when a future change severs a system-edge connection; the artifact tier's job is to fail when output silently corrupts. Both tiers require **falsifiability verification** — every test in the corpus must be proven to detect the failure mode it claims to cover.

**Scope:** full feature slice, exercised against real (or realistic) infrastructure. Unlike component tests, integration tests do not stub collaborators *within* the slice. Unlike E2E tests, they do not involve a browser or end-user UI interaction.

---

## Args

`/integration-test <branch> [--repo <owner/repo>] [--work-dir <path>] [--tier wiring|artifact|both] [--interactive] [--update-golden] [--scenario <id>] [--all] [--all-confirmed] [--handoff-file <path>]`

- `branch`: feature branch to analyse and write tests for.
- `--repo`: GitHub repo. Auto-detected from `git remote` if omitted.
- `--work-dir`: path to git working tree. Defaults to `git rev-parse --show-toplevel`.
- `--tier`: which tier(s) to write. Defaults to `both`.
- `--interactive`: opt-in interactive confirmation before writing tests (write flow) or per-file approval (update flow).
- `--update-golden`: switch to **Golden Update Flow** (see end of this document). Mutually exclusive with normal write flow.
- `--scenario <id>`: only used with `--update-golden`. Restrict to listed scenario IDs.
- `--all` / `--all-confirmed`: only used with `--update-golden`. See Golden Update Flow.
- `--handoff-file <path>`: path to upstream Assessment HANDOFF block.

**Default mode is non-interactive** for both flows. The safety layer is the diff classification (write flow's static checks, update flow's classification table), not a prompt.

---

## Inputs (Assessment HANDOFF)

When invoked by the resolve-issue orchestrator, the upstream assessment provides:

```
HANDOFF
INTEGRATION_TESTS=<true|false>
IMPACT_SET=<comma-separated module paths>
DIRECT_CHANGES=<comma-separated file paths>
TRANSITIVE_REACH=<comma-separated module paths>
END_HANDOFF
```

If `INTEGRATION_TESTS=false`, emit `SUCCESS=true, TESTS_WRITTEN=0` immediately and stop. Skipping is a valid outcome.

In direct mode (no `--handoff-file`), derive `IMPACT_SET` from `git diff --name-only <base>..<branch>` and warn that scenario detection will be diff-shallow.

---

## Step 0 — Setup

**Turn 1:** initialize task tracking. Call `TodoWrite` with entries for Steps 0–6 (Step 0 `in_progress`). Loads the schema early so later updates don't trigger a cache-invalidating `ToolSearch` mid-session.

### Repo and branch

- `REPO`: from `--repo`, else `gh repo view --json nameWithOwner -q .nameWithOwner`.
- `GIT_ROOT`: from `--work-dir`, else `git rev-parse --show-toplevel`. If empty, stop and tell the user `/integration-test` requires a local checkout.
- Switch to `<branch>` if not already on it: `git checkout <branch>`.
- `BASE_BRANCH`: prefer `gh repo view --repo "$REPO" --json defaultBranchRef -q .defaultBranchRef.name`; fall back to `main`/`dev`.

### Scratch directory

```bash
test -d "$GIT_ROOT/.agent-work" || {
  echo ".agent-work/ not found. Run:"
  echo "  mkdir -p $GIT_ROOT/.agent-work && echo '.agent-work/' >> $GIT_ROOT/.git/info/exclude"
  exit 1
}

BRANCH_SLUG="$(echo "$branch" | tr '/' '-' | tr -cd '[:alnum:]-')"
WORK_DIR="$GIT_ROOT/.agent-work/integration-test-$BRANCH_SLUG"
mkdir -p "$WORK_DIR"
```

All subagent inputs and outputs live under `$WORK_DIR`.

### Parse Assessment HANDOFF (orchestrated mode)

If `--handoff-file` was given, read it and extract `INTEGRATION_TESTS`, `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH`. If `INTEGRATION_TESTS=false`, emit:

```
HANDOFF
SUCCESS=true
TESTS_WRITTEN=0
TEST_FILES=
GOLDEN_FILES=
SCENARIOS_COVERED=
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

### Update-golden routing

If `--update-golden` was passed, jump to the **Golden Update Flow** at the end of this document. The write-flow steps below do not execute.

After Step 0: mark Step 0 done, Step 1 `in_progress`.

---

## Step 1 — Framework + Infrastructure Discovery (orchestrator only, no subagent)

Mechanical. Do not delegate; this must be deterministic.

### Framework detection

Walks `GIT_ROOT` for framework signals and produces `FRAMEWORK` records — one per affected language subtree.

| Language | Signals to check | Resolved fields |
|---|---|---|
| Python | `pyproject.toml [tool.pytest]`, `pytest.ini`, `setup.cfg` | `runner=pytest`, marker `integration_wiring` / `integration_artifact`, naming `test_*.py` |
| Node/TS | `package.json scripts.test`, `jest.config.*`, `vitest.config.*` | `runner=jest`/`vitest`, marker `describe('wiring:'`/`describe('artifact:'`, naming `*.test.ts` / `*.spec.ts` |
| Go | `go.mod` | `runner=go test`, marker `//go:build integration_wiring` / `//go:build integration_artifact` |
| Rust | `Cargo.toml` | `runner=cargo test`, marker per existing `[features]` |
| Java/Kotlin | `build.gradle[.kts]`, `pom.xml` | `runner=gradle test`/`mvn test`, marker per existing convention |

For polyglot repos, resolve one `FRAMEWORK` per affected language subtree from `IMPACT_SET`. Each handled independently. Never invent a cross-language runner.

For each `FRAMEWORK`, scan 2–3 existing integration test files (use `Glob` then `Read`) to infer `test_dir_pattern`, `naming_pattern`, and `marker_strategy`. If the project already uses a single-tier marker (`@pytest.mark.integration`), adopt it and use `describe(...)` / file-name suffix to distinguish wiring vs. artifact. Do not introduce a new tagging mechanism.

Generation command discovery (used in Golden Update Flow): scan an existing artifact test for a `# GOLDEN: regenerate with: ...` comment header, or default to the convention table in the Update Flow.

### Infrastructure recon

Walk `GIT_ROOT` for these signals:

| Signal | What it means |
|---|---|
| `docker-compose.yml` / `docker-compose.test.yml` | Local infrastructure available |
| `testcontainers` import in any test file | Per-test container spin-up strategy in use |
| `DATABASE_URL`, `REDIS_URL`, `AMQP_URL` in `.env.test` or `.env.example` | Required env vars |
| `tests/fixtures/`, `tests/seeds/`, `scripts/seed*.sql` | Fixture/seed mechanism |
| `pytest-django`, `pytest-asyncio`, `@nestjs/testing` | Framework-level test DB support |
| `conftest.py` with `db` / `client` / `app` fixtures | Existing integration test setup patterns |
| `--transaction` flag, `django.test.TestCase`, `pytest.mark.django_db(transaction=False)` | Transaction-rollback isolation in use |
| `.github/workflows/*.yml` with `services:` block | CI-level service containers |

Record to `$WORK_DIR/infra-recon.json`:

- `INFRA_STRATEGY`: one of `docker-compose` / `testcontainers` / `external-env` / `unknown`
- `REQUIRES_LOCAL_INFRA`: true/false
- `SEED_MECHANISM`: path to seed scripts or fixture loaders, or `none`
- `ENV_VARS_REQUIRED`: list of required environment variables
- `ISOLATION_MODEL`: one of `transaction-rollback` / `truncation` / `fixture-reload` / `unknown`
- `EXISTING_INTEGRATION_SETUP`: paths to existing `conftest.py` / test helpers
- `CI_ARTIFACT_EXCLUDED`: true/false — whether CI is confirmed to exclude artifact tier from per-push runs (scan `.github/workflows/*.yml` for marker-based filtering)

If `INFRA_STRATEGY=unknown`, emit `SUCCESS=false, FAILURE_REASON=INFRA_UNKNOWN`. Do not guess or invent infrastructure.

If `ISOLATION_MODEL=unknown`, emit a warning and proceed. Writers will use the most conservative approach (transaction-rollback) and note the assumption.

If `CI_ARTIFACT_EXCLUDED=false`, emit a warning:
```
[integration-test] WARNING: CI does not appear to exclude the artifact tier from per-push runs.
Artifact tests will run on every push. Add marker-based filtering before committing artifact tests.
```
Do not fail — surface the concern.

### Marker registration

For pytest: if `pyproject.toml` has `[tool.pytest.ini_options] markers` and lacks the integration markers in use, add them idempotently (check before writing). For other frameworks: do not modify config.

After Step 1: mark Step 1 done, Step 2 `in_progress`.

---

## Step 2 — Feature Scope Agent (subagent, single invocation)

*Delegated to:* **Feature Scope Agent** subagent. Single Sonnet call. Prompt lives in [integration-test/feature-scope-prompt.md](integration-test/feature-scope-prompt.md).

Unlike component-test's Boundary Mapper (which produces a verifiable structural map from the module call graph), the Feature Scope Agent produces a **semantic map** from acceptance criteria and user-visible behaviors. Because semantic reasoning is less reliable than structural traversal, its outputs require cross-validation against the actual diff before being passed to writers (Step 2b).

### Inputs to the subagent

- `IMPACT_SET`, `DIRECT_CHANGES` (from HANDOFF or Step 0 fallback)
- `.agent-work/ISSUE_<n>_PLAN.md` — full path; the subagent reads the acceptance criteria section
- `.agent-work/ISSUE_<n>_ADR.md` if present
- `EXISTING_INTEGRATION_TESTS` — list produced by `Grep`-ing for the marker convention from Step 1
- `GIT_ROOT`
- `OUTPUT_PATH`: `$WORK_DIR/scenario-map.json`

### Spawn

```
Agent({
  description: "Feature Scope Agent",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: <full contents of integration-test/feature-scope-prompt.md, with input section substituted>
})
```

### Step 2b — Scenario validation (orchestrator, after Feature Scope Agent returns)

The Feature Scope Agent's semantic map must be cross-checked before passing to writers. For each scenario in `scenario-map.json`:

1. **Verify each `http_entry_point` exists in the diff or in the source tree.** For each `"POST /auth/login"` entry, `Grep` the repo for a route registration matching that method + path. If not found, mark scenario `unverifiable: true`.
2. **Verify each file in `layers_involved` exists on disk.** `Glob` each module path. If not found, mark `unverifiable: true`.
3. Drop all `unverifiable: true` scenarios from the active list. Record them in `$WORK_DIR/unverifiable-scenarios.txt` for the HANDOFF.

Filter the surviving list to `already_covered: false` entries — these go to Step 4. If filtered count is 0, the change is genuinely covered or has no integration-level surface: emit `SUCCESS=true, TESTS_WRITTEN=0` with empty `FAILURE_REASON` and an empty `NON_SIMPLE_BUGS` block. Stop.

### Interactive confirmation gate

Skip this gate unless `--interactive` was passed. In automatic mode proceed directly to Step 3.

If `--interactive`, print:

```
[integration-test] Found <N> uncovered scenarios:
  1. slice-auth-login (POST /auth/login) — wiring + artifact
  2. slice-user-profile (GET /users/:id) — wiring only (volatile output)
  ...

Proceed to write tests for all of these? [yes / select <ids> / no]
```

Wait for user input. `select 1,3` writes only those. `no` stops with `SUCCESS=false, TESTS_WRITTEN=0, FAILURE_REASON=USER_DECLINED` and an empty `NON_SIMPLE_BUGS` block.

After Step 2: mark Step 2 done, Step 3 `in_progress`.

---

## Step 3 — Infrastructure Availability Check (orchestrator)

Before spawning writers, verify infra is reachable (if possible), and check required env vars.

```bash
MISSING_VARS=""
for VAR in $ENV_VARS_REQUIRED; do
  if [ -z "${!VAR}" ]; then
    MISSING_VARS="$MISSING_VARS $VAR"
  fi
done

if [ -n "$MISSING_VARS" ]; then
  echo "[integration-test] INFO: Required env vars not set:$MISSING_VARS"
  echo "[integration-test] Tests will be written but smoke run will be skipped (INFRA_NOT_AVAILABLE=true)"
  INFRA_NOT_AVAILABLE=true
else
  INFRA_NOT_AVAILABLE=false
fi
```

Do not start Docker containers. Do not block on missing infra. Record `INFRA_NOT_AVAILABLE` for Step 6.

After Step 3: mark Step 3 done, Step 4 `in_progress`.

---

## Step 4 — Test Writers (subagents, parallel, one per scenario)

*Delegated to:* **Integration Test Writer** subagents. Prompt lives in [integration-test/test-writer-prompt.md](integration-test/test-writer-prompt.md).

### Concurrency

Cap parallel writers at **4** to avoid runner/IDE contention. If there are more than 4 scenarios, run in batches of 4. **Do not tell writers about each other** — each writer's context is its own scenario plus the framework + infra recon only.

### Per-writer inputs

For each scenario `S`:
- `SCENARIO` — the JSON entry from `scenario-map.json` (post-validation)
- `FRAMEWORK` — the resolved framework record for `S`'s primary language
- `INFRA_RECON` — the full `infra-recon.json`
- `EXAMPLE_INTEGRATION_TEST_PATH` — pick one existing integration test from the same subtree as the entry point (or `null` if none exist)
- `OUTPUT_WIRING_PATH` — derived from `FRAMEWORK.test_dir_pattern` + naming pattern. Example for TS+jest: `tests/integration/<S.id>.wiring.test.ts`. **Check for collision** before passing — if a file exists, append `-2`, `-3`, etc.
- `OUTPUT_ARTIFACT_PATH` — same convention with `.artifact.test.<ext>`. Set to `null` if `S.volatile_output: true` (no golden generated).
- `OUTPUT_RECORD_PATH` — `$WORK_DIR/writer-record-<S.id>.json`
- `GIT_ROOT`

**Critical:** writers do not see each other's outputs. They do not know a falsifiability check runs after them.

### Spawn (parallel)

In a single response, emit one `Agent` call per scenario in the current batch. All `model: "sonnet"`.

### After all writers return

Read each `writer-record-<S.id>.json`. Categorize:
- `error: "FILE_EXISTS"` → orchestrator-side bug; rename and re-spawn that single writer.
- `skipped: true` → add to NON_SIMPLE_BUGS with `FAILURE_REASON=NO_SEAM` (writer reported no usable test-client entry point).
- Otherwise → add `(S.id, wiring_file, artifact_file)` to the active list for Step 5.

### Static checks (orchestrator, before Step 5)

For each written file, validate:

**Assertion presence** — at least one of `assert`, `expect(`, `should`, `t.` per language. No assertion → `WRITER_FAILED_STATIC`. Quarantine the file (move to `$WORK_DIR/quarantine/`) and add a NON_SIMPLE_BUGS entry.

**Positive wiring assertions** — wiring files must contain at least one status code assertion AND one schema/type assertion. A wiring test that only checks `status == 200` is `TIER_INCOMPLETE_WIRING` → route to fix loop in Step 6a.

**Positive artifact assertions** — artifact files must reference a golden fixture path (substring match for `.golden.json` or framework-specific snapshot helper). An artifact test that only checks status codes is `TIER_BLEED_ARTIFACT` → quarantine, NON_SIMPLE_BUGS.

**Tier separation** — wiring file must NOT reference any `.golden.json` path; artifact file MUST reference one (unless `volatile_output`). Mixed-tier file is a writer bug → quarantine, NON_SIMPLE_BUGS with `FAILURE_REASON=TIER_BLEED_WIRING`.

**Long sleeps** — grep for `time\.Sleep|asyncio\.sleep|setTimeout` with numeric argument > 1000 (ms) or > 1 (s). `SLOW_TEST_DETECTED` → quarantine, NON_SIMPLE_BUGS.

**Hard-coded IDs** — grep for patterns like `id: 1`, `/users/1`, `WHERE id = 1` in test bodies. Flag as `HARDCODED_ID_WARNING` — not fatal, record in HANDOFF as a NON_SIMPLE_BUGS entry.

After Step 4: mark Step 4 done, Step 5 `in_progress`.

---

## Step 5 — Falsifiability Check (orchestrator, per scenario)

**This step is an exit condition, not a guideline.** Component-test's negative control verified that tests detect broken wiring via code mutation. Integration tests require an analogous check, but the mutation targets infrastructure boundaries, not source code.

For each active scenario `S`, run two probes (one per tier file written).

### 5a — Wiring falsifiability

Identify the route registration line for `S.http_entry_points[0]` in the source tree. Apply a minimal in-place patch that comments out the registration; run only the wiring test for `S`; revert immediately.

```bash
ROUTE_FILE="<file containing route registration>"
ROUTE_LINE="<line number of registration>"

cp "$ROUTE_FILE" "$WORK_DIR/backup-route-$S.id.bak"
trap 'cp "$WORK_DIR/backup-route-$S.id.bak" "$ROUTE_FILE"' EXIT INT TERM

# Comment out the registration
awk -v ln="$ROUTE_LINE" '{ if (NR==ln) print "// SABOTAGED: " $0; else print }' \
  "$ROUTE_FILE" > "$ROUTE_FILE.tmp" && mv "$ROUTE_FILE.tmp" "$ROUTE_FILE"

# Run only the wiring test for this scenario
case "$FRAMEWORK_RUNNER" in
  pytest)  pytest "$OUTPUT_WIRING_PATH" -v ;;
  jest)    npx jest "$OUTPUT_WIRING_PATH" ;;
  vitest)  npx vitest run "$OUTPUT_WIRING_PATH" ;;
  ...
esac
RUN_EXIT=$?

# Restore IMMEDIATELY
cp "$WORK_DIR/backup-route-$S.id.bak" "$ROUTE_FILE"
trap - EXIT INT TERM
```

Acceptance criterion: wiring test must fail with a non-success status (404, 503, connection refused) — not a crash. A test that times out is `WRONG_LAYER`. A test that continues to pass is `FALSIFIABILITY_FAILED`.

If no route registration line can be identified, mark `falsifiability: "no-seam"` — record in NON_SIMPLE_BUGS with `FAILURE_REASON=NO_SEAM`. Do not set `SUCCESS=false`.

### 5b — Artifact falsifiability

If the scenario has an artifact file, corrupt one field in the generated golden fixture; run the artifact test; revert.

```bash
GOLDEN_FILE="$WORK_DIR/golden/$S.id.golden.json"
cp "$GOLDEN_FILE" "$WORK_DIR/backup-golden-$S.id.bak"
trap 'cp "$WORK_DIR/backup-golden-$S.id.bak" "$GOLDEN_FILE"' EXIT INT TERM

# Mutate one leaf value: pick the first string field and prepend "CORRUPTED-"
# Use jq for JSON mutation
jq '.[(keys[0])] = "CORRUPTED-" + (.[(keys[0])] | tostring)' "$GOLDEN_FILE" \
  > "$GOLDEN_FILE.tmp" && mv "$GOLDEN_FILE.tmp" "$GOLDEN_FILE"

# Run the artifact test
case "$FRAMEWORK_RUNNER" in
  pytest)  pytest "$OUTPUT_ARTIFACT_PATH" -v ;;
  jest)    npx jest "$OUTPUT_ARTIFACT_PATH" ;;
  ...
esac
RUN_EXIT=$?

cp "$WORK_DIR/backup-golden-$S.id.bak" "$GOLDEN_FILE"
trap - EXIT INT TERM
```

Acceptance criterion: artifact test must fail with a value-mismatch assertion error. A passing test against a corrupted golden is `FALSIFIABILITY_FAILED`.

### 5c — Interpret results

- **PASS** (test fails with expected error: non-200 for wiring, value mismatch for artifact) → record `falsifiability: "verified"`. Proceed.
- **WRONG_LAYER** (test fails with crash / exception / timeout) → NON_SIMPLE_BUGS entry with `FAILURE_REASON=WRONG_LAYER`. Test is asserting the wrong boundary. Do NOT drop from TESTS_WRITTEN.
- **FALSIFIABILITY_FAILED** (test passes against broken wiring or corrupted golden) → NON_SIMPLE_BUGS entry with `FAILURE_REASON=FALSIFIABILITY_FAILED`. Critical — the test cannot detect the failure it claims to cover. Do NOT set `SUCCESS=false` at the top level (the test file is still a contract document), but it MUST appear in NON_SIMPLE_BUGS.
- **NO_SEAM** (no route line found / no golden generated) → NON_SIMPLE_BUGS entry with `FAILURE_REASON=NO_SEAM`.

If `INFRA_NOT_AVAILABLE=true`, skip Step 5 entirely — record `falsifiability: "skipped-no-infra"` for each scenario in HANDOFF notes. The check cannot run without infra.

After Step 5: mark Step 5 done, Step 6 `in_progress`.

---

## Step 6 — Smoke Run and HANDOFF (orchestrator only)

### Wiring smoke run

Run the wiring tier only. Apply a 120s timeout to prevent indefinite hanging on missing containers.

```bash
timeout 120 \
  pytest -m "integration_wiring" $(cat "$WORK_DIR/test-files-wiring.txt") -v 2>&1 \
  | tee "$WORK_DIR/smoke-run.log"
RUN_EXIT=$?

if [ $RUN_EXIT -eq 124 ]; then
  echo "[integration-test] Smoke run timed out after 120s — infrastructure likely unavailable"
  INFRA_NOT_AVAILABLE=true
  RUN_EXIT=0
fi

# Connection error heuristic
if grep -qE 'ConnectionRefused|ECONNREFUSED|could not connect|Unable to connect' "$WORK_DIR/smoke-run.log"; then
  INFRA_NOT_AVAILABLE=true
  RUN_EXIT=0
fi
```

Verify (when smoke run did execute):
- Runner exit code 0
- `--passWithNoTests` not in effect; assert at least 1 test was collected. If 0, emit `SUCCESS=false, FAILURE_REASON=NO_TESTS_COLLECTED`.

If the runner cannot be located on PATH, emit `SUCCESS=false, FAILURE_REASON=RUNNER_NOT_VERIFIED`.

If `INFRA_NOT_AVAILABLE=true` (from Step 3 env check or this step's timeout/connection heuristic): emit a warning, leave files staged, and set `SUCCESS=true` with `INFRA_NOT_AVAILABLE=true` in HANDOFF.

### 6a — Tier 1 Fix Loop

If the smoke run has any failures NOT classified as infra:

1. Spawn a **Test Fixer** subagent (prompt: [integration-test/test-fixer-prompt.md](integration-test/test-fixer-prompt.md)).
2. Pass it: the runner failure output, all wiring test file paths, the FRAMEWORK record, GIT_ROOT, and the `NEEDS_FIX` list (scenario IDs flagged from `TIER_INCOMPLETE_WIRING` checks in Step 4).
3. Fixer classifies failures, attempts mechanical fixes (cap 2 per file), and returns a record at `$WORK_DIR/fixer-record.json`.
4. Re-run the wiring smoke. Collect remaining failures into NON_SIMPLE_BUGS using the fixer's diagnoses.
5. If all failures resolved: `SUCCESS=true`, NON_SIMPLE_BUGS appended only with non-fix-loop entries.
6. If non-simple failures remain: `SUCCESS=true`, NON_SIMPLE_BUGS non-empty.
7. Hard failures (runner not found, 0 collected): `SUCCESS=false` unchanged.

Hard rule for the fixer: may not weaken assertions (no replacing exact-value checks with `.toBeDefined()`, no removing assertions, no changing expected values). Weakening = reclassify as non-simple.

### Golden fixture staging

If artifact tests were written, the writers placed generated goldens at `$WORK_DIR/golden/<S.id>.golden.json`. Move them to the committed location:

```bash
mkdir -p "$GIT_ROOT/tests/integration/golden"
cp "$WORK_DIR/golden/"*.json "$GIT_ROOT/tests/integration/golden/" 2>/dev/null || true
git add "$GIT_ROOT/tests/integration/golden/" 2>/dev/null || true
```

Golden fixtures are committed alongside the tests. Do not generate from live production data. If `volatile_output: true`, no golden file is generated.

### Stage test files (do not commit)

```bash
git add $(cat "$WORK_DIR/test-files.txt")
```

Leave files staged; do not commit. The calling orchestrator (or the user, if invoked directly) decides when to commit. If `--interactive`, print a summary before staging:

```
[integration-test] <N> tests written, wiring smoke green, falsifiability verified.
Staging files — commit when ready.
```

### Emit HANDOFF

```
HANDOFF
SUCCESS=<true|false>
TESTS_WRITTEN=<int>
TEST_FILES=<comma-separated forward-slash paths>
GOLDEN_FILES=<comma-separated forward-slash paths, or empty>
SCENARIOS_COVERED=<comma-separated scenario IDs>
UNVERIFIABLE_SCENARIOS=<comma-separated scenario IDs dropped in Step 2b, or empty>
INFRA_NOT_AVAILABLE=<true|false>
INFRA_STRATEGY=<docker-compose|testcontainers|external-env|unknown>
CI_ARTIFACT_EXCLUDED=<true|false>
RUN_COMMAND_WIRING=<command to run wiring tier locally>
RUN_COMMAND_ARTIFACT=<command to run artifact tier locally>
RUN_COMMAND_UPDATE_GOLDEN=<command to regenerate golden fixtures>
FAILURE_REASON=<empty if SUCCESS=true; one of: INFRA_UNKNOWN | RUNNER_NOT_VERIFIED | NO_TESTS_COLLECTED | USER_DECLINED>
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

Path normalization: always forward slashes, even on Windows. Multi-line values are not supported in HANDOFF.

Mark Step 6 done. Stop.

---

## Hard Rules (write flow)

1. **No assertion-free tests.** Detected in Step 4 static checks → `WRITER_FAILED_STATIC`. Quarantined, NON_SIMPLE_BUGS.
2. **No tier bleed.** Wiring tests must contain schema assertions, not exact-value golden comparisons. Artifact tests must reference a committed golden fixture, not only check status codes. Detected in Step 4.
3. **Tiers in separate files.** A file mixing wiring and artifact test cases is a writer bug → `TIER_BLEED_WIRING`, quarantine.
4. **No hard-coded row IDs.** Seed rows; capture generated IDs. `HARDCODED_ID_WARNING` recorded but not fatal.
5. **No long sleeps.** `SLOW_TEST_DETECTED` → quarantine, NON_SIMPLE_BUGS.
6. **Falsifiability must be verified.** `FALSIFIABILITY_FAILED` → NON_SIMPLE_BUGS. Does not set `SUCCESS=false` directly, but must appear in HANDOFF. `INFRA_NOT_AVAILABLE=true` exempts the check (recorded as `falsifiability: "skipped-no-infra"`).
7. **No volatile-output artifact tests.** `volatile_output: true` scenarios get wiring tests only.
8. **Never modify source files.** If no seam exists, flag `NO_SEAM`, not a source edit.
9. **Runner must be invoked (wiring tier).** Exception: `INFRA_NOT_AVAILABLE=true`. Smoke timeout or connection error → set flag, proceed.
10. **No tests that duplicate existing integration coverage.** Verified by Feature Scope Agent's `already_covered` filter + Step 2b validation.

---

## Constraints

- Integration tests must be tagged so artifact tier does not run on every CI push.
- Tests run against real infrastructure. Do not introduce new fakes for infrastructure collaborators — use what the project already has, or stop with `INFRA_UNKNOWN`.
- Never commit to `main`/`master`. Stage; commit only on the feature branch.
- Golden fixtures are committed alongside tests. Do not generate from live production data.
- Subagents communicate only via `$WORK_DIR/*.json` files. No subagent receives another subagent's transcript.
- Writers must not share state assumptions. Each scenario's test file must be independently executable.

---

## Progress output

Emit one line per decision, prefixed `[integration-test]`:

```
[integration-test] Framework: pytest detected (Python). Wiring marker: @pytest.mark.integration_wiring
[integration-test] Infrastructure: docker-compose detected. Isolation: transaction-rollback.
[integration-test] CI artifact exclusion: confirmed
[integration-test] Feature scope: 4 scenarios from plan, 3 uncovered (1 already covered by auth_test.py)
[integration-test] Scenario validation: 3 verified, 0 unverifiable
[integration-test] Infra check: DATABASE_URL set. Proceeding with smoke run.
[integration-test] Writing tests: 3 scenarios × 2 tiers = 6 files (4 parallel writers)...
[integration-test] Falsifiability slice-auth-login (wiring): PASS (test failed on missing route)
[integration-test] Falsifiability slice-auth-login (artifact): PASS (test failed on corrupted golden)
[integration-test] Falsifiability slice-user-profile (wiring): NO_SEAM — route binding not isolatable
[integration-test] Smoke run (wiring tier): 3 passed, 0 failed
[integration-test] HANDOFF: SUCCESS=true, TESTS_WRITTEN=6, GOLDEN_FILES=2, NON_SIMPLE_BUGS=1
```

Skips are named explicitly. A silent skip is a bug.

---

## Golden Update Flow (`--update-golden`)

A separate mode for **regenerating committed golden fixtures** when an intentional behavior change has legitimately altered output.

```
/integration-test <branch> --update-golden [--scenario <id>[,<id>...]] [--all] [--all-confirmed] [--interactive]
```

This mode does **not** write new test files, does **not** call the Feature Scope Agent, and does **not** spawn writers. It runs only the committed artifact tests in generation mode, normalizes the output, classifies the diffs, and stages updates.

### When NOT to use

- A test is failing and you are not sure whether the implementation or the golden is at fault. Resolve the cause first.
- Goldens are flaking due to non-determinism. Fix normalization or mark scenario `volatile_output: true` in the writer; do not paper over with regeneration.
- "Just to be safe" after a refactor. Refactors should not change observable output. If they do, the goldens will fail in CI and you'll see exactly what changed.

### Pre-flight gates (hard requirements)

1. **Working tree clean.** `git status --porcelain` returns empty. Refuse with `FAILURE_REASON=DIRTY_WORKING_TREE` otherwise.
2. **Branch is not `main`/`master`.** Refuse with `FAILURE_REASON=ON_PROTECTED_BRANCH`.
3. **Infrastructure available.** Hard-fails on missing infra: `FAILURE_REASON=INFRA_REQUIRED_FOR_UPDATE`.
4. **Wiring tier green for in-scope scenarios.** Run wiring tests for in-scope scenarios first. If any fail, refuse with `FAILURE_REASON=WIRING_FAILED:<scenario-ids>`.

### Step U1 — Scope selection

1. **`--scenario <id>` provided:** in-scope = listed scenarios. Verify each ID corresponds to a committed artifact test file. Unknown → `FAILURE_REASON=UNKNOWN_SCENARIO:<id>`.
2. **Default (no flag):** in-scope = scenarios whose artifact test file OR `layers_involved` modules appear in `git diff --name-only <BASE>..HEAD`. Recover `layers_involved` by parsing the `# SCENARIO:` comment header in each artifact test file.
3. **`--all`:** in-scope = every committed artifact test in the repo.
   - `--all` alone (non-interactive default): refuse with `FAILURE_REASON=ALL_REQUIRES_CONFIRMATION`.
   - `--all --interactive`: prompt for confirmation.
   - `--all --all-confirmed`: proceed without prompting (intended for orchestrated flows).

Write the in-scope list to `$WORK_DIR/update-scope.txt` (one scenario ID per line).

### Step U2 — Generation

For each in-scope scenario, run its artifact test in **generation mode**, sequentially (no parallel regeneration — DB-state pollution risk). Use the project's convention:

| Framework | Generation invocation |
|---|---|
| pytest + syrupy/snapshot | `pytest --snapshot-update tests/integration/<id>.artifact.test.py` |
| pytest (custom golden) | `GOLDEN_UPDATE=1 pytest tests/integration/<id>.artifact.test.py` |
| Jest | `npx jest --updateSnapshot tests/integration/<id>.artifact.test.ts` |
| Vitest | `npx vitest run -u tests/integration/<id>.artifact.test.ts` |
| Go | `go test -update ./tests/integration/...` |
| Custom | Read from the test's `# GOLDEN: regenerate with: <command>` header. Refuse to guess. |

For each generation:

```bash
# Capture original
cp "tests/integration/golden/<id>.golden.json" "$WORK_DIR/golden-original-<id>.json"

# Run with timeout
timeout 60 <generation_command> 2>&1 | tee "$WORK_DIR/generate-<id>.log"
GEN_EXIT=$?

# Capture generated and revert in place (Step U5 decides whether to keep)
cp "tests/integration/golden/<id>.golden.json" "$WORK_DIR/golden-generated-<id>.json"
cp "$WORK_DIR/golden-original-<id>.json" "tests/integration/golden/<id>.golden.json"
```

Rationale for revert: leaves the working tree in its original state until Step U5 explicitly approves a change. Ctrl-C mid-flow does not leak un-reviewed updates.

If generation exits non-zero or times out, mark scenario `GENERATION_FAILED` and skip to next.

### Step U3 — Normalization

Generated output may contain non-deterministic fields (timestamps, UUIDs, request IDs). Normalize before diffing.

For each generated golden:

1. **Read scenario rules** from `tests/integration/golden/<id>.normalize.json` if present:
   ```json
   {
     "strip_paths": ["$.metadata.request_id", "$.timestamps[*].generated_at"],
     "replace_paths": {"$.created_at": "<TIMESTAMP>"}
   }
   ```
2. **Default normalization** if no rules file:
   - ISO 8601 timestamps within last 24h → `<TIMESTAMP>`
   - UUIDv4 patterns → `<UUID>`
   - Fields named `request_id`, `trace_id`, `correlation_id` → `<ID>`
   - Surface a warning that defaults were applied.
3. **Stability hash:** run generation twice, normalize both, hash both. Differing hashes → `FAILURE_REASON=NON_DETERMINISTIC:<id>`. Recommend marking the scenario `volatile_output: true` (which would convert it to wiring-only on next write).

Write normalized output to `$WORK_DIR/golden-normalized-<id>.json`.

### Step U4 — Diff classification

For each scenario, diff `$WORK_DIR/golden-normalized-<id>.json` against the committed `tests/integration/golden/<id>.golden.json`.

| Class | Definition | Default action (non-interactive) | With `--interactive` |
|---|---|---|---|
| `UNCHANGED` | No structural or value differences after normalization. | No action. | No action. |
| `VALUE_CHANGED` | Same structure; one or more leaf values differ. | Stage. | Prompt. |
| `FIELD_ADDED` | New keys present in generated; structure compatible. | Stage. | Prompt. |
| `FIELD_REMOVED` | Keys absent in generated. | `REVIEW_REQUIRED` (not staged). | Prompt. |
| `STRUCTURE_CHANGED` | Type changed (string→array, etc.). | `REVIEW_REQUIRED` (not staged). | Prompt. |
| `NEW_GOLDEN` | No committed golden exists. | Stage. | Prompt. |
| `GENERATION_FAILED` | Step U2 exited non-zero or U3 detected non-determinism. | Drop. Record in HANDOFF. | Drop. Record in HANDOFF. |

Write the classification to `$WORK_DIR/update-classifications.json`.

`FIELD_REMOVED` and `STRUCTURE_CHANGED` never auto-stage in any mode — there is no flag that bypasses this. The safety layer is the classification, not the prompt.

### Step U5 — Review and stage

**Default (non-interactive):**

Apply per-class default actions. Print one summary line per scenario:

```
[integration-test] slice-auth-login: VALUE_CHANGED → staged
[integration-test] slice-user-profile: FIELD_REMOVED → REVIEW_REQUIRED (not staged)
```

**With `--interactive`:**

For each scenario in any non-`UNCHANGED` class, print the diff and prompt:

```
[integration-test] slice-auth-login: VALUE_CHANGED
  $.user.last_login: "2026-04-25T10:00:00Z" → "2026-04-25T11:30:00Z"
  $.session.expires_in: 3600 → 7200

  Update this golden? [yes / no / show-full-diff / quit]
```

`quit` is atomic — nothing decided so far is staged. `FAILURE_REASON=USER_QUIT`.

**Stage approved updates:**

```bash
for id in $APPROVED_IDS; do
  cp "$WORK_DIR/golden-normalized-$id.json" "tests/integration/golden/$id.golden.json"
  git add "tests/integration/golden/$id.golden.json"
done
```

Do not commit. The user (or orchestrator) commits, ideally as `chore(test): update golden fixtures for <reason>`.

### HANDOFF schema (update mode)

```
HANDOFF
MODE=update-golden
SUCCESS=<true|false>
SCENARIOS_IN_SCOPE=<int>
GOLDENS_UPDATED=<comma-separated scenario IDs whose goldens were staged>
GOLDENS_UNCHANGED=<comma-separated scenario IDs with no diff after normalization>
GOLDENS_REVIEW_REQUIRED=<comma-separated scenario IDs with FIELD_REMOVED or STRUCTURE_CHANGED, not staged>
GENERATION_FAILED=<comma-separated scenario IDs where generation crashed or non-determinism was detected>
FAILURE_REASON=<empty if SUCCESS=true; one of: INFRA_REQUIRED_FOR_UPDATE | WIRING_FAILED:<ids> | UNKNOWN_SCENARIO:<id> | DIRTY_WORKING_TREE | ON_PROTECTED_BRANCH | USER_QUIT | ALL_REQUIRES_CONFIRMATION>
NON_SIMPLE_BUGS
BUG
BUG_ID=update-golden-<scenario-id>-<n>
FAILURE_REASON=<NON_DETERMINISTIC|GENERATION_TIMEOUT|GENERATION_CRASHED|REVIEW_REQUIRED>
DIAGNOSIS=<one paragraph>
END_BUG
END_NON_SIMPLE_BUGS
END_HANDOFF
```

`SUCCESS=true` is valid even when some scenarios are in `GOLDENS_REVIEW_REQUIRED` — the flow ran correctly; the user re-runs interactively to approve held-back changes. `SUCCESS=true` with `GOLDENS_UPDATED=` empty and `GOLDENS_UNCHANGED=` populated is the "everything's already in sync" no-op.

### Hard Rules (update mode)

1. **Working tree clean before generation.** No exceptions.
2. **Wiring tier green for in-scope scenarios.** Generating against broken implementation is forbidden.
3. **Goldens reverted in place after generation.** Step U5 stages only what's explicitly approved (or auto-staged per classification).
4. **`FIELD_REMOVED` and `STRUCTURE_CHANGED` never auto-stage.** Always `REVIEW_REQUIRED` in non-interactive; always prompt in interactive.
5. **Sequential generation only.** No parallel regeneration across scenarios.
6. **Non-deterministic scenarios surfaced, not silently regenerated.** Stability-hash failure → loud fail.
7. **No new test files.** Update mode regenerates fixtures only.

### Interaction with the resolve-issue orchestrator

Update mode is **not** invoked automatically by `/resolve-issue`. Golden updates should be a deliberate decision tied to an intentional behavior change, not a side effect of `/resolve-issue` running on a branch. If a write-flow falsifiability check or smoke run fails because committed goldens are stale, the failure is the correct signal — surfacing it in `NON_SIMPLE_BUGS` lets the human decide whether to regenerate or revert.
