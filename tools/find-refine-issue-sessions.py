#!/usr/bin/env python3
"""Find sessions where the human invoked /refine-issue in the past N days.

Adapted from find-refine-epic-sessions.py for the /refine-issue command.

Phase model for /refine-issue (see commands/refine-issue.md):
  root-pre-cmd       before the /refine-issue invocation
  root-scan          after /refine-issue up to first user reply
                     (setup, repo detection, gh issue fetch, resume check,
                      stub INTENT file write, GitHub comment stub)
  root-interview     first user reply up to Spec agent spawn (Step 2 Q&A;
                     may include inline Explore subagents)
  root-post-spec     Spec agent spawned onward (Step 4 publish + Step 5 report)
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


SESSIONS_DIR = os.path.expanduser("~/.claude/projects")

# Keywords used to classify a subagent by its meta description.
# /refine-issue spawns:
#   - one Spec agent (Step 3) — description typically contains "spec" / "refined spec" / "formalize"
#   - optional Explore agents during the interview (Step 2 preemptive lookups)
_PHASE_PATTERNS = [
    # "Refine issue …", "Refine GitHub issue …", "Refine MCP …" — the Spec agent's
    # description. Use \brefine\b so we don't match "Refiner" (a foreign workflow).
    ("spec",     re.compile(r"\bspec\b|formaliz|refined.spec|surface.area|\brefine\b", re.I)),
    ("explore",  re.compile(r"explore|codebase|\bscan\b|lookup|\bsearch\b", re.I)),
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


def collect_usage(filepath, window_start: str | None = None,
                  window_end: str | None = None):
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
                ts = record.get("timestamp") or ""
                if window_start and ts and ts < window_start:
                    continue
                if window_end and ts and ts >= window_end:
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
    "root-scan",
    "root-interview",
    "root-post-spec",
]

ROOT_PHASE_LABEL = {
    "root-pre-cmd":    "R-PRE",
    "root-scan":       "R-SCAN",
    "root-interview":  "R-INTV",
    "root-post-spec":  "R-POST-SPEC",
}

COMMAND_TAG = "<command-name>/refine-issue</command-name>"


def collect_root_phases(filepath, window_end: str | None = None):
    """Split ROOT assistant usage into sub-phases by event timeline.

    Phases:
      root-scan       before first user reply after /refine-issue
      root-interview  first user reply up to first Spec agent spawn
      root-post-spec  first Spec agent spawn onward
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
                    tag = "user_cmd" if COMMAND_TAG in text else "user_reply"
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
                            if (isinstance(block, dict)
                                    and block.get("type") == "tool_use"
                                    and block.get("name") in ("Agent", "Task")):
                                desc = (block.get("input") or {}).get("description", "")
                                events.append((ts, "task_spawn", {}, "", classify_subagent(desc)))
                    events.append((ts, "assistant", dict(usage), model, ""))
    except Exception:
        pass

    events.sort(key=lambda e: e[0])

    t_cmd = None
    for ts, tag, _u, _m, _p in events:
        if tag == "user_cmd":
            t_cmd = ts
            break

    t_first_user_reply = t_first_spec = None
    seen_assistant_since_cmd = False
    for ts, tag, _u, _m, task_phase in events:
        if t_cmd is not None and ts < t_cmd:
            continue
        if tag == "assistant":
            seen_assistant_since_cmd = True
        if tag == "user_reply" and t_first_user_reply is None and seen_assistant_since_cmd:
            t_first_user_reply = ts
        elif tag == "task_spawn":
            # Only "spec"-classified spawns mark the post-spec phase.
            # Explore spawns during interview do not.
            if task_phase == "spec" and t_first_spec is None:
                t_first_spec = ts

    def phase_for(ts: str) -> str:
        if t_cmd is not None and ts < t_cmd:
            return "root-pre-cmd"
        if t_first_user_reply is None or ts < t_first_user_reply:
            return "root-scan"
        if t_first_spec is None or ts < t_first_spec:
            return "root-interview"
        return "root-post-spec"

    phases: dict[str, dict] = {}
    for ts, tag, usage, model, _ in events:
        if tag != "assistant":
            continue
        if window_end and ts >= window_end:
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


