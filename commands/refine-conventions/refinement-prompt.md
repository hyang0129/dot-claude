# Refinement Subskill — Resolve `[TBD]` Entries

This subskill runs when `CONVENTIONS.md` exists and contains `[TBD]` markers, OR when the file is structurally incomplete (missing Preamble, missing Stack & Context, or no conventions at all) without any explicit `[TBD]`. The job is to fill in what's deferred and re-emit.

Tone: same advisory tone as setup. Claude proposes, user picks. No challenger pass, no contestedness test, no anchor interrogation.

---

## Step 1 — Inventory what needs filling

Read the existing `CONVENTIONS.md`. Build a punch list of items needing resolution:

1. **Missing Preamble** — `## Preamble` heading absent or empty paragraph below it.
2. **Missing Stack & Context** — `## Stack & Context` heading absent, empty, or contains `[TBD]` for required fields.
3. **Whole-area `[TBD]`** — an `### <Area>` subsection whose body is `[TBD]`.
4. **Field-level `[TBD]`** — a convention with a `[TBD]` value in any field (`How:`, `Notes:`, `Revisit when:`, or the rule line itself if somehow deferred).
5. **Empty Conventions section** — `## Conventions` heading present but no `### <Area>` subsections under it.

Tell the user what was found:

```
Found N items needing resolution:

  - Missing Preamble
  - Stack & Context: [TBD] for <field>
  - Whole-area [TBD]: <area>, <area>
  - Field [TBD]: <area> > "<rule line>" > <field>
  - ...

I'll walk each in order. You can also tell me to skip any item — it stays [TBD].
```

---

## Step 2 — Walk each item

For each item in the punch list, run the matching procedure.

### Missing Preamble

Propose a one-paragraph Preamble per the template schema (names the how-we-build-it layer, references the constitution, states that conventions are practical defaults, states that the only hard requirement is not violating a constitutional law). Show to user; accept / edit.

### Missing or partial Stack & Context

For each missing or `[TBD]` field, ask the user directly. If a value can be inferred from the repo (manifests, lockfiles), surface the inference and ask for confirmation rather than asking blind.

### Whole-area `[TBD]`

Treat as a fresh area draft using the full setup Phase 2 per-area procedure (Steps A–D). That means: ask the user what they already have in mind for the area first, then decide whether to invoke research, then propose to fill gaps around the user's input, then accept / edit / cut / add.

### Field-level `[TBD]`

Single-field elicitation:

- `How: [TBD]` → Claude proposes a concrete realization (pattern, library, command). Show; accept / edit / cut. If the user has nothing useful to add, removing the `How:` line entirely is fine — `How` is optional.
- `Notes: [TBD]` → Claude proposes one line of rationale or an alternative considered. Same accept / edit / cut. Removing the line is fine.
- `Revisit when: [TBD]` → Claude does NOT propose. Ask the user: "Was there a specific trigger you wanted to capture, or should this line be removed?" `Revisit when` is opt-in; defaulting to remove is correct.
- Rule line `[TBD]` → ask the user what the rule should be; Claude does not invent a rule out of thin air.

### Empty Conventions section

Treat as a partial setup: build an area list (per the canonical ordering, scoped to what the project needs), confirm with the user, then walk Phase 2 of setup.

---

## Step 3 — Conflict pass on changes

After all punch-list items are resolved, run a conflict pass on every convention that was added or edited in this session (not the whole file). Use the same procedure as setup Phase 3, Step 1.

If no conventions were added or edited (e.g., the only resolution was filling the Preamble), skip the pass.

---

## Step 4 — Re-emit

Write the updated `CONVENTIONS.md` per the schema. Apply the canonical area ordering. If the file is now complete (zero `[TBD]`, all required sections), generate `CONVENTIONS.mini.md`. If markers remain (user chose to leave some `[TBD]` deferred), skip mini generation and delete any existing stale mini.

---

## Step 5 — Session summary

```
Items resolved:          <count>
Items left as [TBD]:     <count> — listed below
Conventions added/edited this session: <count>
Possible-conflict hits:  <count> — adjudicated as: <kept N / edited N / removed N>
Mini generated:          yes | no (skipped — [TBD] remain)
Next run will enter:     refinement mode ([TBD] still present) | amendment mode (complete)
```

If items were left as `[TBD]`, list them so the user can come back to them.

---

## Closing rules

- Do not invent missing values silently. Either propose-and-confirm with the user, or leave `[TBD]` in place.
- Do not run a full conflict pass over conventions that did not change in this session — they were already passed at original emit.
- Do not delete a `Revisit when:` line unless the user confirms. It may carry meaning Claude doesn't see.
