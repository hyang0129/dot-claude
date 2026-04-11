# Refine Issue

## Purpose

Converts a vague issue or one-line description into a behavioral spec that implementation agents
cannot satisfy without also satisfying the user's real intent.

The core failure this command prevents: implementations that technically close a ticket while
leaving the user's actual experience unchanged — a `check_fk()` function that exists but is
never called, a pipeline phase added to a legacy script but not to the CLI or orchestration server.

**This command never writes source code and never opens PRs.**
Its sole output is a refined spec document, optionally posted as a GitHub issue comment.

The refined spec is the intended input to `/resolve-issue` or `/fix-issue`.

---

## Args

`/refine-issue <issue> [--post]`

- `issue`: required. One of:
  - GitHub issue number (e.g. `42`)
  - Full GitHub issue URL (e.g. `https://github.com/org/repo/issues/42`)
  - Quoted free-form description (e.g. `"add reading level checks to the generation pipeline"`)
- `--post`: optional flag. If present and `issue` is a number or URL, post the refined spec as a
  comment on the GitHub issue after producing it.

Detect whether `issue` is a number/URL/repo-ref or a free-form description:
- If it matches `^[\w.-]+/[\w.-]+#\d+$` (e.g. `owner/repo#42`) → extract `owner/repo` and issue number.
- If it matches `^\d+$` → treat as issue number (repo must be detected).
- If it matches `^https?://github\.com/` → extract `owner/repo` and issue number from the URL.
- Otherwise → treat as free-form description. `--post` is silently ignored in this mode.

---

## Setup

### Repo detection (issue reference mode only)

If `issue` is `owner/repo#number` or a full URL, extract `owner/repo` directly — no detection or
confirmation needed. Set `REPO=<owner/repo>` and proceed.

If `issue` is just a number, detect the repo:
```bash
git remote -v
gh repo view --json nameWithOwner
```

Determine `owner/repo`:
- If exactly one GitHub remote, use it.
- If multiple remotes, prefer `upstream` (fork workflow), otherwise `origin`.
- If no remote can be found, check conversation context for a repo name.

**Confirm only when the repo was auto-detected** (i.e., `issue` was a bare number):
```
Repo detected: <owner/repo> (from <source>)

Proceed with issue #<number> in <owner/repo>? [yes / no / different-repo]
```

Wait for the user to confirm or correct. Then set `REPO=<owner/repo>`.

### Fetch the issue (issue reference mode only)

```bash
gh issue view <number> --repo <owner/repo> --json number,title,body,labels,comments
```

If `gh` is unavailable, stop and tell the user to install the GitHub CLI.

