# `/integration-test` Skill Spec — Draft v0.2

> Revised after challenger review. Key changes from v0.1: integration-specific falsifiability check replaces dropped Sabotage Planner; scenario validation step added; separate files per tier (not two blocks); golden fixture lifecycle model; DB isolation contract; CI tier-exclusion verification; infrastructure lifecycle ownership.

---

## Purpose

Writes durable integration tests covering full feature slices end-to-end. Tests exercise real infrastructure — real database, real HTTP stack, real message queues — and verify that the plumbing of the entire vertical slice is correct and that it produces the right output.

Two tiers with no overlap, written to **separate files per tier**:

- **Wiring tier** (`@integration:wiring`) — verifies structural correctness: routes resolve, handlers register, DI wires up, schemas validate, the service starts and responds. Real infra for the primary collaborator (real DB), stubs for remote third-party services only. Time budget per test < 5s, suite total < 60s. **Runs on every CI push.** Assertions: status code, Content-Type, response schema structure. No exact value comparison.
- **Artifact tier** (`@integration:artifact`) — verifies output correctness against committed golden fixtures: exact response body, DB row set, emitted events. Real infra, no stubs. No tight time budget. **Runs nightly or on label.** Assertions: exact value match against committed `.golden.json` files.

Both tiers are written in the same skill invocation in **separate files per scenario per tier**, so either tier can run in isolation without triggering the other's setup cost. Tagging is enforced via the project's existing mechanism (pytest markers, Jest projects, Go build tags).

Like component tests, integration tests are written for the corpus. The wiring tier's job is to fail when a future change severs a system-edge connection; the artifact tier's job is to fail when output silently corrupts. Both tiers require **falsifiability verification** — every test in the corpus must be proven to detect the failure mode it claims to cover.

**Scope:** full feature slice, exercised against real (or realistic) infrastructure. Unlike component tests, integration tests do not stub collaborators *within* the slice. Unlike E2E tests, they do not involve a browser or end-user UI interaction.

---

## Args

`/integration-test <branch> [--repo <owner/repo>] [--work-dir <path>] [--tier wiring|artifact|both] [--interactive] [--update-golden] [--handoff-file <path>]`

- `branch`: feature branch to analyse and write tests for.
- `--repo`: GitHub repo. Auto-detected from `git remote` if omitted.
- `--work-dir`: path to git working tree. Defaults to `git rev-parse --show-toplevel`.
- `--tier`: which tier(s) to write. Defaults to `both`.
- `--interactive`: print scenario map and confirm before writing tests.
- `--update-golden`: regenerate golden fixtures for existing artifact tests from the current implementation's output. Does not write new tests. Separate mode — if passed, skip to Golden Update Flow.
- `--handoff-file <path>`: path to the upstream Assessment HANDOFF block.

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

**Note:** The Feature Scope Agent derives scenarios from `ISSUE_<n>_PLAN.md` directly — the Assessment HANDOFF does not need to supply pre-enumerated feature slices. The HANDOFF supplies structural signals (`IMPACT_SET`, `DIRECT_CHANGES`); semantic scenario extraction is the Feature Scope Agent's job.

In direct mode (no `--handoff-file`), derive `IMPACT_SET` from `git diff --name-only <base>..<branch>` and warn that slice detection will be diff-shallow.

---

## Step 0 — Setup

**Turn 1:** initialize task tracking. Call `TodoWrite` with entries for Steps 0–6 (Step 0 `in_progress`).

### Repo and branch

- `REPO`: from `--repo`, else `gh repo view --json nameWithOwner -q .nameWithOwner`.
- `GIT_ROOT`: from `--work-dir`, else `git rev-parse --show-toplevel`.
- Switch to `<branch>`: `git checkout <branch>`.
- `BASE_BRANCH`: prefer `gh repo view --repo "$REPO" --json defaultBranchRef -q .defaultBranchRef.name`; fall back to `main`.

### Scratch directory

```bash
BRANCH_SLUG="$(echo "$branch" | tr '/' '-' | tr -cd '[:alnum:]-')"
WORK_DIR="$GIT_ROOT/.agent-work/integration-test-$BRANCH_SLUG"
mkdir -p "$WORK_DIR"
```

All subagent inputs and outputs live under `$WORK_DIR`.

After Step 0: mark Step 0 done, Step 1 `in_progress`.

---

## Step 1 — Framework + Infrastructure Discovery (orchestrator only)

Mechanical. Two tasks: detect the test framework and detect available test infrastructure.

### Framework detection

Same logic as `/component-test` Step 1. Produce `FRAMEWORK` records per affected language subtree.

Additionally scan for integration-specific marker conventions: existing `@integration:wiring` / `@integration:artifact` markers (or project equivalents). If a different convention is already in use (e.g. `@pytest.mark.integration`, Jest `testPathPattern=integration`), adopt it — do not introduce a new tagging scheme.

### Infrastructure recon

Walk `GIT_ROOT` for signals:

