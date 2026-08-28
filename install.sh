#!/usr/bin/env bash
# Symlink this repo's config into ~/.claude, ~/.codex, and ~/.agents.
# Idempotent. Existing non-symlink files are backed up to <name>.bak.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

link() {  # link <src> <dest>
  [ -e "$1" ] || return 0
  if [ -e "$2" ] && [ ! -L "$2" ]; then mv "$2" "$2.bak"; echo "  backed up $2 -> $2.bak"; fi
  ln -sfn "$1" "$2"
  echo "  $2 -> $1"
}

mkdir -p "$HOME/.claude" "$HOME/.codex" "$HOME/.agents"

# Claude Code. AGENTS.md is linked so CLAUDE.md's relative @AGENTS.md import
# resolves through ~/.claude/ and survives the repo moving.
for name in CLAUDE.md AGENTS.md skills agents model-conduct hooks; do
  link "$REPO/$name" "$HOME/.claude/$name"
done

# Codex CLI: global instructions + shared skills (Agent Skills standard).
link "$REPO/AGENTS.md" "$HOME/.codex/AGENTS.md"
link "$REPO/skills"    "$HOME/.agents/skills"

# settings.json is merged with per-machine state; seed once, never overwrite.
if [ ! -e "$HOME/.claude/settings.json" ]; then
  cp "$REPO/settings.json" "$HOME/.claude/settings.json"
  echo "  seeded settings.json"
else
  echo "  settings.json exists — left alone (diff against $REPO/settings.json)"
fi
echo "Done."
