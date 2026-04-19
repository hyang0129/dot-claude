# Surrogate Q&A Process Analysis
## /refine-epic Session: hyang0129/onlycodes#62
### Issues #69–75 | 2026-04-17

---

## Executive Summary

Across all 7 child issues, **no genuine back-and-forth Q&A occurred** between the refine-issue
Intent Interviewer and the surrogate. In every case the surrogate collapsed the Intent Interview
into a single self-directed monologue — posing questions to itself and answering them immediately
from the epic intent documents, without pausing for an external turn. The refine-issue skill, as
currently implemented, never prompted the surrogate with a question; it ran inline and the
surrogate pre-empted the interview loop entirely.

Despite this structural bypass, **output quality was consistently high**: answers were specific,
grounded in ADR citations, and backed by real codebase exploration. Genuine gaps in issue bodies
were surfaced in 5 of 7 issues.

---

## Per-Issue Findings

### Issue #69 — Add characterization tests for existing analyze summary behavior

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — single monologue in record 26 |
| Questions posed | 5 self-posed (outcome, hidden scope, acceptance, constraints, motivation) |
| Answer grounding | Grounded; one addition (empty-results-dir scenario) was a reasonable inference |
| Escalations | None |

**Gaps surfaced:**
- No `tests/fixtures/` directory exists — must be created from scratch
- `tabulate` is present in venv, affects which golden file is primary
- No `conftest.py` at repo root — "autouse guard" must be added
- Added 5th scenario (empty results directory) not in original issue

**Assessment:** Specific and grounded. Empty-results-dir addition was inferred, not fabricated — confirmed by codebase read.

---

### Issue #70 — Refactor analyze.py → analyze/ package (atomic rename)

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — self-interview in a single turn |
| Questions posed | 5 (coexistence rule, `__pycache__` risk, test updates, smoke test scope, byte-identical output) |
| Answer grounding | 4/5 from epic docs; 1 (cli.py import) deferred to codebase read and verified |
| Escalations | None |

**Gaps surfaced:**
- `swebench/__init__.py` and `__main__.py` only reference `analyze` in docstrings — `cli.py` is the sole live call site, narrowing the change surface
- The `__pycache__` stale-pyc risk and required PR-description note were elevated from epic docs to explicit acceptance criteria

**Assessment:** The deferral of Q4 (cli.py import) to a codebase read rather than assuming was the right call — highest-quality answer in the set.

---

### Issue #71 — Stage 1 extractor (analyze/extractor.py + fixtures)

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — 4-round self-interview in one turn |
| Questions posed | 4 (return type, A-vs-C fixture, triage formula, `count_turns` export contract) |
| Answer grounding | 3/4 from ADR; triage weighting formula was partially inferred (not in epic docs) |
| Escalations | None |

**Gaps surfaced:**
- A-vs-C synthetic fixture entirely absent from issue acceptance criteria — added
- `count_turns`/`TURN_DEFINITION` must be public module exports (implied but not stated)
- `result.num_turns` anti-pattern empirically confirmed: django__django-11964 showed `result.num_turns=12` vs `count_turns()=11` — a real discrepancy caught by codebase read
- 3 open questions left for implementer: ARM_CRASH detection, Jaccard format, triage weights

**Assessment:** Best codebase research of the 7 — empirical confirmation of the turn-counting discrepancy was a genuine find, not a paperwork exercise.

---

### Issue #72 — Stage 2a log compressor (analyze/compress.py)

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — surrogate pre-empted interviewer after reading codebase (lines 19–34) |
| Questions posed | 5 (mapped to standard refine-issue probe dimensions) |
| Answer grounding | Grounded; two-level JSON nesting verified against real smoketest logs |
| Escalations | None |

**Gaps surfaced:**
- `result` records must be preserved — original issue was silent on this
- Confirmed two-level nesting pattern (`tool_result` → `content[].text` JSON string) from real logs
- No CLI surface for compress.py — deferred to #73 (explicit now, was implicit)
- Test coverage threshold (≥85%) was not in the issue

**Assessment:** The pre-read of smoketest JSONL before writing answers was the right move — the two-level nesting detail would have been easy to get wrong from docs alone.

---

### Issue #73 — Stage 2b runner (analyze/run.py + subagent prompt + CLI skeleton)

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — self-answered all probe dimensions in message [17] |
| Questions posed | 5 (standard probe dimensions from refine-issue instructions) |
| Answer grounding | Strongly grounded; answers quote exact ADR string literals verbatim |
| Escalations | None |

