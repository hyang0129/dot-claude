# Global Agent Instructions for `homen`

## Storage Policy

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
