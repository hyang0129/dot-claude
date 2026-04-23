# Refine Constitution — Skill Plan

## File layout

Mirrors the `refine-epic` convention:

```
commands/
  refine-constitution.md            # entry point: state detection + routing
  refine-constitution/
    setup-prompt.md                 # subskill: no constitution → first draft
    refinement-prompt.md            # subskill: draft → more complete draft
    amendment-prompt.md             # subskill: complete → complete' (may regress)
    research-prompt.md              # shared: research subagent brief
    challenger-prompts.md           # shared: adversarial subagent brief(s)
    constitution-template.md        # shared: output schema + gap-marker grammar
```

Shared files live alongside the three mode subskills because all three modes invoke research and challenger subagents and all three emit the same output format.

---

## Entry point — `refine-constitution.md`

**Args**: optional path to the constitution file. Default: `CONSTITUTION.md` at repo root.

**Behavior**:

1. **Load existing file** if present; otherwise mark as absent.
2. **State detection** (mechanical, not judgment):
   - Absent or empty → **setup**.
   - Contains any `[NEEDS …]`, `[DRAFT]`, `[DEFERRED …]`, or `[MISSING]` markers → **refinement**.
   - Has thesis + 3–10 laws each with all five elements (Stance, Why, Rejected Alternative, Anti-pattern, Scope) + rejected-alternatives section, no markers → **complete**. Route to **amendment**.
   - Ambiguous (e.g. some laws look complete, others clearly aren't, no explicit markers) → **refinement** with a normalization pass that injects markers for incomplete sections before starting.
3. **Announce the mode** to the user in one sentence ("Detected a draft with 2 laws missing Whys — entering refinement mode"). Let the user override if they want amendment on a draft, or setup on an existing file they want to scrap.
4. **Dispatch** to the matching subskill by reading its prompt file and following it.

The entry point itself contains no interview logic — it's thin routing plus mode announcement.

---

## Subskill 1 — `setup-prompt.md` (no constitution)

Full first-pass flow. Phases match the constitution guide's Steps 0–7.

1. **Thesis extraction** (3–5 turns of conversation). Goal: one paragraph, positioning claim, distinguishes what's load-bearing from what's instrumental. Push back on descriptions. Do not proceed until the user produces a sentence of the form "X is the product; Y is the delivery surface" or equivalent.
2. **Research spawn** (after thesis is clear). Invoke the research subagent (see shared section) with the thesis as context. Run sequentially, wait for results.
3. **Debate elicitation** (briefed by research). "What did you almost build but rejected?" The research results let the skill ask targeted follow-ups: "[Competitor X] does Y — did you evaluate that?" Collect a list of settled debates before drafting any law.
4. **Opposite-stance test** on each debate. Discard debates where no real project takes the opposite stance (those become `CLAUDE.md` candidates, surfaced at end).
5. **Challenger pass**. Invoke the challenger subagent(s) (see shared section). The user rebuts; concessions revise the debate list.
6. **Law drafting**. For each surviving debate, walk the Anatomy: Stance → Why (failure-in-the-world) → Rejected Alternative → Anti-pattern → Scope. Apply bluffing detection on each Why. Admit as `[DRAFT]` with markers for missing elements; defer laws whose Why the user can't produce.
7. **Corollaries** after all laws are drafted.
8. **Precedence ordering + review heuristic**.
9. **Emit** `CONSTITUTION.md` using `constitution-template.md`. Emit `CONSTITUTION.research.md` (cached research findings). Print a summary: laws admitted, laws deferred, `CLAUDE.md` candidates.

The setup subskill is the longest-running one. It's expected to span one working session.

---

## Subskill 2 — `refinement-prompt.md` (draft → better draft)

Resumes from markers. Does not re-interview sections the user already accepted.

1. **Load existing constitution and research cache.** Enumerate all markers: `[NEEDS WHY]`, `[NEEDS ANTI-PATTERN]`, `[DRAFT]` laws, `[DEFERRED …]` laws, missing sections (no rejected-alternatives block, no review heuristic, etc.).
2. **Present the gap list** to the user. Let them pick which to tackle this session (or "all"). Deferred laws are skipped by default unless the user signals new evidence ("there was an incident on X — let's try law 4 again").
3. **Refresh research if needed.** Triggers: thesis has changed since last run, a new debate surfaced that prior research didn't cover, research file is older than N days, or the user says so. Otherwise reuse the cache.
4. **Per-gap walk**, using the same Anatomy + bluffing detection as setup but scoped to the specific gap. A `[NEEDS WHY]` gap runs only the Why elicitation and its challenge; an `[UNCHALLENGED DEBATE]` gap runs the challenger subagent for that one law.
5. **Post-refinement check**: did any session changes add a new law? If yes, enforce the cap — if adding this law would exceed 10, force the demote-or-retire conversation before closing.
6. **Emit** updated `CONSTITUTION.md`. If all markers cleared and the constitution now passes the completeness check, announce "constitution is now complete — next run will default to amendment mode." Otherwise announce remaining gaps.

Refinement is short. Most sessions will touch 1–3 gaps.

---

## Subskill 3 — `amendment-prompt.md` (complete → amended)

Starts from the assumption that the user wants to *change* something, not fill a gap.

1. **Ask what the user wants to do.** Constrained menu:
   - Add a law (new debate surfaced)
   - Sharpen a Why (incident revealed a better failure mode)
   - Retire a law (no longer load-bearing)
   - Demote a law to convention/`CLAUDE.md`
   - Add to rejected-alternatives section
   - Reorder precedence
   - Amend the thesis (rare, heavy — triggers a review of every law for still-applicable)
2. **Dispatch** to the matching subpath:
   - **Add a law** → run just the debate → research-refresh → challenger → law-drafting flow for that one debate. **Regression rule**: if drafting admits the law with any marker, the constitution moves back to draft state for the next run. This is the regression path.
   - **Sharpen Why** → run Why elicitation + bluffing detection against the user's new evidence. Replace Why, keep law as complete if the new Why is concrete.
   - **Retire** → confirm with user, remove law, renumber. Add a one-line entry to rejected-alternatives section with the retirement reason.
   - **Demote** → move to a "promoted to `CLAUDE.md`" list at the bottom of the constitution (so future readers see the history). Do not silently delete.
   - **Thesis amendment** → heavy path. Re-run opposite-stance test on every existing law. Laws that no longer pass become markers; constitution regresses to draft.
3. **Cap enforcement**. Adding a law while at the cap forces the demote-or-retire conversation first.
4. **Emit** updated constitution.

---

## Shared — research subagent (`research-prompt.md`)

Invoked by setup and by refinement/amendment when the research cache is stale or when a new debate needs backing.

**Input**: thesis, list of debates/design choices already elicited, any specific query from the caller.

**Task**: web search for (a) the most-adopted alternatives in this problem space, (b) projects that have published ADRs or architecture posts on the same design choices, (c) concrete opposite-stance examples for each debate.

**Output**: per-debate entries with: alternative project name, its stance, a sourced one-paragraph Why (with link), whether the opposite stance is defensible. Plus a general "design space" overview.

**Cached** to `CONSTITUTION.research.md`.

---

## Shared — challenger subagents (`challenger-prompts.md`)

Adapted from the refine-epic challenger pattern but aimed at constitution laws, not epic intent. Three angles:

1. **Necessity challenger**: "Is this invariant load-bearing, or a convention in disguise?" Applies the opposite-stance test using research findings. Receives the debate + research only, not the user's Why.
2. **Scope challenger**: "Does this law overreach or underreach?" Argues the law should be narrower (a carve-out applies) or wider (the stated scope misses cases that share the same failure mode).
3. **Rejected-alternative challenger**: "Is the alternative you rejected actually the strongest one?" Uses research to propose a different alternative as the real opposite stance, forcing the user to defend against the stronger version.

Run sequentially or in parallel depending on session. The user rebuts in writing; concessions feed back into the drafting phase.

---

## Shared — output template (`constitution-template.md`)

Defines:

- Required sections: Thesis, Laws (numbered, ordered by precedence), Rejected Alternatives, Corollaries, Review Heuristic, Demoted-to-Convention log (amendment artifact).
- Per-law schema: Stance, Why, Rejected Alternative, Anti-pattern, Scope (optional), Detector (optional).
- **Marker grammar** (load-bearing for the refinement subskill's resume logic):
  - `[DRAFT]` — law is admitted but at least one element is a marker
  - `[NEEDS WHY]`, `[NEEDS REJECTED-ALT]`, `[NEEDS ANTI-PATTERN]` — specific element missing
  - `[DEFERRED — <reason>]` — law was deferred; not revisited until user brings evidence
  - `[UNCHALLENGED]` — law drafted but not yet run through challenger subagents
- **Completeness rule**: constitution is "complete" iff zero markers + thesis + ≥3 laws + rejected-alternatives section + review heuristic.

---

## Regression path (explicit)

Complete → draft transitions happen in exactly two places, both in the amendment subskill:
1. Adding a new law that lands with any marker.
2. Amending the thesis, which re-runs the opposite-stance test on every law and may inject markers.

The entry point detects this on the next run (markers present → refinement mode) and the cycle continues. No separate "regressed" state is needed — the existing marker-based detection handles it.

---

## Build order

1. `constitution-template.md` (everything else depends on the marker grammar).
2. `refine-constitution.md` entry point with state detection stub.
3. `setup-prompt.md` (the hardest; getting this right validates the whole flow).
4. `research-prompt.md` + `challenger-prompts.md` (needed by setup).
5. `refinement-prompt.md` (straightforward once setup works — it's a subset).
6. `amendment-prompt.md` (smallest flows, but depends on everything else being solid).
