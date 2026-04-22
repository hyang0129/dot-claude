# /pr-review-cycle — implementation plan

Companion to [pr-review-cycle-improvements.md](pr-review-cycle-improvements.md).
That doc explains *what* and *why*; this doc specifies *how* — literal edits
to [commands/pr-review-cycle.md](../../commands/pr-review-cycle.md) sequenced
into waves of increasing structural risk.

Target expected savings after all waves ship: **~$220–260 / 60 days**.

---

## Wave sequencing

| Wave | Scope | Risk | Expected saving / 60d |
|---|---|---|---|
| **W1** | I-2: add `--reviewer-model` flag, default `claude-opus-4-7` | text-only, zero | $0 at default; ~$40–60 additional if Sonnet wins A/B |
| **W2a** | I-1 part A: REVIEW_BUNDLE for Reviewer | medium | ~$185–215 |
| **W2b** | I-1 part B: INTENT_BUNDLE for Intent Validator | medium | ~$33–43 |

Each wave is independently shippable and has its own acceptance check.
Waves are strictly additive — later waves build on earlier ones but do not
require them, except as noted in the conflict-resolution section below.

---

## Wave 1 — `--reviewer-model` flag (text-only)

### Goal

Let callers override the Reviewer model per-invocation without editing the
skill. Default to `claude-opus-4-7`. Enables A/B testing of
reviewer-quality vs. model tier once W2 bundling makes the comparison fair.

### Edit 1-A — extend "Parse arguments" section (~line 46–60)

Insert a new subsection **after** the existing positional-argument parsing
and **before** "This means the Reviewer runs `cycles + 1` times total…":

```markdown
### Parse named flags

After positional argument parsing, scan the remaining argv for named flags.

**`--reviewer-model=<model-id>`** (default: `claude-opus-4-7`)
- Accept the flag anywhere in argv — before, between, or after positional args.
- Match with a regex like `^--reviewer-model=(.+)$` against each remaining
  token; on match, set `REVIEWER_MODEL` and remove the token from argv.
- Validate against this allow-list:
    - `claude-opus-4-7` (default)
    - `claude-opus-4-6`
    - `claude-sonnet-4-6`
    - `claude-haiku-4-5`
- If the value is not in the allow-list, stop and tell the user:
    > Unknown --reviewer-model=<value>. Allowed: claude-opus-4-7,
    > claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5.
- If the flag is absent, set `REVIEWER_MODEL=claude-opus-4-7`.
- `REVIEWER_MODEL` is bound for the entire invocation — all cycles run with
  the same model. It is NOT re-parsed per cycle.

This flag is exclusively for A/B testing Reviewer quality vs. cost. The
Fixer and Intent Validator models are not configurable at this time.
```

### Edit 1-B — Reviewer agent header (line 102)

Before:
```markdown
### Agent 1 — Reviewer (`model: "claude-opus-4-6"`)
```

After:
```markdown
### Agent 1 — Reviewer (`model: $REVIEWER_MODEL`, default `claude-opus-4-7`)
```

### Edit 1-C — spawn-time model reference

In the Coordination Flow section, wherever the Reviewer is spawned
(currently implicit in the flow diagram plus the "Initial Review" and
"Repeat while CURRENT_CYCLE ≤ MAX_CYCLES" sections), add an explicit
instruction:

```markdown
When spawning the Reviewer (Cycle N, Initial, or Final), pass
`model: $REVIEWER_MODEL` in the Agent tool call.
```

Place this instruction once, near the top of the "Coordination Flow"
section (~line 277), so all three spawn sites inherit it.

### Edit 1-D — Human Review Summary footer

In the "Human Review Summary" section (~line 366), insert a line after
`Cycles run:`:

```markdown
Reviewer model: $REVIEWER_MODEL<if default: " (default)">
```

### Edit 1-E — PR comment footer

In the "Post Final Summary to PR" section (~line 433), add this line to the
comment body, just above `### Final review state`:

```markdown
**Reviewer model**: $REVIEWER_MODEL<if default: " (default)">
```

### Acceptance check (Wave 1)

- [ ] `/pr-review-cycle` with no flag uses `claude-opus-4-7`; PR comment
  footer reads `Reviewer model: claude-opus-4-7 (default)`.
- [ ] `/pr-review-cycle --reviewer-model=claude-sonnet-4-6` runs the Reviewer
  on Sonnet end-to-end (all cycles + Final). PR comment footer omits
  ` (default)`.
