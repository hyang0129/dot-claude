---
version: 1.0.0
---

# Refine Conventions

## Purpose

Detects the current state of a project conventions file and routes to the matching subskill. The three modes — setup, refinement, and amendment — each have their own prompt file; this entry point does nothing but detect state, announce it, and dispatch.

This command never writes source code and never opens PRs. Its only outputs are `CONVENTIONS.md` (created or updated by a subskill) and, optionally, `CONVENTIONS.mini.md` (written by a subskill when the master is complete).

Conventions are the **how-we-build-it** layer of a project's governance stack. They sit under the constitution. A convention is any practical default — best practice, taste call, library pick, file-layout pattern — that guides immediate implementation. The only hard requirement is that a convention does not violate a constitutional law. There is no contestedness test, no required anchor, no sunset trigger. If the project has no complete constitution, this command cannot run — the conflict pass at emit time needs the law list.

---

## Args

`/refine-conventions [path]`

- `path`: optional. Path to the conventions file. Defaults to `CONVENTIONS.md` at the repo root. Accepts absolute or repo-relative paths.

Optional flags (override auto-detected state when the user disagrees with the detection):

- `--force-setup` — treat the file as absent and run the full first-draft flow, regardless of content.
- `--force-refinement` — enter refinement mode even if the file appears complete.
- `--force-amendment` — enter amendment mode even if `[TBD]` markers are present.
- `--base <branch>` — check out this branch before reading the conventions file. If omitted, the base branch is auto-detected (see Step 1).

Flags take precedence over all detection logic. When a `--force-*` flag is present, skip Steps 1.5–2 and go directly to Step 3.

---

## Output

This command produces or updates:

- `CONVENTIONS.md` — the conventions file, at `path` (default: repo root).
- `CONVENTIONS.mini.md` — derived agent-injection target; written only when the master is complete (zero `[TBD]` markers). See the mini schema in `commands/refine-conventions/conventions-template.md`.
- `CONVENTIONS.research.md` — optional research cache, written by the research subskill when invoked. Not part of the completeness check.

It never writes source files, never creates branches, never opens PRs, and never edits `CONSTITUTION.md`.

---

## Step 0 — Setup

Call `TodoWrite` to initialize task tracking with entries for Steps 0–4, marking Step 0 `in_progress`. This loads the `TodoWrite` schema early so subsequent updates do not trigger a cache-invalidating `ToolSearch` mid-session.

Entries:
1. Step 0 — setup (in_progress)
2. Step 1 — load conventions file
3. Step 1.5 — constitution gate + candidate ingestion
4. Step 2 — state detection
5. Step 3 — announce mode
6. Step 4 — dispatch to subskill

Mark Step 0 done before proceeding.

---

## Step 1 — Load Conventions File

Resolve the target path:
- If `path` was provided, use it directly.
- Otherwise, detect the repo root:
  ```bash
  git rev-parse --show-toplevel 2>/dev/null
  ```
  and set `CONVENTIONS_PATH=<root>/CONVENTIONS.md`.

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

Before reading `CONVENTIONS_PATH`, check for `CONVENTIONS.wip.md` in the same directory.

If found:
- Read it and extract the `Phase completed:` line.
- Tell the user: "Found an in-progress setup session (last checkpoint: Phase N, area: X). Resume it, or discard it and start fresh? (resume/discard)"
- If **resume**: set `STATE=WIP` and proceed to Step 4 (`setup` mode). The setup subskill reads `CONVENTIONS.wip.md` at its start and picks up from the last completed phase. Skip Steps 1.5–3.
- If **discard**: delete `CONVENTIONS.wip.md` and continue normally with the steps below.
- If `CONVENTIONS.md` also exists with content alongside `CONVENTIONS.wip.md`: treat the WIP file as a recovery file for in-progress setup state only, and do not override the existing `CONVENTIONS.md` unless the user confirms.

Attempt to read the file at `CONVENTIONS_PATH`.

- If the file does not exist, or exists but is empty (zero bytes or whitespace only): set `STATE=ABSENT`.
- If the file exists and has content: retain the full text for Step 2.

Mark Step 1 done, Step 1.5 in_progress.

---

## Step 1.5 — Constitution Gate + Candidate Ingestion

### Constitution gate

Resolve `CONSTITUTION_PATH`: look for `CONSTITUTION.md` in the same directory as `CONVENTIONS_PATH` (default: repo root).

Attempt to read `CONSTITUTION.md`.

**If absent or unreadable:**

> "Conventions need a complete constitution to check against. No `CONSTITUTION.md` was found at `<CONSTITUTION_PATH>`. Run `/refine-constitution` first."

Exit. Do not proceed.

