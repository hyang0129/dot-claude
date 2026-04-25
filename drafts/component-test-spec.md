# `/component-test` Skill Spec — Panel Synthesis

> Draft synthesized from a 5-person expert panel: Alex Chen (Test Architecture), Sam Park (Agentic Systems), Jordan Reyes (Platform/DevOps), Riley Thompson (Senior/Skeptic), Morgan Wu (Developer Experience).

---

## Purpose

Writes durable boundary tests that fail when *future, unrelated* changes break the wiring between modules. The primary value is corpus accretion — a deposit that pays out when someone else changes nearby code months from now. The tests are not primarily a check that the current PR works.

### Precise Boundary Definition (Alex Chen)

Three tiers, no overlap:

- **Unit test** — one module, all collaborators doubled. Tests a *decision*.
- **Component test** — two or more real modules cooperating across one named boundary. Minimal doubles (only I/O: network, filesystem, clock). Tests a *contract*.
- **Integration test** — full vertical slice, real infrastructure, real HTTP. Tests a *flow*.

A component test that doubles a same-package collaborator is a unit test wearing a costume. A component test that spins up the full stack is an integration test. Both are rejected.

---

## Agent Architecture

### Agent Delegation Map

The skill runs as a thin **orchestrator** on the main thread that spawns three kinds of subagents. Subagents communicate via temp files (JSON manifests, written test files) and bounded HANDOFF blocks — never via shared conversation context.

| Subagent | Fan-out | Tools | Suggested model | Inputs | Output |
|---|---|---|---|---|---|
| **Boundary Mapper** | 1× | Glob, Grep, Read | Sonnet | `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH`, list of existing component tests | `boundary-map.json` (Step 1 schema) |
| **Test Writer** | N×, parallel — one per uncovered boundary | Read, Write | Sonnet/Opus | One boundary entry, caller/callee signatures, one example test, framework conventions | One test file + `{boundary, test_file, test_count, slow_boundary}` |
| **Sabotage Planner** | N×, parallel — one per boundary, after Test Writer completes | Read | Haiku | Callee module source, the test file just written (structure only) | `{file, line, mutation}` patch spec — must target an interface binding, not implementation body |

**The orchestrator (main thread) owns and never delegates:**
- Reading the Assessment HANDOFF and Framework Discovery (Step 2 — mechanical, deterministic)
- Bash plumbing: temp directory creation, sabotage patch application, runner invocation, try/finally cleanup
- Cross-boundary decisions: rate-limiting parallel writers, idempotent marker registration in `pyproject.toml`, per-language polyglot routing
- Emitting the final HANDOFF block

**Why three roles, not one or five:**

- **Boundary Mapper is solo.** Ranking and deduplication need a holistic view of the impact set; fanning it out re-introduces the duplication it's supposed to filter.
- **Test Writer fans out per boundary.** Each invocation's context is just two modules plus one example, so total context usage is bounded independent of impact-set size, and a single bad boundary cannot poison the others. Directly defuses the "Integration Test in Disguise" pre-mortem — a per-boundary writer cannot accidentally chain 12 modules together.
- **Sabotage Planner is separate from Test Writer.** Independence *is* the verification. A test author who also picks the sabotage point will (consciously or not) choose a mutation their own assertions already catch. An independent agent reading only the callee picks the interface binding the contract actually depends on. This is the structural defense against the "Confident Green Suite" pre-mortem.
- **Negative-control test execution stays in the orchestrator.** Resolver-patching and try/finally cleanup must be deterministic; LLM-driven cleanup is how temp directories leak.

**Context-bleed prevention (Sam Park):**
- No subagent sees another subagent's transcript. They exchange structured outputs (JSON files, test files) only.
- Test Writer is *not* told that a negative control will run. Otherwise it writes tests defensive enough to pass any sabotage.
- Sabotage Planner is *not* shown the test assertions — only the test file's structural signature (imports, entry-point call). Otherwise it picks a mutation that bypasses the assertions. (Alex Chen)

**Failure isolation:**
- A Test Writer that crashes or returns garbage drops *its* boundary with `FAILURE_REASON=WRITER_FAILED:<boundary>`; other boundaries still ship.
- A Sabotage Planner that cannot identify a sabotage point marks its boundary `NEGATIVE_CONTROL_UNVERIFIED=true`; the orchestrator surfaces this in HANDOFF and emits overall `SUCCESS=false`. ("It Always Says SUCCESS" requires this — silently passing unverified boundaries is the failure mode.)

### Step 1 — Boundary Analysis Agent

