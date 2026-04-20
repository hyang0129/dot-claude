#!/usr/bin/env python
"""dump_no_signal_cases.py — extract localized logs for no-signal cache misses.

For each cache miss where compute_signals() returns empty, write a markdown
file containing the N turns leading up to the miss plus the miss turn itself,
so subagents can investigate what non-obvious thing caused the cache break.

Usage:
  python dump_no_signal_cases.py [--since SPEC] [--until SPEC]
                                 [--context N] [--limit M]
                                 [--out-dir DIR]

Defaults: --since 1d, --context 5, --out-dir <this-script-dir>/results/
"""

import argparse
import sys
from pathlib import Path

# Reuse helpers from cache_miss.py
sys.path.insert(0, str(Path(__file__).parent))
from cache_miss import (  # noqa: E402
    annotate_misses,
    compute_signals,
    extract_assistant_turns,
    parse_time_spec,
    project_slug_from_path,
    session_id_from_path,
    text_of_message,
    walk_sessions,
)


USER_TEXT_MAX = 2000
ASSISTANT_TEXT_MAX = 2000
TOOL_INPUT_MAX = 300
TOOL_RESULT_MAX = 500


def truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n...[truncated {len(s) - n} chars]"


def fmt_tool_input(inp: dict) -> str:
    import json as _json
    try:
        raw = _json.dumps(inp, ensure_ascii=False)
    except Exception:
        raw = str(inp)
    return truncate(raw, TOOL_INPUT_MAX)


def render_event(ev: dict, lines: list[str]) -> None:
    """Append a markdown rendering of a single event to `lines`."""
    t = ev.get("type", "?")
    ts = ev.get("timestamp", "")

    if t == "user":
        msg = ev.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else msg
        # Tool results come back as user messages with content=[{type:tool_result,...}]
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    tool_id = item.get("tool_use_id", "?")
                    result = item.get("content", "")
                    if isinstance(result, list):
                        result = " ".join(
                            (x.get("text", "") if isinstance(x, dict) else str(x))
                            for x in result
                        )
                    lines.append(f"### tool_result  ({ts})")
                    lines.append(f"tool_use_id: `{tool_id}`")
                    lines.append("```")
                    lines.append(truncate(str(result), TOOL_RESULT_MAX))
                    lines.append("```")
                    return
        # Plain user message
        text = text_of_message(msg)
        if text.strip():
            lines.append(f"### user  ({ts})")
            lines.append("```")
            lines.append(truncate(text, USER_TEXT_MAX))
            lines.append("```")
        return

    if t == "assistant":
        msg = ev.get("message", {}) or {}
        usage = msg.get("usage") or {}
        content = msg.get("content", [])
        header = f"### assistant  ({ts})"
        if usage:
            header += (
                f"  — input={usage.get('input_tokens', 0):,} "
                f"cache_read={usage.get('cache_read_input_tokens', 0):,} "
                f"cache_creation={usage.get('cache_creation_input_tokens', 0):,}"
            )
        lines.append(header)

        text_parts: list[str] = []
        tool_calls: list[tuple[str, dict]] = []
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                itype = item.get("type")
                if itype == "text":
                    text_parts.append(item.get("text", ""))
                elif itype == "tool_use":
                    tool_calls.append((item.get("name", "?"), item.get("input", {}) or {}))
                elif itype == "thinking":
                    text_parts.append(f"[thinking] {item.get('thinking', '')}")
        elif isinstance(content, str):
            text_parts.append(content)

        combined_text = "\n".join(p for p in text_parts if p.strip())
        if combined_text.strip():
            lines.append("```")
            lines.append(truncate(combined_text, ASSISTANT_TEXT_MAX))
            lines.append("```")
        for name, inp in tool_calls:
            lines.append(f"- **tool_use** `{name}` — `{fmt_tool_input(inp)}`")
        return

    if t == "system":
        sub = ev.get("subtype", "")
        lines.append(f"### system:{sub}  ({ts})")
        if sub == "compact_boundary":
            meta = ev.get("compactMetadata", {}) or {}
            lines.append(
                f"- trigger: `{meta.get('trigger', '?')}`  "
                f"preTokens: {meta.get('preTokens', '?')}"
            )
        else:
            # Render a short summary of other system events
            keys = [k for k in ev.keys() if k not in ("type", "subtype", "timestamp", "uuid")]
            if keys:
                lines.append(f"- keys: {keys}")
        return

    # Attachments and others
    att = ev.get("attachment")
    if isinstance(att, dict):
        atype = att.get("type", "?")
        lines.append(f"### attachment:{atype}  ({ts})")
        if atype == "deferred_tools_delta":
            added = att.get("addedNames", []) or []
            removed = att.get("removedNames", []) or []
            if added:
                lines.append(f"- addedNames ({len(added)}): {added[:20]}")
            if removed:
                lines.append(f"- removedNames ({len(removed)}): {removed[:20]}")
        return

    lines.append(f"### {t}  ({ts})  — (unrendered)")