def find_first_ts(jsonl_path: str) -> str:
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("timestamp")
                if ts:
                    return ts
    except Exception:
        pass
    return ""


def load_subagents(session_dir: str, window_start: str | None = None,
                   window_end: str | None = None) -> list[dict]:
    """Load subagents, optionally filtering to [window_start, window_end)."""
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

        first_ts = find_first_ts(jsonl_path)
        if window_start and first_ts and first_ts < window_start:
            continue
        if window_end and first_ts and first_ts >= window_end:
            continue

        # Classify: agent_type=="Explore" is always explore-class.
        # Otherwise match description against refine-issue-specific keywords.
        if agent_type == "Explore":
            phase = "explore"
        else:
            phase = classify_subagent(description)

        usage, by_model = collect_usage(jsonl_path)
        records.append({
            "agent_id": agent_id,
            "description": description,
            "agent_type": agent_type,
            "phase": phase,
            "file": jsonl_path,
            "first_ts": first_ts,
            "usage": usage,
            "usage_by_model": by_model,
        })

    phase_order = {"spec": 0, "explore": 1, "other": 2}
    records.sort(key=lambda r: (phase_order.get(r["phase"], 9), r["description"]))
    return records


_FOREIGN_SUBAGENT_PAT = re.compile(
    r"fix.?issue|review.?fix|\bE2E\b|reviewer|resolve.?issue|\brefiner\b|merge.?queue|"
    r"pr.?finalize|paranoid|rebase|e2e-qa|resume|cover letter|copy.?edit",
    re.I,
)


def find_refine_issue_window(filepath: str, cmd_ts: str) -> str | None:
    """Return end-of-window ts. The /refine-issue workflow ends at the earliest of:
      (a) next user slash-command in the session
      (b) the first ROOT assistant turn that spawns a foreign-workflow subagent
          (fix-issue, review-fix, E2E, reviewer, refiner, etc.)
    """
    best: str | None = None
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
                ts = rec.get("timestamp") or ""
                if ts <= cmd_ts:
                    continue
                kind = rec.get("type")
                msg = rec.get("message") or {}
                if kind == "user" and msg.get("role") == "user":
                    text = extract_text(msg.get("content", ""))
                    if "<command-name>/" in text and COMMAND_TAG not in text:
                        if best is None or ts < best:
                            best = ts
                elif kind == "assistant":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for b in content:
                            if (isinstance(b, dict)
                                    and b.get("type") == "tool_use"
                                    and b.get("name") in ("Agent", "Task")):
                                desc = (b.get("input") or {}).get("description", "")
                                if _FOREIGN_SUBAGENT_PAT.search(desc or ""):
                                    if best is None or ts < best:
                                        best = ts
                                    break
    except Exception:
        pass
    return best


def scan_sessions(days=7, verbose=False):
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
            if COMMAND_TAG not in text:
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

            cmd_ts = record.get("timestamp") or ""
            window_end = find_refine_issue_window(filepath, cmd_ts)

            root_usage, root_by_model = collect_usage(
                filepath, window_start=cmd_ts, window_end=window_end
            )
            root_phases = collect_root_phases(filepath, window_end=window_end)

            session_dir = os.path.join(os.path.dirname(filepath), session_id)
            subagents = load_subagents(
                session_dir, window_start=cmd_ts, window_end=window_end
            )

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


HDR_COLS  = f"{'In':>9}  {'CacheW':>9}  {'CacheR':>10}  {'Out':>8}  {'Hit%':>5}"
DIVIDER   = "-" * 110
_HR = "-" * 110
_HR2 = "=" * 110

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


def fmt_usage(usage: dict) -> str:
    return (
        f"{usage['input_tokens']:>9,}  "
        f"{usage['cache_creation_input_tokens']:>9,}  "
        f"{usage['cache_read_input_tokens']:>10,}  "
        f"{usage['output_tokens']:>8,}  "
        f"{cache_hit_pct(usage):>4.0f}%"
    )

PHASE_LABEL = {
    "spec":      "SPEC",
    "explore":   "EXPL",
    "other":     "    ",
}


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


