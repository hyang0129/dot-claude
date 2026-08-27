# Doctrine Template

Reference schema for `DOCTRINE.md` files produced by the `/refine-doctrine` skill.
Consumed by: entry point (state detection), refinement subskill (resume logic),
amendment subskill (regression detection), and any downstream tool that checks a
repo's doctrine for completeness.

---

## File location convention

Default: `DOCTRINE.md` at the repository root, alongside `CONSTITUTION.md`.

Override: pass an explicit path as the first argument to `/refine-doctrine`.
The skill reads and writes that path for the entire session.

---

## Output schema

A complete `DOCTRINE.md` has these top-level sections in this order:

```
# <Project Name> — Doctrine

## Preamble

## Standing Orders

## Retired Orders          ← amendment artifact, append-only

## Promoted-to-Law Log     ← amendment artifact, append-only
```

### Preamble (required)

One paragraph. States that this is the tech-bound layer of the project's governance
stack — rules here serve constitutional laws under current technology and will retire
when their assumptions stop holding. Names the constitution it anchors to. A useful
Preamble distinguishes what makes a rule doctrine (contingent on tech) from what would
make it a law (eternal given the project's purpose).

### Standing Orders (required, ≥1)

Each order governs a class of decisions that current technology forces, anchored to a
constitutional law. When the tech assumption stops holding, the order retires.

Hard guidance: 3–8 orders is the productive range. More than 10 is a signal that the
orders are conventions, not doctrine.

### Retired Orders (append-only)

Populated only when a Sunset Trigger fires or an amendment retires an order. Never
delete entries — the log preserves the reasoning for future contributors who would
otherwise re-propose the same rule.

### Promoted-to-Law Log (append-only)

Populated only when a Standing Order turns out to be eternal and is handed off to the
constitution. Never delete entries — a tombstone here and a forward pointer to the
constitution law it became.

---

## Per-order schema

Each Standing Order block:

```markdown
**Order N** — <one-sentence rule>

- **Anchor:** Law M (<stance summary>) [+ Law K (<stance summary>) if multi-anchor]
- **Tech Assumption:** <observable technological condition that makes this rule necessary>
- **Sunset Trigger:** <observable condition that retires this rule>
- **Anti-pattern:** <concrete violation shape, checkable in PR review>
- **Scope:** <optional — subsystem or surface this governs>
- **Detector:** <optional — grep pattern, file glob, or AST query for candidate violations>
```

### Field descriptions

**Order N — rule** (required): The rule stated as an imperative sentence. Present
tense. Specific enough that a reader can picture a code-level violation. Not "avoid
X" but "never do X when Y," or "always route X through Y when Z." The sentence
must be falsifiable — a PR reviewer should be able to determine whether a change
violates it.

**Anchor** (required): Which constitutional law or laws currently force this rule to
exist. Format: `Law N (<one-phrase stance summary>)`. If two laws together force the
rule, list both. The Anchor field is doctrine's load-bearing coupling to the
constitution — an Order without a valid Anchor is convention masquerading as doctrine.

**Tech Assumption** (required): The observable technological condition that makes this
rule necessary *right now*. Must be checkable: a reader should be able to look at the
current state of the technology and determine whether the assumption still holds.
"Current LLMs cannot reliably maintain state across tool calls" is observable.
"AI is still immature" is not. If the assumption cannot be checked by inspection of a
measurable condition, it fails.

**Sunset Trigger** (required): The observable condition that, when it fires, retires
this Order. Must be falsifiable — a reader should be able to check whether it has
fired. "When context window limits exceed 1M tokens at production pricing" is
falsifiable. "When the technology matures" is not. A trigger that cannot be checked
is not a trigger — it is a wish.

**Anti-pattern** (required): The concrete thing that code would do if this Order were
violated. Specific enough to be checkable in a PR review. Not "bad X" but the actual
shape of the violation: which file, which function call, which data structure. If a PR
reviewer cannot tell from the Anti-pattern whether a diff violates the Order, the
Anti-pattern is too vague.

**Scope** (optional): The subsystem, surface, or file boundary this Order governs.
Omit if it applies uniformly across the codebase with no carve-outs. Do not invent a
scope to fill a blank.

**Detector** (optional): A grep pattern, file glob, or AST query that matches candidate
violations. An Order without a Detector is valid — some orders require reasoning, not
pattern matching.

---

### Order heading variants

| Heading form | Meaning |
|---|---|
| `**Order N** — <rule>` | Complete, challenged order |
| `**[DRAFT] Order N** — <rule>` | At least one element is a marker; not yet complete |
| `**Order N** — <rule> [UNCHALLENGED]` | Drafted but challenger subagents not yet run |
| `**[DRAFT] Order N** — <rule> [UNCHALLENGED]` | Both conditions apply |

---

## Marker grammar

Markers are load-bearing tokens parsed by the refinement subskill's resume logic.
**Do not alter their spelling.** Parsers match them literally.

### Element-level markers

Appear as the value of a field when that field's content has not yet been produced.

| Marker | Field it replaces | Cleared when |
|---|---|---|
| `[NEEDS ANCHOR]` | **Anchor** value | Author references a valid law from CONSTITUTION_LAWS |
| `[NEEDS ASSUMPTION]` | **Tech Assumption** value | Author produces an observable, checkable condition |
| `[NEEDS SUNSET]` | **Sunset Trigger** value | Author produces a falsifiable trigger condition |
| `[NEEDS ANTI-PATTERN]` | **Anti-pattern** value | Author produces a concrete, checkable violation shape |

Example usage:

```markdown
**Order 2** — [DRAFT] Never call an LLM provider SDK directly from feature modules

- **Anchor:** [NEEDS ANCHOR]
- **Tech Assumption:** [NEEDS ASSUMPTION]
- **Sunset Trigger:** [NEEDS SUNSET]
- **Anti-pattern:** Calling `openai.chat.completions.create()` from a file outside
  the provider abstraction layer.
```

### Order-level markers

| Marker | Position | Meaning | Cleared when |
|---|---|---|---|
| `[DRAFT]` | Prefix inside heading | Order has at least one element marker | All element markers in the order are cleared |
| `[UNCHALLENGED]` | Suffix on heading | Order has been drafted but challenger subagents not yet run | Challenger pass completes for this order |
| `[STALE]` | Suffix on heading | Sunset trigger condition appears to have fired; order needs retirement review | User confirms the order is retired or that the condition has not fired |

The `[DRAFT]` prefix is added automatically when any element marker is written.
It is removed automatically when all element markers in that order are cleared.

The `[STALE]` marker is set by the refinement subskill when the Sunset Trigger
references a condition the subskill can detect has fired (e.g., a date-based trigger
that has passed, or a tech condition the user reports as changed). It is not set
automatically — it requires either user input or a research subagent finding.

### Document-level markers

| Marker | Where it appears | Meaning |
|---|---|---|
| `[MISSING]` | In place of a required section's content | The section heading is present but content has not been produced. Used for Preamble and Standing Orders. |

---

## Retired Orders log format

```markdown
## Retired Orders

- **Order <former number> — <rule verbatim>**: retired <YYYY-MM-DD>.
  Reason: <one sentence — which sunset trigger fired or which amendment retired it>.
  Original anchor: Law N (<stance summary>).
  Original tech assumption: <verbatim>.
```

Entries are append-only. Renumbering remaining active orders does not affect the log.

---

## Promoted-to-Law Log format

```markdown
## Promoted-to-Law Log

- **Order <former number> — <rule verbatim>**: promoted <YYYY-MM-DD>.
  Reason: <one sentence — why this turned out to be eternal, not tech-bound>.
  Became: Law N in CONSTITUTION.md (<date constitution was updated>).
  Note: run `/refine-constitution --force-amendment` Subpath A to ratify.
```

Entries are append-only. The log is a handoff record — the actual law lives in
`CONSTITUTION.md` after the user runs `/refine-constitution`.

---

## Contestedness filter (the doctrine key filter)

This filter is the analogue of the constitution's load-bearing test, but inverted.

**Constitution filter:** "Would this still be a law if technology were perfect?"
A rule that only holds because of current tech limitations fails this test and belongs
in doctrine, not the constitution.

**Doctrine filter (inverse):** "Given current technology, is there a credible
counter-rule another competent team would adopt — a rule that anchors to the *same*
constitutional law but reaches the opposite operational conclusion because they weigh
the tech constraints differently?"

If the answer is **NO** — no competent team following the same constitution would
adopt a counter-rule — then the candidate is **not doctrine**. It is a default or
convention. Move it to `CLAUDE.md`.

Examples:

- "Always batch writes" — another team with the same law about data integrity but
  a different tech stack (row-level locking instead of eventual consistency) might
  adopt "never batch writes." Credible counter-rule exists. This is doctrine.

- "Use 4-space indentation" — no competent team following any constitution would
  adopt a rule requiring 2-space indentation based on tech constraints. This is a
  convention. It belongs in `CLAUDE.md`.

The challenger subagents enforce this filter: the Counter-rule Challenger specifically
constructs the credible counter-rule. If it cannot, the Order is demoted to
convention.

---

## Completeness rule

A doctrine is **complete** if and only if ALL of the following hold:

1. Zero markers anywhere in the file (`[DRAFT]`, `[NEEDS ANCHOR]`, `[NEEDS ASSUMPTION]`,
   `[NEEDS SUNSET]`, `[NEEDS ANTI-PATTERN]`, `[UNCHALLENGED]`, `[STALE]`, `[MISSING]`).
2. Preamble section is present and non-empty.
3. Standing Orders section contains ≥1 order.
4. Every Standing Order has all four required fields present and non-empty: Anchor,
   Tech Assumption, Sunset Trigger, Anti-pattern.
5. Every Order's Anchor references at least one law from the project's `CONSTITUTION.md`.

**Complete** is the routing signal the entry point uses to dispatch to amendment mode
rather than refinement mode. An incomplete doctrine with no markers (e.g., a Standing
Order with an empty Anchor field but no `[NEEDS ANCHOR]` tag) routes to refinement
with `NORMALIZE=true`.

---

## Worked example

### Well-formed Standing Order

```markdown
**Order 1** — Route all LLM calls through the provider abstraction; never call a vendor SDK from feature modules

- **Anchor:** Law 3 (All state mutations route through a single abstraction layer)
- **Tech Assumption:** No vendor SDK offers a stable, provider-agnostic interface at the feature-call level; switching providers requires touching call sites directly.
- **Sunset Trigger:** When a stable, provider-agnostic SDK (e.g., a ratified OpenAI-compatible standard adopted by ≥3 major providers) is available and covers ≥90% of the call patterns in this codebase.
- **Anti-pattern:** Importing `openai`, `anthropic`, or any vendor SDK in a file outside `src/providers/`. Calling `.chat.completions.create()` or equivalent from a feature module.
- **Scope:** All modules under `src/` that initiate LLM calls. The `src/providers/` directory is the boundary.
- **Detector:** `grep -r "from 'openai'" src/ --include="*.ts" | grep -v "src/providers/"`
```

### Draft order with markers

```markdown
**[DRAFT] Order 2** — Never cache embeddings across schema versions [UNCHALLENGED]

- **Anchor:** Law 1 (Surface only edges with statically provable targets)
- **Tech Assumption:** [NEEDS ASSUMPTION]
- **Sunset Trigger:** [NEEDS SUNSET]
- **Anti-pattern:** Reusing an embedding store after a schema migration without invalidating the cache.
```

In this example: the Order has a usable Anchor and Anti-pattern but is missing an
observable Tech Assumption and a falsifiable Sunset Trigger. The `[DRAFT]` prefix
reflects the presence of element markers. The `[UNCHALLENGED]` suffix reflects that
the challenger subagents have not yet been run. Refinement mode will target
`[NEEDS ASSUMPTION]` and `[NEEDS SUNSET]` in separate elicitation passes.

---

## Mini doctrine schema

`DOCTRINE.mini.md` is a derived artifact — auto-generated from `DOCTRINE.md`
whenever the master is written in a complete state (zero markers). Never edit it
directly. If the master has markers remaining after a session, skip mini generation
(or delete an existing stale mini).

**Purpose:** agent injection. The full doctrine is context-heavy; agents competing
with code and issue context for attention window cannot reliably adhere to it.
The mini strips everything except what an agent needs to *check* code against an
order: the rule, the anti-pattern (concrete violation shape), and the detector (where
present). The Anchor, Tech Assumption, Sunset Trigger, and Why context live in the
master for human authoring and edge-case reasoning.

### Mini schema

```markdown
# <Project Name> — Doctrine (Mini)
<!-- Auto-derived from DOCTRINE.md — do not edit directly -->

## Standing Orders

### Order 1 — <rule verbatim from Order 1 heading>
**Anti-pattern:** <Anti-pattern field verbatim>
**Detector:** `<Detector field>` ← omit this line entirely if no Detector is defined
**Scope:** <Scope field verbatim> ← omit this line entirely if no Scope is defined

### Order 2 — <rule verbatim from Order 2 heading>
**Anti-pattern:** <Anti-pattern field verbatim>

... (one block per active order, same structure)

---

If any proposed change violates an Order above: redesign required — not a carve-out.
Doctrine reflects current-tech decisions; if you believe an Order's assumption no longer
holds, raise it for retirement rather than working around it.
```

### Generation rules

1. Copy the rule from each Order heading exactly (strip `[DRAFT]` / `[UNCHALLENGED]` /
   `[STALE]` markers if somehow present — but mini is only generated when those are absent).
2. Copy the Anti-pattern field verbatim. Do not summarize or shorten.
3. Copy the Detector field verbatim if present. Omit the `**Detector:**` line entirely
   if the order has no Detector.
4. Copy the Scope field verbatim if present. Omit the `**Scope:**` line entirely if
   the order has no Scope.
5. Omit Anchor, Tech Assumption, Sunset Trigger, and all other fields.
6. Omit Retired Orders and Promoted-to-Law Log sections.
7. The closing block (`If any proposed change…`) is fixed — do not alter it.
8. Retired Orders do not appear in the mini. The mini reflects active orders only.
