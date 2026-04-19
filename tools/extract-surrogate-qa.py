#!/usr/bin/env python3
"""
Extract Q&A pairs from /refine-issue surrogate sessions.

Finds all surrogate subagents in a /refine-epic session, reads the INTENT
files they wrote, and extracts the "Clarifying Q&A Log" section from each.

Usage:
    python extract-surrogate-qa.py [session_id] [project_dir] [output_file]

Defaults to the epic #62 session in -workspaces-hub-1.
Writes to stdout if no output_file given.
"""

import json
import os
import sys
import glob
import re
import io

DEFAULT_SESSION_ID = "e729024f-265c-4962-bb7f-c5db545d8aab"
DEFAULT_PROJECT = "C:/Users/HongM/.claude/projects/-workspaces-hub-1"


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


def get_issue_number(records):
    """Extract child issue number from the surrogate's first user message."""
    for r in records:
        if r.get("type") == "user":
            content = r.get("message", {}).get("content", [])
            if isinstance(content, str):
                m = re.search(r"child issue #(\d+)", content)
                if m:
                    return int(m.group(1))
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        m = re.search(r"child issue #(\d+)", c.get("text", ""))
                        if m:
                            return int(m.group(1))
            break
    return None


def get_intent_writes(records):
    """Return list of (file_path, content) for all INTENT file writes."""
    writes = []
    for r in records:
        if r.get("type") != "assistant":
            continue
        for c in r.get("message", {}).get("content", []):
            if (
                isinstance(c, dict)
                and c.get("type") == "tool_use"
                and c.get("name") == "Write"
            ):
                fpath = c.get("input", {}).get("file_path", "")
                content = c.get("input", {}).get("content", "")
                if "INTENT_" in fpath:
                    writes.append((fpath, content))
    return writes


def extract_qa_log(intent_content):
    """Extract the Clarifying Q&A Log section from an INTENT file."""
    # Find the section
    m = re.search(r"##\s*Clarifying Q[&\w\s]*Log\s*\n(.*?)(?=\n##\s|\Z)", intent_content, re.DOTALL)
    if not m:
        return None
    return m.group(1).strip()


def parse_qa_pairs(qa_log_text):
    """
    Parse Q/A pairs from the log text.
    Handles multiple formats:
      - Q: ... / A: ...
      - - Q: ... / A: ...
      - Narrative (no structured Q/A)
    Returns list of (question, answer) tuples, or empty list if narrative only.
    """
    pairs = []

    # Try format: "Q: ...\nA: ..." (with possible leading dashes/bullets)
    pattern = re.compile(
        r"[-*]?\s*Q:\s*(.*?)\n\s*[-*]?\s*A:\s*(.*?)(?=\n\s*[-*]?\s*Q:|\Z)",
        re.DOTALL
    )
    matches = pattern.findall(qa_log_text)
    if matches:
        for q, a in matches:
            pairs.append((q.strip(), a.strip()))
        return pairs

    # Try format: "**Q: ...**\nA: ..."
    pattern2 = re.compile(
        r"\*\*Q:\s*(.*?)\*\*\s*\n\s*A:\s*(.*?)(?=\n\s*\*\*Q:|\Z)",
        re.DOTALL
    )
    matches2 = pattern2.findall(qa_log_text)
    if matches2:
        for q, a in matches2:
            pairs.append((q.strip(), a.strip()))
        return pairs

    return pairs


def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SESSION_ID
    project_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROJECT
    out_file = sys.argv[3] if len(sys.argv) > 3 else None

    if out_file:
        output = open(out_file, "w", encoding="utf-8")
    else:
        output = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    def p(*args, **kwargs):
        print(*args, **kwargs, file=output)

    subagents_dir = os.path.join(project_dir, session_id, "subagents")
    if not os.path.isdir(subagents_dir):
        p(f"No subagents directory at: {subagents_dir}")
        return

    subagent_files = sorted(glob.glob(os.path.join(subagents_dir, "*.jsonl")))
    p(f"Scanning {len(subagent_files)} surrogate subagents in session {session_id}\n")

    all_results = []
    for path in subagent_files:
        records = read_records(path)
        issue_num = get_issue_number(records)
        intent_writes = get_intent_writes(records)

        if not intent_writes:
            continue

        for fpath, content in intent_writes:
            qa_log = extract_qa_log(content)
            if qa_log is None:
                continue
            pairs = parse_qa_pairs(qa_log)
            all_results.append({
                "issue": issue_num,
                "intent_file": os.path.basename(fpath),
                "qa_log_raw": qa_log,
                "pairs": pairs,
            })

    # Sort by issue number
    all_results.sort(key=lambda x: x["issue"] or 9999)

    # Summary header
    total_pairs = sum(len(r["pairs"]) for r in all_results)
    issues_with_qa = [r for r in all_results if r["pairs"]]
    p(f"Found Q&A in {len(issues_with_qa)}/{len(all_results)} issues ({total_pairs} total Q&A pairs)\n")

    for r in all_results:
        issue_label = f"Issue #{r['issue']}" if r["issue"] else "Unknown"
        p("=" * 72)
        p(f"{issue_label} -- {r['intent_file']}")
        p("=" * 72)

        if not r["pairs"]:
            p("[Narrative only -- no structured Q/A pairs extracted]")
            p()
            p(r["qa_log_raw"])
        else:
            for i, (q, a) in enumerate(r["pairs"], 1):
                p(f"Q{i}: {q}")
                p(f"A{i}: {a}")
                p()
        p()

    if out_file:
        output.close()
        print(f"Written to {out_file}")


if __name__ == "__main__":
    main()
