# dot-claude

Reusable Claude Code configuration — skills, guides, settings, and templates — portable across machines and environments.

## What's in here

| Directory | Purpose |
|---|---|
| `CLAUDE.md` | Global instructions loaded into every Claude Code session |
| `settings.json` | Permissions, env vars, allowed domains |
| `commands/` | Custom slash commands (`/fix-issue`, `/review-fix`, `/rebase`) |
| `guides/` | Reference docs read on-demand by commands and CLAUDE.md |
| `hooks/` | Event-driven shell scripts (pre/post tool execution) |
| `prompts/` | Subagent prompt bodies loaded by commands (not user-invocable) |
| `templates/` | Scaffolding: devcontainer skeleton, starter project CLAUDE.md |

## Install

Clone this repo, then symlink into `~/.claude`:

**Linux / macOS / WSL / Git Bash:**
```bash
git clone https://github.com/YOUR_USER/dot-claude.git
cd dot-claude
./install.sh
```

**Windows (cmd.exe):** symlinks are unreliable under Docker Desktop / WSL, so use the copy-based
fallback:
```batch
git clone https://github.com/YOUR_USER/dot-claude.git
cd dot-claude
fix-install.cmd
```

`install.sh` symlinks tracked config into `~/.claude`, plus `AGENTS.md` into `~/.codex` so Codex and
Claude Code share one storage/workflow policy. It is idempotent and backs up any existing real file
to `<name>.bak`. `settings.json` is copied, not linked, and never overwritten once it exists.
Runtime directories (sessions, projects, telemetry) are left untouched.

## Not tracked

Runtime state, secrets, and per-machine memory are excluded via `.gitignore`:
- `sessions/`, `projects/`, `telemetry/`, `debug/`, etc.
- `.credentials.json`, auth caches
- `memory/`, `MEMORY.md`

## Updating

Since files are symlinked, pulling this repo updates your live `~/.claude` config immediately. No re-install needed.

## Templates

### Dev container

Copy `templates/devcontainer/` into your project's `.devcontainer/` directory. See `guides/devcontainer-guide.md` for Windows + Docker Desktop pitfalls this skeleton already handles.

### Project CLAUDE.md

Copy `templates/project-claude-md.md` into a new project as `.claude/CLAUDE.md` and fill in the blanks.
