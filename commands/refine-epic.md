# Refine Epic

## Purpose

Captures and locks the **intent** behind an epic — the author's feared failure mode, resolved
tradeoffs, hard invariants, and rejected alternatives — so that every downstream decision
(child issue boundaries, implementation calls, agent escalations) can be resolved by reference
to that intent instead of re-asking the author.

Decomposition into independently shippable child issues is a consequence of this, not the goal.
Child issues exist to propagate intent into executable slices; the dependency graph, integration
seams, and risk register exist to keep that propagation honest. If intent capture fails, nothing
downstream can recover — conflicting PRs, duplicated slices, and missed subsystems are all
symptoms of an unvalidated WHY, not of a bad cut of the work.

The core failure this command prevents: agents (or humans) executing epic work against an
inferred intent that diverges from the author's actual one.

**This command never writes source code and never opens PRs.**
Its outputs, in priority order:
1. A validated intent document, published to the epic issue body and as a changelog comment
   (the master surface for all downstream work).
2. A compressed intent digest, embedded into every child issue so the WHY travels with the work.
3. An index document + per-slice child drafts that carry the intent forward into executable units.
4. Optionally, GitHub child issues created after decomposition.

The natural pipeline: `/refine-epic` → intent locked and published → child issues created,
each inheriting compressed intent → surrogate-driven `/refine-issue` per child (seeded from
intent, no re-asking the author) → `/resolve-issue` per child.

---

## Args

`/refine-epic <epic>`

- `epic`: required. One of:
  - GitHub issue number (e.g. `147`)
  - Full GitHub issue URL (e.g. `https://github.com/org/repo/issues/147`)
  - `owner/repo#number` reference (e.g. `acme/api#147`)
  - Quoted free-form description (e.g. `"migrate all storage backends to S3"`)

Input detection:
- Matches `^[\w.-]+/[\w.-]+#\d+$` → extract `owner/repo` and issue number directly.
- Matches `^\d+$` → bare issue number; repo must be detected (see Setup).
- Matches `^https?://github\.com/` → extract `owner/repo` and issue number from URL.
- Otherwise → free-form description.

---

## Setup

### Repo detection

If `epic` is `owner/repo#number` or a full URL, extract `owner/repo` directly — no detection or
confirmation needed. Set `REPO=<owner/repo>` and proceed.

If `epic` is a **free-form description**, detect the repo the same way as a bare number (below),
then confirm with the user before proceeding. The GitHub epic issue will be created after the
intent document is written (see Step 2 — Publish).

If `epic` is a bare number, detect the repo:
```bash
git remote -v
gh repo view --json nameWithOwner
```

Determine `owner/repo`:
- If exactly one GitHub remote, use it.
- If multiple remotes, prefer `upstream` (fork workflow), otherwise `origin`.
- If no remote can be found, check conversation context for a repo name.

**Confirm only when the repo was auto-detected** (i.e., `epic` was a bare number):
```
Repo detected: <owner/repo> (from <source>)

Proceed with epic #<number> in <owner/repo>? [yes / no / different-repo]
```

Wait for the user to confirm or correct. Then set `REPO=<owner/repo>`.

### Fetch the epic (issue reference mode only)

```bash
gh issue view <number> --repo <REPO> --json number,title,body,labels,comments
```

Also fetch any issues already linked as children so the Decomposer does not re-propose them:

```bash
gh issue list --repo <REPO> \
  --search "\"#<number>\" in:body" \
  --json number,title,state \
  --limit 50
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

If `GIT_ROOT` is empty, all output goes to `/tmp/EPIC_<slug>-<number>/`. Mark all surface area
as `[UNVERIFIED — no codebase]`. Report this path to the user in the final summary.

### Output directory

Set `EPIC_DIR`:
- With git root: `$GIT_ROOT/.claude-work/EPIC_<slug>-<number>/`
- Without git root: `/tmp/EPIC_<slug>-<number>/`

where `<slug>` is a 3–4 word kebab-case summary of the epic title or description, and `<number>`
is the issue number (or a short hash for free-form).

---

## Step 1 — Resume Check

Before spawning anything, check whether a prior decomposition exists:

```bash
test -d "$EPIC_DIR" && echo "EXISTS" || echo "MISSING"
```

If the directory exists, list its contents and ask:
```
Found existing epic work: .claude-work/EPIC_<slug>-<number>/
  intent.md          (present / missing)
  index.md           (present / missing)
  child-1-<slug>.md
  child-2-<slug>.md
  ...

Resume options:
  (r) resume decomposition — skip Clarifier, go straight to Decomposer (requires intent.md)
  (i) re-run intent validation only — redo Clarifier, keep existing child drafts
  (s) start over — delete everything and begin from Step 2
```

- **Resume (r)**: if `intent.md` is present, skip Step 2 (Clarifier) and spawn the Decomposer
  directly. If `intent.md` is missing, treat as start-over and warn the user.
  If `index.md` is also present, skip to Step 4 (present decomposition) — do not re-spawn
  the Decomposer agent.
- **Re-run intent (i)**: delete `intent.md` only, re-run Step 2, keep all child draft files.
- **Start over (s)**: delete the directory contents and continue to Step 2.
- **Free-form mode** (no issue number): skip this check entirely.

---

## Step 2 — Intent Validation (Interactive)

**This step is the highest-leverage point in the entire workflow.** The failure mode it prevents
is not under-documentation — it is capturing an intent that diverges from the organization's
actual intent, or from the author's *considered* intent (vs. their reflexive one). Every
compounding misalignment in downstream child issues traces back to a gap here.

Before spawning the Clarifier, tell the user:

```
Starting intent validation. I'll scan the codebase and map stakeholders first, then ask
scan-calibrated questions (not abstract tradeoff questions). A separate Challenger agent
will then produce the strongest counter-intent the evidence also supports, and you'll
rebut it. The rebuttal is the most load-bearing content in the final document.

