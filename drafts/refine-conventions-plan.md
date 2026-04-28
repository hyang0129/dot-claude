# `/refine-conventions` — Implementation Plan

Replaces `/refine-doctrine`. Doctrine is retired in full; no migration needed (greenfield).

---

## Why this exists

The constitution interview already drilled hard on **why** — opinion-heavy, contested, four-challenger pass. After that, the user does not need a second opinion-extraction phase. They need an **advisory** layer that says: given your stack and your constitution, here is **how** to build it.

Conventions are the engineering and architectural guidance for immediate implementations. They live outside `CLAUDE.md` because `CLAUDE.md` cannot hold 800 lines of practice guidance without poisoning every agent's context window.

A convention can be:
- A best practice with no real alternative (use parameterized queries, pin deps with a lockfile).
- A taste call (use Flask because user prefers it and no law prohibits it).
- A pattern (route all LLM calls through `src/providers/`).
- A library/tool pick (Pytest over unittest).

**The only hard requirement:** a convention must not violate a constitutional law. That is checked once at emit time, not litigated per entry.

There is no anchor field, no contestedness filter, no sunset trigger, no challenger pass.

---

## Concept shift from doctrine

| Doctrine (retired) | Conventions (new) |
|---|---|
| User proposes, Claude challenges | Claude proposes, user approves/edits |
| Anchor to a specific law required | No anchor field |
| Contestedness filter ("credible counter-rule must exist") | No filter — best practices welcome |
| Tech Assumption field per order | None |
| Sunset Trigger field per order | None (optional "Revisit when …" if user volunteers it) |
| 3 adversarial challenger subagents | None |
| Marker grammar `[NEEDS ANCHOR]` / `[NEEDS ASSUMPTION]` / `[NEEDS SUNSET]` / `[UNCHALLENGED]` / `[STALE]` | Just `[TBD]` for blanks |
| Numbered Standing Orders | Sectional by area; conventions inside sections |
| Outputs `DOCTRINE.md` + `DOCTRINE.mini.md` | Outputs `CONVENTIONS.md` + `CONVENTIONS.mini.md` |
| Constitution gate: must be complete | Constitution gate: must be complete (kept — needed for the conflict pass) |

---

## File layout

```
commands/
  refine-conventions.md                          ← entry point + state detection + dispatch
  refine-conventions/
    conventions-template.md                      ← schema + completeness rule + mini schema
    setup-prompt.md                              ← 3-phase advisory drafting flow
    refinement-prompt.md                         ← fill [TBD] blanks; no challenger logic
    amendment-prompt.md                          ← add / edit / remove conventions
    research-prompt.md                           ← optional: tech-fact lookups (best-practice probes)
```

Outputs (at repo root by default):

- `CONVENTIONS.md` — master document, sectional, can be long.
- `CONVENTIONS.mini.md` — agent-injection cheat sheet (rules + detectors only), auto-derived when complete.
- `CONVENTIONS.research.md` — optional research cache, only if research subskill is invoked.

---

## Document schema

### Top-level structure

```
# <Project Name> — Conventions

## Preamble

## Stack & Context

## Conventions
### <Area 1>
### <Area 2>
...

## Notes & Trade-offs       ← optional, prose
```

### Per-convention shape

```markdown
### <Area>

**<Convention name / one-line rule>**
- **How:** <optional — pattern, library, file layout, command>
- **Notes:** <optional — why we picked this, alternatives considered, gotchas>
- **Revisit when:** <optional — only if the user volunteers a trigger>
```

Only the rule line is required. Everything else is optional.

### Suggested areas (Claude picks based on what the project actually needs)

- Language & runtime version
- Web framework / API layer
- Data access (ORM, migrations, pooling)
- Background jobs / queues
- Testing (framework, layout, coverage targets)
- Dependency management (lockfile, version pinning, update cadence)
- Code organization (directory layout, module boundaries)
- Error handling & exceptions
- Logging & observability
- Configuration & secrets
- Build & deploy
- Security (input validation, auth, secrets handling)
- LLM / AI integration (if applicable)
- Frontend (if applicable)

Areas are suggestions, not a checklist. Skip areas that don't apply. Add areas that do.

### Marker

Only one marker exists: `[TBD]` as a field value when the user wants to defer a section. The refinement subskill targets `[TBD]` entries. No `[DRAFT]`, no `[NEEDS X]`, no `[UNCHALLENGED]`.

---

## Setup flow (3 phases)

### Phase 1 — Stack & context intake

**Inputs:** `CONSTITUTION_LAWS` from the entry point, the repo itself, optional `CONVENTION_CANDIDATES` from the constitution session.

**Steps:**

