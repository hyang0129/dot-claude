# /fix-issue improvement plan — remove in-skill Reviewer

Decision: `/fix-issue` no longer reviews. After implementation + binary checks
pass, the skill pushes the branch and leaves the PR in **draft**. The user runs
`/pr-review-cycle <PR>` to review, fix findings, and (later) flip to ready.

**Rationale.** The in-skill Reviewer (`REV` subagent) and its fix-apply loop
(`R-POST-REV` on ROOT) together account for ~36% of `/fix-issue` cost in the
14-day window ($222.58 of $614.91). `/pr-review-cycle` already performs the
same review with a better architecture — per-finding Fixer subagents on a
small context instead of Opus-ROOT patching files with 200K of accumulated
prompt replayed on every turn. Users already chain the two skills in
practice, so removing the in-skill Reviewer is a deduplication, not a
capability loss.

**Safety verified.** `/pr-review-cycle` is draft-indifferent: it uses only
`gh pr view`, `gh pr diff`, `gh pr comment`, and Fixer commits to the branch.
No `isDraft` checks, no `gh pr ready` / `gh pr merge` calls.

---

## Expected impact

| Metric | Before (14d) | After (est.) | Delta |
|---|---|---|---|
| REV subagent cost | $106.71 | $0 | −$106.71 |
| R-POST-REV ROOT cost | $115.87 | $0 | −$115.87 |
| Skill-attributable total | $614.91 | ~$392 | ~**−36%** |
| Per-invocation mean | ~$6.34 | ~$4.04 | ~−$2.30 |

Caveats: the user still pays `/pr-review-cycle` cost for the same PRs — but
that cost already exists in the current workflow (users chain the skills
manually, paying for both reviewers). The genuine saving is the in-skill
Reviewer + ROOT-fix-apply that is now redundant.

## Risk

**Risk 1: user forgets to run `/pr-review-cycle` and merges an unreviewed PR.**
Mitigation: leave the PR in **draft**. `gh pr merge` on a draft requires an
explicit `--force` flag or flipping to ready, so there is meaningful friction
before an unreviewed merge. The Final Summary also nudges the user to run
`/pr-review-cycle`.

**Risk 2: `/pr-review-cycle` doesn't like something about the draft state we
haven't noticed.** Mitigation: verified above (no draft-gated code paths).
Acceptance check explicitly runs one end-to-end `/fix-issue` → `/pr-review-cycle`
flow on a test issue before closing the change.

**Risk 3: a Tier-1 bug fix that would have been caught by the current
Reviewer's "scope creep" check now ships to draft unchecked.** Accepted.
`/pr-review-cycle` catches the same things more rigorously with its Intent
Validator. The only window of exposure is "user opens draft PR and reads it
themselves without running `/pr-review-cycle`" — which is their choice.

---

## Wave 1 — text-only edits to `commands/fix-issue.md`

Zero structural risk. All edits are deletions or re-wordings.

### 1.1 Delete Step 5 entirely
- [ ] Remove lines 582–611 (the whole `## Step 5 — Reviewer` section,
      including Reviewer agent instructions and the iteration loop).
- [ ] Remove the `---` separator at line 611.

### 1.2 Rewire Step 5b (E2E QA) to run immediately after validation
- [ ] Rewrite the opening sentence of `## Step 5b — E2E QA` so it reads:
      `After Step 4 validation passes, run E2E QA if the repo has Playwright
      tests.` (was: implicitly after Step 5).
- [ ] Unchanged: the push + `/e2e-qa` invocation and PASS/FAIL gating. E2E
      failures still block proceeding.

### 1.3 Rewrite Step 6 — push, no ready flip
- [ ] Rename the heading from `## Step 6 — Push and Mark PR Ready` to
      `## Step 6 — Push (PR stays in draft)`.
- [ ] Update the checklist — delete the `Reviewer findings addressed or
      documented` bullet; keep the other four bullets.
- [ ] Replace the final block:
      ```bash
      gh pr ready <PR_NUMBER> --repo <owner/repo>
      ```
      with:
      ```bash
      # PR is intentionally left in draft. The user runs:
      #   /pr-review-cycle <PR_NUMBER>
      # to review the PR. That skill does not flip draft state either — the
      # user marks it ready manually when they are satisfied.
      ```
- [ ] Remove the `Outstanding items` section placeholder from the PR body
      template (nothing populates it without a Reviewer).

### 1.4 Update Step 6b Documentation Agent PR body template
- [ ] Delete the `## Outstanding items` block from the body template around
      lines 812–815. Keep the rest of the Implementation walkthrough.
- [ ] The existing sentence "This runs before `/pr-review-cycle` so
      reviewers have full context when they open the PR" stays — it is now
      literally accurate.

### 1.5 Final Summary nudge
- [ ] In `## Final Summary`, delete the `### Review findings` block (three
      bullets about critical/major/minor).
- [ ] Remove `Reviewer` from the `### Agents used` list.
- [ ] Append a new block at the bottom of the summary template:
      ```
      ### Next step
      PR is in draft. Run `/pr-review-cycle <PR_NUMBER>` to review, then mark
      ready when satisfied.
      ```

### 1.6 Subagent Context Bootstrap list
- [ ] Remove `Reviewer` from the bootstrap list at line 271 (subagents that
      read/modify source code). Keep Planner, Architect, Coder, Tester,
      Integrator, Documentation Agent.

### 1.7 Tier descriptions in Step 3
- [ ] Rewrite `### Tier 1 — single Coder, then Reviewer` heading and text
      to `### Tier 1 — single Coder`. Replace the sequence diagram
      `Coder → [binary checks] → commit → Reviewer` with
      `Coder → [binary checks] → commit`.
- [ ] In `### Tier 2` section, remove "then spawn Reviewer" from the last
      sentence.
- [ ] In `### Tier 3` section, remove "then Reviewers in parallel
      (correctness / security / performance — one lens per invocation)."
- [ ] Remove the Step 3 model note about Reviewer (lines ~487: "use
      `model: "claude-opus-4-6"` for Reviewer agents") — there are no
      Reviewer agents in this skill anymore.

### 1.8 Copy the edited file into `~/.claude/commands/`
Per repo `CLAUDE.md`: `commands/` files are copied, not symlinked. After
editing the repo copy, manually copy into `~/.claude/commands/fix-issue.md`.

**Acceptance checks (Wave 1):**
- [ ] `grep -ci reviewer commands/fix-issue.md` returns the number of
      Reviewer mentions — should drop from current (≈35) to 0 *excluding*
      the Step 6b sentence that mentions `/pr-review-cycle` by name and any
      cross-reference we intentionally keep.
- [ ] `grep -n "gh pr ready" commands/fix-issue.md` returns no matches.
- [ ] Markdown renders without broken section references.

---

## Conflicts / things we are *not* doing

- **Not** auto-invoking `/pr-review-cycle` from `/fix-issue`. Keeping them
  composable means the user can review on their own timeline (e.g. after
  hand-editing, after rebasing) rather than always immediately after `fix-issue`.
- **Not** changing `/pr-review-cycle` to flip draft → ready. That's a merge
  concern, not a review concern. Final flip stays manual.
- **Not** altering R-DONE accounting (the 20.2% tail of user-continuation
  turns in the session file). That cost is real but not skill-attributable;
  the only mitigation is session hygiene (user starts a fresh Claude Code
  session after the PR is open), which is orthogonal to this change.

---

## Sequencing

Wave 1 is a single PR against `dot-claude`.