| Signal | What it means |
|---|---|
| `docker-compose.yml` / `docker-compose.test.yml` | Local infrastructure available |
| `testcontainers` import in any test file | Per-test container spin-up strategy in use |
| `DATABASE_URL`, `REDIS_URL`, `AMQP_URL` in `.env.test` or `.env.example` | Required env vars |
| `tests/fixtures/`, `tests/seeds/`, `scripts/seed*.sql` | Fixture/seed mechanism |
| `pytest-django`, `pytest-asyncio`, `@nestjs/testing` | Framework-level test DB support |
| `conftest.py` with `db` / `client` / `app` fixtures | Existing integration test setup patterns |
| `--transaction` or `django.test.TestCase` | Transaction-rollback isolation in use |
| `.github/workflows/*.yml` with `services:` block | CI-level service containers |

Record:
- `INFRA_STRATEGY`: one of `docker-compose` / `testcontainers` / `external-env` / `unknown`
- `REQUIRES_LOCAL_INFRA`: true/false
- `SEED_MECHANISM`: path to seed scripts or fixture loaders, or `none`
- `ENV_VARS_REQUIRED`: list of required environment variables
- `ISOLATION_MODEL`: one of `transaction-rollback` / `truncation` / `fixture-reload` / `unknown` — how existing integration tests achieve test isolation
- `EXISTING_INTEGRATION_SETUP`: paths to existing conftest.py / test helpers
- `CI_ARTIFACT_EXCLUDED`: true/false — whether CI is confirmed to exclude the artifact tier from per-push runs (scan `.github/workflows/*.yml` for marker-based filtering)

Write to `$WORK_DIR/infra-recon.json`.

**CI tier-exclusion check:** If `CI_ARTIFACT_EXCLUDED=false`, emit a warning line:

```
[integration-test] WARNING: CI does not appear to exclude the artifact tier from per-push runs.
Artifact tests will run on every push. Add marker-based filtering before committing artifact tests.
```

Do not fail here — some projects intentionally run everything. Surface the concern.

If `INFRA_STRATEGY=unknown`, emit `SUCCESS=false, FAILURE_REASON=INFRA_UNKNOWN`. Do not guess or invent infrastructure.

If `ISOLATION_MODEL=unknown`, emit a warning and proceed. Writers will use the most conservative approach (transaction-rollback) and note the assumption.

After Step 1: mark Step 1 done, Step 2 `in_progress`.

---

## Step 2 — Feature Scope Agent (subagent, single invocation)

*Delegated to:* **Feature Scope Agent**. Single Sonnet call.

Unlike the Boundary Mapper (which produces a verifiable structural map from the module call graph), the Feature Scope Agent produces a **semantic map** from acceptance criteria and user-visible behaviors. Because semantic reasoning is less reliable than structural traversal, its outputs require cross-validation against the actual diff before being passed to writers (Step 2b).

### Inputs to the subagent

- `IMPACT_SET`, `DIRECT_CHANGES` from HANDOFF
- `.agent-work/ISSUE_<n>_PLAN.md` — full file (acceptance criteria section drives scenario extraction)
- `.agent-work/ISSUE_<n>_ADR.md` if present
- `GIT_ROOT`
- `EXISTING_INTEGRATION_TESTS` — list produced by grepping for integration markers across the test tree
- `OUTPUT_PATH`: `$WORK_DIR/scenario-map.json`

### Output schema

```json
[
  {
    "id": "slice-auth-login",
    "description": "User logs in with valid credentials via POST /auth/login",
    "acceptance_criterion": "Returns 200 with JWT, sets session cookie",
    "http_entry_points": ["POST /auth/login"],
    "layers_involved": ["AuthController", "AuthService", "UserRepository", "SessionStore"],
    "already_covered": false,
    "tier": ["wiring", "artifact"],
    "golden_fixture_candidate": true,
    "volatile_output": false
  }
]
```

`volatile_output: true` means the scenario's output changes on every run (e.g. includes a timestamp, generated ID, or server-assigned nonce). Volatile scenarios are written as wiring-only — no artifact golden is generated for them.

### Ranking signals (priority order)

1. Acceptance criteria from `ISSUE_<n>_PLAN.md` — each AC is a candidate scenario
2. New HTTP routes or message queue consumers added in the diff
3. New service entry points (public methods called from outside the slice)
4. Scenarios already covered by existing integration tests (`already_covered: true`)

Filter to `already_covered: false` entries before Step 2b. If 0 uncovered scenarios, emit `SUCCESS=true, TESTS_WRITTEN=0` and stop.

### Step 2b — Scenario validation (orchestrator, after Feature Scope Agent returns)

The Feature Scope Agent's semantic map must be cross-checked before passing to writers. For each scenario in `scenario-map.json`:

1. **Verify each `http_entry_point` exists in the diff.** For each `"POST /auth/login"` in `http_entry_points`, grep the diff for a route registration matching that method + path. If not found, mark scenario `unverifiable: true`.
2. **Verify each file in `layers_involved` exists on disk.** Glob each module path. If not found, mark `unverifiable: true`.
3. Drop all `unverifiable: true` scenarios from the active list. Record them in `$WORK_DIR/unverifiable-scenarios.txt` for the HANDOFF.

This step has no equivalent in component-test because the Boundary Mapper's outputs are inherently verifiable. Integration scenarios require explicit validation because the Feature Scope Agent reasons about intent.

After Step 2: mark Step 2 done, Step 3 `in_progress`.

---

## Step 3 — Infrastructure Availability Check (orchestrator)

Before spawning writers, verify infra is reachable (if possible), and check required env vars.