- [ ] `/pr-review-cycle --reviewer-model=gpt-4` exits with the allow-list
  error. Does not silently fall through.
- [ ] Flag works with positional args in any order: both
  `/pr-review-cycle --reviewer-model=X feature/y` and
  `/pr-review-cycle feature/y 3 --reviewer-model=X` succeed.

### Conflicts

None with other waves. Wave 1 touches only the skill's argument-parsing and
Reviewer-header text. Both W2a and W2b will modify the Reviewer / Intent
Validator spawn *prompts*, not their header lines. If W1 and W2 ship
out-of-order, W2a must preserve the `model: $REVIEWER_MODEL` syntax
introduced here.

---

## Wave 2a — REVIEW_BUNDLE for the Reviewer

### Goal

Every Reviewer spawn (Initial, Cycle N, Final) receives the PR diff and
current contents of touched files inline in its prompt, eliminating the
current 10–40-turn Read/Grep ceremony.

### Edit 2a-A — add bundle-assembly step in Setup

Insert a new subsection in the "Setup" section, immediately **after**
"Check for existing reviews:" (~line 79) and **before** "Track state:":

````markdown
### Assemble review bundle

Write `.agent-work/REVIEW_BUNDLE.md` before the first Reviewer spawn. The
bundle is reused across all Reviewer invocations in this run.

```bash
PR_NUM=<pr-number>
BUNDLE="$GIT_ROOT/.agent-work/REVIEW_BUNDLE.md"

# PR metadata (top of bundle)
{
  echo "# Review bundle for PR #$PR_NUM"
  echo
  echo '## PR metadata'
  gh pr view "$PR_NUM" \
    --json number,title,body,baseRefName,headRefName,additions,deletions \
    --jq '"- Title: " + .title + "\n- Base: " + .baseRefName
          + "\n- Head: " + .headRefName
          + "\n- +" + (.additions|tostring) + " / -" + (.deletions|tostring)
          + "\n\n### Body\n" + .body'
  echo
  echo '## PR diff'
  echo '```diff'
  gh pr diff "$PR_NUM"
  echo '```'
  echo
  echo '## Touched files (current contents)'
} > "$BUNDLE"

# Per-file contents, skipping binary/generated patterns, capped at 1000 lines
SKIP_PATTERNS='\.lock$|-lock\.|\.min\.(js|css)$|\.generated\.|^(dist|build|node_modules)/'
gh pr view "$PR_NUM" --json files --jq '.files[].path' | while read -r f; do
  if [[ "$f" =~ $SKIP_PATTERNS ]] || [[ ! -f "$GIT_ROOT/$f" ]]; then
    printf '\n<file path="%s" skipped="binary-or-generated"/>\n' "$f" >> "$BUNDLE"
    continue
  fi
  printf '\n<file path="%s">\n```\n' "$f" >> "$BUNDLE"
  head -n 1000 "$GIT_ROOT/$f" >> "$BUNDLE"
  printf '\n```\n</file>\n' >> "$BUNDLE"
done

# Repo + global context at the bottom (smallest, least hot)
{
  echo
  echo '## Repo context'
  [ -f "$GIT_ROOT/CLAUDE.md" ]          && { echo '### $GIT_ROOT/CLAUDE.md';   cat "$GIT_ROOT/CLAUDE.md"; }
  [ -f "$HOME/.claude/CLAUDE.md" ]      && { echo '### ~/.claude/CLAUDE.md';    cat "$HOME/.claude/CLAUDE.md"; }
  INDEX="$GIT_ROOT/docs/agent_index.md"
  [ -f "$INDEX" ]                        && { echo '### docs/agent_index.md (first 200 lines)'; head -n 200 "$INDEX"; }
  [ -f "$GIT_ROOT/.codesight/CODESIGHT.md" ] && { echo '### .codesight/CODESIGHT.md'; cat "$GIT_ROOT/.codesight/CODESIGHT.md"; }
} >> "$BUNDLE"

