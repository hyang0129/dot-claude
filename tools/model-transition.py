#!/usr/bin/env python3
"""Show first/last timestamps for each model used by subagents.

Useful for spotting when a new model rollout started and the old one stopped.

Usage:
    py -3 model-transition.py [--models opus-4-6,opus-4-7]
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--models", "-m",
        help="Comma-separated model substrings to filter (default: all)",
        default=None,
    )
    return p.parse_args()


def main():
    args = parse_args()
    filters = [m.strip() for m in args.models.split(",")] if args.models else None

    projects_dir = Path.home() / ".claude" / "projects"
    # model -> {"first": ts, "last": ts, "count": int}
    stats: dict[str, dict] = defaultdict(lambda: {"first": None, "last": None, "count": 0})

    for jsonl_path in projects_dir.glob("*/*/subagents/*.jsonl"):
        file_mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            with open(jsonl_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {})
                    if not isinstance(msg, dict) or msg.get("role") != "assistant":
                        continue
                    model = msg.get("model")
                    if not model:
                        continue
                    if filters and not any(f in model for f in filters):
                        continue
                    # Prefer explicit timestamp on the entry, fall back to file mtime
                    ts = entry.get("timestamp") or file_mtime
                    s = stats[model]
                    s["count"] += 1
                    if s["first"] is None or ts < s["first"]:
                        s["first"] = ts
                    if s["last"] is None or ts > s["last"]:
                        s["last"] = ts
        except OSError:
            pass

    if not stats:
        print("No matching subagent messages found.")
        return

    BOLD = "\033[1m"
    RESET = "\033[0m"
    print(f"\n{BOLD}{'MODEL':<40}  {'FIRST SEEN':<22}  {'LAST SEEN':<22}  {'MSGS':>6}{RESET}")
    print("-" * 96)
    for model in sorted(stats, key=lambda m: stats[m]["first"] or ""):
        s = stats[model]
        print(f"{model:<40}  {s['first'] or '?':<22}  {s['last'] or '?':<22}  {s['count']:>6}")
    print()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