```bash
# Check required env vars
for VAR in $ENV_VARS_REQUIRED; do
  if [ -z "${!VAR}" ]; then
    MISSING_VARS="$MISSING_VARS $VAR"
  fi
done

if [ -n "$MISSING_VARS" ]; then
  echo "[integration-test] INFO: Required env vars not set: $MISSING_VARS"
  echo "[integration-test] Tests will be written but smoke run will be skipped (INFRA_NOT_AVAILABLE=true)"
  INFRA_NOT_AVAILABLE=true
fi
```

Do not start Docker containers. Do not block on missing infra. Record `INFRA_NOT_AVAILABLE` for Step 5.

After Step 3: mark Step 3 done, Step 4 `in_progress`.

---

## Step 4 — Test Writers (subagents, parallel, one per scenario)

*Delegated to:* **Integration Test Writer** subagents. Prompt lives in `integration-test/test-writer-prompt.md`.

### Key decisions

**Separate files per tier.** Each writer produces two files: `<scenario-id>.wiring.test.<ext>` and `<scenario-id>.artifact.test.<ext>` (unless `volatile_output: true`, in which case only the wiring file). Keeping tiers in separate files prevents artifact-tier setup code from executing during wiring-tier runs, preserving the wiring tier's time budget.

**DB isolation contract per writer.** Each writer is told the project's `ISOLATION_MODEL` and must follow it strictly:
- `transaction-rollback`: wrap all DB mutations in a transaction, roll back in teardown. Every test starts with clean state.
- `truncation`: truncate all tables touched by the scenario before and after the test. List affected tables in a comment at the top of the file.
- `fixture-reload`: call the project's existing fixture-reload helper before and after.

Writers must not assume specific integer IDs for seeded rows. If a scenario's assertions depend on a specific ID (e.g. `GET /users/1`), the writer must seed the row and capture the generated ID, not hard-code `1`.

### Concurrency

Cap parallel writers at **4**. For more than 4 scenarios, run in batches. Writers see `INFRA_RECON` and `SCENARIO` but never other writers' outputs.

### Per-writer inputs

For each scenario `S`:
- `SCENARIO` — the JSON entry from `scenario-map.json` (post-validation)
- `FRAMEWORK` — the resolved framework record
- `INFRA_RECON` — the full `infra-recon.json`
- `EXAMPLE_INTEGRATION_TEST_PATH` — one existing integration test from the same subtree (or null if none)
- `OUTPUT_WIRING_PATH` — `tests/integration/<scenario-id>.wiring.test.<ext>`. Check for collision.
- `OUTPUT_ARTIFACT_PATH` — `tests/integration/<scenario-id>.artifact.test.<ext>`. Null if `volatile_output: true`.
- `OUTPUT_RECORD_PATH` — `$WORK_DIR/writer-record-<S.id>.json`
- `GIT_ROOT`

### Test anatomy — wiring file

```
[Setup]    Seed minimum state via project's fixture/seed mechanism.
           Capture generated IDs — do not hard-code row IDs.

[Act]      Issue one HTTP request (or one queue message) via the test HTTP client.
           Do not call service methods directly.

[Assert]   Assert status code is in expected range (200, 201, etc.)
           Assert Content-Type header.
           Assert response body matches schema structure (field presence, types, not exact values).
           Assert no unhandled exception in server logs (if log capture is available).

[Teardown] Roll back / truncate / reload per ISOLATION_MODEL.
           Do not rely on GC or test ordering.
```

### Test anatomy — artifact file

```
[Setup]    Same as wiring setup. Seed with deterministic data (fixed strings, fixed dates).
           All seeded values must appear in the golden fixture.

[Act]      Same HTTP request as wiring file. Do not share Act code between files — they run
           independently.

[Assert]   Assert response body exactly matches golden fixture at
           tests/integration/golden/<scenario-id>.golden.json.
           Assert DB rows exactly match golden fixture at
           tests/integration/golden/<scenario-id>.db.golden.json (if applicable).
           Assert emitted events exactly match golden fixture (if applicable).

[Teardown] Same as wiring teardown.

[Golden generation note] Include a comment at the top:
# GOLDEN: regenerate with: /integration-test <branch> --update-golden
```

### Static checks (orchestrator, before Step 5)

For each written file, validate:

**Assertion presence:** at least one of `assert`, `expect(`, `should`, `t.` per language. No assertion → `WRITER_FAILED_STATIC`. Quarantine and record in NON_SIMPLE_BUGS.

**Positive wiring assertions:** wiring files must contain at least one status code assertion AND one schema/type assertion. A wiring test that only checks `status == 200` is `TIER_INCOMPLETE_WIRING`. Route to fix loop.

**Positive artifact assertions:** artifact files must reference a golden fixture path. An artifact test that only checks status codes is `TIER_BLEED_ARTIFACT`. Record in NON_SIMPLE_BUGS.

**Long sleeps:** grep for `time\.Sleep|asyncio\.sleep|setTimeout` with argument `> 1000` (ms) or `> 1` (s). `SLOW_TEST_DETECTED` → quarantine, NON_SIMPLE_BUGS.

**Hard-coded IDs:** grep for patterns like `id: 1`, `/users/1`, `WHERE id = 1` in the test bodies. Flag as `HARDCODED_ID_WARNING` — not fatal, but record in HANDOFF notes.

After Step 4: mark Step 4 done, Step 5 `in_progress`.

---

## Step 5 — Falsifiability Check (orchestrator)

