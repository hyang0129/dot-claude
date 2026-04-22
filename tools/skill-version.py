#!/usr/bin/env python3
"""Extract skill invocations and their versions from Claude Code session logs.

For each `Skill` tool_use in a session JSONL, Claude Code injects the full
SKILL.md body as a user text message right after the tool_result. This util
pairs the tool_use with that body, hashes it, and parses the `version:`
frontmatter field if present.

Usage:
    # List every skill invocation in a session
    python skill-version.py <session.jsonl>

    # Look up one invocation by its tool_use_id
    python skill-version.py <session.jsonl> --tool-use-id toolu_01ABC...

    # JSON output
    python skill-version.py <session.jsonl> --json
"""

import argparse
import hashlib
import json
import re
import sys
from typing import Iterator


FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
VERSION_RE = re.compile(r"^version:\s*(.+?)\s*$", re.MULTILINE)


def _parse_version(body: str) -> str | None:
    m = FRONTMATTER_RE.match(body)
    if not m:
        return None
    vm = VERSION_RE.search(m.group(1))
    return vm.group(1).strip() if vm else None


def _sha8(body: str) -> str:
    normalized = body.replace("\r\n", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:8]


def _iter_records(jsonl_path: str) -> Iterator[tuple[int, dict]]:
    with open(jsonl_path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except json.JSONDecodeError:
                continue


def extract_from_session(jsonl_path: str) -> list[dict]:
    """Return one entry per Skill tool_use in the session.

    Each entry: {tool_use_id, skill, args, version, sha, line, body_line}.
    `version` is None if the SKILL.md has no version: frontmatter field.
    `body_line` is None if the body message couldn't be located.
    """
    pending: dict[str, dict] = {}
    awaiting_body: list[dict] = []
    results: list[dict] = []

    for line_no, obj in _iter_records(jsonl_path):
        msg = obj.get("message") or {}
        role = msg.get("role")
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue

        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")

            if role == "assistant" and ptype == "tool_use" and part.get("name") == "Skill":
                tu_id = part.get("id")
                inp = part.get("input") or {}
                pending[tu_id] = {
                    "tool_use_id": tu_id,
                    "skill": inp.get("skill"),
                    "args": inp.get("args"),
                    "line": line_no,
                    "version": None,
                    "sha": None,
                    "body_line": None,
                }
            elif role == "user" and ptype == "tool_result":
                tu_id = part.get("tool_use_id")
                if tu_id in pending:
                    awaiting_body.append(pending.pop(tu_id))
            elif role == "user" and ptype == "text" and awaiting_body:
                entry = awaiting_body.pop(0)
                body = part.get("text", "") or ""
                entry["sha"] = _sha8(body)
                entry["version"] = _parse_version(body)
                entry["body_line"] = line_no
                results.append(entry)

    results.extend(awaiting_body)
    results.sort(key=lambda e: e["line"])
    return results


def extract_from_turn(jsonl_path: str, tool_use_id: str) -> dict | None:
    """Return the single Skill invocation matching `tool_use_id`, or None."""
    for entry in extract_from_session(jsonl_path):
        if entry["tool_use_id"] == tool_use_id:
            return entry
    return None


def _format_table(entries: list[dict]) -> str:
    if not entries:
        return "(no Skill invocations found)"
    rows = [("line", "skill", "version", "sha", "tool_use_id", "args")]
    for e in entries:
        rows.append((
            str(e["line"]),
            e["skill"] or "?",
            e["version"] or "-",
            e["sha"] or "-",
            (e["tool_use_id"] or "")[:20],
            (e["args"] or "")[:40],
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out = []
    for r in rows:
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("jsonl", help="Path to session JSONL file")
    ap.add_argument("--tool-use-id", help="Return only the entry with this tool_use_id")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    args = ap.parse_args()

    if args.tool_use_id:
        entry = extract_from_turn(args.jsonl, args.tool_use_id)
        if entry is None:
            print(f"tool_use_id not found: {args.tool_use_id}", file=sys.stderr)
            return 1
        payload = [entry]
    else:
        payload = extract_from_session(args.jsonl)

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(_format_table(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
