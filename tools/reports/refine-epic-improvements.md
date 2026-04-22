# /refine-epic — Improvement Action List

Evidence base: [refine-epic-2026-04-22.md](refine-epic-2026-04-22.md) (12 sessions, past 7 days) and [analyze-236-post-chal.md](analyze-236-post-chal.md) (deep dive on session #11, R-POST-CHAL).

Cost context after the `message.id` dedup fix:
- 12 sessions over 7 days = **~$117 total**
- Per-phase ranking: DECO $26.77 · R-INTV $24.40 · R-POST-DECO $22.01 · R-POST-CHAL $16.64 · SURR $13.26 · R-SCAN $9.30 · R-POST-SURR $1.67
- Every ROOT turn replays ~70–110K tokens of cached context. At Opus rates that's ~$0.13/turn of pure replay before any output is generated.

---

## 1. Skill body reduction

**Problem.** [commands/refine-epic.md](../../commands/refine-epic.md) is 1,280 lines (~25–35K tokens). The harness injects it verbatim as a user message at invocation, and it rides along in every turn's cache-read for the entire session. Across a 15-turn session on Opus that's **~$0.60 of replay cost attributable to the skill file itself**, before any real work is done.

**What the skill body currently contains:**

| Section | Approx. lines | Who needs it | Needed when |
|---|---|---|---|
| Purpose + priority + pipeline overview | ~30 | ROOT only | once, at start |
| Args + mode description | ~30 | ROOT only | once, at start |
| Setup (repo detection, git root, EPIC_DIR) | ~90 | ROOT only | Steps 0–1 |
| Step 1 — Resume Check | ~35 | ROOT only | Step 1 |
| Step 2 — Clarifier process (Sub-phases 1–6 + artifacts + publish) | ~500 | ROOT + (a slice is read by Challengers) | Step 2 |
| Step 3 — Decomposer instructions + output templates | ~300 | **Decomposer subagent**, not ROOT | Step 3 |
| Step 4 — Child issue creation loop | ~40 | ROOT only | Step 4 |
| Step 5 — Surrogate instructions + template | ~70 | **Surrogate subagents**, not ROOT | Step 5 |
| Step 6 — Summary comment | ~25 | ROOT only | Step 6 |
| Process Gates + Constraints footer | ~40 | ROOT only | reference |

**Observation.** Roughly **~30% of the file is content that only a subagent ever needs to read** (Decomposer prompts, Surrogate prompts, child issue templates) — but because it lives in the skill body it rides along in every ROOT turn's cache-read.

**Proposed actions**

- [ ] **1a. Move Decomposer instructions out.** Relocate "Decomposer agent instructions" (Phase A / B / C + Quality checks + child draft template) into a separate file — either `commands/refine-epic/decomposer-prompt.md` or a dedicated subagent prompt loaded by the Decomposer spawn. ROOT should only need to know: "spawn the Decomposer, pass it X Y Z, it writes `index.md` + `child-<N>.md` files." Estimated savings: ~300 lines / ~8K tokens from ROOT replay.
- [ ] **1b. Move Surrogate instructions out.** Same treatment for Step 5's Surrogate block. ~70 lines / ~1.5K tokens.
- [ ] **1c. Move Challenger prompts out.** Sub-phase 5's three Challenger role prompts are already block-quoted strings that get passed to subagents; they can live in a separate file that ROOT reads only at spawn time. ~40 lines / ~1K tokens.
- [ ] **1d. Compress the intent.md + compressed-intent section templates.** These markdown templates are ~200 lines combined. Keep the authoritative copy in a separate `intent-templates.md` that ROOT loads only when writing those artifacts (Sub-phase 5→6 transition). Or inline-generate from a shorter schema. ~5K tokens.
- [ ] **1e. Trim redundant prose in Sub-phase descriptions.** Sub-phases 3–4 repeat the same "bluffing vs. considered-position" framing in slightly different words in multiple places. Deduplicate. ~2–3K tokens.
- [ ] **1f. Remove org-mode branches the user doesn't run.** `--org` mode adds substantial lines (stakeholder matrix, borrowed-invariant dispositions, Sub-phase 6 gate). If it's never used in practice, factor into a separate `commands/refine-epic-org.md` variant. ~150 lines / ~4K tokens (check git log to confirm it's unused).

**Cold-start amplifier.** R-SCAN analysis on session 236 shows the first turn of every session costs $0.75, of which **94.9% is cache-write** (38K tokens × $18.75/M Opus write rate = $0.715). Reducing the skill from 38K → 14K tokens (1a–1e combined) drops the cold-start from $0.75 → $0.30 and saves $0.036/turn on every subsequent replay. Across a 15-turn session: **~$0.95 saved per epic** — larger than the per-turn replay savings alone because the write rate ($18.75/M) is 12.5× the read rate ($1.50/M).

**Expected impact (if all of 1a–1e land):** skill body shrinks from ~30K tokens to ~12–14K. First-turn cold-start drops by ~$0.45. Per-turn cache-read saves ~$0.036/turn. Combined across a 15-turn Opus session: **~$0.95/epic**. Over 12 epics/week: **~$11/week**.

- [ ] **1g. Clarify the Sub-phase 1 scan delegation rule.** The skill currently says *"Run the Clarifier process directly in this session — do NOT spawn a subagent for this step."* Session 236 shows ROOT correctly violated this by delegating the codebase scan to a Sonnet subagent (`"Sub-phase 1 codebase scan for state ownership"`), keeping grep/read results out of ROOT's cache and off every subsequent ROOT turn's replay cost. The prohibition was intended to prevent the Q&A from being delegated (a surrogate can't do the premortem), but it inadvertently bans the scan delegation too. Fix: split the instruction: *"Run the Q&A rounds directly in this session — do NOT delegate Sub-phases 3–5 to a subagent. The Sub-phase 1 codebase scan SHOULD be delegated to a Sonnet subagent to keep tool-result volume out of ROOT's cache."* This formalizes a behavior ROOT is already discovering on its own.

**Risk.** Splitting the file means a Decomposer or Surrogate subagent must know how to load its own prompt file. Either (a) the parent passes the file contents inline at spawn (adds one-time read cost but doesn't bloat ROOT), or (b) the subagent reads the file itself on startup (small cost, keeps the parent clean). Option (a) is simpler.

**Acceptance check.** After the split, re-run `python tools/find-refine-epic-sessions.py --days 7 --md ...` on one fresh `/refine-epic` invocation; average ROOT turn `cache_read_input_tokens` should drop by 15K+. First-turn cost on R-SCAN should be ≤$0.35.

---

## 2. Collapse publish turns 4–7 into a single Sonnet Publisher subagent

**Problem.** After the Challenger rebuttal, ROOT itself runs four mechanical turns back-to-back, each paying ~$0.13 in cached-context replay on Opus before any real work happens:

1. `Write EPIC_DIR/intent.md` (~20–25 KB assembled markdown)
2. `Write EPIC_DIR/intent-compressed.md` (extractive verbatim concatenation of sections 2a, 2b, 3, 4, 6, 8, 9)
3. `Bash: gh issue comment <number>` (post full intent with `<!-- INTENT_DOC -->` marker)
4. `Bash: gh issue edit <number>` (rewrite epic body with `## Validated Intent` section, preserving original description)

From [analyze-236-post-chal.md](analyze-236-post-chal.md), these were turns 4–7 of R-POST-CHAL and cost **$1.89 of the $3.34 phase (57%)**. None of them need ROOT's full accumulated context (scan artifacts, Q&A transcript, challenger outputs) — they only need the finalized intent text and a few parameters.

**Proposed action — collapse into one `Agent` spawn.**

ROOT assembles the full intent text (keeps the transcript + rebuttal in context to do this correctly) and emits it as part of the subagent prompt. The Publisher handles all four mechanical steps inside one subagent lifetime and returns one value: `INTENT_COMMENT_URL`.

- [ ] **2a. Publisher subagent prompt (inline inputs).**
  - `INTENT_MD_CONTENT` — the finalized `intent.md` text, verbatim.
  - `EPIC_DIR` — absolute path.
  - `REPO` — e.g. `owner/repo`.
  - `EPIC_NUMBER` — integer.
  - `TIER` — `Lite` | `Standard` | `Heavy` (determines which sections appear in the body rewrite).
  - `BODY_SECTIONS` — the tier-specific list of section headings to include in the epic body (so the Publisher doesn't need tier logic).
  - `COMPRESSED_SCHEMA` — ordered list of section headings to extract verbatim into `intent-compressed.md`.

  Model: `claude-sonnet-4-6`. No reasoning required — all steps are file I/O and string manipulation.

- [ ] **2b. Publisher control flow (must be this order for atomicity).**
  1. `Write EPIC_DIR/intent.md` with `INTENT_MD_CONTENT`.
  2. Derive `intent-compressed.md` by extracting `COMPRESSED_SCHEMA` sections verbatim from `INTENT_MD_CONTENT` (no LLM paraphrase — literal string slicing between headings). `Write EPIC_DIR/intent-compressed.md`.
  3. `gh issue comment <EPIC_NUMBER> --repo <REPO> --body-file -` with the full intent + `<!-- INTENT_DOC -->` marker. Parse the returned URL → `INTENT_COMMENT_URL`.
  4. `gh issue view <EPIC_NUMBER> --repo <REPO> --json body -q .body` to read `ORIGINAL_BODY`. If `ORIGINAL_BODY` already contains `## Validated Intent`, strip that section through `## Original Description` before proceeding (idempotent re-run).
  5. `gh issue edit <EPIC_NUMBER> --repo <REPO> --body-file -` with `## Validated Intent` + `BODY_SECTIONS` prepended to the cleaned `ORIGINAL_BODY`.
  6. Return `INTENT_COMMENT_URL`.

- [ ] **2c. Failure atomicity.** If the Publisher crashes partway, ROOT has no easy recovery path. Two mitigations:
  - Publisher must log each completed step to stderr (`step 1 done`, `step 2 done`, ...) so ROOT can see where it stopped.
  - Enhance Step 1 (Resume Check) in the skill: detect partial publish by checking both `test -f intent.md` AND whether the epic has a comment containing `<!-- INTENT_DOC -->`. If local file exists but GitHub comment doesn't (or vice versa), offer a "finish publishing" resume option that re-spawns just the Publisher.

- [ ] **2d. ROOT changes in [commands/refine-epic.md](../../commands/refine-epic.md).** Sub-phase 5 (after rebuttal capture) currently flows into "Produce intent artifact" → "Create epic GitHub issue (free-form mode only)" → "Publish to GitHub — two surfaces" → "Extractive compression". Replace all of those sections with:
  > After the rebuttal is captured and any conceded-point revisions land in the intent sections, ROOT assembles the full intent.md text in-memory, then spawns the Publisher subagent with `INTENT_MD_CONTENT` and parameters above. The Publisher returns `INTENT_COMMENT_URL`. ROOT reports the URL to the user and proceeds to Step 3.

- [ ] **2e. Step 6 decomposition summary (bonus).** The Step 6 `gh issue comment` runs at peak ROOT context (after all surrogates have returned). Reuse the Publisher pattern with a lighter prompt: `SUMMARY_MD_CONTENT` + repo + number → one Bash call, return the comment URL. Cheaper because the context is smaller than it would be on ROOT, and doesn't require Opus. Estimated additional savings: ~$0.15/epic.

- [ ] **2f. Free-form epic creation.** In free-form mode, an epic issue is created *before* publishing. Keep that `gh issue create` call on ROOT (it needs the epic number returned to proceed), or move it into the Publisher and widen the return value to `(EPIC_NUMBER, INTENT_COMMENT_URL)`. Latter is cleaner — one subagent owns all GitHub writes for this phase.

**Expected impact per epic**

Rough math from session 236 numbers:

| Cost component | Before (ROOT Opus) | After (Publisher Sonnet) |
|---|---|---|
| 4 turns × ~$0.13 cache-read replay | $0.52 | — (one subagent spawn, small context) |
| Write intent.md (~8K output) | Opus: $0.60 | Sonnet: $0.12 |
| Write intent-compressed.md (~3.5K output) | Opus: $0.26 | Sonnet: $0.05 |
| 2 × Bash gh commands (~3K output combined) | Opus: $0.23 | Sonnet: $0.05 |
| Publisher subagent overhead (input + cache-write for its small prompt) | — | ~$0.05 |
| **Total** | **$1.61** | **$0.27** |

**~$1.34 saved per epic, or roughly 40% of R-POST-CHAL phase cost.** Across 12 epics/week: ~$16/week. Larger than #1's savings because it hits the output-heavy turns, not just the replay.

**Risk.** The "final intent content" passed to the Publisher must be complete — if ROOT drops any section during assembly, the Publisher can't recover it. Mitigation: ROOT assembles the full intent.md text (as it does today) and passes it verbatim; the Publisher is a pure "write + publish" executor with no synthesis.

Secondary risk: body-rewrite idempotence. The skill currently says "If the epic body already contains a `## Validated Intent` section (prior run), replace it in place rather than stacking." The Publisher prompt must preserve this behavior — include the detection rule in the prompt, and cover it with a manual test on a re-run of an already-refined epic.

**Acceptance check.** On a fresh `/refine-epic` invocation:
- R-POST-CHAL ROOT turn count drops from 8 → ~4 (Challenger spawn, rebuttal display, Publisher spawn, move to Step 3).
- Publisher subagent appears in [find-refine-epic-sessions.py](../find-refine-epic-sessions.py) output under a new phase label; verify its cost is <$0.30.
- GitHub surfaces unchanged: epic body has Validated Intent section, changelog comment posted with `<!-- INTENT_DOC -->` marker.

---

## 3. Front-load TodoWrite on turn 1; tighten phase-transition instructions to reduce mid-session updates

**Problem — ToolSearch schema injection causes mid-session cold writes.**

`TodoWrite` is a deferred tool in Claude Code: its schema is not loaded into the API's tool-definitions array at session start. Before ROOT can call it, Claude Code automatically emits a `ToolSearch` to fetch the schema. Analysis across 12 sessions shows every `ToolSearch` is followed by a cache miss on the next turn — the schema injection changes the API request prefix, breaking the existing cache checkpoint. In the two R-INTV phases analysed:

| Session | ToolSearch turn | Next turn (TodoWrite) | Cold-write cost |
|---|---|---|---|
| 236 R-INTV | turn 4, t+8m58s | turn 5, cw=59K, cr=16K | **$1.22** |
| 196 R-INTV | turn 3, t+18m14s | turn 4, cw=84K, cr=0 | **$1.63** |

**Problem — clustered mid-session TodoWrites indicate ambiguous phase instructions.**

Scripted search shows sessions where ROOT calls `TodoWrite` 3–4 times within 10 minutes (sessions `7c1c0cea`, `dc1f1529`). Multiple rapid-fire updates indicate the agent is re-planning because the skill's phase-transition instructions are unclear — not because it has new information to record. Each update is a redundant turn at ~$0.25 on Opus.

**TodoWrite is genuinely useful in long sessions.** In sessions with wide phase separation (e.g. `2e84b994`, 4 writes spread across t+89m, 107m, 125m, 179m), `TodoWrite` helps the agent stay oriented across a 3-hour, 50-turn run. The goal is not to eliminate it — it's to make it deliberate (one write per phase, planned not reactive) instead of frantic (several corrective rewrites per phase).

**Proposed actions**

- [ ] **3a. Add a turn-1 TodoWrite to the skill's opening.** The skill should instruct ROOT to call `TodoWrite` on its very first turn, initializing the todo list with all phases it will run. Turn 1 is always a cold cache write (session start), so the ToolSearch + schema injection adds nothing to the cold-write cost — it just slightly widens an already-paid write. All subsequent `TodoWrite` calls in the session then have the schema pre-loaded, no ToolSearch, no mid-session cache invalidation.

  Add to the skill's Step 0 (Setup):
  > Before doing anything else, call `TodoWrite` to initialize your task list with Steps 0–6 (marking Step 0 `in_progress`). This loads the TodoWrite schema early so subsequent updates don't trigger a cache-invalidating ToolSearch mid-session.

- [ ] **3b. Tighten phase-transition language to eliminate re-planning updates.** For each major phase boundary in the skill (after Step 2 Clarifier, after Step 3 / Researchers return, after Step 4, after Step 5), add an explicit one-line instruction telling ROOT exactly what to do next and what single `TodoWrite` update to make. Remove any open-ended "plan the next step" language that causes ROOT to reason about next steps from scratch. Expected: one deliberate `TodoWrite` per phase transition instead of 2–4 corrective ones.

- [ ] **3c. `Monitor` and `TaskOutput` become obsolete via section 4.** These two deferred tools are currently ToolSearch'd mid-session when ROOT waits on the Decomposer background agent. Section 4 eliminates background agents; ROOT collects Researcher outputs synchronously. No explicit action needed here beyond implementing section 4.

**Expected impact.** The $1.22–$1.63 cold write caused by mid-session ToolSearch is eliminated by 3a. The clustered-rewrite pattern (2–3 extra TodoWrite turns per session) is reduced by 3b. Combined: **~$1.50–2/epic** in cache-miss and redundant-turn savings. At 12 epics/week: **~$18–24/week**.

**Risk.** Low. Adding a turn-1 TodoWrite is purely additive; it cannot break existing behavior. Tightening phase-transition language carries the same risk as any skill instruction change — test on one fresh session before rolling out.

**Acceptance check.** On a fresh `/refine-epic` invocation:
- Turn 1 (or 2) contains a `TodoWrite` call; no `ToolSearch` query for `TodoWrite` appears anywhere in the session after turn 2.
- `Monitor` and `TaskOutput` ToolSearch calls do not appear (once section 4 is implemented).
- Total `TodoWrite` calls across the session ≤ 1 per phase (Steps 0–6 = 7 max); no two `TodoWrite` calls within 5 minutes of each other.

---

## 4. Rework decomposition phase — fold A/C into ROOT, parallel Sonnet subagents for B

Evidence base: [analyze-236-post-deco.md](analyze-236-post-deco.md) — R-POST-DECO on session 236 was 9 turns / $2.51 / 1h11m wall-clock.

**Problem.** Step 3 spawns a single Opus Decomposer subagent that does Phase A (understand epic), Phase B (per-workstream codebase research), and Phase C (write artifacts) end-to-end. This has three specific inefficiencies:

1. **Phase A is redundant.** ROOT has just finished Step 2, which means `intent.md`, the epic body, Sub-phase 1 scan outputs (vocabulary grep, coarse module boundaries, coupling map, borrowed invariants), and the Q&A transcript are already hot in ROOT's cache. The Decomposer's "Phase A — Understand the Epic's Scope and Decomposition Goal" re-derives scope, workstream seams, and dependency identification from scratch — work ROOT could do inline in 1 turn from context it already paid to load.
2. **Phase B's per-workstream searches are embarrassingly parallel but serialized.** The "5-step checklist per workstream" (vocab grep, entry-point enum, dead-integration check, integration-seam detection, test coverage probe) runs sequentially inside one subagent. For a 4-workstream epic that's ~20 searches serialized; they share no state and could run concurrently.
3. **Phase C writes are light work misallocated to Opus.** Assembling `index.md` from Phase A/B outputs and writing `child-<N>-<slug>.md` drafts is template-filling, not reasoning. It pays Opus rates for clerical work.

Observed post-return ROOT behavior (turns 2–9 of R-POST-DECO on 236) compounds the problem: ROOT spent ~$1 improvising a re-review of the Decomposer's artifacts (ls, Read index.md, Read one arbitrary child, TodoWrite, then an unprescribed "let me present this for your review" pause that contradicts Step 5's "run immediately after Step 4"). The skill leaves a gap between "Decomposer returned" and "run Step 4" and ROOT fills it with low-value ceremony.

**Proposed action — split the phase into three pieces:**

- [ ] **4a. Phase A → ROOT, inline.** Replace the Decomposer's Phase A with a short ROOT step: from `intent.md` + Sub-phase 1 scan + epic body, produce a private working note covering stated scope, decomposition goal (with slice candidates), dependency identification, and workstream seams. ROOT already has every input loaded — this is 1 turn of pure reasoning, no tool calls. Output: an in-memory workstream list with `(name, concern, candidate slices)` per workstream, plus a candidate slice → workstream mapping.

- [ ] **4b. Phase B → N parallel Sonnet Researcher subagents, one per workstream.** Spawn one Sonnet subagent per workstream identified in 4a, all in a single ROOT response so they run concurrently. Pass each Researcher:
  - The workstream name + concern (from 4a).
  - The candidate slices in this workstream (from 4a).
  - `intent-compressed.md` contents (slice-relevant invariants — the Researcher needs these to do coverage probes and flag invariant-violating patterns).
  - `GIT_ROOT`.
  - The 5-step research checklist as its prompt (vocab grep, entry-point enum, dead-integration check, integration-seam detection, test coverage probe).

  Each Researcher returns a structured JSON/markdown blob: `{workstream, files_touched, entry_points, suspected_unwired[], integration_seams[], coverage_gaps[], notes}`. No file writes — pure research output.

  Model: `claude-sonnet-4-6`. Reasoning load is low; the work is grep + file enumeration + counting, not architectural judgment.

- [ ] **4c. Phase C → ROOT, inline.** ROOT collects all Researcher outputs, merges integration seams across workstreams (seams that appear in multiple Researchers' output are the real cross-slice coordination points), runs the Quality Checks (DAG-ness, Slice Independence, every risk has a mitigation, every child has a Behavioral Question or is marked NEEDS HUMAN INPUT), then writes `index.md` and `child-<N>-<slug>.md` files directly. Inherited Intent blocks are populated by ROOT using slice-relevance filtering against `intent-compressed.md`.

  Rationale for keeping Phase C on ROOT (not a separate Sonnet writer): ROOT already has the intent doc, Sub-phase 1 scan, Phase A working notes, and the Researcher outputs all in context by this point. A separate writer subagent would pay a cold-start to re-load a subset of that. The writing itself is cheap output — it's the context assembly that was expensive, and ROOT has already paid for it.

- [ ] **4d. Kill the post-decomposer improvisation gap in the skill.** Add explicit text between Step 3 and Step 4:

  > The Researchers' outputs and the artifacts ROOT wrote from them are authoritative. Do not re-read `index.md` or sample child drafts to "verify" before Step 4 — the Quality Checks already ran inline as part of Phase C. Proceed directly to Step 4.

  And at the Step 4 → Step 5 boundary, restate the existing "run immediately after Step 4, no questions asked" as a negative instruction addressed to ROOT: *"Do not pause for user approval between creating child issues and spawning the first Surrogate."*

- [ ] **4e. Collapse turns 6+7 of Step 4 into one Bash script.** The observed session split child-issue creation into two Bash calls (create issues, then set titles) because the skill's example uses a title-derivation step that doesn't round-trip cleanly through the `gh issue create` loop. Rewrite the Step 4 Bash example as a single heredoc'd script that derives titles from child-draft first-line headers and creates all issues in one pass.

**Phase structure change.** The analyzer's current phases are split by Decomposer spawn and Surrogate spawn. After this refactor, **DECO ceases to exist** as a phase — there is no Decomposer subagent. What used to be two phases (DECO = subagent internals, R-POST-DECO = ROOT's handling of the return) collapses into one ROOT-owned phase bracketed by the first Researcher spawn and the first Surrogate spawn. [tools/find-refine-epic-sessions.py](../find-refine-epic-sessions.py) will need its `classify_subagent` updated: Decomposer label goes away, new `researcher` label appears, and `compute_phase_boundaries` uses first-Researcher-spawn where it used first-Decomposer-spawn.

**Expected impact**

Rough math against session 236. Current DECO phase cost the session **$26.77** (the Decomposer subagent's internal turns across the 12-session sample — biggest single phase in the pipeline). Current R-POST-DECO on 236 was **$2.51** (the 9 ROOT turns after it returned). Those two phases **merge into a single ROOT-owned phase** after the refactor:

| Component | Before | After |
|---|---|---|
| DECO subagent internals (Phase A + B + C, Opus) | ~$2–3 on session 236 (share of the $26.77 across 12 sessions) | — (phase no longer exists) |
| ROOT turn 1 — spawn Decomposer | $0.47 | — |
| ROOT turn 2 — redundant "decomposer running" text | $0.24 | — (drop, per 4d) |
| ROOT turns 3–5 — ls + Read index + Read child | $0.72 | — (drop, per 4d) |
| ROOT turn 8 — TodoWrite | $0.25 | — (drop, per #3) |
| ROOT turn 9 — unprescribed pause for approval | $0.34 | — (drop, per 4d) |
| ROOT Phase A inline (1 turn reasoning, no tools) | — | ~$0.13 (cache replay only) |
| Parallel Researcher spawns (N≈4, Sonnet, 1 wall-clock slot) | — | ~$0.40 total |
| ROOT Phase C inline (merge + quality checks + write artifacts, ~2–3 turns) | — | ~$0.60 |
| Step 4 issue creation (1 Bash instead of 2, per 4e) | $0.49 (2 turns) | $0.25 (1 turn) |
| **Combined phase total** | **~$4.50–5.50** on session 236 | **~$1.40** |

**Net: ~$3–4 saved per epic.** At 12 epics/week: **~$36–48/week**. Still the largest single-phase win in the list.

The savings come from three places: (1) Opus → Sonnet for the mechanical per-workstream research work, (2) work that was happening twice (Sub-phase 1 scan in Step 2, then Decomposer's Phase A/B re-doing the same shape of scan in Step 3) now only happens once, (3) ROOT's improvised post-return ceremony (turns 2–5, 8–9) is eliminated by making the skill tell ROOT what to do after the research returns.

Secondary benefit: wall-clock. The Decomposer takes ~7 minutes serially on 236. Running 4 Researchers in parallel cuts that to whatever the slowest workstream takes — probably ~2 minutes. User gets their decomposition review ~5 minutes sooner.

**Risks**

1. **Cross-workstream integration seams.** A seam is defined as "a file or component that multiple workstreams will need to modify." In the current single-Decomposer design, one agent sees all workstreams and can spot seams. With N parallel Researchers, each sees only its own workstream — no individual Researcher can flag a seam. Mitigation: ROOT's Phase C merge step detects seams by intersecting `files_touched` across Researcher outputs. Any file that appears in ≥2 Researchers' lists is a seam candidate, surfaced in the `index.md` Integration Seams table with the slices that touched it. This is actually *more reliable* than the current approach because it's mechanical, not judgment-based.
2. **Workstream boundary errors in Phase A propagate.** If ROOT splits workstreams wrongly in 4a, the Researchers waste effort. Mitigation: keep workstream identification in Phase A deliberately coarse (3–6 workstreams max, by primary system boundary — data, API, CLI, frontend, jobs, infra). The 5-step checklist is robust to slightly-wrong boundaries because the dead-integration check and seam detection both operate on symbol names, not workstream scope.
3. **Sonnet may miss subtleties an Opus Decomposer would catch.** The 5-step checklist is deliberately mechanical. Sonnet is appropriate for grep + count + list. Architectural judgment (is this a real slice? does it deserve its own child issue?) stays on ROOT in Phase A.
4. **Parallel spawn output volume in one ROOT response.** Spawning 4 subagents in one response inflates ROOT's output tokens for that turn. This is still cheaper than serializing 4 turns × ~$0.13 cache replay each.

**Acceptance check.** On a fresh `/refine-epic` invocation:
- R-POST-DECO ROOT turn count drops from 9 → ~5 (Phase A reasoning, parallel Researcher spawn, Phase C writes (1–2 turns), Step 4 create-issues Bash, move-to-Step-5 line).
- Researcher subagents appear in [find-refine-epic-sessions.py](../find-refine-epic-sessions.py) output as a new phase; combined cost should be <$0.50.
- No `TodoWrite` call between Decomposer-equivalent work and Step 5 spawn.
- `index.md` Integration Seams table is populated mechanically from ROOT's merge step, not from a single-agent's judgment call.

---

## 5. Forbid surrogate batching — one Agent spawn per child, no batching

Evidence base: session `dc36844a` (issue #887, `hyang0129/video_agent_long`).

**Problem.** The skill says *"For each child issue, spawn a dedicated Surrogate agent. Do not start the next child until the current one completes."* On the 887 session, ROOT violated this: it spawned a **single** surrogate (`description: "Step 5 — 15-way surrogate refinement"`) and passed all 15 children into one continuous agent context. The skill instruction is grammatically clear but doesn't explicitly forbid batching, and ROOT "helpfully" consolidated 15 spawns into 1.

Cost consequence: in a single-agent serial run, every turn re-reads the full accumulated context. By child 12 the cache context was 125K tokens; by child 14 it peaked at 166K. Total cache reads: **29.8M tokens across 370 turns**, vs. a predicted ~6M if 15 separate agents had each started fresh (~20 turns × ~40K avg context × 15). At Sonnet rates ($0.30/1M cache read) that's ~$8.95 of replay vs. ~$1.80 — a **$7.15 waste on this session alone**.

This is the largest single observed deviation from expected cost in the 12-session dataset. SURR is usually cheap ($0.35/session average excluding 887). Session 887 alone accounts for **71% of all SURR cost** across all 12 sessions.

**Why ROOT batched.** The skill says "spawn a dedicated Surrogate agent" per child but doesn't say "one Agent tool call per child." With 15 children, ROOT reasoned that one subagent handling 15 serial `/refine-issue` calls is equivalent to 15 subagents — which it isn't, because context isolation is lost and the quadratic replay penalty kicks in.

**Proposed actions**

- [ ] **5a. Make the spawn instruction unambiguous.** Rewrite the Step 5 spawn paragraph:

  > For each child issue, emit one `Agent` tool call. Do NOT batch multiple children into one agent — each surrogate must start with a fresh context. With N children, ROOT emits N separate `Agent` calls, waiting for each to complete before emitting the next (surrogates are serial because a later child may be out of scope for an earlier one's escalation, not because they share state).

- [ ] **5b. Name the batching failure mode explicitly.** Add a Constraints bullet:

  > Do not describe a single subagent as a "multi-way" or "N-way" surrogate. One subagent = one child issue. A subagent that processes multiple children in sequence is a correctness bug: escalations from child N pollute child N+1's context, and the quadratic cache-growth penalty makes it 3–5× more expensive than intended.

- [ ] **5c. Consider parallelizing surrogates (future).** The skill currently serializes surrogates because "a later child may reference an earlier one's escalations." In practice, escalations are logged and surfaced to the user at the end — they don't need to feed back into subsequent surrogates during the run. If escalation cross-contamination is not a real concern, surrogates could be parallelized (N Agent calls emitted in one ROOT turn), cutting wall-clock time from O(N) to O(1) and removing any temptation to batch. Deferred until confirmed safe.

**Expected impact.** SURR cost on a typical 6-child epic: ~$0.80 (6 × ~$0.13/surrogate at correct per-child context). SURR cost on a 15-child epic at correct shape: ~$2.00. Actual observed on 887: $9.37. **Fix restores ~$7/epic for large epics, ~$0 for small ones** (small epics like 3–4 children don't have enough scale for the quadratic penalty to bite).

**Risk.** None from the skill-text change. The instruction gets stricter, not looser. The only behavior it disallows is the incorrect batching.

**Acceptance check.** On a fresh `/refine-epic` with N ≥ 6 children:
- Subagent count in session directory = N surrogate agents + 3 Challengers + Researchers + any other helpers.
- No subagent description contains "N-way" or "multi-way" or a number before "surrogate."
- SURR cost ≤ N × $0.20 (generous upper bound per surrogate on Sonnet).

