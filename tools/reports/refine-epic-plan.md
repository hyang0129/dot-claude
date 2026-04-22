# /refine-epic — Implementation Plan

Evidence base: `refine-epic-improvements.md` (12 sessions, 7 days, ~$117 total).

---

## Conflicts and resolutions

| Conflict | Resolution |
|---|---|
| **1a vs Section 4** — 1a says move Decomposer prompt to a file; Section 4 eliminates the Decomposer entirely | 1a is moot; Researcher prompt (4b) takes its place |
| **3b depends on Section 4** — phase-transition tightening must follow the phase restructure | 3b moves to Wave 3, done after 4a–4e |
| **3c auto-resolved by Section 4** — Monitor/TaskOutput ToolSearch calls exist only because of the background Decomposer | No explicit action; resolved when 4 lands |
| **1f prerequisite for Section 4** — fewer org-mode branches makes the decomposition rewrite cleaner | 1f moves to Wave 1 |
| **2f + 2b coordination** — free-form mode needs `gh issue create` before publishing; proposal is to move it into Publisher | Publisher owns all GitHub writes; returns `(EPIC_NUMBER, INTENT_COMMENT_URL)` |

---

## Wave 1 — Text changes, no structural risk

**1f — Factor out `--org` mode**

Verify unused: `git log -S '\-\-org'` against session data + repo history. If confirmed:
- Extract org-only content (Sub-phase 6 confirmation gate, stakeholder matrix in scan targets, org branches in Q list, `*org mode only*` scan targets, Sign-Off Gate table in index template) into `commands/refine-epic-org.md`.
- Replace in main skill with one-line stub: `*Org mode (`--org`): see [refine-epic-org.md](refine-epic-org.md).*`
- Saves ~150 lines / ~4K tokens; simplifies Wave 3 rewrite.

**5a + 5b — Fix surrogate batching**

Rewrite Step 5 spawn paragraph:

> For each child issue, emit one `Agent` tool call. Do NOT batch multiple children into one agent — each surrogate must start with a fresh context. With N children, ROOT emits N separate `Agent` calls, waiting for each to complete before emitting the next.

Add Constraints bullet:

> Do not describe a single subagent as a "multi-way" or "N-way" surrogate. One subagent = one child issue. A subagent that processes multiple children in sequence is a correctness bug: escalations from child N pollute child N+1's context, and the quadratic cache-growth penalty makes it 3–5× more expensive than intended.

**1g — Clarify Sub-phase 1 scan delegation**

Replace:
> Run the Clarifier process directly in this session — do NOT spawn a subagent for this step.

With:
> Run the Q&A rounds directly in this session — do NOT delegate Sub-phases 3–5 to a subagent. The Sub-phase 1 codebase scan SHOULD be delegated to a Sonnet subagent to keep tool-result volume out of ROOT's cache.

**3a — Turn-1 TodoWrite**

Add to Step 0 (Setup), before repo detection:

> Before doing anything else, call `TodoWrite` to initialize your task list with Steps 0–6 (marking Step 0 `in_progress`). This loads the TodoWrite schema early so subsequent updates don't trigger a cache-invalidating ToolSearch mid-session.

---

## Wave 2 — Publisher subagent (~$1.34/epic savings)

**What ROOT does:**
1. Assembles the full intent text in-memory from Q&A transcript + rebuttal (synthesis, needs full context — stays on ROOT).
2. Writes `EPIC_DIR/intent.md` to disk via a single `Write` tool call (file I/O, not output tokens — no print to user).
3. Tells the user: `Intent document written to .agent-work/EPIC_<slug>-<number>/intent.md. Posting to GitHub now...`
4. Spawns Publisher (see below).
5. Once Publisher returns, reports: `Intent posted: <INTENT_COMMENT_URL>`

**What ROOT does NOT do:** print the full document, write `intent-compressed.md`, post the GitHub comment, edit the issue body.

**Publisher subagent** (`model: "claude-sonnet-4-6"`)

Prompt lives in `commands/refine-epic/publisher-prompt.md`. ROOT reads this file at spawn time and passes its contents inline to the subagent.

Inputs passed to Publisher:
- `EPIC_DIR` — absolute path (Publisher reads `intent.md` from here)
- `REPO` — `owner/repo`
- `EPIC_NUMBER` — integer (or `null` for free-form mode)
- `TIER` — `Lite | Standard | Heavy`
- `BODY_SECTIONS` — ordered list of section headings to include in the epic body rewrite (ROOT resolves tier logic; Publisher is a pure executor)
- `COMPRESSED_SCHEMA` — ordered list of section headings to extract verbatim into `intent-compressed.md`
- `FREE_FORM_TITLE` — epic title string (only present in free-form mode; signals Publisher to create the issue first)

