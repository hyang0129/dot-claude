#!/usr/bin/env python3
"""Inventory the transcript corpus: files, sessions, projects, date span.

A "session" = one top-level transcript file (one sessionId) under
~/.claude/projects/<project>/. Subagent/workflow transcripts live under
*/subagents/ and */workflows/ and are NOT separate user sessions — they're
child agents spawned inside a parent session. This counts both.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from collections import defaultdict

PROJECTS = Path.home() / ".claude" / "projects"

SYSREMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
IDE_WRAP = re.compile(r"<ide_[\w]+>.*?</ide_[\w]+>", re.DOTALL)
NOISE = ("<task-notification>", "[Request interrupted")


def is_genuine(content):
    """True iff this user record is human-authored prose (not a tool result/noise)."""
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "tool_result":
                    return False
                if b.get("type") == "text" and b.get("text"):
                    parts.append(b["text"])
        raw = "\n".join(parts)
    else:
        return False
    if not raw or raw.lstrip().startswith(NOISE):
        return False
    if "<command-name>" in raw:
        return True
    raw = IDE_WRAP.sub("", SYSREMINDER.sub("", raw)).strip()
    return bool(raw)


# `claude -p` / print / SDK headless mode logs entrypoint == "sdk-cli".
# Interactive entrypoints: "claude-vscode" (IDE), "cli" (terminal REPL).
HEADLESS_ENTRYPOINTS = {"sdk-cli"}


def first_last_human(path):
    """Return (genuine_prompts, all_user_turns, first_ts, last_ts, sessionIds, project, entrypoints)."""
    n = 0
    turns = 0
    first = last = None
    sids = set()
    proj = None
    ents = set()
    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0, None, None, sids, None, ents
    with fh:
        for line in fh:
            if '"user"' not in line and '"sessionId"' not in line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("sessionId"):
                sids.add(d["sessionId"])
            if d.get("cwd") and not proj:
                proj = d["cwd"]
            if d.get("type") == "user":
                turns += 1
                if d.get("entrypoint"):
                    ents.add(d["entrypoint"])
                if d.get("isSidechain") or d.get("isMeta"):
                    continue
                ut = d.get("userType")
                if ut and ut != "external":
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict) or not is_genuine(msg.get("content")):
                    continue
                ts = d.get("timestamp")
                if ts:
                    first = first or ts
                    last = ts
                n += 1
    return n, turns, first, last, sids, proj, ents


def projname(cwd):
    if not cwd:
        return "?"
    return cwd.replace("\\", "/").rstrip("/").split("/")[-1]


def main():
    main_files = []
    sub_files = []
    for f in PROJECTS.rglob("*.jsonl"):
        if "/subagents/" in f.as_posix() or "/workflows/" in f.as_posix():
            sub_files.append(f)
        else:
            main_files.append(f)

    all_sids = set()
    all_first = all_last = None
    by_proj = defaultdict(lambda: {"sessions": 0, "prompts": 0})
    empty = 0
    sizes = []
    headless = []          # excluded claude -p sessions
    incl_prompts = 0

    for f in main_files:
        n, turns, first, last, sids, cwd, ents = first_last_human(f)
        p = projname(cwd) if cwd else projname(f.parent.name)
        if ents and ents <= HEADLESS_ENTRYPOINTS:   # purely headless -> exclude
            headless.append((f.name, p, n, first))
            continue
        all_sids |= sids
        if first:
            all_first = min(all_first, first) if all_first else first
        if last:
            all_last = max(all_last, last) if all_last else last
        by_proj[p]["sessions"] += 1
        by_proj[p]["prompts"] += n
        incl_prompts += n
        sizes.append(n)
        if n == 0:
            empty += 1

    print(f"EXCLUDED headless `claude -p` (sdk-cli) sessions: {len(headless)}")
    for name, p, n, first in headless:
        print(f"    proj={p}  prompts={n}  {first}  ({name})")

    print(f"\nMAIN-THREAD INTERACTIVE SESSIONS (analyzed): {len(sizes):,}")
    print(f"  distinct sessionIds:                       {len(all_sids):,}")
    print(f"  project directories:                       {len(by_proj)}")
    print(f"  sessions with 0 genuine prompts:           {empty}")
    print(f"SUBAGENT/WORKFLOW child transcripts (separate): {len(sub_files):,}")
    print(f"date span (genuine prompts):  {all_first}  ->  {all_last}")

    sizes_sorted = sorted(s for s in sizes if s > 0)
    if sizes_sorted:
        m = len(sizes_sorted)
        print(f"\ngenuine prompts per (non-empty) session: "
              f"min {sizes_sorted[0]}  median {sizes_sorted[m//2]}  "
              f"max {sizes_sorted[-1]}  mean {sum(sizes_sorted)/m:.1f}")
    print(f"total genuine human prompts (interactive): {incl_prompts:,}")

    print("\nPER PROJECT (sessions / genuine-prompts):")
    for p, d in sorted(by_proj.items(), key=lambda kv: -kv[1]["prompts"]):
        print(f"  {p:<42} {d['sessions']:>4} sessions   {d['prompts']:>6} prompts")


if __name__ == "__main__":
    main()
