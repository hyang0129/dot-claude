# Warp Orchestration Playbook

**Goal:** run **one Claude session as the orchestrator** that spawns and manages **Claude Code**
agent sessions in Warp tabs — so you don't manually open tabs or start agents in the GUI yourself.

This session runs **inside a Warp tab**, and it spawns new **Claude Code** sessions (the `claude`
CLI) as **tabs in the same window**, which you can watch and take over.

## The model

```
   YOU ──► this Claude session (orchestrator, running in a Warp tab)
                 │
                 ├─ warp-spawn  ──►  new TAB in this window, runs `claude '<prompt>'`   ◀── primary
                 │                    (warp://action/new_tab + keystrokes; needs Accessibility)
                 │
                 └─ oz CLI      ──►  headless local/cloud runs, monitored via `oz run`   ◀── secondary
                                      (no visible tab; cloud currently out of credits)
```

- **Primary — visible same-window tabs:** `bin/warp-spawn "<prompt>"` opens a tab next to this one
  and runs `claude '<prompt>'`, launching a **Claude Code** session you can watch and take over. See
  **[spawning-sessions.md](spawning-sessions.md)**.
- **Secondary — headless `oz`:** `oz agent run` / `run-cloud` for background/parallel work with no
  visible tab; monitored via `oz run list/get`. Useful when you don't need to watch it. Cloud is
  **out of add-on credits** right now. See **[oz-reference.md](oz-reference.md)**.

## Prerequisites

- **Accessibility:** Warp granted macOS Accessibility (System Settings → Privacy & Security →
  Accessibility → **Warp = ON**). Required for `warp-spawn` keystrokes. Verify:
  `osascript -e 'tell application "System Events" to tell process "Warp" to get name of windows'`.
- **Run from within Warp** so "active window" is the window you see.
- **`oz` (optional, headless path):** logged in (`oz whoami`); aliases `oz`/`ozj` in `~/.zshrc`.

## Quick start

```sh
warp-spawn "say hi"                          # visible tab in this window, runs `claude 'say hi'`
warp-spawn "summarize git log" ~/some/repo   # with a working directory
ozj run list                                 # headless runs (oz path)
```

## Boundary: what spawns what

- **Visible tabs (`warp-spawn`)** now launch **Claude Code** (`claude`) — a full Claude Code session
  in a Warp tab. These are peers of *this* session, not its subagents.
- **Headless `oz`** still drives **Warp's own cloud/local agent** — a separate system.
- Both are distinct from Claude Code's *in-session* subagents / `/schedule` / `/loop`.

## Index

- **[spawning-sessions.md](spawning-sessions.md)** — primary mechanism: visible same-window tabs.
- **[recipes/devcontainer-claude-agent.md](recipes/devcontainer-claude-agent.md)** — spawn an *authenticated* Claude agent in a remote (homen) devcontainer via a Warp tab.
- **[orchestration-runbook.md](orchestration-runbook.md)** — how the orchestrator operates (both modes).
- **[oz-reference.md](oz-reference.md)** — headless `oz` CLI cheatsheet.
- **[templates/](templates/)** — prompt + `oz` config templates.
- **[runs/registry.md](runs/registry.md)** — log of headless `oz` runs.
- **bin/** — `warp-spawn` (visible tabs), `ozj` (oz with JSON output).

Activate from any session with **`/warp`** (skill: `warp-orchestrator`).
