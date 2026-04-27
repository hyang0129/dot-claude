---
version: 1.0.0
---

# Refine Doctrine

## Purpose

Detects the current state of a project doctrine file and routes to the matching subskill. The three modes — setup, refinement, and amendment — each have their own prompt file; this entry point does nothing but detect state, announce it, and dispatch. It contains no interview logic, no order-drafting logic, and no contestedness detection. Those live in the subskills. The separation is intentional: state detection is mechanical and can be verified by inspection; the interview is judgment-heavy and must be isolated so each mode can evolve independently.

This command never writes source code and never opens PRs. Its only outputs are `DOCTRINE.md` (created or updated by a subskill) and, optionally, `DOCTRINE.mini.md` (written by a subskill when the master is complete).

Doctrine is the tech-bound layer of a project's governance stack. It sits below the constitution. Every Standing Order must anchor to at least one constitutional law and carry an observable tech assumption that, when it changes, retires the order. If the project has no complete constitution, this command cannot run — doctrine without anchors is just convention.

---

## Args

`/refine-doctrine [path]`

- `path`: optional. Path to the doctrine file. Defaults to `DOCTRINE.md` at the repo root. Accepts absolute or repo-relative paths.

Optional flags (override auto-detected state when the user disagrees with the detection):

- `--force-setup` — treat the file as absent and run the full first-draft flow, regardless of content.
- `--force-refinement` — enter refinement mode even if the file appears complete.
- `--force-amendment` — enter amendment mode even if markers are present.
- `--base <branch>` — check out this branch before reading the doctrine file. If omitted, the base branch is auto-detected (see Step 1).

Flags take precedence over all detection logic. When a `--force-*` flag is present, skip Steps 1–2 and go directly to Step 3.

---

## Output

This command produces or updates:

- `DOCTRINE.md` — the doctrine file, at `path` (default: repo root).
- `DOCTRINE.mini.md` — derived agent-injection target; written only when the master is complete (zero markers). See the mini schema in `commands/refine-doctrine/doctrine-template.md`.

It never writes source files, never creates branches, never opens PRs, and never edits `CONSTITUTION.md` directly (promote-to-law creates a tombstone and tells the user to run `/refine-constitution --force-amendment`).

---

## Step 0 — Setup

Call `TodoWrite` to initialize task tracking with entries for Steps 0–4, marking Step 0 `in_progress`. This loads the `TodoWrite` schema early so subsequent updates do not trigger a cache-invalidating `ToolSearch` mid-session.

Entries:
1. Step 0 — setup (in_progress)
2. Step 1 — load doctrine file
3. Step 1.5 — constitution gate + candidate ingestion
4. Step 2 — state detection
5. Step 3 — announce mode
6. Step 4 — dispatch to subskill

Mark Step 0 done before proceeding.

---

## Step 1 — Load Doctrine File

Resolve the target path:
- If `path` was provided, use it directly.
- Otherwise, detect the repo root:
  ```bash
  git rev-parse --show-toplevel 2>/dev/null
  ```
  and set `DOCTRINE_PATH=<root>/DOCTRINE.md`.

### Base branch checkout

After the repo root is known, switch to the correct base branch:

```bash
# Detect base branch (skip if --base was given)
if [ -n "<BASE_FROM_ARG>" ]; then
  BASE_BRANCH="<BASE_FROM_ARG>"
else
  BASE_BRANCH="$(gh repo view --json defaultBranchRef \
    --jq '.defaultBranchRef.name' 2>/dev/null)"
  if [ -z "$BASE_BRANCH" ]; then
    git show-ref --verify --quiet refs/heads/dev 2>/dev/null \
      && BASE_BRANCH="dev" || BASE_BRANCH="main"
  fi
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "$BASE_BRANCH" ]; then
  git checkout "$BASE_BRANCH"
fi
```

Tell the user: `On branch <BASE_BRANCH>.` (one line; omit if already on that branch).

Skip the branch checkout if no repo root was found (no git repo, running outside a project).

### WIP detection

