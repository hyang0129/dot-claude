# /fix-issue Planner improvement plan — Sonnet + bounded reads

Decision: switch the Planner subagent from Opus to Sonnet, and add a
two-sentence prompt instruction telling it to use bounded Reads on large
files.

**Rationale.** In the 14-day window, the Planner subagent costs $67.13
across 27 invocations ($2.49 mean). Drilling shows that ~70% of that cost
is `mech_silent` turns — Opus tool-call ceremony with median 41 output
tokens, just deciding which file to grep next. Sonnet does that decision
identically at ~5× cheaper cache rates. The only turn that benefits from
Opus judgment is the final synthesis Write of the plan document (~7% of
cost) — and at $0.44 per Write turn the saving from also routing that to
Sonnet is small relative to the quality risk, so we move the whole
subagent and accept the synthesis-quality tradeoff.

The prompt addition attacks the secondary cause: the Planner currently
Reads whole files by default, so every byte enters its context permanently
and is paid for again on every later turn. Telling it to use offset/limit
on >300-line files trims the 49.9% cache-write share without any
architectural change.

---

## Expected impact

| Metric | Before (14d) | After (est.) | Delta |
|---|---|---|---|
| Planner cost | $67.13 | $11–13 | ~−$55 |
| Per-invocation Planner mean | $2.49 | $0.45 | ~−$2.04 |
| Planner share of skill total | 10.9% | ~2% | — |

This stacks on top of the prior Reviewer-removal plan. Combined estimate
for both changes: ~$278/14d saved (~45% off the skill).

## Risk

**Risk 1: Sonnet produces a weaker plan than Opus, causing wasted Coder
waves downstream.** Realistic — Sonnet is less likely to surface
non-obvious architectural concerns. Mitigations:
- The plan still gets reviewed downstream by `/pr-review-cycle` (per the
  prior decision to drop Step 5 from `/fix-issue`). A weak plan that
  produces a bad PR gets caught at review time, not at merge time.
- For Tier-3 issues, the Architect is still spawned (and stays on Opus
  per Step 2b). Sonnet only plans; Opus still arbitrates open architectural
  questions.
- If a specific category of plan turns out to be reliably wrong on Sonnet,
  we revisit. Easy to revert: it's a one-word change.

**Risk 2: bounded-read instruction confuses Sonnet into missing context
it needed.** Low. The instruction is permissive ("use offset/limit when
files are large") not prohibitive ("never Read whole files"). Sonnet can
ignore it when whole-file context is genuinely needed.

**Risk 3: latency.** Sonnet turns are typically faster than Opus, so the
total Planner wall-clock time should drop slightly. No latency regression
expected.

---

## Wave 1 — text-only edits to `commands/fix-issue.md`

All edits live in Step 2's Planner agent section (lines ~310–390). Zero
structural risk.

### 1.1 Change Planner model from Opus to Sonnet
- [ ] At line 312, change:
      ```
      Regardless of tier, spawn a **Planner agent** first (`model: "claude-opus-4-6"`).
      ```
      to:
      ```
      Regardless of tier, spawn a **Planner agent** first (`model: "claude-sonnet-4-6"`).
      ```

### 1.2 Add bounded-read instruction
- [ ] In Step 2 Planner instructions (the numbered list at line 314), find
      the "Search the codebase for all affected files" item (line ~324)
      and replace its sub-bullets:
      ```
      3. Search the codebase for all affected files:
         - Grep for symbols, function names, patterns mentioned in the issue
         - Read the files most likely involved
      ```
      with:
      ```
      3. Search the codebase for all affected files:
         - Grep for symbols, function names, patterns mentioned in the issue
         - Read the files most likely involved. When a file is >300 lines,
           use Read with offset/limit to load only the section Grep
           identified — do not Read entire test fixtures, lockfiles, or
           generated code. Whole-file Reads are only for short files or
           when you genuinely need the full context.
      ```

### 1.3 Copy the edited file into `~/.claude/commands/`
Per repo `CLAUDE.md`: `commands/` files are copied, not symlinked. After
editing the repo copy, manually copy into `~/.claude/commands/fix-issue.md`.

**Acceptance checks (Wave 1):**
- [ ] `grep -n "claude-opus" commands/fix-issue.md` no longer returns the
      Planner line — only Architect (line ~394) and any other
      intentionally-Opus subagents remain.
- [ ] `grep -n "offset/limit" commands/fix-issue.md` returns the new
      instruction.

---

## Things we are *not* doing

- **Not** routing Planner's final Write turn to Opus for synthesis.
  Adds a model-handoff step for ~$0.40/session of marginal Opus value.
  Not worth the prompt complexity. Sonnet does the Write fine.
- **Not** introducing an Explore sub-sub-agent to summarise files for the
  Planner (Lever 2 architectural option). After the Sonnet switch, the
  remaining cache I/O is small enough that the indirection isn't worth
  the plan-quality risk.
- **Not** adding a Tier-1 short-circuit that skips the Planner. Only 2
  Tier-1 sessions in the 14-day window — not enough volume to justify a
  separate code path.
- **Not** adding an Opus reviewer over the Sonnet plan. Considered and
  rejected — verifying a plan in vacuum can't catch the failure modes
  that matter (missed files), and the plan-quality safety net is provided
  by `/pr-review-cycle` downstream.

---

## Sequencing

Wave 1 can ship in the same `dot-claude` PR as the Step-5-removal plan
(`fix-issue-plan.md`). Both touch only `commands/fix-issue.md` and don't
conflict.