**This step is an exit condition, not a guideline.** The component-test spec's negative control verified that tests detect broken wiring via code mutation. Integration tests require an analogous check, but the mutation model must target infrastructure boundaries, not source code.

Integration tests hit real infrastructure, so breaking the implementation code would require a source change — that's the job of a different test type. Instead, integration falsifiability is verified by **removing or breaking the infrastructure binding** that the test exercises.

For each active scenario `S`, run the following falsifiability probe:

### 5a — Wiring falsifiability

Temporarily break the route registration or DI binding:

```bash
# Strategy: rename the route or remove it, run the wiring test, confirm 404/connection-error
# This is a READ-ONLY check for most web frameworks:
# - Express/Fastify: comment out the router.register() line in the diff
# - FastAPI/Django: comment out the URL pattern line
# - NestJS: remove the @Controller decorator temporarily
# Applied via the same patch/revert mechanism as component-test Step 4c:
SABOTAGE_FILE="<route registration file>"
# Apply minimal patch: comment out the route registration line
# Run the wiring test
# Assert the test FAILS with a non-200 status (404, 503, connection refused)
# Revert IMMEDIATELY
```

Acceptance criterion: wiring test must fail with a meaningful non-success response, not with a framework crash. A test that times out is `WRONG_LAYER` (it's not checking the route boundary). A test that continues to pass is `FALSIFIABILITY_FAILED`.

If no route registration line can be identified from the diff for this scenario, mark `falsifiability: "no-seam"` — record in NON_SIMPLE_BUGS, do not set `SUCCESS=false`.

### 5b — Artifact falsifiability

Corrupt one field in the golden fixture, run the artifact test, confirm it fails:

```bash
# Apply a one-field mutation to the golden JSON:
# - Change a string value: "user@example.com" → "corrupted@example.com"
# - Change a number: 42 → 999
# Run the artifact test
# Assert the test FAILS with an assertion mismatch (not a crash)
# Revert golden fixture IMMEDIATELY
```

Acceptance criterion: artifact test must fail with a value-mismatch assertion error. A test that passes against a corrupted golden is `FALSIFIABILITY_FAILED`.

### 5c — Interpret results

- Test fails with expected error (non-200 for wiring, value mismatch for artifact) → **PASS**. Record `falsifiability: "verified"`.
- Test fails with a crash / exception → **NON_SIMPLE_BUGS** with `FAILURE_REASON=WRONG_LAYER`. Test is asserting the wrong boundary. Do not drop from TESTS_WRITTEN.
- Test passes against broken wiring/corrupted golden → **NON_SIMPLE_BUGS** with `FAILURE_REASON=FALSIFIABILITY_FAILED`. Critical — the test cannot detect the failure it claims to cover.
- No seam found (`no-seam`) → **NON_SIMPLE_BUGS** with `FAILURE_REASON=NO_SEAM`. Test written and staged but unverified.

`FALSIFIABILITY_FAILED` does NOT set `SUCCESS=false` at the top level — the test file is still a contract document. But it must appear in NON_SIMPLE_BUGS.

After Step 5: mark Step 5 done, Step 6 `in_progress`.

---

## Step 6 — Smoke Run and HANDOFF (orchestrator)

### Infrastructure timeout model

Run the wiring tier only. Apply a **timeout** to the runner invocation to prevent indefinite hanging when containers fail to start:

```bash
timeout 120 \
  pytest -m "integration and wiring" $(cat "$WORK_DIR/test-files-wiring.txt") -v 2>&1 \
  | tee "$WORK_DIR/smoke-run.log"
RUN_EXIT=$?

if [ $RUN_EXIT -eq 124 ]; then
  echo "[integration-test] Smoke run timed out after 120s — infrastructure likely unavailable"
  INFRA_NOT_AVAILABLE=true
  RUN_EXIT=0  # timeout is not a test failure
fi
```

If `INFRA_NOT_AVAILABLE=true` (from Step 3 env check or Step 6 timeout), skip the smoke run, emit a warning, and set `SUCCESS=true` with `INFRA_NOT_AVAILABLE=true` in HANDOFF.

**Connection error heuristic:** if runner output contains `ConnectionRefused`, `ECONNREFUSED`, `OperationalError: could not connect`, `Unable to connect to server`, treat as `INFRA_NOT_AVAILABLE=true` and proceed.

### 6a — Tier 1 Fix Loop

On failures that are NOT infra-related (import errors, syntax errors, wrong fixture path, assertion errors): spawn a **Test Fixer** subagent. Pass the failure output, all test file paths, FRAMEWORK record. Cap 2 fixes per file. Fixer may not weaken assertions.

### Golden fixture staging

If artifact tests were written:

```bash
mkdir -p "$GIT_ROOT/tests/integration/golden"
# Copy generated golden fixtures to the committed location
cp "$WORK_DIR/golden/"*.json "$GIT_ROOT/tests/integration/golden/"
git add "$GIT_ROOT/tests/integration/golden/"
```

Golden fixtures are committed alongside the tests. They represent the contract. Do not generate golden fixtures from live production data. If `volatile_output: true`, no golden file is generated.

### Stage files (do not commit)

```bash
git add $(cat "$WORK_DIR/test-files.txt")
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
FAILURE_REASON=<empty if SUCCESS=true; one of: INFRA_UNKNOWN | INFRA_ENV_MISSING:<vars> | RUNNER_NOT_VERIFIED | NO_TESTS_COLLECTED>
NON_SIMPLE_BUGS
BUG
BUG_ID=integration-test-<scenario-id>-<n>
FAILURE_REASON=<TIER_BLEED_ARTIFACT|TIER_INCOMPLETE_WIRING|SLOW_TEST_DETECTED|WRITER_FAILED_STATIC|FALSIFIABILITY_FAILED|WRONG_LAYER|NO_SEAM|HARDCODED_ID_WARNING>
DIAGNOSIS=<one paragraph>
END_BUG
END_NON_SIMPLE_BUGS
END_HANDOFF
```

Mark Step 6 done. Stop.

---

## Golden Update Flow (`--update-golden`)

A separate mode for **regenerating committed golden fixtures** when an intentional behavior change has legitimately altered output. Invoked as:

```
/integration-test <branch> --update-golden [--scenario <id>[,<id>...]] [--all] [--interactive]
```

- `--scenario <id>`: regenerate goldens only for the listed scenario IDs. Repeatable / comma-separated.
- `--all`: regenerate every committed golden in the repo, regardless of branch impact. Dangerous — see Step U1.
- `--interactive`: opt into per-file approval prompts. Without this flag, the flow runs non-interactively and stages all changes that pass classification (subject to the always-review classes — see Step U5).

**Default mode is non-interactive** to match the write flow's default and to make `--update-golden` safely usable from orchestrated contexts. The safety layer is not the prompt — it is the diff classification (Step U4): `FIELD_REMOVED` and `STRUCTURE_CHANGED` are recorded as `REVIEW_REQUIRED` and never auto-staged regardless of mode.

This mode does **not** write new test files, does **not** call the Feature Scope Agent, and does **not** spawn writers. It runs only the committed artifact tests in generation mode, normalizes the output, classifies the diffs, and stages updates.

### When to use

- A schema addition added a new field to a response, and the golden must include it.
- A locale change altered date or currency formatting.
- A computed field's algorithm changed and the new value is the intended output.
- A bugfix corrected a value that the golden had previously locked in as wrong.

### When NOT to use

- A test is failing and you are not sure whether the implementation or the golden is at fault. Resolve the cause first; never use `--update-golden` to make a red test green without understanding why output changed.
- Goldens are flaking due to non-determinism (timestamps, generated IDs leaking through). Fix the test's normalization or mark the scenario `volatile_output: true` in the writer; do not paper over with regeneration.
- You want to regenerate after a refactor "just to be safe." Refactors should not change observable output. If they do, the goldens will fail in CI and you will see exactly what changed — that signal is the point.

### Pre-flight gates (hard requirements)

Update mode has stricter pre-flight requirements than the write flow because it modifies committed contracts.

1. **Working tree must be clean.** `git status --porcelain` returns empty. Refuse to run with uncommitted changes — too easy to conflate intentional golden updates with stray edits.
2. **Branch must not be `main` / `master`.** Updates land on a feature branch only.
3. **Infrastructure must be available.** Unlike the write flow's `INFRA_NOT_AVAILABLE` fallback, update mode hard-fails on missing infra. Generation requires running tests against real infrastructure. If env vars are missing or the smoke probe (Step U2's pre-check) fails, emit `SUCCESS=false, FAILURE_REASON=INFRA_REQUIRED_FOR_UPDATE`.
4. **Wiring tier must be green for the in-scope scenarios.** Run wiring tests for the in-scope scenarios first. If any wiring test fails, the implementation is broken — do not regenerate goldens against a broken implementation. Emit `SUCCESS=false, FAILURE_REASON=WIRING_FAILED:<scenario-ids>`.

