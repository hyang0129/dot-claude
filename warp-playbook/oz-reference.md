# `oz` Command Reference

> **Secondary / headless path.** `oz` runs agents with **no visible tab**. For the visible
> same-window sessions that are the primary model, see [spawning-sessions.md](spawning-sessions.md).
> Note: **cloud `oz` runs are out of add-on credits** right now (`insufficient_credits`).

Verified against Warp `0.2026.06.17` on 2026-06-19. Binary: `/Applications/Warp.app/Contents/Resources/bin/oz`.
For machine parsing use `ozj` (forces `--output-format json`).

> `oz --help` prints usage. `oz <cmd> --help` for any subcommand.
>
> **Gotchas:**
> - Put `--output-format` (and other global flags) **after** the subcommand, e.g. `oz run list --output-format json`. Before the subcommand, `oz` parses the subcommand as a URL positional and errors. The `ozj` wrapper sidesteps this by exporting `WARP_OUTPUT_FORMAT=json` instead of using the flag.
> - In zsh, a quoted var is **not** word-split, so `c="run get"; oz $c` passes `run get` as one arg and fails. Pass subcommand words literally.

## Global flags (on every subcommand)

| Flag | Notes |
|---|---|
| `--output-format json\|ndjson\|pretty\|text` | env `WARP_OUTPUT_FORMAT`; default `pretty`. Use `json`/`ndjson` to parse. |
| `--model <MODEL_ID>` | override base model; see `oz model list`. |
| `--api-key <KEY>` | env `WARP_API_KEY`; for headless/unattended auth. |
| `--debug` | verbose logging. |

## Auth & identity

```sh
oz whoami            # current user
oz login / oz logout # interactive auth
oz api-key ...       # manage API keys (for cron / cloud / CI)
```

## `oz agent` — define & launch agents

```sh
oz agent run        -p "<task>"        # run LOCALLY, streams in the foreground
oz agent run-cloud  -p "<task>"        # dispatch a REMOTE/background run, returns a run id
oz agent list | get | create | update | delete
oz agent skills                        # list available agent skills
oz agent profile ...                   # manage agent profiles
```

**Prompt sources** (one required): `-p/--prompt` · `--saved-prompt <id>` · `--task-id <id>` ·
`--skill <name|repo:skill|org/repo:skill>` · `-f/--file <yaml|json>` (env `WARP_AGENT_CONFIG_FILE`).
Skills are searched in `.agents/skills/`, `.warp/skills/`, `.claude/skills/`, `.codex/skills/`.

**`run-cloud` extra flags:**

| Flag | Purpose |
|---|---|
| `-n, --name <NAME>` | label the task |
| `--model <MODEL_ID>` | e.g. `claude-4-7-opus-high`, `claude-4-6-sonnet-high`, `auto-genius` |
| `--conversation <ID>` | **continue/steer an existing cloud conversation** (follow-up turns) |
| `-e, --environment <ID>` / `--no-environment` | cloud environment to run in (`oz environment`) |
| `--mcp <path\|json>` | start MCP servers before the run (repeatable) |
| `--agent <UID>` | run as a saved agent (applies its skills/model, attributes credit) |
| `--host <WORKER_ID>` | `warp` = Warp infra; any other value = a self-hosted worker by name |
| `--team` / `--personal` | visibility scope |
| `--open` | open the session in the Warp GUI once available (manual takeover) |

**`agent create`:** `--name` (req) · `--description` · `--secret <NAME>` (repeat) · `--skill <SKILL>` (repeat) · `--base-model <MODEL_ID>`.

## `oz run` — monitor & coordinate runs

```sh
ozj run list                       # all ambient agent tasks  -> {page_info, runs:[...]}
ozj run get <TASK_ID>              # status of one run
oz  run get <TASK_ID> --conversation   # fetch that run's conversation/output
ozj run conversation get <CONV_ID>     # fetch a conversation by conversation id
oz  run message <SUB>             # inter-run messaging (see below)
```

**`run message` (run-to-run, NOT user→run):** `watch` · `send` · `list` · `read` · `mark-delivered`.
`send` requires: `--to <RUN_ID>...` (repeatable) `--subject` `--body` `--sender-run-id <ID>`.
→ Use only for **agent-to-agent** handoffs. To steer a run yourself, use `run-cloud --conversation <ID>`.

**Stopping a run:** no CLI `stop`/`cancel` exists. Either let it finish, or `--open` the session in
Warp and stop it from the GUI/dashboard. (Re-check `oz run --help` after Warp updates.)

## Scheduling (Warp-side cron)

```sh
oz schedule create --name <N> --cron "<expr>" --prompt "<task>"   # or --skill <SKILL>
oz schedule list | get | update | pause | unpause | delete
```
Distinct from Claude Code's `/schedule` and `/loop` — this schedules **Warp** agents.

## Other subcommands

| Command | Purpose |
|---|---|
| `oz model list` | available models (incl. Claude tiers + `auto*`) |
| `oz environment` (alias `e`) | manage cloud environments for cloud runs |
| `oz mcp` | manage MCP servers |
| `oz secret` | upload/manage secrets (attach to agents via `--secret`) |
| `oz integration` (alias `i`) | manage integrations |
| `oz artifact` | manage run artifacts |
| `oz federate` | federated identity tokens |
| `oz completions` | shell completions to stdout |
| `oz dump-debug-info` | debug dump |
