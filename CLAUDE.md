# Global Claude Code Instructions

## Storage Policy on `homen`

The root filesystem (`/`) is approximately 100 GB and is reserved for the
operating system, packages, system services, logs, and small per-user
configuration files.

- Put all repositories, worktrees, virtual environments, build outputs,
  datasets, media, models, caches, and generated artifacts under `/work/hong`.
- Use `/work/hong/<repo>` for code and `/work/hong/media/` for large media.
- Do not copy working data into `/home/hong` and do not create compatibility
  symlinks there unless the user explicitly requests one.
- Before a large clone, copy, download, build, or generation job, verify the
  destination with `df -P <path>`. Working data must resolve to
  `/dev/mapper/ubuntu--vg-work`, mounted at `/work`.
- If a tool defaults to a large cache or artifact directory under `$HOME`,
  configure that data to live under `/work/hong` instead.

Use canonical `/work/hong/...` paths in commands and documentation.

## Starting Work in a Repo

At the start of any task in a repository, read the repo's `CLAUDE.md` (if it exists) before doing anything else. This file contains project-specific instructions, conventions, and constraints that override defaults. Use `Glob` to check for `CLAUDE.md` at the repo root.

## Modifying Global Config

`~/.claude/CLAUDE.md`, `commands/`, `guides/`, `hooks/`, `skills/`, `prompts/` and
`templates/` are **symlinks** into the `dot-claude` repo at `~/dot-claude/`. Editing either
path edits the same file, and `git pull` updates live config immediately — there is nothing
to copy. Make changes in `~/dot-claude/` so they are version-controlled, then commit.

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
