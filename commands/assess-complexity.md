---
version: 1.0.0
---

# Assess Complexity

## Purpose

Assess the tier (1/2/3) and ADR requirement for a GitHub issue. A shared utility invoked by `/fix-issue` (when no `--tier` override is present) and by `/resolve-issue` Step 0 (before spawning `/fix-issue`), so the assessment runs exactly once regardless of entry point.

## Inputs

The caller passes the full issue body (title + body + comments, already fetched). This skill does not re-fetch.

## Subagent

Spawn a single Assessment subagent (`model: "claude-sonnet-4-6"`) with the issue body.

### Assessment subagent instructions

Read the issue title, body, and comments in full. Assess the complexity tier and ADR requirement.

**Tier signals:**

- **Tier 1 (simple):**
  - Touches one module or area
  - Bug fix, small feature, config or docs change
  - Requirements fully described in the issue
  - Estimated diff < ~200 lines

- **Tier 2 (medium):**
  - Touches 2–4 loosely coupled areas or layers (e.g. frontend + backend, API + tests)
  - Requirements clear but spans multiple files/domains
  - Estimated diff 200–800 lines
  - May still warrant an Architect if open questions exist

- **Tier 3 (complex):**
  - Spans multiple subsystems or teams
  - Issue contains open questions, "TBD", or phrases like "we need to decide"
  - Requires changes to shared interfaces, data models, or config
  - Estimated diff > 800 lines, or significant unknowns

**ADR_REQUIRED rules:**

Set `ADR_REQUIRED=true` when any of:
- `TIER=3` → `ADR_REASON=TIER_3`
- `TIER=2` → `ADR_REASON=TIER_2`
- Issue text mentions changing shared config, public APIs, or data models → `ADR_REASON=SHARED_INTERFACE_SUSPECTED`

When multiple conditions match, use the highest-priority reason: `TIER_3` > `TIER_2` > `SHARED_INTERFACE_SUSPECTED`.

Rationale: any change spanning multiple files or domains (Tier 2+) has enough cross-cutting reach that a one-paragraph ADR is cheap insurance. Tier 1 changes (single module, fully described, < ~200 lines) are self-contained enough that no ADR is needed.

`SHARED_INTERFACE_SUSPECTED` is a lightweight signal from issue text only. A full shared-interface impact probe runs later in `/resolve-issue` Step 0 (pre-probe) and Step 2 as a consistency gate — this upfront flag lets the ADR be requested before `/fix-issue` starts, avoiding mid-run blockers.

**Open questions:** list any decisions or ambiguities not resolvable from the issue text alone. Use semicolons as separators. Leave empty if none.

**Output:**

```
HANDOFF
TIER=<1|2|3>
TIER_RATIONALE=<one sentence citing the signals that matched>
ADR_REQUIRED=<true|false>
ADR_REASON=<TIER_3 | TIER_2_OPEN_QUESTIONS | SHARED_INTERFACE_SUSPECTED | empty>
OPEN_QUESTIONS=<semicolon-separated, or empty>
END_HANDOFF
```

## Output

The HANDOFF block emitted by the subagent is the output of this skill. Pass it to the caller as-is.
