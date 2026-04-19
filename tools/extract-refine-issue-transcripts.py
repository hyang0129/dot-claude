#!/usr/bin/env python3
"""
Extract /refine-issue subagent transcripts from a /refine-epic session.

Usage:
    python extract-refine-issue-transcripts.py [parent-session-id] [project-dir]

Defaults to the epic #62 session in -workspaces-hub-1.

Output: prints a human-readable transcript for each subagent, showing
the issue number, tool calls, and final summary.
"""

import json
import os
import sys
import glob
from datetime import datetime, timezone

# Defaults
DEFAULT_SESSION_ID = "e729024f-265c-4962-bb7f-c5db545d8aab"
DEFAULT_PROJECT = "C:/Users/HongM/.claude/projects/-workspaces-hub-1"


def get_text(content):
    """Extract text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                elif c.get("type") == "tool_result":
                    inner = c.get("content", "")
                    parts.append(f"[tool_result: {str(inner)[:200]}]")
        return " ".join(parts)
    return str(content)


def read_records(path):
    records = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def summarize_subagent(path):
    """Return a human-readable transcript of a subagent session."""
    records = read_records(path)
    lines = []
    lines.append(f"File: {os.path.basename(path)}")

    for r in records:
        t = r.get("type")
        if t == "user":
            msg = r.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            text = c.get("text", "")
                            lines.append(f"\n[USER] {text[:500]}")
                        elif c.get("type") == "tool_result":
                            inner = c.get("content", "")
                            lines.append(f"  [tool_result] {str(inner)[:300]}")
            else:
                lines.append(f"\n[USER] {str(content)[:500]}")

        elif t == "assistant":
            msg = r.get("message", {})
            for c in msg.get("content", []):
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    text = c.get("text", "").strip()
                    if text:
                        lines.append(f"\n[ASSISTANT] {text[:500]}")
                elif c.get("type") == "tool_use":
                    name = c.get("name", "")
                    inp = c.get("input", {})
                    if name == "Skill":
                        lines.append(f"\n  [Skill] {inp.get('skill','')} args={inp.get('args','')}")
                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        lines.append(f"\n  [Bash] {cmd[:200]}")
                    elif name == "Agent":
                        lines.append(f"\n  [Agent] subagent_type={inp.get('subagent_type','')} prompt={str(inp.get('prompt',''))[:150]}")
                    elif name == "SendMessage":
                        lines.append(f"\n  [SendMessage] to={inp.get('to','')} msg={str(inp.get('message',''))[:200]}")
                    else:
                        lines.append(f"\n  [{name}] {json.dumps(inp)[:200]}")

    return "\n".join(lines)


def find_refine_issue_subagents(session_id, project_dir):
    """Find subagent files in the session's subagents/ directory."""
    subagents_dir = os.path.join(project_dir, session_id, "subagents")
    if not os.path.isdir(subagents_dir):
        print(f"No subagents directory found at: {subagents_dir}")
        return []

    files = sorted(glob.glob(os.path.join(subagents_dir, "*.jsonl")))
    return files


def get_issue_number_from_subagent(path):
    """Try to extract the child issue number from the subagent's first user message."""
    records = read_records(path)
    for r in records:
        if r.get("type") == "user":
            content = r.get("message", {}).get("content", [])
            text = get_text(content)
            # Look for "child issue #NN" or "issue #NN"
            import re
            m = re.search(r"child issue #(\d+)", text)
            if m:
                return int(m.group(1))
            # Also check if it's refine-issue skill invocation
            m = re.search(r"#(\d+)", text)
            if m:
                return int(m.group(1))
    return None


def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SESSION_ID
    project_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROJECT
    out_file = sys.argv[3] if len(sys.argv) > 3 else None

    # Redirect stdout to UTF-8 file if specified, or wrap stdout for UTF-8
    import io
    if out_file:
        output = open(out_file, "w", encoding="utf-8")
    else:
        output = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    def p(*args, **kwargs):
        print(*args, **kwargs, file=output)

    p(f"Parent session: {session_id}")
    p(f"Project dir: {project_dir}\n")

    subagent_files = find_refine_issue_subagents(session_id, project_dir)
    if not subagent_files:
        p("No subagent files found.")
        return

    p(f"Found {len(subagent_files)} subagent session(s):\n")
    for path in subagent_files:
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        issue_num = get_issue_number_from_subagent(path)
        issue_label = f"issue #{issue_num}" if issue_num else "unknown issue"
        records = read_records(path)
        p(f"  {os.path.basename(path)} | {issue_label} | {mtime.strftime('%H:%M:%S')} UTC | {len(records)} records")

    p()

    # Sort by issue number
    def sort_key(path):
        n = get_issue_number_from_subagent(path)
        return n if n else 9999

    for path in sorted(subagent_files, key=sort_key):
        issue_num = get_issue_number_from_subagent(path)
        issue_label = f"Issue #{issue_num}" if issue_num else "Unknown"
        p("=" * 80)
        p(f"SUBAGENT TRANSCRIPT -- {issue_label}")
        p("=" * 80)
        p(summarize_subagent(path))
        p()


if __name__ == "__main__":
    main()
