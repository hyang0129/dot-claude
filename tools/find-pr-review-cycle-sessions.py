#!/usr/bin/env python3
"""Find sessions where the human invoked /pr-review-cycle in the past N days.

Usage:
    python find-pr-review-cycle-sessions.py [--days 14] [--detail] [--md PATH] [--json]

A true invocation is identified by a user message containing:
    <command-name>/pr-review-cycle</command-name>
"""

import argparse
import glob
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


SESSIONS_DIR = os.path.expanduser("~/.claude/projects")
COMMAND_TAG = "<command-name>/pr-review-cycle</command-name>"
# The skill was previously named /review-fix — include older sessions too.
COMMAND_TAGS = (
    "<command-name>/pr-review-cycle</command-name>",
    "<command-name>/review-fix</command-name>",
)


def _has_command_tag(text: str) -> bool:
    return any(t in text for t in COMMAND_TAGS)

# Subagent classification — order matters (first match wins).
_PHASE_PATTERNS = [
    ("intent",    re.compile(r"intent\s*valid|validator", re.I)),
    ("reviewer",  re.compile(r"reviewer|(initial|final)\s+(pr\s+)?review|pr\s+review|review.*cycle|cycle\s*\d+\s*review", re.I)),
    ("fixer",     re.compile(r"fixer|fix(?:\s|:|\b).*(F-|finding)", re.I)),
    ("explore",   re.compile(r"explore|codebase|scan", re.I)),
]


def classify_subagent(description: str) -> str:
    for label, pat in _PHASE_PATTERNS:
        if pat.search(description or ""):
            return label
    return "other"


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            c.get("text", "") for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    return ""


def parse_ts(ts_str):
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


_EMPTY_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
}


def _empty_usage():
    return dict(_EMPTY_USAGE)


def collect_usage(filepath):
    totals = _empty_usage()
    by_model: dict[str, dict] = {}
    seen_msg_ids = set()
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "assistant":
                    continue
                msg = record.get("message") or {}
                mid = msg.get("id")
                if mid and mid in seen_msg_ids:
                    continue
                if mid:
                    seen_msg_ids.add(mid)
                usage = msg.get("usage") or {}
                model = msg.get("model") or "unknown"
                for key in totals:
                    v = usage.get(key, 0)
                    totals[key] += v
                    by_model.setdefault(model, _empty_usage())[key] += v
    except Exception:
        pass
    return totals, by_model


ROOT_PHASES = [
    "root-pre-cmd",
    "root-setup",
    "root-post-reviewer",
    "root-post-fixer",
    "root-post-intent",
    "root-skill-done",
]

ROOT_PHASE_LABEL = {
    "root-pre-cmd":       "R-PRE",
    "root-setup":         "R-SETUP",
    "root-post-reviewer": "R-POST-REV",
    "root-post-fixer":    "R-POST-FIX",
    "root-post-intent":   "R-POST-INT",
    "root-skill-done":    "R-DONE",
}

# Sentinel the skill emits in its terminal PR-summary comment. When we see a
# Bash tool call containing this, the skill has completed — any subsequent
# ROOT work is user-continuation, not skill-attributable.
SKILL_DONE_SENTINEL = "<!-- review-fix-summary -->"


