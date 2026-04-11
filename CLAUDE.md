# Global Claude Code Instructions

## Starting Work in a Repo

At the start of any task in a repository, read the repo's `CLAUDE.md` (if it exists) before doing anything else. This file contains project-specific instructions, conventions, and constraints that override defaults. Use `Glob` to check for `CLAUDE.md` at the repo root.

## Modifying Global Config

This file and all files under `~/.claude/commands/` and `~/.claude/guides/` are **copied** from the `dot-claude` repo. Do NOT edit them in `~/.claude/` directly. Instead, make changes in the repo at `~/Code Projects/dot-claude/` so they are version-controlled. After making changes, manually copy the updated files into `~/.claude/` (no install script — just copy).

## Dev Containers

Before creating or modifying any devcontainer file (`.devcontainer/devcontainer.json`, `Dockerfile`, `initialize.cmd`, `post-create.sh`, `.gitattributes`), you MUST read `~/.claude/guides/devcontainer-guide.md` first. Do not write devcontainer files from memory — the guide contains hard-won fixes for Windows + Docker Desktop + WSL pitfalls that are not obvious.

## Pull Requests

Before reviewing or pushing to a PR, you MUST read `~/.claude/guides/pr-guide.md` first. It defines the workflow for tracking review findings and verifying fixes before pushing.

**NEVER use `--admin` to force through a merge.** If a PR cannot be merged due to branch protection (required checks, required reviews, etc.), stop and inform the user — do not bypass protections with `--admin`.

## Long-Running Tasks

For long-running tasks (builds, installs, tests, downloads, etc.), pipe output to a temp log file so progress can be checked incrementally:

```bash
python train.py 2>&1 | tee /tmp/progress.log
```


## Agent Teams for GitHub Issues

Before spawning an agent team to work on a GitHub issue, you MUST read `~/.claude/guides/agent-team-guide.md` first. It defines tier selection (simple/medium/complex), role assignments, file ownership rules, the task spec template, the ADR gate for complex issues, and the PR checklist.
