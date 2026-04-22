#!/usr/bin/env python3
"""In-depth analysis of a single /refine-issue session's phase.

Usage:
    python analyze-refine-issue-phase.py <match> <phase> [--top N] [--md PATH]

Args:
    match   substring matching the session id or issue URL
    phase   one of: scan | intv | post-spec | pre

Flags:
    --top N  show full tool-input detail for the N most expensive turns (default 5)
    --md PATH write a markdown report to PATH instead of stdout
"""

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime


_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "refine_issue_sessions", os.path.join(_HERE, "find-refine-issue-sessions.py"),
)
_re = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_re)


PHASE_ALIAS = {
    "scan":      "root-scan",
    "intv":      "root-interview",
    "interview": "root-interview",
    "post-spec": "root-post-spec",
    "pre":       "root-pre-cmd",
    # Subagent drills — walk the subagent's own jsonl file
    "spec":      "sub-spec",
    "explore":   "sub-explore",
}


def find_session(match: str, days: int = 30):
    sessions = _re.scan_sessions(days=days)
    low = match.lower()
    candidates = [
        s for s in sessions
        if low in (s.get("issue_url") or "").lower()
        or low in s["session_id"].lower()
    ]
    if not candidates:
        print(f"No session matches {match!r} in the past {days} days.", file=sys.stderr)
        print("Known sessions:", file=sys.stderr)
        for s in sessions:
            print(f"  {s['session_id'][:8]}  {s.get('issue_url','')}", file=sys.stderr)
        sys.exit(1)
    if len(candidates) > 1:
        print(f"Ambiguous match {match!r}:", file=sys.stderr)
        for s in candidates:
            print(f"  {s['session_id']}  {s.get('issue_url','')}", file=sys.stderr)
        sys.exit(1)
    return candidates[0]


def walk_turns(filepath: str):
    events: list[dict] = []
    turns_by_mid: dict[str, dict] = {}
    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp", "") or ""
            kind = rec.get("type")
            msg = rec.get("message") or {}
            if kind == "user" and msg.get("role") == "user":
                content = msg.get("content", "")
                text = _re.extract_text(content)
                has_tool_result = isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content
                )
                if not text.strip() and has_tool_result:
                    events.append({"kind": "user_tool_result", "ts": ts, "text": ""})
                    continue
                if _re.COMMAND_TAG in text:
                    events.append({"kind": "user_cmd", "ts": ts, "text": text[:500]})
                else:
                    events.append({"kind": "user_reply", "ts": ts, "text": text[:500]})
            elif kind == "assistant":
                mid = msg.get("id") or rec.get("uuid") or ""
                content = msg.get("content", [])
                block_tools = []
                block_texts = []
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_use":
                            block_tools.append({"name": b.get("name", ""), "input": b.get("input") or {}})
                        elif b.get("type") == "text":
                            block_texts.append(b.get("text", ""))
                if mid in turns_by_mid:
                    turn = turns_by_mid[mid]
                    turn["tool_calls"].extend(block_tools)
                    if block_texts:
                        turn["text"] = (turn["text"] + " " + " ".join(block_texts))[:500]
                else:
                    turn = {
                        "kind": "assistant",
                        "ts": ts,
                        "mid": mid,
                        "model": msg.get("model") or "unknown",
                        "usage": msg.get("usage") or {},
                        "tool_calls": list(block_tools),
                        "text": " ".join(block_texts)[:500],
                    }
                    turns_by_mid[mid] = turn
                    events.append(turn)
    yield from events


def compute_phase_boundaries(events: list) -> dict:
    t_cmd = None
    for e in events:
        if e["kind"] == "user_cmd":
            t_cmd = e["ts"]
            break

    t_first_user_reply = t_first_spec = None
    seen_assistant = False
    for e in events:
        if t_cmd and e["ts"] < t_cmd:
            continue
        if e["kind"] == "assistant":
            seen_assistant = True
            for tc in e["tool_calls"]:
                if tc["name"] in ("Agent", "Task"):
                    desc = (tc["input"] or {}).get("description", "")
                    sa_phase = _re.classify_subagent(desc)
                    if sa_phase == "spec" and t_first_spec is None:
                        t_first_spec = e["ts"]
        elif e["kind"] == "user_reply" and seen_assistant and t_first_user_reply is None:
            t_first_user_reply = e["ts"]

    inf = "9999-99-99T99:99:99Z"
    boundaries = {
        "root-pre-cmd":    ("0000-00-00T00:00:00Z", t_cmd or inf),
        "root-scan":       (t_cmd or inf, t_first_user_reply or inf),
        "root-interview":  (t_first_user_reply or inf, t_first_spec or inf),
        "root-post-spec":  (t_first_spec or inf, inf),
    }
    return boundaries


