# Constitution Template

Reference schema for `CONSTITUTION.md` files produced by the `/refine-constitution`
skill. Consumed by: entry point (state detection), refinement subskill (resume logic),
amendment subskill (regression detection), and any downstream tool that checks a
repo's constitution for completeness.

---

## File location convention

Default: `CONSTITUTION.md` at the repository root.

Override: pass an explicit path as the first argument to `/refine-constitution`.
The skill reads and writes that path for the entire session.

---

## Output schema

A complete `CONSTITUTION.md` has these top-level sections in this order:

```
# <Project Name> — Constitution

## Thesis

## Laws

## Rejected Alternatives

## Corollaries          ← optional

## Review Heuristic

## Demoted-to-Convention Log   ← amendment artifact, optional
```

### Thesis (required)

One paragraph. A positioning claim — what this project *is* and what matters in it,
not a description of what it does. Must distinguish what is the product from what is
the delivery surface.

### Laws (required, 3–10, ordered by precedence)

Numbered `## Law N — <Stance>`. Ordered from most to least fundamental. When two laws
conflict, the earlier one wins. The ordering is an explicit precedence statement.

Hard cap: 10. Adding law N+1 when N=10 requires demoting or retiring an existing law
first.

### Rejected Alternatives (required)

A flat list of whole-project design choices that were evaluated and rejected. One line
per entry: what + one-sentence reason rejected or delegated. Not the same as the
per-law Rejected Alternative field — this section covers decisions wider than any
single law.

### Corollaries (optional)

Non-obvious decisions that emerge when **two or more laws acting together** force a
call neither law makes alone. A corollary is a mini constitutional ruling: given
these principles, in this class of situation, here is the call we make and what we
give up to make it. If a single law is sufficient to motivate the statement, it is
not a corollary — it belongs in that law's anti-pattern or rejected-alternative
section. An empty Corollaries section is acceptable and often correct.

Format:

```
**Corollary N+M.K** — <one-sentence statement of the call>

- **Derived from:** Law N + Law M (+ Law … if applicable; minimum 2)
- **Tension:** <one sentence — what these laws each pull toward in this concrete decision class>
- **Stance:** <which law wins this decision and the concrete behavior that follows>
- **Anti-corollary:** <the coherent opposite call, framed positively, naming what it would gain (which failure mode it avoids) and what it would cost (which failure mode it accepts)>
```

Numbering: `N+M.K` makes the multi-law derivation visible at a glance — e.g.
`Corollary 1+4.1` is the first corollary derived from the Law 1 / Law 4 pair. If
three laws are involved use `N+M+P.K`.

**Admission gate.** A corollary may be written to this section only if all four
conditions hold:

1. **Multi-law derivation:** ≥2 distinct laws cited in `Derived from`.
2. **Concrete decision class:** `Tension` names a specific situation (schema
   migration vs. rebuild, sync vs. async, eager vs. lazy, fail-loud vs. degrade,
   etc.) — not "in general" or "in principle".
3. **Stance is contested:** the `Anti-corollary` is a coherent opposite call
   argued on the constitution's own terms, not a strawman ("the opposite is:
   ignore Law N" is not an anti-corollary, it is a law violation).
4. **Net-new content:** not equivalent to anything already in either source law's
   anti-pattern or rejected-alternative section.

Failing the gate means the candidate is dropped, not patched.

### Review Heuristic (optional but high-value)

An ordered checklist of questions for PR review. Format:

```
1. Does this satisfy Law 1 (<Stance summary>)?
2. Does this satisfy Law 2 (<Stance summary>)?
…
N. Does this satisfy Law N (<Stance summary>)?

If any answer is "no or unclear", the feature requires redesign — not a carve-out.
```

### Demoted-to-Convention Log (amendment artifact, optional)

Populated only by the amendment subskill when a law is demoted. Preserves history so
future readers understand that a convention in `CLAUDE.md` was once a law.

```
- **Law <former number> — <Stance>**: demoted <YYYY-MM-DD>. Reason: <one sentence>.
  Moved to: CLAUDE.md § <section>.
```

---

## Per-law schema

Each law block:

```markdown
## Law N — <Stance>

**Why:** <1–3 sentences describing failure in the world if this law is violated.
Not failure in the code — failure observable by a user, downstream consumer, or
in an incident. Concrete enough that a future agent can apply it to a case the
law didn't explicitly cover.>

**Rejected Alternative:** <The specific other design the author considered and
why this project does not take it. Names the alternative explicitly.>

**Anti-pattern:** <The concrete thing the code would do if this law were violated.
Specific enough to be checkable in a PR review. Not "bad X" — the actual shape of
the violation.>

**Scope:** <Optional. The subsystems or boundaries this law governs. Omit if
repo-wide with no carve-outs.>

**Detector:** <Optional. A grep pattern, file glob, or AST query that matches
candidate violations. A law without a detector is valid — some laws require
reasoning, not pattern matching.>
```

### Law heading variants

| Heading form | Meaning |
|---|---|
| `## Law N — <Stance>` | Complete, challenged law |
| `## [DRAFT] Law N — <Stance>` | At least one element is a marker; not yet complete |
| `## Law N — <Stance> [UNCHALLENGED]` | Drafted but challenger subagents not yet run |
| `## [DRAFT] Law N — <Stance> [UNCHALLENGED]` | Both conditions apply |

---

## Marker grammar

Markers are load-bearing tokens parsed by the refinement subskill's resume logic.
**Do not alter their spelling.** Parsers match them literally.

### Element-level markers

Appear as the value of a field when that field's content has not yet been produced.

| Marker | Field it replaces | Cleared when |
|---|---|---|
| `[NEEDS WHY]` | **Why** value | Author produces a concrete failure-in-the-world Why |
| `[NEEDS REJECTED-ALT]` | **Rejected Alternative** value | Author names the alternative and rejection reason |
| `[NEEDS ANTI-PATTERN]` | **Anti-pattern** value | Author produces a concrete, checkable violation shape |

Example usage:

```markdown
**Why:** [NEEDS WHY]
**Rejected Alternative:** [NEEDS REJECTED-ALT]
**Anti-pattern:** [NEEDS ANTI-PATTERN]
```

### Law-level markers

Appear as a prefix or suffix on the law heading.

| Marker | Position | Meaning | Cleared when |
|---|---|---|---|
| `[DRAFT]` | Prefix on heading | Law has at least one element marker | All element markers in the law are cleared |
| `[UNCHALLENGED]` | Suffix on heading | Law has been drafted but challenger subagents have not been run against it | Challenger pass completes for this law |

The `[DRAFT]` prefix is added automatically when any element marker is written into
a law. It is removed automatically when all element markers in that law are cleared.

### Law-body replacement markers

Replace the entire body of a law (all fields below the heading).

| Marker | Form | Meaning |
|---|---|---|
| `[DEFERRED — <reason>]` | Standalone line | Law was deferred because the Why could not be produced. Not revisited unless the user brings new evidence. The `<reason>` is a one-sentence note from the session when the law was deferred. |

Example:

```markdown
## [DRAFT] Law 3 — All state mutations route through the command bus

[DEFERRED — author could not produce a concrete failure mode; revisit after next incident involving race condition on optimistic update]
```

### Document-level markers

Appear as the content of an entire required section when that section is absent or
empty.

| Marker | Where it appears | Meaning |
|---|---|---|
| `[MISSING]` | In place of a required section's content | The section heading is present but content has not been produced. Used for Rejected Alternatives and Review Heuristic. |

Example:

```markdown
## Rejected Alternatives

[MISSING]
```

---

## Completeness rule

A constitution is **complete** if and only if ALL of the following hold:

1. Zero markers anywhere in the file (`[DRAFT]`, `[NEEDS WHY]`, `[NEEDS REJECTED-ALT]`,
   `[NEEDS ANTI-PATTERN]`, `[DEFERRED — …]`, `[UNCHALLENGED]`, `[MISSING]`).
2. Thesis section is present and non-empty.
3. Laws section contains ≥3 and ≤10 numbered laws.
4. Every law has all four required elements present and non-empty: Why, Rejected
   Alternative, Anti-pattern, Stance (already in heading).
5. Rejected Alternatives section is present with ≥1 entry.
6. Review Heuristic section is present and non-empty.

**Complete** is the routing signal the entry point uses to dispatch to amendment mode
rather than refinement mode. An incomplete constitution with no markers (e.g., law
count < 3, or Rejected Alternatives section absent entirely) routes to refinement.