Expect: 1–3 interactive rounds depending on epic tier (Lite / Standard / Heavy).
```

**Run the Clarifier process directly in this session** — do NOT spawn a subagent for this step.
The Clarifier requires multiple interactive Q&A rounds with the real user; a subagent cannot
do that. You are the Clarifier for Step 2.

### Clarifier process

Role: elicit intent via evidence-grounded questions, detect anchoring and bluffing, force
disconfirmation via a Challenger pass, produce a tier-appropriate intent artifact. No source
file writes. No branch, commit, or PR creation.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` and `$GIT_ROOT/CLAUDE.md` if they exist.
2. If `GIT_ROOT` is unavailable, Sub-phase 1 degrades to vocabulary-only. Mark scan outputs
   `SKIPPED — no codebase` and proceed. Lite tier becomes unavailable; default to Standard.

---

**Sub-phase 1 — Evidence First: Codebase + Stakeholder Scan**

Before asking the user any question, scan the codebase and surface the evidence that will
calibrate every subsequent question. The epistemic principle: anchoring is hard to undo. Ask
the user about concretes, not abstractions.

**Scan target 1 — Existing domain implementations.** Grep for key nouns and verbs from the
epic title/body. Does this capability partially exist? Is the epic extending or replacing?

**Scan target 2 — Rejection signals.** Commented-out code, FIXME/TODO notes naming
alternatives, dependency manifests showing added-then-removed libraries. Surface as evidence,
do not interpret.

**Scan target 3 — Coarse module boundaries.** Top-level packages/directories the epic will
touch. Name only — do not read internals yet.

**Scan target 4 — Stakeholder map (CODEOWNERS + call graph).** Read `CODEOWNERS` if present.
For every module the epic will touch, identify the owning team. For every symbol or file the
epic will modify, grep for call sites *outside* the owning module — those are downstream
consumers. Produce: `<module> → owner → N external consumers`.

**Scan target 5 — Borrowed invariants.** Identify contracts this epic will load-bear on:
schemas, SLOs documented in code or config, rate limits, auth boundaries, retention policies.
These are constraints the epic depends on but does not own.

Produce two working artifacts (not output files yet — surfaced inline during Sub-phase 3):

1. **Inferences list.** Up to 5 named inferences, prioritized by "would change the shape of
   at least one child issue if wrong." Format: `[INFER] <claim>. Confirm or correct.`
2. **Stakeholder matrix.** Every adjacent team and the specific surface they own that this
   epic will touch, plus every borrowed invariant with its owner.

---

**Sub-phase 2 — Tier Decision**

From the scan, assess epic size and pick a tier. State the choice to the user with reasoning
drawn from the scan; allow one override.

- **Lite** — touches ≤1 module, no adjacent team owns affected code, <1 week of work,
  ≤2 child issues. Output: a Kill-Criterion Card (5 fields, ~150 words). No full intent doc,
  no compressed derivative, no changelog comment.
- **Standard** — 2–3 modules, 1–2 adjacent teams affected, 1–4 weeks, 3–6 child issues.
  Output: full `intent.md` + extractive compression + GitHub publishing.
- **Heavy** — >3 modules, or >2 adjacent teams affected, or >4 weeks, or >6 child issues, or
  Sub-phase 1 found a rejection signal against a library currently in production. Output:
  Standard + mandatory stakeholder confirmation before decomposition + required ADR links
  for ONE-WAY-DOOR priors.

Present:
```
Tier: <chosen> — because <reasoning from scan>.
Override to {Lite|Standard|Heavy}? Otherwise proceed with <chosen>.
```

---

**Sub-phase 3 — Premortem + Scan-Calibrated Questions**

Replace abstract tradeoff questions with one narrative-forcing prompt plus scan-grounded
follow-ups. Do not pre-name tradeoff axes — that anchors the user onto a framing the
Clarifier already has.

**Premortem (always asked, verbatim):**

> "It is six months from now. This epic shipped on schedule and every line of code works as
> designed. Despite that, someone is writing a blameless postmortem about why this was the
> wrong thing to build — or the right thing built the wrong way. Write the first paragraph
> of that postmortem. Be specific: name the cohort affected, the observable symptom, and the
> decision that looks wrong in hindsight."

