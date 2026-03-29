# Dev Container Setup Guide

Reference for creating devcontainer configurations on Windows + Docker Desktop.

## devcontainer.json

```json
{
  "name": "Project Name",
  "build": { "dockerfile": "Dockerfile" },
  "customizations": {
    "vscode": {
      "extensions": ["anthropic.claude-code"]
    }
  },
  "initializeCommand": ".devcontainer\\initialize.cmd",
  "postCreateCommand": ".devcontainer/post-create.sh",
  "remoteUser": "vscode"
}
```

## initialize.cmd (runs on Windows host via cmd.exe)

Must be a `.cmd` file — not `.sh` (bash resolves to WSL which lacks /bin/bash) and not inline `bash -c` (cmd.exe mangles quotes).

```batch
@echo off
REM Clean stale VS Code Server installs from Docker Desktop WSL root (tiny 135MB FS)
wsl -d docker-desktop -- rm -rf /root/.vscode-remote-containers /root/.vscode-server /root/.vscode 2>nul
REM Capture git identity for post-create.sh
git config --global user.name > .devcontainer\.gituser.tmp 2>nul
git config --global user.email >> .devcontainer\.gituser.tmp 2>nul
exit /b 0
```

## post-create.sh (runs inside Linux container)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Apply git identity captured by initialize.cmd
GITUSER_TMP="$(dirname "$0")/.gituser.tmp"
if [ -f "$GITUSER_TMP" ]; then
  GIT_NAME=$(sed -n '1p' "$GITUSER_TMP")
  GIT_EMAIL=$(sed -n '2p' "$GITUSER_TMP")
  [ -n "$GIT_NAME" ]  && git config --global user.name  "$GIT_NAME"
  [ -n "$GIT_EMAIL" ] && git config --global user.email "$GIT_EMAIL"
  rm -f "$GITUSER_TMP"
fi

# (Claude Code permissions can be bypassed via the Claude Code UI — see below)
```

## Dockerfile

Use BuildKit cache mounts for apt:
```dockerfile
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get -y install --no-install-recommends ...
```
Do NOT `rm -rf /var/lib/apt/lists/*` when using cache mounts.

## .gitignore (required)

The `initialize.cmd` script writes `.gituser.tmp` into `.devcontainer/`. Exclude it:
```
.devcontainer/.gituser.tmp
```

## Claude Code — Custom Commands (host → container)

Custom commands (`~/.claude/commands/*.md`) live on the Windows host and are not visible
inside the container unless explicitly mounted. Use a two-mount approach:

1. **Base mount** — `~/.claude/` for runtime state (credentials, sessions, projects, plugins):
```json
"source=${localEnv:USERPROFILE}\\.claude,target=/home/vscode/.claude,type=bind,consistency=cached"
```

2. **dot-claude repo mount** — the whole repo, bypassing NTFS symlinks that break inside
   Linux containers (their targets like `/c/Users/...` don't exist):
```json
"source=${localEnv:USERPROFILE}\\Code Projects\\dot-claude,target=/home/vscode/.dot-claude,type=bind,consistency=cached"
```

Then in `post-create.sh`, symlink the tracked files into `~/.claude/`, replacing the broken
Windows symlinks. Linux-native symlinks work fine inside the container:
```bash
DOT_CLAUDE="/home/vscode/.dot-claude"
if [ -d "$DOT_CLAUDE" ]; then
  for f in CLAUDE.md settings.json; do
    ln -sf "$DOT_CLAUDE/$f" "/home/vscode/.claude/$f"
  done
  for d in commands guides; do
    rm -rf "/home/vscode/.claude/$d"
    ln -sf "$DOT_CLAUDE/$d" "/home/vscode/.claude/$d"
  done
fi
```

To track new files/dirs from `dot-claude`, add them to the loop in `post-create.sh`.
After adding mounts, **Rebuild Container** to apply.

## Claude Code Permissions

To bypass permissions for Claude Code inside the devcontainer, enable it via the Claude Code UI under General Settings specifically for the dev container session. No file-based configuration is needed.

## .gitattributes (required)

Enforce line endings to prevent `\r` errors in Linux containers:
```
*.sh text eol=lf
*.cmd text eol=crlf
```

## Pitfalls learned

- **cmd.exe runs initializeCommand on Windows** — forward slashes are interpreted as flags, single quotes aren't recognized
- **Docker Desktop WSL root is only 135MB** — VS Code Server installs accumulate there and never get cleaned up, causing "No space left on device"
- **`bash` on Windows may resolve to WSL** (not Git Bash), and the docker-desktop distro is Alpine with no `/bin/bash`
- **Git checks out `.sh` files with CRLF on Windows** by default — Linux sees `bash\r` and fails
- **Windows NTFS symlinks break inside Linux containers** — targets like `/c/Users/...` don't exist. Fix: bind-mount the `dot-claude` repo and symlink files in `post-create.sh` (Linux symlinks work fine)
- **Cannot execute scripts from `--mount=type=cache` directories** — BuildKit's overlay fs holds an fd open, causing `ETXTBSY` ("Text file busy"). Fix: `cp` the script to a regular path (e.g. `/tmp/cmake-exec.sh`) and execute from there