1. Read the repo to detect stack signals: language manifests (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`), lockfiles, framework imports, infra hints (`Dockerfile`, `.github/workflows/`), existing `README.md`.
2. Surface what was detected and ask the user to confirm/correct: language, framework, deploy target, team size, anything they already have strong opinions on.
3. Surface any `CONVENTION_CANDIDATES` from the constitution session (rename of "Doctrine Candidates" — see cleanup section). These were preferences voiced during constitution work that didn't make it as laws. Treat as starting points; user confirms or drops each.
4. Capture all of the above into a `Stack & Context` block that becomes a section in `CONVENTIONS.md`.

**Exit:** confirmed stack + context block + list of areas to draft conventions for.

### Phase 2 — Drafting by area

For each area identified in Phase 1, Claude proposes conventions in a small batch (2–6 entries per area). User accepts, edits, or cuts each.

**Drafting rules:**

- Claude proposes best-practice defaults for the user's stack. No contestedness test.
- If the user already has a preference, Claude records it verbatim (e.g., "Web framework: Flask, user preference").
- Claude can suggest alternatives in a `Notes` line, but the rule is what the user picks.
- No anchor field. No tech-assumption interrogation. No sunset interrogation.
- If the user wants to defer an area, write `[TBD]` and move on.

**Pacing:** one area at a time. Do not dump all areas at once. After each area, confirm before moving to the next.

**Exit:** every identified area has at least one entry (or `[TBD]`).

### Phase 3 — Constitution conflict pass + emit

**Conflict pass (single, lightweight):**

1. Claude scans the full draft against `CONSTITUTION.md`.
2. For each convention, ask: does this appear to violate any law?
3. Surface any apparent conflicts to the user as a list. User adjudicates: keep, edit, or remove.
4. No challenger subagents. This is a single in-line review by Claude.

**Emit:**

1. Write `CONVENTIONS.md` per the schema.
2. If the document has zero `[TBD]` markers, also write `CONVENTIONS.mini.md`.
3. Print a short session summary: areas covered, entry count, `[TBD]` count, next mode (refinement if `[TBD]` present, amendment otherwise).

---

## Refinement flow

Triggered when `CONVENTIONS.md` exists and contains `[TBD]` markers.

For each `[TBD]`, Claude proposes a fill, user accepts/edits/cuts. Same advisory tone as setup. No challenger pass. When all `[TBD]` are resolved, run the constitution conflict pass and re-emit.

---

## Amendment flow

Triggered when `CONVENTIONS.md` exists and is complete (no `[TBD]`).

User states what they want to change. Claude makes the edit, runs the constitution conflict pass on changed entries only, re-emits. No challenger pass.

Add / edit / remove are all in scope. There is no "promote-to-law" path — if a convention turns out to be eternal, the user runs `/refine-constitution --force-amendment` separately.

---

## Mini schema

`CONVENTIONS.mini.md` is auto-derived. Strips Notes, Revisit-when, Stack & Context, Preamble. Keeps the per-area rule lines and any `How` field that names a concrete pattern, library, or command. Purpose: agent-injection cheat sheet.

```markdown
# <Project Name> — Conventions (Mini)
<!-- Auto-derived from CONVENTIONS.md — do not edit directly -->

## <Area 1>
- <rule>
- <rule>
  - How: <how line>

## <Area 2>
- <rule>
...

---

If a proposed change conflicts with a convention above, raise it for amendment rather than working around it.
```

Generated only when the master has zero `[TBD]` markers. If markers remain, skip mini generation and delete any stale mini file.

---

## Entry point (`commands/refine-conventions.md`)

Mirrors the structure of `refine-doctrine.md` but trimmed:

- **Args:** `[path]`, `--force-setup`, `--force-refinement`, `--force-amendment`, `--base <branch>`.
- **Step 0:** TodoWrite init.
- **Step 1:** load `CONVENTIONS.md`; check for `CONVENTIONS.wip.md` and offer resume/discard.
- **Step 1.5:** constitution gate (must exist and be complete) + ingest `## Convention Candidates` from `CONSTITUTION.md` if present.
- **Step 2:** state detection — three rules:
  - `STATE=ABSENT` → `MODE=setup`.
  - File contains `[TBD]` → `MODE=refinement`.
  - Else → `MODE=amendment`.
- **Step 3:** announce mode.
- **Step 4:** dispatch to subskill.

No marker normalization step (Rule 4 in doctrine), no `STALE` detection, no `UNCHALLENGED` tracking — none of those markers exist.

---

## WIP file

`CONVENTIONS.wip.md` is used during setup only, to checkpoint after each area in Phase 2 (so a long session can resume). Deleted on successful Phase 3 emit. Format:

```markdown
# Conventions WIP — Setup in Progress

## Phase completed: 2 (area: <area name>)

## Stack & Context
<captured block>

## Areas remaining
- <area>
- <area>

## Drafted so far
<the in-progress CONVENTIONS.md content>
```

Refinement and amendment do not need WIP files (single-pass operations).

---

## Cleanup plan

### A — Retire doctrine skill (delete)

```
commands/refine-doctrine.md
commands/refine-doctrine/amendment-prompt.md
commands/refine-doctrine/challenger-prompts.md
commands/refine-doctrine/doctrine-template.md
commands/refine-doctrine/refinement-prompt.md
commands/refine-doctrine/research-prompt.md
commands/refine-doctrine/setup-prompt.md
```

Greenfield: no `DOCTRINE.md` or `DOCTRINE.mini.md` exists in any tracked project. No migration shims, no deprecation period.

### B — Update `/refine-constitution` to hand off to conventions

Files to edit:

1. **`commands/refine-constitution/constitution-template.md`**
   - Rename section `## Filtered Doctrine Candidates` → `## Convention Candidates`.
   - Update prose at lines ~123–144 to reference conventions and `/refine-conventions` instead of doctrine and Standing Orders.
   - Drop "waiting to become a doctrine Standing Order" framing — replace with "carried forward as a starting point for `/refine-conventions`".
   - Drop the "promoted-to-Standing-Order tombstone" mechanic (no promote path in conventions).

2. **`commands/refine-constitution/challenger-prompts.md`**
   - Challenger 4 (Perfect Technology): keep the test (it still filters tech-bound rules out of the constitution). Update the recommendation language: instead of "Move to DOCTRINE.md as a Standing Order anchored to this assumption", say "Move to `## Convention Candidates` for `/refine-conventions` to consider as a stack-level guideline."
   - Update the rebuttal-handling text at lines ~233–237: write the candidate to `## Convention Candidates` (not `## Filtered Doctrine Candidates`); drop the "waits for `/refine-doctrine`" sentence and replace with "carried forward to `/refine-conventions` as a starting point."
   - Drop the **Observable Condition** field requirement on candidate entries — conventions don't need it. Keep just: stance, voiced-by, captured date.

### C — Drafts cleanup

After this plan is approved and the new skill is built:

```
drafts/refine-doctrine-plan.md           ← delete (superseded by this file)
drafts/refine-doctrine-panel-discussion.md  ← delete (input to the doctrine design, no longer relevant)
```

Optionally keep `refine-doctrine-panel-discussion.md` archived if there are insights worth preserving — read first before deleting.

### D — README / global docs

Search for references to doctrine in:

- `CLAUDE.md` (project + global)
- `README.md`
- `guides/`

Replace `/refine-doctrine` mentions with `/refine-conventions`. Replace doctrine/Standing Order vocabulary with conventions vocabulary.

---

## Order of operations (suggested commit sequence)

1. **Commit 1 — write the new skill.** Create `commands/refine-conventions.md` and `commands/refine-conventions/*`. Don't touch doctrine or constitution yet.
2. **Commit 2 — wire constitution handoff.** Edit `refine-constitution/constitution-template.md` and `refine-constitution/challenger-prompts.md` to produce `## Convention Candidates` and reference `/refine-conventions`.
3. **Commit 3 — retire doctrine.** Delete the entire `commands/refine-doctrine/` tree and `commands/refine-doctrine.md`.
4. **Commit 4 — drafts and docs cleanup.** Delete superseded drafts, update README/CLAUDE.md/guides references.

Splitting the deletions into their own commit keeps the history readable and lets the new skill be tested in isolation before doctrine vanishes.

---

## Resolved design decisions

### Research subskill — kept, reshaped

`commands/refine-conventions/research-prompt.md` is invoked during Phase 2 drafting (not Phase 1). For a given area, the research subagent returns:

- **Current best practice(s)** for the user's stack — short list with one-line rationale each.
- **Alternatives the user might not have considered** — including newer entrants, stack-specific options, or trade-off-driven picks (e.g., "consider Litestar instead of Flask if you want async-first").
- **Common gotchas** at the area level.

ROOT presents the research output to the user inside the area's drafting batch. User picks, edits, or supplies their own. The research is advisory — it does not gate the draft.

Research is invoked when:
- Claude has low confidence on best practice for the user's stack (unfamiliar combo, niche language).
- The user asks "what are my options for X?" in-line.
- A stack version is recent enough that training data may be stale.

Research is skipped when the user has already stated a clear preference for an area.

Output is cached to `CONVENTIONS.research.md` (optional file, not part of completeness check) so re-runs don't re-query.

### Mini format — bulleted under area headings

Proposed bulleted format in the Mini schema section above is final. Conventions don't always have anti-patterns; bulleted rules + optional `How:` lines stay terse and readable when injected.

### Section ordering — fixed order in template

`conventions-template.md` defines a canonical area order. Drafting can happen in any order, but emit always re-sorts to canonical order. Canonical order:

1. Language & runtime
2. Dependency management
3. Code organization
4. Web framework / API layer (if applicable)
5. Frontend (if applicable)
6. Data access
7. Background jobs / queues (if applicable)
8. LLM / AI integration (if applicable)
9. Configuration & secrets
10. Error handling & exceptions
11. Logging & observability
12. Testing
13. Build & deploy
14. Security

Areas not used in a given project are omitted entirely (no empty headings). Project-specific areas not on this list are appended at the end in the order they were drafted.