Before reading `DOCTRINE_PATH`, check for `DOCTRINE.wip.md` in the same directory.

If found:
- Read it and extract the `Phase completed:` line.
- Tell the user: "Found an in-progress setup session (last checkpoint: Phase N). Resume it, or discard it and start fresh? (resume/discard)"
- If **resume**: set `STATE=WIP` and proceed to Step 4 (`setup` mode). The setup subskill reads `DOCTRINE.wip.md` at its start and picks up from the last completed phase. Skip Steps 1.5–3.
- If **discard**: delete `DOCTRINE.wip.md` and continue normally with the steps below.
- If `DOCTRINE.md` also exists with content alongside `DOCTRINE.wip.md`: treat the WIP file as a recovery file for pre-Phase-5 state only, and do not override the existing `DOCTRINE.md` unless the user confirms.

Attempt to read the file at `DOCTRINE_PATH`.

- If the file does not exist, or exists but is empty (zero bytes or whitespace only): set `STATE=ABSENT`.
- If the file exists and has content: retain the full text for Step 2.

Mark Step 1 done, Step 1.5 in_progress.

---

## Step 1.5 — Constitution Gate + Candidate Ingestion

This step is doctrine-specific. It has no equivalent in `/refine-constitution`.

### Constitution gate

Resolve `CONSTITUTION_PATH`: look for `CONSTITUTION.md` in the same directory as `DOCTRINE_PATH` (default: repo root).

Attempt to read `CONSTITUTION.md`.

**If absent or unreadable:**

> "Doctrine anchors require a complete constitution. No `CONSTITUTION.md` was found at `<CONSTITUTION_PATH>`. Run `/refine-constitution` first."

Exit. Do not proceed.

**If present, check completeness.** A constitution is complete if all of the following hold:
1. Zero markers (`[DRAFT]`, `[NEEDS WHY]`, `[NEEDS REJECTED-ALT]`, `[NEEDS ANTI-PATTERN]`, `[DEFERRED`, `[UNCHALLENGED]`, `[MISSING]`).
2. Thesis section is non-empty.
3. Between 3 and 10 numbered laws (`## Law N — ...` headings).
4. Every law has all four required elements: Stance (heading), Why, Rejected Alternative, Anti-pattern.
5. Rejected Alternatives section present.
6. Review Heuristic section present.

**If incomplete (any condition fails):**

> "Doctrine anchors require a complete constitution. The existing `CONSTITUTION.md` has markers or missing sections. Run `/refine-constitution` to complete it first."

Exit. Do not proceed.

**If complete:** extract the law list into memory as `CONSTITUTION_LAWS`:

```
Law 1: <stance summary> (from: ## Law 1 — <Stance>)
Law 2: <stance summary>
...
```

This list is used throughout the session for anchor validation: every Standing Order's Anchor field must reference at least one law from this list by number and stance summary.

### Candidate ingestion

Scan `CONSTITUTION.md` for a `## Filtered Doctrine Candidates` section. If present, load all entries.

Each entry has the form:
```
- **Candidate:** <stance>
  **Voiced by:** <name or role>
  **Anchor candidate:** Law N (<stance summary>)
  **Observable condition:** <tech assumption>
  **Captured:** <YYYY-MM-DD>
```

For each candidate:
- Flag any candidate captured more than 6 months before today with `[STALE — captured <date>]`.
- Collect all candidates into a working list: `DOCTRINE_CANDIDATES`.

If `DOCTRINE_CANDIDATES` is non-empty, surface them to the user at the start of the session:

> "During constitution work, these opinions were captured as doctrine candidates:
>
> [list: stance, anchor candidate, captured date, stale flag if applicable]
>
> We will start from these before drafting new orders."

Candidates with a stale flag should be re-tested against the current state of the tech before becoming Standing Orders. Surface the flag and ask the user: "This candidate is over 6 months old — does the observable condition still hold?"

If `DOCTRINE_CANDIDATES` is empty or the section does not exist, proceed without mentioning it.

