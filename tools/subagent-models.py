#!/usr/bin/env python3
"""Report which models were used by subagents in sessions over the past N days.

Scans ~/.claude/projects/*/*/subagents/*.jsonl files and extracts the model
field from assistant messages. Subagent sessions are identified by the
isSidechain flag and their location under a parent session's subagents/ dir.

Usage:
    py -3 subagent-models.py [--days N] [--json] [--verbose]

Default: past 7 days.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=7, help="Look back N days (default 7)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--verbose", "-v", action="store_true", help="Show per-subagent detail")
    return p.parse_args()


def iter_subagent_jsonl(cutoff: datetime):
    """Yield (project, parent_session_id, agent_id, path) for recent subagent files."""
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return
    for jsonl_path in projects_dir.glob("*/*/subagents/*.jsonl"):
        mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime)
        if mtime < cutoff:
            continue
        parts = jsonl_path.parts
        # …/projects/<project>/<session_id>/subagents/<agent_id>.jsonl
        project = parts[-4]
        parent_session = parts[-3]
        agent_id = jsonl_path.stem
        yield project, parent_session, agent_id, jsonl_path, mtime


def extract_models(path: Path) -> list[str]:
    """Return all unique models seen in assistant messages in this JSONL."""
    models = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = entry.get("message", {})
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    model = msg.get("model")
                    if model:
                        models.append(model)
    except OSError:
        pass
    return models


def main():
    args = parse_args()
    cutoff = datetime.now() - timedelta(days=args.days)

    # agent_id -> {project, parent_session, models, agent_type, mtime}
    subagents = []
    model_counter: Counter = Counter()

    for project, parent_session, agent_id, path, mtime in iter_subagent_jsonl(cutoff):
        meta_path = path.with_suffix(".meta.json")
        agent_type = None
        if meta_path.exists():
            try:
                agent_type = json.loads(meta_path.read_text()).get("agentType")
            except Exception:
                pass

        models = extract_models(path)
        unique_models = list(dict.fromkeys(models))  # ordered dedup
        model_counter.update(unique_models)

        subagents.append({
            "agentId": agent_id,
            "agentType": agent_type,
            "project": project,
            "parentSession": parent_session,
            "lastUpdated": mtime.strftime("%Y-%m-%dT%H:%M:%S"),
            "models": unique_models,
            "messageCount": len(models),
        })

    subagents.sort(key=lambda s: s["lastUpdated"], reverse=True)

    if args.json:
        print(json.dumps({"subagents": subagents, "modelTotals": dict(model_counter)}, indent=2))
        return

    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[90m"

    print(f"\n{BOLD}Subagent Model Usage — past {args.days} day(s){RESET}\n")

    if not subagents:
        print("No subagent sessions found in that window.")
        return

    # Summary table
    print(f"{BOLD}Model counts (unique per subagent session):{RESET}")
    for model, count in model_counter.most_common():
        print(f"  {count:>4}x  {model}")

    print(f"\n{BOLD}Total subagent sessions:{RESET} {len(subagents)}")

    if args.verbose:
        print(f"\n{BOLD}Per-subagent detail:{RESET}")
        print(f"  {'LAST UPDATED':<20}  {'TYPE':<12}  {'MODELS':<40}  {'MSGS':>4}  PROJECT / PARENT SESSION")
        print("  " + "-" * 105)
        for s in subagents:
            models_str = ", ".join(s["models"]) if s["models"] else "(none)"
            atype = (s["agentType"] or "unknown")[:12]
            project_short = s["project"][-30:] if len(s["project"]) > 30 else s["project"]
            print(
                f"  {s['lastUpdated']:<20}  {atype:<12}  {models_str:<40}  "
                f"{s['messageCount']:>4}  {DIM}{project_short} / {s['parentSession']}{RESET}"
            )

    print()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