### Step U1 — Scope selection

Determines which goldens are in scope. Three modes, in order of preference:

1. **`--scenario <id>` provided:** in-scope = exactly the listed scenarios. Verify each ID corresponds to a committed artifact test file (`tests/integration/<id>.artifact.test.<ext>`). Unknown IDs → hard fail with `FAILURE_REASON=UNKNOWN_SCENARIO:<id>`.

2. **Default (no flag):** in-scope = scenarios whose artifact test file OR whose `layers_involved` modules appear in `git diff --name-only <BASE>..HEAD`. Computed by:
   - For each artifact test file under `tests/integration/`, parse the `# SCENARIO:` comment header to recover the scenario's `layers_involved`.
   - Mark the test in-scope if either the test file itself or any layer module is in the diff.
   - This is the safe default: it limits regeneration to scenarios the branch could plausibly affect.

3. **`--all`:** in-scope = every committed artifact test in the repo. Because `--all` masks unintended output changes from unrelated scenarios, it requires an explicit confirmation flag regardless of interactive mode:

   - `--all` alone (non-interactive default): refuse with `FAILURE_REASON=ALL_REQUIRES_CONFIRMATION`. The user must add either `--interactive` (to confirm at the prompt) or `--all-confirmed` (to acknowledge the risk explicitly in scripted use).
   - `--all --interactive`: print a warning and prompt:

     ```
     [integration-test] --all will regenerate <N> golden fixtures across <M> scenarios.
     This will mask any unintended output changes from unrelated scenarios.
     Proceed? [yes / no]
     ```

   - `--all --all-confirmed`: proceed without prompting. Intended for orchestrated flows where the caller has already gated on the decision.

   This is a deliberate friction layer — `--all` is the dangerous mode and the default non-interactive behavior must not silently accept it.

