---
version: 1.0.0
---

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

`/refine-issue <issue> [--no-post] [--base <branch>] [--obvious]`

- `issue`: required. One of:
  - GitHub issue number (e.g. `42`)
  - Full GitHub issue URL (e.g. `https://github.com/org/repo/issues/42`)
  - Quoted free-form description (e.g. `"add reading level checks to the generation pipeline"`)
- `--no-post`: optional flag. If present and `issue` is a number or URL, keep the refined spec
  local only — do not post it to GitHub. Ignored in free-form mode (see below).
- `--base <branch>`: optional flag. Specifies the base branch to check out before scanning the
  codebase. If omitted, the base branch is auto-detected (see Setup).
- `--obvious`: optional flag. Skip the interactive intent interview. A user-surrogate subagent
  answers the probe dimensions from the issue body + codebase + constitution, citing sources
  for each answer and marking anything it cannot ground as `[unanswered]`. ROOT then presents
  the surrogate's draft intent summary for a single confirm/correct round before proceeding
  to Step 3. Use this when the issue body is detailed enough that intent is mechanical (dead
  code removal, field renames, well-documented bugfixes). If the surrogate returns mostly
  `[unanswered]` markers or many `[ESCALATE]` entries, that's a signal the issue is not
  actually obvious — drop the flag and run the interactive flow.

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

### Base branch checkout

After `REPO` is set, switch to the correct base branch so the codebase scan runs against clean,
merged code rather than a feature branch:

```bash
# Detect base branch (skip if --base was given)
if [ -n "<BASE_FROM_ARG>" ]; then
  BASE_BRANCH="<BASE_FROM_ARG>"
else
  BASE_BRANCH="$(gh repo view --repo "$REPO" --json defaultBranchRef \
    --jq '.defaultBranchRef.name' 2>/dev/null)"
  if [ -z "$BASE_BRANCH" ]; then
    git show-ref --verify --quiet refs/heads/dev 2>/dev/null \
      && BASE_BRANCH="dev" || BASE_BRANCH="main"
  fi
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "$BASE_BRANCH" ]; then
  # Refuse to switch away from a dirty working tree — the user has uncommitted work.
  if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree has uncommitted changes on $CURRENT_BRANCH. Stash or commit before re-running." >&2
    exit 1
  fi
  git checkout "$BASE_BRANCH"
fi

# Sync the base branch with its remote so the codebase scan sees current code.
# Working tree must be clean (already enforced above when switching branches; re-check in
# case we were already on the base branch with dirty state).
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree on $BASE_BRANCH is dirty. Stash or commit before re-running." >&2
  exit 1
fi

SYNC_NOTE=""
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  REMOTE="$(git rev-parse --abbrev-ref '@{u}' | cut -d/ -f1)"
  git fetch --quiet "$REMOTE" "$BASE_BRANCH" 2>/dev/null || true
  LOCAL_SHA="$(git rev-parse HEAD)"
  REMOTE_SHA="$(git rev-parse '@{u}')"
  BASE_SHA="$(git merge-base HEAD '@{u}')"
  if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    SYNC_NOTE=""  # already up to date
  elif [ "$LOCAL_SHA" = "$BASE_SHA" ]; then
    git merge --ff-only '@{u}' >/dev/null
    SYNC_NOTE=" (fast-forwarded to $REMOTE/$BASE_BRANCH)"
  elif [ "$REMOTE_SHA" = "$BASE_SHA" ]; then
    SYNC_NOTE=" (local is ahead of $REMOTE/$BASE_BRANCH — not syncing)"
  else
    echo "Base branch $BASE_BRANCH has diverged from $REMOTE/$BASE_BRANCH." >&2
    echo "Resolve the divergence (rebase, reset, or pick a different --base) before re-running." >&2
    echo "Refusing to scan against a base that doesn't match the remote — the spec would describe code the reviewers can't see." >&2
    exit 1
  fi
else
  # No upstream. If we plan to post to GitHub, we cannot validate that the local code matches
  # the GitHub repo we're publishing to — bail. If --no-post was passed, the spec is local
  # only and a missing remote is acceptable.
  if [ "<NO_POST_FLAG>" != "true" ]; then
    echo "Base branch $BASE_BRANCH has no upstream tracking — cannot verify it matches the GitHub repo we'd be posting to." >&2
    echo "Either set tracking (git branch --set-upstream-to=<remote>/$BASE_BRANCH) or re-run with --no-post." >&2
    exit 1
  fi
  SYNC_NOTE=" (no upstream — local-only spec)"
fi
```

