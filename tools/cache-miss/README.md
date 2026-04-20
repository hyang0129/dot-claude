# cache-miss

Tools for investigating Claude Code prompt-cache misses from session JSONL
transcripts under `~/.claude/projects/`.

## Why

Prompt cache misses are expensive: every missed turn re-hashes tens to
hundreds of thousands of tokens. Claude Code logs per-turn usage (including
`cache_read_input_tokens` and `cache_creation_input_tokens`) to the session
JSONL, so we can reconstruct when the cache broke and — with enough signals
— *why*.

The goal is a detector that mechanically explains every miss. The remaining
"no signal" cases are the research frontier: each one is either a bug in the
detector (signal exists but we don't check for it) or a new kind of cause we
haven't catalogued yet.

## Workflow

1. **Find new cache miss causes.** Dump the context around misses the
   detector can't explain, then read the transcripts (or hand them to
   subagents) and hypothesize what broke the prefix.
2. **Mechanize.** Add a signal to `compute_signals()` in `cache_miss.py`
   that fires on the pattern.
3. **Re-run.** Sweep recent sessions; confirm the new signal catches what it
   should, and watch for regressions.
4. **Expand.** Repeat. The detector's catch-rate should monotonically improve
   over time. New no-signal cases = new patterns to investigate.

## Scripts

### `cache_miss.py`

Three subcommands for per-session analysis:

```bash
# Per-turn token table with MISS flags
python cache_miss.py timeline <session-id-or-path> [--with-signals]

# Explain one specific miss (list signals that fired)
python cache_miss.py explain <session> <turn-index>

# Compact summary (duration, hit-rate, largest miss, dominant cause)
python cache_miss.py summarize <session>

# All three support --all + --since/--until to walk every session:
python cache_miss.py summarize --all --since 1d
```

Time specs: ISO (`2026-04-20`) or relative (`7d`, `24h`, `30m`).

### `dump_no_signal_cases.py`

Walks sessions in a time window, finds misses where `compute_signals()`
returned empty, and writes one markdown file per case to `results/`. Each
file contains the N turns before the miss plus the full event log in between
— designed to be consumed by a subagent (or read directly).

```bash
python dump_no_signal_cases.py --since 2d --context 5 --limit 10
```

Defaults: `--since 1d`, `--context 5`, `--out-dir <script-dir>/results/`.

`results/` is gitignored because it contains transcript excerpts (per-machine,
potentially sensitive).

## Current signal catalog

Defined in `compute_signals()` in `cache_miss.py`. Each signal is a named
reason the cache prefix would change between prev turn and miss turn:

| Signal | Fires when |
|---|---|
| `time-gap` | Gap > `TIME_GAP_TTL_SECONDS` between prev and miss turn (default 3600s, assumes 1h TTL via `ENABLE_PROMPT_CACHING_1H=1`) |
| `compaction` | `compact_boundary` system event in window |
| `file-write` | `Write`/`Edit`/`MultiEdit`/`Bash` touched `CLAUDE.md`, `MEMORY.md`, `settings.json`, or `.claude/` |
| `slash-command` | User message contained `/model`, `/compact`, `/clear`, `/reset`, `/reload` |
| `tool-expansion` | `ToolSearch` call in miss-turn window, prior turn itself, or window before prior turn |
| `new-mcp-tool` | New `mcp__*` tool name first appeared in the same three-window span |
| `tools-list-delta` | `deferred_tools_delta` attachment added tools |
| `queued-command-flush` | `queued_command` attachments flushed — user messages typed while agent was mid-turn insert N new user-turn boundaries into the prefix at once |

## Thresholds (tune in `cache_miss.py`)

```python
MISS_CACHE_READ_DROP_PCT = 0.50   # cache_read must drop >50% vs prior turn
MISS_CACHE_CREATION_MIN  = 1000   # AND cache_creation must be >1000 tokens
TIME_GAP_TTL_SECONDS     = 3600   # 1h — matches ENABLE_PROMPT_CACHING_1H
```

If you turn off the 1h cache (`unset ENABLE_PROMPT_CACHING_1H`), drop
`TIME_GAP_TTL_SECONDS` back to 300.

## Hypothesized causes still uncatalogued

Things we've seen in no-signal cases but haven't mechanized yet:
- Skill auto-load (skill definitions injected into system prompt mid-session)
- CLAUDE.md / MEMORY.md reloads that don't go through a Write tool call
- Subagent lifecycle transitions (spawn/return) that reorder attachments
- MCP server reconnect (tool schemas re-registered with slightly different order/shape)

Each one is an opportunity to add a signal and raise the catch rate.