def collect_root_phases(filepath):
    """Split ROOT assistant usage by last-subagent-spawned.

    Phases, in order:
      root-pre-cmd         — before the /pr-review-cycle command.
      root-setup           — after command, before first reviewer subagent spawn.
      root-post-reviewer   — after any reviewer spawn, until a fixer spawns.
      root-post-fixer      — after any fixer spawn, until next reviewer or intent.
      root-post-intent     — after intent validator spawn.

    State transitions on every subagent spawn based on classify_subagent(desc):
      reviewer  → root-post-reviewer
      fixer     → root-post-fixer
      intent    → root-post-intent
    """
    events: list[tuple[str, str, dict, str, str]] = []
    seen_msg_ids: set[str] = set()
    try:
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
                    text = extract_text(msg.get("content", ""))
                    if not text.strip():
                        continue
                    tag = "user_cmd" if _has_command_tag(text) else "user_reply"
                    events.append((ts, tag, {}, "", ""))
                elif kind == "assistant":
                    mid = msg.get("id")
                    if mid and mid in seen_msg_ids:
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if (isinstance(block, dict)
                                        and block.get("type") == "tool_use"
                                        and block.get("name") in ("Agent", "Task")):
                                    desc = (block.get("input") or {}).get("description", "")
                                    events.append((ts, "task_spawn", {}, "", classify_subagent(desc)))
                        continue
                    if mid:
                        seen_msg_ids.add(mid)
                    usage = msg.get("usage") or {}
                    model = msg.get("model") or "unknown"
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if (block.get("type") == "tool_use"
                                    and block.get("name") in ("Agent", "Task")):
                                desc = (block.get("input") or {}).get("description", "")
                                events.append((ts, "task_spawn", {}, "", classify_subagent(desc)))
                            elif (block.get("type") == "tool_use"
                                    and block.get("name") == "Bash"):
                                cmd = (block.get("input") or {}).get("command", "") or ""
                                if SKILL_DONE_SENTINEL in cmd:
                                    events.append((ts, "skill_done_sentinel", {}, "", ""))
                    events.append((ts, "assistant", dict(usage), model, ""))
    except Exception:
        pass

    events.sort(key=lambda e: e[0])

    t_cmd = None
    for ts, tag, _u, _m, _p in events:
        if tag == "user_cmd":
            t_cmd = ts
            break

    # Build a per-timestamp phase function driven by transitions.
    # Walk events and, at each subagent spawn, record the transition timestamp.
    transitions: list[tuple[str, str]] = []  # (ts, new_phase)
    if t_cmd is not None:
        transitions.append((t_cmd, "root-setup"))

    t_first_intent = None
    for ts, tag, _u, _m, task_phase in events:
        if t_cmd is not None and ts < t_cmd:
            continue
        if tag != "task_spawn":
            continue
        if task_phase == "reviewer":
            transitions.append((ts, "root-post-reviewer"))
        elif task_phase == "fixer":
            transitions.append((ts, "root-post-fixer"))
        elif task_phase == "intent":
            transitions.append((ts, "root-post-intent"))
            if t_first_intent is None:
                t_first_intent = ts
        # explore/other do not transition

    # Terminate root-post-intent at the first of:
    #   (a) bash emitting the <!-- review-fix-summary --> PR comment — the skill's
    #       explicit terminal step
    #   (b) first user_reply after intent validator return — user has resumed
    #       driving the conversation, so anything after is continuation work
    # Turns after this boundary are classified as root-skill-done and are NOT
    # skill-attributable.
    t_done = None
    if t_first_intent is not None:
        for ts, tag, _u, _m, _p in events:
            if ts < t_first_intent:
                continue
            if tag == "skill_done_sentinel":
                t_done = ts
                break
        if t_done is None:
            for ts, tag, _u, _m, _p in events:
                if ts <= t_first_intent:
                    continue
                if tag == "user_reply":
                    t_done = ts
                    break
    if t_done is not None:
        transitions.append((t_done, "root-skill-done"))

    transitions.sort(key=lambda x: x[0])

    def phase_for(ts: str) -> str:
        if t_cmd is not None and ts < t_cmd:
            return "root-pre-cmd"
        # Find the latest transition whose ts <= given ts.
        cur = "root-pre-cmd" if t_cmd is None else "root-setup"
        for tts, newph in transitions:
            if tts <= ts:
                cur = newph
            else:
                break
        return cur

    phases: dict[str, dict] = {}
    for ts, tag, usage, model, _ in events:
        if tag != "assistant":
            continue
        ph = phase_for(ts)
        bucket = phases.setdefault(ph, {"usage": _empty_usage(), "by_model": {}})
        for k in bucket["usage"]:
            bucket["usage"][k] += usage.get(k, 0)
        mb = bucket["by_model"].setdefault(model, _empty_usage())
        for k in mb:
            mb[k] += usage.get(k, 0)
    return phases


