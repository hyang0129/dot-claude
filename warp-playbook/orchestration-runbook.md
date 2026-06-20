# Orchestration Runbook

How this Claude session operates as the Warp orchestrator. Two modes — prefer **visible** unless the
user wants fire-and-forget background work.

## Mode A — Visible same-window tabs (primary)

Spawns a **Claude Code** session (the `claude` CLI) in a new tab you can see and take over.
Mechanism + prereqs: [spawning-sessions.md](spawning-sessions.md).

1. Compose a **single-line** prompt (Return submits).
2. Spawn: `warp-spawn "<prompt>" [cwd]` → opens a tab in this window and runs `claude '<prompt>'`,
   launching an interactive Claude Code session with that prompt as its first message.
3. Tell the user it's open; they watch/steer it directly in that tab.
4. For multiple agents, call `warp-spawn` repeatedly (each is a new tab). Re-assert focus timing if a
   machine is slow.

Notes:
- Requires Warp Accessibility (verify before first spawn — see spawning-sessions.md) and `claude` on PATH.
- Keystrokes are best-effort: after spawning, confirm with the user rather than assuming output.
- First `claude` launch in a fresh repo dir may show a folder-trust prompt the user accepts once.
- To fall back to Warp's own agent instead of `claude`, set `WARP_SPAWN_AGENT=warp`.

## Mode B — Headless `oz` runs (secondary)

No visible tab; for background/parallel work you don't need to watch. Commands: [oz-reference.md](oz-reference.md).

1. Compose a complete, autonomous prompt (see [templates/dispatch-prompt.md](templates/dispatch-prompt.md)).
2. Dispatch: `oz agent run-cloud -n "<label>" -p "<prompt>"` (background) or `oz agent run` (local).
3. Record the run in [runs/registry.md](runs/registry.md) (id, label, mode, model, time, status).
4. Monitor: `ozj run list` / `ozj run get <id>`; read `oz run get <id> --conversation`.
5. Iterate via `oz agent run-cloud --conversation <id>`; agent-to-agent via `oz run message send`.

⚠️ **Cloud is currently out of add-on credits** (`insufficient_credits`) — `run-cloud` fails instantly.
Local `oz agent run` reached `INPROGRESS` (not blocked the same way) but is headless. Until credits
are topped up, prefer **Mode A** for anything that must actually run.

## Choosing a mode

| Want | Mode |
|---|---|
| See it / take it over / one window | **A** (`warp-spawn`) |
| Background, parallel, don't need to watch | **B** (`oz`), credits permitting |
| Scheduled/cron Warp agent | `oz schedule` (headless) |

## Safety

- Cloud `oz` dispatch can bill; confirm scope for destructive/outbound/large-fan-out tasks.
- Mode A types into the active Warp window — keep the focus/delay safeguards so keystrokes never land
  in the Claude tab (see spawning-sessions.md).
- Secrets go in `oz secret` / are typed by the user, never inlined into prompts you log.
