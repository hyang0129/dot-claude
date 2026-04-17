#!/usr/bin/env python3
"""List all registered Claude Code sessions and flag zombie subagents.

A zombie subagent is a running claude.exe process whose PID is NOT in the
~/.claude/pid-registry/. These are orphaned agent spawns that outlived their
parent session.

Usage:
    python check-zombie-sessions.py [--json]
"""

import argparse
import ctypes
import json
import os
import sys
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path

STALE_THRESHOLD_HOURS = 3


# ── Windows process snapshot ──────────────────────────────────────────────────

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def snapshot_processes():
    """Return dict of pid -> {ppid, name} for all running processes."""
    TH32CS_SNAPPROCESS = 0x2
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (-1, 0):
        return {}

    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    procs = {}
    if k32.Process32First(snap, ctypes.byref(entry)):
        while True:
            procs[entry.th32ProcessID] = {
                "ppid": entry.th32ParentProcessID,
                "name": entry.szExeFile.decode(errors="replace"),
            }
            if not k32.Process32Next(snap, ctypes.byref(entry)):
                break
    k32.CloseHandle(snap)
    return procs


def is_alive(pid: int, procs: dict) -> bool:
    return pid in procs


def get_claude_pids(procs: dict) -> set[int]:
    return {pid for pid, info in procs.items() if info["name"].lower() == "claude.exe"}


# ── Registry loading ──────────────────────────────────────────────────────────

def load_registry() -> list[dict]:
    registry_dir = Path.home() / ".claude" / "pid-registry"
    if not registry_dir.exists():
        return []
    entries = []
    for f in sorted(registry_dir.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            data = json.loads(f.read_text())
            data["_file"] = f.name
            data["_mtime"] = datetime.fromtimestamp(f.stat().st_mtime)
            entries.append(data)
        except Exception:
            pass
    return entries


# ── Status classification ─────────────────────────────────────────────────────

STATUS_ALIVE = "alive"
STATUS_STALE = "stale"      # alive but no SessionStart event in >3 hours
STATUS_DEAD = "dead"        # registered session whose PID is gone
STATUS_ZOMBIE = "zombie"    # running claude.exe NOT in registry (subagent orphan)


def classify_sessions(registry: list[dict], procs: dict, claude_pids: set[int]) -> list[dict]:
    registered_pids = {e["pid"] for e in registry if e.get("pid")}
    stale_cutoff = datetime.now() - timedelta(hours=STALE_THRESHOLD_HOURS)

    sessions = []
    for entry in registry:
        pid = entry.get("pid")
        alive = pid is not None and is_alive(pid, procs)
        mtime: datetime = entry.get("_mtime")
        if alive and mtime and mtime < stale_cutoff:
            status = STATUS_STALE
        else:
            status = STATUS_ALIVE if alive else STATUS_DEAD
        sessions.append({
            "sessionId": entry.get("sessionId"),
            "pid": pid,
            "ppid": procs[pid]["ppid"] if pid and pid in procs else None,
            "cwd": entry.get("cwd"),
            "source": entry.get("source"),
            "startedAt": entry.get("startedAt"),
            "lastUpdatedAt": mtime.strftime("%Y-%m-%dT%H:%M:%S") if mtime else None,
            "status": status,
        })

    # Unregistered running claude.exe processes = zombie subagents
    zombie_pids = claude_pids - registered_pids
    for zpid in sorted(zombie_pids):
        ppid = procs[zpid]["ppid"] if zpid in procs else None
        sessions.append({
            "sessionId": None,
            "pid": zpid,
            "ppid": ppid,
            "cwd": None,
            "source": None,
            "startedAt": None,
            "lastUpdatedAt": None,
            "status": STATUS_ZOMBIE,
        })

    return sessions


# ── Formatting ────────────────────────────────────────────────────────────────

COLORS = {
    STATUS_ALIVE:  "\033[32m",  # green
    STATUS_STALE:  "\033[33m",  # yellow
    STATUS_DEAD:   "\033[90m",  # dark gray
    STATUS_ZOMBIE: "\033[31m",  # red
}
RESET = "\033[0m"
BOLD = "\033[1m"


def fmt_status(status: str, use_color: bool) -> str:
    label = status.upper().ljust(6)
    if use_color:
        return f"{COLORS[status]}{label}{RESET}"
    return label


def fmt_age(mtime_str: str | None) -> str:
    if not mtime_str:
        return "?"
    try:
        delta = datetime.now() - datetime.strptime(mtime_str, "%Y-%m-%dT%H:%M:%S")
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        return f"{h}h{m:02d}m ago"
    except Exception:
        return "?"


def print_table(sessions: list[dict]):
    use_color = sys.stdout.isatty()

    print(f"\n{BOLD}Claude Code Session Status{RESET}\n")
    header = f"{'STATUS':<7} {'PID':>7} {'PPID':>7}  {'LAST UPDATE':<15}  {'SOURCE':<10}  CWD"
    print(header)
    print("-" * 105)

    for s in sessions:
        status = s["status"]
        pid = str(s["pid"]) if s["pid"] else "?"
        ppid = str(s["ppid"]) if s["ppid"] else "?"
        age = fmt_age(s.get("lastUpdatedAt"))
        source = (s["source"] or "unknown").ljust(10)
        cwd = s["cwd"] or "(unknown)"
        session_id = f"  [{s['sessionId']}]" if s["sessionId"] else "  [no session ID]"

        status_label = fmt_status(status, use_color)
        print(f"{status_label} {pid:>7} {ppid:>7}  {age:<15}  {source}  {cwd}")
        print(f"{'':7}  {session_id}")

    print()
    alive = sum(1 for s in sessions if s["status"] == STATUS_ALIVE)
    stale = sum(1 for s in sessions if s["status"] == STATUS_STALE)
    dead = sum(1 for s in sessions if s["status"] == STATUS_DEAD)
    zombies = sum(1 for s in sessions if s["status"] == STATUS_ZOMBIE)
    print(f"Summary: {alive} alive, {stale} stale (>{STALE_THRESHOLD_HOURS}h), {dead} dead, {zombies} zombie")
    if stale:
        print(f"\n{COLORS[STATUS_STALE]}WARNING: {stale} stale session(s) — alive but no activity in >{STALE_THRESHOLD_HOURS} hours.{RESET}")
    if zombies:
        print(f"\n{COLORS[STATUS_ZOMBIE]}WARNING: {zombies} zombie subagent(s) detected — unregistered running claude.exe process(es).{RESET}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if os.name != "nt":
        print("This tool currently only supports Windows.", file=sys.stderr)
        sys.exit(1)

    procs = snapshot_processes()
    claude_pids = get_claude_pids(procs)
    registry = load_registry()
    sessions = classify_sessions(registry, procs, claude_pids)

    # Sort: alive first, stale, zombies, then dead
    order = {STATUS_ALIVE: 0, STATUS_STALE: 1, STATUS_ZOMBIE: 2, STATUS_DEAD: 3}
    sessions.sort(key=lambda s: order[s["status"]])

    if args.json:
        print(json.dumps(sessions, indent=2))
    else:
        print_table(sessions)


if __name__ == "__main__":
    main()