### Git root detection

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$GIT_ROOT" ]; then
  for candidate in /workspaces/* "$HOME"/repos/* "$HOME"/repo/* "$HOME"/projects/* "$HOME"/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
fi
```

If `GIT_ROOT` is empty, the Refiner agent will work without codebase context — note this in the
output spec. Do not stop. Skip the scratch directory setup below.

If `GIT_ROOT` is set, the **orchestrator** (you, not the subagent) must verify the scratch
directory before spawning anything:
```bash
test -d "$GIT_ROOT/.claude-work" && echo "EXISTS" || echo "MISSING"
```
If `MISSING`, stop and tell the user:
```
.claude-work/ not found in this repo. Please run:
  mkdir -p <GIT_ROOT>/.claude-work && echo '.claude-work/' >> <GIT_ROOT>/.git/info/exclude
Then re-run this command.
```
Do not proceed until the directory exists.

When `GIT_ROOT` is empty, the Refiner agent writes its output to a temp path instead:
`/tmp/REFINED_<slug>.md`. Report this path to the user in the final summary.

---

## Step 1 — Spawn Refiner Agent

Spawn a **Refiner agent** (`model: "opus"`).

Pass it:
- The full issue body + comments (if issue reference mode), or the free-form description.
- `GIT_ROOT` (or note that codebase context is unavailable).
- The output path: `.claude-work/REFINED_<slug>.md` (or `/tmp/REFINED_<slug>.md` if GIT_ROOT
  is empty) where `<slug>` is a 3–4 word kebab-case summary of the issue title or description.

### Refiner agent instructions

Role: read-only research + produce refined spec. No file writes except the output document.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions)
   if they exist.
2. If `.codesight/CODESIGHT.md` exists at `$GIT_ROOT`, read it in full.
3. If `docs/agent_index.md` exists at `$GIT_ROOT`, read it in full.
   If not found there, glob for `**/agent_index.md` and read any match.

**Phase A — Understand the stated request**

Read the issue or description in full. Identify:
- What the author *literally asked for* (the stated task)
- What they almost certainly *actually want* (the observable outcome)
- Any language that suggests partial awareness of the system (e.g. "add a check" when they mean
  "the output should meet a standard")

**Phase B — Codebase surface area research**

Search the codebase to enumerate *every place where the behavior the user wants must be present*.
Do not assume the issue author knows all the relevant components.

Key searches to perform:
- Grep for symbols, function names, and domain terms from the issue/description.
- Identify all user-facing entry points (CLI commands, API routes, server handlers, scripts,
  configuration hooks) that are relevant to the requested behavior.
- For each entry point found, check whether the relevant behavior currently exists there, is
  partially present, or is entirely absent.
- Look for prior implementations that were added but not wired in — search for functions that
  are defined but never called in any execution path.

**Phase C — Produce the refined spec**

Write `.claude-work/REFINED_<slug>.md`:

```markdown
# Refined Spec: <title> (#<number> | free-form)

## Job Statement
When I <situation>, I want to <motivation>, so I can <outcome>.

## Behavioral Intent
<2–3 sentences: what must be *observably different* after this is resolved. Write this from
the user's perspective — describe the experience, not the implementation. If a check is added,
the intent is not "the check exists" but "the output consistently meets the standard.">

## Hidden Assumptions Surfaced
- <assumption the issue author made that may not be obvious to an implementer>
- <assumption about which components are in scope>
- <any "and obviously it should work in X too" that will never be said aloud>

## Acceptance Scenarios

One scenario per entry point. Each scenario must be falsifiable — it must be expressible as a
test that would have caught the failure if it had been written before implementation.

### Entry Point: <name> (e.g. CLI `generate` command)
**Given** <precondition — system state before the action>
**When** <the user's action at this entry point>
**Then** <observable outcome — what the user sees or measures>
**Falsifiability:** <the test that would have caught "wired but disconnected" — e.g.
"an integration test that calls `cli generate` and asserts the output FK grade is ≤ 6">

### Entry Point: <name> (e.g. Orchestration Server `/run` endpoint)
**Given** ...
**When** ...
**Then** ...
**Falsifiability:** ...

[One block per relevant entry point. If an entry point is explicitly out of scope, say so
and explain why.]

## Surface Area

Every component that must change for all acceptance scenarios to pass. This is the definitive
list — if a component is not on this list, it will not be touched. If the implementer believes
something is missing, they must flag it before writing code.

| Component | File / path | Change required | Acceptance scenario(s) it satisfies |
|---|---|---|---|
| <e.g. FK check function> | `src/pipeline/quality.py` | Wire into generation pipeline | Entry Point: CLI, Entry Point: Server |
| <e.g. CLI `generate` command> | `src/cli/generate.py` | Pass FK result to output validator | Entry Point: CLI |
| <e.g. Orchestration server> | `server/handlers/run.py` | Apply same validation before returning | Entry Point: Server |

## Out of Scope
<Anything that might seem related but should NOT be changed in this issue. Be explicit — if
left unspecified, implementers may either under- or over-reach.>