Mark Step 1.5 done, Step 2 in_progress.

---

## Step 2 — State Detection

This step is purely mechanical. Do not apply editorial judgment. Apply the rules in order; the first matching rule wins.

**Rule 0 — Force flag present**: if the user passed `--force-setup`, `--force-refinement`, or `--force-amendment`, skip all rules and go directly to Step 3 with the corresponding state.

**Rule 1 — Absent**: if `STATE=ABSENT` (set in Step 1), set `MODE=setup`. Stop.

**Rule 2 — Explicit markers present**: scan the full file text for any of the following strings (literal, case-sensitive):

```
[DRAFT]
[NEEDS ANCHOR]
[NEEDS ASSUMPTION]
[NEEDS SUNSET]
[NEEDS ANTI-PATTERN]
[UNCHALLENGED]
[STALE]
[MISSING]
```

Note: `[STALE]` is matched as a prefix (it may be followed by ` — <context>]`). If any marker is found anywhere in the file, set `MODE=refinement`. Stop.

**Rule 3 — Structurally complete**: check that all of the following are true:

1. A Preamble section is present with a non-empty paragraph.
2. There is at least one Standing Order block under `## Standing Orders`.
3. Every Standing Order contains all four required fields: Anchor, Tech Assumption, Sunset Trigger, Anti-pattern.
4. Every Order's Anchor references at least one law from `CONSTITUTION_LAWS`.
5. Zero markers from Rule 2 are present.

If all five conditions hold, set `MODE=amendment`. Stop.

**Rule 4 — Ambiguous (no markers, but structurally incomplete)**: the file has content, no explicit markers fired in Rule 2, but Rule 3 did not pass (missing Preamble, orders with empty fields, Anchor referencing a non-existent law, etc.). Set `MODE=refinement` and set `NORMALIZE=true`. The normalization step runs at the start of the refinement subskill — it injects specific `[NEEDS ...]` markers into each incomplete element before the subskill's main loop begins. This makes the ambiguous case identical to the explicit-marker case from the subskill's perspective.

Mark Step 2 done, Step 3 in_progress.

---

## Step 3 — Announce Mode

Tell the user the detected mode in one sentence. Be specific about what was found.

Examples:
- `No doctrine file found — entering setup mode.`
- `Detected a draft with [NEEDS ASSUMPTION] on Order 2 and [UNCHALLENGED] on Order 3 — entering refinement mode.`
- `Doctrine appears complete (4 orders, no markers) — entering amendment mode.`
- `Doctrine has content but Order 3 is missing a Sunset Trigger and there is no Preamble — entering refinement mode with normalization.`

If a `--force-*` flag was passed, announce the override explicitly:
- `--force-amendment flag set — skipping state detection and entering amendment mode.`

Do not ask the user to confirm the mode. If they want a different mode, they re-run with the appropriate `--force-*` flag.

Mark Step 3 done, Step 4 in_progress.

---

## Step 4 — Dispatch

Read the matching subskill prompt file and follow its instructions. Do not summarize or abbreviate the subskill — read it and execute it in full.

| MODE | Subskill file |
|------|--------------|
| setup | `commands/refine-doctrine/setup-prompt.md` |
| refinement | `commands/refine-doctrine/refinement-prompt.md` |
| amendment | `commands/refine-doctrine/amendment-prompt.md` |

Pass the following context into the subskill:

- `DOCTRINE_PATH` — resolved absolute path.
- `CONSTITUTION_PATH` — resolved absolute path.
- `CONSTITUTION_LAWS` — extracted law list with numbers and stance summaries.
- `DOCTRINE_CANDIDATES` — candidate list from Step 1.5 (may be empty).
- `MODE` — detected or forced.
- `NORMALIZE` — `true` only when Rule 4 fired; omit or `false` otherwise.
- The full file text read in Step 1 (or the empty-file signal if `STATE=ABSENT`).

Mark Step 4 in_progress when the subskill begins. Mark Step 4 done when the subskill completes and `DOCTRINE.md` has been written.