Tell the user: `On branch <BASE_BRANCH><SYNC_NOTE>.` (one line; omit if already on that branch and no sync note). If the "ahead" warning fires, surface it prominently — the spec's surface-area table may reference lines that don't exist on the remote yet.

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
test -d "$GIT_ROOT/.agent-work" && echo "EXISTS" || echo "MISSING"
```
If `MISSING`, stop and tell the user:
```
.agent-work/ not found in this repo. Please run:
  mkdir -p <GIT_ROOT>/.agent-work && echo '.agent-work/' >> <GIT_ROOT>/.git/info/exclude
Then re-run this command.
```
Do not proceed until the directory exists.

When `GIT_ROOT` is empty, the Spec agent writes its output to a temp path instead:
`/tmp/REFINED_<slug>-<number>.md`. Report this path to the user in the final summary.

### Constitution detection

If `GIT_ROOT` is set, look for a project constitution (prefer the mini form, since it is the
designated agent-injection target):

```bash
CONSTITUTION_PATH=""
for candidate in "$GIT_ROOT/CONSTITUTION.mini.md" "$GIT_ROOT/CONSTITUTION.md"; do
  if [ -f "$candidate" ]; then
    CONSTITUTION_PATH="$candidate"
    break
  fi
done
```

If `CONSTITUTION_PATH` is non-empty, **read it in full now, in this session** (not via a
subagent) — Step 2 must be able to cite laws inline while the interview is running, and a
subagent's findings won't be in your working context when you need them. Tell the user one
line: `Constitution detected: <N laws> loaded from <basename>.` Keep the file in context for
the duration of Step 2; Step 3's Spec agent will re-read it from disk.

If no constitution is found, proceed without one. Skip the constitution-inference rule and the
"Constitution fit" probe dimension in Step 2, and skip the constitution sections in the Step 3
spec template. Do not infer laws from `CLAUDE.md` or general engineering norms — only a real
constitution grants the authority to pre-fill answers.

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
ls "$GIT_ROOT/.agent-work/REFINED_${SLUG}"-*.md 2>/dev/null
# Partial interview draft
ls "$GIT_ROOT/.agent-work/INTENT_${SLUG}"-*.md 2>/dev/null
```

If a **completed spec** (`REFINED_*`) is found, ask:
```
Found existing refined spec: .agent-work/REFINED_<slug>-<id>.md

Resume from it (r) or start over (s)?
```
- If **resume**: read the existing file, skip to Step 4 and proceed from there.
- If **start over**: delete both the `REFINED_*` and any `INTENT_*` file, continue to Step 2.

If only a **partial interview draft** (`INTENT_*`) is found (no `REFINED_*`), ask:
```
Found a partial interview draft: .agent-work/INTENT_<slug>-<id>.md
The interview was interrupted before a spec was produced.

Resume the interview from the saved Q&A (r) or start over (s)?
```
- If **resume**: read the draft, reconstruct what was covered from the Q&A log, and continue the interview from where it left off (Step 2) — do not re-ask questions already answered.
- If **start over**: delete the draft and continue to Step 2 fresh.

---

## Step 2 — Intent Interview

**Mode selection:**
- If `--obvious` was passed → run the **surrogate flow** (Step 2a).
- Otherwise → run the **interactive flow** (Step 2b, the default).

---

### Step 2a — Surrogate flow (`--obvious` only)

Spawn the user-surrogate subagent (`commands/refine-issue/surrogate-prompt.md`,
`model: "claude-sonnet-4-6"`). Pass it:

- The full issue body and comments (or the free-form description, in free-form mode).
- `GIT_ROOT` (or note that codebase context is unavailable).
- `CONSTITUTION_PATH` (empty if no constitution was loaded).
- The output path: `.agent-work/INTENT_<slug>-<id>.md`.
- The slug and id, so the surrogate can produce the file directly.

The surrogate runs the same probe dimensions the interactive flow uses, answers each
from the inputs (with `Source:` citations), marks anything ungrounded as `[unanswered]`,
and writes the `INTENT_<slug>-<id>.md` file in one shot. It does **not** post to GitHub
— that happens after the user confirms below.

When the surrogate returns, present its work to the real user:

1. Render the draft intent summary in chat (read the file the surrogate wrote).
2. List `[unanswered]` entries explicitly, e.g.:
   *"Surrogate could not ground 2 probes: priority/timeline, downstream-dependency.
   Issue body is silent on both."*
3. List any `[ESCALATE]` entries verbatim — these are questions the surrogate flagged
   for the human.
4. Ask:
   ```
   Confirm to proceed to spec, or correct anything?
   ```

Resolution:
- **User confirms** → finalize the intent file (strip the `[DRAFT — surrogate]` marker
  from the title). Post the finalized intent to GitHub once (issue-ref mode: comment;
  free-form mode: create the issue). Proceed to Step 3.
- **User corrects** → apply the correction to the intent file directly. If the
  correction surfaces a new dimension or open question rather than a simple text fix,
  fall through into the interactive flow (Step 2b) using the corrected file as the
  starting point — the user's correction counts as Round 1. When the user re-confirms,
  finalize and proceed to Step 3.

If `GIT_ROOT` is empty **and** the issue body is shorter than ~10 lines, warn before
spawning the surrogate: *"Limited grounding available — codebase context is unavailable
and the issue body is short. Surrogate may return many `[unanswered]` entries. Proceed
with `--obvious` (y) or drop into interactive (n)?"* — and respect the user's choice.

---

### Step 2b — Interactive flow (default)

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

6. **Constitution fit** (only when a constitution was detected in Setup)
   - Which law does this work touch hardest? Walk the Review Heuristic and name any
     question that would answer "unclear" under the current scope.
   - For any scope carve-out (e.g. "only tool X for now", "deferred to issue #N"), does the
     carve-out leave another surface in violation of a law in the interim — and is that
     acceptable, a follow-up with a tracked issue, or something the user hadn't considered?
   - Is the author deliberately choosing a stance *stricter* than the constitution requires
     (over-compliance), or stopping at the law's minimum? Either is valid, but it must be
     explicit so downstream implementers don't quietly relax or tighten it.

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
- **When a constitution was detected in Setup, check it before asking each planned
  question.** For each question, scan the loaded constitution for a law whose stance,
  anti-pattern, Why clause, or rejected alternative constrains the answer. If one does,
  present the inference inline instead of asking open-endedly:
  ```
  I was going to ask: <the question>
  Per Law N (<short name>): I infer <answer> because <specific clause — anti-pattern,
  Why failure mode, or rejected alternative — quoted or paraphrased tightly>.
  Stop me if that's wrong — <next question>
  ```
  Rules on using this:
  - **The constitution never reduces the question count.** Every probe dimension above
    (outcome / hidden scope / acceptance / constraints / priority / constitution fit) must
    still be covered. The constitution only pre-fills *proposed answers within* those
    dimensions; the user must still confirm, narrow, or override.
  - **Cite the specific clause, not the law number alone.** "Per Law 1" is not a citation;
    "Per Law 1's anti-pattern on truncation without a machine-readable signal" is. This
    both lets the user audit the inference and forces you to actually check rather than
    hallucinate law coverage.
  - **If an inference collides with what the user wants, that tension is data** — surface
    it in the round's summary, do not swallow it. A user who wants to be stricter than a
    law, or who is knowingly accepting a carve-out, is naming a non-obvious intent the
    spec must carry forward.
  - **Do not infer from `CLAUDE.md`, general engineering norms, or "obviously".** Only
    clauses that appear in the loaded constitution grant inference authority. If the
    constitution is silent on a question, ask the user open-endedly.
