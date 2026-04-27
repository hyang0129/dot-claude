# Shared Complexity Assessment Skill

## Motivation

Both `/resolve-issue` and `/fix-issue` need to assess issue complexity (tier 1/2/3) and decide whether an ADR is required. Currently `/fix-issue` does this as its Step 1. When `/resolve-issue` is the entry point, it would either:

- redundantly let `/fix-issue` re-assess after running its own check, or
- skip assessment and miss the chance to request an ADR upfront (forcing mid-run recovery).

The fix: extract the assessment into a single shared skill that either caller can invoke. When `/resolve-issue` runs it first, the results are forwarded to `/fix-issue` as flags so the work isn't duplicated.

## New file: `commands/assess-complexity.md`

A small, focused, read-only skill. Inputs: the issue body (already fetched by the caller — the skill does not re-fetch). Spawns a single Sonnet subagent.

Output (same HANDOFF format both callers consume):

```
HANDOFF
TIER=<1|2|3>
TIER_RATIONALE=<one sentence>
ADR_REQUIRED=<true|false>
ADR_REASON=<TIER_3 | TIER_2_OPEN_QUESTIONS | SHARED_INTERFACE_SUSPECTED | empty>
OPEN_QUESTIONS=<semicolon-separated, or empty>
END_HANDOFF
```

### Tier signals

Same heuristics `/fix-issue` Step 1 uses today (lifted verbatim into the new skill):

- **Tier 1** — small, localized, well-specified bugfix or tweak.
- **Tier 2** — multi-file change, some design judgment, but scope is clear.
- **Tier 3** — cross-cutting, architectural, or scope-ambiguous.

### ADR_REQUIRED rules

`ADR_REQUIRED=true` when any of:

- `TIER=3` → reason `TIER_3`
- `TIER=2` AND `OPEN_QUESTIONS` non-empty → reason `TIER_2_OPEN_QUESTIONS`
- Issue mentions changing shared config, public APIs, or data models → reason `SHARED_INTERFACE_SUSPECTED`

`SHARED_INTERFACE_SUSPECTED` is a lightweight signal from the issue text only. The full shared-interface impact probe still runs later in `/resolve-issue` Step 2 — this upfront flag just lets us request the ADR before `/fix-issue` starts, avoiding mid-run blockers.

## Modify: `commands/fix-issue.md`

- **Step 1 (tier assessment)** — if `--tier <N>` was passed by the caller, skip the assessment and use the provided `TIER` / `ADR_REQUIRED` values directly. Otherwise spawn `/assess-complexity` exactly as the new skill prescribes.
- **New flag: `--require-adr`** — when present, forces Step 2b (ADR drafting) regardless of tier/open-questions.
- **Final HANDOFF** — add `ADR_PATH=<path or empty>` so `/resolve-issue` Step 2-pre can do a consistency check.

## Modify: `commands/resolve-issue.md`

- **New Step 0** — fetch the issue, spawn `/assess-complexity`, parse the HANDOFF block.
- **Step 1 (fix-issue invocation)** — always forward `--tier <TIER>` (avoids duplicate assessment). Append `--require-adr` if `ADR_REQUIRED=true`. Final shape:
  ```
  /fix-issue <issue> --tier <TIER> [--require-adr] [--worktree] [--base <branch>]
  ```
- **Step 2-pre** — simplified to a consistency check using `ADR_PATH` from Step 1's HANDOFF:
  - `SHARED_INTERFACE_HIT=true` AND `ADR_PATH` non-empty → log and proceed.
  - `SHARED_INTERFACE_HIT=true` AND `ADR_PATH` empty → internal error (Step 0 should have caught it); stop with a message explaining the gap.

## Files

| Action | File |
| --- | --- |
| Create | `commands/assess-complexity.md` |
| Modify | `commands/fix-issue.md` |
| Modify | `commands/resolve-issue.md` |

## Why this shape

- **Single source of truth** for tier signals and ADR rules — change them once, both callers stay aligned.
- **No duplicate work** when `/resolve-issue` is the entry point — the assessment runs exactly once.
- **`/fix-issue` standalone still works** — when invoked directly without `--tier`, it falls back to running `/assess-complexity` itself.
- **ADR requested upfront**, not discovered missing mid-run — `SHARED_INTERFACE_SUSPECTED` from the issue text is a cheap pre-check; the heavyweight shared-interface probe still runs in `/resolve-issue` Step 2 as a consistency gate, not a blocker.
