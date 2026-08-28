---
name: pr-review-cycle
description: "Drive review of an open PR to completion: pr-reviewer agent gathers tiered findings, triage into fix / propose / escalate, apply and verify repairs, validate intent, push. Run after the PR is open and before finalizing."
disable-model-invocation: true
---

# PR Review Cycle

Review findings come from the `pr-reviewer` custom agent (`~/.claude/agents/pr-reviewer.md`)
— its tier definitions are the quality gate and are never restated or overridden here. This
skill owns sequencing, triage, fixing, verification, and reporting.

## Setup

1. **Git root** (dev-container safe — the shell may start at `/workspaces`, above the mount):
   ```bash
   GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
   if [ -z "$GIT_ROOT" ]; then
     for candidate in /workspaces/* /workspaces/*/* "$HOME"/repos/* "$HOME"/projects/* "$HOME"/*; do
       [ -d "$candidate/.git" ] && { GIT_ROOT="$candidate"; break; }
     done
   fi
   ```
   Still empty → stop; tell the user to run from inside a repo or pass the path as first arg.
   **All git commands run from `GIT_ROOT`** (`git -C "$GIT_ROOT" …`).
2. **Scratch dir**: require `$GIT_ROOT/.agent-work/`; if missing, stop and tell the user to
   `mkdir -p $GIT_ROOT/.agent-work && echo '.agent-work/' >> $GIT_ROOT/.git/info/exclude`.
   All artifacts live there, gitignored via info/exclude, never committed.
3. **Args**: `/pr-review-cycle [repo-path] [branch] [cycles]` — repo-path when cwd is outside
   the repo; branch defaults to current; cycles default 2 (a bare integer first arg is cycles).
   The Reviewer runs `cycles + 1` times: once per fix cycle plus a final read-only review.
4. **Dirty-tree check**: if the working tree has uncommitted changes, stop and warn — never
   mix pre-existing changes with review fixes.
5. **PR**: `gh pr list --head <branch>` — none found → stop. Fetch metadata + diff. If the PR
   has zero reviews, set `NEEDS_INITIAL_REVIEW=true`.
6. **Capture pre-loop HEAD** before any Fixer commits — the boundary between what the author
   wrote and what the loop added:
   ```bash
   git -C "$GIT_ROOT" rev-parse HEAD > "$GIT_ROOT/.agent-work/PRE_LOOP_HEAD.sha"
   ```
7. **Review bundle** — write `.agent-work/REVIEW_BUNDLE.md` once, reused by every Reviewer
   spawn this run: PR metadata + body, full `gh pr diff` in a fenced block, repo `CLAUDE.md`,
   global `~/.claude/CLAUDE.md`, first 200 lines of `docs/agent_index.md` if present.

## Loop

Repeat while `CURRENT_CYCLE ≤ MAX_CYCLES`; then always run a Final Review and Intent
Validation. If `NEEDS_INITIAL_REVIEW`, run one extra Reviewer pass first and post its findings
as a PR review comment (read-only — the comment states which findings will be auto-applied vs.
surfaced for author decision) before entering cycle 1.

**Reviewer** (per cycle): spawn the `pr-reviewer` agent with the bundle path and output path
`.agent-work/REVIEW_FINDINGS_<N>.md`.

**Early exit**: zero critical or major tier-`fix` findings at the start of a cycle → skip
straight to Final Review. `propose`/`escalate` findings never trigger fix cycles.

**Post-rebase validation**: if the branch was rebased since the last cycle, run the full test
suite and diff pre/post-rebase state of changed files before the Reviewer starts; any
regression is a Critical finding fixed before all others that cycle.

### Triage (orchestrator — never writes code itself)

Only tier-`fix` findings are eligible for Fixers. Build `.agent-work/FIX_PLAN_<N>.md`:

- **Dependency graph**: findings are independent only if they touch different files or
  provably non-overlapping, non-interdependent sections and neither fix could invalidate the
  other. Same function/class, shared signatures, or state ordering → dependent, serial.
- **Default to serial** unless ≥5 actionable tier-`fix` findings this cycle — below that,
  coordination overhead outweighs parallelism. When in doubt, serial.
- A tier-`fix` finding that turns out to need a human decision is promoted to `propose` —
  a finding that needs a decision is definitionally not tier `fix`. Never the reverse.
- Critical before minor within a dependency chain.

**Surface non-fix findings** before running any Fixer: post `propose` diffs and `escalate`
issue drafts as one PR comment wrapped in `<!-- review-fix-proposals -->` markers. Post once
per cycle, only for findings not already in an earlier cycle's comment (de-dupe by title+file).

### Fixers (one per finding, parallel within a batch)

