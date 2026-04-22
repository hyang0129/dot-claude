#!/usr/bin/env python3
"""Find sessions where the human invoked /refine-epic in the past N days.

Usage:
    python find-refine-epic-sessions.py [--days 3] [--detail] [--json]

A true invocation is identified by a user message containing:
    <command-name>/refine-epic</command-name>

This tag is only injected by the Claude Code harness when the human types
the slash command — it is NOT present in AI-generated text that merely
mentions the skill name.
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
_PHASE_PATTERNS = [
    ("challenger",  re.compile(r"challenger", re.I)),
    ("researcher",  re.compile(r"research", re.I)),
    ("publisher",   re.compile(r"publish", re.I)),
    ("surrogate",   re.compile(r"surrogate|refine.issue", re.I)),
    ("explore",     re.compile(r"explore|codebase.scan|scan", re.I)),
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
    """Sum all non-duplicate assistant usage entries in a JSONL file.

    Returns (totals_dict, by_model_dict) where by_model maps model name -> usage dict.
    """
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
                # One API response can span multiple JSONL records (one per content
                # block) all carrying the same usage. Dedup on message.id, not the
                # per-record uuid, or costs would be multiplied.
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
    "root-post-challenger",
    "root-post-researcher",
    "root-post-surrogate",
]

ROOT_PHASE_LABEL = {
    "root-pre-cmd":          "R-PRE",
    "root-scan":             "R-SCAN",
    "root-interview":        "R-INTV",
    "root-post-challenger":  "R-POST-CHAL",
    "root-post-researcher":  "R-POST-RESE",
    "root-post-surrogate":   "R-POST-SURR",
}


def collect_root_phases(filepath):
    """Split ROOT assistant usage into heuristic sub-phases by event timeline.

    Phases, in order:
      root-scan            — before the user's first reply after /refine-epic (Sub-phase 1 scan).
      root-interview       — first user reply up to first subagent (Agent) spawn (Sub-phases 2–4).
      root-post-challenger — first Agent spawn up to first researcher spawn (rebuttal + publish).
      root-post-researcher — first researcher spawn up to first surrogate spawn (decomposition).
      root-post-surrogate  — first surrogate spawn onward (consumption + final summary).
    When a transition is missing (e.g. no researcher spawned), later phases collapse into the
    last reached phase naturally.
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
                        continue  # tool_result-only turn
                    tag = "user_cmd" if "<command-name>/refine-epic</command-name>" in text else "user_reply"
                    events.append((ts, tag, {}, "", ""))
                elif kind == "assistant":
                    mid = msg.get("id")
                    if mid and mid in seen_msg_ids:
                        # Still scan content for task spawns (tool_use blocks are
                        # spread across records for one API message).
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

    t_first_user_reply = t_first_chal = t_first_rese = t_first_surr = None
    seen_assistant_since_cmd = False
    for ts, tag, _u, _m, task_phase in events:
        if t_cmd is not None and ts < t_cmd:
            continue  # ignore pre-command history for boundary detection
        if tag == "assistant":
            seen_assistant_since_cmd = True
        if tag == "user_reply" and t_first_user_reply is None and seen_assistant_since_cmd:
            # A "user_reply" before any assistant turn is typically harness-injected
            # skill-prompt content, not a real human reply.
            t_first_user_reply = ts
        elif tag == "task_spawn":
            # Explore/other early subagents (Sub-phase 1 scan support) don't mark a
            # phase boundary. Only the pipeline-structural spawns do.
            if task_phase == "challenger" and t_first_chal is None:
                t_first_chal = ts
            if task_phase == "researcher" and t_first_rese is None:
                t_first_rese = ts
            if task_phase == "surrogate" and t_first_surr is None:
                t_first_surr = ts

    def phase_for(ts: str) -> str:
        if t_cmd is not None and ts < t_cmd:
            return "root-pre-cmd"
        if t_first_user_reply is None or ts < t_first_user_reply:
            return "root-scan"
        if t_first_chal is None or ts < t_first_chal:
            return "root-interview"
        if t_first_rese is None or ts < t_first_rese:
            return "root-post-challenger"
        if t_first_surr is None or ts < t_first_surr:
            return "root-post-researcher"
        return "root-post-surrogate"

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
    """Fraction of input tokens served from cache (reads / total input-side tokens)."""
    total = (usage["input_tokens"]
             + usage["cache_creation_input_tokens"]
             + usage["cache_read_input_tokens"])
    if total == 0:
        return 0.0
    return usage["cache_read_input_tokens"] / total * 100