*Delegated to:* **Boundary Mapper** subagent (single invocation).


**Input:** `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH` from the Assessment HANDOFF.

**Tooling:** Glob + Grep only — no LLM-driven file discovery. The LLM classifies what it reads, not where to look.

**Output:** A structured JSON boundary map written to a temp file:
```json
[
  {
    "caller": "services/auth",
    "callee": "repos/token",
    "call_sites": 3,
    "already_covered": false,
    "boundary_type": "service→repository"
  }
]
```

**Ranking signals (priority order):**
1. `IMPACT_SET` from Assessment HANDOFF — transitive reach already computed, don't recompute
2. Cross-package import paths in the diff — each unique `(caller_module, callee_module)` pair is a candidate
3. Interface/abstract-class implementations changed — high-value seams
4. Dependency injection registrations changed — wiring changes are exactly what component tests protect
5. Filter out boundaries already covered by existing component tests

Produce: `[(caller, callee, call_site_count, already_covered)]`. Write tests only for uncovered boundaries. If the impact set is too large for context budget, scope to highest-degree nodes and log excluded modules in `FAILURE_REASON`.

**Critical:** Run Boundary Analysis as a separate agent invocation from the Test Writer. Do not share a conversation thread — context bleed causes the Test Writer to inherit uncertainty from the analysis pass. (Sam Park)

### Step 2 — Framework Discovery

Walk the repo root and each affected path in `IMPACT_SET` for framework signals:

| Language | Signals |
|---|---|
| Python | `pyproject.toml` `[tool.pytest]`, `pytest.ini`, `setup.cfg` |
| Node/TS | `package.json` scripts.test, `jest.config.*`, `vitest.config.*` |
| Go | `go.mod` → `go test ./...` |
| Rust | `Cargo.toml` → `cargo test` |
| Java/Kotlin | `build.gradle[.kts]`, `pom.xml` |

For polyglot repos, resolve one runner *per affected language subtree* from `IMPACT_SET`. Handle each independently — no cross-language runner is invented.

Scan 2–3 existing test files to infer actual naming and placement conventions before writing anything. Do not guess. (Jordan Reyes)

### Step 3 — Test Writer Agent

*Delegated to:* **Test Writer** subagents, one per uncovered boundary, run in parallel. Orchestrator caps concurrency to avoid IDE/runner contention (suggested: 4). Each writer receives only its own boundary entry from `boundary-map.json`, the framework conventions resolved in Step 2, the caller/callee signatures, and one example test — never the full boundary map.

**Prompt constraints (non-negotiable):**
- Supply actual function signatures and type definitions, not just filenames. Force the agent to read the real source before writing any assertion.
- Require a `# TESTING:` comment above each test stating the invariant encoded and which transitive edge it covers. Makes hallucinated tests visible in review.
- Inject one real passing example from the existing test suite so the agent pattern-matches to the project's idiom, not training-data defaults.
- Prohibit: `any` casts, `mock.anything()` where the actual value is knowable, trivially-true assertions (`expect(result).toBeDefined()`, `assert result == result`).

**Test anatomy — Arrange/Act/Assert + Object Mother:**
```
[Arrange]  Build real caller and real callee with production wiring.
           Substitute only infrastructure (DB → in-memory fake, HTTP → test server stub).
           Use factory helpers, not inline literal data.
[Act]      Call exactly one entry point on the caller.
[Assert]   Assert on observable output (return value, state mutation, event emitted).
           Assert the contract, not the implementation. No spy on private methods.
[Teardown] Reset shared fakes to empty state. No global singletons left dirty.
```

**Real vs. doubled collaborators:** Use real in-process collaborators within the same bounded context. Double only: non-deterministic I/O (time, random, network), process-boundary I/O (DB, message broker, filesystem), or external ownership. Doubling in-process collaborators severs the wiring the test is supposed to protect. (Alex Chen)

**< 1s enforcement:** Use in-memory fakes (implementing the real interface), not mocks. After writing, run a static grep over generated files for: `time.Sleep`, `asyncio.sleep`, `setTimeout`, `fetch(`, `http.Get(`, `requests.`, `subprocess`, `exec.Command`. Any hit is rewritten to a stub before HANDOFF. If a boundary has no injectable seam, flag `SLOW_BOUNDARY=true` in HANDOFF — do not skip, do not silently introduce a new abstraction layer. (Jordan Reyes + Alex Chen)

**Context window budget:** Load in order, stop at 60% of context limit:
1. Boundary map JSON
2. Direct change diff
3. Type stubs/signatures for transitive modules (not full source)
4. One example test file from existing suite

