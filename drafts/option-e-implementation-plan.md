# Option E Implementation Plan — Targeted Test Skills

## Goal

Replace `--boundaries` in `resolve-issue.md` Step 2g with two new skills designed for the Class B path: `/component-test-targeted` and `/integration-test-targeted`. Existing `/component-test` and `/integration-test` stay byte-identical.

## Decisions to make first

Before any file work, three calls. Defaults below are my recommendations — flag any you'd reverse.

### D1 — Step-sharing strategy

The targeted skills reuse most of the existing orchestration (framework discovery, static checks, falsifiability, smoke run, HANDOFF emission). Options:

- **D1.a — Reference by name**: targeted skill says "follow `component-test.md` *Framework Discovery* step verbatim." Pinned to step *names*, not numbers. Smallest markdown; risks silent drift if wording diverges.
- **D1.b — Extract heavy steps to shared files**: pull falsifiability and smoke-run blocks (the long bash chunks) into `commands/component-test/_shared-falsifiability.md` etc. Both skills include them.
- **D1.c — Duplicate**: copy the content into each targeted skill. Self-contained, drift on every edit.

**Default:** D1.a for short conceptual steps, D1.b for the long bash blocks. No D1.c.

### D2 — Input shape from Bug Review

- **D2.a — Structured scope file**: Bug Review writes `<WORK_DIR>/.agent-work/targeted-<component|integration>-scope-<ISSUE_NUMBER>.json`. Targeted skill reads via `--scope-file <path>`. Typed contract on disk.
- **D2.b — CLI free-text**: targeted skill takes `--boundaries "<text>"` and re-reads Bug Review HANDOFF for context. Same shell-quoting risks as Option A.

**Default:** D2.a. The whole point of new skills is to fix the contract, not re-encode it as CLI strings.

### D3 — Writer prompt: reuse vs fork

- **D3.a — Reuse existing `test-writer-prompt.md`** with two new optional input fields (`bug_context`, `motivating_diagnoses`). Writer ignores them when absent.
- **D3.b — Fork to `test-writer-targeted-prompt.md`** with Class B framing baked in.

**Default:** D3.a. Promote to D3.b only if review of generated tests shows the existing prompt produces wrong-framing tests.

## Phases

### Phase 1 — Resolver prompts (parallel-able)

Two new prompt files — lighter cousins of Boundary Mapper / Feature Scope Agent. Both consume the scope file and produce the *same JSON output schema* the existing Test Writers already consume, so writers don't change.

**1.1** `commands/component-test/boundary-resolver-prompt.md` (~80 lines)

For each `{description, bug_ids, related_files}` in the scope file:
1. Parse the description for caller/callee or module names.
2. Grep call sites with the same structural rigor as Boundary Mapper.
3. Populate the standard `boundary-map.json` record (`id`, `caller`, `callee`, `caller_files`, `callee_files`, `call_sites`, `boundary_type`).
4. **Skip** the `already_covered` filter — Fix Planner already considered coverage.
5. Unmatched descriptions → `excluded[]` with `reason: "OVERRIDE_NOT_FOUND"`.

**1.2** `commands/integration-test/scenario-resolver-prompt.md` (~100 lines)

Same shape for `scenario-map.json`: parse descriptions for `METHOD path` and system-edge cues; grep route registrations; populate `http_entry_points`, `layers_involved`, `tier`, `volatile_output`. Skip `already_covered`. Step 2b cross-validation in the existing integration-test.md applies unchanged.

### Phase 2 — Targeted skill files

**2.1** `commands/component-test-targeted.md` (~120 lines, mostly references)

Structure:
- **Args**: `<branch> [--repo] [--work-dir] --scope-file <path>` (scope-file required).
- **Step 0** — Setup. Parse scope file.
- **Step 1** — Framework Discovery. *Reference `component-test.md` Framework Discovery.*
- **Step 2** — **Boundary Resolution** (new): spawn the resolver from Phase 1.1.
- **Step 3** — Test Writers. *Reference `component-test.md` Test Writers.* Adds `bug_context` to the per-writer input record.
- **Step 4** — Negative Control. *Reference `component-test.md`.*
- **Step 5** — Suite Run + Fix Loop + HANDOFF. *Reference `component-test.md`.*

**2.2** `commands/integration-test-targeted.md` (~140 lines)

Same shape, integration-specific:
- Step 1 references Framework + Infrastructure Recon from `integration-test.md`.
- Step 2 is the new Scenario Resolver.
- Step 2b cross-validation references `integration-test.md` Step 2b.
- Steps 3–6 reference the originals.

