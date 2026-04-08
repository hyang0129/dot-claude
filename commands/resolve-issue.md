# Resolve Issue

## Purpose

Orchestrator only. Sequences `/fix-issue`, `/review-fix`, and `/rebase` as isolated subagents with fresh context windows.

**This command never reads files, never runs git commands, and never writes code.**
Its sole job is to pass structured handoff data between the three phases.

Running each phase in a separate subagent prevents the context accumulation that causes poor
handoff adherence when all three phases run in a single growing conversation.

---

## Args

Same as `/fix-issue`: `/resolve-issue <issue> [tier] [--worktree] [--base <branch>]`

All arguments are forwarded verbatim to the fix-issue subagent.

---

## Step 1 — fix-issue phase

Spawn an Agent subagent (`model: "opus"`) to run the fix-issue skill with the provided arguments.

Append these instructions to the subagent prompt:

> After presenting the Final Summary, **stop immediately**. Do not invoke `/review-fix` or any
> other command — the orchestrator handles sequencing. Return the following block as the very
> last thing in your output:
>
> ```
> HANDOFF
> WORK_DIR=<absolute path — WORK_DIR value set during branch creation>
> BRANCH=<branch name, e.g. fix/issue-42-short-slug>
> PR_URL=<full GitHub PR URL, or empty if PR creation failed>
> PR_NUMBER=<integer, or empty if PR creation failed>
> REPO=<owner/repo>
> SUCCESS=<true|false>
> FAILURE_REASON=<empty if SUCCESS=true, otherwise a one-line description>
> END_HANDOFF
> ```

Wait for the subagent to complete. Parse the `HANDOFF` block from its output.

**Gate**: if `SUCCESS=false`, stop here. Report `FAILURE_REASON` to the user. Do not proceed to Step 2.

---

## Step 2 — review-fix phase

Spawn an Agent subagent (`model: "opus"`) to run the review-fix skill:

```
/review-fix <WORK_DIR> <BRANCH>
```

Append these instructions to the subagent prompt:

> After presenting the Human Review Summary and posting the PR comment with the
> `<!-- review-fix-summary -->` sentinel, **stop immediately**. Do not invoke `/rebase` —
> the orchestrator handles sequencing. Return the following block as the very last thing
> in your output:
>
> ```
> HANDOFF
> SUCCESS=<true|false>
> BLOCKERS=<"none" | brief one-line description of each blocker, semicolon-separated>
> FAILURE_REASON=<empty if SUCCESS=true, otherwise a one-line description>
> END_HANDOFF
> ```
>
> Blockers that prevent /rebase from running:
> - Any batch failed its tests and was not committed
> - The final push failed
> - The intent validator found high-risk findings that were not resolved

Wait for the subagent to complete. Parse the `HANDOFF` block from its output.

**Gate**: if `SUCCESS=false` or `BLOCKERS` is not `none`, stop here. Report the blockers to
the user. Do not proceed to Step 3.

---

## Step 3 — rebase phase

Spawn an Agent subagent (`model: "opus"`) to run the rebase skill:

```
/rebase <BRANCH>
```

No additional instructions needed — rebase runs to its own terminal state (READY or BLOCKER)
and reports to the user directly.

Wait for the subagent to complete. Relay its terminal state to the user.

---

## Final report

Present to the user:

```
## resolve-issue complete: #<number> <title>

Phase 1 — fix-issue:  ✓ PR #<PR_NUMBER> created (<PR_URL>)
Phase 2 — review-fix: ✓ <N> findings addressed, <N> cycles
Phase 3 — rebase:     <READY ✓ | BLOCKER ✗ — see above>

Branch: <BRANCH>
PR: <PR_URL>
```

---

## Constraints

- This orchestrator never touches files, git, or GitHub directly.
- Each subagent runs in an isolated context — do not summarize or repeat the subagents' internal work beyond what is needed for the final report.
- If any phase fails, stop immediately and report to the user. Do not attempt to continue or retry automatically.
- The subagents handle all error reporting within their phases. Only the `HANDOFF` gate conditions (SUCCESS, BLOCKERS) determine whether to proceed.
- Never pass `--admin` or bypass branch protection at any phase.
