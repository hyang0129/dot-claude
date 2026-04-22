# Skill Token Analysis Guide

How to investigate token usage for a Claude Code skill, identify the expensive phases, and generate a concrete improvement plan. The process was developed for `/refine-epic` but applies to any multi-turn, multi-subagent skill.

---

## When to use this

Run this analysis when:
- A skill consistently costs more than expected (e.g. >$10/invocation)
- You suspect a specific phase is the culprit but don't have turn-level evidence
- You want to prioritize optimization work with real cost numbers, not guesses

---

## Overview

The process has four stages:

```
1. Broad scan        → per-session, per-phase summary across recent invocations
2. Targeted drill    → per-turn cost + tool-call detail on the expensive sessions
3. Synthesis         → root-cause findings with cost estimates
4. Planning          → wave-sequenced implementation plan resolving conflicts
```

Each stage informs the next. The scan tells you where to drill; the drill tells you why it's expensive; the synthesis tells you what to change; the plan tells you in what order.

---

## Stage 1 — Build the session scanner

Write a Python script (e.g. `tools/find-<skill>-sessions.py`) that:

1. **Identifies true invocations.** Scan `~/.claude/projects/**/*.jsonl` for user messages containing `<command-name>/<skill-name></command-name>`. This tag is injected by the Claude Code harness only when the human types the slash command — it is not present in AI-generated text that merely mentions the skill.

2. **Skips subagent files.** Session files under a `.../subagents/` path are children of a root session, not roots themselves. Filter them out of the top-level scan.

3. **Deduplicates usage by `message.id`.** One API response is often split across multiple JSONL records (one per content block), all carrying identical usage data. Dedup on `message.id`, not the per-record `uuid`, or costs will be multiplied by the number of content blocks per turn.

4. **Loads subagent usage.** Each root session may have a `<session-id>/subagents/` directory with per-subagent JSONL files and `.meta.json` sidecar files. Read these to get a full picture of total session cost.

5. **Classifies subagents by phase.** Match `description` fields from `.meta.json` against regex patterns to label each subagent's role (e.g. `challenger`, `decomposer`, `surrogate`, `explore`). This lets you aggregate cost by functional role, not by arbitrary agent ID.

6. **Splits ROOT into sub-phases by timeline.** A single root session contains multiple logical phases (scan, interview, post-challenger, post-decomposer, etc.). Detect phase boundaries by scanning for:
   - The `/skill-name` command timestamp → start
   - First real user reply (after at least one assistant turn) → end of scan phase
   - First subagent spawn of each type → phase transition
   
   Assign each assistant turn to a phase based on its timestamp relative to these boundaries.

7. **Reports cost by model.** Cache pricing varies 5–15× between Haiku and Opus. Always break out cost per model, not just per total token count. Use pricing constants (input, output, cache-write, cache-read rates) applied to the `usage` fields in each assistant message.

**Output modes to implement:**
- `--summary` — one row per session, total tokens + cost
- `--detail` — per-session breakdown by role (ROOT, CHAL, DECO, SURR, etc.)
- `--md PATH` — write a full Markdown report for review in the IDE
- `--json` — raw JSON for programmatic analysis

**Key metrics to surface:**
- `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`
- `hit%` = cache_read / (input + cache_write + cache_read) — high hit% is good; low hit% on a mature session signals a mid-session cache invalidation
- Cost per phase and cost per session

---

## Stage 2 — Build the phase analyzer

Once you have a session scanner that identifies which phase is most expensive, write a second script (e.g. `tools/analyze-<skill>-phase.py`) that drills into one session × phase at turn-level granularity.

The phase analyzer:

1. **Takes `<match> <phase>` as arguments.** `match` is a substring of the issue URL or session ID; `phase` is a short alias (`scan`, `intv`, `post-chal`, etc.).

2. **Walks every event in the session JSONL in timestamp order.** Merge all records sharing a `message.id` into a single logical turn — accumulate tool_use blocks from later records into the first record's turn object.