Write the in-scope list to `$WORK_DIR/update-scope.txt` (one scenario ID per line).

### Step U2 — Generation

For each in-scope scenario, run its artifact test in **generation mode**. The mechanism is framework-specific; record it in `infra-recon.json`'s framework record:

| Framework | Generation invocation |
|---|---|
| pytest + syrupy/snapshot | `pytest --snapshot-update tests/integration/<id>.artifact.test.py` |
| pytest (custom golden) | `GOLDEN_UPDATE=1 pytest tests/integration/<id>.artifact.test.py` |
| Jest | `npx jest --updateSnapshot tests/integration/<id>.artifact.test.ts` |
| Vitest | `npx vitest run -u tests/integration/<id>.artifact.test.ts` |
| Go | `go test -update ./tests/integration/...` (project must support `-update` flag) |
| Custom | Read the convention from an existing artifact test's comment header (`# GOLDEN: regenerate with: <command>`). Refuse to guess. |

Run **one scenario at a time**, sequentially. Parallel regeneration risks DB-state pollution between scenarios that the test isolation model would normally prevent at single-test scope but not across runs.

For each generation:

```bash
timeout 60 <generation_command> 2>&1 | tee "$WORK_DIR/generate-<id>.log"
GEN_EXIT=$?

case $GEN_EXIT in
  0)   ;;  # success, proceed to normalization
  124) echo "[integration-test] Generation timed out for <id>"; mark FAILED ;;
  *)   echo "[integration-test] Generation failed for <id> (exit $GEN_EXIT)"; mark FAILED ;;
esac
```

Generated goldens land at the path the test references (e.g. `tests/integration/golden/<id>.golden.json`). Generation mode **overwrites in place** — capture the original first:

```bash
cp "tests/integration/golden/<id>.golden.json" "$WORK_DIR/golden-original-<id>.json"
# then run generation
cp "tests/integration/golden/<id>.golden.json" "$WORK_DIR/golden-generated-<id>.json"
# revert the in-place file until Step U5 decides whether to keep the change
cp "$WORK_DIR/golden-original-<id>.json" "tests/integration/golden/<id>.golden.json"
```

Rationale: the user has not yet approved the change. Leaving the regenerated file in place before review means a Ctrl-C mid-flow leaves the working tree dirty with un-reviewed updates.

### Step U3 — Normalization

Generated output frequently contains fields that are non-deterministic across runs even within "deterministic" tests: server-assigned timestamps, request IDs, ISO datetimes for "now", connection IDs in error responses. These will cause the regenerated golden to differ from the committed golden on every run, defeating the point of regeneration.

For each generated golden, apply normalization:

1. **Read the scenario's normalization rules** from a committed `tests/integration/golden/<id>.normalize.json` if present. Schema:

   ```json
   {
     "strip_paths": ["$.metadata.request_id", "$.timestamps[*].generated_at"],
     "replace_paths": {"$.created_at": "<TIMESTAMP>"}
   }
   ```

2. **Default normalization** if no rules file exists: detect and replace common volatile patterns:
   - ISO 8601 timestamps within the last 24 hours → `<TIMESTAMP>`
   - UUIDv4 patterns → `<UUID>`
   - Fields named `request_id`, `trace_id`, `correlation_id` → `<ID>`
   - Surface a warning so the maintainer knows defaults were applied.

3. **Compute a stability hash:** run generation twice, normalize both, hash both. If hashes differ, the scenario has volatility that escapes normalization — emit `FAILURE_REASON=NON_DETERMINISTIC:<id>`, recommend marking the scenario `volatile_output: true` (which would convert it to wiring-only on next write).

Write the normalized output to `$WORK_DIR/golden-normalized-<id>.json`.

### Step U4 — Diff classification

For each scenario, diff `$WORK_DIR/golden-normalized-<id>.json` against `tests/integration/golden/<id>.golden.json` (the committed file). Classify each diff:

| Class | Definition | Default action (non-interactive) | With `--interactive` |
|---|---|---|---|
| `UNCHANGED` | No structural or value differences after normalization. | No action. | No action. |
| `VALUE_CHANGED` | Same JSON structure; one or more leaf values differ. | Stage. | Prompt. |
| `FIELD_ADDED` | New keys present in generated; structure otherwise compatible. | Stage. | Prompt. |
| `FIELD_REMOVED` | Keys present in committed but absent in generated. | `REVIEW_REQUIRED` (not staged). | Prompt. |
| `STRUCTURE_CHANGED` | Type changed (string→array, object→string, etc.). | `REVIEW_REQUIRED` (not staged). | Prompt. |
| `NEW_GOLDEN` | No committed golden exists; this is a first-time generation. | Stage. | Prompt. |
| `GENERATION_FAILED` | Step U2 exited non-zero or U3 detected non-determinism. | Drop. Record in HANDOFF. | Drop. Record in HANDOFF. |

Write the classification to `$WORK_DIR/update-classifications.json`:

```json
[
  {"id": "slice-auth-login", "class": "VALUE_CHANGED", "diff_summary": "1 field changed: $.user.last_login"},
  {"id": "slice-user-profile", "class": "FIELD_REMOVED", "diff_summary": "removed $.user.legacy_role"},
  ...
]
```

