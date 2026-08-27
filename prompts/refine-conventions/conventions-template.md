# Conventions Template

Reference schema for `CONVENTIONS.md` files produced by the `/refine-conventions` skill.
Consumed by: entry point (state detection), refinement subskill (`[TBD]` resolution),
amendment subskill (edits), and any downstream tool that checks a repo's conventions
for completeness.

---

## File location convention

Default: `CONVENTIONS.md` at the repository root, alongside `CONSTITUTION.md`.

Override: pass an explicit path as the first argument to `/refine-conventions`.
The skill reads and writes that path for the entire session.

---

## Output schema

A complete `CONVENTIONS.md` has these top-level sections in this order:

```
# <Project Name> — Conventions

## Preamble

## Stack & Context

## Conventions
### <Area 1>
### <Area 2>
...

## Notes & Trade-offs   ← optional, prose; omit if empty
```

### Preamble (required)

One paragraph. States that this is the **how-we-build-it** layer of the project's
governance stack — engineering and architectural guidance for immediate implementation,
sitting under the constitution. Names the constitution it complements. Notes that
conventions are practical defaults: best practices, taste calls, and stack picks. The
only hard requirement on a convention is that it does not violate a constitutional law.
Conventions can be edited freely as the stack evolves; the constitution is the
load-bearing layer, not this file.

### Stack & Context (required)

Captured during Phase 1 of setup. Names the project's language, runtime, framework,
deploy target, team size, and any constraints that shaped the convention set. Acts
as the orientation block for new contributors and as the input record for any future
re-run of `/refine-conventions`.

Format:

```markdown
- **Language & runtime:** <e.g., Python 3.12>
- **Primary framework:** <e.g., Flask 3.x>
- **Data layer:** <e.g., PostgreSQL 16, SQLAlchemy 2.x>
- **Deploy target:** <e.g., Fly.io>
- **Team size:** <e.g., solo / 3 engineers / large team>
- **Constraints:** <one or two lines on anything notable>
```

Fields can be added or omitted to fit the project. Use `[TBD]` if a field is intentionally deferred.

### Conventions (required, ≥1 area)

The body of the file. Organized by area. Each area is an `###` subsection containing
one or more conventions.

### Notes & Trade-offs (optional)

Free-form prose. Use it to record considered-and-rejected alternatives, deferred
decisions, or context a future reader would want when amending the file. Omit the
section entirely if empty — do not leave a blank heading.

---

## Per-convention schema

Inside each `### <Area>` subsection, conventions are listed as bold-headed bullets:

```markdown
### <Area>

**<One-line rule, imperative>**
- **How:** <optional — pattern, library, file layout, command>
- **Notes:** <optional — why we picked this, alternatives considered, gotchas>
- **Revisit when:** <optional — only if the user volunteers a trigger>

**<Next rule>**
- ...
```

### Field descriptions

**Rule line** (required): The convention stated as one short imperative or declarative
sentence. Specific enough that a reader knows what to do. Examples: `Use Flask for the
HTTP layer.` `Pin all production dependencies in uv.lock.` `Route all LLM calls through
src/providers/.`

**How** (optional): Concrete realization of the rule. A library name, a file path, a
command, a code pattern. Omit if the rule is self-explanatory.

**Notes** (optional): Why this was picked, what alternatives were considered, known
gotchas. Useful when the choice is taste-based or non-obvious. Omit if there's nothing
worth adding.

**Revisit when** (optional): A signal that would prompt re-evaluation — e.g.,
`Revisit when team size exceeds 5.` Only include when the user volunteers a trigger.
Conventions do not require sunset triggers; this field is convenience, not contract.

---

## Canonical area ordering

`CONVENTIONS.md` emits areas in this fixed order regardless of drafting sequence.
Areas not used in a given project are **omitted entirely** (no empty headings).
Project-specific areas not on this list are appended at the end in the order they
were drafted.

1. Language & runtime
2. Dependency management
3. Code organization
4. Web framework / API layer
5. Frontend
6. Data access
7. Background jobs / queues
8. LLM / AI integration
9. Configuration & secrets
10. Error handling & exceptions
11. Logging & observability
12. Testing
13. Build & deploy
14. Security

The setup subskill draws from this list when proposing areas to the user. Not every
project needs every area.

---

## Marker grammar

There is exactly one marker:

| Marker | Where it appears | Meaning |
|---|---|---|
| `[TBD]` | As a field value, or as the entire body of an area subsection | Author intentionally deferred this content |

Examples:

