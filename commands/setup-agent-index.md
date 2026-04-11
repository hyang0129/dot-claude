# Setup Agent Index

Builds `docs/agent_index.md` and `docs/modules/` for an existing codebase so that future
Planner agents can discover existing capabilities before planning new implementations.

Designed for codebases with little or no documentation. Assumes nothing — infers what it
can, surfaces what it cannot as explicit gaps for human review.

---

## Setup

### Git root detection

```bash
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$GIT_ROOT" ]; then
  for candidate in /workspaces/* "$HOME"/repos/* "$HOME"/repo "$HOME"/projects/* "$HOME"/*; do
    if [ -d "$candidate/.git" ]; then
      GIT_ROOT="$candidate"
      break
    fi
  done
fi
```

If `GIT_ROOT` is still empty, stop:
> "Could not find a git repository. Run this command from inside a repo."

Set up scratch directory:

First, check if the scratch directory already exists:
```bash
test -d "$GIT_ROOT/.claude-work" && echo "EXISTS" || echo "MISSING"
```
If `EXISTS`, skip to creating the subdirectory. If `MISSING`, create it:
```bash
mkdir -p "$GIT_ROOT/.claude-work" && echo '.claude-work/' >> "$GIT_ROOT/.git/info/exclude"
```
Then create the subdirectory:
```bash
mkdir -p "$GIT_ROOT/.claude-work/agent-index"
WORK="$GIT_ROOT/.claude-work/agent-index"
```

Check if `docs/agent_index.md` already exists:

```bash
[ -f "$GIT_ROOT/docs/agent_index.md" ] && echo "EXISTS"
```

If it exists, warn the user:

```
docs/agent_index.md already exists. Running this command will rebuild it from scratch.
Existing module docs in docs/modules/ will be overwritten.

Proceed? [yes / no]
```

Wait for confirmation before continuing.

---

## Phase 0 — Structural Survey (shell only, no agents)

All work in this phase is pure shell. No LLM calls. Goal: produce a shard manifest that
tells Scanner agents exactly which files to read.

### Step 0a: File inventory

```bash
find "$GIT_ROOT" -type f \( \
  -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \
  -o -name "*.py" -o -name "*.go" -o -name "*.rs" -o -name "*.java" \
  -o -name "*.cs" -o -name "*.rb" -o -name "*.swift" \
\) \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/.venv/*" \
  -not -path "*/vendor/*" \
  -not -path "*/dist/*" \
  -not -path "*/build/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/migrations/*" \
  -not -name "*.test.*" \
  -not -name "*.spec.*" \
  -not -name "*.min.*" \
  | sort > "$WORK/all_files.txt"

wc -l "$WORK/all_files.txt"
find "$GIT_ROOT" -type d -not -path "*/.git/*" -not -path "*/node_modules/*" \
  | sort > "$WORK/all_dirs.txt"
```

### Step 0b: Identify cross-cutting files

Files imported by more than 10 other files are cross-cutting — they belong to no single
partition shard and are assigned to a **dedicated Cross-cutting Scanner** that runs in
parallel with the partition Scanners. The orchestrator only assigns work; it never reads
these files itself.

```bash
# Build import edge list (language-agnostic grep)
grep -rn \
  -e "^import " \
  -e "^from .* import" \
  -e "^require(" \
  -e "^const .* = require" \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  --include="*.py" --include="*.go" \
  "$GIT_ROOT" \
  | grep -v node_modules | grep -v ".git" \
  > "$WORK/raw_imports.txt"

# Count how many files reference each path token
awk '{print $NF}' "$WORK/raw_imports.txt" \
  | tr -d '"'"'" | sed "s/[;,]$//" \
  | sort | uniq -c | sort -rn \
  | awk '$1 > 10 {print $2}' \
  > "$WORK/cross_cutting_tokens.txt"
```

Record in `$WORK/cross_cutting.txt`.

**If the cross-cutting set exceeds 50 files**, split it alphabetically into two shards and
assign each to its own Scanner. The orchestrator's job is shard assignment only — it never
reads the files themselves. Partition Scanners receive the list of cross-cutting file paths
as a skip-list ("these files are handled separately — do not document them").

