#!/usr/bin/env python3
"""SessionStart hook: inject the model-conduct patch matching this session's model.

Reads the hook payload from stdin, finds the model id, and emits the matching
model-conduct/<family>.md as additionalContext. No match -> injects nothing.
Exits 0 unconditionally so a failure never blocks a session.
"""
import json, os, sys

ALIASES = {"fable": "opus", "mythos": "opus"}  # same wordiness profile

try:
    payload = json.load(sys.stdin)
    model = payload.get("model") or os.environ.get("ANTHROPIC_MODEL") or ""
    if isinstance(model, dict):
        model = model.get("id") or model.get("display_name") or ""
    model = model.lower()
    conduct_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model-conduct")
    for fname in sorted(os.listdir(conduct_dir)):
        if not fname.endswith(".md"):
            continue
        family = fname[:-3]
        matches = [family] + [a for a, target in ALIASES.items() if target == family]
        if any(m in model for m in matches):
            with open(os.path.join(conduct_dir, fname)) as f:
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f.read().strip()}}))
            break
except Exception:
    pass
sys.exit(0)
