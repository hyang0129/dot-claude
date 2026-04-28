# Setup Subskill — First-Draft Conventions Interview

This subskill runs when no conventions file exists. It produces the first draft of `CONVENTIONS.md` by **drafting on behalf of the user and letting them pick, edit, or cut**. The tone is advisory, not adversarial. The user already went through the opinion-heavy constitution interview — this phase should feel like a competent collaborator proposing the practical defaults, not a second round of pressure-testing.

Conventions are the how-we-build-it layer. Best practices are welcome. Taste calls are welcome ("we use Flask because the user prefers Flask"). The only hard requirement is that no convention violates a constitutional law — checked once, in Phase 3.

---

## Resume logic (when STATE=WIP)

If the entry point passed `STATE=WIP`, a prior session was interrupted. Read `CONVENTIONS.wip.md` and determine `Phase completed: N` and the area in progress.

- **Phase 1** → stack & context block is saved; skip Phase 1. Resume at Phase 2 with the area list.
- **Phase 2 (area: X)** → all areas drafted up to and including X are saved in the in-progress `CONVENTIONS.md` body inside the WIP file. Resume Phase 2 starting with the next area.
- **Phase 3** → drafting is complete; resume at Phase 3 (conflict pass + emit).

When resuming, tell the user: "Resuming from Phase N. Here is what was captured so far: [brief summary of stack + areas drafted]. We continue from [next area or phase]."

Do not re-do work from completed phases.

---

## Phase 1 — Stack & context intake

**Goal:** capture enough about the project to propose sensible defaults in Phase 2.

### Step 1 — Read the repo

Inspect the project to detect stack signals. Read manifests and lockfiles, look at the directory shape, scan for framework imports. Useful files to check (skip those that don't exist):

- `package.json`, `pnpm-lock.yaml`, `yarn.lock`
- `pyproject.toml`, `requirements.txt`, `uv.lock`, `poetry.lock`, `.python-version`
- `go.mod`, `go.sum`
- `Cargo.toml`, `Cargo.lock`
- `Gemfile`, `Gemfile.lock`
- `composer.json`
- `Dockerfile`, `docker-compose.yml`
- `.github/workflows/`, `.gitlab-ci.yml`, `fly.toml`, `vercel.json`
- `README.md` (skim only — context, not authority)

Keep the read shallow. The goal is signal, not a full code audit.

### Step 2 — Surface what was detected and ask the user to confirm

Present a short summary in this form:

```
Here's what I detected from the repo:

  Language & runtime:    <e.g., Python 3.12 (from .python-version)>
  Primary framework:     <e.g., Flask 3.x (from pyproject.toml)>
  Data layer:            <e.g., PostgreSQL + SQLAlchemy 2.x>
  Deploy target:         <e.g., Fly.io (from fly.toml)>
  Other signals:         <anything notable>

A few questions to round this out:

  1. Team size? (solo / small / large)
  2. Anything you already have a strong preference on for this project?
  3. Any constraints I should know about? (e.g., must run on Windows, no
     background workers yet, must avoid a specific vendor, etc.)
```

If a signal is missing or the project is greenfield enough that detection found nothing useful, ask the user directly for the missing field.

### Step 3 — Ingest convention candidates

If `CONVENTION_CANDIDATES` is non-empty (from Step 1.5 of the entry point), present them:

```
During constitution work, you voiced these preferences as convention candidates:

  - <stance>  (voiced by <name>, <date>) [STALE if applicable]
  - <stance>  ...

I'll treat these as starting points. For each, confirm: keep / edit / drop?
```

Walk each candidate. Confirmed candidates carry into Phase 2 as pre-seeded conventions in the relevant areas.

### Step 4 — Build the area list

Based on the confirmed stack, propose the list of areas to draft. Use the canonical ordering from `commands/refine-conventions/conventions-template.md`. Skip areas that don't apply to this project — for example:

- Skip "Frontend" if there is no frontend.
- Skip "LLM / AI integration" if the project doesn't call any model.
- Skip "Background jobs / queues" if the user confirmed no async work.

Tell the user the proposed area list and ask if they want to add or remove any.

### Capture the Stack & Context block

Once Steps 1–4 are confirmed, write the final `Stack & Context` block (per the template schema) and save it. This block is what Phase 3 emits as the second section of `CONVENTIONS.md`.

### WIP checkpoint

Write `CONVENTIONS.wip.md` at the same directory as `CONVENTIONS_PATH`:

```markdown
# Conventions WIP — Setup in Progress

## Phase completed: 1

## Stack & Context
<the captured block>

## Areas to draft
- <area 1>
- <area 2>
- ...

## Convention candidates carried forward
- <area>: <candidate stance>
- ...

## Drafted so far
(empty until Phase 2 starts)
```

Tell the user: "Stack and context saved to `CONVENTIONS.wip.md` — progress is now recoverable."

Mark Phase 1 done.

---

## Phase 2 — Drafting by area

Walk the area list one area at a time. **Do not batch areas.** Each area gets its own focused exchange so the user can engage without scrolling past unrelated content.

### Per-area procedure

**Step A — Ask the user what they have in mind first.**

Before proposing anything, surface the area and ask:

```
Area: <area name>

What conventions do you already have in mind here? (libraries, patterns, file
layout, hard "must / must not" rules — anything you've already decided.) Just
list them informally; I'll formalize and fill in around them.

If you'd like me to propose without input, say "you propose" and I'll draft
a starting batch for you to react to.
```

Capture whatever the user offers verbatim — these are anchored entries that Claude must not overwrite. They become pre-seeded conventions in the area, on equal footing with confirmed convention candidates from Phase 1.

If the user says "you propose" (or similar), proceed with no anchored entries.

If the user names something Claude doesn't fully understand (e.g., a library it doesn't recognize, an unusual pattern), ask one short clarifying question rather than guessing.

