# Amendment Subskill — Edit a Complete Conventions File

This subskill runs when `CONVENTIONS.md` exists and is complete (no `[TBD]`, all required sections). The job is to apply user-requested changes — add, edit, remove — and re-emit.

Tone: advisory, terse. The user knows what they want; Claude makes it happen and runs the conflict pass on what changed.

---

## Step 1 — Capture the request

Ask the user (skip if they already stated it in the invocation message):

```
What would you like to change?

  - Add: a new convention or a whole new area.
  - Edit: change the rule, How, Notes, or Revisit when on an existing convention.
  - Remove: drop a convention or a whole area.
  - Reorganize: move a convention between areas, rename an area.
  - Update Stack & Context: stack changes (new framework, version bump, etc.).
```

Capture the request as a list of discrete changes. If the user describes them as prose, restate as a numbered list and confirm before proceeding.

---

## Step 2 — Apply each change

Walk the change list one at a time.

### Add a convention

Ask which area. If the area doesn't exist, treat as "add a whole new area" (next case).

For the new convention, ask the user for the rule line first — they initiated the change, they have the rule in mind. Optionally ask for `How`, `Notes`, or `Revisit when` — but only if the user wants them. Do not pad with empty fields.

If the user is uncertain on the rule and asks for suggestions, optionally invoke the research subskill (`commands/refine-conventions/research-prompt.md`) to surface best practices for the area. Same rules as setup Phase 2 — invoke when it adds signal, skip when the user already has a preference.

### Add a whole new area

Place per the canonical ordering from `commands/refine-conventions/conventions-template.md`. Project-specific areas not on the canonical list go at the end.

Walk the new area as a Phase 2 area in setup, running the full per-area procedure (Steps A–D): ask the user what they have in mind for the area first, then decide on research, then propose to fill gaps, then accept / edit / cut / add.

### Edit a convention

Show the current entry verbatim. Ask what changes. Apply. If only the rule line is changing in a way that meaningfully alters intent (not a typo fix), prompt the user to consider whether `Notes` should be updated to reflect the new rationale.

### Remove a convention

Show the current entry verbatim. Confirm: `Remove "<rule>" from area <X>? (yes/no)`. Apply.

If removing a convention leaves an area empty, ask: "This was the last convention in <area>. Remove the area too? (yes/no)"

### Reorganize

Moving a convention between areas: cut from source, paste to destination, preserve verbatim. Renaming an area: change the `### <Area>` heading; preserve all conventions inside.

### Update Stack & Context

Walk the field(s) the user wants to change. Update verbatim. If the change implies a downstream convention edit (e.g., "we switched from Flask to FastAPI" → the Web framework area's conventions need updating), surface the implication: "This may also affect the Web framework / API layer conventions. Want to walk them now?"

---

## Step 3 — Conflict pass on changed entries only

Run the conflict pass on every convention that was added or edited in this session — not the whole file. Removed conventions don't need a pass. Reorganized conventions don't need a pass unless the rule line changed.

Use the same procedure as setup Phase 3, Step 1.

If no conventions were added or had their rule line edited (e.g., the only change was a typo fix in a `Notes:` line, or a Stack & Context update), skip the pass.

---

## Step 4 — Re-emit

Write the updated `CONVENTIONS.md` per the schema. Apply the canonical area ordering. The file should remain complete (no new `[TBD]` introduced); regenerate `CONVENTIONS.mini.md`.

If the user introduced a `[TBD]` deliberately during edits (e.g., added a convention with a deferred `How:`), the file is no longer complete — delete the existing `CONVENTIONS.mini.md` to prevent stale state, and tell the user the next run will enter refinement mode.

---

## Step 5 — Session summary

```
Changes applied:         <count>
  Added:                 <count> conventions, <count> areas
  Edited:                <count> conventions, <count> Stack & Context fields
  Removed:               <count> conventions, <count> areas
  Reorganized:           <count> moves, <count> renames
Possible-conflict hits:  <count> — adjudicated as: <kept N / edited N / removed N>
Mini regenerated:        yes | no (deferred — [TBD] introduced)
```

---

## Closing rules

- Do not silently restructure beyond what the user asked. If a remove leaves an empty area, ask before removing the area.
- Do not run a full conflict pass over the entire file — only the changes.
- Do not promote a convention to a constitutional law from inside this skill. If the user says "this should be a law, not a convention," instruct them to run `/refine-constitution --force-amendment` separately. Removing the convention is in scope; promoting it is not.
- Do not edit `CONSTITUTION.md` from this skill, ever.
