#!/usr/bin/env python3
"""DoD run-to-completion guard. One script, two hook events.

UserPromptSubmit: arms/disarms a per-session flag when the prompt is
"/dod on" / "/dod off" (slash optional). Deterministic — the model is not
involved in toggling. Any other prompt resets the block counter so a fresh
user message always grants a full budget.

Stop: while the flag is armed, blocks the model from ending its turn unless
the payload's last_assistant_message opens a line with a terminal marker:
  - "DOD: MET"        -> allow stop, disarm the guard
  - "BLOCKED:"        -> allow stop, guard stays armed
Anything else (a plan, a promise, a status essay) gets blocked with a reason
telling the model to keep working or declare BLOCKED.

Safety valve: after MAX_BLOCKS consecutive blocked stops without a user
prompt, allow the stop (prevents a runaway loop burning tokens). The harness
has its own cap (CLAUDE_CODE_STOP_HOOK_BLOCK_CAP, default 8) — settings.json
raises it above MAX_BLOCKS so this counter is the one that governs.
Exits 0 on any internal error so a bug here never bricks a session.
"""
import json, os, re, sys

MAX_BLOCKS = 25
FLAG_DIR = os.path.expanduser("~/.claude/dod-flags")
# anchored to line start so prose *mentioning* the markers doesn't trip them
MARKER = re.compile(r"^\s*(DOD: MET|BLOCKED:)", re.M)


def flag_path(session_id):
    return os.path.join(FLAG_DIR, session_id)


def read_count(path):
    try:
        with open(path) as f:
            return int(f.read().strip() or 0)
    except Exception:
        return 0


def main():
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name", "")
    session_id = payload.get("session_id", "")
    if not session_id:
        return
    flag = flag_path(session_id)

    if event == "UserPromptSubmit":
        prompt = payload.get("prompt", "").strip().lower()
        if prompt in ("/dod on", "dod on"):
            os.makedirs(FLAG_DIR, exist_ok=True)
            with open(flag, "w") as f:
                f.write("0")
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "DoD guard ARMED (harness-enforced): your turn cannot end until your "
                    "final message contains 'DOD: MET' (definition of done fully met, "
                    "evidence stated) or 'BLOCKED: <reason>' (something only the user can "
                    "resolve). Plans, promises, and status updates do not end the turn — "
                    "do the work instead. Never offer continue/pause options while armed.")}}))
        elif prompt in ("/dod off", "dod off"):
            try:
                os.remove(flag)
            except FileNotFoundError:
                pass
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "DoD guard disarmed."}}))
        elif os.path.exists(flag):
            # fresh user message: reset the runaway counter
            with open(flag, "w") as f:
                f.write("0")
        return

    if event == "Stop":
        if not os.path.exists(flag):
            return
        # payload field is the current turn's final text; the transcript file
        # lags the in-memory conversation and can serve the previous turn
        text = payload.get("last_assistant_message") or ""
        m = MARKER.search(text)
        if m:
            if m.group(1) == "DOD: MET":
                os.remove(flag)
            return
        # legit wait: background subagents/tasks re-invoke the session on
        # completion, and the next Stop gets checked again — allow, stay armed
        tasks = payload.get("background_tasks") or []
        if any(not isinstance(t, dict)
               or t.get("status") in (None, "running", "pending")
               for t in tasks):
            with open(flag, "w") as f:
                f.write("0")
            return
        count = read_count(flag) + 1
        if count > MAX_BLOCKS:
            # ponytail: hard cap instead of smarter loop detection; raise if real
            # epics legitimately need >25 harness-continued turns
            with open(flag, "w") as f:
                f.write("0")
            sys.stderr.write("DoD guard: block limit reached, allowing stop.\n")
            return
        with open(flag, "w") as f:
            f.write(str(count))
        print(json.dumps({
            "decision": "block",
            "reason": (
                "DoD guard: a run-to-completion directive is standing. Continue working "
                "toward the definition of done now, in this turn. End the turn only with "
                "'DOD: MET' plus evidence, or 'BLOCKED: <specific thing only the user can "
                "resolve>'. Do not end on a plan, a promise, a status summary, or "
                "continue/pause options. If you are waiting on a background task, monitor "
                "it or do other pending work meanwhile. "
                f"(harness-continued turn {count}/{MAX_BLOCKS})")}))


try:
    main()
except Exception:
    pass
sys.exit(0)
