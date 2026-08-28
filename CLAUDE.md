@AGENTS.md

# Claude Code Notes

The import above resolves through `~/.claude/AGENTS.md` (a symlink into the
dot-claude repo), so it survives the repo being moved or renamed.

Claude-specific config: `skills/` (shared with Codex via `~/.agents/skills`),
`agents/` (Claude-only custom agents), `model-conduct/` + its SessionStart
hook (per-model guidance injection).