Do not accept a one-line answer. If the response is <4 sentences or abstract ("it didn't solve
the problem"), push back: "Too abstract — give me the specific scenario. Who is angry, what
did they try to do, what happened instead?"

**Scan-calibrated follow-ups (Standard + Heavy).** Generate 3–5 questions grounded in
Sub-phase 1 evidence. Do not ask abstract tradeoff questions. Templates:

- *"I found [specific code pattern]. My inference is [interpretation]. Is that right — and
  if not, what should I understand instead?"*
- *"Here are two inferences I could draw from the same evidence: A or B. Which is closer, or
  is it neither?"* (use this disconfirming frame for at least one follow-up)

**Required questions (Standard + Heavy):**

- **Q-stakeholders:** "Name three people or teams who must not be surprised when this ships.
  For each, what's the specific thing they'd be surprised by?"
- **Q-borrowed:** *(seeded with the Sub-phase 1 borrowed-invariants list)* "For each of these,
  have you confirmed with the owner, or are you assuming stability? If confirmed, paste or
  link the confirmation. If assuming, state the blast radius if the assumption breaks."
- **Q-commitment:** "If this ships and six months later we want to walk it back, what's the
  hardest thing to undo? Name the specific artifact — a table, a protocol field, a public
  API, a vendor contract."
- **Q-success:** "What measurable signal in production proves this worked? Give a specific
  metric and a threshold. If you cannot name one, state why this is unfalsifiable."
- **Q-kill:** "What dated, falsifiable condition would make you abandon this epic — not
  ship it poorly, abandon it?"
- **Q-portfolio:** "What are you not doing this cycle because you're doing this?"

**Lite tier asks only:** premortem, Q-kill, Q-success, Q-stakeholders (if any external
consumers exist in the scan), Q-portfolio. Skip the rest.

Present all questions for a round together in a single block — do not serialize.

---

**Sub-phase 4 — Bluffing and Anchoring Detection**

Score every answer against these detectors. Any two firing triggers a **probe round** —
reject the abstract answer and force a concrete anchor before continuing.

Bluffing signals:
- Answer arrives in <15 seconds and echoes the epic body phrasing verbatim.
- Certainty markers without reasoning ("obviously", "clearly", "we all know").
- Tradeoff answers that name both sides without committing ("fast *and* correct").
- Invariants phrased as preferences ("should be", "ideally", "would be nice").
- No named alternative in Q-kill or priors ("nothing really", "we just knew").
- Feared-failure mode that's a restatement of the goal inverted ("failure = it doesn't work").

Considered-position signals (do not probe further):
- Names the alternative and its strongest argument *before* rejecting it.
- Cites a concrete past incident, PR, or observed behavior.
- Qualifies ("usually X, except when Y").

**Probe round prompts:** "Name one specific user who would be angry." / "Describe the
incident that made you conclude this." / "Walk me through the last time you saw this
failure." / "Steelman the opposite position — what would someone who disagreed argue?"
Continue probing until answers carry concrete anchors.

---

**Sub-phase 5 — Challenger Pass (Standard + Heavy only)**

Before writing the intent document, spawn a **Challenger subagent**
(`model: "claude-sonnet-4-6"`). This is the single highest-leverage structural protection
against sycophancy — the Clarifier stops being the only voice in the room.

Pass the Challenger:
- Sub-phase 1 scan outputs (inferences list, stakeholder matrix, borrowed invariants).
- The Q&A transcript from Sub-phase 3, verbatim.
- **Do NOT pass the epic body text.** The Challenger must reason from scan + transcript only.

Challenger instructions:

> You are an adversarial reviewer. Your job is to produce the strongest case *against* the
> author's stated intent — the alternative epic the same evidence could equally support.
> You have no access to the original epic body; you have only the codebase scan and the
> Q&A transcript.
>
> Produce a one-page counter-intent: a plausible alternative interpretation of what the
> author should actually be doing, grounded in the evidence. Argue that the author's
> stated intent is the wrong shape, the wrong scope, the wrong priority, or optimizing
> for the wrong failure mode. Name the strongest alternative concretely. Cite specific
> scan findings or Q&A excerpts.
>
> Do not hedge. The user's rebuttal of this document is the most load-bearing content
> in the final intent artifact.

Present the Challenger's output to the user:

```
A separate agent, given only the scan and your answers (not your epic body), could
reasonably conclude THIS instead:

<paste Challenger output>

Rebut it. Where specifically is it wrong? What does it miss? If parts of it are
correct, which parts will you absorb into the intent document?
```

Capture the rebuttal verbatim. It becomes Section 10 of the intent document. A rebuttal that
concedes one or more points triggers a revision round on the sections it affects.

---

**Sub-phase 6 — Stakeholder Confirmation Gate (Heavy tier only)**

For every borrowed invariant identified in Sub-phase 1 and confirmed in Q-borrowed, require
one of three dispositions from the author:

- **Confirmed** — paste or link the owner's confirmation.
- **Tagged** — tag the owning team on the epic issue with a deadline for response. Proceed
  but flag as `CONDITIONAL` in the intent doc.
- **Assumed, unverified** — explicit acknowledgement, with the specific blast radius stated.

If a borrowed invariant on a critical path is **Assumed, unverified**, halt:

```
HALT — critical-path borrowed invariant is unverified:

<invariant> — owner: <team>

Confirm with the owner, tag them with a deadline, or accept documented blast radius
before decomposition.
```

---

**P0 blocker / contradiction detection (runs throughout Sub-phases 3–5).**

While processing answers, evaluating the Challenger rebuttal, or reading the epic body, watch
for:
- Dependency on an unresolved external decision.
- A stated constraint that contradicts the epic's stated goal.
- An explicit "we haven't decided" gating the entire decomposition.
- An answer that directly contradicts another answer or scan evidence.

If found, halt and surface it specifically. Do not proceed until resolved.

```
HALT — <P0 blocker | contradictory intent>:

<specifics>

Resolve before the intent document can be written.
```

---

**Produce intent artifact**

**Lite tier → `EPIC_DIR/intent.md` (Kill-Criterion Card)**

```markdown
# Epic Intent Card: <Title>

**Epic Issue:** <org/repo>#<number> — <URL>
**Captured:** <YYYY-MM-DD>
**Tier:** Lite

---

## Cohort
<One sentence: who the user is, named concretely.>

## Status Quo
<What this cohort does today without this epic.>

## Kill Criterion
<Dated, falsifiable condition under which this epic is abandoned — not shipped poorly,
abandoned. Example: "If by 2026-06-01, weekly active cohort users have not moved by 15%,
abandon.">

## One ABSOLUTE Invariant
<The single constraint whose violation requires undoing the work. If the author named more
than one, Sub-phase 4 pushed back until they chose one.>

## Opportunity Cost
<The other work not happening this cycle because this epic is.>
```

This card **is** the compressed form. No Compressor runs for Lite tier. Pass the card itself
directly to downstream agents.

**Standard + Heavy tier → `EPIC_DIR/intent.md`**

Write each section as causal prose — no keyword bullet lists. A downstream agent reading
this must be able to simulate the author's answer to an implementation decision that was
never explicitly raised.

```markdown
# Epic Intent: <Title>

**Epic Issue:** <org/repo>#<number> — <URL>
**Captured:** <YYYY-MM-DD>
**Tier:** <Standard | Heavy>

---

## 1. Trigger and Pain
<Observable symptoms today. Why now rather than later?>

## 2a. Author-Feared Failure Mode
<The author's premortem paragraph, verbatim. The outcome that would make this a failure
even if every line of code shipped correctly.>

## 2b. System-Level Failure Mode
<What the organization regrets in 18 months even if the author's feared failure didn't
materialize. Constructed from the stakeholder map + Challenger rebuttal, ratified by the
author. If author-fear and system-fear diverge, note the divergence explicitly — that
divergence is often the most important signal in this document.>

## 3. Decision Priors
<One paragraph per major tradeoff axis already resolved. "We chose X over Y because Z."
Tag each: REVERSIBLE / ONE-WAY-DOOR / EXPENSIVE-TO-REVERSE. For each prior, also state:
"What would change our mind" — the falsifiable trigger that flips the choice. End with
a single **Dominant Priority** sentence naming the prior that outweighs the others.>

## 4. Stakeholder Intent & Borrowed Invariants
<Stakeholder matrix from Sub-phase 1, plus the author's Q-stakeholders answers. For each
borrowed invariant: owner, disposition (Confirmed / Tagged / Assumed-unverified), blast
radius if violated. Distinguishes constraints this epic OWNS (section 8) from constraints
this epic DEPENDS ON but another team owns.>

## 5. Architectural Commitment & Reversibility
<From Q-commitment. Distinguish code-reversible (rename, refactor) from architecture-
reversible (schema, protocol, identity, storage engine, vendor contract). Name the
irreversible commitments concretely — "adds column X to table Y", not "database change".>

## 6. Success Metrics & Kill Criterion
<From Q-success and Q-kill. Quantified production signal (metric + threshold) proving the
epic worked. Dated, falsifiable abandonment condition. These are the sections child issues
are scored against.>

## 7. Rollback Posture
<How a rollback works: feature flag, config toggle, migration reversal, irreversible.
State the blast radius of a bad ship, the revert time, and the observability hook (log,
metric, alert) that detects the need to roll back.>

## 8. Invariants (Author-Owned)
<Hard constraints this epic OWNS. ABSOLUTE (violation requires undoing) or STRONG
(violation requires documented override). Quantified where possible: "p99 < 150ms",
"error rate < 0.1%", "cost < $500/month". Qualitative invariants without numbers are
flagged for the author to quantify or drop.>

## 9. Anti-Choices (incorporates Non-Goals)
<"We considered X and rejected it because Y." Include explicit "this epic does not do X"
non-goals. Conditional rejections state the revisit condition. Drop any rejection that
the author cannot name the strongest argument for — Sub-phase 4 already caught those.>

## 10. Challenger Rebuttal
<The Challenger's counter-intent (verbatim) followed by the author's rebuttal (verbatim).
Conceded points are called out explicitly and reflected in updates to sections 1–9.>

## 11. Open Questions (Author-Deferred)
<Name decision, why unresolved, flag: ESCALATE (surface to user before proceeding) or
TIMEBOX (agent may decide within 24h, document reasoning). Empty with heading if none.>

---

## Inferences From Existing Code
<From Sub-phase 1, author-ratified in Sub-phase 3. Each entry: [INFER] statement → author's
response.>
```

Value Function (previously a separate section) is removed — it duplicated Decision Priors.
Non-Goals are merged into Anti-Choices. Feared Failure is split into author-level (2a) and
system-level (2b) because they diverge more often than authors admit.

After writing `intent.md`, print the full document to the user.

If Sub-phases 3–5 completed without halting and the Challenger rebuttal either resolved or
explicitly accepted every conceded point, the intent is validated — proceed directly to
publishing. Only pause if TIMEBOX items remain unaddressed:

```
Intent document written. One unresolved item before I proceed:

<specific gap>

Clarify this and I'll post the document and start decomposition.
```

---

**Create epic GitHub issue (free-form mode only):**

If the input was a free-form description, create the epic issue now before publishing the
intent document. Title is derived from the description (kebab-slug expanded to title case):

```bash
gh issue create --repo <REPO> \
  --title "<epic title>" \
  --body-file - <<'EOF'
<paste the Trigger and Pain section text from intent.md here — do not reference the file path>

---
*Epic created by /refine-epic from free-form description. Full intent document will follow as a comment.*
EOF
```

Use `--body-file -` and a heredoc so content is passed inline, not as a file reference.
Capture the new issue number and URL. Set `<number>` to this value. Update `EPIC_DIR` to
use the new issue number (rename the directory if needed). From this point forward, treat
this as issue reference mode.

---

**Publish to GitHub — two surfaces:**

First, post the full intent as a changelog comment on the epic issue, with the
`<!-- INTENT_DOC -->` marker for downstream tooling:

```bash
gh issue comment <number> --repo <REPO> --body-file - <<'EOF'
<!-- INTENT_DOC -->
## Epic Intent Document (generated by /refine-epic)

<paste the full text of intent.md here — do not reference the file path>

---
*This document captures the validated intent before decomposition. Reply with corrections
before decomposition is reviewed.*
EOF
```

Capture the returned comment URL as `INTENT_COMMENT_URL`.

Second, rewrite the epic issue body to prepend a `## Validated Intent` section. Keep the
original author's text below. For Standard/Heavy, include sections **2a, 2b, 3, 4, 6, 8, 9,
and 10** — section 10 (Challenger Rebuttal) is deliberately surfaced on the body so the
disconfirming work is visible to all downstream readers. For Lite, the body gets the
Kill-Criterion Card verbatim.

```bash
ORIGINAL_BODY="$(gh issue view <number> --repo <REPO> --json body -q .body)"
gh issue edit <number> --repo <REPO> --body-file - <<EOF
## Validated Intent

*Captured by /refine-epic on <YYYY-MM-DD>. Tier: <Lite|Standard|Heavy>.
Full document: <INTENT_COMMENT_URL>*

<paste the tier-appropriate sections per above>

---

## Original Description

\${ORIGINAL_BODY}
EOF
```

If the epic body already contains a `## Validated Intent` section (prior run), replace it
in place rather than stacking. Detect by matching the heading through `## Original Description`.

Report both URLs to the user.

---

**Extractive compression (Standard + Heavy only — replaces the Haiku Compressor).**

Compression is now a deterministic concatenation performed by the main agent — no LLM
paraphrase. LLM paraphrase smooths away the load-bearing qualifiers ("X over Y *when Z
holds*") that cost multiple Q&A rounds to elicit. Write `EPIC_DIR/intent-compressed.md` by
verbatim extraction:

```markdown
# Compressed Intent: <Title>

**Full intent:** <INTENT_COMMENT_URL>

## Feared Failure Modes
<Section 2a verbatim>

<Section 2b verbatim>

## ABSOLUTE Invariants
<Every ABSOLUTE-tagged item from Section 8, verbatim. Drop STRONG.>

## Load-Bearing Decision Priors
<The Dominant Priority paragraph from Section 3, verbatim. Plus every ONE-WAY-DOOR and
EXPENSIVE-TO-REVERSE prior, verbatim, including its "What would change our mind" trigger.
Drop REVERSIBLE priors.>

## Borrowed Invariants (Unconfirmed on Critical Path)
<From Section 4: only entries with disposition "Tagged" or "Assumed, unverified".
Skip this section entirely if all confirmed.>

## Success Metric & Kill Criterion
<Section 6 verbatim>

## Irreversible Commitments
<From Section 5, only the irreversible items, verbatim.>

## Key Anti-Choices
<Top 3 from Section 9, author-ranked if Heavy tier, otherwise first 3. Verbatim.>
```

No paraphrase. No token budget. No summarization.

For Lite tier, skip `intent-compressed.md` — the Kill-Criterion Card is already the
compressed form.

Do not print `intent-compressed.md` to the user — it is scaffolding for child issues.

The Clarifier process is now complete. Proceed to Step 3 and spawn the Decomposer.

---

## Step 3 — Decomposition (Autonomous)

**Intent is now locked. Tell the user they can step away:**

```
Intent document is finalized and posted to GitHub. Spawning the Decomposer now — this
will run autonomously and may take several minutes. Come back when you see the
decomposition summary. You don't need to stay.
```

The Decomposer runs to completion without requiring user input. Do not interrupt it with
questions, progress checks, or confirmations. The user reviews the full output in Step 4.

Spawn a **Decomposer agent** (`model: "claude-opus-4-6"`).

Pass it:
- The full epic body + comments (if issue reference mode), or the free-form description.
- The list of already-existing child issues (if any were found during Setup).
- `GIT_ROOT` (or note that codebase context is unavailable).
- `EPIC_DIR` as the output directory.
- `EPIC_DIR/intent.md` as the source of truth for author intent. The Decomposer must read
  this document before Phase A and treat it as authoritative. When any implementation
  decision conflicts with the codebase evidence found in Phase B, the Decomposer resolves
  the conflict using the reasoning in `intent.md` — specifically sections 3 (Decision Priors),
  5 (Invariants), and 2 (Feared Failure Mode) — rather than escalating.
- `EPIC_DIR/intent-compressed.md` — the compressed version the Decomposer embeds into each
  child draft's Inherited Intent block (see C2). The Decomposer picks the *slice-relevant*
  invariants for each child rather than pasting the full compressed file verbatim.
- `INTENT_COMMENT_URL` — the GitHub URL of the full intent comment, to cite in each child's
  Inherited Intent block so readers can always reach the unabridged document.

### Decomposer agent instructions

Role: read-only research + produce decomposition plan. No file writes except documents inside
`EPIC_DIR`. No source file modifications. No branch or PR creation.

**Context bootstrap (do this before anything else):**
1. Read `~/.claude/CLAUDE.md` (global instructions) and `$GIT_ROOT/CLAUDE.md` (repo instructions)
   if they exist.
2. If `.codesight/CODESIGHT.md` exists at `$GIT_ROOT`, read it in full.
3. If `docs/agent_index.md` exists at `$GIT_ROOT`, read it in full.
   If not found there, glob for `**/agent_index.md` and read any match.
4. If `GIT_ROOT` is unavailable, Phase B degrades to vocabulary-only analysis — no file paths,
   no call-site counts. Mark every surface area row as `UNVERIFIED — codebase not available`
   and continue.

---

**Phase A — Understand the Epic's Scope and Decomposition Goal**

Read the epic issue body and all comments in full. Produce a private working note (not an output
file) covering:

**A1. Stated scope.** What the author literally described. Quote the key phrases.

**A2. Decomposition goal.** What the author actually needs: independently shippable slices that
each move the system toward the epic's end state. Distinguish between:
- Slices the author named explicitly
- Slices implied by the work but not mentioned
- Work mentioned that is NOT a slice (cross-cutting concerns, one-time migrations, infra
  prerequisites)

**A3. Dependency identification.** For each candidate slice, ask:
- Can this ship and deliver value without any other slice being complete?
- If no: which slice must precede it, and why?

A slice that cannot answer "yes" to the first question is not independently shippable. It must
either be merged with its dependency or flagged as a prerequisite block.

**A4. Workstream seams.** Group slices by the primary system boundary they cross (e.g. data
layer, API layer, CLI, frontend, background jobs, infra). Seams are where the decomposition
cuts — slices within a workstream are sequential; slices across workstreams may be parallel.

Do not include existing child issues (passed in from Setup) as proposed slices. Reference them
in the index doc under a "Existing Children" section.

---

**Phase B — Codebase Research (run per workstream, not per epic)**

For each workstream identified in Phase A, perform independent surface area research. Do not
collapse multiple workstreams into a single search pass.

**Required search checklist per workstream — do not skip steps:**

1. **Vocabulary grep.** Grep for the primary noun and verb from the workstream's concern.
   Record every file that matches.

2. **Entry point enumeration.** Search for all user-facing entry points relevant to this
   workstream: `**/cli*`, `**/commands*`, `**/handlers*`, `**/routes*`, `**/views*`,
   `**/server*`, `**/app*`, `**/jobs*`, `**/tasks*`, `**/workers*`, `**/settings*`,
   `**/config*`. List every match — do not filter yet.

3. **Dead integration check.** For each function or class that implements the workstream's core
   behavior: grep for its name and count call sites. If call sites ≤ 1 (defined but not called,
   or only self-referential), flag it as a suspected unwired integration — file and line number.
   Do not conclude whether it is truly dead; surface the evidence for the implementer.

4. **Integration seam detection.** Identify any file or component that multiple workstreams
   will need to modify. Flag these explicitly — they require sequencing or coordination across
   slices and must appear in the Risk Register.

5. **Test coverage probe.** Grep for the workstream's primary symbols in `**/test*` and
   `**/spec*` directories. Record which entry points have no corresponding test file match —
   these are coverage gaps the slice spec must address.

After completing all workstream searches, state explicitly:
```
Decomposition research: examined N files across M workstreams.
Integration seams identified: <list>
Coverage confidence: [high / medium / low — explain if medium or low]
```

---

**Phase C — Produce Output Artifacts**

Write two artifact types into `EPIC_DIR`.

**C1. Epic index document** — `EPIC_DIR/index.md`

```markdown
# Epic: <Title>

**Epic Issue:** <org/repo>#<number> — <URL>
**Status:** DRAFT | UNKNOWNS_BLOCKED | READY_TO_EXECUTE
**Last Updated:** <YYYY-MM-DD>

---

## Problem Statement

<One paragraph. What user experience or system property is broken or missing today?
Written from the outside in — observable symptoms, not internal state.>

## Goals

<Bulleted outcome statements. Each must be falsifiable at the epic level.
Format: "Users/operators/systems can <observable outcome> without <current friction>."
Do NOT write Given/When/Then here — that belongs in child issues.>

-
-

## Non-Goals

<Explicit. If it came up in discussion and was ruled out, it belongs here.>

-

## Constraints

<Technical, organizational, or contractual limits that shape the solution space.>

-

---

## Open Questions / Unknowns

| ID | Question | Priority | Resolution Owner | Deadline | Status |
|----|----------|----------|-----------------|----------|--------|
| U1 | | P0/P1/P2 | | YYYY-MM-DD | OPEN |

**Gate rule:** No child issues move to implementation until all P0 unknowns are RESOLVED.
If any P0 unknown is OPEN, epic status MUST be `UNKNOWNS_BLOCKED`.

---

## Dependency Graph

<ASCII or prose. Describes sequencing constraints across slices.
If all slices are parallelizable, state that explicitly.>

```
[Slice 1] ──► [Slice 3] ──► [Slice 5]
[Slice 2] ──► [Slice 3]
[Slice 4] (independent — parallel with Slice 1 and 2)
```

## Integration Seams

<Shared components that multiple slices modify. For each seam: which slices touch it and
what coordination is required.>

## Decomposition Table

| Child # | Title | Behavioral Question | Depends On | DRI / Team | Rough Effort | Status |
|---------|-------|---------------------|------------|------------|--------------|--------|
| 1 | | | — | TBD | XS/S/M/L/XL | DRAFT |
| 2 | | | Child #1 | TBD | | DRAFT |

**Behavioral Question:** The specific observable behavior this child issue must produce.
One sentence. If you cannot write it from available context, mark the cell `NEEDS HUMAN INPUT`
and do not create a draft file for that child.

## Risk Register

| Risk | Affected Slices | Likelihood | Mitigation |
|------|----------------|------------|------------|
| <e.g. shared DB migration conflicts> | Slice 2, Slice 4 | Medium | Land Slice 2 first |
| <e.g. API contract change breaks callers> | Slice 3 | Low | Version the endpoint |

## Out of Scope for This Epic

<Anything explicitly excluded. If unspecified, implementers will over-reach or under-reach.>

## Existing Children

<Child issues that already exist at the time of refinement. Do not re-propose these.>

---

## Sign-Off Gate

| Role | Name | Status | Date |
|------|------|--------|------|
| Engineering DRI | | PENDING | |
| Affected Team Lead(s) | | PENDING | |

**Gate rule:** Epic must reach APPROVED from all required roles before any child issue is
handed to `/resolve-issue`. Partial sign-off does not unblock execution. The Decomposer
cannot enforce this mechanically — it states it explicitly and sets status accordingly.
```

**C2. Per-slice child issue draft** — `EPIC_DIR/child-<N>-<slug>.md`, one file per slice

```markdown
# Child Issue Draft: <Title>

**Parent Epic:** <org/repo>#<epic-number>
**Child Index:** <N> of <total>
**DRI / Team:** <name or TBD>
**Rough Effort:** XS | S | M | L | XL
**Depends On:** Child #<N> | none

---

## Behavioral Question

<One sentence. The observable behavior this issue must produce when complete.>

## Inherited Intent (from epic #<epic-number>)

*Compressed from the validated intent document. Full version: <INTENT_COMMENT_URL>*

**Feared Failure Mode:** <verbatim from intent-compressed.md — do not paraphrase>

**Invariants that apply to this slice:**
- <ABSOLUTE invariant 1 relevant to this slice's surface area>
- <ABSOLUTE invariant 2 relevant to this slice's surface area>

**Relevant Decision Priors:** <1–2 priors from intent-compressed.md whose tradeoff axis
this slice is most likely to touch. One sentence each. If none apply, write "None — this
slice does not cross any resolved tradeoff axis" and link to the full intent comment.>

<The Decomposer populates this block from intent-compressed.md. Slice-relevance filter:
include an invariant or prior only if this slice's surface area could plausibly violate it.
When uncertain, include it — under-inclusion here is the failure mode this block exists
to prevent.>

## Background

<Context from the epic scoping this child. 2–4 sentences max. References epic index.>

## Acceptance Scenarios

<One Given/When/Then block per affected entry point — same schema as /refine-issue.>

### Scenario 1 — <Entry Point Name>
**Given** <precondition>
**When** <user action at this entry point>
**Then** <observable outcome>
**Falsifiability:** <the test that would have caught "wired but disconnected">

## Surface Area

| Component | File / path (with line numbers) | Change required | Scenario(s) it satisfies |
|-----------|--------------------------------|-----------------|--------------------------|
| | `src/example.py:42` | | |

## Integration Seams

<Any files this slice shares with adjacent slices. Coordination required.>

## Slice Independence Statement

This slice can ship without any other slice in this epic being complete because:
<one concrete reason — e.g. "it adds a new column with a default value and no existing code
path reads it until child #3 wires the API.">

If this statement cannot be written, do not create this child draft — merge the slice with
its dependency and document the merge in the epic index.

## Out of Scope

<Anything explicitly excluded from THIS child even if related to the epic.>

## Open Questions

| ID | Question | Priority | Owner | Deadline |
|----|----------|----------|-------|----------|
```

---

**Quality checks before finishing:**

- [ ] Every slice has a written Slice Independence Statement. Any slice that failed the
  independence test is merged with its dependency or converted to a prerequisite.
- [ ] No file path appears in two different slice surface area tables without an explicit
  Integration Seam entry in the index and in both affected child drafts.
- [ ] The dependency graph is a DAG — no cycles.
- [ ] Every risk in the Risk Register maps to at least one named mitigation.
- [ ] The dead integration check ran for every workstream. Every suspicious symbol appears in
  the relevant child's surface area table with a "verify wiring" note.
- [ ] Every child with a missing Behavioral Question is marked `NEEDS HUMAN INPUT` in the
  decomposition table, and no draft file was created for it.
- [ ] Every child draft's Inherited Intent block contains a verbatim Feared Failure Mode,
  at least the slice-relevant ABSOLUTE invariants, and the `INTENT_COMMENT_URL` citation.
  A child with an empty or placeholder Inherited Intent block is not considered complete.
- [ ] Coverage confidence statement is present. Any workstream rated "low" is flagged in the
  index for human review before implementation begins.
- [ ] If any P0 unknown exists, epic status is set to `UNKNOWNS_BLOCKED` and no child drafts
  are written — only the index with the unknowns table.

---

## Step 4 — Create Child GitHub Issues

Trigger: Decomposer completes Step 3 with no P0 unknowns blocking.

For each slice with a complete Behavioral Question, in dependency order (leaves of
the DAG first):

```bash
gh issue create --repo <REPO> \
  --title "<proposed child issue title from index.md>" \
  --body "$(cat <<'EOF'
Part of epic #<number>.

<full contents of EPIC_DIR/child-<N>-<slug>.md>

---
*Generated by /refine-epic. Review before running /resolve-issue on this child issue.*
EOF
)" \
  --label "child-issue"
```

After each issue is created, capture its number and URL. Update `EPIC_DIR/index.md` to record
the mapping: `Child N → #<child-number> <url>`.

After all child issues are created, print:
```
Child issues created:
  Child 1: #<n> <title> — <url>
  Child 2: #<n> <title> — <url>
  ...

Starting surrogate-driven refinement for each child. No questions will be asked —
the epic intent document provides the surrogate's knowledge base.
```

---

## Step 5 — Surrogate-Driven Child Refinement

Run immediately after Step 4, processing children in dependency order (serial).

The premise: Step 2 captured enough author reasoning that a surrogate seeded from
`intent.md` can answer all questions the `/refine-issue` Intent agent would ask —
without escalating to the real user.

### Per-child: spawn a Surrogate agent (model: "claude-sonnet-4-6")

For each child issue, spawn a dedicated Surrogate agent. Do not start the next child
until the current one completes.

Pass each Surrogate:
- Full contents of `EPIC_DIR/intent-compressed.md` (not the full `intent.md` — the compressed
  version is sufficient for answering refinement questions and keeps the Surrogate's context
  focused on what matters to this slice)
- Full contents of the assigned child's draft: `EPIC_DIR/child-<N>-<slug>.md`
- The path to `EPIC_DIR/intent.md` — the Surrogate may read it on demand if a question
  cannot be resolved from the compressed version
- Full contents of all other child drafts (for understanding what is NOT this child's scope)
- The epic issue body and comments
- The child issue number and GitHub URL

**Surrogate agent instructions:**

You are the product owner for this epic, acting as a surrogate. Your knowledge base is
`intent-compressed.md` (primary) and the child draft. `intent.md` is available on-disk if
you need to check a detail the compressed version omitted. You have no opinions beyond
what those documents state — you do not guess or invent intent.

Your job: run `/refine-issue <child-number>` and act as the human respondent throughout
its Intent agent dialogue. When the Intent agent asks you questions, answer from
`intent-compressed.md` first, citing the relevant section (e.g., "Per Decision Priors: ...").
Consult `intent.md` only if the compressed version is insufficient.

If a question cannot be answered from either document or the child draft, respond:
`[ESCALATE] <question> — not resolved by the intent document.`
Log all escalations. Do not block on them — let `/refine-issue` continue and note the
open question in the intent summary's Open Questions section.

All other `/refine-issue` behavior is unchanged: complete the Intent agent dialogue,
confirm the intent summary, and let the Spec agent run its full codebase research and
produce the refined spec. The spec will be posted to the child's GitHub issue by
`/refine-issue` as normal.

After the Surrogate completes, collect any escalations and report them.

---

After all children complete, surface escalations to the user:

```
Surrogate refinement complete:
  Child 1: #<n> <title> — spec posted <url>
  Child 2: #<n> <title> — spec posted <url>
  ...

Escalations requiring human input:
  Child 1 (#<n>): <question>   ← or "None"
```

If there are escalations, wait for the user to answer, then update the relevant child's
spec comment on GitHub with the resolved intent.

Then proceed immediately to Step 6.

---

## Step 6 — Post Decomposition Summary

Post a summary comment on the GitHub epic issue:

```bash
gh issue comment <number> --repo <REPO> --body "$(cat <<'EOF'
## refine-epic: decomposition complete

Child issues and refined specs:
  Child 1: #<n> <title> — <url>
    Spec: <one-line behavioral intent>
  Child 2: #<n> <title> — <url>
    Spec: <one-line behavioral intent>
  ...

Dependency order: <list>
Integration seams: <N>
Open escalations: <N> (review before /resolve-issue)

Ready for /resolve-issue per child, in dependency order.
EOF
)"
```

Then tell the user in-chat:
```
Done. Decomposition posted to <epic issue url>.
Next step: /resolve-issue <child-number> for each child, in dependency order.
```

Stop.

---

## Process Gates

**Gate 1 — Unknowns Gate** (blocks all child issue drafting)
Condition: Any P0 unknown in the Open Questions table is OPEN.
Action: Set epic status to `UNKNOWNS_BLOCKED`. Output the index doc with the unknowns table
populated. Stop. Do not write any child draft files. Prompt the user to resolve P0 unknowns
and re-run.

**Gate 2 — Behavioral Question Gate** (blocks individual child drafting)
Condition: The Decomposer cannot produce a one-sentence Behavioral Question for a child from
available context.
Action: Add the child row to the decomposition table with Behavioral Question =
`NEEDS HUMAN INPUT` and Effort = `?`. Do not create a draft file for that child. Continue
drafting other children where the question is answerable.

**Gate 3 — Sign-Off Gate** (advisory — blocks handoff to `/resolve-issue`)
Condition: Any required role in the Sign-Off table is PENDING.
Action: Epic index status must read `DRAFT` or `UNKNOWNS_BLOCKED`, never `READY_TO_EXECUTE`.
State explicitly in output: *"This epic is not cleared for implementation. Obtain sign-off
from: <list>."* The Decomposer cannot enforce this mechanically beyond stating it.

---

## Constraints

- Never write or modify source files.
- Never open branches, commits, or PRs.
- Child issues are created automatically after decomposition. Do not hold issue creation
  waiting for user input unless a P0 unknown blocks it (Gate 1).
- Rough effort uses T-shirt sizing only (XS/S/M/L/XL). No story points, no hours. Precision
  is false at epic definition time.
- Never invent a DRI or team assignment. Use `TBD` and flag it as requiring human input before
  the Sign-Off Gate clears.
- If the codebase cannot be scanned (no git root, access denied, too large), mark all surface
  area rows as `UNVERIFIED` and state scan coverage explicitly.
- The output is a recommendation, not a binding contract. The user should review the
  decomposition before any child issue is handed to `/resolve-issue`.
- If blocked or uncertain about the repo structure, stop and report rather than guessing.
