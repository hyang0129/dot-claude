# /pr-review-cycle — improvement plan

Generated 2026-04-22. Based on analysis of 51 sessions over the past 60 days.

- Total ROOT-session spend across those sessions: **$756** (after the scanner
  was tightened to exclude pre-command sibling subagents and post-summary
  user-continuation work)
- Skill-attributable portion: **$505** (excludes R-PRE, R-DONE, OTHER)
- Top phases: **REV $275 (54.5%)**, INT $62 (12.4%), R-SETUP $39 (7.7%),
  R-POST-REV $39 (7.7%), R-POST-INT $34 (6.8%), FIX $29 (5.8%), R-POST-FIX
  $26 (5.1%)

See source reports:
- [Broad scan](pr-review-cycle-60d.md)
- Reviewer drills: [d2987528 (PR #886)](analyze-d2987528-reviewer.md), [d9a8b6e1 (PR #679)](analyze-d9a8b6e1-final-reviewer.md)
- Intent-Validator drills: [bc611316 (PR "the PR")](analyze-bc611316-int.md), [04a4bd9a (PR #825)](analyze-04a4bd9a-int.md)
- R-POST-INT drills (informed the scanner tightening, no action): [d30f23fd](analyze-d30f23fd-post-int.md), [d2987528](analyze-d2987528-post-int.md)

**Guiding constraint from user:** the Reviewer is a critical quality gate.
No change may weaken review depth or coverage. Cost reductions must come from
removing mechanical ceremony, not from cutting the spec.

---

## I-1 — Bundle diff + touched-file contents into the Reviewer AND Intent Validator spawn prompts

### Problem

The Reviewer subagent is the single most expensive phase across all sessions:
**REV $275 / 60d (36% of grand, 54.5% of attributable)** after tightening the
scanner. The Intent Validator exhibits the same inefficiency at smaller scale:
**INT $62.53 / 60d (12.4% of attributable)**, across 53 runs averaging $1.18.
Both drilled sessions for each phase show the same shape:

**Reviewer:**
- d2987528 — 21 turns, $4.46 (opus-4-7): Read 11× / Grep 7× / Bash 2× / Write 1×
- d9a8b6e1 — 60 turns, $11.25 (opus-4-6): Read 38× / Grep 19× / Bash 2× / Write 1×

**Intent Validator:**
- bc611316 — 23 turns, $3.51 (opus-4-7): Read 14× / Grep 5× / Bash 2× / Write 2×
- 04a4bd9a — 13 turns, $3.03 (opus-4-7): Read 5× / Grep 1× / Bash 7× / Write 1×

The first 7–15 turns of the **Reviewer** are pure mechanical ceremony:
1. `Read CLAUDE.md` (always, ~19K cw)
2. `Bash(ls .agent-work; ls agent_index.md)`
3. `Read agent_index.md`
4. `Read .agent-work/PR_DIFF.txt` — often read twice, each time triggering a
   ~15K-token cache-write because the diff is a new file to the subagent
5. `Read <touched file 1>`, `Read <touched file 2>`, … — once per touched file
6. Then a long tail of `Grep` for callers and analogous patterns

The **Intent Validator** has the same shape with different content. Its first
3–7 turns are:
1. `Bash(git diff <base>...<pre-loop-head>)` to get the original PR state
2. `Bash(git log/diff)` to get the auto-fix commits added by the loop
3. `Read` each file that appears in both diffs
4. Compare pre-loop vs post-loop intent, Write `INTENT_VALIDATION.md`

In 04a4bd9a the two most expensive turns are a 35K cache-write Reading
`worker_cli.py` and a 20K cache-write Reading two agent modules.

Every turn after the first replays the full accumulated context as cache-read.
That replay is ~80% of both subagents' bills: per-turn cost $0.16–0.45 even
when the turn does nothing but a single `Read` with 1 output token. Cost grows
roughly linearly with PR size (turn count).

### Evidence

| Subagent | Session | Turns | Cost | Read | Grep | Bash |
|---|---|---|---|---|---|---|
| Reviewer | d2987528 | 21 | $4.46 | 11 / $2.55 | 7 / $1.20 | 2 |
| Reviewer | d9a8b6e1 | 60 | $11.25 | 38 / $7.11 | 19 / $3.52 | 2 |
| Intent Validator | bc611316 | 23 | $3.51 | 14 / $2.15 | 5 / $0.69 | 2 |
| Intent Validator | 04a4bd9a | 13 | $3.03 | 5 / $1.75 | 1 / $0.20 | 7 / $1.23 |

The single most expensive Reviewer turn (`$0.40–0.45`) first Reads
`PR_DIFF.txt` — a 15–20K-token cache-write paid inside the subagent.

### Proposed actions

Have ROOT (or a Preparer delegate) assemble **bundles** *before* spawning the
expensive read-only subagents, and pass each bundle inline in its spawn prompt
so the subagent arrives with every document it needs already in context.

Two distinct bundles are required because the Reviewer and Intent Validator
compare different states:

| Bundle | For | Contents |
|---|---|---|
| `REVIEW_BUNDLE.md` | Reviewer (all cycles + Final Reviewer) | PR metadata · full `gh pr diff` · current contents of touched files · CLAUDE.md · index excerpt |
| `INTENT_BUNDLE.md` | Intent Validator (runs once at end) | Pre-loop PR diff (the original author's intent) · post-loop commits diff (what the fix-loop added) · current contents of files touched by *either* diff · CLAUDE.md · index excerpt |

- [ ] 1. In R-SETUP, after resolving PR metadata, ROOT runs a single
  preparation step (inline Bash, no new subagent) that writes
  `.agent-work/REVIEW_BUNDLE.md` containing:
    - PR metadata (title, body, base, head, additions, deletions)
    - Full `gh pr diff <num>` output
    - For each touched file (from `gh pr view --json files`): **current
      contents** wrapped in `<file path="...">...</file>` tags
    - A size-capped excerpt (first ~200 lines) of `$GIT_ROOT/docs/agent_index.md`
      or `.codesight/CODESIGHT.md` if present
    - The global + repo `CLAUDE.md` files (they are both small)
- [ ] 2. Immediately before the Intent Validator spawn (after all fix cycles
  complete), ROOT assembles `.agent-work/INTENT_BUNDLE.md`:
    - **Pre-loop diff**: the contents of `.agent-work/PR_DIFF.txt` captured
      in R-SETUP (this is the original author's PR state)
    - **Post-loop diff**: `git log <pre-loop-head>..HEAD` + `git diff
      <pre-loop-head>..HEAD` covering only the commits the fix-loop added
    - **Touched-file contents**: current full contents of every file that
      appears in *either* diff (these are the files where intent risks live)
    - CLAUDE.md + index excerpt (same as REVIEW_BUNDLE)
    - ROOT must capture `<pre-loop-head>` at R-SETUP before the first Fixer
      commit; store it in `.agent-work/PRE_LOOP_HEAD.sha`
- [ ] 3. Apply a **size cap** on each bundle: if the assembled bundle exceeds
  `BUNDLE_SOFT_CAP_LINES=5000` lines, drop per-file contents but keep the
  diffs; mark `BUNDLE_TRUNCATED=true` in the header so the subagent knows to
  fall back to `Read` on demand.
- [ ] 4. Change the Reviewer subagent's spawn prompt from "review PR #N" to:

  > You are reviewing PR #N. Produce `.agent-work/REVIEW_FINDINGS_<cycle>.md`
  > per the spec below. The PR diff, current contents of touched files, and
  > repo context are **already in your prompt** — do not Read them again. Use
  > Read/Grep only for files not included here (e.g. callers, analogous
  > patterns elsewhere in the codebase), and only when your review genuinely
  > needs them.
  >
  > `<REVIEW_BUNDLE contents>` + `<original spec>`
- [ ] 5. Change the Intent Validator's spawn prompt similarly:

  > You are performing intent validation on PR #N. Produce
  > `.agent-work/INTENT_VALIDATION.md` per the spec below. The pre-loop diff
  > (original author's intent), the post-loop fix commits, and the current
  > contents of all affected files are **already in your prompt** — do not
  > Bash `git diff` or Read them again. Use Read/Grep only if you need to
  > check a caller or invariant elsewhere in the codebase.
  >
  > `<INTENT_BUNDLE contents>` + `<original spec>`
- [ ] 6. Remove the existing Context Bootstrap preamble for the Reviewer and
  Intent Validator specifically (it's now redundant — the bundles already
  contain CLAUDE.md and the index excerpt). Keep the bootstrap for the Fixer
  since it doesn't receive a bundle.

### Expected impact

**Reviewer** — per-invocation cost drops from **$3–11** (model-dependent,
scales with PR size) to **~$1–2**:
- Turn 1 pays one cache-write for the assembled bundle (~30–60K tokens for a
  median PR) → ~$0.60–1.10 on opus-4-7, ~$0.12–0.22 on sonnet-4-6.
- Subsequent turns are only emitted when the Reviewer genuinely needs an
  out-of-bundle Grep (callers, cross-file patterns), typically 2–5 turns max.
- Write of `REVIEW_FINDINGS_<cycle>.md` = 1 turn.

**Intent Validator** — per-invocation cost drops from **~$1.20 avg** to
**~$0.30–0.60**:
- Bundle is typically smaller than the Reviewer bundle (only files in the
  pre+post-loop diff union, not all PR-touched files).
- Turn 1 pays ~$0.20–0.40 cache-write on opus-4-7 for a median case.
- Emits findings in 2–4 more turns; Write `INTENT_VALIDATION.md`.

**Population estimate:**
- REV: $275 → ~$60–90 / 60d → **savings ~$185–215**
- INT: $63 → ~$20–30 / 60d → **savings ~$33–43**
- **Combined: ~$220–260 / 60 days (≈$27–32 / week)**

Marginal cost to add the Intent Validator bundle on top of the Reviewer
bundle: the Preparer logic is reused almost verbatim with a different file
list, so engineering effort is +10–20% of the Reviewer-only version.

### Risk

1. **Subagent misses out-of-bundle context.** Pattern-consistency and
   test-coverage-validity checks sometimes require reading callers of touched
   functions — those files are not in the bundle. Mitigation: both specs
   already tell the subagents to grep for analogues; they can still do that
   as-needed.
2. **Oversized bundles on monster PRs.** A 30-file refactor could blow up the
   bundle to 100K+ tokens and the cache-write cost spikes. Mitigation: the
   size cap (action 3) falls back to diff-only so the worst case is the
   current behaviour minus one redundant `Read PR_DIFF.txt`.
3. **Binary / generated files leak into bundle.** `gh pr view --json files`
   includes minified JS, lock files, generated schemas, etc. Mitigation: skip
   any file matching `*.lock`, `*.min.js`, `*-lock.*`, `*.generated.*`,
   `dist/**`, `build/**`; truncate individual files to 1000 lines.
4. **ROOT pays to assemble.** Two bash/disk-read steps on Opus ROOT at
   ~$0.20–0.50 each. Net cost is still strongly negative.
5. **Pre-loop-head SHA lost on rebase.** If the user rebases mid-loop, the
   stored `<pre-loop-head>` may no longer exist. Mitigation: capture the SHA
   at R-SETUP into `.agent-work/PRE_LOOP_HEAD.sha`; if it's unreachable at
   Intent Validator time, fall back to `git log origin/<base>..HEAD` and mark
   `INTENT_BUNDLE_DEGRADED=true` in the bundle header. Intent Validator then
   Bashes `git` itself as a safety net.
6. **Intent Validator's pre-loop diff is now assembled server-side, not
   verified.** The original skill had the subagent reconstruct the pre-loop
   diff via `git log --oneline`. With bundling, ROOT hands it the diff
   directly. Bug in the preparer could mislead the validator. Mitigation:
   include the `<pre-loop-head>` SHA in the bundle header so the validator
   can cross-check if it distrusts the handed diff.

### Acceptance check

For a representative PR (≥3 touched files, <20 lines changed per file):
- **Reviewer** turn count drops from current baseline (15–25 turns) to
  **≤ 6 turns**; phase cost drops to **≤ 33% of baseline**.
- **Intent Validator** turn count drops from current baseline (10–20 turns)
  to **≤ 5 turns**; phase cost drops to **≤ 40% of baseline**.
- `REVIEW_FINDINGS_<cycle>.md` still contains findings on the same 2–3 seeded
  issues that the current Reviewer catches (manual A/B check on 2 real PRs).
- `INTENT_VALIDATION.md` still catches a deliberately-seeded intent-risk
  scenario (e.g. an automated fix that reverses statement ordering in a
  load-bearing block) — run on a contrived PR if no real one is available.

---

## I-2 — Configurable `--reviewer-model` flag (default `claude-opus-4-7`)

### Problem

The Reviewer's model is hard-coded in the skill file as
`model: "claude-opus-4-6"`. To run an A/B test (e.g., sonnet-4-6 vs opus-4-7
on review quality, once bundling is in place) we need to be able to change
the model per-invocation without editing the skill.

A/B data will also inform whether the long-term default should stay on Opus
or move down. Until that data exists, default stays on the highest-quality
tier: **`claude-opus-4-7`** (the current latest, and the model the most recent
session actually used).

### Proposed actions

- [ ] 1. In the **Parse arguments** section, after the positional parsing,
  scan the remaining argv for a named flag `--reviewer-model=<model-id>` and
  set `REVIEWER_MODEL` from it. If the flag is absent, default to
  `claude-opus-4-7`.
- [ ] 2. Accept the flag anywhere in argv (before, between, or after the
  positional args) to keep invocation ergonomic:
    - `/pr-review-cycle --reviewer-model=claude-sonnet-4-6`
    - `/pr-review-cycle feature/xyz 3 --reviewer-model=claude-opus-4-7`
    - `/pr-review-cycle ~/repos/foo --reviewer-model=claude-sonnet-4-6`
- [ ] 3. Validate the value against a known list: `claude-opus-4-7`,
  `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`. On unknown
  value, stop and tell the user the allowed set.
- [ ] 4. Change the Reviewer agent definition from literal
  `model: "claude-opus-4-6"` to reference `$REVIEWER_MODEL` in the spawn
  prompt. Example edit at line 102:

  Before:
  > ### Agent 1 — Reviewer (`model: "claude-opus-4-6"`)

  After:
  > ### Agent 1 — Reviewer (`model: $REVIEWER_MODEL`, default `claude-opus-4-7`)

  And in the coordination flow where the Reviewer is spawned, pass
  `model: $REVIEWER_MODEL` explicitly.
- [ ] 5. **Do not** make Intent Validator or Fixer configurable in this
  change. Intent Validator is quality-critical and low-frequency; Fixer is
  already Sonnet. Scope creep to "all models configurable" is rejected — the
  only A/B test we're setting up right now is Reviewer.
- [ ] 6. Log the chosen model in the Human Review Summary and the PR comment:
  > **Reviewer model:** claude-opus-4-7 (default)
  >
  > so retrospective A/B analysis can attribute findings to model without
  > parsing logs.

### Expected impact

Zero direct cost change at default settings (opus-4-7 ≈ same price as
opus-4-6). Enables the A/B experiment. If post-experiment we flip the default
to sonnet-4-6, compounded savings on top of I-1 are an **additional ~$40–60 /
60 days** (Reviewer is already small after bundling; Sonnet shaves another
~60% off the residual).

### Risk

1. **Model-ID drift.** Hard-coding a short allow-list will need updating when
   new models ship. Mitigation: accept the list explicitly, revisit quarterly.
2. **Inconsistent A/B data.** If users inadvertently pick the flag mid-cycle,
   cycle 1 and cycle 2 could run different models. Mitigation: the flag is
   parsed once at setup; it binds for all cycles in that invocation.
3. **Forgotten override.** User sets `--reviewer-model=sonnet` for one PR,
   forgets, ships a buggy finding. Mitigation: the summary-posted-to-PR
   (action 6) surfaces the model explicitly so reviewers see what was used.

### Acceptance check

- `/pr-review-cycle` with no flag uses `claude-opus-4-7`; PR comment footer
  reads "Reviewer model: claude-opus-4-7 (default)".
- `/pr-review-cycle --reviewer-model=claude-sonnet-4-6` runs Reviewer on
  Sonnet end-to-end; PR comment footer reads the non-default model.
- Unknown model id exits with a clear error listing allowed values; does not
  fall through to the default silently.

---

## Explicit non-goals for this plan

Listed so future analyses don't re-surface them as "missed":

- **Cross-cycle cache reuse of the bundle.** Estimated savings ~$0.30/week;
  complicated by the 5-minute default cache TTL vs 10–30 min inter-cycle
  gaps. Not worth the complexity.
- **Splitting the Reviewer into N parallel per-file reviewers.** Coordination
  overhead and merging-findings cost outweighs the benefit on the typical
  3–6-file PR we see.
- **Trimming the Reviewer's checklist.** User explicitly designated this
  phase as a quality gate. Cost savings from spec-trimming come at the direct
  cost of review depth; rejected.
- **Making Fixer / Intent Validator *model* configurable.** Scope creep for
  I-2. Intent Validator *does* get bundled by I-1 (same mechanism, different
  bundle), but its model stays pinned at Opus. Re-examine configurability only
  if a future analysis shows Fixer or post-bundling Intent costs >15% of
  attributable total.

- **Merging Final Reviewer + Intent Validator into a single subagent.** One
  drilled user (bc611316) already does this manually via a combined spawn;
  the skill's current coordination flow spawns them in parallel in a single
  ROOT turn, which gets most of the benefit. Merging them conceptually
  changes the contract (two separate deliverables, two separate output
  files) — rejected as scope creep. Revisit only if bundling lands and the
  two agents still look redundant.

---

## Sequencing

Both changes are additive and independent:

- **Wave 1 — I-2 (reviewer-model flag):** text-only change in the skill file.
  Zero structural risk. Ship first so we have a way to dial the model
  separately from bundling.
- **Wave 2 — I-1 (bundling, Reviewer + Intent Validator):** requires two
  new Bash preparation steps (one in R-SETUP for the review bundle, one
  immediately before Intent Validator spawn for the intent bundle), shared
  bundle size-cap / binary-filter logic, and prompt restructuring on both
  subagents. Medium structural risk, contained to the two spawn paths. Ship
  the Reviewer half first, then the Intent Validator half, so each half is
  independently verifiable against its acceptance check.

An implementation plan document (`pr-review-cycle-plan.md`) will expand these
waves with literal text edits, conflict resolution, and wave-level acceptance
checks.