Each Fixer applies exactly one finding — never reviews, never fixes other things noticed along
the way. Prepend the context bootstrap (read global + repo `CLAUDE.md`, codebase index).
Refusal gates, in order:
1. **Tier gate**: tier ≠ `fix` → refuse, write `Status: refused — tier <X>`.
2. **Scope gate**: would the fix introduce a new module, public type, schema field, or exceed
   ~20% of the PR's own diff size? → refuse — should have been `escalate`.
3. **Tightening override** — refuse as decision-required regardless of the finding's flags if
   the fix would add: a guard, validation gate, enforcement constraint, or error promotion
   absent from the original code; shape expansion of a public data structure (new response
   fields, flat→nested, widened payload, on-disk schema); a new abstraction layer; or a change
   to a persisted format.
4. Otherwise apply; where two equivalent spellings of the same fix exist, choose the one that
   preserves the closest-preceding documented intent (PR body, linked issue, docstring), and
   record the decision with options considered.
5. **Impact trace** (required for critical/major): every caller of the changed function and
   whether the fix invalidates its assumptions; callees added/removed and their side-effects.
6. Write `.agent-work/FIX_RESULT_<id>.md`: status (fixed|skipped|blocked|refused), files,
   decision, impact trace. Final message: `DONE` or `BLOCKED(reason)` — never a question.

### Verify + commit (per batch)

- Re-read touched files; run tests if detectable. Any fix broke another → resolve before the
  next batch.
- Critical/major results missing `## Impact Trace` → back to the Fixer queue before commit.
- **Fixture-edit check**: a fix touching both production code and a test fixture / conftest /
  setup function requires a `## Fixture Change Justification` stating which behavior contract
  changed and whether a new test pins it — otherwise revert the production change or add the
  test. Never commit a fixture patch alone (fixture edits are the classic masking signal for a
  silently altered contract).
- Commit per batch, only the batch's files — never `git add -A`. Tests fail → do NOT commit;
  flag the batch for manual review and continue. Never merge, never force-push, never push to
  main. Push the branch after all batches.

## Intent Validation (always, after Final Review)

Purpose: verify the automated loop did not revert, weaken, or contradict the *original intent*
of the PR — reviewers optimize for quality signals; this pass optimizes for functional
correctness of the author's fix.

**SHA reachability guard** — before assembling the bundle:
```bash
PRE_LOOP="$(cat "$GIT_ROOT/.agent-work/PRE_LOOP_HEAD.sha")"
git -C "$GIT_ROOT" cat-file -e "$PRE_LOOP^{commit}" 2>/dev/null || {
  echo "pre-loop HEAD no longer reachable — the branch was rebased mid-loop;"
  echo "the fix-loop diff cannot be reconstructed. Re-run from scratch on the rebased branch."
  exit 1; }
```
A mid-loop rebase orphans the saved SHA and poisons the fixer diff — this guard exists because
it happened.

Write `.agent-work/INTENT_BUNDLE.md` (pre-loop SHA, PR metadata, `git log` and `git diff
PRE_LOOP..HEAD`, repo context) and spawn a read-only validator agent (opus) on it. It compares,
per file touched by both the original diff and the loop's commits, what the author changed vs.
what the fixers changed, hunting these failure patterns: **ordering reversals** (style fix
undoes order-dependent correctness, e.g. `load_dotenv()` before env-reading imports), **guard
removal**, **guard addition** (fixer-added enforcement absent from the original and the spec —
fixture edits alongside are the masking signal), **logic inversion** (polarity flipped in a
clarity refactor), **dead code** (original fix path now unreachable), **config/env
neutralisation**, and **tier overreach** (a committed change whose footprint belonged in
`propose`/`escalate` — design work smuggled through the auto-apply path). Findings:
`[INTENT-RISK: high|med|low]` with original intent, pre/post-loop quoted state, risk,
recommended action → `.agent-work/INTENT_VALIDATION.md`, or "No intent risks detected."

## Wrap-up

1. Commit residual tracked changes only (`git add -u`, commit only if staged non-empty), push.
   Push fails → report and stop; do not hand off to finalization.
2. Present the human summary in conversation: cycles run (note early exit), per-cycle finding
   counts, all fixes applied with commits, decisions made (**flag each for CONFIRM/OVERRIDE**),
   proposed and escalated findings, failed batches, outstanding findings, intent-validation
   results in full.
3. Post the summary to the PR wrapped in `<!-- review-fix-summary -->` /
   `<!-- review-fix-summary-end -->` markers — downstream finalization locates the comment by
   these sentinels, so post it even when the review is clean. Never truncate the
   intent-validation section. If intent validation didn't run, say "Intent validation: not run."

## Constraints

- Minimal, targeted fixes — no refactoring beyond a finding's direct cause.
- Respect the three-tier split absolutely: never upgrade a tier to get past the auto-apply
  gate; downgrade freely.
- Never merge; never force-push; stop if `gh` is unavailable.
- When handing to a human, always include the PR URL.
