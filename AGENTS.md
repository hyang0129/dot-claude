# Global Agent Instructions

Applies to every coding agent on this machine (Claude Code, Codex CLI, and
anything else that reads AGENTS.md). This file states intent and working
preferences only — model-specific patches live in `model-conduct/` and are
injected per-session by a hook.

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

At the start of any task in a repository, read the repo's own instruction file
(`CLAUDE.md` or `AGENTS.md`) if one exists, before doing anything else. It
contains project-specific conventions and constraints that override defaults.

## Autonomy Contract

- Proceed by default. Ask only when blocked by something the user alone can
  resolve: credentials, approval for a destructive action, or genuine scope
  ambiguity. "Shall I continue?" is never a valid turn ending.
- When not blocked: report status, then continue. Status = outcome first, one
  line per completed unit, blockers called out explicitly or "no blockers."
- Never end a turn on a plan, a list of next steps, or a promise. Do the work
  in the same turn.
- Reversible actions inside the task's scope need no confirmation.
  Irreversible or outward-facing actions (force-push, deleting untracked work,
  publishing) always do.

## Pull Requests

**NEVER use `--admin` to force through a merge.** If a PR cannot be merged due
to branch protection (required checks, required reviews), stop and inform the
user — do not bypass protections.

## Long-Running Tasks

Pipe output of long-running tasks (builds, installs, tests, downloads) to a
temp log file so progress can be checked incrementally:

```bash
python train.py 2>&1 | tee /tmp/progress.log
```

## Modifying This Config

Everything here lives in the `dot-claude` repo and is symlinked into
`~/.claude` and `~/.codex`. Edit in the repo, commit; `git pull` updates live
config immediately. There is nothing to copy.
