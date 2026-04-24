---
version: 1.0.0
---

# Refine Constitution

## Purpose

Detects the current state of a project constitution and routes to the matching subskill. The three modes — setup, refinement, and amendment — each have their own prompt file; this entry point does nothing but detect state, announce it, and dispatch. It contains no interview logic, no law-drafting logic, and no bluffing detection. Those live in the subskills. The separation is intentional: state detection is mechanical and can be verified by inspection; the interview is judgment-heavy and must be isolated so each mode can evolve independently.

This command never writes source code and never opens PRs. Its only outputs are `CONSTITUTION.md` (created or updated by a subskill) and, optionally, `CONSTITUTION.research.md` (written by the research subagent invoked from within a subskill).

---

## Args

`/refine-constitution [path]`

- `path`: optional. Path to the constitution file. Defaults to `CONSTITUTION.md` at the repo root. Accepts absolute or repo-relative paths.

Optional flags (override auto-detected state when the user disagrees with the detection):

- `--force-setup` — treat the file as absent and run the full first-draft flow, regardless of content.
- `--force-refinement` — enter refinement mode even if the file appears complete.
- `--force-amendment` — enter amendment mode even if markers are present.
- `--base <branch>` — check out this branch before reading the constitution file. If omitted, the
  base branch is auto-detected (see Step 1).

Flags take precedence over all detection logic. When a `--force-*` flag is present, skip Steps 1–2 and go directly to Step 3.

---

## Output

This command produces or updates:

- `CONSTITUTION.md` — the constitution file, at `path` (default: repo root).
- `CONSTITUTION.mini.md` — derived agent-injection target; written only when the master is complete (zero markers). See the mini schema in `commands/refine-constitution/constitution-template.md`.
- `CONSTITUTION.research.md` — research cache written by the research subagent; present only when a subskill invokes it.

It never writes source files, never creates branches, and never opens PRs.

---

## Step 0 — Setup

Call `TodoWrite` to initialize task tracking with entries for Steps 0–4, marking Step 0 `in_progress`. This loads the `TodoWrite` schema early so subsequent updates do not trigger a cache-invalidating `ToolSearch` mid-session.

Entries:
1. Step 0 — setup (in_progress)
2. Step 1 — load constitution file
3. Step 2 — state detection
4. Step 3 — announce mode
5. Step 4 — dispatch to subskill

Mark Step 0 done before proceeding.

---

## Step 1 — Load Constitution File

Resolve the target path:
- If `path` was provided, use it directly.
- Otherwise, detect the repo root:
  ```bash
  git rev-parse --show-toplevel 2>/dev/null
  ```
  and set `CONSTITUTION_PATH=<root>/CONSTITUTION.md`.

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

Skip this step if no repo root was found (no git repo, running outside a project).

Attempt to read the file at `CONSTITUTION_PATH`.

- If the file does not exist, or exists but is empty (zero bytes or whitespace only): set `STATE=ABSENT`.
- If the file exists and has content: retain the full text for Step 2.

Mark Step 1 done, Step 2 in_progress.

---

## Step 2 — State Detection

This step is purely mechanical. Do not apply editorial judgment. Apply the rules in order; the first matching rule wins.

**Rule 0 — Force flag present**: if the user passed `--force-setup`, `--force-refinement`, or `--force-amendment`, skip all rules and go directly to Step 3 with the corresponding state.

**Rule 1 — Absent**: if `STATE=ABSENT` (set in Step 1), set `MODE=setup`. Stop.

**Rule 2 — Explicit markers present**: scan the full file text for any of the following strings (literal, case-sensitive):

```
[DRAFT]
[NEEDS WHY]
[NEEDS REJECTED-ALT]
[NEEDS ANTI-PATTERN]
[DEFERRED
[UNCHALLENGED]
[MISSING]
```

Note: `[DEFERRED` is matched as a prefix (it is followed by ` — <reason>]`, so check for the opening bracket and the word DEFERRED, not the full string). If any marker is found anywhere in the file, set `MODE=refinement`. Stop.

**Rule 3 — Structurally complete**: check that all of the following are true:

1. A thesis paragraph is present (a non-empty paragraph before the first numbered law heading).
2. There are between 3 and 10 numbered laws (headings of the form `## Law N — <Stance>`, optionally prefixed `## [DRAFT] Law N — ...` or suffixed `... [UNCHALLENGED]` per the template's heading variants). Other heading depths or inline `**Law N**` prose do not count.
3. Every law contains all four required elements: a Stance line, a Why line/block, a Rejected Alternative line/block, and an Anti-pattern line/block.
4. A "Rejected Alternatives" section is present at the document level (not inside a law).
5. A "Review Heuristic" section is present.
6. Zero markers from Rule 2 are present.

If all six conditions hold, set `MODE=amendment`. Stop.

**Rule 4 — Ambiguous (no markers, but structurally incomplete)**: the file has content, no explicit markers fired in Rule 2, but Rule 3 did not pass (missing sections, laws with incomplete elements, fewer than 3 laws, etc.). Set `MODE=refinement` and set `NORMALIZE=true`. The normalization step runs at the start of the refinement subskill — it injects specific `[DRAFT]` and `[NEEDS ...]` markers into each incomplete element before the subskill's main loop begins. This makes the ambiguous case identical to the explicit-marker case from the subskill's perspective.

Mark Step 2 done, Step 3 in_progress.

---

## Step 3 — Announce Mode

Tell the user the detected mode in one sentence. Be specific about what was found.

Examples:
- `No constitution file found — entering setup mode.`
- `Detected a draft with [NEEDS WHY] on Law 2 and [UNCHALLENGED] on Law 3 — entering refinement mode.`
- `Constitution appears complete (5 laws, no markers) — entering amendment mode.`
- `Constitution has content but Law 3 is missing an Anti-pattern and there is no Review Heuristic section — entering refinement mode with normalization.`

If a `--force-*` flag was passed, announce the override explicitly:
- `--force-amendment flag set — skipping state detection and entering amendment mode.`

Do not ask the user to confirm the mode. If they want a different mode, they re-run with the appropriate `--force-*` flag.

Mark Step 3 done, Step 4 in_progress.

---

## Step 4 — Dispatch

Read the matching subskill prompt file and follow its instructions. Do not summarize or abbreviate the subskill — read it and execute it in full.

| MODE | Subskill file |
|------|--------------|
| setup | `commands/refine-constitution/setup-prompt.md` |
| refinement | `commands/refine-constitution/refinement-prompt.md` |
| amendment | `commands/refine-constitution/amendment-prompt.md` |

Pass the following context into the subskill:

- `CONSTITUTION_PATH` — resolved absolute path.
- `MODE` — detected or forced.
- `NORMALIZE` — `true` only when Rule 4 fired; omit or `false` otherwise.
- The full file text read in Step 1 (or the empty-file signal if `STATE=ABSENT`).

Mark Step 4 in_progress when the subskill begins. Mark Step 4 done when the subskill completes and `CONSTITUTION.md` has been written.
