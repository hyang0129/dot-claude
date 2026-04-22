---
version: 1.0.0
---

# Refine Epic — Org Mode Overlay

This document describes the **deltas** applied to `/refine-epic` when the `--org` flag is passed.
The main skill in [refine-epic.md](refine-epic.md) is written for solo mode (single-author
ownership). When `--org` is set, read this file at the start of the session and apply its
overrides throughout.

If `--org` is NOT passed, ignore this file entirely.

---

## Why org mode exists

Solo mode assumes one author owns all affected surfaces. Org mode adds protocol for work that
crosses adjacent-team boundaries: stakeholder mapping, borrowed-invariant confirmation,
sign-off gates. These produce throughput cost (extra rounds, mandatory confirmation pauses)
that would be noise for a solo author but are load-bearing when multiple teams depend on
the outcome.

---

## Sub-phase 1 — scan additions

In addition to the solo-mode scan targets, perform:

**Scan target 4 extension — CODEOWNERS lookup.** Read `CODEOWNERS` (at `$GIT_ROOT` or
`.github/CODEOWNERS`). For every module the epic will modify, identify the owning team.
Extend the coupling summary to: `<module> → owner → N external consumers`. This owner column
drives the stakeholder matrix and Sub-phase 6.

**Scan target 5 extension — internally-owned borrowed invariants.** In solo mode, only
externally-owned invariants count. In org mode, internally-owned invariants held by OTHER
teams also count — record them with owning team. The author cannot self-confirm these.

Working artifact: **stakeholder matrix** (teams + surfaces owned) instead of solo mode's
plain coupling summary. All borrowed invariants list their owners.

---

## Sub-phase 2 — tier thresholds

Override solo thresholds with:

- **Lite** — touches ≤1 module, **no adjacent team owns affected code**, <1 week, ≤2 children.
- **Standard** — 2–3 modules, **1–2 adjacent teams affected**, 1–4 weeks, 3–6 children.
- **Heavy** — >3 modules, **OR >2 adjacent teams affected**, OR >4 weeks, OR >6 children,
  OR Sub-phase 1 found a rejection signal against a library currently in production.

Heavy tier in org mode additionally requires mandatory stakeholder confirmation before
decomposition (Sub-phase 6, below).

---

## Sub-phase 3 — required questions (Standard + Heavy)

All of the following apply (solo mode drops most of these):

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

**Lite tier (org):** premortem, Q-kill, Q-success, Q-stakeholders (if external consumers
exist in scan), Q-portfolio. Skip the rest.

---

## Sub-phase 6 — Stakeholder Confirmation Gate (Heavy tier only)

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

## Intent document — Section 4 (Stakeholder Intent & Borrowed Invariants)

In solo mode this section is minimal. In org mode, populate fully:
- Stakeholder matrix from Sub-phase 1
- Author's Q-stakeholders answers
- Each borrowed invariant with owner, disposition, blast-radius-if-violated

---

## Index document — Sign-Off Gate

Append to the index template:

```markdown
## Sign-Off Gate

| Role | Name | Status | Date |
|------|------|--------|------|
| Engineering DRI | | PENDING | |
| Affected Team Lead(s) | | PENDING | |

**Gate rule:** Epic must reach APPROVED from all required roles before any child issue is
handed to `/resolve-issue`. Partial sign-off does not unblock execution. ROOT cannot enforce
this mechanically — it states it explicitly and sets status accordingly.
```

### Additional process gate

**Gate 3 — Sign-Off Gate** (advisory — blocks handoff to `/resolve-issue`)
Condition: Any required role in the Sign-Off table is PENDING.
Action: Epic index status must read `DRAFT` or `UNKNOWNS_BLOCKED`, never `READY_TO_EXECUTE`.
State explicitly in output: *"This epic is not cleared for implementation. Obtain sign-off
from: <list>."*