def write_markdown(sessions, days, path):
    lines = []
    lines.append(f"# /refine-issue sessions — past {days} days\n")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ")
    lines.append(f"Sessions found: **{len(sessions)}**\n")

    if not sessions:
        lines.append("_No invocations found._\n")
    else:
        lines.append("## Summary\n")
        lines.append("| # | Invoked (UTC) | Issue | Sub | In | CacheW | CacheR | Out | Hit% | Cost |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for i, s in enumerate(sessions, 1):
            ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
            issue_short = (s["issue_url"] or "(no args)").replace("https://github.com/", "")
            issue_short = _wrap_cell(issue_short, 40)
            lines.append(
                f"| {i} | {ts} | {issue_short} | {len(s['subagents'])} | {_md_usage_row(s['total_usage'])} | {_fmt_cost(s['total_cost'])} |"
            )
        grand = {k: sum(s["total_usage"][k] for s in sessions)
                 for k in ("input_tokens", "output_tokens",
                           "cache_creation_input_tokens", "cache_read_input_tokens")}
        grand_cost = sum(s["total_cost"] for s in sessions)
        lines.append(f"| **TOT** | | | | {_md_usage_row(grand)} | **{_fmt_cost(grand_cost)}** |\n")

        lines.append("## Per-session breakdown\n")
        for i, s in enumerate(sessions, 1):
            ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
            issue_short = (s["issue_url"] or "(no args)").replace("https://github.com/", "")
            lines.append(f"### #{i} — {ts} — {issue_short}\n")
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
                desc = _wrap_cell(desc_raw, 20)
                sa_cost = cost_by_model(sa["usage_by_model"])
                lines.append(f"| {label} | {desc} | — | {_md_usage_row(sa['usage'])} | {_fmt_cost(sa_cost)} |")
                for model, mu in sorted(sa["usage_by_model"].items()):
                    c = cost_usd(mu, model)
                    lines.append(f"| | | `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(c)} |")

            lines.append(f"| **TOTAL** | | | {_md_usage_row(s['total_usage'])} | **{_fmt_cost(s['total_cost'])}** |\n")

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

        phase_agg: dict[tuple[str, str], dict] = {}
        for s in sessions:
            for ph, bucket in s.get("root_phases", {}).items():
                plabel = ROOT_PHASE_LABEL.get(ph, ph)
                for model, mu in bucket["by_model"].items():
                    agg_bucket = phase_agg.setdefault((plabel, model), _empty_usage())
                    for k in agg_bucket:
                        agg_bucket[k] += mu[k]
            for sa in s["subagents"]:
                phase_label = PHASE_LABEL.get(sa["phase"], "").strip() or "OTHER"
                for model, mu in sa["usage_by_model"].items():
                    bucket = phase_agg.setdefault((phase_label, model), _empty_usage())
                    for k in bucket:
                        bucket[k] += mu[k]

        phase_totals: dict[str, float] = {}
        for (phase, _), mu in phase_agg.items():
            phase_totals[phase] = phase_totals.get(phase, 0.0) + cost_usd(mu, _)

        phase_order = [
            "R-PRE", "R-SCAN", "R-INTV", "R-POST-SPEC",
            "SPEC", "EXPL", "OTHER",
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
        lines.append("| Phase | Cost |")
        lines.append("|---|---|")
        for phase, total in sorted(phase_totals.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {phase} | {_fmt_cost(total)} |")
        lines.append("")

        lines.append("---")
        lines.append("Phases: SPEC=spec-agent, EXPL=explore-subagents  ")
        lines.append("Hit% = cache_read / (input + cache_write + cache_read)")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def print_summary(sessions, days):
    if not sessions:
        print(f"No /refine-issue invocations found in the past {days} days.")
        return
    print(f"\nFound {len(sessions)} /refine-issue invocation(s) in the past {days} days:\n")
    print(f"{'#':<3}  {'Invoked At (UTC)':<22}  {'Issue':<45}  {'Sub':>3}  {HDR_COLS}  {'Cost':>8}")
    print(DIVIDER)
    for i, s in enumerate(sessions, 1):
        ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
        issue_short = (s["issue_url"] or "(no args)").replace("https://github.com/", "")[:45]
        t = s["total_usage"]
        nsub = len(s["subagents"])
        print(f"{i:<3}  {ts:<22}  {issue_short:<45}  {nsub:>3}  {fmt_usage(t)}  {_fmt_cost(s['total_cost']):>8}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
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