Exclude: full source of unchanged files, lock files, generated code, large fixtures.

**Test file placement and naming:** Match what already exists — scan existing tests rather than assuming. Generated files must land where the runner already discovers them without config changes. (Jordan Reyes)

**Tagging without new infrastructure:**
- pytest: `@pytest.mark.component` — register in `pyproject.toml` `[tool.pytest.ini_options] markers` only if not already present, and only if `--strict-markers` is not set without it
- Jest/Vitest: `describe('component:', ...)` prefix — parseable by `--testNamePattern`
- Go: `//go:build component` build tag; verify CI invocation supports it or fall back to plain `_test.go`
- Rust: `#[cfg(feature = "component-tests")]` only if feature block already exists; otherwise `#[test]` with doc comment

### Step 4 — Negative Control Verification

*Delegated to:* **Sabotage Planner** subagent (one per boundary, parallel) for *choosing* the mutation. The orchestrator (not the subagent) applies the patch, runs the suite, asserts ≥1 failure, and reverts. The Sabotage Planner is given the callee source and the test file's imports/entry-point only — never the assertions.

**This is an exit condition, not a guideline.** (Riley Thompson)

After tests are written, verify that at least one generated test would fail if the wiring it covers is broken:

1. Create a temp copy of the callee module.
2. Inject a deliberate fault: replace the interface binding with a no-op, or comment out the return statement.
3. Run only the new test files against the temp copy (use `--rootDir` override or equivalent).
4. Assert that ≥ 1 test fails with a meaningful assertion error — not a `NullPointerException` crash, which means the test is asserting the wrong layer.
5. Clean up the temp copy unconditionally (try/finally in bash scaffolding, not in LLM-generated code).

**If all tests pass against broken wiring → emit `SUCCESS=false`.** No exceptions.

**Watch for:** path-aliased imports (`@/lib/...`) resolve to the original source, not the temp copy. The resolver config must be patched for the temp run — document this per language in the implementation. (Sam Park)

**Watch for:** swallowed exceptions. If the module catches and logs errors rather than surfacing them, the negative control passes even when wiring is broken. The sabotage must target the interface binding, not the implementation body. (Alex Chen, Riley Thompson)

### Step 5 — Suite Run and HANDOFF

*No delegation* — orchestrator only. Aggregates per-boundary records from Test Writer + Sabotage Planner outputs, runs the full new-test suite, emits HANDOFF.

Run the new tests with the project's existing command. Verify:
- The runner exits non-zero on failure (some frameworks exit 0 with `--passWithNoTests` — always assert ≥ 1 test was collected)
- All new tests pass
- Negative control has already been verified (Step 4)

Emit HANDOFF. Do not emit `SUCCESS=true` if the runner was not actually invoked. If the runner cannot be located, emit `SUCCESS=false` with `FAILURE_REASON=RUNNER_NOT_VERIFIED`. (Morgan Wu)

---

## HANDOFF Schema

```
HANDOFF
SUCCESS=<true|false>
TESTS_WRITTEN=<int>
TEST_FILES=<comma-separated forward-slash paths>
SLOW_BOUNDARIES=<comma-separated module pairs where no seam existed, or empty>
TEST_BOUNDARY_SUMMARY=<one-line per boundary: caller→callee: what invariant is tested>
FAILURE_REASON=<empty if SUCCESS=true>
END_HANDOFF
```

**Notes:**
- `TESTS_WRITTEN=0` with `SUCCESS=true` is valid when `COMPONENT_TESTS=false` from assessment — signals intentional skip, not a crash
- Paths must always use forward slashes (Windows compatibility)
- `TEST_BOUNDARY_SUMMARY` is surfaced in the PR description by the orchestrator — write it for a human who hasn't read the issue
- Do not add `COVERAGE_DELTA` or `ASSERTIONS_PER_FILE` — the orchestrator cannot act on them and they invite gaming

---

## Hard Rules (SUCCESS=false if violated)

1. **No assertion-free tests.** Statically verify assertion presence before HANDOFF.
2. **No tautological assertions.** `assert result == result`, `assert True`, `expect(fn()).toBeDefined()` are detectable and fail.
3. **No tests that mock the module under test.** If the test patches away the thing it's testing, it cannot detect wiring failure.
4. **No tests that duplicate existing unit test coverage verbatim.** Check existing corpus. Identical input/output pair with identical setup = skip or fail.
5. **Negative control must demonstrate at least one test fails on broken wiring.** No exceptions. (The entire purpose of the skill collapses without this.)
6. **Runner must be invoked and verified.** `SUCCESS=true` without executing the tests is a lie.

