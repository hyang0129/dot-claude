#!/usr/bin/env python3
"""SessionStart hook: register this Claude Code session's PID.

Writes ~/.claude/pid-registry/<session_id>.json whenever a main session starts,
resumes, clears, or compacts. Enables zombie-subagent detection: any running
claude.exe whose PID is NOT in this registry is a subagent (candidate zombie).

This hook captures the Claude Code PID by walking the parent process chain,
since the hook itself runs inside an intermediate shell/python process.

Exits 0 unconditionally so a failure never blocks a session from starting.
"""

import json
import os
import sys
import time
from pathlib import Path


def find_claude_pid_windows():
    """Walk the Windows parent process chain until we find claude.exe."""
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x2

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

    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (-1, 0):
        return None

    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    procs = {}
    if k32.Process32First(snap, ctypes.byref(entry)):
        while True:
            procs[entry.th32ProcessID] = (
                entry.th32ParentProcessID,
                entry.szExeFile.decode(errors="replace"),
            )
            if not k32.Process32Next(snap, ctypes.byref(entry)):
                break
    k32.CloseHandle(snap)

    pid = os.getpid()
    for _ in range(6):
        if pid not in procs:
            return None
        ppid, name = procs[pid]
        if name.lower() == "claude.exe":
            return pid
        pid = ppid
    return None


def find_claude_pid_posix():
    """Walk /proc parent chain until we find a claude-named process."""
    pid = os.getpid()
    for _ in range(6):
        try:
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip().lower()
            if "claude" in name:
                return pid
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("PPid:"):
                        pid = int(line.split()[1])
                        break
                else:
                    return None
        except Exception:
            return None
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    session_id = payload.get("session_id")
    if not session_id:
        return

    if os.name == "nt":
        claude_pid = find_claude_pid_windows()
    else:
        claude_pid = find_claude_pid_posix()

    registry_dir = Path.home() / ".claude" / "pid-registry"
    registry_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "pid": claude_pid,
        "hookParentPid": os.getppid(),
        "sessionId": session_id,
        "cwd": payload.get("cwd"),
        "source": payload.get("source"),
        "model": payload.get("model"),
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    (registry_dir / f"{session_id}.json").write_text(json.dumps(entry, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
