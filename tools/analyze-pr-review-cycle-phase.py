#!/usr/bin/env python3
"""In-depth analysis of a single /pr-review-cycle session's phase or a subagent.

Usage:
    python analyze-pr-review-cycle-phase.py <match> <phase> [--top N] [--md PATH]

Args:
    match   substring matching the session id or args (e.g. "d2987528" or "886")
    phase   one of:
              pre | setup | post-rev | post-fix | post-int      (ROOT sub-phases)
              rev:<substr>                                       (a reviewer subagent)
              fix:<substr>                                       (a fixer subagent)
              int:<substr>                                       (intent validator)
              sub:<substr>                                       (any subagent by description)

Flags:
    --top N   show full tool-input detail for the N most expensive turns (default 6)
    --md PATH write a markdown report to PATH instead of stdout
    --days D  look-back window (default 60)
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime


_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "prrc_sessions", os.path.join(_HERE, "find-pr-review-cycle-sessions.py"),
)
_prrc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prrc)


PHASE_ALIAS = {
    "pre":       "root-pre-cmd",
    "setup":     "root-setup",
    "post-rev":  "root-post-reviewer",
    "post-fix":  "root-post-fixer",
    "post-int":  "root-post-intent",
}


def find_session(match: str, days: int):
    sessions = _prrc.scan_sessions(days=days)
    low = match.lower()
    candidates = [
        s for s in sessions
        if low in (s.get("issue_url") or "").lower()
        or low in s["session_id"].lower()
    ]
    if not candidates:
        print(f"No session matches {match!r} in the past {days} days.", file=sys.stderr)
        for s in sessions:
            print(f"  {s['session_id'][:8]}  {s.get('issue_url','')}", file=sys.stderr)
        sys.exit(1)
    if len(candidates) > 1:
        print(f"Ambiguous match {match!r}:", file=sys.stderr)
        for s in candidates:
            print(f"  {s['session_id']}  {s.get('issue_url','')}", file=sys.stderr)
        sys.exit(1)
    return candidates[0]


def walk_turns(filepath: str, command_tag=None):
    """Yield events from a JSONL file, with assistant turns merged by message.id."""
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
                text = _prrc.extract_text(content)
                has_tool_result = isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content
                )
                if not text.strip() and has_tool_result:
                    events.append({"kind": "user_tool_result", "ts": ts, "text": ""})
                    continue
                tags = command_tag if isinstance(command_tag, (list, tuple)) else ([command_tag] if command_tag else [])
                if any(t and t in text for t in tags):
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


def compute_root_boundaries(events: list) -> dict:
    """Return {phase_key: (start_ts_inclusive, end_ts_exclusive)}."""
    t_cmd = None
    for e in events:
        if e["kind"] == "user_cmd":
            t_cmd = e["ts"]
            break

    transitions: list[tuple[str, str]] = []
    for e in events:
        if t_cmd and e["ts"] < t_cmd:
            continue
        if e["kind"] != "assistant":
            continue
        for tc in e["tool_calls"]:
            if tc["name"] not in ("Agent", "Task"):
                continue
            desc = (tc["input"] or {}).get("description", "")
            sa_phase = _prrc.classify_subagent(desc)
            if sa_phase == "reviewer":
                transitions.append((e["ts"], "root-post-reviewer"))
            elif sa_phase == "fixer":
                transitions.append((e["ts"], "root-post-fixer"))
            elif sa_phase == "intent":
                transitions.append((e["ts"], "root-post-intent"))

    inf = "9999-99-99T99:99:99Z"
    pre_end = t_cmd or inf
    # Find each transition's first occurrence in order to compute phase ranges.
    first_rev = next((ts for ts, p in transitions if p == "root-post-reviewer"), None)
    first_fix = next((ts for ts, p in transitions if p == "root-post-fixer"), None)
    first_int = next((ts for ts, p in transitions if p == "root-post-intent"), None)

    # Setup phase ends at the first subagent spawn (any of the three).
    setup_end = min([t for t in (first_rev, first_fix, first_int) if t] or [inf])

    # Remaining phases are "approximate" — for multi-cycle the same phase can recur.
    # We report all turns whose *last-transition* state matches the phase label.
    return {
        "root-pre-cmd":       ("0000-00-00T00:00:00Z", pre_end),
        "root-setup":         (t_cmd or inf, setup_end),
        # These three are not contiguous in multi-cycle runs; use state-classifier below.
        "root-post-reviewer": (first_rev or inf, inf),
        "root-post-fixer":    (first_fix or inf, inf),
        "root-post-intent":   (first_int or inf, inf),
    }


def state_at(ts: str, t_cmd: str | None, transitions: list[tuple[str, str]]) -> str:
    if t_cmd is not None and ts < t_cmd:
        return "root-pre-cmd"
    cur = "root-setup" if t_cmd is not None else "root-pre-cmd"
    for tts, newph in transitions:
        if tts <= ts:
            cur = newph
        else:
            break
    return cur


def _fmt_tool_input(tc: dict, max_len: int = 200) -> str:
    name = tc["name"]
    inp = tc["input"] or {}
    if name in ("Agent", "Task"):
        return f"Agent({inp.get('description', '')[:120]}, type={inp.get('subagent_type','')})"
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


def _fmt_cost(c: float) -> str:
    if c == 0:
        return "—"
    if c < 0.01:
        return f"${c:.4f}"
    return f"${c:.2f}"


def analyze_root_phase(session: dict, phase_key: str, top_n: int) -> list[str]:
    events = list(walk_turns(session["session_file"], _prrc.COMMAND_TAGS))
    events.sort(key=lambda e: e["ts"])

    t_cmd = next((e["ts"] for e in events if e["kind"] == "user_cmd"), None)
    transitions = []
    for e in events:
        if e["kind"] != "assistant":
            continue
        if t_cmd and e["ts"] < t_cmd:
            continue
        for tc in e["tool_calls"]:
            if tc["name"] not in ("Agent", "Task"):
                continue
            desc = (tc["input"] or {}).get("description", "")
            sa_phase = _prrc.classify_subagent(desc)
            if sa_phase == "reviewer":
                transitions.append((e["ts"], "root-post-reviewer"))
            elif sa_phase == "fixer":
                transitions.append((e["ts"], "root-post-fixer"))
            elif sa_phase == "intent":
                transitions.append((e["ts"], "root-post-intent"))

    assistant_events = [
        e for e in events
        if e["kind"] == "assistant"
        and state_at(e["ts"], t_cmd, transitions) == phase_key
    ]

    return _format_report(session, phase_key, assistant_events, top_n)


def analyze_subagent(session: dict, sub_match: str, top_n: int) -> list[str]:
    low = sub_match.lower()
    matches = [sa for sa in session["subagents"]
               if low in sa["description"].lower() or low in sa["agent_id"].lower()]
    if not matches:
        print(f"No subagent matches {sub_match!r}. Known:", file=sys.stderr)
        for sa in session["subagents"]:
            print(f"  {sa['phase']:>9}  {sa['agent_id'][:10]}  {sa['description']}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Ambiguous subagent match {sub_match!r}:", file=sys.stderr)
        for sa in matches:
            print(f"  {sa['phase']:>9}  {sa['agent_id'][:10]}  {sa['description']}", file=sys.stderr)
        sys.exit(1)
    sa = matches[0]
    events = list(walk_turns(sa["file"], command_tag=None))
    events.sort(key=lambda e: e["ts"])
    assistant_events = [e for e in events if e["kind"] == "assistant"]
    label = f"subagent:{sa['phase']} — {sa['description']}"
    return _format_report(session, label, assistant_events, top_n, subagent=sa)


def _format_report(session, phase_key, assistant_events, top_n, subagent=None):
    for e in assistant_events:
        e["cost"] = _prrc.cost_usd(e["usage"], e["model"])
    total_usage = _prrc._empty_usage()
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
    lines.append(f"# /pr-review-cycle phase analysis: {phase_key}\n")
    lines.append(f"**Session:** `{session['session_id']}`  ")
    lines.append(f"**Project:** `{session['project']}`  ")
    lines.append(f"**Args:** {session.get('issue_url') or '(free-form)'}  ")
    lines.append(f"**Invoked:** {session.get('invoked_at')}  ")
    if subagent:
        lines.append(f"**Subagent file:** `{subagent['file']}`  ")
    lines.append(f"**Assistant turns:** {len(assistant_events)}  ")
    lines.append(f"**Phase cost:** **{_fmt_cost(total_cost)}**  ")
    lines.append(
        f"**Tokens:** in={total_usage['input_tokens']:,}  "
        f"cw={total_usage['cache_creation_input_tokens']:,}  "
        f"cr={total_usage['cache_read_input_tokens']:,}  "
        f"out={total_usage['output_tokens']:,}  "
        f"hit%={_prrc.cache_hit_pct(total_usage):.0f}%"
    )
    lines.append("")

    if not assistant_events:
        lines.append("_No assistant turns fell inside this phase window._")
        return lines

    lines.append("## Tools used (turns that called tool N, summed cost of those turns)\n")
    lines.append("| Tool | Turns | Cost |")
    lines.append("|---|---|---|")
    for name, _c in sorted(tool_cost.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name or '(text only)'} | {tool_turns.get(name, 0)} | {_fmt_cost(tool_cost[name])} |")
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
            f"`{_prrc._shorten_model(e['model'])}` | "
            f"{u.get('input_tokens',0):,} | "
            f"{u.get('cache_creation_input_tokens',0):,} | "
            f"{u.get('cache_read_input_tokens',0):,} | "
            f"{u.get('output_tokens',0):,} | "
            f"{_fmt_cost(e['cost'])} | "
            f"{tool_summary} |"
        )
    lines.append("")

    lines.append(f"## Top {top_n} most expensive turns (full detail)\n")
    top = sorted(assistant_events, key=lambda e: -e["cost"])[:top_n]
    for rank, e in enumerate(top, 1):
        u = e["usage"]
        idx = assistant_events.index(e) + 1
        lines.append(
            f"### #{rank} — turn {idx} — {_fmt_cost(e['cost'])} "
            f"({_prrc._shorten_model(e['model'])}, t+{_hms(t0, e['ts'])})"
        )
        lines.append(
            f"- in={u.get('input_tokens',0):,}  "
            f"cw={u.get('cache_creation_input_tokens',0):,}  "
            f"cr={u.get('cache_read_input_tokens',0):,}  "
            f"out={u.get('output_tokens',0):,}"
        )
        if e["text"]:
            snippet = e["text"].replace("\n", " ").strip()[:400]
            lines.append(f"- text: {snippet!r}")
        if e["tool_calls"]:
            lines.append("- tool calls:")
            for tc in e["tool_calls"]:
                lines.append(f"  - {_fmt_tool_input(tc, 300)}")
        lines.append("")

    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("match", help="substring matching args or session id")
    p.add_argument("phase", help="pre|setup|post-rev|post-fix|post-int | rev:|fix:|int:|sub:<substr>")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--md", default=None)
    args = p.parse_args()

    session = find_session(args.match, days=args.days)

    ph = args.phase
    m = re.match(r"^(rev|fix|int|sub):(.+)$", ph)
    if m:
        lines = analyze_subagent(session, m.group(2), top_n=args.top)
    else:
        phase_key = PHASE_ALIAS.get(ph, ph if ph.startswith("root-") else "root-" + ph)
        lines = analyze_root_phase(session, phase_key, top_n=args.top)

    out = "\n".join(lines) + "\n"
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Wrote {args.md}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