**Gaps surfaced:**
- `analyze.py` must be refactored from `click.command` → `click.group` — not in issue body
- `run_meta.json` write-on-every-run requirement was in ADR but absent from acceptance criteria
- `--output-dir` and `--run-id` flags missing from issue's AC bullets
- 3 open questions for implementer: behavior of existing `analyze summary` during group refactor, `--results-dir` default, exact dry-run output format

**Assessment:** Highest verbatim precision — quoted exact retry error string literal from the ADR. The Click-group refactor gap was a genuine find from codebase inspection.

---

### Issue #74 — Stage 3 synthesizer + registry.py + seed patterns.json

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — collapsed to solo monologue at line 17; wrote INTENT file unilaterally |
| Questions posed | None explicitly posed; resolved ADR decisions Q2/Q3/Q5 internally |
| Answer grounding | ADR-grounded for all contract details; two codebase findings came from `git ls-tree` |
| Escalations | None |

**Gaps surfaced:**
- `analyze.py` flat file must NOT be replaced (original issue didn't say this)
- `swebench/analyze/` package doesn't exist yet — implementer must branch from #73's delivery branch
- `load_patterns` returns `(None, error_msg)` on malformed JSON — explicit crash-recovery contract not in issue

**Assessment:** Good, but weakest process fidelity: no Q&A trace at all, making it hard to audit which decision came from which source. Output quality high despite this.

---

### Issue #75 — Docs: update CLAUDE.md with analyze pathology + patterns.json

| Dimension | Finding |
|---|---|
| Back-and-forth? | No — surrogate concluded "no questions needed" at record 14 before interview started |
| Questions posed | None — process went straight to writing |
| Answer grounding | Entirely from system-prompt context (verbatim flag list, schema, constraints) |
| Escalations | None |

**Gaps surfaced:**
- `.gitignore` covers all of `results_swebench/` — implementer must confirm `patterns.json` at repo root is still tracked
- Flag names/defaults must be re-confirmed once #74 lands (package doesn't exist yet)

**Assessment:** The surrogate functioned as a pass-through transcriber. The system prompt held the complete answer set; the surrogate added nothing new. Shortest and least interesting of the 7.

---

## Cross-Cutting Patterns

### 1. The Intent Interview Was Universally Bypassed

In all 7 sessions, the surrogate collapsed the intent interview into a single monologue turn rather
than waiting for the refine-issue skill to ask questions one at a time. This is a structural
consequence of how the skill runs — it's inlined, not a separate agent, so the surrogate sees the
full skill instructions up front and self-directs the interview. The "surrogate answers questions"
flow was never exercised as an interactive turn-based exchange.

### 2. Codebase Research Mattered More Than the Interview

The most valuable findings in every session came from the **Spec agent's codebase exploration**,
not from the Q&A. The turn-counting discrepancy in #71, the two-level nesting pattern in #72,
the Click-group refactor requirement in #73, and the `analyze.py`-must-not-be-replaced constraint
in #74 were all discovered by reading actual code — not by answering interview questions.

### 3. Epic Doc Density Determined Interview Depth

Sessions where the surrogate's system prompt had dense, specific ADR content (#73, #70, #74) had
the most grounded answers and fewest open questions. Sessions with thinner epic coverage (#75)
produced pass-through transcription. The surrogate's value-add was proportional to how much
interpretation the epic docs required.

### 4. Escalations: 0/7

No question was escalated to a human across any of the 7 sessions. This is either a sign the epic
was extremely well-specified, or that the surrogate preferred to infer rather than flag uncertainty.
The #71 triage-weighting inference (not in epic docs) leans toward the latter.

### 5. Three Open Questions Surfaced (Not Escalations)

Issues #71 and #73 produced a total of 6 open questions posted to the spec for the implementer
to resolve before coding. These are the only cases where the process acknowledged genuine
under-specification in the epic docs. They represent the real output of the Q&A process.

---

## Implications

**For the surrogate design:** The current approach works but the "question-answering" framing is
somewhat misleading — the surrogate doesn't answer questions, it synthesizes a spec from docs and
codebase research. If genuine interactive Q&A is desired, the Intent Interviewer would need to
run as a separate agent that pauses and sends questions to the surrogate via `AskUserQuestion`.

**For epic quality:** The 6 open questions across #71/#73, and the 0 escalations, suggest the epic
ADR docs are dense enough to cover most decisions but leave implementation details (weighting
formulas, CLI refactor mechanics) under-specified. These are the right things to leave open.

**For /refine-issue improvement:** The most reliable gap-finder was codebase research, not the
interview. The skill already mandates Phase A surface-area research — that's doing the heavy lifting.
The intent interview adds value primarily by forcing the surrogate to articulate the "why" before
the "what."

---

*Generated 2026-04-17 from 7 subagent transcript reviews of session e729024f.*