def load_subagents(session_dir: str) -> list[dict]:
    """Return one record per subagent JSONL, enriched with meta description."""
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

        usage, by_model = collect_usage(jsonl_path)
        records.append({
            "agent_id": agent_id,
            "description": description,
            "agent_type": agent_type,
            "phase": classify_subagent(description),
            "file": jsonl_path,
            "usage": usage,
            "usage_by_model": by_model,
        })

    # Sort by phase order for readability
    phase_order = {"challenger": 0, "explore": 1, "researcher": 2, "publisher": 3, "surrogate": 4, "other": 5}
    records.sort(key=lambda r: (phase_order.get(r["phase"], 9), r["description"]))
    return records


def scan_sessions(days=3, verbose=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    pattern = os.path.join(SESSIONS_DIR, "**", "*.jsonl")
    all_files = glob.glob(pattern, recursive=True)

    candidate_files = []
    for fp in all_files:
        # Skip subagent files — they are children, not roots
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
            if "<command-name>/refine-epic</command-name>" not in text:
                continue

            ts = parse_ts(record.get("timestamp"))
            if ts is None or ts < cutoff:
                continue

            dedup_key = (filepath, record.get("timestamp", ""))
            if dedup_key in seen_sessions:
                continue
            seen_sessions.add(dedup_key)

            # Extract issue URL from <command-args>
            args = ""
            if "<command-args>" in text:
                start = text.index("<command-args>") + len("<command-args>")
                end = text.index("</command-args>") if "</command-args>" in text else len(text)
                args = text[start:end].strip()

            root_usage, root_by_model = collect_usage(filepath)
            root_phases = collect_root_phases(filepath)

            session_dir = os.path.join(os.path.dirname(filepath), session_id)
            subagents = load_subagents(session_dir)

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


# ── formatting helpers ────────────────────────────────────────────────────────

HDR_COLS  = f"{'In':>9}  {'CacheW':>9}  {'CacheR':>10}  {'Out':>8}  {'Hit%':>5}"
DIVIDER   = "-" * 110

# Windows cmd/powershell often uses cp1252; avoid Unicode box-drawing chars
_HR = "-" * 110
_HR2 = "=" * 110

# Per-MTok pricing (USD). Keys match substrings of short model names.
# Cache write = 1.25x input; cache read = 0.1x input.
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
    """Collapse verbose model IDs to a readable short form."""
    # e.g. claude-sonnet-4-6 -> sonnet-4-6, claude-opus-4-7-20251101 -> opus-4-7
    m = re.sub(r"^claude-", "", model)
    m = re.sub(r"-\d{8}$", "", m)  # strip trailing date stamps
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
    "challenger": "CHAL",
    "researcher": "RESE",
    "publisher":  "PUBL",
    "surrogate":  "SURR",
    "explore":    "EXPL",
    "other":      "    ",
}


def print_summary(sessions, days):
    if not sessions:
        print(f"No /refine-epic invocations found in the past {days} days.")
        return

    print(f"\nFound {len(sessions)} /refine-epic invocation(s) in the past {days} days:\n")
    print(f"{'#':<3}  {'Invoked At (UTC)':<22}  {'Issue':<45}  {'Sub':>3}  {HDR_COLS}")
    print(DIVIDER)

    for i, s in enumerate(sessions, 1):
        ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
        issue_short = (s["issue_url"] or "(no args)").replace("https://github.com/", "")
        t = s["total_usage"]
        nsub = len(s["subagents"])
        print(f"{i:<3}  {ts:<22}  {issue_short:<45}  {nsub:>3}  {fmt_usage(t)}")

    print()
    grand = {k: sum(s["total_usage"][k] for s in sessions)
             for k in ("input_tokens", "output_tokens",
                       "cache_creation_input_tokens", "cache_read_input_tokens")}
    print(f"{'TOT':<3}  {'':22}  {'':45}  {'':3}  {fmt_usage(grand)}")
    print()
    print("In=input  CacheW=cache_write  CacheR=cache_read  Out=output  Hit%=cache_read/(all input)")


