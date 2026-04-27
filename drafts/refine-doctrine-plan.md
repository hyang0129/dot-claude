# `/refine-doctrine` — Implementation Plan

## Purpose recap

Constitution captures rules that survive the perfect-surface test ("would this still be a law if technology had no limits?"). Doctrine captures the **opinionated, contested rules that exist precisely because of current technology** — the layer the constitution refinement deliberately filters out.

Each doctrine entry is anchored to a constitutional law, names its tech assumption, and carries a sunset trigger that retires it when the assumption no longer holds.

---

## File layout (mirrors `refine-constitution`)

```
commands/
  refine-doctrine.md                          ← entry point + state detection
  refine-doctrine/
    doctrine-template.md                      ← schema, marker grammar, completeness rule
    setup-prompt.md                           ← first-draft interview
    refinement-prompt.md                      ← marker-driven elicitation
    amendment-prompt.md                       ← change a complete doctrine
    challenger-prompts.md                     ← contestedness pressure tests (3 challengers)
    research-prompt.md                        ← optional: probe current-tech assumptions
```

Outputs (at repo root by default):

- `DOCTRINE.md` — master document
- `DOCTRINE.mini.md` — agent injection target (auto-derived when complete)
- `DOCTRINE.research.md` — research cache (optional)

---

## Document schema (`DOCTRINE.md`)

```
# <Project Name> — Doctrine

## Preamble
<one paragraph: this is the tech-bound layer; rules here serve constitutional laws under
current technology and will retire when their assumptions stop holding>

## Standing Orders
**Order N** — <one-sentence rule>
- **Anchor:** Law M (<stance summary>) [+ Law K if multi-anchor]
- **Tech Assumption:** <observable technological condition that makes this rule necessary>
- **Sunset Trigger:** <observable condition that retires this rule>
- **Anti-pattern:** <concrete violation shape, checkable in PR review>
- **Scope:** <optional — subsystem or surface this governs>

## Retired Orders
<append-only log when sunset triggers fire or amendment retires an order>

## Promoted-to-Law Log
<append-only — when a Standing Order turns out to be eternal and gets promoted
to the constitution, leave a tombstone here with the date and forward pointer>
```

### Required elements per Standing Order

1. **Anchor** — must reference at least one existing law in `CONSTITUTION.md`. Validated mechanically in Step 2 of the entry point.
2. **Tech Assumption** — must name an *observable* condition (model context window, tool latency, multi-surface availability, etc.). "Current LLMs are not smart enough" fails; "agents have ~200K effective context" passes.
3. **Sunset Trigger** — must be falsifiable. "When tech improves" fails; "when single-surface autonomy reliably exceeds 4-hour tasks without orchestration" passes.
4. **Anti-pattern** — concrete violation shape. Same standard as the constitution.

### Optional

- **Scope** — limits which surfaces the order applies to (e.g., `claude-code` only).
- **Detector** — grep / file-glob hint, same as constitution.

---

## The inversion: contested-under-current-tech filter

The constitution's filter: *"would this still be a law if technology were perfect?"*
Doctrine's filter is the inverse: *"given current technology, is there a credible counter-rule another competent team would adopt?"*

Setup and refinement prompts must embed this filter at every drafting step. If the answer is **no — every reasonable team would do this** → it is a default, not doctrine. Drop it. (Defaults belong in `CLAUDE.md` as conventions, not in `DOCTRINE.md` as rules.)

The challenger pass uses the inverted question explicitly. A Standing Order that no one would credibly counter is not contested, and gets demoted to convention.

---

## Marker grammar (mirrors constitution)

Element-level:
- `[NEEDS ANCHOR]` — Anchor field empty
- `[NEEDS ASSUMPTION]` — Tech Assumption empty or non-observable
- `[NEEDS SUNSET]` — Sunset Trigger empty or unfalsifiable
- `[NEEDS ANTI-PATTERN]` — same as constitution

Order-level:
- `[DRAFT]` — at least one element marker present
- `[UNCHALLENGED]` — challenger pass not run
- `[STALE]` — sunset trigger condition appears to have fired (set by amendment mode; not by setup/refinement)

Document-level:
- `[MISSING]` — required section empty (Preamble, Standing Orders)

Same load-bearing rule as constitution: parsers match these literally.

---

## Entry point (`commands/refine-doctrine.md`)

Steps mirror `refine-constitution.md` exactly:

1. **Step 0 — Setup**: TodoWrite scaffold.
2. **Step 1 — Load**: resolve `DOCTRINE_PATH`; checkout base branch; check for `DOCTRINE.wip.md`; read file.
3. **Step 1.5 — Constitution gate + candidate ingestion** *(new, doctrine-specific)*: read `CONSTITUTION.md` from the same directory.
   - If absent or incomplete (markers present, < 3 laws, etc.): refuse to proceed. Tell the user: *"Doctrine anchors require a complete constitution. Run `/refine-constitution` first."* Exit.
   - If complete: extract the law list (numbers + stances) into memory for anchor validation later.
   - **Filtered candidate ingestion**: scan `CONSTITUTION.md` for a `## Filtered Doctrine Candidates` section. If present, load all entries into a candidate list. At the start of the setup or amendment session, surface these to the user before any new interview work: *"During constitution work, these opinions were captured as doctrine candidates — [list]. Let's start here before drafting new orders."* Each entry has four fields: original phrasing, who voiced it, constitutional anchor, observable condition, and capture date. Candidates older than 6 months get a freshness flag. This step is mandatory; skip only if the section is absent.
4. **Step 2 — State detection**: same three-mode routing (`ABSENT` → setup, markers present → refinement, structurally complete → amendment, ambiguous → refinement+normalize).
5. **Step 3 — Announce mode**.
6. **Step 4 — Dispatch**: read the matching subskill prompt and execute.

Force flags: `--force-setup`, `--force-refinement`, `--force-amendment`, `--base <branch>`.

---

## Setup subskill (first-draft interview)

Phase structure (analog of constitution setup):

1. **Anchor selection** — pick a constitutional law that has visible tech-bound implementation pressure. The interview asks: *"Which law currently forces you to make calls that wouldn't be needed if tech were perfect?"*
2. **Pressure surfacing** — for each pressured law, elicit the concrete decision class (orchestration, batching, retry strategy, etc.).
3. **Rule drafting** — author the Order. Apply the contested-under-current-tech filter inline. If the rule isn't contested, drop it and return to step 2.
4. **Tech assumption** — force the author to name the *observable* condition. Reject vague answers with `[NEEDS ASSUMPTION]`.
5. **Sunset trigger** — force a falsifiable retirement condition. Reject "when X improves" with `[NEEDS SUNSET]`.
6. **Anti-pattern** — concrete violation shape.
7. **Challenger pass** — run challenger subagents (see below) to test contestedness.
8. **Finalize** — strip markers, write `DOCTRINE.md`, derive `DOCTRINE.mini.md`.

Use `DOCTRINE.wip.md` checkpointing exactly like the constitution setup does.

---

## Refinement subskill

Marker-driven. Same loop as constitution refinement: find first marker, elicit, write, advance. Add one extra check at start: re-validate every Anchor against the current `CONSTITUTION.md` law list. If a law was renumbered or retired, mark the affected Order with `[NEEDS ANCHOR]` and surface this to the user before continuing.

---

## Amendment subskill

Menu (analog of constitution amendment, but doctrine-specific):

```
What do you want to amend?

  A  Add an Order              — new tech-bound pressure surfaced
  B  Update a Tech Assumption  — observed condition shifted
  C  Retire an Order           — sunset trigger fired (move to Retired Orders log)
  D  Promote an Order to Law   — turned out to be eternal; hand off to /refine-constitution
  E  Demote an Order to Convention — wasn't actually contested (move to CLAUDE.md)
  F  Reorder                   — precedence between Orders
  G  Amend the Preamble
```

**Subpath C (retire)** is the highest-value amendment. It's how doctrine stays from rotting into legacy:

1. For each Order, ask the user: *"Has the sunset trigger fired? (yes/no/unsure)"*
2. If yes: move the full Order block (verbatim) into Retired Orders with date + reason. Remove from active set.
3. If unsure: mark `[STALE]` and surface for review next session.

**Subpath D (promote)** crosses the constitution boundary. Run the perfect-surface test on the Order. If it passes: write a tombstone in Promoted-to-Law Log, then exit and instruct the user to run `/refine-constitution --force-amendment` and select "Add a law" (Subpath A there). Do not edit `CONSTITUTION.md` directly from doctrine.

---

## Challenger subagents (`challenger-prompts.md`)

Three challengers, each a one-shot subagent:

1. **Counter-rule challenger** — *"Propose a credible counter-rule another competent team would adopt instead of this Order, justified on the same constitutional anchor. If you cannot, the Order is not contested and should be demoted to convention."*
2. **Tech-assumption challenger** — *"Is the Tech Assumption observable and falsifiable? If a reader cannot tell whether it currently holds by checking a measurable thing, reject it."*
3. **Sunset challenger** — *"Construct the cheapest scenario where the sunset trigger fires within 18 months. If you cannot, the trigger is not load-bearing and should be sharpened."*

Each runs with full Order context but no other Orders, to keep judgments independent.

> **Note:** A fourth challenger — the **perfect-technology challenger** — belongs to `/refine-constitution`, not here. It tests *laws*, not Standing Orders: "Assume infinite compute, zero latency, perfect consistency. Does this law still hold?" A law that fails that test is a doctrine candidate, not a law. That challenger lives in `commands/refine-constitution/challenger-prompts.md` and is part of the constitution-side additions described in the Build Order below.

---

## Mini schema (`DOCTRINE.mini.md`)

Auto-generated when master is complete. Strips Why/Anchor/Sunset (those are for human authoring); keeps only what an agent needs to *check* code against an Order:

```
# <Project Name> — Doctrine (Mini)
<!-- Auto-derived from DOCTRINE.md — do not edit directly -->

## Standing Orders

### Order 1 — <rule verbatim>
**Anti-pattern:** <verbatim>
**Detector:** `<verbatim>` ← omit if absent
**Scope:** <verbatim> ← omit if absent

... (one block per Order)

---

If any proposed change violates an Order above: redesign required — not a carve-out.
Doctrine reflects current-tech decisions; if you believe an Order's assumption no longer
holds, raise it for retirement rather than working around it.
```

---

## Constitution-side prerequisite

The filtered candidate handoff requires a one-time addition to `/refine-constitution`: a `## Filtered Doctrine Candidates` section appended to `CONSTITUTION.md` whenever the setup or refinement interview filters an opinion that fails the perfect-technology test. Each entry:

```
- **Candidate:** <original phrasing verbatim>
  **Voiced by:** <name or role>
  **Anchor candidate:** Law N (<stance>)
  **Observable condition:** <what makes this currently necessary>
  **Captured:** <YYYY-MM-DD>
```

This section is not part of the constitution's completeness check — its absence does not block the constitution from being marked complete. It is an optional output artifact that doctrine ingests. Implement this addition to `refine-constitution` before building the doctrine entry point, or the Step 1.5 ingestion step will always find nothing.

---

## Build order

1. **`doctrine-template.md`** first — schema, marker grammar, completeness rule. This is the contract everything else references.
2. **Constitution-side addition** — add `## Filtered Doctrine Candidates` section output to `/refine-constitution` setup and refinement subskills.
3. **Entry point `refine-doctrine.md`** — state detection mirrors constitution closely; add the constitution-gate and candidate-ingestion step (Step 1.5).
4. **Setup subskill** — heaviest lift; the contested-filter must be embedded in every drafting prompt; ingested candidates surface at session start.
5. **Refinement subskill** — port from constitution refinement; add anchor revalidation.
6. **Challenger prompts** — three subagent briefs for doctrine; the counter-rule challenger is the load-bearing one. The perfect-technology challenger is a constitution-side addition (Step 2) and does not live here.
7. **Amendment subskill** — last; depends on a working setup + refinement loop.
8. **Research prompt** — optional, can ship later. Useful when a Tech Assumption needs grounding (e.g., "what is the current effective context window for X?").

---

## Open questions for the user before building

1. **Doctrine without constitution** — should `/refine-doctrine` ever run standalone (e.g., a project where the constitution is in someone's head)? Current plan: refuse. Confirm.
2. **Multi-surface scope** — should `Scope` accept surface tags (`claude-code`, `codex`, etc.) as a first-class concept, or stay free-text? First-class makes mini-injection per-surface possible later.
3. **Promotion handoff** — Subpath D currently exits and tells the user to invoke constitution amendment manually. Cleaner alternative: doctrine amendment directly invokes `/refine-constitution --force-amendment` as a subskill. The manual handoff is safer (one document changes per skill run) but clunkier.
4. **Retirement automation** — should the amendment menu auto-walk every Order asking about sunset, or only on explicit user request via Subpath C? Auto-walk catches rot but lengthens every amendment session.