### Step U5 — Review and stage

**Default (non-interactive):**

Apply the per-class default action from the Step U4 table:
- `VALUE_CHANGED`, `FIELD_ADDED`, `NEW_GOLDEN` → stage immediately.
- `FIELD_REMOVED`, `STRUCTURE_CHANGED` → recorded as `REVIEW_REQUIRED` in HANDOFF, NOT staged.

Print one summary line per scenario as decisions are made:

```
[integration-test] slice-auth-login: VALUE_CHANGED → staged
[integration-test] slice-user-profile: FIELD_REMOVED → REVIEW_REQUIRED (not staged)
```

The user (or orchestrator) re-runs with `--interactive --scenario slice-user-profile` to review the held-back changes.

**With `--interactive`:**

For each scenario in any non-`UNCHANGED` class, print the diff and prompt:

```
[integration-test] slice-auth-login: VALUE_CHANGED
  $.user.last_login: "2026-04-25T10:00:00Z" → "2026-04-25T11:30:00Z"
  $.session.expires_in: 3600 → 7200

  Update this golden? [yes / no / show-full-diff / quit]
```

`yes` → copy normalized to committed location, stage. `no` → leave committed file untouched. `quit` → stop the flow; do not stage anything decided so far (atomic — all or nothing per session).

**Always-review classes (cannot be auto-staged):**
- `FIELD_REMOVED` — too easy to silently delete a contract field.
- `STRUCTURE_CHANGED` — too easy to break downstream consumers.

These two classes never auto-stage, regardless of mode. In non-interactive runs they go to `REVIEW_REQUIRED`; in interactive runs they prompt with no auto-yes shortcut.

**Stage:**

```bash
for id in $APPROVED_IDS; do
  cp "$WORK_DIR/golden-normalized-$id.json" "tests/integration/golden/$id.golden.json"
  git add "tests/integration/golden/$id.golden.json"
done
```

Do not commit. The user (or orchestrator) decides when to commit, ideally in a dedicated commit titled `chore(test): update golden fixtures for <reason>`.

### HANDOFF schema for update mode

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

`SUCCESS=true` is valid even when some scenarios are in `GOLDENS_REVIEW_REQUIRED` — the flow ran correctly; the user simply needs to re-run interactively to approve those changes.

`SUCCESS=true` with `GOLDENS_UPDATED=` empty and `GOLDENS_UNCHANGED=` populated is the "everything's already in sync" outcome. Equivalent to a no-op.

### Failure modes and recovery

| Failure | Cause | Recovery |
|---|---|---|
| `INFRA_REQUIRED_FOR_UPDATE` | DB / queue unreachable | Start infra, re-run. Update mode cannot fall back to an in-memory mode. |
| `WIRING_FAILED:<ids>` | Implementation broken for in-scope scenarios | Fix the implementation first. Goldens cannot be regenerated against a broken slice. |
| `NON_DETERMINISTIC:<id>` | Output volatile even after normalization | Add normalization rules to `<id>.normalize.json`, or mark scenario `volatile_output: true` and re-run `/integration-test` write flow to convert to wiring-only. |
| `GENERATION_TIMEOUT` | 60s per-scenario cap exceeded | Slice is too slow for golden regeneration. Investigate seed data size; reduce or split the scenario. |
| `DIRTY_WORKING_TREE` | Uncommitted changes present | Commit or stash, re-run. |
| `USER_QUIT` | User chose `quit` in interactive review | Nothing staged. Safe to re-run. |

### Interaction with the resolve-issue orchestrator

Update mode is **not** invoked automatically by `/resolve-issue`. The write flow's `--update-golden` flag does not appear in the resolve-issue arg list, and the orchestrator does not chain to it after a write.

Rationale: golden updates should be a deliberate human-initiated decision tied to an intentional behavior change, not a side effect of `/resolve-issue` running on a branch. If a write-flow falsifiability check or smoke run fails because committed goldens are stale, the failure is the correct signal — surfacing it in `NON_SIMPLE_BUGS` lets the human decide whether to regenerate or revert.

A future orchestrator could observe `FAILURE_REASON=GOLDEN_STALE` in NON_SIMPLE_BUGS and offer to chain `--update-golden`, but that gating belongs in the orchestrator, not in this skill.

### Hard Rules (update mode)

1. **Working tree must be clean before generation.** No exceptions.
2. **Wiring tier must be green for in-scope scenarios.** Generating against broken implementation is forbidden.
3. **Goldens are reverted in place after generation.** Step U5 stages only what the user (or `--non-interactive`) explicitly approves.
4. **`FIELD_REMOVED` and `STRUCTURE_CHANGED` never auto-stage.** In non-interactive (default) mode they are recorded as `REVIEW_REQUIRED`; in `--interactive` mode they always prompt. There is no flag that bypasses this.
5. **Sequential generation only.** No parallel regeneration across scenarios.
6. **Non-deterministic scenarios are surfaced, not silently regenerated.** If output is unstable across two generation runs, fail loudly.
7. **No new test files.** Update mode regenerates fixtures only. Use the write flow for new tests.

---

## Hard Rules

