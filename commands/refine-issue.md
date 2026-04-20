# Refine Issue

## Purpose

Captures and locks the **intent** behind an issue — the real-world outcome the user wants, the
hidden assumptions they didn't write down, and the failure modes they won't tolerate — so that
an implementation agent can resolve every downstream decision (which entry points to touch,
what "done" looks like, what's out of scope) by reference to that intent instead of re-asking
the user.

The refined spec is a consequence of this, not the goal. Acceptance scenarios, surface area
tables, and falsifiability tests exist to project the captured intent onto the codebase so
implementers cannot satisfy the letter of the spec while missing the point. If intent capture
fails, nothing downstream can recover — a `check_fk()` that exists but is never called, a
pipeline phase added to a legacy script but not to the CLI or server, a ticket closed with the
user's actual experience unchanged — these are all symptoms of intent that was inferred from
the issue body rather than validated with the author.

The core failure this command prevents: implementations that technically close a ticket while
executing against an intent that diverges from the user's actual one.

**This command never writes source code and never opens PRs.**
Its outputs, in priority order:
1. A validated intent summary (Job Statement, Behavioral Intent, Hidden Assumptions, Out of
   Scope) — the source of truth the Spec agent and every downstream implementer reads first.
2. A refined spec that projects that intent onto the codebase as falsifiable acceptance
   scenarios and a concrete surface area table.
3. Optionally, the spec posted to the GitHub issue (the approval surface).

The refined spec is the intended input to `/resolve-issue` or `/fix-issue`.

---

## Args

`/refine-issue <issue> [--no-post]`

- `issue`: required. One of:
  - GitHub issue number (e.g. `42`)
  - Full GitHub issue URL (e.g. `https://github.com/org/repo/issues/42`)
  - Quoted free-form description (e.g. `"add reading level checks to the generation pipeline"`)
- `--no-post`: optional flag. If present and `issue` is a number or URL, keep the refined spec
  local only — do not post it to GitHub. Ignored in free-form mode (see below).

Detect whether `issue` is a number/URL/repo-ref or a free-form description:
- If it matches `^[\w.-]+/[\w.-]+#\d+$` (e.g. `owner/repo#42`) → extract `owner/repo` and issue number.
- If it matches `^\d+$` → treat as issue number (repo must be detected).
- If it matches `^https?://github\.com/` → extract `owner/repo` and issue number from the URL.
- Otherwise → treat as free-form description. `--no-post` is silently ignored in this mode
  (free-form always creates a new issue).

**Default posting behavior:**
- Issue reference mode (number, URL, `owner/repo#N`): post the refined spec to GitHub **by default**.
  Pass `--no-post` to suppress this and keep the spec local only.
- Free-form mode: always creates a new GitHub issue — `--no-post` has no effect. Warn if the user
  passes it: *"`--no-post` ignored; free-form mode always creates a new issue."*

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

If `GIT_ROOT` is empty, the Spec agent will work without codebase context — note this in the
output spec. Do not stop. Skip the scratch directory setup below.

If `GIT_ROOT` is set, verify the scratch directory exists before spawning anything:
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

When `GIT_ROOT` is empty, the Spec agent writes its output to a temp path instead:
`/tmp/REFINED_<slug>-<number>.md`. Report this path to the user in the final summary.

---

## Step 1 — Resume Check

Before spawning anything, check whether prior work exists for this issue.

**Generate a slug early** — you need it for both the resume check and Step 2 checkpointing:
- Issue reference mode: derive from the issue title (lowercase, spaces→hyphens, truncate at 40 chars).
- Free-form mode: derive from the first 8 words of the description the same way.

Store it as `SLUG` for use throughout.

**Check for existing work (both issue-ref and free-form mode):**

```bash
# Completed spec
ls "$GIT_ROOT/.claude-work/REFINED_${SLUG}"-*.md 2>/dev/null
# Partial interview draft
ls "$GIT_ROOT/.claude-work/INTENT_${SLUG}"-*.md 2>/dev/null
```

If a **completed spec** (`REFINED_*`) is found, ask:
```
Found existing refined spec: .claude-work/REFINED_<slug>-<id>.md

Resume from it (r) or start over (s)?
```
- If **resume**: read the existing file, skip to Step 4 and proceed from there.
- If **start over**: delete both the `REFINED_*` and any `INTENT_*` file, continue to Step 2.

If only a **partial interview draft** (`INTENT_*`) is found (no `REFINED_*`), ask:
```
Found a partial interview draft: .claude-work/INTENT_<slug>-<id>.md
The interview was interrupted before a spec was produced.

Resume the interview from the saved Q&A (r) or start over (s)?
```
- If **resume**: read the draft, reconstruct what was covered from the Q&A log, and continue the interview from where it left off (Step 2) — do not re-ask questions already answered.
- If **start over**: delete the draft and continue to Step 2 fresh.

---

## Step 2 — Intent Interview (interactive, multi-round)

Conduct the intent interview directly in this session. Do not spawn a subagent for this step.

This is the most important step in this workflow. Your sole job here is to fully understand what
the user wants and why — not to produce a document, not to search code. Run as many rounds as
needed until intent is completely understood.

Role: dialogue-only. No file writes, no code search, no spec production.

**You are a requirements interviewer, not a spec writer.**

Your job is to understand the user's intent so completely that a different agent — who has never
spoken to the user — could produce a spec the user would sign off on without a single correction.

**Start by reading the issue or description carefully.** Then immediately begin probing. Do not
attempt to summarize or restate the issue back to the user — start asking.

**Probe dimensions (work through all of these across as many rounds as needed):**

1. **The real outcome**
   - What does success look like from the user's perspective — not a code change, a *lived experience*?
   - What would change about their day if this were done right?
   - If the feature disappeared tomorrow, what would they miss?

2. **Hidden scope**
   - Are there places where this behavior should apply that the issue doesn't mention?
   - Has the user ever been surprised that something "worked" in one place but not another?
   - Is there anything they assumed was obvious that they didn't bother writing down?

3. **Acceptance conditions**
   - How will they know it's working? What will they check?
   - What's the simplest thing that would count as "not done"?
   - Is there a failure mode they've seen before that they definitely don't want to repeat?

4. **Constraints and non-goals**
   - What should explicitly NOT change as part of this?
   - Is there anything that would be tempting to add but is out of scope for now?
   - Are there performance, backward-compatibility, or API-stability concerns?

5. **Priority and motivation**
   - Why is this important now? What triggered the request?
   - Is there a deadline, a downstream dependency, or a user complaint that drove this?

**Conversation rules:**
- **Ask all relevant questions per round** — do not artificially limit to one or two. Group
  questions by dimension so the user can answer them in one pass. It is better to ask six
  related questions at once than to make the user wait through six separate rounds.
- **Bundle conditional follow-ups into the same message.** If the answer to one question
  determines what the next question should be, ask both together:
  ```
  Will this need to work offline? If yes — should it queue and replay when reconnected,
  or silently skip until back online?
  ```
  Do not wait for the answer to the first half before asking the second half when the
  branching is simple and obvious.
- **Before moving to the next round, verify that the user actually answered what you asked.**
  If they skipped a question or gave an incomplete answer, re-ask the missing part explicitly
  before continuing. Do not silently drop unanswered questions.
- **Before asking the user any question that the codebase could answer** (e.g. "does X already
  exist?", "where does this behavior happen?", "is Y currently wired?"), spawn a quick Explore
  subagent to look it up first. Then present the finding inline instead of asking:
  ```
  I was going to ask: <the question>
  Looking at the code, I found: <what the subagent returned>
  Stop me if that's wrong — <next question>
  ```
  Only fall back to asking the user directly if the search is inconclusive. Questions about
  intent, priority, and lived experience always go to the user — code cannot answer those.
- When the user answers, synthesize what you've learned before asking the next round.
  Show them you understood, then probe the remaining gaps.
- If an answer opens a new dimension you hadn't considered, follow it.
- Do not declare understanding complete until you can articulate:
  - The job statement (when / want / so I can) with a real-world outcome
  - At least one hidden assumption the issue didn't surface
  - What "done" looks like from the user's perspective
  - What's explicitly out of scope
- Signal completion by saying:
  ```
  I think I have a complete picture of your intent. Here's what I'll hand off to the spec:

  **Job statement:** When I <situation>, I want to <motivation>, so I can <real-world outcome>.
  **Core behavioral intent:** <2–3 sentences on observable change>
  **Key hidden assumptions:** <bullet list>
  **Done looks like:** <what the user will check>
  **Out of scope:** <explicit exclusions>

  Does this capture it accurately, or is there anything to correct?
  ```
- Wait for the user to confirm or correct before concluding.

**Checkpoint writes — do not wait until the end:**

At the very start of Step 2 — before asking any questions — write a stub draft to:
`.claude-work/INTENT_<slug>-<id>.md`

```markdown
# Intent Summary: <title or first line of description> [DRAFT — interview in progress]

## Job Statement
[pending]

## Behavioral Intent
[pending]

## Hidden Assumptions Surfaced
[pending]

## Acceptance Conditions (user-stated)
[pending]

## Out of Scope
[pending]

## Motivation Context
[pending]

## Clarifying Q&A Log
```

After **each interview round**, append the exchange to the `Clarifying Q&A Log` section of the draft file:
```
**Round N**
Q: <your questions>
A: <user's answers>
```

This ensures that if the session is interrupted, partial work is recoverable via the resume check in Step 1.

**Output:** When the user confirms, overwrite the draft with the finalized structured intent summary at the same path:
`.claude-work/INTENT_<slug>-<id>.md`

```markdown
# Intent Summary: <title>

## Job Statement
When I <situation>, I want to <motivation>, so I can <real-world outcome>.

## Behavioral Intent
<2–3 sentences: what must be observably different after this is resolved, from the user's
perspective — describe the experience, not the implementation>

## Hidden Assumptions Surfaced
- <assumption the issue author made that may not be obvious to an implementer>
- <assumption about which components are in scope>
- <any "and obviously it should work in X too" that was never written down>

## Acceptance Conditions (user-stated)
<What the user said they will check. Not test cases — their natural language description of
"done." The Spec agent will formalize these into scenarios.>

## Out of Scope
<Explicit exclusions, confirmed with the user>

## Motivation Context
<Why now, what triggered it, any urgency or downstream dependency>

## Clarifying Q&A Log
<A compact log of the key exchanges — question → answer — that surfaced non-obvious intent.
Include only rounds that changed understanding, not small clarifications.>
```

---

## Step 3 — Spec Agent (one-shot formalization)

After the Intent agent completes and the intent summary is written, spawn a **Spec agent**
(`model: "claude-opus-4-6"`).

Pass it:
- The full issue body + comments (if issue reference mode), or the free-form description.
- The path to the intent summary: `.claude-work/INTENT_<slug>-<number>.md`
- `GIT_ROOT` (or note that codebase context is unavailable).
- The output path: `.claude-work/REFINED_<slug>-<number>.md`

### Spec agent instructions

Role: read-only codebase research + produce refined spec. No file writes except the output document.
No dialogue with the user — all intent is already captured in the intent summary.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions)
   if they exist.
2. If `.codesight/CODESIGHT.md` exists at `$GIT_ROOT`, read it in full.
3. If `docs/agent_index.md` exists at `$GIT_ROOT`, read it in full.
   If not found there, glob for `**/agent_index.md` and read any match.
4. Read the intent summary at `.claude-work/INTENT_<slug>-<number>.md` in full. This is your
   source of truth for what the user wants — treat it as authoritative.

**Phase A — Codebase surface area research**

Search the codebase to enumerate *every place where the behavior described in the intent summary
must be present*. Do not assume the issue author knows all the relevant components.

**Required search checklist — perform all of these before declaring surface area complete:**
1. The user-facing verb from the issue title (e.g. "validate", "check", "generate")
2. The object noun from the issue title (e.g. "reading level", "FK grade", "token")
3. Any existing symbol or function that already does a fraction of the requested behavior
4. All files matching repo-convention globs for entry points:
   `**/cli*`, `**/commands*`, `**/handlers*`, `**/routes*`, `**/pipeline*`, `**/server*`
5. Any config, hook, or script files that invoke the affected behavior

After completing the checklist, state explicitly:
```
Surface area search: examined N files, found M candidate matches across the required checklist.
Coverage confidence: [high / medium / low — explain if medium or low]
```

For each entry point found, check whether the relevant behavior currently exists there, is
partially present, or is entirely absent.

**Dead-code check:** For any symbol that appears to implement the requested behavior, grep for
its name and count call sites. If call sites ≤ 1 (i.e., only the definition), flag it as
suspicious: *"defined at `src/quality.py:42` but found no call sites — may be unwired."*
Do not conclude it is unreachable; list the evidence and let the implementer verify.

If `GIT_ROOT` is empty, Phase A cannot run against a real codebase. Mark all surface area rows
as `[UNVERIFIED — no codebase]` and note that the user must validate the table manually.

**Phase B — Produce the refined spec**

Write `.claude-work/REFINED_<slug>-<number>.md`. Ground every section in the intent summary —
do not invent intent. If the intent summary is silent on something, say so explicitly.

```markdown
# Refined Spec: <title> (#<number> | free-form)

## Job Statement
When I <situation>, I want to <motivation>, so I can <outcome>.

*Bad example (too shallow):* "When I generate content, I want to check reading level, so I can
have reading level checked." The outcome is just the motivation restated.
*Good example:* "When I generate content, I want to check reading level, so I can confidently
publish material that any 6th grader can read without friction."
The outcome must describe a real-world consequence, not just the presence of the mechanism.

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

| Component | File / path (with line numbers) | Change required | Acceptance scenario(s) it satisfies |
|---|---|---|---|
| <e.g. FK check function> | `src/pipeline/quality.py:42` | Wire into generation pipeline | Entry Point: CLI, Entry Point: Server |
| <e.g. CLI `generate` command> | `src/cli/generate.py:118` | Pass FK result to output validator | Entry Point: CLI |
| <e.g. Orchestration server> | `server/handlers/run.py:77` | Apply same validation before returning | Entry Point: Server |

Include the starting line number of the relevant function or block. If line numbers are
unavailable (e.g., no codebase), mark the path as `[UNVERIFIED]`.

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
- The job statement outcome is a real-world consequence, not a restatement of the motivation.
- The surface area search coverage statement is present and honest.
- Any suspicious dead-code symbols are flagged in the surface area table or as a note.
- The job statement, behavioral intent, and hidden assumptions are grounded in the intent summary —
  not inferred independently. If the intent summary is missing something, flag it rather than guess.

---

## Step 4 — Publish to GitHub

Publish the spec to GitHub **before** reporting completion. The GitHub issue is the approval
surface — the user reviews and approves the spec there, not in this session.

### If the input was a free-form description (no existing issue)

Always create a new GitHub issue with the refined spec as the body:

```bash
SPEC_PATH="$GIT_ROOT/.claude-work/REFINED_<slug>-<number>.md"
BODY_PATH="/tmp/gh_body_<number>.md"
{
  echo "## Refined Spec (generated by /refine-issue)"
  echo ""
  cat "$SPEC_PATH"
  echo ""
  echo "---"
  echo "*Spec generated by /refine-issue — ready for review.*"
} > "$BODY_PATH"
gh issue create --repo <REPO> \
  --title "<title derived from the Job Statement>" \
  --body-file "$BODY_PATH"
```

`REPO` is determined from the current git remote (same logic as bare-number detection in Setup).
If no remote can be determined, ask the user which repo to create the issue in.

### If the input was an issue reference and `--no-post` was NOT passed (default)

Post the refined spec as a comment on the existing issue:

```bash
SPEC_PATH="$GIT_ROOT/.claude-work/REFINED_<slug>-<number>.md"
BODY_PATH="/tmp/gh_body_<number>.md"
{
  echo "## Refined Spec (generated by /refine-issue)"
  echo ""
  cat "$SPEC_PATH"
  echo ""
  echo "---"
  echo "*Spec generated by /refine-issue — ready for review.*"
} > "$BODY_PATH"
gh issue comment <number> --repo <REPO> --body-file "$BODY_PATH"
```

### If the input was an issue reference and `--no-post` was passed

Do not post to GitHub. The spec exists only locally.

---

## Step 5 — Report Completion

After publishing, present this summary (do not print the full spec — the user reviews it on GitHub):

```
## refine-issue complete

Input: #<number> <title> | "<description>"
Intent summary: .claude-work/INTENT_<slug>-<number>.md
Spec: <issue URL or .claude-work/REFINED_<slug>-<number>.md if --no-post>
Search coverage: <coverage statement from Phase A>

Entry points identified: <N>
Surface area: <N> components
```

---

## Constraints

- Never write or modify source files.
- Never open branches, commits, or PRs.
- Never assume the issue author has named all the components that need to change.
- If a codebase is unavailable (no git root), the Spec agent must clearly mark the surface
  area table as "unverified — codebase not available" and the user must validate it manually.
- The output spec is a *recommendation*, not a binding contract — the user should review it
  before passing it to `/fix-issue` or `/resolve-issue`.
- If blocked or uncertain about the repo structure, stop and report rather than guessing.
- The Intent agent must not produce a spec — only the intent summary. The Spec agent must not
  conduct dialogue — only formalize what the Intent agent discovered.