### Step 0c: Directory coupling matrix

Directories that frequently import from each other should be in the same shard.

```bash
# For each import line: record (source_dir → target_dir) edge
python3 - <<'EOF'
import sys, re, os, json
from pathlib import Path
from collections import defaultdict

coupling = defaultdict(int)
with open(os.environ['WORK'] + '/raw_imports.txt') as f:
    for line in f:
        m = re.match(r'(.+?\.(?:ts|tsx|js|py|go)):\d+:', line)
        if not m: continue
        src_dir = str(Path(m.group(1)).parent)
        # extract quoted path
        path_m = re.search(r"['\"]([./][^'\"]+)['\"]", line)
        if not path_m: continue
        rel = path_m.group(1)
        try:
            target = str(Path(src_dir, rel).resolve().parent)
        except Exception:
            continue
        if src_dir != target:
            key = tuple(sorted([src_dir, target]))
            coupling[key] += 1

results = [{"a": k[0], "b": k[1], "weight": v}
           for k, v in sorted(coupling.items(), key=lambda x: -x[1])[:200]]
print(json.dumps(results, indent=2))
EOF
> "$WORK/dir_coupling.json"
```

### Step 0d: Build shard manifest

Target shard size: 8,000–12,000 LOC. Maximum 24 shards. Never split a directory
across two shards unless it alone exceeds 15,000 LOC.

Algorithm:
1. Group files by top-level source directory. Compute LOC per directory (`wc -l`).
2. Cluster tightly coupled directories (weight > 5 in coupling matrix) into the same shard.
3. Split oversized directories at the subdirectory boundary.
4. Each shard entry lists: shard ID, directories covered, exact file list, estimated LOC.

Write to `$WORK/manifest.json`:

```json
{
  "total_files": 2847,
  "total_loc": 198000,
  "cross_cutting": ["src/types/index.ts", "src/config/db.ts"],
  "shards": [
    {
      "id": "01",
      "label": "auth + session (coupled)",
      "directories": ["src/auth/", "src/session/"],
      "files": ["src/auth/index.ts", "..."],
      "neighbor_files": ["src/middleware/auth.ts"],
      "estimated_loc": 9800
    }
  ]
}
```

`neighbor_files`: files outside the shard that are directly imported by or import from
this shard. Each Scanner receives these as read-only context (to resolve boundary
ambiguities), not as files to document.

Print a summary before proceeding:

```
Structural survey complete.

  Files indexed:    <N>
  Total LOC:        ~<N>
  Shards:           <N> (avg <N> LOC each)
  Cross-cutting:    <N> files

Proceeding to parallel scan.
```

---

## Phase 1 — Parallel Scanning

Spawn **Scanner agents** (`model: "haiku"`) in batches of at most **4 concurrent agents**.
Process all shards in waves: start the first 4, wait for all 4 to finish, then start the
next batch of up to 4, and so on. One of these shards is the cross-cutting shard (files
from `$WORK/cross_cutting.txt`); it uses the same Scanner instructions as partition shards.
The orchestrator assigns it like any other shard and receives its `scan-crosscutting.json`
output alongside the partition outputs. The orchestrator never reads the cross-cutting files
itself.

### Scanner agent instructions

Role: read assigned files and extract structured capability information. No file writes
except your output JSON. Do not read files outside your assigned list and neighbor_files.

Input:
- `shard.files` — your files to document
- `shard.neighbor_files` — read for boundary context only, do not document
- `cross_cutting` list — do not document these; a dedicated Cross-cutting Scanner handles them
- `shard.label` — a hint about what this shard covers

Task:

1. Read every file in `shard.files`. Read `shard.neighbor_files` only to resolve ambiguities
   at the boundary.

2. For each directory in your shard, identify the module-level responsibility: what does this
   directory do as a unit, from the perspective of a caller outside it?

3. For each exported public symbol (function, class, type, constant, hook, command):
   - Name and file path
   - One-sentence purpose inferred from name + signature + comments only
   - Confidence: `high` (name + signature + comments unambiguous) / `medium` (name clear,
     behavior partially inferred) / `low` (name opaque, no comments, behavior unclear)