- When the user answers, synthesize what you've learned before asking the next round.
  Show them you understood, then probe the remaining gaps.
- If an answer opens a new dimension you hadn't considered, follow it.
- Do not declare understanding complete until you can articulate:
  - The job statement (when / want / so I can) with a real-world outcome
  - At least one hidden assumption the issue didn't surface
  - What "done" looks like from the user's perspective
  - What's explicitly out of scope
- **Before signalling completion, do a final constitution check** (only when a constitution was
  detected in Setup). With the full intent now in view — job statement, behavioral intent,
  assumptions, scope carve-outs — scan the loaded constitution for any tension that only becomes
  visible in the *aggregate* (i.e., a combination of answers that collectively leave a surface
  non-compliant, even if each individual answer passed its per-question check). This is distinct
  from probe dimension 6: dimension 6 fires mid-interview when intent is still being assembled;
  this check fires against the complete, coherent picture. If a tension is found, include it as
  a `**Constitution tension:**` bullet in the completion summary below — do not re-enter probe
  rounds. If no tensions are found, omit the bullet entirely.
- Signal completion by saying:
  ```
  I think I have a complete picture of your intent. Here's what I'll hand off to the spec:

  **Job statement:** When I <situation>, I want to <motivation>, so I can <real-world outcome>.
  **Core behavioral intent:** <2–3 sentences on observable change>
  **Key hidden assumptions:** <bullet list>
  **Done looks like:** <what the user will check>
  **Out of scope:** <explicit exclusions>
  **Constitution tension:** <only present if the final check found an aggregate tension — cite
  the specific clause and the carve-out or scope choice that creates it. Omit this line
  entirely if no tensions were found.>

  Does this capture it accurately, or is there anything to correct?
  ```
- Wait for the user to confirm or correct before concluding.

**Checkpoint writes — do not wait until the end:**

At the very start of Step 2 — before asking any questions — write a stub draft locally and on GitHub:

**Local file** `.agent-work/INTENT_<slug>-<id>.md`:
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

**GitHub (issue-ref mode):** Post a comment on the existing issue and capture its ID:
```bash
COMMENT_ID=$(gh issue comment <number> --repo <REPO> \
  --body "## Intent Interview — in progress

*The intent interview has started. This comment will be updated after each round.*

### Q&A Log
*(no rounds completed yet)*" \
  --json id --jq '.id')
```

**GitHub (free-form mode):** Create the GitHub issue now (before asking questions) with a draft body, and capture the new issue number for use as `<id>` throughout:
```bash
ISSUE_URL=$(gh issue create --repo <REPO> \
  --title "<first ~10 words of description>" \
  --body "## Intent Interview — in progress

*The intent interview has started. This issue will be updated after each round.*

### Q&A Log
*(no rounds completed yet)*")
# Extract issue number from URL for use as <id>
```

After **each interview round**, do both:

1. Append to the local draft file's `Clarifying Q&A Log` section:
```
**Round N**
Q: <your questions>
A: <user's answers>
```

2. Edit the GitHub comment/issue body to append the new round:
```bash
# Issue-ref mode — update the existing comment
gh api repos/<REPO>/issues/comments/$COMMENT_ID \
  --method PATCH \
  --field body="## Intent Interview — in progress
...
### Q&A Log
**Round 1** ...
**Round N**
Q: <questions>
A: <answers>"

# Free-form mode — update the issue body
gh issue edit <new-issue-number> --repo <REPO> \
  --body "<updated body with new round appended>"
```

This ensures that if the session is interrupted, the work is recoverable from GitHub (not just the local filesystem), and the resume check in Step 1 can pick up either source.

**Output:** When the user confirms, overwrite the local draft with the finalized intent summary. Then replace the GitHub comment/issue body with the final content (no "[DRAFT]" marker):
`.agent-work/INTENT_<slug>-<id>.md`

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