# Size cap — if >5000 lines, keep diff + metadata, drop per-file contents.
# A 5000-line bundle is ~30K tokens; above that the cache-write cost starts
# to outweigh the turn-count savings.
BUNDLE_LINES=$(wc -l < "$BUNDLE")
if [ "$BUNDLE_LINES" -gt 5000 ]; then
  # Rebuild without per-file contents.
  { grep -n '^## Touched files' "$BUNDLE" | head -1 | cut -d: -f1 | xargs -I{} head -n {} "$BUNDLE"
    echo
    echo 'BUNDLE_TRUNCATED=true  # original was '"$BUNDLE_LINES"' lines; per-file contents omitted'
    echo
    echo '## Repo context'
    [ -f "$GIT_ROOT/CLAUDE.md" ]      && { echo '### $GIT_ROOT/CLAUDE.md'; cat "$GIT_ROOT/CLAUDE.md"; }
    [ -f "$HOME/.claude/CLAUDE.md" ]  && { echo '### ~/.claude/CLAUDE.md'; cat "$HOME/.claude/CLAUDE.md"; }
  } > "$BUNDLE.tmp" && mv "$BUNDLE.tmp" "$BUNDLE"
fi
```

Save the list of skipped files for Reviewer transparency:
```bash
grep '<file path=.*skipped=' "$BUNDLE" | head -20 > "$GIT_ROOT/.agent-work/REVIEW_BUNDLE_SKIPPED.txt"
```
````

### Edit 2a-B — Reviewer spawn prompt

In the Reviewer agent definition (Agent 1), replace the "Instructions"
opening with:

```markdown
**Context bundle (already in your prompt)**:

The review bundle below contains:
- PR metadata (title, body, base, head, +/- counts)
- The full PR diff
- Current contents of every touched file (or `skipped=` markers for
  binary/generated files; check `.agent-work/REVIEW_BUNDLE_SKIPPED.txt` if
  you need the list)
- Repo CLAUDE.md, global CLAUDE.md, and the codebase index excerpt

**Do NOT re-read the bundle's contents** via Read or Bash. Use Read/Grep
only for files NOT in the bundle — typically callers of touched functions
or analogous patterns elsewhere in the codebase, and only when the review
genuinely needs them.

If the bundle header contains `BUNDLE_TRUNCATED=true`, the per-file contents
were dropped due to size. Fall back to `Read` on individual files as needed.

`<BUNDLE>` _(the skill spawning you inlines `$(cat .agent-work/REVIEW_BUNDLE.md)` here)_

**Instructions**:

1. Understand the intent from the PR title and description (in the bundle).
2. _[existing step 2 — structured finding format]_
3. _[existing step 3 — categories]_
4. _[existing step 4 — scope check]_
5. _[existing step 5 — pattern consistency]_
6. _[existing step 6 — test coverage validity]_
7. Output `.agent-work/REVIEW_FINDINGS_<cycle>.md` with all findings
   organized by severity.
```

Remove the "Context bootstrap" bullet list from the "Subagent Context
Bootstrap" section *for the Reviewer only* — the bundle supersedes it. Update
that section to read:

```markdown
## Subagent Context Bootstrap

When spawning the **Fixer**, prepend these instructions to its prompt:

> **Context bootstrap** (do this before your main task):
> 1. Read `~/.claude/CLAUDE.md` …  _(existing content)_
> 2. Read codebase index files …  _(existing content)_