**Step B — Decide whether to invoke research.**

Invoke the research subskill (`commands/refine-conventions/research-prompt.md`) when ANY of:

- You have low confidence on best practice for the user's stack in this area, AND the user did not already cover the area completely in Step A.
- The user asked "what are my options for X?" in-line for this area, or said "you propose" with no constraints.
- The stack version is recent enough that training data may be stale (>~6 months past the assistant's knowledge cutoff for fast-moving areas like JS frameworks or LLM tooling).

Skip research when:

- The user gave a complete picture for the area in Step A (just record it).
- The area is well-trodden and stable (e.g., language version pinning, lockfile use).
- A confirmed convention candidate already covers the area.

If invoking research, dispatch the research subskill with the area name, the stack context, and the user's Step A input. Wait for it to return. Cache its output to `CONVENTIONS.research.md` (append, with a heading per area).

**Step C — Propose to fill gaps around what the user already named.**

Take the user's Step A entries as fixed. Propose additional conventions only where the area still has uncovered surface — patterns, defaults, or related rules the user did not mention.

Present the batch as: `[anchored from your input]` entries first (formalized into the per-convention schema), then `[suggested]` entries. Each follows the schema from `conventions-template.md`:

```
**<rule line>**
- How: <optional concrete realization>
- Notes: <optional rationale or alternatives>
```

If research returned alternatives that compete with what the user named in Step A, surface them in the `Notes` line of the relevant anchored entry — e.g., `Notes: Considered FastAPI; Flask was your pick.` Do not propose them as competing entries.

Do not pad with conventions that are obvious or unhelpful (e.g., "use git" — skip).

If a confirmed convention candidate from Phase 1 covers part of this area, treat it as anchored input on equal footing with the user's Step A input.

If the user covered the entire area in Step A and there are no useful additions to suggest, say so plainly and move to Step D with the user's input alone — do not invent fillers.

**Step D — Let the user accept, edit, cut, or add.**

Present the batch and ask: `Accept / edit / cut / add?` for the area as a whole. Walk per-entry only if the user wants to. Capture the user's words verbatim where they edit or add.

If the user wants to defer the entire area, write `[TBD]` as the area body and move on. If the user wants to defer a single field within an entry, write `[TBD]` for that field.

**Step E — Append to in-progress `CONVENTIONS.md` and update WIP.**

After completing each area (Steps A through D done):

1. Write the current state of all drafted areas to `CONVENTIONS.md` using the schema from `conventions-template.md` — Preamble (use a placeholder one-paragraph version for now; finalize in Phase 3), Stack & Context (from Phase 1), and the Conventions section with all areas drafted so far. Areas not yet reached are omitted.
2. Update `CONVENTIONS.wip.md`: set `Phase completed: 2 (area: <name>)` and replace the `Drafted so far` block with a one-line summary per area completed.

Do not wait until all areas are drafted to write `CONVENTIONS.md` for the first time. Write it after area 1. Overwrite it after each subsequent area. This means the refinement subskill can resume from the file alone if the WIP is lost.

### Exit condition

Every area in the list has been walked. Each produced either a set of accepted conventions (with or without `[TBD]`) or was intentionally deferred as a whole-area `[TBD]`.

---

## Phase 3 — Constitution conflict pass + emit

### Step 1 — Conflict pass

Read the full set of drafted conventions and `CONSTITUTION_LAWS`. For each convention, ask: does this appear to violate any law?

Be conservative. The pass exists to catch obvious conflicts (e.g., a convention that picks a vendor whose use the constitution prohibits, a logging convention that violates a privacy law). Do not flag stylistic mismatches.

Surface any apparent conflicts to the user as a single list:

```
I see possible conflicts with the constitution:

  - Convention "<rule>" in area <X>
    Possibly conflicts with Law <N> (<stance summary>) because <one-sentence reason>.
    Keep / edit / remove?

  - ...
```

If the list is empty, tell the user: "No apparent conflicts with the constitution."

User adjudicates each item: keep (override the flag), edit (rewrite the convention), or remove (drop the convention). Apply changes.

### Step 2 — Finalize the Preamble

Write a one-paragraph Preamble per the template schema. It should:

- Name this as the how-we-build-it layer.
- Reference the constitution by name (use the `# <Project Name>` heading from `CONSTITUTION.md`).
- State that conventions are practical defaults — best practices, taste calls, and stack picks.
- State that the only hard requirement is not violating a constitutional law.

Show it to the user for confirmation. Edit on request.

### Step 3 — Emit `CONVENTIONS.md`

Write the final document to `CONVENTIONS_PATH`. Apply the canonical area ordering from `conventions-template.md` regardless of drafting order. After writing, delete `CONVENTIONS.wip.md` — the session is no longer interrupted.

### Step 4 — Emit `CONVENTIONS.mini.md` (conditional)

Check whether `CONVENTIONS.md` is complete (zero `[TBD]` markers, Preamble present, Stack & Context present, ≥1 area with ≥1 convention).

- **If complete:** generate `CONVENTIONS.mini.md` per the mini schema in `conventions-template.md`.
- **If not complete (`[TBD]` remain):** skip mini generation. Do not write or update `CONVENTIONS.mini.md`. If an existing mini file is present from a prior run, delete it to prevent stale state.

### Step 5 — Session summary

Print to the user (do not write to file):

```
Areas drafted:           <count>
Conventions admitted:    <count> (of which <tbd-count> carry [TBD])
Possible-conflict hits:  <count> — adjudicated as: <kept N / edited N / removed N>
Mini generated:          yes | no (skipped — [TBD] remain)
Next run will enter:     refinement mode ([TBD] present) | amendment mode (complete)
```

---

## Closing rules

- Do not invent a convention the user did not approve. Every entry must trace back to either a confirmed convention candidate, a research-surfaced suggestion the user accepted, or a Claude proposal the user accepted.
- Do not litigate. If the user picks a non-best-practice option, record it. The Notes line can mention the alternative once; do not push back further.
- Do not require the `Notes` or `How` field. If the rule is self-explanatory and the user did not give a reason, emit just the rule line.
- Do not skip the conflict pass. It is the only constitution-enforced gate; without it, conventions can drift away from the constitution silently.
- Do not invoke research for every area. Research is for areas where it adds signal — not as a default ritual.
