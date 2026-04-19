#!/usr/bin/env python3
"""Find a Claude Code session whose first human message matches a search string."""

import json
import os
import sys
import glob

SEARCH = "epic https://github.com/hyang0129/onlycodes/issues/62 is approved"

def get_first_human_message(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = record.get("message", {})
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                        content = " ".join(parts)
                    return content
    except Exception as e:
        return None
    return None

sessions_dir = os.path.expanduser("~/.claude/projects")
pattern = os.path.join(sessions_dir, "**", "*.jsonl")
files = glob.glob(pattern, recursive=True)

print(f"Searching {len(files)} session files...\n")

matches = []
for filepath in files:
    first_msg = get_first_human_message(filepath)
    if first_msg and SEARCH.lower() in first_msg.lower():
        matches.append((filepath, first_msg))

if matches:
    for filepath, msg in matches:
        print(f"FOUND: {filepath}")
        print(f"  First message: {msg[:200]}")
        print()
else:
    print("No matching session found.")
    print("\nChecking broader search across all ~/.claude session dirs...")
    # Also check ~/.claude/sessions/*.json
    sessions2 = glob.glob(os.path.expanduser("~/.claude/sessions/*.json"))
    for filepath in sessions2:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            # Try different structures
            messages = data.get("messages", []) or data.get("conversation", [])
            for msg in messages:
                role = msg.get("role", "")
                if role == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        parts = [c.get("text", "") for c in content if isinstance(c, dict)]
                        content = " ".join(parts)
                    if SEARCH.lower() in content.lower():
                        print(f"FOUND in sessions/: {filepath}")
                        print(f"  Message: {content[:200]}")
                    break
        except Exception:
            pass
