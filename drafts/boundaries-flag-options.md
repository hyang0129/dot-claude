# `--boundaries` Flag Contract Gap — Options Memo

## 1. Problem statement

[`commands/resolve-issue.md:495,501`](commands/resolve-issue.md#L495) Step 2g spawns secondary `/component-test` and `/integration-test` runs with a `--boundaries "<...>"` argument. Neither skill declares that flag in its `Args` list ([`component-test.md:24`](commands/component-test.md#L24), [`integration-test.md:29`](commands/integration-test.md#L29)). As a result the orchestrator passes a payload that the skills will silently ignore: their discovery agents (Boundary Mapper, Feature Scope Agent) will re-derive scope from scratch instead of consuming the Fix Planner's pre-approved boundary list. The Step 2g comment "boundaries are pre-supplied by the Fix Planner, not re-derived from the diff" ([`resolve-issue.md:504`](commands/resolve-issue.md#L504)) is currently aspirational, not enforced.

## 2. Today's flow — how boundaries are discovered

### `/component-test`

- Inputs ([`component-test.md:36-51`](commands/component-test.md#L36)): the upstream Assessment HANDOFF supplies `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH`. None of these are "the bug fix's new seams" — they are the original PR's diff reach.
- Step 2 ([`component-test.md:138-158`](commands/component-test.md#L138)) spawns a single Boundary Mapper subagent. It walks `IMPACT_SET` with `Grep`/`Glob`, extracts `(caller, callee)` pairs from imports, classifies them, and writes `$WORK_DIR/boundary-map.json`.
- Output schema ([`boundary-mapper-prompt.md:88-108`](commands/component-test/boundary-mapper-prompt.md#L88)): a JSON object with `boundaries[]` entries containing `id, caller, callee, caller_files, callee_files, call_sites, already_covered, boundary_type, discovery, rank_signal, notes`. Plus `excluded[]`.
- Downstream ([`component-test.md:160-162,193-201`](commands/component-test.md#L160)): the orchestrator filters to `already_covered: false`, then per-boundary spawns parallel Test Writer subagents that each receive the full JSON entry verbatim. The structured fields (`caller_files`, `callee_files`, `boundary_type`) are load-bearing for the writer prompt.

### `/integration-test`

- Inputs ([`integration-test.md:45-56`](commands/integration-test.md#L45)): same Assessment HANDOFF with `INTEGRATION_TESTS`, `IMPACT_SET`, `DIRECT_CHANGES`, `TRANSITIVE_REACH`.
- Step 2 ([`integration-test.md:188-212`](commands/integration-test.md#L188)) spawns a Feature Scope Agent. It reads `ISSUE_<n>_PLAN.md` acceptance criteria, identifies HTTP entry points by grepping route registrations, and writes `$WORK_DIR/scenario-map.json`.
- Output schema ([`feature-scope-prompt.md:106-128`](commands/integration-test/feature-scope-prompt.md#L106)): `scenarios[]` with `id, description, acceptance_criterion, http_entry_points (METHOD path), layers_involved (file paths), already_covered, tier (wiring/artifact), golden_fixture_candidate, volatile_output, notes`. Plus `excluded[]` and `dropped_acceptance_criteria[]`.
- Step 2b ([`integration-test.md:214-222`](commands/integration-test.md#L214)) cross-validates: each `http_entry_point` is grepped against the source tree; each file in `layers_involved` is `Glob`-checked. Unverifiable scenarios are dropped. This validation pass exists *because* the agent's output is semantic and unreliable.
- Downstream ([`integration-test.md:280-292`](commands/integration-test.md#L280)): per-scenario Test Writers receive the full JSON entry.

**Key shape difference.** Component test boundaries are *structural* (verifiable from the call graph). Integration test scenarios are *semantic* (require AC text + route grep + manual cross-check). Anything we feed in from outside has to satisfy each skill's downstream consumers — particularly the writers, which depend on populated `caller_files`/`callee_files` (component) and `http_entry_points`/`layers_involved` (integration).

## 3. What Fix Planner gives us

From [`resolve-issue.md:283-297`](commands/resolve-issue.md#L283), the Fix Planner emits in its HANDOFF:

```
NEW_COMPONENT_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
NEW_INTEGRATION_TESTS_NEEDED=<comma-separated boundary descriptions, or empty>
```

Definitions ([`resolve-issue.md:296-297`](commands/resolve-issue.md#L296)):

- `NEW_COMPONENT_TESTS_NEEDED`: "per-boundary descriptions for new module boundaries the fix introduces that are not already covered by a component test."
- `NEW_INTEGRATION_TESTS_NEEDED`: "per-boundary descriptions for new system-edge paths or new artifact outputs the fix introduces."

**Format reality:** comma-separated free-text strings — short human-readable descriptions, not structured records. The Fix Planner is read-only (Read/Grep/Glob/Bash for git diff only, [`resolve-issue.md:277`](commands/resolve-issue.md#L277)) so it *could* in principle emit richer per-boundary info, but it currently emits a flat list.

The CLI proposed in Step 2g (`--boundaries "<NEW_COMPONENT_TESTS_NEEDED>"`) just splatters that string onto the command line. There is a structural impedance mismatch with both downstream JSON schemas.

Also note: Step 2g passes `--handoff-file <HANDOFF_FILE>` but `HANDOFF_FILE` ([`resolve-issue.md:146`](commands/resolve-issue.md#L146)) is the *Assessment* HANDOFF, not the Bug Review / Fix Planner HANDOFF. So the secondary invocation today still inherits the original `IMPACT_SET`/`DIRECT_CHANGES` — there is no path for the skill to reach the Fix Planner's bug-review handoff at all.

## 4. Options

### Option A — Add `--boundaries` flag (string passthrough)

**Mechanism**

- Add `--boundaries "<comma-separated descriptions>"` to the `Args` of both skills.
- In Step 0 (Setup), if `--boundaries` is set, store as `BOUNDARY_OVERRIDE_TEXT`.
- In Step 2, if `BOUNDARY_OVERRIDE_TEXT` is set, modify the discovery-agent prompt: pass the override text and instruct the agent to *only* produce entries matching those descriptions (still doing the structural grep work to fill in `caller_files`/`http_entry_points`/etc.).
- The agent's structured output schema is unchanged; what changes is how it picks candidates.

**Pros**

- Smallest surface change at the CLI boundary; matches what Step 2g already tries to call.
- Preserves the current discovery-agent role: it still produces validated JSON, still cross-checks file existence (integration-test Step 2b stays load-bearing).
- Free-text in / structured out — the agent does the impedance-matching, which is exactly what an LLM is for.

**Cons**

- Command-line strings have shell-escaping risk (commas, quotes, parens in descriptions). The orchestrator would need to be careful with quoting; long lists could exceed sane CLI limits.
- The agent could still hallucinate or reinterpret the override list; we lose hard control. If the Fix Planner says "auth → token-rotator boundary" and the agent finds no such call site, behavior is ambiguous (drop? keep with empty `caller_files`? error?).
- The override semantics (replace? seed and add? subset?) need a clear spec — nothing in the prompt files today distinguishes "ranking input" from "exhaustive whitelist."

**Change footprint (~3 files)**

- `commands/component-test.md`: add flag in Args, add parse in Step 0, branch in Step 2. ~10 lines.
- `commands/integration-test.md`: same. ~10 lines.
- `commands/component-test/boundary-mapper-prompt.md` and `commands/integration-test/feature-scope-prompt.md`: add an "if `BOUNDARY_OVERRIDE_TEXT` is non-empty, use it as the candidate set" section. ~15 lines each.
- `commands/resolve-issue.md`: no change (already passes `--boundaries`).

### Option B — Extend the Assessment HANDOFF file with override fields

**Mechanism**

- Add optional fields to the Assessment HANDOFF block read by the skills: `BOUNDARIES_OVERRIDE=...` (component) and `SCENARIOS_OVERRIDE=...` (integration).
- For Step 2g, the orchestrator writes a *second* HANDOFF file (or rewrites the Assessment HANDOFF in place) that adds those fields and then re-passes `--handoff-file`.
- Skills' Step 0 parses the new fields; if present, behave like Option A.

**Pros**

- No new flag; the existing `--handoff-file` channel is reused. Keeps the skill's external surface stable.
- Long lists are safe (file payload, not command line).
- The skill code already reads HANDOFF files, so plumbing is local.

**Cons**

- Conflates two distinct upstream contracts: the Assessment HANDOFF (orchestrator's pre-impl judgment) and the Bug Review HANDOFF (post-impl bug-fix scope). Mixing them creates an ambiguous "where does this field live" question.
- Forces the orchestrator to either mutate `assessment-handoff-<n>.txt` (destructive — Step 2c, 2d may still want the original) or write a derived file with no clear naming convention.
- HANDOFF block format ([`component-test.md:41-47`](commands/component-test.md#L41)) is currently a flat KV list — multiline structured boundary descriptions don't fit naturally.

**Change footprint (~3 files, but messier)**

- `commands/resolve-issue.md`: emit a new HANDOFF or amend existing. ~15 lines, plus a naming decision.
- Both skills: extend HANDOFF parser, document new fields, branch in Step 2. ~15 lines each.
- Both prompt files: same as Option A.

### Option C — Structured scope file via `--scope-file <path>`

**Mechanism**

- Orchestrator writes `<WORK_DIR>/.agent-work/component-test-scope-<ISSUE_NUMBER>.json` and `<WORK_DIR>/.agent-work/integration-test-scope-<ISSUE_NUMBER>.json` — typed objects matching the *output* schema of the discovery agents (boundaries[] with caller/callee/files; scenarios[] with http_entry_points/layers_involved).
- The Fix Planner is upgraded to emit, alongside the free-text `NEW_*_TESTS_NEEDED`, a structured `BOUNDARIES_JSON=<file path>` field that points at the scope file. (Or the Bug Review Agent transcribes the free text into JSON before invoking the skills.)
- Add `--scope-file <path>` to both skills. When set, Step 2 reads the file *as if* it were the discovery agent's output — skipping the discovery agent entirely and going straight to validation (Step 2b for integration) and writers.

**Pros**

- Strongest type safety. The on-disk shape *is* the contract — no string parsing, no shell quoting.
- Fix Planner can be promoted from "free-text descriptions" to "structured scope," which is more aligned with what downstream actually needs. Reduces re-derivation work.
- Cleanly skips the discovery agent (avoids two LLM calls for the same job in the Class B path).
- Same flag pattern works uniformly for both skills.

**Cons**

- Requires upgrading the Fix Planner to produce structured boundary records — the Fix Planner currently has only read-only tools and would need to grep call graphs / route registrations itself, which is the discovery agent's whole job. Risk of duplicating logic, or of the Fix Planner producing under-specified records.
- Largest change footprint: Fix Planner prompt + bug review handoff schema + both skills + both discovery-agent prompts (which now have a "skip yourself" branch).
- Bypassing the discovery agent means we lose its validation pass (the integration-test Step 2b cross-check is exactly the "agent might lie" insurance). We'd need to apply that validation to the scope file regardless.

**Change footprint (~5 files)**

- `commands/resolve-issue.md`: extend Fix Planner prompt + Bug Review HANDOFF + Step 2g writes scope file. ~30 lines.
- Both skills: add `--scope-file` flag, branch in Step 0/2, run Step 2b validation against the scope-file contents. ~25 lines each.
- Both prompt files: minimal change (only relevant when scope-file is *not* present).

### Option D — Pre-write `boundary-map.json` / `scenario-map.json` + `--skip-discovery`

**Mechanism**

- Orchestrator pre-creates `$WORK_DIR/.agent-work/component-test-<branch-slug>/boundary-map.json` (the exact path the skill would write) and the equivalent `scenario-map.json`.
- Add `--skip-discovery` flag to both skills. When set, Step 2 skips the agent spawn and reads the file as-is.
- Free-text `NEW_*_TESTS_NEEDED` is converted to the on-disk JSON either by the Bug Review Agent or by a small helper subagent.

**Pros**

- Surgically minimal change to the *skill internals* — Step 2 just toggles between "spawn agent" and "read existing file."
- The on-disk JSON file already is the single source of truth in the existing flow; we're just shifting who writes it.
- Discovery output and writer input are guaranteed coherent (same schema).

**Cons**

- Two state channels (`--handoff-file` for inputs, pre-written JSON for scope, `--skip-discovery` flag) — high risk of drift if any one is missing or stale across re-runs.
- Pre-writing a file at a path determined by `BRANCH_SLUG` couples the orchestrator to the skill's internal directory layout. If the skill ever changes its `$WORK_DIR` convention, the orchestrator silently breaks.
- Same impedance problem as C: someone still has to convert free-text descriptions into structured records — just relocated upstream into the orchestrator.
- Component-test's Step 2 also runs `EXISTING_COMPONENT_TESTS` filtering and `already_covered` checks ([`boundary-mapper-prompt.md:53-59`](commands/component-test/boundary-mapper-prompt.md#L53)). Skipping discovery skips that pass — every pre-supplied boundary lands in the active list whether or not it's already covered.

**Change footprint (~5 files)**

- `commands/resolve-issue.md`: write the JSON files + use new flag. ~25 lines, including format conversion.
- Both skills: add `--skip-discovery`, branch in Step 2. ~10 lines each.
- Discovery-agent prompts: untouched (they don't run).
- New "boundary translator" logic somewhere upstream. ~unbounded lines.

### Option E (discovered) — Make Step 2g a different skill

**Mechanism**

- Don't try to reshape `/component-test` and `/integration-test`. Define `/component-test-targeted` and `/integration-test-targeted` as separate skills that take pre-supplied boundary descriptions and reuse the Test Writer + Negative Control / Falsifiability stages of the existing skills.
- Step 2g calls these new skills instead.

**Pros**

- Zero risk of polluting the Class A path's contracts. The existing skills stay focused on "discover from scratch."
- The targeted skills can have different tradeoffs (e.g., no `already_covered` filtering since the Fix Planner already considered that).

**Cons**

- Code duplication: framework discovery, writer spawning, sabotage / falsifiability orchestration would need to be either copy-pasted or extracted. Big refactor.
- Adds a new command surface to maintain.
- Doesn't actually fix the Step 2g bug today; it's a longer-term restructuring.

**Change footprint** — large (~3+ new files).

## 5. Recommendation

**Option A, with one structural assist from C.**

Concretely:

1. Land Option A first. Add `--boundaries "<text>"` to both skills' `Args`. In Step 2, the discovery agent receives the override text and is instructed to **rank/seed candidates from the text but still do the grep work** to populate `caller_files`/`http_entry_points`/`layers_involved`/`already_covered`. If the agent cannot find a real call site for an item in the override list, it reports it under `excluded` with reason `OVERRIDE_NOT_FOUND` — orchestrator surfaces this as a NON_SIMPLE_BUGS entry but does not fail. This preserves the current "every boundary is verifiable against the call graph" invariant ([`boundary-mapper-prompt.md:5`](commands/component-test/boundary-mapper-prompt.md#L5), [`feature-scope-prompt.md:7`](commands/integration-test/feature-scope-prompt.md#L7)).
2. After A is stable, evaluate whether Step 2g's CLI string is brittle in practice. If yes, migrate to Option C (structured scope file) — at which point the Fix Planner emits a JSON sidecar and the skills add `--scope-file` as an alternative (not a replacement) channel. Option A and Option C can coexist cleanly: `--scope-file` wins if both are present.

**Why not B, D, or E.**

- B mixes upstream contracts and forces awkward HANDOFF rewrites.
- D bypasses the discovery agent's `already_covered` filtering and validation pass — the Class B path would then write tests that duplicate existing coverage. Also brittle to internal path layout.
- E is a real future option but is a refactor, not a fix.

**Migration cost (Option A only).**

- 4 files: `resolve-issue.md` (no edit, but verify quoting in the spawn line), `component-test.md`, `integration-test.md`, `boundary-mapper-prompt.md`, `feature-scope-prompt.md`.
- Roughly 50–80 lines of additions across the four edited files. No deletions. No data migration. Backwards compatible (skills without `--boundaries` behave exactly as today).

## 6. Open questions

1. **Override semantics.** When `--boundaries "auth→token, login→session"` is passed, is that an *exhaustive whitelist* (only those, no others) or a *priority seed* (always those, plus anything else the discovery agent finds)? The Step 2g phrasing "focused invocation" suggests whitelist. Confirm.
2. **Failure mode when an override description doesn't match a real call site.** Hard fail? Drop with a NON_SIMPLE_BUGS entry? Pass through to writers with empty `caller_files` and let the writer fail? Recommendation: NON_SIMPLE_BUGS with `FAILURE_REASON=OVERRIDE_NOT_FOUND`, do not block.
3. **Free-text format.** Are descriptions guaranteed to be parseable as discrete items by splitting on `,`? Is there a need for a stricter Fix Planner output (e.g., each item on its own line, or `id|description` pairs)? Recommendation: tighten the Fix Planner contract to one description per `;`-delimited entry to avoid collisions with commas inside descriptions.
4. **`HANDOFF_FILE` in Step 2g points at the Assessment HANDOFF, not the Bug Review HANDOFF.** Is that intentional? It means the skill sees the original `IMPACT_SET`, not the post-fix files. Probably fine for Class B (the fix is `CONTAINED`), but worth a sentence in `resolve-issue.md` Step 2g making this explicit.
5. **Should `already_covered` filtering still run on overridden boundaries?** Fix Planner already inferred "not already covered" by definition — re-running the filter could drop boundaries the planner deliberately picked. Recommendation: when override is set, log `already_covered` for visibility but do not drop on it.
6. **One level of automated repair only** ([`resolve-issue.md:508`](commands/resolve-issue.md#L508)). If a Step 2g run produces its own NON_SIMPLE_BUGS, those are informational. Confirm that an `OVERRIDE_NOT_FOUND` entry routing to NON_SIMPLE_BUGS does not loop back into the Bug Review path.
