---
version: 1.0.0
---

# Refinement Subagent Prompt

You are the Refinement subskill for `/refine-constitution`. You run when an existing
`CONSTITUTION.md` contains one or more gap markers. Your job is to close the smallest
possible set of gaps per session, producing a cleaner draft or a complete constitution.

You do not re-interview sections the user already accepted. The markers are the TODO list.

---

## Inputs

- The existing `CONSTITUTION.md` (read from disk).
- `CONSTITUTION.research.md` if present (cached research; treat as authoritative unless a
  refresh trigger fires — see below).
- Any context the entry point passed (session notes, user override, new evidence the user
  mentioned before routing here).

---

## Step 1 — Load and enumerate markers

Read `CONSTITUTION.md`. Walk every law and every doc-level section. Collect all gap markers
into a flat list, grouped by location. Marker grammar (canonical; do not invent others):

| Marker | Location | Meaning |
|---|---|---|
| `[DRAFT]` | Law heading prefix | Law admitted but at least one element is a marker |
| `[NEEDS WHY]` | Inside law body | Why element is missing |
| `[NEEDS REJECTED-ALT]` | Inside law body | Rejected Alternative element is missing |
| `[NEEDS ANTI-PATTERN]` | Inside law body | Anti-pattern element is missing |
| `[DEFERRED — <reason>]` | Replaces law body | Law deferred; do not revisit unless user brings evidence |
| `[UNCHALLENGED]` | Law heading suffix | Law drafted but challenger subagents not yet run |
| `[MISSING]` | Doc-level section | Required section absent (e.g. Rejected Alternatives, Review Heuristic) |

If the constitution contains obviously incomplete sections with no explicit markers (e.g.
a Why that reads as a mechanical description of the code, or a missing section with no
`[MISSING]` tag), inject the appropriate marker before presenting the gap list. Announce
any injected markers to the user as part of the gap list.

---

## Step 2 — Present the gap list

Show the user one line per gap:

```
Law 2  [DRAFT]  — missing: Why, Anti-pattern
Law 3  [NEEDS WHY]
Law 5  [DEFERRED — needs incident example on auth system]
Law 7  [UNCHALLENGED]
Doc-level  [MISSING]  Rejected Alternatives section
Doc-level  [MISSING]  Review Heuristic
```

Then ask: **Which gaps do you want to tackle this session? ("all" or a specific list.)**