## When to Write Zero Tests and Still Emit SUCCESS=true

- The change touches only infrastructure (logging, metrics, formatting) with no module boundary crossing
- All affected boundaries are already covered by existing component tests with negative controls
- No concrete observable output exists at the boundary (nothing to assert against)

Zero tests + honest `FAILURE_REASON` is correct. Five meaningless tests is not.

---

## Progress Output (Morgan Wu)

Emit structured, scannable lines prefixed `[component-test]`:
```
[component-test] Discovering test surface from impact set (12 modules)...
[component-test] 3 uncovered boundaries identified: AuthService→TokenRepo, UserService→AuthService, ...
[component-test] Skipping PaymentService→Logger: infrastructure-only boundary
[component-test] Writing tests to src/__tests__/auth/AuthService.component.test.ts...
[component-test] Running negative control on AuthService→TokenRepo... PASS (1 test failed as expected)
[component-test] Negative control on UserService→AuthService... PASS
[component-test] Suite run: 6 tests passed, 0 failed
```

Each line reports a decision, not just activity. Skips are named explicitly.

---

## Invocation Modes

**Orchestrated (default):** Non-interactive, progress to log, files staged and committed with a conventional commit message. `COMPONENT_TESTS=false` from Assessment skips the skill with `TESTS_WRITTEN=0, SUCCESS=true`.

**Direct (`/component-test <branch>`):** `--interactive` on by default — prints `TEST_BOUNDARY_SUMMARY` and asks for confirmation before writing files. `--no-interactive` falls back to orchestrated behavior.

---

## Consolidated Gotchas

### Agentic / LLM (Sam Park)
- **Agent reuses import paths from diff, not module graph.** Moved file = old import path = compile-time success, runtime failure.
- **Negative control temp-copy breaks with path-aliased imports.** Patch the resolver config per project, or detect and warn.
- **`TESTS_WRITTEN` count gets gamed.** Gate on distinct transitive edges covered, not raw test count.
- **Test runner `--passWithNoTests` exits 0.** Always assert ≥ 1 test was collected.
- **Jest mock hoisting.** `jest.mock()` is hoisted before imports — agent-generated mocks after import statements fail silently.
- **Context bleed between agents.** Boundary Analysis and Test Writer must run as separate invocations.
- **Mixed test frameworks in monorepos.** Scope per language subtree; don't pick one and silently skip the rest.

### Architecture / Correctness (Alex Chen)
- **Sabotage targets wrong layer.** Retry/circuit-breaker in the caller masks callee failure. Target the interface binding, not the implementation body.
- **Object Mother data bleeds between tests.** Each test needs explicit store reset, not GC.
- **Boundary too coarse.** Controller→service facade hides sub-service wiring. Recurse one level into the impact set.
- **Dynamic dispatch missed by grep.** Python `importlib`, Java reflection, JS `require(variable)`. Supplement with DI container registration inspection.
- **Agent introduces abstraction layer.** If there's no seam, flag `SLOW_BOUNDARY=true` — never modify source files.
- **Existing tests mislabelled.** `*_component_test.*` may contain unit tests. Check the body, not the filename.

### Platform / CI (Jordan Reyes)
- **pytest `conftest.py` scope creep.** Fixtures two directories up work locally, break with `--rootdir` scoping in CI.
- **Jest `moduleNameMapper` gaps.** Path aliases fail in CI if not in `jest.config.js`. Use relative imports or verify alias exists.
- **Go test caching.** Tests that assert constants re-run even without source changes — cache hit masks real staleness.
- **Gradle daemon startup.** JVM bootstrap is 30–60s in ephemeral CI. The < 1s constraint applies to test body, not runner bootstrap.
- **pytest marker registration before suite gate.** `--strict-markers` in CI will fail on unregistered `component` mark.
- **Cargo feature flag silence.** Verify CI invocation includes `--features component-tests` or fall back to plain `#[test]`.
- **Vitest worker isolation.** Module-level singletons behave differently than Jest's shared module state.