3. **Recomputes phase boundaries** using the same heuristic as the scanner (command timestamp, first-user-reply, subagent-spawn timestamps). Apply boundaries to select only the turns that fall inside the requested phase.

4. **Produces a chronological turn table** with columns: turn #, elapsed time since phase start, model, in/cw/cr/out tokens, cost, tools called. This makes it easy to spot which turns are burning money and why.

5. **Produces a tool-usage summary** — for each tool name that appeared in the phase, how many turns called it and what was the combined cost of those turns. This highlights if a single tool (e.g. `Write`) is responsible for most of the phase cost.

6. **Shows top-N most expensive turns in full detail** — tokens, cost, text snippet, and formatted tool-call inputs (file paths, Bash commands, agent descriptions). These are the specific turns to target.

**What to look for in the output:**
- Turns with high `cache_write` but low `cache_read` → mid-session cache invalidation (something changed the prompt prefix)
- Turns that are expensive purely from `cache_read` with trivial output → context-replay penalty (the model is paying to re-read accumulated context just to do a small task)
- Clusters of small, cheap turns → may indicate the agent is doing unnecessary ceremony (TodoWrite rewrites, redundant reads)
- A single very expensive turn → may indicate a large file Write or a complex synthesis that could be delegated to a cheaper model

---

## Stage 3 — Run the analysis

### Broad scan first

```bash
python tools/find-<skill>-sessions.py --days 7 --md tools/reports/<skill>-YYYY-MM-DD.md
```

Open the report and read:
- Which sessions are outliers (top 20% by cost)?
- Which phases dominate total cost across all sessions?
- Is there one phase that's consistently expensive, or is variance high across sessions?

### Drill the expensive sessions

For each outlier session, drill the two or three most expensive phases:

```bash
python tools/analyze-<skill>-phase.py <session-match> intv \
    --top 6 --md tools/reports/analyze-<session-match>-intv.md

python tools/analyze-<skill>-phase.py <session-match> post-chal \
    --top 6 --md tools/reports/analyze-<session-match>-post-chal.md
```

Drill a second session's same phase to corroborate patterns — if the same behavior appears in two independent sessions, it's systematic, not a one-off.

### What to document per phase

For each phase analyzed, note:
- **Total cost and turn count**
- **Dominant cost driver** (cache-write on first turn? Output-heavy turns? Context-replay on every turn?)
- **Which tools appeared** and in which turns
- **Any anomalous turns** (big spikes, suspicious tool patterns, unexpected ToolSearch calls)
- **The root cause** in one sentence

---

## Stage 4 — Synthesize improvements

Write `tools/reports/<skill>-improvements.md` with one section per problem found. Each section should contain:

1. **Problem statement** — what's happening, where (which phase, which turns), and why it's expensive
2. **Evidence** — specific numbers from the analysis reports (turn cost, token counts, phase totals)
3. **Proposed actions** — numbered, checkboxed list of concrete changes; include the exact text to add/replace in the skill file where relevant
4. **Expected impact** — estimate savings per invocation and per week (sessions/week × savings/session)
5. **Risk** — what could go wrong with this change; what invariants must be preserved
6. **Acceptance check** — measurable criteria for verifying the fix worked (e.g. "turn count in this phase drops from 8 → ~4", "first-turn cost ≤ $0.35")

**Common improvement categories to look for:**

| Pattern | What it means | Typical fix |
|---|---|---|
| High cache-write on first turn | Skill body is large; cold-start pays for it | Extract subagent-only content to separate files loaded at spawn time |
| Mid-session cache invalidation | A ToolSearch fetched a deferred tool schema, changing the prompt prefix | Pre-load that tool on turn 1 |
| Expensive turns doing file I/O or bash | Mechanical work running on a large-context Opus turn | Delegate to a Sonnet Publisher/Writer subagent with a small, flat context |
| Sequential per-item turns | Agent is processing items one-by-one on ROOT | Spawn N parallel subagents, one per item |
| Quadratic context growth | Single subagent handling N serial items | Enforce one-subagent-per-item; name the batching failure mode explicitly in the skill |
| Improvised post-return ceremony | Skill leaves a gap between "subagent returned" and "proceed to next step" | Add explicit bridge text in the skill telling ROOT exactly what to do next |
| Multiple rapid TodoWrite calls | Phase-transition instructions are ambiguous; agent is re-planning | Add turn-1 TodoWrite (loads schema early); tighten phase boundaries to one update each |