4. Identify non-obvious facts that a future agent could not infer by reading the file:
   - Environment variable dependencies
   - External I/O (HTTP, DB, queues, file system)
   - Side effects not apparent from the signature
   - Known gotchas (TODO/FIXME/HACK/WARNING annotations)
   - Extension points (exported interfaces, factory functions, plugin hooks)
   - Performance or concurrency constraints visible from the code

5. Flag anything you cannot confidently describe with `UNCLEAR`:
   ```json
   {
     "symbol": "doTheThing",
     "file": "src/pipeline/legacy.ts",
     "line": 88,
     "reason": "Name opaque, no comments, side effects unknown from static analysis"
   }
   ```
   Flag a symbol as UNCLEAR only when: name + signature + comments together do not
   give sufficient information. Do not fabricate intent. Do not guess.

Output: `$WORK/scan-<shard-id>.json`

```json
{
  "shard_id": "03",
  "modules": [
    {
      "directory": "src/notifications/",
      "purpose": "Dispatches notifications via multiple backends (email, SMS, push, Slack)",
      "confidence": "high",
      "primary_entry": "src/notifications/index.ts",
      "exports": [
        {
          "symbol": "sendNotification",
          "file": "src/notifications/dispatcher.ts",
          "line": 34,
          "signature": "sendNotification(type: NotificationType, recipient: User, payload: object): Promise<void>",
          "purpose": "Routes a notification to the appropriate backend based on user preferences",
          "confidence": "high",
          "non_obvious": [
            "Dynamic backend loading via importlib — available backends enumerated at runtime, not statically",
            "Async only — do not call from synchronous request handlers"
          ],
          "extension_point": "Add new backends by implementing INotificationBackend in src/notifications/backends/"
        }
      ],
      "env_deps": ["SENDGRID_API_KEY", "TWILIO_ACCOUNT_SID"],
      "io_deps": ["HTTP: SendGrid API", "HTTP: Twilio API"],
      "unclear": []
    }
  ]
}
```

After all Scanners complete, orchestrator verifies all `scan-*.json` files are present.
If any shard failed, re-run that Scanner once before continuing.

---

## Phase 2 — Gap Analysis

Gap analysis runs in two sub-phases to keep each agent's context window bounded.

### Phase 2a — Per-shard classification (parallel)

Spawn **Gap Classifier agents** (`model: "haiku"`) in batches of at most **4 concurrent
agents**. Process shards in waves of 4: start 4, wait for all to finish, then start the
next batch. Each agent sees only its own shard's unclear items — never the full corpus.
Maximum 50 unclear items per agent. If a shard produced more than 50, split it into
batches and spawn an additional agent per batch (counting against the 4-agent cap).

#### Gap Classifier instructions

Role: classify the unclear items from your assigned shard. No file writes except your
output JSON.

Input:
- Your shard's `$WORK/scan-<id>.json` (unclear array only)
- Your shard's `shard.files` content (for re-reading specific symbols if needed)

Task:

Classify each unclear item as one of:

**INFERABLE** — the answer is derivable from the symbol's name, signature, neighboring
comments, or the files you can see. Record your reasoning in one sentence.

**DEAD_CODE** — the symbol is exported but nothing in your shard imports or calls it.
Record the evidence.

**NEEDS_HUMAN** — genuinely ambiguous after your analysis. Cannot be resolved from code
alone.

For NEEDS_HUMAN items produce:

```json
{
  "id": "TBD",
  "symbol": "<name>",
  "file": "<path>",
  "line": <n>,
  "what_we_know": "...",
  "what_we_dont_know": "<concrete decision, not open-ended question>",
  "blocking_capability": "<capability name>",
  "options": ["A: ...", "B: ...", "C: Exclude from index entirely"]
}
```

Output: `$WORK/gaps-shard-<id>.json`

```json
{
  "shard_id": "<id>",
  "inferable": [{"symbol": "...", "file": "...", "resolution": "..."}],
  "dead_code": [{"symbol": "...", "file": "...", "evidence": "..."}],
  "needs_human": [/* NEEDS_HUMAN objects above */]
}
```

