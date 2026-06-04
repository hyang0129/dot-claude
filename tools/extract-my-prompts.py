#!/usr/bin/env python3
"""Extract the user's own typed prompts from Claude Code transcripts.

Walks ~/.claude/projects/**/*.jsonl, keeps genuine human messages (type=="user",
not a sidechain, not a tool_result, external userType), strips injected
<system-reminder> / <command-*> noise, dedups by uuid, sorts by timestamp, and
writes the last N to a JSONL + a readable text dump for analysis.

Usage:
    py -3 tools/extract-my-prompts.py [N]   # default N=500
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
OUT_JSONL = Path(__file__).resolve().parent.parent / "drafts" / "my-prompts.jsonl"
OUT_TXT = Path(__file__).resolve().parent.parent / "drafts" / "my-prompts.txt"

SYSREMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
IDE_WRAP = re.compile(r"<ide_[\w]+>.*?</ide_[\w]+>", re.DOTALL)  # ide_opened_file, ide_selection, ide_diagnostics
# Harness-injected pseudo-messages that are never human prompts:
NOISE_PREFIX = ("<task-notification>", "[Request interrupted")
CMD_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
CMD_MSG = re.compile(r"<command-message>.*?</command-message>", re.DOTALL)
LOCAL_STDOUT = re.compile(r"<local-command-stdout>.*?</local-command-stdout>", re.DOTALL)
TAG_STRIP = re.compile(r"</?(command-message|command-args|command-name|local-command-stdout)>")


def extract_text(content) -> str | None:
    """Return the human-authored text of a user message, or None if it's not one."""
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "tool_result":
                # pure tool result -> not a human prompt
                return None
            if t == "text" and b.get("text"):
                parts.append(b["text"])
        raw = "\n".join(parts)
    else:
        return None

    if not raw:
        return None

    # Slash command? capture as "/name args"
    cmd = CMD_NAME.search(raw)
    if cmd:
        name = cmd.group(1).strip()
        args = CMD_ARGS.search(raw)
        argtxt = (args.group(1).strip() if args else "")
        return f"{name} {argtxt}".strip()

    # Drop pure harness pseudo-messages
    if raw.lstrip().startswith(NOISE_PREFIX):
        return None

    # Strip injected noise / context wrappers, keep any trailing human text
    raw = SYSREMINDER.sub("", raw)
    raw = IDE_WRAP.sub("", raw)
    raw = LOCAL_STDOUT.sub("", raw)
    raw = CMD_MSG.sub("", raw)
    raw = TAG_STRIP.sub("", raw)
    raw = raw.strip()
    return raw or None


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rows = []
    seen = set()
    files = [p for p in PROJECTS.rglob("*.jsonl")
             if "/subagents/" not in p.as_posix() and "/workflows/" not in p.as_posix()]
    for f in files:
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line or '"type":"user"' not in line.replace(" ", ""):
                    # cheap pre-filter; still parse below to be safe
                    if '"user"' not in line:
                        continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") != "user":
                    continue
                if d.get("isSidechain"):
                    continue
                if d.get("isMeta"):
                    continue
                ut = d.get("userType")
                if ut and ut != "external":
                    continue
                uuid = d.get("uuid")
                if uuid and uuid in seen:
                    continue
                msg = d.get("message", {})
                if not isinstance(msg, dict):
                    continue
                text = extract_text(msg.get("content"))
                if not text:
                    continue
                if uuid:
                    seen.add(uuid)
                rows.append({
                    "ts": d.get("timestamp", ""),
                    "cwd": d.get("cwd", ""),
                    "branch": d.get("gitBranch", ""),
                    "session": d.get("sessionId", ""),
                    "text": text,
                })

    rows.sort(key=lambda r: r["ts"])
    last = rows[-n:]

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for r in last:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    with OUT_TXT.open("w", encoding="utf-8") as out:
        for i, r in enumerate(last, 1):
            proj = Path(r["cwd"]).name if r["cwd"] else "?"
            out.write(f"\n===== [{i}] {r['ts']}  proj={proj}  branch={r['branch']} =====\n")
            out.write(r["text"].strip() + "\n")

    print(f"total genuine prompts found: {len(rows)}")
    print(f"wrote last {len(last)} to {OUT_JSONL.name} and {OUT_TXT.name}")
    if last:
        print(f"date range of last {len(last)}: {last[0]['ts']}  ->  {last[-1]['ts']}")


if __name__ == "__main__":
    main()
