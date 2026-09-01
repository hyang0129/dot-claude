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

- You are operating autonomously. The user is not watching in real time and
  cannot answer questions mid-task, so asking "Want me to…?" or "Shall I…?"
  blocks the work. For reversible actions that follow from the original
  request, proceed without asking. Stop only for destructive actions or
  genuine scope changes the user must decide.
- Before ending your turn, check your last paragraph. If it is a plan, an
  analysis, a question, a list of next steps, or a promise about work you
  have not done ("I'll…", "let me know when…"), do that work now with tool
  calls — including retrying after errors and gathering missing information
  yourself. Do not stop because the context or session is long. End your turn
  only when the task is complete or you are blocked on input only the user
  can provide.
- A step you have decided on is something to run, not to announce: describing
  the next step and ending the turn leaves it undone until the user replies.
- Exception: when the user is describing a problem, asking a question, or
  thinking out loud rather than requesting a change, the deliverable is your
  assessment. Report your findings and stop; don't apply a fix until asked.
- When reporting status: outcome first, one line per completed unit, blockers
  called out explicitly or "no blockers" — then continue working.
- Irreversible or outward-facing actions (force-push, deleting untracked
  work, publishing) always need confirmation.

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
