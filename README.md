# dot-claude

Global agent configuration for this machine, shared by Claude Code and Codex
CLI. Eleven content files; git history of the predecessor repo is the archive
for everything that has no successor here.

| Path | Purpose |
|---|---|
| `AGENTS.md` | The instruction file, both hosts: intent and working preferences only |
| `CLAUDE.md` | 10-line shim: imports AGENTS.md + Claude-only notes |
| `skills/` | Shared skills (Claude `/name` commands; Codex via `~/.agents/skills`) |
| `agents/` | Claude-only custom agent definitions |
| `model-conduct/` | Per-model patch files, injected by the SessionStart hook |
| `hooks/inject-model-conduct.py` | The repo's one hook: match model → inject patch |
| `settings.json` | Tracked seed; copied once by install.sh, never overwritten |

## Install

```bash
git clone <this-repo> ~/dot-claude && ~/dot-claude/install.sh
```

Symlinks everything into `~/.claude`, `~/.codex/AGENTS.md`, and
`~/.agents/skills`. Idempotent; real files are backed up to `.bak`.
Pulling the repo updates live config immediately — nothing to copy.

## Rules of the repo

- AGENTS.md carries user intent and preferences. Model-specific patches go in
  `model-conduct/`, one line per confirmed quirk — never in AGENTS.md.
- No workflow scripts, rules dirs, or hooks are added speculatively. Machinery
  earns existence only when prose has demonstrably failed.
- Battle-tested skill text transplants verbatim; only plumbing gets rewritten.