## Constitution Alignment
<Only include this section if a constitution was detected. Omit entirely otherwise — do not
leave an empty "N/A" stub.>

- **Laws touched:** <list of law numbers and short names this work interacts with>
- **Inferences carried forward:** <each inference the user confirmed during the interview,
  tagged with its source clause — e.g. "Response must disclose incompleteness (Law 1
  anti-pattern on truncation)">
- **Carve-outs / tensions:** <any scope limit or behavior choice that tensions with a law,
  plus the Review-Heuristic answer the author is accepting — e.g. "file_skeleton only;
  callers/callees deferred to #51. Accepts that those tools remain Law-1-non-compliant in
  the interim because staleness is a graph-wide property and fixing one tool demonstrates
  the pattern before propagating.">
- **Stance vs. minimum:** <for each law touched, note whether the chosen behavior meets
  the law's minimum or exceeds it, and why>

## Clarifying Q&A Log
<A compact log of the key exchanges — question → answer — that surfaced non-obvious intent.
Include only rounds that changed understanding, not small clarifications.>
```

---

## Step 3 — Spec Agent (one-shot formalization)

After the Intent agent completes and the intent summary is written, spawn a **Spec agent**
(`model: "claude-sonnet-4-6"`).

Pass it:
- The full issue body + comments (if issue reference mode), or the free-form description.
- The path to the intent summary: `.agent-work/INTENT_<slug>-<number>.md`
- `GIT_ROOT` (or note that codebase context is unavailable).
- The output path: `.agent-work/REFINED_<slug>-<number>.md`
- `REPO` (owner/repo).
- `CONSTITUTION_PATH` (empty string if no constitution was detected).
- Publish mode: one of `comment` (issue-ref, default), `create` (free-form), or `none` (`--no-post`).
- For `comment` mode: the existing issue number to comment on.

### Spec agent instructions

Role: read-only codebase research, produce refined spec, **then publish it to GitHub and return
a short summary to ROOT.** The Spec agent owns both writing the spec file and the `gh` publish
step so ROOT does not have to replay its accumulated context on trivial Bash calls. No dialogue
with the user — all intent is already captured in the intent summary.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions)
   if they exist.
2. If `.codesight/CODESIGHT.md` exists at `$GIT_ROOT`, read it in full.
3. If `docs/agent_index.md` exists at `$GIT_ROOT`, read it in full.
   If not found there, glob for `**/agent_index.md` and read any match.
4. Read the intent summary at `.agent-work/INTENT_<slug>-<number>.md` in full. This is your
   source of truth for what the user wants — treat it as authoritative.
5. If `CONSTITUTION_PATH` is non-empty, read that file in full. The intent summary's
   "Constitution Alignment" section tells you which laws are load-bearing for this work;
   the constitution text itself is the authoritative source for clause wording you cite in
   the spec (acceptance scenarios and carve-outs must reference specific clauses, not just
   law numbers). If `CONSTITUTION_PATH` is empty, skip the constitution sections in the
   spec template below — do not invent laws from `CLAUDE.md` or general norms.

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

Write `.agent-work/REFINED_<slug>-<number>.md`. Ground every section in the intent summary —
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
**Upholds:** <only when a constitution exists: Law N (short name) — specific clause this
scenario enforces, e.g. "Law 1 — every query answer declares its own certainty; the
`stale: bool` annotation is the machine-readable disclosure Law 1's anti-pattern requires.">

### Entry Point: <name> (e.g. Orchestration Server `/run` endpoint)
**Given** ...
**When** ...
**Then** ...
**Falsifiability:** ...
**Upholds:** ...

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
left unspecified, implementers may either under- or over-reach. For any carve-out that leaves
a surface in tension with a constitution law, say so and name the Review-Heuristic stance the
author is accepting.>

## Constitution Alignment
<Only include this section if `CONSTITUTION_PATH` is non-empty. Omit entirely otherwise.>

- **Laws touched:** <list of law numbers and short names>
- **Inference log:** <each inference carried from the intent summary into this spec, tagged
  with its source clause — these are the pre-filled answers the user confirmed during the
  interview. Include them here so downstream implementers see the reasoning, not just the
  acceptance criteria.>
- **Carve-outs / tensions:** <any scope limit or behavior choice in this spec that tensions
  with a law, plus the Review-Heuristic answer the author is accepting. One bullet per
  carve-out. If there are none, write "None — every surface in scope is in compliance.">
- **Stance vs. minimum:** <for each law touched, whether the chosen behavior meets the
  minimum or exceeds it, and why>

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
- **When a constitution exists** (`CONSTITUTION_PATH` non-empty): every acceptance scenario
  has an `Upholds:` line citing the specific clause it enforces (not just a law number);
  every carve-out in Out of Scope that tensions with a law is named in Constitution
  Alignment's `Carve-outs / tensions` bullet along with the Review-Heuristic stance; every
  law listed in `Laws touched` appears in at least one `Upholds:` line or carve-out note.

**Phase C — Publish to GitHub**

After the spec file is written and quality-checked, publish it per the `Publish mode` you were
given. The GitHub issue is the approval surface — the user reviews and approves the spec there.

Build the body file once and reuse it:

```bash
SPEC_PATH="$GIT_ROOT/.agent-work/REFINED_<slug>-<number>.md"
BODY_PATH="/tmp/gh_body_<number>.md"
{
  echo "## Refined Spec (generated by /refine-issue)"
  echo ""
  cat "$SPEC_PATH"
  echo ""
  echo "---"
  echo "*Spec generated by /refine-issue — ready for review.*"
} > "$BODY_PATH"
```

- **Publish mode `comment`** (issue-ref, default): check whether a prior spec comment already exists on the issue, then patch it in place rather than appending a new one:
  ```bash
  PRIOR_COMMENT_ID=$(gh issue view <number> --repo <REPO> --json comments \
    --jq '[.comments[] | select(.body | startswith("## Refined Spec (generated by /refine-issue)")) | .databaseId] | last // empty')
  if [ -n "$PRIOR_COMMENT_ID" ]; then
    gh api repos/<REPO>/issues/comments/$PRIOR_COMMENT_ID \
      --method PATCH --field body="$(cat "$BODY_PATH")"
  else
    gh issue comment <number> --repo <REPO> --body-file "$BODY_PATH"
  fi
  ```
  This ensures re-runs update the existing spec comment in place rather than appending a duplicate, so `resolve-issue` always sees exactly one authoritative spec.
- **Publish mode `create`** (free-form): `gh issue create --repo <REPO> --title "<title derived from the Job Statement>" --body-file "$BODY_PATH"` — capture the new issue URL from stdout.
- **Publish mode `none`** (`--no-post`): skip publishing; the spec exists only locally.

### Spec agent return summary

After publishing (or skipping, if `none`), return exactly these fields to ROOT — nothing else.
Do not repeat the spec body; ROOT does not need it.

```
ISSUE_URL: <URL of the comment or new issue, or "(local only)" if --no-post>
SPEC_PATH: .agent-work/REFINED_<slug>-<number>.md
ENTRY_POINTS: <N>
SURFACE_AREA: <N components>
SEARCH_COVERAGE: <one-sentence coverage statement from Phase A>
```

---

## Step 4 — Report Completion

The Spec agent published the spec. ROOT's only remaining job is to print the summary below
using the fields the Spec agent returned — do not read the spec file, do not post anything,
do not re-render context. The user reviews the spec on GitHub.

```
## refine-issue complete

Input: #<number> <title> | "<description>"
Intent summary: .agent-work/INTENT_<slug>-<number>.md
Spec: <ISSUE_URL from Spec agent>
Search coverage: <SEARCH_COVERAGE from Spec agent>

Entry points identified: <ENTRY_POINTS>
Surface area: <SURFACE_AREA>

Review the spec on GitHub and approve or request changes there.
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