The Reviewer and Intent Validator do NOT receive this preamble — their
respective bundles (REVIEW_BUNDLE.md, INTENT_BUNDLE.md) already contain
this context inline.
```

### Edit 2a-C — inline the bundle into each Reviewer spawn

Wherever the skill currently says "spawn the Reviewer", update to
"spawn the Reviewer, inlining `$(cat .agent-work/REVIEW_BUNDLE.md)` into the
`<BUNDLE>` slot of its prompt template". Three sites:
- Initial Review section (~line 280)
- Per-cycle Reviewer spawn (in the Coordination Flow loop diagram)
- Final Review spawn (near the end of the loop section)

### Acceptance check (Wave 2a)

- [ ] For a representative PR (3–6 touched files, <20 lines each), Reviewer
  turn count drops from baseline (15–25 turns) to **≤ 6 turns**.
- [ ] Reviewer phase cost drops to **≤ 33% of baseline** on the same PR.
- [ ] `.agent-work/REVIEW_BUNDLE.md` exists after R-SETUP and is gitignored
  via `.git/info/exclude` (it's already inside `.agent-work/` which is
  covered by the existing exclude).
- [ ] `REVIEW_FINDINGS_<cycle>.md` still catches the same 2–3 seeded issues
  on a real PR as the pre-W2a version (manual A/B on 2 real PRs).
- [ ] Bundle size cap triggers on a deliberate monster PR (>5000 lines of
  touched files) and the Reviewer still completes successfully by falling
  through to Read.
- [ ] `REVIEW_BUNDLE_SKIPPED.txt` lists any `.lock` / `.min.js` / generated
  files that were filtered out.

### Conflicts

- **With W1:** W2a's Reviewer header is unchanged by W2a; it inherits W1's
  `model: $REVIEWER_MODEL` if W1 shipped first. If W2a ships first, use the
  current literal `model: "claude-opus-4-6"` and W1 will replace it. **No
  merge conflict** — W1 and W2a edit disjoint text blocks.
- **With W2b:** W2a's edit to "Subagent Context Bootstrap" mentions the
  Intent Validator preemptively, and W2b will further modify that section.
  If W2b ships before W2a, W2a's edit to that section becomes the final
  form. Resolution: W2a writes the definitive Bootstrap-section text now
  (Fixer-only); W2b need not touch that section.

---

## Wave 2b — INTENT_BUNDLE for the Intent Validator

### Goal

The Intent Validator receives the pre-loop PR diff, the auto-fix commits
diff, and current contents of all affected files inline in its prompt —
eliminating the need for the validator to `Bash(git diff)` and `Read` files
itself.

### Edit 2b-A — capture pre-loop HEAD in R-SETUP

In the Setup section, **after** `Find the associated PR:` and **before**
`Fetch full PR context:` (~line 64), add:

```markdown
### Capture pre-loop HEAD

Before any Fixer commits anything, record the current branch tip so the
Intent Validator can later diff pre-loop vs post-loop state:

```bash
git -C "$GIT_ROOT" rev-parse HEAD > "$GIT_ROOT/.agent-work/PRE_LOOP_HEAD.sha"
```

This SHA is the boundary between "what the PR author wrote" and "what the
automated fix-loop added".
```

### Edit 2b-B — assemble INTENT_BUNDLE immediately before Intent Validator spawn

In the Coordination Flow section, immediately before "Intent Validation
(always runs, no fixes):" (~line 328), add:

````markdown
### Assemble intent bundle

Before spawning the Intent Validator, write `.agent-work/INTENT_BUNDLE.md`:

```bash
PR_NUM=<pr-number>
BUNDLE="$GIT_ROOT/.agent-work/INTENT_BUNDLE.md"
PRE_LOOP="$(cat "$GIT_ROOT/.agent-work/PRE_LOOP_HEAD.sha")"
BASE_REF="<base-branch>"

# Verify the pre-loop SHA is still reachable. A mid-loop rebase could have
# orphaned it. If so, degrade gracefully.
if ! git -C "$GIT_ROOT" cat-file -e "$PRE_LOOP^{commit}" 2>/dev/null; then
  DEGRADED=true
else
  DEGRADED=false
fi

{
  echo "# Intent validation bundle for PR #$PR_NUM"
  echo
  echo "- Pre-loop HEAD SHA: \`$PRE_LOOP\`"
  [ "$DEGRADED" = true ] && echo '- **INTENT_BUNDLE_DEGRADED=true** — pre-loop HEAD unreachable (rebase?); diffs below are reconstructed from base-branch tip instead'
  echo
  echo '## Pre-loop PR diff (original author intent)'
  echo '```diff'
  cat "$GIT_ROOT/.agent-work/PR_DIFF.txt" 2>/dev/null \
    || gh pr diff "$PR_NUM"
  echo '```'
  echo
  echo '## Post-loop commits (added by automated fix cycles)'
  if [ "$DEGRADED" = false ]; then
    git -C "$GIT_ROOT" log --oneline "$PRE_LOOP..HEAD"
    echo
    echo '## Post-loop diff'
    echo '```diff'
    git -C "$GIT_ROOT" diff "$PRE_LOOP..HEAD"
    echo '```'
  else
    git -C "$GIT_ROOT" log --oneline "origin/$BASE_REF..HEAD"
    echo
    echo '## Post-loop diff (degraded — reconstructed from base)'
    echo '```diff'
    git -C "$GIT_ROOT" diff "origin/$BASE_REF..HEAD"
    echo '```'
  fi
  echo
  echo '## Current contents of files touched by either diff'
} > "$BUNDLE"