def _fmt_tool_input(tc: dict, max_len: int = 120) -> str:
    name = tc["name"]
    inp = tc["input"] or {}
    if name in ("Agent", "Task"):
        return f"Agent({inp.get('description', '')[:80]})"
    if name == "Bash":
        cmd = (inp.get("command") or "").replace("\n", " ")
        return f"Bash({cmd[:max_len]})"
    if name == "Read":
        return f"Read({inp.get('file_path','')})"
    if name == "Write":
        content_len = len(inp.get("content", "") or "")
        return f"Write({inp.get('file_path','')}, {content_len:,}B)"
    if name == "Edit":
        return f"Edit({inp.get('file_path','')})"
    if name == "Grep":
        return f"Grep({inp.get('pattern','')[:60]!r} in {inp.get('path','.')})"
    if name == "Glob":
        return f"Glob({inp.get('pattern','')})"
    keys = list(inp.keys())[:2]
    return f"{name}({', '.join(keys)})"


def _hms(ts_a: str, ts_b: str) -> str:
    try:
        a = datetime.fromisoformat(ts_a.replace("Z", "+00:00"))
        b = datetime.fromisoformat(ts_b.replace("Z", "+00:00"))
        delta = b - a
        total = int(delta.total_seconds())
        h, rem = divmod(total, 3600)
        m, sec = divmod(rem, 60)
        return f"{h:d}h{m:02d}m{sec:02d}s" if h else f"{m:d}m{sec:02d}s"
    except Exception:
        return "?"