def print_detail(sessions, days):
    if not sessions:
        print(f"No /refine-epic invocations found in the past {days} days.")
        return

    print(f"\nFound {len(sessions)} /refine-epic invocation(s) in the past {days} days:\n")

    for i, s in enumerate(sessions, 1):
        ts = s["invoked_at"][:19].replace("T", " ") if s["invoked_at"] else "unknown"
        issue_short = (s["issue_url"] or "(no args)").replace("https://github.com/", "")
        nsub = len(s["subagents"])

        print(_HR2)
        print(f"  #{i}  {ts}  |  {issue_short}  |  {nsub} subagent(s)")
        print(f"  project: {s['project']}   session: {s['session_id'][:8]}...")
        print(_HR)
        print(f"  {'Role':<8}  {'Description':<48}  {HDR_COLS}")
        print(f"  {'-'*8}  {'-'*48}  {'-'*50}")

        # Root orchestrator row
        print(f"  {'ROOT':<8}  {'(orchestrator)':<48}  {fmt_usage(s['root_usage'])}")
        for model, mu in sorted(s["root_usage_by_model"].items()):
            mshort = _shorten_model(model)
            print(f"  {'':8}  {'  ' + mshort:<48}  {fmt_usage(mu)}")

        # Per-subagent rows
        for sa in s["subagents"]:
            label = PHASE_LABEL.get(sa["phase"], "    ")
            desc = (sa["description"] or sa["agent_type"] or sa["agent_id"][:16])[:48]
            print(f"  {label:<8}  {desc:<48}  {fmt_usage(sa['usage'])}")
            for model, mu in sorted(sa["usage_by_model"].items()):
                mshort = _shorten_model(model)
                print(f"  {'':8}  {'  ' + mshort:<48}  {fmt_usage(mu)}")

        # Session total
        print(f"  {'-'*8}  {'-'*48}  {'-'*50}")
        print(f"  {'TOTAL':<8}  {'':<48}  {fmt_usage(s['total_usage'])}")
        print()

    # Grand total across all sessions
    grand = {k: sum(s["total_usage"][k] for s in sessions)
             for k in ("input_tokens", "output_tokens",
                       "cache_creation_input_tokens", "cache_read_input_tokens")}
    print(_HR2)
    print(f"  {'GRAND':<8}  {f'({len(sessions)} sessions)':<48}  {fmt_usage(grand)}")
    print()
    print("Phases — CHAL=challenger  RESE=researcher  PUBL=publisher  SURR=surrogate  EXPL=explore")
    print("Hit% = cache_read / (input + cache_write + cache_read)")


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
    """Wrap text in a markdown table cell using <br> at word boundaries."""
    text = (text or "").replace("|", "\\|").replace("\n", " ").strip()
    if not text:
        return ""
    import textwrap as _tw
    chunks = _tw.wrap(text, width=width, break_long_words=True, break_on_hyphens=False)
    return "<br>".join(chunks) if chunks else text


def write_markdown(sessions, days, path):
    lines = []
    lines.append(f"# /refine-epic sessions — past {days} days\n")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ")
    lines.append(f"Sessions found: **{len(sessions)}**\n")

    if not sessions:
        lines.append("_No invocations found._\n")
    else:
        # Summary table
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

        # Per-session detail
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

            # Root row + model rows
            lines.append(f"| ROOT | (orchestrator) | — | {_md_usage_row(s['root_usage'])} | {_fmt_cost(s['root_cost'])} |")
            for model, mu in sorted(s["root_usage_by_model"].items()):
                c = cost_usd(mu, model)
                lines.append(f"| | | `{_shorten_model(model)}` | {_md_usage_row(mu)} | {_fmt_cost(c)} |")

            # Root sub-phase rows (heuristic)
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

            # Subagents
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

        # Aggregate by model across all sessions
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

        # Aggregate by (phase, model) — ROOT is split into sub-phases.
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
            "R-PRE", "R-SCAN", "R-INTV", "R-POST-CHAL", "R-POST-RESE", "R-POST-SURR",
            "CHAL", "EXPL", "RESE", "PUBL", "SURR", "OTHER",
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
        # Phase subtotal rows
        lines.append("")
        lines.append("### Phase totals\n")
        lines.append("| Phase | Cost |")
        lines.append("|---|---|")
        for phase, total in sorted(phase_totals.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {phase} | {_fmt_cost(total)} |")
        lines.append("")

        lines.append("---")
        lines.append("Phases: CHAL=challenger, RESE=researcher, PUBL=publisher, SURR=surrogate, EXPL=explore  ")
        lines.append("Hit% = cache_read / (input + cache_write + cache_read)")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=3,
                        help="Look back N days (default: 3)")
    parser.add_argument("--detail", action="store_true",
                        help="Show per-subagent breakdown with phase labels and cache hit %%")
    parser.add_argument("--md", metavar="PATH", default=None,
                        help="Write a Markdown report to PATH")
    parser.add_argument("--json", action="store_true",
                        help="Emit raw JSON array instead of summary table")
    args = parser.parse_args()

    sessions = scan_sessions(days=args.days, verbose=True)

    if args.json:
        print(json.dumps(sessions, indent=2))
        return

    if args.md:
        write_markdown(sessions, args.days, args.md)
        print(f"Wrote markdown report to {args.md}", file=sys.stderr)
        return

    if args.detail:
        print_detail(sessions, args.days)
    else:
        print_summary(sessions, args.days)


if __name__ == "__main__":
    main()
