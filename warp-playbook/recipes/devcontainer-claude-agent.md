# Recipe: Spawn an authenticated Claude agent in a remote devcontainer

Open a **visible Warp tab** (in this window) that SSHes into a homen devcontainer and runs an
**already-authenticated, interactive** Claude agent — so it can validate intent / ask questions and
you drive it in that tab. Builds on [../spawning-sessions.md](../spawning-sessions.md).

## The pattern

```sh
ssh -t <hubN> "cd /workspaces/<folder>/<repo> && env -u ANTHROPIC_API_KEY <native-claude> '<prompt or /command>'"
```

### Verified example (homen `hub_2`, `video_agent_long`, refine an issue)

```sh
ssh -t hub2 "cd /workspaces/hub_2/video_agent_long && env -u ANTHROPIC_API_KEY \
  /home/vscode/.vscode-server/extensions/anthropic.claude-code-2.1.179-linux-x64/resources/native-binary/claude \
  '/refine-issue https://github.com/hyang0129/video_agent_long/issues/1600'"
```

## Why each piece

- **`ssh -t <hubN>`** — the `hub1`..`hub6` / `llmatro` aliases tunnel straight into the running
  devcontainers (see the `connect-to-homen` memory). `-t` allocates a TTY so the interactive Claude
  TUI renders over the double-hop SSH.
- **`env -u ANTHROPIC_API_KEY`** — **critical / the auth fix.** These containers export an *empty*
  `ANTHROPIC_API_KEY`. Claude sees it, tries (failed) API-key auth, and prompts you to log in.
  Removing it lets Claude use the **existing OAuth token** in `~/.claude/.credentials.json`
  (subscription `max`; auto-refreshes). Verify auth headlessly:
  `env -u ANTHROPIC_API_KEY <native-claude> -p "reply READY"` → should print `READY`.
- **`<native-claude>`** — the **VSCode Claude extension's bundled native binary** (no node/npm needed).
  The path contains a version, so resolve the newest robustly:
  ```sh
  CLA=$(ls -dt ~/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/claude | head -1)
  ```
- **`'<prompt or /command>'`** — single-quoted so a slash-command + URL stays one argument. Run
  **interactively** (omit `-p`) so the agent can ask questions and you answer in the tab; use `-p`
  only for fire-and-forget.

## Spawn it as a Warp tab

Open a new tab in the active window and type the command into it (interactive terminal, so it runs as
a shell command and you can drive the agent). The command is passed via `osascript` argv to avoid
quoting issues:

```sh
CMD='ssh -t hub2 "cd /workspaces/hub_2/video_agent_long && env -u ANTHROPIC_API_KEY /home/vscode/.vscode-server/extensions/anthropic.claude-code-2.1.179-linux-x64/resources/native-binary/claude '"'"'/refine-issue https://github.com/hyang0129/video_agent_long/issues/1600'"'"'"'
open "warp://action/new_tab?path=$HOME"; sleep 2
osascript - "$CMD" <<'APPLESCRIPT'
on run argv
  set theCmd to item 1 of argv
  tell application "Warp" to activate
  delay 0.5
  tell application "System Events" to tell process "Warp"
    keystroke theCmd
    delay 0.7
    key code 36
  end tell
end run
APPLESCRIPT
```

(Don't spawn while you're typing in Warp — keystrokes collide. Wait ~2s after `new_tab` so the new
tab is focused before typing; otherwise the command can land in the Claude tab.)

## Notes

- `gh` inside the containers is authed (e.g. `hyang0129`) for issue/PR ops.
- The empty-`ANTHROPIC_API_KEY` fix is per-launch and **resets on container rebuild** — re-apply.
- Hub → container map and per-container SSH setup live in the `connect-to-homen` memory.