## Clarifying Questions
<Questions the implementer should answer before writing code. If none, write "None — proceed
directly to implementation.">
```

**Quality checks before finishing:**
- Every acceptance scenario is for a distinct entry point (not a distinct feature).
- Every row in the surface area table is traceable to at least one acceptance scenario.
- The behavioral intent describes what the user *observes*, not what the code *does*.
- The job statement passes the "so I can <outcome>" test — if the outcome is trivially the same
  as the motivation, the job statement is not deep enough; revise it.

---

## Step 2 — Present the Refined Spec

Read `.claude-work/REFINED_<slug>.md` and print it to the user in full.

Then present this summary:

```
## refine-issue complete

Input: #<number> <title> | "<description>"
Output: .claude-work/REFINED_<slug>.md

Entry points identified: <N>
Surface area: <N> components

Next step: /resolve-issue <number> [or /fix-issue <number>]
Note: share the refined spec with the issue or copy it into the issue body before resolving,
so the implementation agent works from the behavioral intent, not the original description.
```

---

## Step 3 — Publish to GitHub

### If the input was a free-form description (no existing issue)

Always create a new GitHub issue with the refined spec as the body:

```bash
gh issue create --repo <REPO> \
  --title "<title derived from the Job Statement>" \
  --body "$(cat <<'EOF'
## Refined Spec (generated by /refine-issue)

<paste the full contents of .claude-work/REFINED_<slug>.md here>

---
*This spec was generated to surface behavioral intent and surface area before implementation.
If anything looks wrong, edit the spec or comment with corrections before running /resolve-issue.*
EOF
)"
```

`REPO` is determined from the current git remote (same logic as bare-number detection in Setup).
If no remote can be determined, ask the user which repo to create the issue in.

Report the new issue URL to the user:
```
Created issue #<number>: <url>

Next step: /resolve-issue <number> [or /fix-issue <number>]
```

### If the input was an issue reference and `--post` was passed

Post the refined spec as a comment on the existing issue:

```bash
gh issue comment <number> --repo <REPO> --body "$(cat <<'EOF'
## Refined Spec (generated by /refine-issue)

<paste the full contents of .claude-work/REFINED_<slug>.md here>

---
*This spec was generated to surface behavioral intent and surface area before implementation.
If anything looks wrong, edit the spec or comment with corrections before running /resolve-issue.*
EOF
)"
```

Confirm to the user:
```
Refined spec posted as a comment on issue #<number>.
```

### If the input was an issue reference without `--post`

Do not post to GitHub. The spec exists only locally.

---

## Step 4 — Keep the Issue in Sync

**The GitHub issue is the master version of the spec.** The local `.claude-work/REFINED_<slug>.md`
is a working copy only. The issue survives context resets, session outages, and new conversation
windows — the local file does not. Treat every spec update as incomplete until the GitHub issue
reflects it.

After presenting the spec, the user may give feedback, answer clarifying questions, or request
changes. **Any user answer that materially affects the spec must be pushed to the GitHub issue
immediately** — before continuing the conversation or asking further questions:

1. Update the local `.claude-work/REFINED_<slug>.md` with the change.
2. Push the update to GitHub right away:

```bash
# If the spec is the issue body (free-form → created issue, or --post on existing issue):
gh issue edit <number> --repo <REPO> --body "$(cat .claude-work/REFINED_<slug>.md)"

# If the spec was posted as a comment (--post mode):
gh issue comment <number> --repo <REPO> --body "$(cat <<'EOF'
## Spec Update

<describe what changed and why, then paste the updated section>
EOF
)"
```

Do not batch multiple user answers before pushing — push after each change. If the session ends
before the issue is updated, the change is lost.

---

## Constraints

- Never write or modify source files.
- Never open branches, commits, or PRs.
- Never assume the issue author has named all the components that need to change.
- If a codebase is unavailable (no git root), the Refiner agent must clearly mark the surface
  area table as "unverified — codebase not available" and the user must validate it manually.
- The output spec is a *recommendation*, not a binding contract — the user should review it
  before passing it to `/fix-issue` or `/resolve-issue`.
- If blocked or uncertain about the repo structure, stop and report rather than guessing.