def analyze(session: dict, phase_key: str, top_n: int = 5) -> list[str]:
    if phase_key.startswith("sub-"):
        sub_phase = phase_key[len("sub-"):]
        matching = [sa for sa in session["subagents"] if sa["phase"] == sub_phase]
        if not matching:
            raise SystemExit(f"no {sub_phase} subagent in this session")
        # Walk each subagent jsonl; concatenate their turns in chronological order.
        all_events = []
        for sa in matching:
            all_events.extend(walk_turns(sa["file"]))
        all_events.sort(key=lambda e: e["ts"])
        assistant_events = [e for e in all_events if e["kind"] == "assistant"]
        start = assistant_events[0]["ts"] if assistant_events else ""
        end = assistant_events[-1]["ts"] if assistant_events else ""
    else:
        events = list(walk_turns(session["session_file"]))
        boundaries = compute_phase_boundaries(events)

        if phase_key not in boundaries:
            raise SystemExit(f"unknown phase {phase_key}")
        start, end = boundaries[phase_key]

        assistant_events = [
            e for e in events
            if e["kind"] == "assistant" and start <= e["ts"] < end
        ]

    for e in assistant_events:
        e["cost"] = _re.cost_usd(e["usage"], e["model"])

    total_usage = dict(_re._EMPTY_USAGE)
    for e in assistant_events:
        for k in total_usage:
            total_usage[k] += e["usage"].get(k, 0)
    total_cost = sum(e["cost"] for e in assistant_events)

    tool_turns: dict[str, int] = {}
    tool_cost: dict[str, float] = {}
    for e in assistant_events:
        seen_tools = {tc["name"] for tc in e["tool_calls"]}
        for name in seen_tools:
            tool_turns[name] = tool_turns.get(name, 0) + 1
            tool_cost[name] = tool_cost.get(name, 0.0) + e["cost"]

    lines: list[str] = []
    phase_label = _re.ROOT_PHASE_LABEL.get(phase_key, phase_key)
    lines.append(f"# Phase analysis: {phase_label}\n")
    lines.append(f"**Session:** `{session['session_id']}`  ")
    lines.append(f"**Project:** `{session['project']}`  ")
    lines.append(f"**Issue:** {session.get('issue_url') or '(free-form)'}  ")
    lines.append(f"**Invoked:** {session.get('invoked_at')}  ")
    if start != "9999-99-99T99:99:99Z" and end != "9999-99-99T99:99:99Z":
        lines.append(f"**Phase window:** {start} → {end}  ({_hms(start, end)})  ")
    else:
        lines.append(f"**Phase window:** {start} → {end}  ")
    lines.append(f"**Assistant turns:** {len(assistant_events)}  ")
    lines.append(f"**Phase cost:** **${total_cost:.2f}**  ")
    lines.append(
        f"**Tokens:** in={total_usage['input_tokens']:,}  "
        f"cw={total_usage['cache_creation_input_tokens']:,}  "
        f"cr={total_usage['cache_read_input_tokens']:,}  "
        f"out={total_usage['output_tokens']:,}  "
        f"hit%={_re.cache_hit_pct(total_usage):.0f}%"
    )
    lines.append("")

    if not assistant_events:
        lines.append("_No assistant turns fell inside this phase window._")
        return lines

    lines.append("## Tools used (turns that called tool N, summed cost of those turns)\n")
    lines.append("| Tool | Turns | Cost (of those turns) |")
    lines.append("|---|---|---|")
    for name, _cost in sorted(tool_cost.items(), key=lambda kv: -kv[1]):
        lines.append(
            f"| {name or '(text only)'} | {tool_turns.get(name, 0)} | {_re._fmt_cost(tool_cost[name])} |"
        )
    lines.append("")

    t0 = assistant_events[0]["ts"]
    lines.append("## Chronology\n")
    lines.append("| # | t+ | Model | In | CW | CR | Out | Cost | Tools |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, e in enumerate(assistant_events, 1):
        u = e["usage"]
        tool_summary = ", ".join(tc["name"] for tc in e["tool_calls"]) or "_(text)_"
        lines.append(
            f"| {i} | {_hms(t0, e['ts'])} | "
            f"`{_re._shorten_model(e['model'])}` | "
            f"{u.get('input_tokens',0):,} | "
            f"{u.get('cache_creation_input_tokens',0):,} | "
            f"{u.get('cache_read_input_tokens',0):,} | "
            f"{u.get('output_tokens',0):,} | "
            f"{_re._fmt_cost(e['cost'])} | "
            f"{tool_summary} |"
        )
    lines.append("")

    lines.append(f"## Top {top_n} most expensive turns (full detail)\n")
    top = sorted(assistant_events, key=lambda e: -e["cost"])[:top_n]
    for rank, e in enumerate(top, 1):
        u = e["usage"]
        idx = assistant_events.index(e) + 1
        lines.append(
            f"### #{rank} — turn {idx} — {_re._fmt_cost(e['cost'])} "
            f"({_re._shorten_model(e['model'])}, t+{_hms(t0, e['ts'])})"
        )
        lines.append(
            f"- in={u.get('input_tokens',0):,}  "
            f"cw={u.get('cache_creation_input_tokens',0):,}  "
            f"cr={u.get('cache_read_input_tokens',0):,}  "
            f"out={u.get('output_tokens',0):,}"
        )
        if e["text"]:
            snippet = e["text"].replace("\n", " ").strip()[:300]
            lines.append(f"- text: {snippet!r}")
        if e["tool_calls"]:
            lines.append("- tool calls:")
            for tc in e["tool_calls"]:
                lines.append(f"  - {_fmt_tool_input(tc, 200)}")
        lines.append("")

    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("match", help="substring matching issue URL or session id")
    p.add_argument("phase", help="scan|intv|post-spec|pre")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--md", default=None)
    args = p.parse_args()

    phase_key = PHASE_ALIAS.get(args.phase, args.phase)
    if not (phase_key.startswith("root-") or phase_key.startswith("sub-")):
        phase_key = "root-" + args.phase

    session = find_session(args.match, days=args.days)
    lines = analyze(session, phase_key, top_n=args.top)
    out = "\n".join(lines) + "\n"
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Wrote {args.md}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