**If present, check completeness.** A constitution is complete if all of the following hold:
1. Zero markers (`[DRAFT]`, `[NEEDS WHY]`, `[NEEDS REJECTED-ALT]`, `[NEEDS ANTI-PATTERN]`, `[DEFERRED`, `[UNCHALLENGED]`, `[MISSING]`).
2. Thesis section is non-empty.
3. Between 3 and 10 numbered laws (`## Law N — ...` headings).
4. Every law has all four required elements: Stance (heading), Why, Rejected Alternative, Anti-pattern.
5. Rejected Alternatives section present.
6. Review Heuristic section present.

**If incomplete (any condition fails):**

> "The existing `CONSTITUTION.md` has markers or missing sections. Conventions need a complete constitution to check against. Run `/refine-constitution` to complete it first."

Exit. Do not proceed.

**If complete:** extract the law list into memory as `CONSTITUTION_LAWS`:

```
Law 1: <stance summary> (from: ## Law 1 — <Stance>)
Law 2: <stance summary>
...
```

This list is used in the Phase 3 conflict pass (each drafted convention is checked for apparent conflicts with these laws).

### Candidate ingestion

Scan `CONSTITUTION.md` for a `## Convention Candidates` section. If present, load all entries.

Each entry has the form:
```
- **Candidate:** <stance>
  **Voiced by:** <name or role>
  **Captured:** <YYYY-MM-DD>
```

For each candidate:
- Flag any candidate captured more than 6 months before today with `[STALE — captured <date>]`.
- Collect all candidates into a working list: `CONVENTION_CANDIDATES`.

If `CONVENTION_CANDIDATES` is non-empty, surface them to the user at the start of the session:

> "During constitution work, these preferences were noted as convention candidates:
>
> [list: stance, voiced by, captured date, stale flag if applicable]
>
> We will treat these as starting points before drafting other areas."

If `CONVENTION_CANDIDATES` is empty or the section does not exist, proceed without mentioning it.

Mark Step 1.5 done, Step 2 in_progress.

---

## Step 2 — State Detection

This step is purely mechanical. Apply the rules in order; the first matching rule wins.

**Rule 0 — Force flag present**: if the user passed `--force-setup`, `--force-refinement`, or `--force-amendment`, skip all rules and go directly to Step 3 with the corresponding state.

**Rule 1 — Absent**: if `STATE=ABSENT` (set in Step 1), set `MODE=setup`. Stop.

**Rule 2 — `[TBD]` markers present**: scan the full file text for the literal string `[TBD]`. If found anywhere, set `MODE=refinement`. Stop.

**Rule 3 — Complete**: check that all of the following are true:
1. Preamble section is present with a non-empty paragraph.
2. Stack & Context section is present and non-empty.
3. Conventions section has ≥1 area with ≥1 convention.
4. Zero `[TBD]` markers.

If all four conditions hold, set `MODE=amendment`. Stop.

If a file has content but does not satisfy Rule 3 and contains no `[TBD]` markers (e.g., empty Preamble or a Conventions section with no areas), set `MODE=refinement`. The refinement subskill will detect missing required sections and offer to fill them.

Mark Step 2 done, Step 3 in_progress.

---

## Step 3 — Announce Mode

Tell the user the detected mode in one sentence. Be specific about what was found.

Examples:
- `No conventions file found — entering setup mode.`
- `Detected 3 [TBD] entries (areas: Background jobs, Frontend, Security) — entering refinement mode.`
- `Conventions file appears complete (8 areas, no markers) — entering amendment mode.`

If a `--force-*` flag was passed, announce the override explicitly:
- `--force-amendment flag set — skipping state detection and entering amendment mode.`

Do not ask the user to confirm the mode. If they want a different mode, they re-run with the appropriate `--force-*` flag.

Mark Step 3 done, Step 4 in_progress.

---

## Step 4 — Dispatch

Read the matching subskill prompt file and follow its instructions. Do not summarize or abbreviate the subskill — read it and execute it in full.

| MODE | Subskill file |
|------|--------------|
| setup | `commands/refine-conventions/setup-prompt.md` |
| refinement | `commands/refine-conventions/refinement-prompt.md` |
| amendment | `commands/refine-conventions/amendment-prompt.md` |

Pass the following context into the subskill:

- `CONVENTIONS_PATH` — resolved absolute path.
- `CONSTITUTION_PATH` — resolved absolute path.
- `CONSTITUTION_LAWS` — extracted law list with numbers and stance summaries.
- `CONVENTION_CANDIDATES` — candidate list from Step 1.5 (may be empty).
- `MODE` — detected or forced.
- The full file text read in Step 1 (or the empty-file signal if `STATE=ABSENT`).

Mark Step 4 in_progress when the subskill begins. Mark Step 4 done when the subskill completes and `CONVENTIONS.md` has been written.
