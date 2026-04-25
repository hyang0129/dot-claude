---
version: 0.1.0
status: stub
---

# Integration Test

## Purpose

Writes integration tests across two tiers, distinguished by what they verify and how often they run:

- **Wiring tier** (`@integration:wiring` or project-equivalent tag) — verifies that the feature slice's plumbing is correct: routes resolve, handlers register, dependency injection wires up, schemas validate, the service starts and responds. Real infrastructure for the closest collaborator (real DB), stubs for the rest. Time budget per test < 5s, suite total < 60s. **Runs on every CI push.** This is the smoke layer for the integration boundary.
- **Artifact tier** (`@integration:artifact`) — verifies the feature slice produces the *correct output* against committed test fixtures: golden JSON, golden files, golden DB state. Real infra, no stubs. No tight time budget. **Excluded from per-push CI; runs nightly or on label.** This is where output correctness against realistic inputs is proven.

Both tiers are written by the same skill invocation. Tagging is enforced via the project's existing mechanism (pytest markers, Jest projects, Go build tags) so a contributor can run either tier in isolation.

The split mirrors industry practice (Google small/medium/large/enormous, Fowler narrow/broad integration) and is named by *purpose* rather than speed — speed is a downstream consequence. A wiring test that takes 30s is a smell; an artifact test that takes 30s is fine.

Like component tests, integration tests are written primarily for the corpus, not for the current PR. The wiring tier's job is to fail loudly when a future change severs a system-edge connection; the artifact tier's job is to fail loudly when a future change silently corrupts output. Both are about regression detection, not local correctness.

**Scope:** the full feature slice, exercised against real (or realistic) infrastructure — a real database, a real HTTP stack, real message queues. Unlike component tests, integration tests do not stub collaborators within the slice. Unlike E2E tests, they do not involve a browser.

---

## Args

`/integration-test <branch> [--repo <owner/repo>] [--work-dir <path>]`

- `branch`: the feature branch to analyse and write tests for.
- `--repo`: GitHub repo. Auto-detected from `git remote` if omitted.
- `--work-dir`: path to the git working tree. Defaults to `git rev-parse --show-toplevel`.

---

## TODO: Implementation

This skill is a stub. The following steps need to be designed and implemented:

1. **Feature Scope Agent** — reads the branch diff, the plan artifact (`.agent-work/ISSUE_<n>_PLAN.md`), and the acceptance criteria to identify the full feature slices introduced by the branch. Each acceptance criterion is a candidate integration test scenario.

2. **Infrastructure Recon** — identifies what test infrastructure exists for integration testing: Docker Compose files, test database fixtures, seed scripts, environment variable conventions. Determines whether integration tests can be run locally or only in CI.

3. **Test Writer Agent** — writes one integration test per feature slice using the project's integration test framework and conventions. Tests must be tagged or placed so they are excluded from the standard CI unit-test run (e.g. `@pytest.mark.integration`, Jest `--testPathPattern=integration`, etc.).

4. **Validation** — runs the integration test suite in isolation and confirms all new tests pass. Does NOT run as part of standard unit test validation.

5. **HANDOFF block** — returns:
   ```
   HANDOFF
   SUCCESS=<true|false>
   TESTS_WRITTEN=<int>
   TEST_FILES=<comma-separated paths>
   RUN_COMMAND=<command to run integration tests locally>
   FAILURE_REASON=<empty if SUCCESS=true>
   END_HANDOFF
   ```

---

## Constraints

- Integration tests must be tagged or isolated so they do not run on every CI push.
- Tests run against real infrastructure — do not mock databases, queues, or external services unless absolutely unavoidable; note any exceptions explicitly.
- Do not modify source files. Test files only.
- Do not duplicate acceptance criteria already covered by unit or component tests.
- Never commit to main/master.