def slice_events_for_case(
    events: list[dict],
    turns: list[dict],
    miss_idx: int,
    context_turns: int,
) -> list[dict]:
    """Return events from `context_turns` before miss (inclusive of that turn's
    prior window) through the miss turn itself."""
    start_turn = max(0, miss_idx - context_turns)
    start_uuid = turns[start_turn]["uuid"]
    end_uuid = turns[miss_idx]["uuid"]

    # Find event indices. Start from the event *before* start_turn's prior
    # window so we include the user message that triggered it.
    start_event_idx = None
    end_event_idx = None
    for i, ev in enumerate(events):
        if ev.get("uuid") == start_uuid and start_event_idx is None:
            # Walk back to beginning of this turn's window
            j = i - 1
            while j >= 0 and events[j].get("type") == "assistant":
                j -= 1
            # j now points to the last non-assistant event before start_turn,
            # or -1. We want to start at j+1 (inclusive of its user message).
            # Walk back one more user message for extra context.
            while j >= 0 and events[j].get("type") != "user":
                j -= 1
            start_event_idx = max(0, j)
        if ev.get("uuid") == end_uuid:
            end_event_idx = i

    if start_event_idx is None or end_event_idx is None:
        return []
    return events[start_event_idx : end_event_idx + 1]


def render_case(
    path: Path,
    events: list[dict],
    turns: list[dict],
    miss_idx: int,
    context_turns: int,
) -> str:
    """Build a markdown document for one no-signal miss case."""
    sid = session_id_from_path(path)
    slug = project_slug_from_path(path)
    miss = turns[miss_idx]
    prev = turns[miss_idx - 1] if miss_idx > 0 else None

    lines: list[str] = []
    lines.append(f"# Cache miss case — {sid} turn {miss_idx}")
    lines.append("")
    lines.append(f"- **Session path**: `{path}`")
    lines.append(f"- **Project**: `{slug}`")
    lines.append(f"- **Miss turn**: {miss_idx} @ {miss['timestamp']}")
    if prev:
        lines.append(
            f"- **Prev turn usage**: cache_read={prev['cache_read']:,} "
            f"cache_creation={prev['cache_creation']:,}"
        )
    lines.append(
        f"- **Miss turn usage**: cache_read={miss['cache_read']:,} "
        f"cache_creation={miss['cache_creation']:,} "
        f"input_tokens={miss['input_tokens']:,}"
    )
    lines.append(f"- **Signals detected**: none")
    lines.append(f"- **Context window**: {context_turns} prior assistant turns")
    lines.append("")
    lines.append("## Turn-by-turn token deltas (approach to miss)")
    lines.append("")
    lines.append("| Turn | Timestamp | input | cache_read | cache_creation | MISS |")
    lines.append("|---:|:---|---:|---:|---:|:---:|")
    start = max(0, miss_idx - context_turns)
    for i in range(start, miss_idx + 1):
        t = turns[i]
        marker = "**MISS**" if t["miss"] else ""
        lines.append(
            f"| {i} | {t['timestamp']} | {t['input_tokens']:,} | "
            f"{t['cache_read']:,} | {t['cache_creation']:,} | {marker} |"
        )
    lines.append("")
    lines.append("## Event log")
    lines.append("")
    sliced = slice_events_for_case(events, turns, miss_idx, context_turns)
    for ev in sliced:
        render_event(ev, lines)
        lines.append("")

    lines.append("## Investigation prompt for subagent")
    lines.append("")
    lines.append(
        "This cache miss was not explained by any of the standard signals "
        "(time-gap, compaction, sensitive file write, slash command, "
        "tool-expansion, new MCP tool, tools-list-delta). Hypothesize what "
        "may have caused the prompt cache to break between the prior turn and "
        "this turn. Consider: system prompt changes, tool schema churn not "
        "captured by deferred_tools_delta, subagent lifecycle events, "
        "skill loading, CLAUDE.md/memory file reloads, or silent context "
        "rewrites. Cite specific events by timestamp."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="1d", help="Lower bound (default: 1d)")
    parser.add_argument("--until", default=None, help="Upper bound")
    parser.add_argument("--context", type=int, default=5,
                        help="Prior assistant turns to include (default: 5)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max cases to emit")
    parser.add_argument("--out-dir",
                        default=str(Path(__file__).parent / "results"),
                        help="Output directory (default: <script-dir>/results)")
    args = parser.parse_args()

    since = parse_time_spec(args.since)
    until = parse_time_spec(args.until) if args.until else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    emitted = 0
    for path, events in walk_sessions(since, until):
        turns = annotate_misses(extract_assistant_turns(events))
        if not turns:
            continue
        for i, t in enumerate(turns):
            if not t["miss"]:
                continue
            signals = compute_signals(events, turns, i)
            if signals:
                continue  # has a signal — skip
            md = render_case(path, events, turns, i, args.context)
            sid = session_id_from_path(path)
            fname = f"{sid}_turn{i}.md"
            (out_dir / fname).write_text(md, encoding="utf-8")
            emitted += 1
            print(f"wrote {out_dir / fname}")
            if args.limit and emitted >= args.limit:
                print(f"[limit reached: {emitted}]", file=sys.stderr)
                return

    print(f"[done] {emitted} no-signal case(s) written to {out_dir}")


if __name__ == "__main__":
    main()
