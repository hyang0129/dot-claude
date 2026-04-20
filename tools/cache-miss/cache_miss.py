#!/usr/bin/env python
"""cache_miss.py — Claude Code prompt cache miss investigator.

Usage:
  python cache_miss.py timeline  <session-file-or-id> [--json | --jsonl] [--with-signals]
  python cache_miss.py timeline  --all [--since <spec>] [--until <spec>] [--with-signals]
  python cache_miss.py explain   <session-file-or-id> <turn-index> [--json | --jsonl]
  python cache_miss.py summarize <session-file-or-id> [--jsonl]
  python cache_miss.py summarize --all [--since <spec>] [--until <spec>] [--jsonl]

Time specs: ISO (2026-04-15 or 2026-04-15T10:00:00) OR relative (7d, 24h, 30m).
"""

import argparse
import json
import sys
import os
import glob
import re

# On Windows, stdout defaults to cp1252 which can't round-trip arbitrary
# Unicode from JSONL transcripts. Force UTF-8 to avoid OSError on piped output.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Thresholds (tune here)
# ---------------------------------------------------------------------------
MISS_CACHE_READ_DROP_PCT = 0.50   # cache_read must drop by >50% vs prior turn
MISS_CACHE_CREATION_MIN = 1000    # AND cache_creation must be >1000 tokens
# OR: cache_read was >0 last turn but is 0 this turn -> also a MISS
TIME_GAP_TTL_SECONDS = 3600       # 1 hr = Anthropic extended cache TTL (default when telemetry enabled)

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_BATCH_SINCE = "7d"

# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: Path, *, strict: bool = True) -> list[dict]:
    events: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                if strict:
                    sys.exit(f"ERROR: invalid JSON on line {lineno} of {path}: {exc}")
                else:
                    print(
                        f"WARN: skipping invalid JSON on line {lineno} of {path}: {exc}",
                        file=sys.stderr,
                    )
                    continue
    return events


def resolve_session(session_arg: str) -> Path:
    """Accept a file path or a bare session UUID; return resolved Path."""
    p = Path(session_arg)
    if p.exists() and p.suffix == ".jsonl":
        return p
    pattern = str(CLAUDE_PROJECTS_ROOT / "**" / f"{session_arg}.jsonl")
    matches = glob.glob(pattern, recursive=True)
    if len(matches) == 1:
        return Path(matches[0])
    if len(matches) > 1:
        sys.exit(
            f"ERROR: multiple files match session id {session_arg!r}:\n"
            + "\n".join(f"  {m}" for m in matches)
        )
    sys.exit(
        f"ERROR: cannot find session {session_arg!r} — "
        f"not a valid path and no matching JSONL in {CLAUDE_PROJECTS_ROOT}"
    )


def session_id_from_path(path: Path) -> str:
    return path.stem


def project_slug_from_path(path: Path) -> str:
    # Expected layout: ~/.claude/projects/<slug>/<uuid>.jsonl
    try:
        return path.parent.name
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

_REL_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)


def parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_time_spec(spec: str, now: datetime | None = None) -> datetime:
    """Parse ISO datetime or relative (7d/24h/30m/45s). Returns tz-aware UTC."""
    now = now or datetime.now(timezone.utc)
    spec = spec.strip()
    m = _REL_RE.match(spec)
    if m:
        amt = int(m.group(1))
        unit = m.group(2).lower()
        delta = {
            "s": timedelta(seconds=amt),
            "m": timedelta(minutes=amt),
            "h": timedelta(hours=amt),
            "d": timedelta(days=amt),
        }[unit]
        return now - delta
    # ISO
    try:
        dt = datetime.fromisoformat(spec.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        sys.exit(f"ERROR: cannot parse time spec {spec!r} — use ISO or Nd/Nh/Nm/Ns")


def humanize_delta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total < 0:
        return "0s"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins and not days:
        parts.append(f"{mins}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Extract assistant turns
# ---------------------------------------------------------------------------

def extract_assistant_turns(events: list[dict]) -> list[dict]:
    """
    Return one record per unique assistant API response (deduplicated on
    message.id; keep last occurrence — streaming emits same id multiple times).
    """
    by_msg_id: dict[str, dict] = {}
    order: list[str] = []

    for event in events:
        if event.get("type") != "assistant":
            continue
        msg = event.get("message", {})
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if not usage or not isinstance(usage, dict):
            continue
        if not any(k in usage for k in (
            "cache_read_input_tokens", "cache_creation_input_tokens", "input_tokens"
        )):
            continue
        mid = msg.get("id", event.get("uuid", ""))
        if mid not in by_msg_id:
            order.append(mid)
        by_msg_id[mid] = {
            "uuid": event.get("uuid", ""),
            "msg_id": mid,
            "timestamp": event.get("timestamp"),
            "input_tokens": usage.get("input_tokens", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_creation": usage.get("cache_creation_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    return [by_msg_id[mid] for mid in order]


def annotate_misses(turns: list[dict]) -> list[dict]:
    for i, t in enumerate(turns):
        t["turn"] = i
        if i == 0:
            t["miss"] = False
            continue
        prev = turns[i - 1]
        prev_read = prev["cache_read"]
        curr_read = t["cache_read"]
        curr_creation = t["cache_creation"]
        miss = False
        if prev_read > 0 and curr_read == 0:
            miss = True
        elif prev_read > 0:
            drop_pct = (prev_read - curr_read) / prev_read
            if drop_pct > MISS_CACHE_READ_DROP_PCT and curr_creation > MISS_CACHE_CREATION_MIN:
                miss = True
        t["miss"] = miss
    return turns


# ---------------------------------------------------------------------------
# Signal extraction helpers (used by explain, --with-signals, summarize)
# ---------------------------------------------------------------------------

def text_of_message(msg: Any) -> str:
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text", "") or item.get("content", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(str(p) for p in parts)
    return ""


SENSITIVE_FILES = ("CLAUDE.md", "MEMORY.md", "settings.json", "settings.local.json")
SLASH_COMMANDS = ("/model", "/compact", "/clear", "/reset", "/reload")


def _window_for_turn(events: list[dict], turns: list[dict], idx: int) -> tuple[list[dict], list[dict]]:
    """Return (window, prior_window) for turn idx. Window = events strictly between
    prior assistant turn and this turn."""
    this_uuid = turns[idx]["uuid"]
    prev_uuid = turns[idx - 1]["uuid"] if idx > 0 else None

    this_event_idx = None
    prev_event_idx = None
    for i, ev in enumerate(events):
        if ev.get("uuid") == this_uuid:
            this_event_idx = i
        if prev_uuid and ev.get("uuid") == prev_uuid:
            prev_event_idx = i

    if this_event_idx is None:
        return [], events

    start = (prev_event_idx + 1) if prev_event_idx is not None else 0
    return events[start:this_event_idx], events[:start]


def compute_signals(events: list[dict], turns: list[dict], idx: int) -> list[dict]:
    """Return list of {signal_type, description} for a given turn index.

    Reused by `explain`, `timeline --with-signals`, and `summarize`.
    """
    if idx < 0 or idx >= len(turns):
        return []

    turn = turns[idx]
    window, prior_window = _window_for_turn(events, turns, idx)
    out: list[dict] = []

    def add(kind: str, desc: str) -> None:
        out.append({"signal_type": kind, "description": desc})

    # 1. Time gap
    if idx > 0:
        t0 = parse_ts(turns[idx - 1]["timestamp"])
        t1 = parse_ts(turn["timestamp"])
        if t0 and t1:
            gap_s = (t1 - t0).total_seconds()
            if gap_s > TIME_GAP_TTL_SECONDS:
                add(
                    "time-gap",
                    f"{gap_s/60:.1f} min gap between turn {idx-1} and turn {idx} "
                    f"(>{TIME_GAP_TTL_SECONDS//60} min TTL threshold)",
                )

    # 2. Compaction
    for ev in window:
        if ev.get("type") == "system" and ev.get("subtype") == "compact_boundary":
            meta = ev.get("compactMetadata", {}) or {}
            add(
                "compaction",
                f"compact_boundary event in window "
                f"(trigger={meta.get('trigger', 'unknown')}, "
                f"preTokens={meta.get('preTokens', '?')})",
            )

    # 3. Sensitive file writes
    for ev in window:
        if ev.get("type") != "assistant":
            continue
        content = (ev.get("message") or {}).get("content", [])
        if not isinstance(content, list):
            continue
        for item in content:
            if not (isinstance(item, dict) and item.get("type") == "tool_use"):
                continue
            tool = item.get("name", "")
            if tool not in ("Write", "Edit", "MultiEdit", "Bash"):
                continue
            inp = item.get("input", {}) or {}
            fp = inp.get("file_path", "") or inp.get("command", "")
            flagged = any(sf in fp for sf in SENSITIVE_FILES) or ".claude" in fp
            if flagged:
                add("file-write", f"sensitive config file touched: {tool}({fp!r})")

    # 4. Slash commands
    seen_cmds = set()
    for ev in window:
        if ev.get("type") != "user":
            continue
        text = text_of_message(ev.get("message", {}))
        for cmd in SLASH_COMMANDS:
            if cmd in text and cmd not in seen_cmds:
                seen_cmds.add(cmd)
                add("slash-command", f"{cmd} used in user message in window")

    # 5. ToolSearch expansions — scan:
    #   (a) this window (events between prev turn and miss turn), AND
    #   (b) the prior ASSISTANT TURN itself (N-1's own tool_use blocks), AND
    #   (c) the window before the prior turn (between N-2 and N-1).
    # A ToolSearch in turn N-1 loads a schema that bakes into turn N's tools
    # array, so the cache miss surfaces at turn N.
    prior_window_before_prev: list[dict] = []
    if idx > 1:
        prior_window_before_prev, _ = _window_for_turn(events, turns, idx - 1)

    # Get the prior assistant turn's raw event(s) by matching its uuid/msg_id.
    prior_turn_events: list[dict] = []
    if idx > 0:
        prev_uuid = turns[idx - 1]["uuid"]
        prev_msg_id = turns[idx - 1].get("msg_id")
        for ev in events:
            if ev.get("type") != "assistant":
                continue
            if ev.get("uuid") == prev_uuid:
                prior_turn_events.append(ev)
                continue
            msg = ev.get("message") or {}
            if prev_msg_id and msg.get("id") == prev_msg_id:
                prior_turn_events.append(ev)

    def _find_toolsearch(evs: list[dict], label: str) -> None:
        for ev in evs:
            if ev.get("type") != "assistant":
                continue
            content = (ev.get("message") or {}).get("content", [])
            if not isinstance(content, list):
                continue
            for item in content:
                if (isinstance(item, dict) and item.get("type") == "tool_use"
                        and item.get("name") == "ToolSearch"):
                    q = (item.get("input", {}) or {}).get("query", "<unknown>")
                    add("tool-expansion",
                        f"ToolSearch call in {label} (query={q!r}) — tools list changed")

    _find_toolsearch(window, "this window")
    _find_toolsearch(prior_turn_events, "prior turn")
    _find_toolsearch(prior_window_before_prev, "window before prior turn")

    # 6. New MCP tools
    def mcp_names(evs: list[dict]) -> set[str]:
        names: set[str] = set()
        for ev in evs:
            att = ev.get("attachment", {})
            if isinstance(att, dict) and att.get("type") == "deferred_tools_delta":
                for name in att.get("addedNames", []):
                    if "mcp__" in name:
                        names.add(name)
            if ev.get("type") == "assistant":
                content = (ev.get("message") or {}).get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            n = item.get("name", "")
                            if n.startswith("mcp__"):
                                names.add(n)
        return names

    # Scan this window + prior turn + window before prior turn (same reason
    # as ToolSearch above — schemas added in turn N-1 break cache at turn N).
    combined_window = window + prior_turn_events + prior_window_before_prev
    for name in sorted(mcp_names(combined_window) - mcp_names(prior_window)):
        add("new-mcp-tool", f"{name} appeared for first time in this or prior window")

    # 7. deferred_tools_delta attachment (this + prior turn's events + window before)
    for ev in combined_window:
        att = ev.get("attachment", {})
        if isinstance(att, dict) and att.get("type") == "deferred_tools_delta":
            added = att.get("addedNames", []) or []
            if added:
                preview = ", ".join(added[:5]) + ("..." if len(added) > 5 else "")
                add(
                    "tools-list-delta",
                    f"deferred_tools_delta attachment added {len(added)} tool(s): {preview}",
                )

    # 8. Queued-command flush — user-typed messages queued while the agent
    # was mid-turn get flushed into the input as a batch. N new user-message
    # boundaries insert at once, which breaks the cached prefix.
    queued = [
        ev for ev in window
        if isinstance(ev.get("attachment"), dict)
        and ev["attachment"].get("type") == "queued_command"
    ]
    if queued:
        add(
            "queued-command-flush",
            f"{len(queued)} queued user message(s) flushed in window — "
            f"prefix grew by that many message boundaries",
        )

    return out


# ---------------------------------------------------------------------------
# Batch walk
# ---------------------------------------------------------------------------

def _session_last_ts(events: list[dict], path: Path) -> datetime | None:
    """Best-effort: most recent timestamped event; fallback to file mtime."""
    latest: datetime | None = None
    for ev in events:
        ts = parse_ts(ev.get("timestamp"))
        if ts and (latest is None or ts > latest):
            latest = ts
    if latest:
        return latest
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def walk_sessions(
    since: datetime | None,
    until: datetime | None,
) -> Iterable[tuple[Path, list[dict]]]:
    """Yield (path, events) for sessions whose most recent event lies in window.
    Prints summary stats to stderr. Skips parse failures with a warning."""
    all_files = sorted(CLAUDE_PROJECTS_ROOT.glob("**/*.jsonl"))
    total = len(all_files)
    matched = 0
    skipped_window = 0
    skipped_parse = 0

    results: list[tuple[Path, list[dict]]] = []
    for p in all_files:
        try:
            events = load_jsonl(p, strict=False)
        except Exception as exc:
            print(f"WARN: skipping {p} — parse error: {exc}", file=sys.stderr)
            skipped_parse += 1
            continue
        last_ts = _session_last_ts(events, p)
        if last_ts is None:
            skipped_parse += 1
            continue
        if since and last_ts < since:
            skipped_window += 1
            continue
        if until and last_ts > until:
            skipped_window += 1
            continue
        matched += 1
        results.append((p, events))

    print(
        f"[batch] scanned {total} sessions: {matched} matched window, "
        f"{skipped_window} outside window, {skipped_parse} skipped (parse/empty)",
        file=sys.stderr,
    )
    return results


# ---------------------------------------------------------------------------
# Subcommand: timeline
# ---------------------------------------------------------------------------

def _turn_record_with_context(
    turn: dict,
    session_id: str,
    project_slug: str,
    events: list[dict] | None,
    turns: list[dict] | None,
    with_signals: bool,
    include_session_fields: bool,
) -> dict:
    rec = dict(turn)
    if include_session_fields:
        rec["session_id"] = session_id
        rec["project_slug"] = project_slug
    if with_signals and turn["miss"] and events is not None and turns is not None:
        rec["signals"] = compute_signals(events, turns, turn["turn"])
    elif with_signals and turn["miss"]:
        rec["signals"] = []
    return rec


def _print_timeline_table(
    path: Path,
    turns: list[dict],
    events: list[dict],
    with_signals: bool,
) -> None:
    col = {"turn": 5, "timestamp": 26, "input": 8, "cache_r": 9, "cache_c": 11, "miss": 6}
    header = (
        f"{'Turn':>{col['turn']}}  "
        f"{'Timestamp':<{col['timestamp']}}  "
        f"{'Input':>{col['input']}}  "
        f"{'CacheRead':>{col['cache_r']}}  "
        f"{'CacheCreate':>{col['cache_c']}}  "
        f"{'MISS':<{col['miss']}}"
    )
    sep = "-" * len(header)
    print(f"Session: {path}")
    print(sep)
    print(header)
    print(sep)
    for t in turns:
        ts = (t["timestamp"] or "")[:26]
        miss_str = "MISS" if t["miss"] else ""
        print(
            f"{t['turn']:>{col['turn']}}  "
            f"{ts:<{col['timestamp']}}  "
            f"{t['input_tokens']:>{col['input']},}  "
            f"{t['cache_read']:>{col['cache_r']},}  "
            f"{t['cache_creation']:>{col['cache_c']},}  "
            f"{miss_str:<{col['miss']}}"
        )
        if with_signals and t["miss"]:
            signals = compute_signals(events, turns, t["turn"])
            if not signals:
                print(f"       (no signals detected)")
            else:
                for s in signals:
                    print(f"       [{s['signal_type']}] {s['description']}")
    print(sep)
    miss_count = sum(1 for t in turns if t["miss"])
    print(f"{len(turns)} turns, {miss_count} cache miss(es)")


def cmd_timeline(args: argparse.Namespace) -> None:
    # Mutual exclusion checks
    if args.json and args.jsonl:
        sys.exit("ERROR: --json and --jsonl are mutually exclusive")
    if args.all:
        if args.session:
            sys.exit("ERROR: --all cannot be combined with a positional session argument")
        if args.json:
            sys.exit("ERROR: --all cannot be combined with --json (use --jsonl, the default for --all)")

    if args.all:
        since = parse_time_spec(args.since) if args.since else parse_time_spec(DEFAULT_BATCH_SINCE)
        until = parse_time_spec(args.until) if args.until else None
        for path, events in walk_sessions(since, until):
            turns = annotate_misses(extract_assistant_turns(events))
            if not turns:
                continue
            sid = session_id_from_path(path)
            slug = project_slug_from_path(path)
            for t in turns:
                rec = _turn_record_with_context(
                    t, sid, slug, events, turns,
                    with_signals=args.with_signals,
                    include_session_fields=True,
                )
                print(json.dumps(rec))
        return

    # Single-session mode
    if not args.session:
        sys.exit("ERROR: session argument required (or pass --all)")

    path = resolve_session(args.session)
    events = load_jsonl(path)
    turns = annotate_misses(extract_assistant_turns(events))

    if not turns:
        sys.exit("ERROR: no assistant turns with usage data found in this session.")

    sid = session_id_from_path(path)
    slug = project_slug_from_path(path)

    if args.jsonl:
        for t in turns:
            rec = _turn_record_with_context(
                t, sid, slug, events, turns,
                with_signals=args.with_signals,
                include_session_fields=False,
            )
            print(json.dumps(rec))
        return

    if args.json:
        out = [
            _turn_record_with_context(
                t, sid, slug, events, turns,
                with_signals=args.with_signals,
                include_session_fields=False,
            )
            for t in turns
        ]
        print(json.dumps(out, indent=2))
        return

    _print_timeline_table(path, turns, events, args.with_signals)


# ---------------------------------------------------------------------------
# Subcommand: explain
# ---------------------------------------------------------------------------

def cmd_explain(args: argparse.Namespace) -> None:
    if args.json and args.jsonl:
        sys.exit("ERROR: --json and --jsonl are mutually exclusive")

    path = resolve_session(args.session)
    events = load_jsonl(path)
    turns = annotate_misses(extract_assistant_turns(events))

    idx = args.turn
    if idx < 0 or idx >= len(turns):
        sys.exit(
            f"ERROR: turn index {idx} out of range — "
            f"session has turns 0..{len(turns)-1}"
        )

    turn = turns[idx]
    signals = compute_signals(events, turns, idx)

    if args.jsonl:
        for s in signals:
            print(json.dumps({
                "turn": idx,
                "signal_type": s["signal_type"],
                "description": s["description"],
            }))
        return

    if args.json:
        print(json.dumps({
            "turn": idx,
            "timestamp": turn["timestamp"],
            "miss": turn["miss"],
            "usage": {
                "input_tokens": turn["input_tokens"],
                "cache_read": turn["cache_read"],
                "cache_creation": turn["cache_creation"],
            },
            "signals": signals,
        }, indent=2))
        return

    # Human-readable
    if not turn["miss"]:
        print(f"Note: turn {idx} is NOT flagged as a cache miss by timeline heuristics.")
        print("Proceeding with analysis anyway.\n")

    window, _ = _window_for_turn(events, turns, idx)
    print(f"Session : {path}")
    print(f"Turn    : {idx}")
    print(f"Time    : {turn['timestamp'] or 'unknown'}")
    print(
        f"Usage   : input={turn['input_tokens']:,}  "
        f"cache_read={turn['cache_read']:,}  "
        f"cache_creation={turn['cache_creation']:,}"
    )
    print(f"MISS    : {'yes' if turn['miss'] else 'no (not flagged)'}")
    print(f"Window  : {len(window)} events between turn {idx-1 if idx>0 else 'start'} and turn {idx}")
    print()
    if signals:
        print("Candidate causes:")
        for s in signals:
            print(f"  [{s['signal_type']}] {s['description']}")
    else:
        print("No candidate causes detected in the event window.")
        print("The miss may be due to model context changes not visible in the transcript,")
        print("or the system prompt / tool definitions changing between requests.")


# ---------------------------------------------------------------------------
# Subcommand: summarize
# ---------------------------------------------------------------------------

def _summarize_session(path: Path, events: list[dict]) -> dict | None:
    turns = annotate_misses(extract_assistant_turns(events))
    if not turns:
        return None

    sid = session_id_from_path(path)
    slug = project_slug_from_path(path)

    # Duration: first and last assistant turn (fall back to any event timestamp)
    first_ts = parse_ts(turns[0]["timestamp"])
    last_ts = parse_ts(turns[-1]["timestamp"])
    if first_ts is None or last_ts is None:
        # Fall back to any event timestamps
        ev_tss = [t for t in (parse_ts(e.get("timestamp")) for e in events) if t]
        if ev_tss:
            first_ts = first_ts or min(ev_tss)
            last_ts = last_ts or max(ev_tss)

    total_input = sum(t["input_tokens"] for t in turns)
    total_cache_read = sum(t["cache_read"] for t in turns)
    total_cache_creation = sum(t["cache_creation"] for t in turns)
    grand_total = total_input + total_cache_read + total_cache_creation
    cache_pct = (total_cache_read / grand_total * 100.0) if grand_total else 0.0

    misses = [t for t in turns if t["miss"]]

    largest_miss: dict | None = None
    largest_creation = -1
    for t in misses:
        if t["cache_creation"] > largest_creation:
            largest_creation = t["cache_creation"]
            largest_miss = t

    # Dominant cause
    sig_counts: dict[str, int] = {}
    for t in misses:
        sigs = compute_signals(events, turns, t["turn"])
        for s in sigs:
            sig_counts[s["signal_type"]] = sig_counts.get(s["signal_type"], 0) + 1
    dominant = None
    if sig_counts:
        kind, count = max(sig_counts.items(), key=lambda kv: kv[1])
        dominant = {"signal_type": kind, "count": count}

    largest_miss_detail = None
    if largest_miss is not None:
        prev = turns[largest_miss["turn"] - 1] if largest_miss["turn"] > 0 else None
        largest_miss_detail = {
            "turn": largest_miss["turn"],
            "prev_cache_read": prev["cache_read"] if prev else None,
            "cache_read": largest_miss["cache_read"],
            "cache_creation": largest_miss["cache_creation"],
        }

    return {
        "session_id": sid,
        "project_slug": slug,
        "path": str(path),
        "first_event": first_ts.isoformat() if first_ts else None,
        "last_event": last_ts.isoformat() if last_ts else None,
        "duration_seconds": (
            (last_ts - first_ts).total_seconds() if first_ts and last_ts else None
        ),
        "assistant_turns": len(turns),
        "total_input_tokens": total_input,
        "total_cache_read": total_cache_read,
        "total_cache_creation": total_cache_creation,
        "cache_read_pct": round(cache_pct, 2),
        "miss_count": len(misses),
        "largest_miss": largest_miss_detail,
        "dominant_cause": dominant,
    }


def _print_summary_human(summary: dict) -> None:
    print(f"Session: {summary['session_id']}")
    if summary.get("project_slug"):
        print(f"Project: {summary['project_slug']}")
    if summary["first_event"] and summary["last_event"]:
        dt0 = datetime.fromisoformat(summary["first_event"])
        dt1 = datetime.fromisoformat(summary["last_event"])
        print(
            f"Duration: {summary['first_event']} -> {summary['last_event']}  "
            f"({humanize_delta(dt1 - dt0)})"
        )
    else:
        print("Duration: (timestamps unavailable)")
    print(f"Assistant turns: {summary['assistant_turns']}")
    total_prompt = (
        summary["total_input_tokens"]
        + summary["total_cache_read"]
        + summary["total_cache_creation"]
    )
    print(f"Total prompt tokens:     {total_prompt:,}")
    print(f"  Fresh input:           {summary['total_input_tokens']:,}")
    print(
        f"  Served from cache:     {summary['total_cache_read']:,}  "
        f"({summary['cache_read_pct']}%)"
    )
    print(f"  Cache creation:        {summary['total_cache_creation']:,}")
    print(f"Misses: {summary['miss_count']}")
    lm = summary.get("largest_miss")
    if lm:
        prev = lm["prev_cache_read"]
        prev_str = f"{prev:,}" if prev is not None else "n/a"
        print(
            f"  Largest single miss:   turn {lm['turn']}  "
            f"(cache_read dropped from {prev_str} -> {lm['cache_read']:,}, "
            f"creation spiked to {lm['cache_creation']:,})"
        )
    dom = summary.get("dominant_cause")
    if dom:
        print(f"  Dominant cause:        {dom['signal_type']} ({dom['count']} occurrence(s))")
    elif summary["miss_count"] > 0:
        print(f"  Dominant cause:        (no signals detected for any miss)")


def cmd_summarize(args: argparse.Namespace) -> None:
    if args.all:
        if args.session:
            sys.exit("ERROR: --all cannot be combined with a positional session argument")
        since = parse_time_spec(args.since) if args.since else parse_time_spec(DEFAULT_BATCH_SINCE)
        until = parse_time_spec(args.until) if args.until else None
        first = True
        for path, events in walk_sessions(since, until):
            summary = _summarize_session(path, events)
            if summary is None:
                continue
            if args.jsonl:
                print(json.dumps(summary))
            else:
                if not first:
                    print()
                _print_summary_human(summary)
                first = False
        return

    if not args.session:
        sys.exit("ERROR: session argument required (or pass --all)")

    path = resolve_session(args.session)
    events = load_jsonl(path)
    summary = _summarize_session(path, events)
    if summary is None:
        sys.exit("ERROR: no assistant turns with usage data found in this session.")
    if args.jsonl:
        print(json.dumps(summary))
    else:
        _print_summary_human(summary)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate Claude Code prompt cache misses from session JSONL transcripts."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- timeline ----
    p_tl = sub.add_parser("timeline", help="Show per-turn cache token usage and flag likely misses.")
    p_tl.add_argument("session", nargs="?", help="Path to session .jsonl file, or bare session UUID.")
    p_tl.add_argument("--json", action="store_true", help="Output as indented JSON array.")
    p_tl.add_argument("--jsonl", action="store_true", help="Output one JSON object per line.")
    p_tl.add_argument("--all", action="store_true",
                      help="Walk every session under ~/.claude/projects/ (forces --jsonl).")
    p_tl.add_argument("--since", help="Lower bound on last-event time (ISO or Nd/Nh/Nm).")
    p_tl.add_argument("--until", help="Upper bound on last-event time (ISO or Nd/Nh/Nm).")
    p_tl.add_argument("--with-signals", action="store_true",
                      help="Inline candidate signals for each MISS turn.")

    # ---- explain ----
    p_ex = sub.add_parser("explain", help="List candidate causes for a cache miss at a specific turn.")
    p_ex.add_argument("session", help="Path to session .jsonl file, or bare session UUID.")
    p_ex.add_argument("turn", type=int, help="Turn index (from timeline) to investigate.")
    p_ex.add_argument("--json", action="store_true", help="Output as indented JSON.")
    p_ex.add_argument("--jsonl", action="store_true",
                      help="Output one {turn,signal_type,description} per line.")

    # ---- summarize ----
    p_sm = sub.add_parser("summarize", help="Short human-readable report for a session (or all).")
    p_sm.add_argument("session", nargs="?", help="Path to session .jsonl file, or bare session UUID.")
    p_sm.add_argument("--jsonl", action="store_true", help="Emit one JSON object per session.")
    p_sm.add_argument("--all", action="store_true",
                      help="Walk every session under ~/.claude/projects/.")
    p_sm.add_argument("--since", help="Lower bound on last-event time (ISO or Nd/Nh/Nm).")
    p_sm.add_argument("--until", help="Upper bound on last-event time (ISO or Nd/Nh/Nm).")

    args = parser.parse_args()
    if args.cmd == "timeline":
        cmd_timeline(args)
    elif args.cmd == "explain":
        cmd_explain(args)
    elif args.cmd == "summarize":
        cmd_summarize(args)


if __name__ == "__main__":
    main()