---

## Stage 5 — Write the implementation plan

Write `tools/reports/<skill>-plan.md` that sequences the improvements into waves, where each wave is a coherent unit of risk:

- **Wave 1** — text-only changes (rewrite a sentence, add a constraint bullet). Zero structural risk; can ship and test immediately.
- **Wave 2** — new subagent patterns (introduce a Publisher, a Writer). Changes who does work but not the overall flow.
- **Wave 3** — structural overhaul (replace a monolithic subagent with N parallel ones; fold a phase into ROOT). Highest risk; do last.
- **Wave 4** — cleanup (extract prompt files, trim dead branches). Do after structural changes are stable.

**Per wave, specify:**
- The exact changes to make (including the literal text to add/replace in the skill file)
- Conflicts with other waves and how they're resolved
- Acceptance checks

**Conflict resolution is required.** Improvements often conflict (e.g. "move Decomposer prompt to a file" conflicts with "eliminate the Decomposer entirely"). Resolve every conflict explicitly in the plan before starting implementation.

---

## Adapting to a new skill

To apply this process to a different skill (e.g. `/resolve-issue`, `/e2e-qa`):

1. **Identify the invocation tag.** Find how the skill is invoked (`<command-name>/<skill-name></command-name>`) and update the scanner's detection pattern.

2. **Map the skill's phases.** Read the skill's source file and identify the major phases (e.g. setup → scan → interview → publish → decompose → surrogate → summary). These become the phase boundaries the scanner and analyzer detect.

3. **Identify phase boundary signals.** For each phase, decide what event in the JSONL marks the transition: a specific user reply, a subagent spawn with a recognizable description keyword, a file write to a known path, or a specific tool call. Add these to the scanner's `collect_root_phases` function and the analyzer's `compute_phase_boundaries` function.

4. **Copy the two scripts and update the skill-specific constants** (phase names, subagent classification keywords, phase labels for the report).

The cost-accounting, dedup logic, pricing tables, and report formatting are all reusable without modification.

---

## Reference: Cost formulas

```
cost_usd = (
    input_tokens              * price_per_M_input  +
    output_tokens             * price_per_M_output +
    cache_creation_input_tokens * price_per_M_cache_write +
    cache_read_input_tokens   * price_per_M_cache_read
) / 1_000_000

# Approximate pricing (USD/MTok, April 2026):
#   Opus   — in: $15, out: $75, cw: $18.75, cr: $1.50
#   Sonnet — in: $3,  out: $15, cw: $3.75,  cr: $0.30
#   Haiku  — in: $1,  out: $5,  cw: $1.25,  cr: $0.10

hit% = cache_read / (input + cache_write + cache_read) * 100
```

The cache-write rate is 1.25× the input rate; the cache-read rate is 0.1× the input rate. This means:
- A large skill body is paid for at 1.25× on the first (cold) turn
- Every subsequent turn replays it at 0.1× — cheap individually, but adds up across many turns
- Reducing the skill body by 20K tokens saves $0.375/MTok on write and $0.030/MTok on every read thereafter

---

## Files produced by a typical analysis run

```
tools/
  find-<skill>-sessions.py        # session scanner
  analyze-<skill>-phase.py        # phase drill-down analyzer
  reports/
    <skill>-YYYY-MM-DD.md         # broad scan output
    sessions-full.md              # optional wider-window scan
    analyze-<session>-<phase>.md  # per-phase drill reports (one per session×phase)
    <skill>-improvements.md       # synthesized findings + proposed actions
    <skill>-plan.md               # wave-sequenced implementation plan
```
