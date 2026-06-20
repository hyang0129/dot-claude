# Spawning Visible Claude Code Sessions (in Warp tabs)

**This is the primary mechanism.** It lets this Claude session open **Claude Code** agent sessions
you can *see and take over*, as **new tabs in the window you're already in** — no manual GUI work, no
cloud credits.

The new tab runs the **`claude` CLI** (Claude Code), not Warp's own agent. We open a tab, then type
`claude '<prompt>'` and run it — Warp's universal input classifies the leading `claude` token as a
command. (To fall back to Warp's own agent, set `WARP_SPAWN_AGENT=warp`.)

## The key insight

This Claude session runs **inside a Warp tab** (`TERM_PROGRAM=WarpTerminal`, process ancestry
`claude → zsh → Warp`). Two consequences:

1. `warp://action/new_tab` opens a tab in the **active window = this window**, right next to Claude.
2. The app that needs macOS Accessibility to receive synthetic keystrokes is **Warp itself**
   (`dev.warp.Warp-Stable`). Warp drives Warp.

## Mechanism (verified working 2026-06-19; switched to launching `claude` 2026-06-20)

```sh
open "warp://action/new_tab?path=<cwd>"            # 1. visible tab in the active window
# 2. wait for the tab to take focus (~1.6s)
osascript ... keystroke "claude '<prompt>'"; key code 36   # 3. type the command + Return
```

Wrapped in **`bin/warp-spawn "<prompt>" [cwd]`**. The script shell-quotes the prompt (single quotes,
with embedded `'` escaped as `'\''`) and types `claude '<prompt>'` into the new tab, launching an
interactive Claude Code session with that prompt as its first message. Because the input box is
`universal`, the leading `claude` token runs as a command even though `default_session_mode = "agent"`.

**First-run trust prompt:** the first `claude` launch in a freshly-cloned directory may ask
*"Do you trust the files in this folder?"* — the user accepts it once in the tab.

## Prerequisite: Accessibility

Warp must be granted Accessibility: **System Settings → Privacy & Security → Accessibility → Warp = ON**.

- Verify: `osascript -e 'tell application "System Events" to tell process "Warp" to get name of windows'`
  — returns window names if granted, or `-1728 not allowed assistive access` if not.
- If newly toggled and it still errors, Warp may need a restart — but **restarting Warp kills this
  Claude session** (Claude lives in Warp). Relaunch `claude` afterward (the session resumes).

## Safeguards (don't type into the Claude tab)

- Always `open new_tab` first, then **wait** (`sleep ~1.6`) so the new tab is focused before typing.
- `tell application "Warp" to activate` before keystrokes.
- Keep prompts **single-line** (Return submits). For multi-line, send the body, then a separate
  Return — or just compose a single-line instruction.
- Failure signature: if a keystroke ever lands in the Claude tab, it shows up as a stray user
  message in this conversation. If you see that, stop and re-check focus/timing.

## Why not the other routes

| Route | Visible? | Same window? | Runs a command? | Blocker |
|---|---|---|---|---|
| `warp://action/new_tab` + keystrokes (`claude '<prompt>'`) | ✅ | ✅ | ✅ (typed) | needs Accessibility |
| `warp://action/new_window` | ✅ | ❌ new window | ❌ | — |
| `warp://launch/<config>` (exec) | ✅ | ❌ new window | ✅ | launch configs are window-level ([#8833](https://github.com/warpdotdev/warp/issues/8833)) |
| `oz agent run-cloud --open` | ✅ | ❌ | ✅ | cloud + out of credits |
| `oz agent run` / `run-cloud` (headless) | ❌ not a tab | — | ✅ | invisible; cloud credit-blocked |

See [orchestration-runbook.md](orchestration-runbook.md) for how this combines with the headless
`oz` path, and [oz-reference.md](oz-reference.md) for the `oz` command surface.