---

## Worked example

### Well-formed law

```markdown
## Law 1 — Surface only edges with statically provable targets; never emit scored or uncertain edges

**Why:** An agent that trusts a wrong edge wastes more time than one that falls back
to grep. In practice, agents round 0.7 confidence to 1.0 — they do not calibrate to
edge scores. A graph of definite edges with silent false negatives is strictly more
trustworthy for agent consumption than a graph of scored edges treated as certain.

**Rejected Alternative:** Confidence-scored edges with a caller-controlled threshold
(the approach taken by Sourcegraph and most IDE "find usages" features). Rejected
because this project's consumers are agents, not developers — agents cannot use
threshold calibration, they just act. The scored approach shifts the cost of a wrong
edge from "we didn't emit it" to "the agent took a wrong action and the user debugged
it for 20 minutes."

**Anti-pattern:** Emitting a `getattr`-dispatched call as an edge in the graph because
the dispatch target is "probably" the method of that name on that class. Emitting any
edge for which the target cannot be proven by static analysis.

**Scope:** Graph construction only (`analyzer/`, `graph/`). The MCP layer that queries
the graph is not governed by this law — it may return partial results with a
`confidence` annotation for display purposes.

**Detector:** `grep -r "confidence" analyzer/ graph/` — any use of a confidence score
in graph construction is a candidate violation.
```

### Draft law with markers

```markdown
## [DRAFT] Law 3 — All LLM calls route through the single provider abstraction [UNCHALLENGED]

**Why:** [NEEDS WHY]

**Rejected Alternative:** [NEEDS REJECTED-ALT]

**Anti-pattern:** Calling an LLM SDK method directly from a feature module rather
than through the provider abstraction layer.

**Scope:** All modules under `src/` that initiate LLM calls.
```

In this example: the law has a usable Anti-pattern but is missing Why and Rejected
Alternative. The `[DRAFT]` prefix reflects the presence of element markers. The
`[UNCHALLENGED]` suffix reflects that the challenger subagents have not yet been run.
Refinement mode will target `[NEEDS WHY]` and `[NEEDS REJECTED-ALT]` in separate
elicitation passes.

---

## Mini constitution schema

`CONSTITUTION.mini.md` is a derived artifact — auto-generated from `CONSTITUTION.md`
whenever the master is written in a complete state (zero markers). Never edit it
directly. If the master has markers remaining after a session, skip mini generation
(or delete an existing stale mini).

**Purpose:** agent injection. The full constitution is 1,500–2,500 words; agents
competing with code and issue context for attention window cannot reliably adhere to
it. The mini strips everything except what an agent needs to *check* code against a
law: the stance, the anti-pattern (concrete violation shape), and the detector (grep
pattern, where present). The Why and Rejected Alternative live in the master for
human authoring and edge-case reasoning; they do not belong in the injection target.

### Mini schema

```markdown
# <Project Name> — Constitution (Mini)
<!-- Auto-derived from CONSTITUTION.md — do not edit directly -->

**Thesis:** <first sentence of thesis paragraph only>

## Laws

### Law 1 — <Stance verbatim from Law 1 heading>
**Anti-pattern:** <Anti-pattern field verbatim>
**Detector:** `<Detector field>` ← omit this line entirely if no Detector is defined

### Law 2 — <Stance verbatim from Law 2 heading>
**Anti-pattern:** <Anti-pattern field verbatim>

... (one block per law, same structure)

---

If any proposed change violates a law above: redesign required — not a carve-out.
```

### Generation rules

1. Copy the stance from each law heading exactly (strip `[DRAFT]` / `[UNCHALLENGED]`
   markers if somehow present — but mini is only generated when those are absent).
2. Copy the Anti-pattern field verbatim. Do not summarize or shorten.
3. Copy the Detector field verbatim if present. Omit the `**Detector:**` line
   entirely if the law has no Detector.
4. Omit Why, Rejected Alternative, Scope, and all other fields.
5. Omit Corollaries, Rejected Alternatives section, Review Heuristic, and
   Demoted-to-Convention Log.
6. Thesis: first sentence only (up to and including the first period).
7. The closing line (`If any proposed change…`) is fixed — do not alter it.