1. **No assertion-free tests.** Detected in Step 4 static checks → `WRITER_FAILED_STATIC`.
2. **No tier bleed.** Wiring tests must contain schema assertions, not exact-value golden comparisons. Artifact tests must reference a committed golden fixture, not only check status codes.
3. **Tiers in separate files.** A file mixing wiring and artifact test cases is a writer bug — quarantine and reclassify.
4. **No hard-coded row IDs.** Seed rows; capture generated IDs. Flag as `HARDCODED_ID_WARNING`.
5. **No long sleeps.** `SLOW_TEST_DETECTED` → quarantine, NON_SIMPLE_BUGS.
6. **Falsifiability must be verified.** `FALSIFIABILITY_FAILED` → NON_SIMPLE_BUGS. Does not set `SUCCESS=false`, but must appear in HANDOFF.
7. **No volatile-output artifact tests.** `volatile_output: true` scenarios get wiring tests only. Golden files must be deterministic.
8. **Never modify source files.** If no seam exists, flag `NO_SEAM`, not a source edit.
9. **Runner must be invoked (wiring tier).** Exception: `INFRA_NOT_AVAILABLE=true`. Smoke timeout → set flag, proceed.
10. **No tests that duplicate existing integration coverage.** Verified by Feature Scope Agent's `already_covered` filter + Step 2b validation.

---

## Constraints

- Integration tests must be tagged so artifact tier does not run on every CI push.
- Tests run against real infrastructure. Do not introduce new fakes for infrastructure collaborators — use what the project already has, or stop with `INFRA_UNKNOWN`.
- Never commit to `main`/`master`. Stage; commit only on the feature branch.
- Golden fixtures are committed alongside tests. Do not generate from live production data.
- Writers must not share state assumptions. Each scenario's test file must be independently executable.

---

## Differences from `/component-test` (design rationale)

| Concern | Component-test | Integration-test |
|---|---|---|
| Discovery unit | Module boundary (structural, verifiable) | Feature scenario (semantic, requires validation) |
| Infrastructure | In-memory fakes only | Real infra — must be detected before writing |
| Negative control | Sabotage Planner mutates callee source | Falsifiability check breaks route binding or corrupts golden |
| Test files per scenario | 1 | 2 (wiring + artifact) unless volatile |
| Isolation model | GC / in-memory reset | Transaction rollback / truncation / fixture-reload |
| CI placement | Every push | Wiring: every push; Artifact: nightly/label |
| Golden artifacts | None | Committed `.golden.json` files; lifecycle via `--update-golden` |
| Scenario validation | Boundary Mapper outputs are structurally verifiable | Step 2b cross-checks http_entry_points against actual diff |

---

## Progress Output

```
[integration-test] Framework: pytest detected (Python). Wiring marker: @pytest.mark.integration_wiring
[integration-test] Infrastructure: docker-compose detected. Isolation: transaction-rollback.
[integration-test] CI artifact exclusion: confirmed (workflow filters @integration:artifact from push runs)
[integration-test] Feature scope: 4 scenarios from plan, 3 uncovered (1 already covered by auth_test.py)
[integration-test] Scenario validation: 3 verified, 0 unverifiable
[integration-test] Infra check: DATABASE_URL set. Proceeding with smoke run.
[integration-test] Writing tests: 3 scenarios × 2 tiers = 6 files...
[integration-test] Falsifiability check on slice-auth-login (wiring): PASS (test failed on missing route)
[integration-test] Falsifiability check on slice-auth-login (artifact): PASS (test failed on corrupted golden)
[integration-test] Falsifiability check on slice-user-profile (wiring): NO_SEAM — route binding not isolatable
[integration-test] Smoke run (wiring tier): 3 passed, 0 failed
[integration-test] HANDOFF: SUCCESS=true, TESTS_WRITTEN=6, GOLDEN_FILES=2, NON_SIMPLE_BUGS=1
```

Skips are named explicitly. A silent skip is a bug.

---

## Open Questions

1. **Falsifiability for queue-consumer scenarios.** The wiring falsifiability check (break route registration) doesn't transfer to message queue consumers — there's no route to remove. What's the correct probe? Candidate: temporarily replace the queue consumer handler with a no-op, confirm the test detects the missing processing. Needs per-transport-type strategy table.

2. **ISOLATION_MODEL=unknown fallback.** The spec defaults to `transaction-rollback`. If the project uses an ORM that doesn't support test transactions (some ORMs auto-commit), this default will leave dirty state. Should the spec hard-fail on `ISOLATION_MODEL=unknown` rather than guess?

3. **Golden fixture format.** The spec assumes JSON. Some projects use YAML, CSV, or binary snapshots. Should golden format be inferred from the project's existing snapshot/fixture convention (via infra recon), or always JSON? (Affects both the write flow's golden generation and the update flow's normalization logic.)

4. **Parallel writer isolation at the DB layer.** The spec says writers are capped at 4 and produce separate files. But when those files' tests run concurrently (pytest-xdist, jest --runInBand=false), the isolation model must hold. Should the spec require a per-test unique seed namespace (e.g. `TEST_RUN_ID` prefix on all seeded rows) as a mandatory constraint, or defer to the project's existing isolation model?

5. **Default normalization heuristics.** Step U3's default normalization (ISO timestamps within 24h, UUIDv4, common ID field names) is opinionated. Should this be off by default and require an explicit `<id>.normalize.json` rules file, accepting that maintainers will hit non-determinism failures more often? Or kept on, accepting that maintainers may not realize values are being scrubbed from their goldens?