Publisher control flow (must be this order):

1. **Free-form mode only:** `gh issue create` with title + Trigger and Pain section as body. Capture `EPIC_NUMBER` and URL. Return these to ROOT if issue creation fails (partial-publish detection in resume check).
2. Read `EPIC_DIR/intent.md`.
3. Derive `intent-compressed.md` by extracting `COMPRESSED_SCHEMA` sections verbatim (literal string slicing between headings — no LLM paraphrase). Write `EPIC_DIR/intent-compressed.md`.
4. `gh issue comment <EPIC_NUMBER> --repo <REPO>` with full intent + `<!-- INTENT_DOC -->` marker. Capture `INTENT_COMMENT_URL`.
5. `gh issue view <EPIC_NUMBER> --repo <REPO> --json body -q .body` → `ORIGINAL_BODY`. Strip existing `## Validated Intent` section if present (idempotent re-run).
6. `gh issue edit <EPIC_NUMBER> --repo <REPO>` prepending `## Validated Intent` + `BODY_SECTIONS` to cleaned `ORIGINAL_BODY`.
7. Log each completed step to stderr (`step 1 done`, `step 2 done`, ...) for partial-publish recovery.
8. Return `INTENT_COMMENT_URL` (and `EPIC_NUMBER` if free-form mode).

**Resume check update (2c):** Step 1 detects partial publish by checking both `test -f intent.md` AND whether the epic has a comment containing `<!-- INTENT_DOC -->`. Mismatch → offer "finish publishing" resume option that re-spawns just the Publisher.

**Step 6 summary (2e):** Replace the inline `gh issue comment` in Step 6 with a lightweight Publisher spawn: `SUMMARY_MD_CONTENT` + repo + number → one Bash call → return comment URL. Model: `claude-sonnet-4-6`.

**Skill text change (2d):** Replace "Produce intent artifact" → publish → compress block with:

> ROOT assembles the full intent.md text in-memory from the transcript and rebuttal, writes it to `EPIC_DIR/intent.md`, then spawns the Publisher subagent. The Publisher reads the file, generates `intent-compressed.md`, posts the intent as a changelog comment, and rewrites the epic body. ROOT reports the returned URL to the user and proceeds to Step 3.

---

## Wave 3 — Decomposition overhaul (~$3–4/epic savings)

**4a — Phase A inline on ROOT**

Remove Decomposer spawn. Replace the opening of Step 3 with a ROOT reasoning step:

From `intent.md` + Sub-phase 1 scan + epic body, ROOT produces a private working note (no tool calls, no file writes) covering:
- Stated scope (key phrases quoted)
- Decomposition goal: slices named explicitly, slices implied, work that is NOT a slice
- Dependency identification: can each candidate slice ship without another?
- Workstream seams: group slices by primary system boundary (data, API, CLI, frontend, jobs, infra) — 3–6 workstreams max

Output: in-memory workstream list with `(name, concern, candidate_slices[])` per workstream.

**4b — Parallel Sonnet Researcher subagents**

ROOT spawns one Researcher per workstream in a single response (all run concurrently).

Researcher prompt lives in `commands/refine-epic/researcher-prompt.md`. ROOT reads this file once, then passes it inline to each spawn with per-workstream substitutions.

Inputs per Researcher:
- Workstream name + concern
- Candidate slices for this workstream
- `intent-compressed.md` contents (verbatim)
- `GIT_ROOT`
- The 5-step research checklist (vocab grep, entry-point enum, dead-integration check, integration-seam detection, test coverage probe)

Each Researcher returns:
```json
{
  "workstream": "",
  "files_touched": [],
  "entry_points": [],
  "suspected_unwired": [],
  "integration_seams": [],
  "coverage_gaps": [],
  "notes": ""
}
```

No file writes. Model: `claude-sonnet-4-6`.

**4c — Phase C inline on ROOT**

ROOT collects all Researcher outputs and:
1. Intersects `files_touched` across Researchers — any file in ≥2 outputs is a seam candidate.
2. Runs Quality Checks (DAG-ness, Slice Independence, every risk has a mitigation, every child has a Behavioral Question or `NEEDS HUMAN INPUT`).
3. Writes `EPIC_DIR/index.md` and `EPIC_DIR/child-<N>-<slug>.md` files directly.
4. Populates Inherited Intent blocks using slice-relevance filtering against `intent-compressed.md`.

Seam detection is mechanical (intersection), not judgment-based — more reliable than a single-agent approach.

**4d — Kill the post-decomposer improvisation gap**

Add bridge text between Step 3 and Step 4:

> The Researchers' outputs and the artifacts ROOT wrote from them are authoritative. Do not re-read `index.md` or sample child drafts to "verify" before Step 4 — the Quality Checks already ran inline as part of Phase C. Proceed directly to Step 4.

At Step 4 → Step 5 boundary:

> Do not pause for user approval between creating child issues and spawning the first Surrogate.

**4e — Collapse child-issue creation to one Bash script**

Rewrite Step 4's Bash example as a single heredoc'd script that derives titles from child-draft first-line headers and creates all issues in one pass.

**3b — Tighten phase transitions** *(done here, after phase structure is final)*

At each major phase boundary, add an explicit one-line instruction: what to do next + exactly what single `TodoWrite` update to make. Remove any open-ended "plan the next step" language. Boundaries to cover:
- After Step 2 Clarifier (Publisher spawned, intent posted) → mark Step 2 done, Step 3 in_progress, proceed to Phase A
- After Researchers return → mark Researcher phase done, proceed to Phase C writes
- After Step 4 (child issues created) → mark Step 4 done, Step 5 in_progress, spawn first Surrogate
- After Step 5 (all surrogates complete) → mark Step 5 done, Step 6 in_progress, spawn summary Publisher

**3c — auto-resolved** by 4 (no background Decomposer = no Monitor/TaskOutput ToolSearch).

**Tooling update:** In `tools/find-refine-epic-sessions.py`:
- Remove `Decomposer` label from `classify_subagent`
- Add `researcher` label
- Update `compute_phase_boundaries` to use first-Researcher-spawn where it used first-Decomposer-spawn
- DECO phase label goes away; new unified phase spans first-Researcher-spawn → first-Surrogate-spawn

---

## Wave 4 — Skill body cleanup

After all structural changes land, extract and compress:

**1b — Surrogate instructions out**
Extract Step 5's Surrogate agent instructions block to `commands/refine-epic/surrogate-prompt.md`. ROOT reads at spawn time, passes inline. ~70 lines removed from main skill.

**1c — Challenger prompts out**
Extract Sub-phase 5's three Challenger role prompts to `commands/refine-epic/challenger-prompts.md`. ROOT reads at spawn time, passes inline. ~40 lines removed.

**1d — Compress intent templates**
Move the Standard/Heavy `intent.md` section schema and `intent-compressed.md` schema to `commands/refine-epic/intent-templates.md`. ROOT loads only when writing those artifacts. ~200 lines removed.

**1e — Trim redundant prose**
Deduplicate the "bluffing vs. considered-position" framing in Sub-phases 3 and 4 — same examples appear in slightly different words in both places. Consolidate to one location.

---

## Files changed

| File | Change |
|---|---|
| `commands/refine-epic.md` | All direct edits across all waves |
| `commands/refine-epic-org.md` | New — org-mode content (Wave 1) |
| `commands/refine-epic/publisher-prompt.md` | New — Wave 2 |
| `commands/refine-epic/researcher-prompt.md` | New — Wave 3 (replaces 1a) |
| `commands/refine-epic/surrogate-prompt.md` | New — Wave 4 |
| `commands/refine-epic/challenger-prompts.md` | New — Wave 4 |
| `commands/refine-epic/intent-templates.md` | New — Wave 4 |
| `tools/find-refine-epic-sessions.py` | Phase label update — Wave 3 |

---

## Acceptance checks

**Wave 1**
- Turn 1 (or 2) contains a `TodoWrite` call; no `ToolSearch` for `TodoWrite` appears after turn 2.
- Step 5 subagent count = N (one per child); no subagent description contains "N-way" or "multi-way."

**Wave 2**
- R-POST-CHAL ROOT turn count drops from 8 → ~4 (Challenger spawn, rebuttal display, Publisher spawn, move to Step 3).
- Publisher subagent appears in session output; cost < $0.30.
- GitHub surfaces unchanged: epic body has Validated Intent section, changelog comment posted with `<!-- INTENT_DOC -->` marker.
- Re-run on already-refined epic: body rewrite is idempotent (no stacked Validated Intent sections).

**Wave 3**
- Average ROOT turn `cache_read_input_tokens` drops by 15K+ after Wave 4 extraction.
- Researcher subagents appear as a new phase; combined cost < $0.50.
- No `TodoWrite` between Researcher phase and Step 5 spawn.
- `index.md` Integration Seams table populated mechanically from ROOT's merge step.
- First-turn cost on R-SCAN ≤ $0.35.

**Wave 4**
- Skill body shrinks from ~30K tokens to ~12–14K.
- First-turn cold-start cost drops to ≤ $0.35 (from ~$0.75).