### Phase 3 — Bug Review upgrade

Edit `commands/resolve-issue.md` Step 2e:

After classification, if `B`, the Bug Review Agent writes two scope files (one each for component / integration, either may be empty/absent if not needed):

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

HANDOFF additions:

```
TARGETED_COMPONENT_SCOPE_FILE=<path or empty>
TARGETED_INTEGRATION_SCOPE_FILE=<path or empty>
```

Document the JSON schema once in resolve-issue.md and reference it from both Bug Review prompt and resolver prompts. Estimated change: ~40 lines.

### Phase 4 — Step 2g rewrite

Edit Step 2g in `commands/resolve-issue.md`:

```
/component-test-targeted <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --scope-file <TARGETED_COMPONENT_SCOPE_FILE>
/integration-test-targeted <BRANCH> --repo <REPO> --work-dir <WORK_DIR> --scope-file <TARGETED_INTEGRATION_SCOPE_FILE>
```

Drop `--boundaries` and `--handoff-file` from the targeted invocations (scope file carries everything). Skip the corresponding sub-call when its scope file path is empty. Estimated change: ~15 lines.

### Phase 5 — Cross-references

- Footer in `component-test.md` and `integration-test.md`: "For Class B / Step 2g use, see `<targeted skill>`."
- One-line note in resolve-issue.md Step 2e classification description that B routes to the targeted skills.
- Add comments at each "*Reference …*" target step in the existing skills: "this step is also referenced by `<targeted skill>` — preserve heading text on rename."

~10 lines total.

### Phase 6 — Verification

Markdown-only skills, no automated tests. Manual passes:

1. Walk a synthetic scope file through Step 2g by hand. Confirm every reference resolves (paths, prompt files, schema fields).
2. Re-read both targeted skill files end-to-end. Step transitions coherent.
3. Grep for stale terminology — every `boundary-map.json` reference should resolve to the resolver's output.
4. Smoke a real Class A `/component-test` to confirm zero regression in the untouched path.

## Footprint summary

| Action | Files | Approx. lines |
|---|---|---|
| New | `boundary-resolver-prompt.md`, `scenario-resolver-prompt.md`, `component-test-targeted.md`, `integration-test-targeted.md` | ~440 |
| Edit | `resolve-issue.md` (Step 2e + Step 2g + cross-refs) | ~65 |
| Edit | `component-test.md`, `integration-test.md` (footer + ref-target comments) | ~10 |
| Untouched | All existing prompts, `fix-issue.md`, review/finalize skills | — |

Total: ~440 added, ~75 edited.

## Risk register

1. **Reference brittleness (D1.a)**. Targeted skill pins to step *names*. Add a comment at each named step in the original skill noting the cross-reference, so renames don't silently break the targeted skill.
2. **Resolver hallucination**. Free-text "auth → token" might match the wrong call site. Resolver emits the matched call site under `notes` for human review of the HANDOFF. `OVERRIDE_NOT_FOUND` is informational, not blocking.
3. **Scope file schema drift**. Define the JSON shape once, reference from both producer (Bug Review) and consumer (resolver) prompts. Treat the schema as a versioned contract — adding fields is safe, renaming or removing isn't.
4. **No recursive Bug Review on Step 2g output**. Existing constraint at resolve-issue.md:508 ("one level of automated repair only") covers this; the targeted skills' NON_SIMPLE_BUGS are informational only.
5. **Backwards compat sniff test**. Class A path's hash should not change. Run a no-op `/component-test` after Phase 5 and diff against pre-change behavior.

## Order of operations

1. Confirm D1, D2, D3.
2. Parallel: Phase 1 resolvers + Phase 3 Bug Review HANDOFF (both are leaves).
3. Phase 2 targeted skills (needs resolvers).
4. Phase 4 Step 2g (needs scope files + targeted skills).
5. Phase 5 cross-references.
6. Phase 6 verification.

Phases 1–5 are roughly half a day of careful editing.

## Open questions for you

1. Confirm the three defaults (D1.a + D1.b mix, D2.a, D3.a) or override.
2. Should the resolver also run an `already_covered` check as informational (logged but not filtered), or skip it entirely? My lean: log under `notes`, never drop.
3. Component-test's Boundary Mapper today produces `excluded[]` for things it intentionally skipped (out-of-scope language subtree, etc.). Should the resolver reuse the same field for its `OVERRIDE_NOT_FOUND` cases, or use a separate `unresolved[]` field to keep semantics distinct? My lean: separate field. Same for integration's `unverifiable_scenarios`.