# Union of files in pre-loop and post-loop diffs
{
  gh pr view "$PR_NUM" --json files --jq '.files[].path'
  [ "$DEGRADED" = false ] && git -C "$GIT_ROOT" diff --name-only "$PRE_LOOP..HEAD"
} | sort -u | while read -r f; do
  if [[ ! -f "$GIT_ROOT/$f" ]]; then continue; fi
  SKIP_PATTERNS='\.lock$|-lock\.|\.min\.(js|css)$|\.generated\.|^(dist|build|node_modules)/'
  if [[ "$f" =~ $SKIP_PATTERNS ]]; then continue; fi
  printf '\n<file path="%s">\n```\n' "$f" >> "$BUNDLE"
  head -n 1000 "$GIT_ROOT/$f" >> "$BUNDLE"
  printf '\n```\n</file>\n' >> "$BUNDLE"
done

# Repo context — reuse the small footer from REVIEW_BUNDLE if it exists
{
  echo
  echo '## Repo context'
  [ -f "$GIT_ROOT/CLAUDE.md" ]      && { echo '### $GIT_ROOT/CLAUDE.md'; cat "$GIT_ROOT/CLAUDE.md"; }
  [ -f "$HOME/.claude/CLAUDE.md" ]  && { echo '### ~/.claude/CLAUDE.md'; cat "$HOME/.claude/CLAUDE.md"; }
  INDEX="$GIT_ROOT/docs/agent_index.md"
  [ -f "$INDEX" ]                    && { echo '### docs/agent_index.md (first 200 lines)'; head -n 200 "$INDEX"; }
} >> "$BUNDLE"

# Same 5000-line size cap as REVIEW_BUNDLE (see Wave 2a for the truncation logic)
```
````

### Edit 2b-C — Intent Validator spawn prompt

In the Intent Validator definition (Agent 4), replace the "Instructions"
opening with:

```markdown
**Context bundle (already in your prompt)**:

The intent bundle below contains:
- The **pre-loop HEAD SHA** (captured before any Fixer committed)
- The **pre-loop PR diff** — what the original author wrote
- The **post-loop commits and diff** — what the automated fix cycles added
- **Current contents of every file touched by either diff**
- Repo + global `CLAUDE.md`, codebase index excerpt

**Do NOT re-run `git diff`, `git log`, or Read the touched files** — that
information is already in your prompt. Use Read/Grep only if you need to
check a caller or invariant in a file NOT listed in the bundle.

If the bundle header contains `INTENT_BUNDLE_DEGRADED=true`, the pre-loop
HEAD was unreachable (likely a mid-loop rebase). The diffs in the bundle
are reconstructed from the base branch tip, which may include changes the
original author didn't write. If you distrust the bundle, you may
Bash `git log` yourself — but note the degraded state in your output.

Cross-check: the pre-loop SHA is in the bundle header. If you need to
verify the bundle wasn't miscomposed, `git cat-file -e <sha>^{commit}`
and `git diff <sha>..HEAD` directly.

`<BUNDLE>` _(the skill spawning you inlines `$(cat .agent-work/INTENT_BUNDLE.md)` here)_

**Instructions**:

1. Re-read the PR metadata in the bundle to extract the stated intent.
2. _[existing step 3 — compare original vs automated for each touched file]_
3. _[existing step 4 — classic failure patterns]_
4. _[existing step 5 — structured finding format]_
5. _[existing step 6 — "no concerns found" clean output]_
6. Output findings to `.agent-work/INTENT_VALIDATION.md`.
```

The existing step 2 (which told the validator to fetch the original diff via
git) is now **deleted** — the bundle replaces it.

### Acceptance check (Wave 2b)

- [ ] For a representative PR, Intent Validator turn count drops from
  baseline (10–20 turns) to **≤ 5 turns**.
- [ ] Intent Validator phase cost drops to **≤ 40% of baseline** on the same PR.
- [ ] `.agent-work/PRE_LOOP_HEAD.sha` is captured at R-SETUP and is
  reachable at the end of a normal (non-rebased) run.
- [ ] On a deliberately rebased branch, `INTENT_BUNDLE_DEGRADED=true`
  appears in the bundle header and the Intent Validator still produces a
  valid `INTENT_VALIDATION.md`.
- [ ] Seeded intent-risk scenario test: introduce a PR that adds
  `load_dotenv()` as the first statement; have an automated Fixer reorder
  imports above it (a real classic failure pattern from the skill spec).
  The Intent Validator with bundle must still flag this as `INTENT-RISK:
  high`.

### Conflicts

- **With W2a:** both waves define the same `SKIP_PATTERNS` shell variable
  and the same 5000-line size-cap logic. Resolution: extract both into a
  small reusable snippet in a new "Bundle helpers" subsection at the top of
  Setup; Wave 2a creates the subsection, Wave 2b references it. If W2b
  ships first, it creates the subsection instead.
- **With W1:** none. W1 touches only the Reviewer model and flag parsing.
- **With existing skill behavior:** the old Intent Validator instructions
  told it to `git diff <base-branch>...<first-commit-of-loop-or-branch-tip-before-loop>`.
  That instruction is **replaced**, not augmented. If an old artifact file
  (e.g. the prior run's `.agent-work/INTENT_VALIDATION.md`) exists and
  assumes the old shape, it will be overwritten cleanly by the new run.

---

## Global conflict summary

| Touchpoint | W1 | W2a | W2b | Resolution |
|---|---|---|---|---|
| "Parse arguments" section | adds flag-parsing subsection | — | — | W1 owns |
| Reviewer agent header (~line 102) | changes `model:` line | — | — | W1 owns |
| Reviewer agent "Instructions" body | — | rewrites opener + adds bundle slot | — | W2a owns |
| "Subagent Context Bootstrap" section | — | rewrites as Fixer-only | — | W2a owns |
| "Setup" section | — | inserts `REVIEW_BUNDLE` assembly | inserts `PRE_LOOP_HEAD.sha` capture | both, at different anchor points |
| Coordination Flow section | adds model-passing instruction | inlines bundle on Reviewer spawns | inserts `INTENT_BUNDLE` assembly before Intent spawn | each targets a different location |
| Intent Validator agent "Instructions" body | — | — | rewrites opener + deletes old `git diff` step | W2b owns |
| Human Review Summary | adds `Reviewer model:` line | — | — | W1 owns |
| PR comment template | adds `Reviewer model:` line | — | — | W1 owns |
| Shared bundle helpers (`SKIP_PATTERNS`, size-cap) | — | creates | references | W2a creates the subsection; W2b references it |

**No two waves edit the same line.** Merge conflicts cannot arise from
wave-to-wave sequencing; waves can ship in any order.

---

## Rollout and measurement

1. **Ship W1 first** (30 min). Zero structural risk; immediately unblocks
   A/B testing. Flip the default to `claude-opus-4-7` and verify on the
   next real PR that existing behavior is preserved.

2. **Ship W2a next** (1–2 hours). On the first post-W2a PR, run
   `python tools/find-pr-review-cycle-sessions.py --days 1 --md <path>` and
   confirm the new invocation's REV phase cost is **≤ 33% of the average of
   the last 5 pre-W2a invocations on comparable PRs**.

3. **Ship W2b last** (1 hour — reuses W2a's helper logic). On the next PR
   run, confirm the INT phase cost drops similarly. Also confirm the
   degraded-bundle path by manually rebasing a test branch between R-SETUP
   and the Intent Validator spawn, then inspecting the bundle header.

4. **Post-rollout measurement** (2 weeks after W2b ships). Re-run the broad
   scan and compare:
   - REV total for the 2 weeks post-ship vs the 2 weeks pre-ship
   - INT total for same
   - Any regression in `REVIEW_FINDINGS_FINAL.md` or `INTENT_VALIDATION.md`
     quality flagged by manual PR review

5. **A/B the Reviewer model** (optional, after ≥2 weeks of stable W2a+W2b
   operation). Alternate `--reviewer-model=claude-sonnet-4-6` with the
   default `claude-opus-4-7` on every other real PR. Track findings quality
   and cost per PR. If Sonnet's findings quality is indistinguishable on a
   sample of 10 PRs, flip the default to Sonnet in a follow-up W3.

---

## Out of scope for this plan

- Changes to the Fixer (already Sonnet, already small).
- Changes to the Orchestrator.
- Any modification to `/pr-finalize`, `/rebase`, or other skills chained
  after `/pr-review-cycle`.
- Cross-session cache optimizations, prompt-prefix sharing, or bundle
  reuse across invocations. See [pr-review-cycle-improvements.md](pr-review-cycle-improvements.md)
  non-goals for the reasoning.
