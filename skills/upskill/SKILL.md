---
name: upskill
description: "Search the upskill skill registry for a pre-built recipe matching the task, then follow it"
trigger: /upskill
---

# /upskill

Search the [upskill registry](https://github.com/Autoloops/upskill) for a community-vetted skill that matches the described task, then follow its instructions instead of improvising.

## Usage

```
/upskill <task description>       # find best skill for this task and apply it
/upskill find <task description>  # search only, don't apply yet
/upskill inspect <skill_id>       # inspect a specific skill by ID
```

## What You Must Do When Invoked

### Step 1 — Parse the invocation

- If the user passed a task description (e.g. `/upskill set up a Next.js monorepo`), use that as the query.
- If invoked bare (`/upskill`), infer the task from the most recent user message in the conversation.
- If the subcommand is `find`, search and report results but stop before applying.
- If the subcommand is `inspect <id>`, run `upskill inspect <id>` and display the skill content.

### Step 2 — Search the registry

Run:
```bash
upskill find "<detailed task description — 5-8+ words for best results>"
```

Read the results. Prioritize skills where:
- `name_match > 0` (query words appear in the skill name)
- `text_score > 0.8` AND `vec > 0.4` (keyword + semantic alignment)
- `score > 1.4` (strong combined ranking)

Avoid skills marked `weak_description` unless no alternatives exist.

If no results are returned or all scores are weak, tell the user: "No strong skill match found for this task — proceeding without a registry recipe."

### Step 3 — Inspect the top result

Take the top-ranked skill ID and run:
```bash
upskill inspect <skill_id> --md
```

Read the returned SKILL.md instructions carefully.

### Step 4 — Confirm before applying (optional)

If the skill's scope looks significantly different from what the user asked, briefly surface the skill name and a one-line description and ask: "Found **<skill name>** — does this look right?" Otherwise proceed directly.

### Step 5 — Follow the skill

Execute the skill's instructions exactly as written. Treat them as a recipe to follow rather than suggestions to adapt.

### Step 6 — Report outcome (opt-in)

If the skill was applied and you can assess the outcome, run:
```bash
upskill report <skill_version_id> --outcome success|failure|partial --task <kind>
```

Only run this if reporting was enabled during `upskill install`. If unsure, skip it.

## Notes

- This skill is intentionally **not** wired into CLAUDE.md. It only runs when you explicitly call `/upskill`. The registry is not consulted automatically for every task.
- To configure upskill (telemetry, context sharing, submissions), run `upskill config show` in a terminal.