```markdown
**Use Flask for the HTTP layer.**
- **How:** [TBD]
```

```markdown
### Background jobs / queues

[TBD]
```

The refinement subskill targets `[TBD]` entries.

There is no `[DRAFT]` prefix, no `[NEEDS X]` marker, no `[UNCHALLENGED]` suffix, no
`[STALE]` flag. Conventions are not interrogated; they are drafted, picked, and edited.

---

## Completeness rule

A conventions file is **complete** if and only if ALL of the following hold:

1. Zero `[TBD]` markers anywhere in the file.
2. Preamble section is present and non-empty.
3. Stack & Context section is present and non-empty.
4. Conventions section contains ≥1 area with ≥1 convention.

**Complete** is the routing signal the entry point uses to dispatch to amendment mode
rather than refinement mode.

---

## Worked example

```markdown
# Calliope — Conventions

## Preamble

This is the how-we-build-it layer. Conventions complement Calliope's constitution by
spelling out the stack-level defaults, libraries, and patterns we use today. Any
convention here can be edited as the stack evolves; the constitution is the
load-bearing layer that conventions must not violate.

## Stack & Context

- **Language & runtime:** Python 3.12
- **Primary framework:** Flask 3.x
- **Data layer:** PostgreSQL 16, SQLAlchemy 2.x
- **Deploy target:** Fly.io (single region for now)
- **Team size:** Solo
- **Constraints:** No background worker infra yet — defer queue selection.

## Conventions

### Language & runtime

**Use Python 3.12.**
- **How:** Pin via `.python-version`; CI runs the same version.

### Dependency management

**Use uv for dependency resolution and lockfile management.**
- **How:** `uv.lock` is committed; `uv sync` for installs.
- **Notes:** Considered Poetry; uv is faster and the lockfile is portable.

**Pin all production dependencies.**

### Web framework / API layer

**Use Flask 3.x for the HTTP layer.**
- **Notes:** User preference. FastAPI was considered but the project doesn't need
  async-first, and Flask's surface area is smaller.

**Route all routes through blueprints under `app/blueprints/`.**

### Data access

**Use SQLAlchemy 2.x with the typed ORM API.**
- **How:** `MappedAsDataclass` base; no legacy `Query.filter_by()` calls.

**Migrations via Alembic.**
- **How:** `alembic/` at repo root; one migration per PR.

### Testing

**Use pytest.**
- **How:** Tests in `tests/`, mirror the package layout under `app/`.

**Hit a real Postgres in tests, not a mock.**
- **Notes:** A docker-compose file in `tests/` brings up a throwaway Postgres.

### Build & deploy

**Deploy via `fly deploy` from main.**
- **How:** GitHub Actions runs `fly deploy --remote-only` on push to main.

## Notes & Trade-offs

Background jobs deferred — when async work is needed, evaluate Dramatiq vs.
Celery vs. arq. Solo team size makes Dramatiq the early favorite for operational
simplicity.
```

---

## Mini conventions schema

`CONVENTIONS.mini.md` is auto-derived from `CONVENTIONS.md` whenever the master is
written in a complete state (zero `[TBD]` markers). Never edit it directly. If the
master has markers remaining after a session, skip mini generation (or delete an
existing stale mini).

**Purpose:** agent injection. The full conventions file may be long (800+ lines is
expected). Agents competing with code and issue context for attention window cannot
reliably adhere to it. The mini strips Preamble, Stack & Context, Notes & Trade-offs,
and per-convention `Notes` and `Revisit when` lines — keeping just the rule and any
`How:` line that names a concrete pattern, library, or command.

### Mini schema

```markdown
# <Project Name> — Conventions (Mini)
<!-- Auto-derived from CONVENTIONS.md — do not edit directly -->

## <Area 1>
- <rule line, verbatim>
  - How: <how line, verbatim — omit this sub-bullet if no How field>
- <rule line>

## <Area 2>
- <rule line>
...

---

If a proposed change conflicts with a convention above, raise it for amendment via
`/refine-conventions` rather than working around it.
```

### Generation rules

1. Copy the rule line from each convention exactly.
2. Copy the `How` field verbatim if present, as a nested sub-bullet `  - How: <text>`.
3. Omit `Notes`, `Revisit when`, Preamble, Stack & Context, and Notes & Trade-offs.
4. Preserve the canonical area ordering from the master.
5. The closing block (`If a proposed change conflicts…`) is fixed — do not alter it.
6. If a convention has only a rule line and no `How`, emit just `- <rule>` (no nested bullet).
