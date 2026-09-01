---
name: dod
description: "Arm or disarm the harness-enforced DoD guard (/dod on | /dod off). While armed, a Stop hook blocks ending the turn until the final message contains 'DOD: MET' with evidence or 'BLOCKED: <reason>'."
disable-model-invocation: true
---

# DoD Guard

`/dod on` | `/dod off`

The toggle itself is performed by the `dod-stop-guard.py` UserPromptSubmit
hook, deterministically — you do not create or remove any flag file. If the
hook injected a confirmation ("DoD guard ARMED" / "disarmed"), acknowledge it
in one line and, if armed, immediately continue (or start) the standing task.
Never start a line with either marker except to genuinely end the run — the
guard matches them at line start.

If no hook confirmation appears in context, the guard did not fire — tell the
user the hook is not installed or not matching, and do not claim the guard is
active.

While armed, the contract for every turn ending:

- `DOD: MET` — the definition of done is fully met; state the evidence.
- `BLOCKED: <reason>` — something only the user can resolve; be specific.
- Anything else is blocked by the harness and the turn continues.