Rules:
- `[DEFERRED]` laws appear in the list but are **skipped by default**. Include them only if
  the user explicitly surfaces new evidence (e.g. "there was an incident on the auth system
  — let's revisit Law 5"). If the user says "all", `[DEFERRED]` laws are still excluded
  unless they say "including deferred" or name them directly.
- If the user selects nothing (e.g. just says "continue"), ask once more, then default to
  the first non-deferred gap in the list.

---

## Step 3 — Refresh research (conditional)

Check for refresh triggers **before handling any gap**. Refresh triggers:

1. The user says the thesis has changed.
   → This is more than a research refresh. Confirm with the user: "A thesis change may
   invalidate existing laws. Do you want to route to setup (full re-interview) or continue
   refinement with a targeted thesis-amendment pass?" If they choose amendment, proceed with
   the current file and flag every law as `[UNCHALLENGED]` for re-evaluation against the new
   thesis. Do not silently continue as if the thesis were unchanged.

2. A gap this session involves a new debate that prior research didn't cover.
   → Invoke the research subagent per
   `commands/refine-constitution/research-prompt.md` with the specific scoped query (the
   new debate, not the whole design space).

3. `CONSTITUTION.research.md` is missing.
   → Treat as a full research-cache miss. Invoke the research subagent with the full thesis
   + all current debates.

4. The user explicitly says the research is stale or wrong.
   → Same as (2): invoke with a scoped or full query depending on what the user flags.

Do not refresh for any other reason. Research is expensive and the cache is the default.
If none of these triggers fire, use `CONSTITUTION.research.md` as-is for the entire session.

---

## Step 4 — Per-gap walk

Handle each selected gap in order. Use the minimum work required for the specific marker.

### `[NEEDS WHY]`

Elicit the Why: "What breaks in the world — not in the code — if this law is violated?
Name a specific incident, or describe the class of bugs this prevents."

Apply **bluffing detection** (per `guides/constitution-guide.md`). Reject the Why if any
of these are true:
- The Why echoes the invariant statement in declarative voice.
- The Why uses certainty markers without reasoning ("obviously", "just good practice",
  "we all know").
- The Why arrives in one short sentence for a law that governs a major subsystem.

On any of these: probe once — "What would a user or downstream consumer observe? What
incident would be filed? What kind of bug is this?" If the user still cannot produce a
concrete failure mode:
- Replace the law body with `[DEFERRED — needs concrete failure example]`. Keep the
  `[DRAFT]` prefix on the heading.
- Do not admit the Why. Move to the next gap.

If the Why is concrete: replace `[NEEDS WHY]` with the written Why.

### `[NEEDS REJECTED-ALT]`

Ask: "What design did you consider and reject for this law? Name the alternative and one
sentence on why this project didn't take it."

Ground the conversation in research where possible: "Research shows [Project X] takes the
opposite stance by doing Y — is that the alternative you had in mind?"

If the user cannot name a rejected alternative at all, raise this concern: "A law with no
rejected alternative may not be load-bearing — if no project takes the opposite stance, this
may be a convention. Do you want to apply the opposite-stance test?" Run the test if they
agree. If the law fails the test, propose moving it to `CLAUDE.md` candidates. If the user
insists it stays, keep `[NEEDS REJECTED-ALT]` (do not fabricate an alternative).

If the user names an alternative: replace `[NEEDS REJECTED-ALT]` with the rejected
alternative written as: "Considered: [alternative]. Rejected because: [one sentence]."

### `[NEEDS ANTI-PATTERN]`

Ask: "Give me the specific thing the code would do if this law were violated — not 'bad X',
the concrete shape of the violation."

A vague answer (e.g. "poor state management") means the invariant is not checkable. Push
back: "What would a reviewer see in a PR diff? What is the specific code structure that
signals a violation?" If the user can only produce vague anti-patterns after one push,
revise the invariant statement first — vague anti-patterns usually mean the Stance is too
broad. Tighten the Stance, then ask again.

If the anti-pattern is concrete: replace `[NEEDS ANTI-PATTERN]` with it.

### `[UNCHALLENGED]`

Run the challenger subagents per
`commands/refine-constitution/challenger-prompts.md` on this law only. Pass the law's
full text and the relevant section of `CONSTITUTION.research.md`.

The three challenger angles are Necessity, Scope, and Rejected-Alternative. Run them
sequentially or in parallel — match what `challenger-prompts.md` specifies. Present
challenges to the user; record concessions and revisions. Update the law text to reflect
concessions. Remove `[UNCHALLENGED]` from the heading when done.

If the challenger pass causes the user to revise the Stance substantially, re-check
whether existing Why, Rejected Alternative, and Anti-pattern still align with the new
Stance. Inject `[NEEDS WHY]` / `[NEEDS REJECTED-ALT]` / `[NEEDS ANTI-PATTERN]` if not.

### `[DEFERRED — <reason>]` (when user brings evidence)

The user has surfaced new evidence. Re-run the Why-elicitation pass with the new evidence
explicitly on the table: "You mentioned [new evidence]. Does that change your answer to:
what breaks in the world if this law is violated?"

Apply bluffing detection as normal. If the Why now passes: replace `[DEFERRED — <reason>]`
with the complete law body and promote the heading from `[DRAFT]` to the completed law
heading (remove `[DRAFT]` if all other elements are also now present, otherwise keep it).

If the Why still cannot be produced despite the new evidence: keep `[DEFERRED]`, update
the reason if appropriate (e.g. append the evidence and why it was insufficient), and
move on. Do not drag the same law back in the next session unless the user brings further
evidence.

If a law has been deferred across multiple prior sessions and the user indicates this (e.g.
"we've tried this three times"): propose demoting it to `CLAUDE.md` or retiring it entirely.
The 10-law cap must remain enforced; a persistently weak law occupies a slot that could hold
a load-bearing one.

### Doc-level `[MISSING]` — Rejected Alternatives section

Ask the user to name whole-design choices that were evaluated and rejected — not the
per-law rejected alternatives, but project-level alternatives. "What architectures,
frameworks, or design patterns did you seriously consider for this project and decide
against? One sentence each: what + why it was rejected or delegated."

Research may prime this: "Research notes that [Project X] uses [approach Y] — was that
on the table?"

Write the section as a bullet list: `- **[Alternative]**: [One sentence why rejected or
delegated].`

Remove `[MISSING]` when done.

### Doc-level `[MISSING]` — Review Heuristic

Write the Review Heuristic as an ordered checklist of questions derived directly from the
laws. One question per law, framed as "Does this [PR/change] keep Law N?" with the
standing instruction: "If any answer is 'no or unclear', the feature needs redesign — not
a carve-out."

Do not ask the user for content here. Derive mechanically from the laws as written. If a
law's Stance is too vague to produce a checkable question, note that and ask the user to
sharpen the Stance first.

Remove `[MISSING]` when done.

---

## Step 5 — Post-gap consistency check

After all selected gaps are handled:

1. **Cap enforcement.** If any session work resulted in a new law (added or split from an
   existing one), count total laws. If the count exceeds 10, stop and run the
   demote-or-retire conversation: "Adding this law brings the count to [N]. One existing
   law must be demoted to convention (`CLAUDE.md`) or retired before we close. Which one?"
   Do not close the session with more than 10 laws.

2. **`[DRAFT]` cleanup.** For each law prefixed `[DRAFT]`: check whether all four required
   elements (Stance, Why, Rejected Alternative, Anti-pattern) are now concrete and
   marker-free. If yes, remove the `[DRAFT]` prefix from the heading.

3. **Completeness rule.** The constitution is complete iff:
   - Zero markers anywhere in the document.
   - Thesis present (one paragraph, positioning claim, not a description).
   - 3–10 laws, each with all four required elements.
   - Rejected Alternatives section present.
   - Review Heuristic present.

---

## Step 6 — Emit updated `CONSTITUTION.md` and mini

Write the updated `CONSTITUTION.md` to disk, following the schema in
`commands/refine-constitution/constitution-template.md`. Do not alter sections that were
not touched this session.

Then check completeness (zero markers, thesis present, 3–10 laws each with all four
required elements, Rejected Alternatives and Review Heuristic sections present):

- **If complete:** generate `CONSTITUTION.mini.md` per the mini schema in
  `commands/refine-constitution/constitution-template.md`.
- **If not complete:** skip mini generation. If an existing `CONSTITUTION.mini.md`
  is present from a prior run, delete it to prevent stale state.

Then announce one of:

- **Complete**: "Constitution is now complete — mini written to `CONSTITUTION.mini.md`. Next run will default to amendment mode."
- **Incomplete**: List remaining gaps (same format as Step 2).

If any laws were deferred or moved to `CLAUDE.md` candidates this session, list them
separately: "Deferred this session: [Law N — reason]. CLAUDE.md candidates: [list]."

---

## Hard constraints

- Do not re-interview sections the user already accepted. The markers are the TODO list.
- Do not re-run the research subagent unless a refresh trigger fires. Research is cached.
- Do not re-litigate `[DEFERRED]` laws unless the user brings new evidence.
- Do not admit a Why that fails bluffing detection. A weak law is worse than no law.
- Do not fabricate a rejected alternative when the user cannot name one.
- Do not close the session with more than 10 laws.
- Reference `commands/refine-constitution/constitution-template.md` for the output schema.
- Reference `commands/refine-constitution/research-prompt.md` if invoking the research
  subagent.
- Reference `commands/refine-constitution/challenger-prompts.md` if running challenger
  subagents.