---

### Phase 2b — Cross-shard deduplication and structural gap detection

After all Gap Classifiers complete, spawn a single **Gap Merger agent** (`model: "sonnet"`).

#### Gap Merger instructions

Role: merge all per-shard gap outputs, resolve cross-shard INFERABLEs, deduplicate, and
produce the final gap report for human review.

Input:
- All `$WORK/gaps-shard-*.json` files
- `$WORK/manifest.json`

Task:

1. **Cross-shard resolution**: a symbol flagged NEEDS_HUMAN in shard A may be resolved by
   evidence in shard B (e.g., another shard imports it and its usage is unambiguous). If so,
   reclassify as INFERABLE and record the cross-shard source.

2. **Deduplication**: the same symbol may appear in multiple shards' unclear lists. Merge
   into one NEEDS_HUMAN entry. If shards disagree on classification, the stricter one wins
   (NEEDS_HUMAN > INFERABLE).

3. **Assign sequential GAP-NNN IDs** to all remaining NEEDS_HUMAN items.

4. **Structural gaps** — add entries for things no Scanner could detect:
   - Configuration-dependent behavior (settings files not in shard scope)
   - Dynamic loading patterns (runtime plugin registration, dependency injection)
   - Framework-magic registration (decorators, annotations, reflection)
   - Bidirectional module dependencies that create implicit constraints

Output: `$WORK/gaps.md` using this format for each NEEDS_HUMAN item:

```markdown
## GAP-<NNN>: <symbol> in <file>:<line>

**What we know**: <from name, signature, neighboring code, and comments>
**What we don't know**: <concrete decision the human must make>
**Blocking**: <which capability cannot be fully documented without this answer>
**Options**:
- A: <one possible interpretation>
- B: <another possible interpretation>
- C: Exclude from index entirely
```

Print a summary:

```
Gap analysis complete.

  INFERABLE (resolved automatically):   <N>
  DEAD_CODE (excluded from index):      <N>
  NEEDS_HUMAN (require your input):     <N>
  Structural (configuration/dynamic):   <N>

Proceeding to human review.
```

---

## Phase 3 — Human Gap Review (Hard Stop)

**Do not proceed until the human has responded.**

Present the NEEDS_HUMAN gaps from `$WORK/gaps.md` to the user, grouped by category:

```
## Agent Index — Gap Review Required

The scan identified <N> items that cannot be resolved from code alone.
Answer each gap below, then reply APPROVED to continue (or SKIP <id> to exclude
a gap from the index without answering it).

### Behavioral gaps (<N>)
[paste NEEDS_HUMAN items with BEH- prefix]

### Configuration gaps (<N>)
[paste NEEDS_HUMAN items with CONF- prefix]

### External dependency gaps (<N>)
[paste NEEDS_HUMAN items with EXT- prefix]

For each gap, reply:
  GAP-001: <your answer>
  GAP-002: SKIP
  ...
APPROVED
```

As the human replies, write their answers to `$WORK/gaps-resolved.md`:

```markdown
## GAP-001
**Human answer**: <verbatim>

## GAP-002
**Resolution**: SKIPPED — excluded from index
```

When the human says APPROVED (or equivalent), verify every GAP-NNN item in `$WORK/gaps.md`
has a corresponding entry in `$WORK/gaps-resolved.md`. If any are missing, ask specifically:

```
The following gaps were not addressed: GAP-007, GAP-012.
Please answer them or reply SKIP <id> to exclude them.
```

Do not proceed to Phase 4 until all gaps are accounted for.

---

## Phase 4 — Synthesis

Spawn a single **Synthesizer agent** (`model: "opus"`).

### Synthesizer agent instructions

Role: merge all scan outputs and human gap resolutions into a coherent capability map.
No source file reads. Produce draft index and module stubs.

Input:
- All `$WORK/scan-*.json` files
- `$WORK/gaps.md` and `$WORK/gaps-resolved.md`
- `$WORK/manifest.json`

Task:

1. Group modules into capabilities from the **caller's perspective**, not the directory
   structure. A capability is what a future agent would search for ("Authentication",
   "Job Queue") — not a path ("src/auth/").

2. For each capability:
   - Assign a clear, searchable name
   - Identify the primary entry point (the file a caller should import from)
   - List 6–12 tags: the terms a future agent would search for when looking for this
     capability. Include synonyms and common misspellings. Write from the searcher's
     vocabulary, not the implementer's.
   - Note any capabilities that span multiple directories — merge them correctly
   - Record all cross-module dependencies (A depends on B's runtime state)

3. Incorporate human answers: treat them as authoritative. If a human answer contradicts
   a Scanner's inference, the human answer wins.

4. Mark any remaining unresolved items explicitly:
   - SKIPped gaps → `[UNRESOLVED: GAP-NNN — excluded by user]`
   - Structural gaps with no answer → `[UNRESOLVED: dynamic loading — runtime only]`

5. Produce:

   **`$WORK/index-draft.md`** — one entry per capability, in the final `agent_index.md`
   format (see output format below).

   **`$WORK/modules-draft/<capability-name>.md`** — one stub per capability, ~150 words,
   containing:
   - Non-obvious usage (what a caller must know that the signature doesn't show)
   - Extension pattern (how to add a new X to this capability)
   - Constraints (performance, concurrency, ordering, environmental)
   - What not to do (common mistakes, deprecated paths, anti-patterns)
   - Known unknowns section if any gaps remain unresolved for this capability

   Do not summarize what the code already shows. Do not reproduce function signatures.
   Write for a future agent who needs to use this capability without reading the source.

---

## Phase 5 — Parallel Doc Writing

Spawn **Writer agents** (`model: "sonnet"`) in batches of at most **4 concurrent agents** —
one per batch of 4–6 module stubs. Start 4 agents, wait for all to finish, then start the next
batch of up to 4.

### Writer agent instructions

Role: expand your assigned stubs into complete `docs/modules/<name>.md` files.

Input:
- Your assigned `$WORK/modules-draft/<name>.md` stubs
- The corresponding sections of the Scanner outputs for your capabilities
- `$WORK/gaps-resolved.md` (full, for any gap items in your scope)

Task:

Expand each stub. The final module doc must be readable by a future agent that has never
seen this codebase. Contents:

```markdown
# <Capability Name>

## Use
<How to invoke this capability. The non-obvious parts only — not what the function
signature already shows. What must be true before calling it? What does it return
in the error case?>

## Extend
<How to add new behaviour to this capability. Name the file to edit, the interface
to implement, or the registration call to make.>

## Constraints
<Performance, concurrency, ordering, environmental requirements. Only those not
inferable from the type signature.>

## Do not
<Common mistakes. Deprecated paths. Anti-patterns that seem reasonable but break things.>

## Known unknowns
<Only present if gaps remain unresolved for this capability. List each [UNRESOLVED: GAP-NNN]
with the specific question that could not be answered.>
```

Rules:
- Never summarize what code already shows
- Never reproduce function signatures or type definitions
- Never fabricate constraints — only record what was found in the scan or human answers
- If a section has nothing to say, omit it (do not write "N/A")
- Length target: 100–300 words per module doc. Shorter is better.

Output: `docs/modules/<name>.md` for each assigned capability.

Create the directory if absent:
```bash
mkdir -p "$GIT_ROOT/docs/modules"
```

---

## Phase 6 — Index Assembly

Spawn a single **Assembler agent** (`model: "sonnet"`).

### Assembler agent instructions

Role: produce the final `docs/agent_index.md` from the index draft and completed module docs.

Input:
- `$WORK/index-draft.md`
- All completed `docs/modules/*.md`
- `$WORK/manifest.json` (for git SHA recording)

Task:

1. For each capability entry in the draft, verify the `docs/modules/<name>.md` file exists.
   If any are missing, flag them — do not omit them silently.

2. Produce `docs/agent_index.md` in this format:

```markdown
# Agent Capability Index

> Read this before planning any implementation. If a capability relevant to your task
> appears here, use it — do not reimplement it. Grep for keywords from your issue to
> find matches.

<!-- index-generated: <ISO date> -->

---

## <Capability Name>

Path: `<primary entry point>`
Doc: `docs/modules/<name>.md`
Tags: <comma-separated searchable terms>
Depends on: <other capability names, if runtime dependency exists — omit if none>
Unresolved: <[GAP-NNN description] — omit section entirely if no gaps>

---
```

3. Sort entries alphabetically.

4. At the top of each entry, record the source files and their current git SHAs:

```markdown
<!-- sources: src/auth/index.ts@a1b2c3d, src/auth/service.ts@e4f5a6b -->
```

   Get SHAs:
   ```bash
   git -C "$GIT_ROOT" log -1 --format="%H" -- <file>
   ```

   This enables future agents (and the fix-issue Documentation Agent) to detect stale
   entries by comparing recorded SHAs against current ones.

5. Add a footer:

```markdown
---

## Index metadata

Generated: <ISO date>
Codebase LOC: ~<N>
Capabilities indexed: <N>
Unresolved gaps: <N> (search `[UNRESOLVED` to find them)
```

Output: `docs/agent_index.md`

---

## Phase 7 — Validation

Orchestrator runs a spot check. For 3 randomly sampled capabilities:

```bash
# Pick 3 random capability names from the index
grep "^## " "$GIT_ROOT/docs/agent_index.md" | grep -v "Index metadata" \
  | shuf | head -3
```

For each sampled capability, ask: "Using only `docs/agent_index.md` and the linked module
doc, can you answer: (a) how to use this capability, and (b) how to extend it?" If either
answer requires reading source code, flag the module doc as incomplete.

Print validation results. Do not block completion on validation failures — they are
advisory warnings added to a `$WORK/validation-warnings.txt` file.

---

## CLAUDE.md Bootstrap

Check if the project's `CLAUDE.md` (at `$GIT_ROOT/CLAUDE.md`) already contains a pointer
to `docs/agent_index.md`. Search for the string `agent_index`:

```bash
grep -q "agent_index" "$GIT_ROOT/CLAUDE.md" 2>/dev/null && echo "EXISTS"
```

If not found (or CLAUDE.md does not exist), append:

```markdown

## Agent Capability Index

Before planning any implementation, read `docs/agent_index.md` and grep it for terms
related to your task. If a matching capability exists, use it — do not reimplement it.

The index is maintained by the Documentation Agent on each PR. If you implement a new
reusable capability, the Documentation Agent will add it to the index automatically.
```

---

## Commit

Stage and commit all generated files:

```bash
git -C "$GIT_ROOT" add \
  docs/agent_index.md \
  docs/modules/ \
  CLAUDE.md

git -C "$GIT_ROOT" commit -m "$(cat <<'EOF'
docs: generate agent capability index

Auto-generated by /setup-agent-index.
Capabilities indexed: <N>
Unresolved gaps: <N>

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

## Final Summary

```
## setup-agent-index complete

docs/agent_index.md    <N> capabilities indexed
docs/modules/          <N> module docs written

Gaps
  Resolved by cross-shard inference:  <N>
  Resolved by human input:            <N>
  Skipped (excluded from index):      <N>
  Unresolved (marked in index):       <N>

Validation
  Spot checks passed:   <N>/3
  Warnings:             <N> (see .claude-work/agent-index/validation-warnings.txt)

The Planner agent in /fix-issue will now read docs/agent_index.md before planning
any new implementation. Keep it current: the Documentation Agent in /fix-issue
updates it automatically on each PR.
```

---

## Constraints

- Never fabricate capability descriptions — only document what the code or human answers establish
- Never fill an unresolved gap with a guess — mark it `[UNRESOLVED: GAP-NNN]` explicitly
- Module docs must not summarize what code already shows — write only non-inferable facts
- The index is not a changelog or history — it describes current state only
- Do not read files outside the assigned shard scope during scanning
- Cross-cutting files (imported by >10 files) are documented by the dedicated Cross-cutting Scanner, not any partition Scanner and not the orchestrator
- The human gate in Phase 3 is mandatory — do not proceed to synthesis without APPROVED