### Maintenance Rot (Riley Thompson)
- **Hardcoded fixture data tied to current DB seed.** Reseeding breaks tests with no explanation.
- **Assertions on log/error message strings.** Message wording changes; the contract didn't. Test breaks incorrectly.
- **Time-dependent tests without clock injection.** Midnight month-boundary failures.
- **Import private implementation details.** Valid refactors break tests. Cry-wolf failures.
- **Overfitted call signatures.** Adding an optional param requires test updates even when behavior is unchanged.
- **Copy-pasted setup blocks that diverge silently.** Some tests update, some don't; diverged setup tests a configuration that no longer exists.
- **Swallowed exceptions.** Module catches and logs instead of surfacing. Negative control passes forever. Wiring breakage ships.

### Developer Experience (Morgan Wu)
- **Trivially-passing tests poison trust.** One `expect(fn()).toBeDefined()` trains developers to ignore all generated tests.
- **Wrong abstraction level.** Private internals in assertions means valid refactors break tests. Developers start deleting them.
- **Mock overreach.** 6 layers deep when there's one real dependency. Reviewer can't tell what's being tested.
- **Missing the regression case.** The skill defaults to the happy path. The original bug scenario is usually an error path.
- **Filename collision.** Creating `AuthService.test.ts` when one already exists. Check before writing.
- **No error-path coverage.** `catch` blocks and boundary inputs are where bugs live.
- **SUCCESS without runner verification.** Misleads the orchestrator into skipping a validation step.

---

## Pre-Mortem Scenarios

### "The Confident Green Suite" (Alex + Riley)
After 6 months, every PR has `TESTS_WRITTEN=3` in HANDOFF, 92% coverage delta reported. A major refactor silently breaks module contracts. Tests still pass because they mock the dependency. Root cause: negative control verification was silently skipped for path-aliased modules due to resolver patch bug. The entire corpus for aliased projects is unverified.

### "The Flake Factory" (Riley)
One generated test hits an external service behind a thin wrapper with no obvious name. 1-in-8 failure rate. Team trains itself to re-run CI until green. Every future test in that file inherits the same credibility deficit. Eventually the team ignores all CI failures in the component test tier.

### "The Maintenance Anchor" (Riley + Morgan)
Tests are so tightly coupled to the implementation's current shape that every refactor breaks 5 tests unrelated to the refactor's intent. Team stops refactoring. Code ossifies. The test suite becomes a change-prevention system.

### "The Integration Test in Disguise" (Sam)
`TRANSITIVE_REACH` grows as impact sets expand. The Test Writer, given a 12-module impact set, writes tests that spin up database connections to cover all of them in one chain. These are slow, flaky, and belong in `/integration-test`. No gate enforced the boundary constraint.

### "Coverage Metric Laundering" (Riley)
Coverage tools count generated tests. Coverage gate moves from 61% to 74%. Leadership believes the codebase is safer. New tests cover already-safe lines; dangerous lines remain uncovered. Metric improved; risk didn't.

### "It Always Says SUCCESS" (Morgan)
A misconfigured repo (test runner not on PATH in CI) means tests never execute. The skill reports SUCCESS for 6 months. A regression ships. Trust collapses overnight. Root cause: `SUCCESS=true` did not require runner verification.

### "The Rust Feature Flag Silence" (Jordan)
Component tests emitted with `#[cfg(feature = "component-tests")]`. CI runs `cargo test --workspace` without that feature. Zero component tests run in CI for 6 months. Nobody notices because the suite gate ran locally where `.cargo/config.toml` had the feature. Entire corpus is dead weight.

### "The Windows Path Bug" (Sam)
`TEST_FILES` contains backslash paths on Windows. Downstream parser splits on commas and gets unresolvable paths. Simple fix: always emit forward slashes. The schema didn't say this explicitly, so it wasn't done.

---

## Open Questions for the Orchestrator

1. **Negative control isolation** — The temp-copy approach for negative control requires per-language resolver patching. Should the implementation include a language-adapter contract (similar to the impact tool adapter in §2 of the redesign), or hard-code per-language strategies?

2. **`SLOW_BOUNDARY` escalation** — When `SLOW_BOUNDARY=true` is in the HANDOFF, should the orchestrator route those specific boundaries to `/integration-test` automatically, or just log them?

3. **TESTS_WRITTEN=0, SUCCESS=true** — The orchestrator's suite-completeness gate (Step 2d) should treat this as intentional and not re-run component-test. How is "intentional skip" distinguished from "crash with no HANDOFF"? Suggest: crash produces no HANDOFF block at all; `TESTS_WRITTEN=0` + `SUCCESS=true` is the explicit skip signal.

4. **Concurrent PR marker registration** — Two PRs both adding `@pytest.mark.component` to `pyproject.toml` will conflict on merge. Should the skill write markers idempotently (check before adding) and document the merge conflict risk?
