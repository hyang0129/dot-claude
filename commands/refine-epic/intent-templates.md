---
version: 1.0.0
---

# Intent Document Templates

Schemas for the intent artifacts ROOT writes. Load this file only when writing the
artifacts — it is not needed in the interactive Q&A phase.

---

## Lite tier — `intent.md` (Kill-Criterion Card)

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

This card **is** the compressed form. No compression step runs for Lite tier — the
Kill-Criterion Card itself is passed to downstream agents.

---

## Standard + Heavy tier — `intent.md`

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
<Solo mode: short — external borrowed invariants (third-party APIs, vendor contracts) only,
with blast-radius-if-violated.
Org mode: stakeholder matrix from Sub-phase 1, plus Q-stakeholders answers; each borrowed
invariant lists owner, disposition (Confirmed / Tagged / Assumed-unverified), blast radius.
See refine-epic-org.md for org-mode details.>

## 5. Architectural Commitment & Reversibility
<From Q-commitment (org mode) or inferred from Decision Priors (solo mode). Distinguish
code-reversible (rename, refactor) from architecture-reversible (schema, protocol, identity,
storage engine, vendor contract). Name the irreversible commitments concretely — "adds
column X to table Y", not "database change".>

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
non-goals. Conditional rejections state the revisit condition. Drop any rejection where
the author cannot name the strongest argument for — Sub-phase 4 already caught those.>

## 10. Challenger Rebuttal

### Challenger 1 — Necessity
<Challenger 1 output verbatim>

**Rebuttal:** <author's response>

### Challenger 2 — Timing / Priority
<Challenger 2 output verbatim>

**Rebuttal:** <author's response>

### Challenger 3 — Shape / Architecture
<Challenger 3 output verbatim>

**Rebuttal:** <author's response>

## 11. Open Questions (Author-Deferred)
<Name decision, why unresolved, flag: ESCALATE (surface to user before proceeding) or
TIMEBOX (agent may decide within 24h, document reasoning). Empty with heading if none.>

---

## Inferences From Existing Code
<From Sub-phase 1, author-ratified in Sub-phase 3. Each entry: [INFER] statement → author's
response.>
```

---

## `intent-compressed.md` schema

Compression is deterministic concatenation — no LLM paraphrase. The Publisher derives this
file by extracting the following section headings verbatim from `intent.md`:

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

For Lite tier, skip `intent-compressed.md` entirely — the Kill-Criterion Card is the
compressed form.

---

## COMPRESSED_SCHEMA (for Publisher input)

When ROOT spawns the Publisher, it passes this ordered list as `COMPRESSED_SCHEMA`:

```
["2a. Author-Feared Failure Mode", "2b. System-Level Failure Mode", "8. Invariants (Author-Owned) [ABSOLUTE only]", "3. Decision Priors [Dominant + ONE-WAY-DOOR + EXPENSIVE-TO-REVERSE only]", "4. Stakeholder Intent & Borrowed Invariants [Tagged/Assumed only]", "6. Success Metrics & Kill Criterion", "5. Architectural Commitment & Reversibility [irreversible only]", "9. Anti-Choices [top 3]"]
```

## BODY_SECTIONS (for Publisher input)

Standard + Heavy: `["2a", "2b", "3", "4", "6", "8", "9", "10"]` (Challenger Rebuttal is
deliberately surfaced on the body — disconfirming work must be visible to downstream
readers).

Lite: pass the full Kill-Criterion Card as a single section.