def cache_hit_pct(usage: dict) -> float:
    total = (usage["input_tokens"]
             + usage["cache_creation_input_tokens"]
             + usage["cache_read_input_tokens"])
    if total == 0:
        return 0.0
    return usage["cache_read_input_tokens"] / total * 100


def _first_event_ts(filepath: str) -> str | None:
    """Return the first record's timestamp, used to tell when a subagent was spawned."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = rec.get("timestamp")
                if t:
                    return t
    except Exception:
        pass
    return None


def load_subagents(session_dir: str, invoked_at: str | None = None) -> list[dict]:
    """Return subagent records. If invoked_at is provided, include only
    subagents whose first event is at or after that timestamp — i.e. children
    of the /pr-review-cycle invocation, not siblings spawned earlier in the
    same chained session by other skills."""
    subagent_dir = os.path.join(session_dir, "subagents")
    if not os.path.isdir(subagent_dir):
        return []

    records = []
    for fname in sorted(os.listdir(subagent_dir)):
        if not fname.endswith(".jsonl"):
            continue
        agent_id = fname[:-len(".jsonl")]
        jsonl_path = os.path.join(subagent_dir, fname)
        meta_path = os.path.join(subagent_dir, agent_id + ".meta.json")

        description = ""
        agent_type = ""
        if os.path.isfile(meta_path):
            try:
                meta = json.loads(open(meta_path, encoding="utf-8").read())
                description = meta.get("description", "")
                agent_type = meta.get("agentType", "")
            except Exception:
                pass

        first_ts = _first_event_ts(jsonl_path)
        if invoked_at and first_ts and first_ts < invoked_at:
            continue  # sibling spawned before the command — not skill-attributable

        usage, by_model = collect_usage(jsonl_path)
        records.append({
            "agent_id": agent_id,
            "description": description,
            "agent_type": agent_type,
            "phase": classify_subagent(description),
            "file": jsonl_path,
            "first_ts": first_ts,
            "usage": usage,
            "usage_by_model": by_model,
        })

    phase_order = {"reviewer": 0, "fixer": 1, "intent": 2, "explore": 3, "other": 4}
    records.sort(key=lambda r: (phase_order.get(r["phase"], 9), r["description"]))
    return records


def scan_sessions(days=14, verbose=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    pattern = os.path.join(SESSIONS_DIR, "**", "*.jsonl")
    all_files = glob.glob(pattern, recursive=True)

    candidate_files = []
    for fp in all_files:
        if "/subagents/" in fp.replace("\\", "/"):
            continue
        try:
            mtime = os.path.getmtime(fp)
            if datetime.fromtimestamp(mtime, tz=timezone.utc) >= cutoff:
                candidate_files.append(fp)
        except OSError:
            pass

    if verbose:
        print(f"Scanning {len(candidate_files)} recently-modified session files...",
              file=sys.stderr)

    results = []
    seen_sessions = set()

    for filepath in candidate_files:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue

        session_id = os.path.splitext(os.path.basename(filepath))[0]
        project = os.path.basename(os.path.dirname(filepath))

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("type") != "user":
                continue
            msg = record.get("message") or {}
            if msg.get("role") != "user":
                continue

            text = extract_text(msg.get("content", ""))
            if not _has_command_tag(text):
                continue

            ts = parse_ts(record.get("timestamp"))
            if ts is None or ts < cutoff:
                continue

            dedup_key = (filepath, record.get("timestamp", ""))
            if dedup_key in seen_sessions:
                continue
            seen_sessions.add(dedup_key)

            args = ""
            if "<command-args>" in text:
                start = text.index("<command-args>") + len("<command-args>")
                end = text.index("</command-args>") if "</command-args>" in text else len(text)
                args = text[start:end].strip()

            root_usage, root_by_model = collect_usage(filepath)
            root_phases = collect_root_phases(filepath)

            session_dir = os.path.join(os.path.dirname(filepath), session_id)
            subagents = load_subagents(session_dir, invoked_at=record.get("timestamp"))

            total_usage = dict(root_usage)
            total_by_model: dict[str, dict] = {m: dict(u) for m, u in root_by_model.items()}
            for sa in subagents:
                for key in total_usage:
                    total_usage[key] += sa["usage"][key]
                for model, mu in sa["usage_by_model"].items():
                    bucket = total_by_model.setdefault(model, _empty_usage())
                    for key in bucket:
                        bucket[key] += mu[key]

            results.append({
                "session_id": session_id,
                "project": project,
                "invoked_at": record.get("timestamp"),
                "issue_url": args,
                "session_file": filepath,
                "root_usage": root_usage,
                "root_usage_by_model": root_by_model,
                "root_phases": root_phases,
                "root_cost": cost_by_model(root_by_model),
                "subagents": subagents,
                "total_usage": total_usage,
                "total_by_model": total_by_model,
                "total_cost": cost_by_model(total_by_model),
            })

    results.sort(key=lambda r: r["invoked_at"] or "")
    return results


# Pricing (USD/MTok, April 2026)
_PRICING = {
    "opus":   {"in": 15.0, "out": 75.0, "cw": 18.75, "cr": 1.50},
    "sonnet": {"in":  3.0, "out": 15.0, "cw":  3.75, "cr": 0.30},
    "haiku":  {"in":  1.0, "out":  5.0, "cw":  1.25, "cr": 0.10},
}


def _price_for(model: str) -> dict | None:
    m = (model or "").lower()
    for key, price in _PRICING.items():
        if key in m:
            return price
    return None


def cost_usd(usage: dict, model: str) -> float:
    p = _price_for(model)
    if p is None:
        return 0.0
    return (
        usage["input_tokens"]              * p["in"] +
        usage["output_tokens"]             * p["out"] +
        usage["cache_creation_input_tokens"] * p["cw"] +
        usage["cache_read_input_tokens"]   * p["cr"]
    ) / 1_000_000


def cost_by_model(by_model: dict) -> float:
    return sum(cost_usd(u, m) for m, u in by_model.items())


def _shorten_model(model: str) -> str:
    m = re.sub(r"^claude-", "", model)
    m = re.sub(r"-\d{8}$", "", m)
    return m


def _md_usage_row(usage: dict) -> str:
    return (
        f"{usage['input_tokens']:,} | "
        f"{usage['cache_creation_input_tokens']:,} | "
        f"{usage['cache_read_input_tokens']:,} | "
        f"{usage['output_tokens']:,} | "
        f"{cache_hit_pct(usage):.0f}%"
    )


def _fmt_cost(c: float) -> str:
    if c == 0:
        return "—"
    if c < 0.01:
        return f"${c:.4f}"
    return f"${c:.2f}"


def _wrap_cell(text: str, width: int = 20) -> str:
    text = (text or "").replace("|", "\\|").replace("\n", " ").strip()
    if not text:
        return ""
    import textwrap as _tw
    chunks = _tw.wrap(text, width=width, break_long_words=True, break_on_hyphens=False)
    return "<br>".join(chunks) if chunks else text


PHASE_LABEL = {
    "reviewer": "REV",
    "fixer":    "FIX",
    "intent":   "INT",
    "explore":  "EXPL",
    "other":    "    ",
}


def write_markdown(sessions, days, path):
    lines = []
    lines.append(f"# /pr-review-cycle sessions — past {days} days\n")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ")
    lines.append(f"Sessions found: **{len(sessions)}**\n")

    if not sessions:
        lines.append("_No invocations found._\n")
    else:
        lines.append("## Summary\n")
        lines.append("| # | Invoked (UTC) | Args | Sub | In | CacheW | CacheR | Out | Hit% | Cost |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for i, s in enumerate(sessions, 1):
            ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
            args_short = _wrap_cell(s["issue_url"] or "(no args)", 40)
            lines.append(
                f"| {i} | {ts} | {args_short} | {len(s['subagents'])} | {_md_usage_row(s['total_usage'])} | {_fmt_cost(s['total_cost'])} |"
            )
        grand = {k: sum(s["total_usage"][k] for s in sessions)
                 for k in ("input_tokens", "output_tokens",
                           "cache_creation_input_tokens", "cache_read_input_tokens")}
        grand_cost = sum(s["total_cost"] for s in sessions)
        lines.append(f"| **TOT** | | | | {_md_usage_row(grand)} | **{_fmt_cost(grand_cost)}** |\n")

        lines.append("## Per-session breakdown\n")
        for i, s in enumerate(sessions, 1):
            ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
            lines.append(f"### #{i} — {ts} — {s['issue_url'] or '(no args)'}\n")
            lines.append(f"- project: `{s['project']}`")
            lines.append(f"- session: `{s['session_id']}`")
            lines.append(f"- subagents: {len(s['subagents'])}\n")

            lines.append("| Role | Description | Model | In | CacheW | CacheR | Out | Hit% | Cost |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            lines.append(f"| ROOT | (orchestrator) | — | {_md_usage_row(s['root_usage'])} | {_fmt_cost(s['root_cost'])} |")
            for model, mu in sorted(s["root_usage_by_model"].items()):
                c = cost_usd(mu, model)
                lines.append(f"| | | `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(c)} |")

            for ph in ROOT_PHASES:
                if ph not in s["root_phases"]:
                    continue
                bucket = s["root_phases"][ph]
                pu, pmbm = bucket["usage"], bucket["by_model"]
                plabel = ROOT_PHASE_LABEL[ph]
                p_cost = cost_by_model(pmbm)
                lines.append(f"| {plabel} | _(root sub-phase)_ | — | {_md_usage_row(pu)} | {_fmt_cost(p_cost)} |")
                for model, mu in sorted(pmbm.items()):
                    c = cost_usd(mu, model)
                    lines.append(f"| | | `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(c)} |")

            for sa in s["subagents"]:
                label = PHASE_LABEL.get(sa["phase"], "").strip() or "—"
                desc_raw = sa["description"] or sa["agent_type"] or sa["agent_id"][:16]
                desc = _wrap_cell(desc_raw, 24)
                sa_cost = cost_by_model(sa["usage_by_model"])
                lines.append(f"| {label} | {desc} | — | {_md_usage_row(sa['usage'])} | {_fmt_cost(sa_cost)} |")
                for model, mu in sorted(sa["usage_by_model"].items()):
                    c = cost_usd(mu, model)
                    lines.append(f"| | | `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(c)} |")

            lines.append(f"| **TOTAL** | | | {_md_usage_row(s['total_usage'])} | **{_fmt_cost(s['total_cost'])}** |\n")

        # Aggregate by model
        agg: dict[str, dict] = {}
        for s in sessions:
            for model, mu in s.get("total_by_model", {}).items():
                bucket = agg.setdefault(model, _empty_usage())
                for k in bucket:
                    bucket[k] += mu[k]
        lines.append("## Aggregate by model (all sessions)\n")
        lines.append("| Model | In | CacheW | CacheR | Out | Hit% | Cost |")
        lines.append("|---|---|---|---|---|---|---|")
        for model, mu in sorted(agg.items(), key=lambda kv: -cost_usd(kv[1], kv[0])):
            lines.append(f"| `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(cost_usd(mu, model))} |")
        lines.append("")

        # Aggregate by (phase, model)
        phase_agg: dict[tuple[str, str], dict] = {}
        for s in sessions:
            for ph, bucket in s.get("root_phases", {}).items():
                plabel = ROOT_PHASE_LABEL.get(ph, ph)
                for model, mu in bucket["by_model"].items():
                    b = phase_agg.setdefault((plabel, model), _empty_usage())
                    for k in b:
                        b[k] += mu[k]
            for sa in s["subagents"]:
                phase_label = PHASE_LABEL.get(sa["phase"], "").strip() or "OTHER"
                for model, mu in sa["usage_by_model"].items():
                    b = phase_agg.setdefault((phase_label, model), _empty_usage())
                    for k in b:
                        b[k] += mu[k]

        phase_totals: dict[str, float] = {}
        for (phase, model), mu in phase_agg.items():
            phase_totals[phase] = phase_totals.get(phase, 0.0) + cost_usd(mu, model)

        phase_order = [
            "R-PRE", "R-SETUP", "R-POST-REV", "R-POST-FIX", "R-POST-INT", "R-DONE",
            "REV", "FIX", "INT", "EXPL", "OTHER",
        ]
        def _phase_sort_key(phase: str):
            return (phase_order.index(phase) if phase in phase_order else 99, phase)

        lines.append("## Aggregate by phase and model (all sessions)\n")
        lines.append("| Phase | Model | In | CacheW | CacheR | Out | Hit% | Cost |")
        lines.append("|---|---|---|---|---|---|---|---|")
        seen_phases: set[str] = set()
        for (phase, model) in sorted(
            phase_agg.keys(),
            key=lambda pm: (_phase_sort_key(pm[0]), -cost_usd(phase_agg[pm], pm[1])),
        ):
            mu = phase_agg[(phase, model)]
            phase_cell = phase if phase not in seen_phases else ""
            if phase not in seen_phases:
                seen_phases.add(phase)
            lines.append(
                f"| {phase_cell} | `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(cost_usd(mu, model))} |"
            )
        lines.append("")
        lines.append("### Phase totals\n")
        lines.append("| Phase | Cost | % of grand |")
        lines.append("|---|---|---|")
        gc = sum(phase_totals.values()) or 1.0
        for phase, total in sorted(phase_totals.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {phase} | {_fmt_cost(total)} | {total/gc*100:.1f}% |")
        lines.append("")

        lines.append("---")
        lines.append("Phases: REV=reviewer, FIX=fixer, INT=intent-validator, EXPL=explore  ")
        lines.append("ROOT sub-phases: R-PRE, R-SETUP, R-POST-REV (after reviewer returns, orchestrator planning),")
        lines.append("R-POST-FIX (after fixer spawn; wait/verify/commit), R-POST-INT (after intent validator spawn).  ")
        lines.append("Hit% = cache_read / (input + cache_write + cache_read)")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def print_summary(sessions, days):
    if not sessions:
        print(f"No /pr-review-cycle invocations found in the past {days} days.")
        return
    print(f"\nFound {len(sessions)} /pr-review-cycle invocation(s) in the past {days} days:\n")
    print(f"{'#':<3}  {'Invoked At (UTC)':<22}  {'Args':<40}  {'Sub':>3}  {'Cost':>8}")
    print("-" * 90)
    for i, s in enumerate(sessions, 1):
        ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
        args_short = (s["issue_url"] or "(no args)")[:40]
        print(f"{i:<3}  {ts:<22}  {args_short:<40}  {len(s['subagents']):>3}  {_fmt_cost(s['total_cost']):>8}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--md", metavar="PATH", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    sessions = scan_sessions(days=args.days, verbose=True)

    if args.json:
        print(json.dumps(sessions, indent=2))
        return
    if args.md:
        write_markdown(sessions, args.days, args.md)
        print(f"Wrote markdown report to {args.md}", file=sys.stderr)
        return
    print_summary(sessions, args.days)


if __name__ == "__main__":
    main()
