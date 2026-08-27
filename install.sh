#!/usr/bin/env bash
# Symlink this repo's tracked config into ~/.claude (and AGENTS.md into ~/.codex).
# Idempotent. Existing non-symlink files are backed up to <name>.bak.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="$HOME/.claude"
CODEX="$HOME/.codex"

link() {  # link <src> <dest>
  [ -e "$1" ] || return 0
  if [ -e "$2" ] && [ ! -L "$2" ]; then mv "$2" "$2.bak"; echo "  backed up $2 -> $2.bak"; fi
  ln -sfn "$1" "$2"
  echo "  $2 -> $1"
}

mkdir -p "$CLAUDE" "$CODEX"
for name in CLAUDE.md commands guides hooks skills prompts templates agents; do
  link "$REPO/$name" "$CLAUDE/$name"
done
link "$REPO/AGENTS.md" "$CODEX/AGENTS.md"

# settings.json is merged by Claude Code with per-machine state; copy, don't link.
if [ ! -e "$CLAUDE/settings.json" ]; then
  cp "$REPO/settings.json" "$CLAUDE/settings.json"
  echo "  copied settings.json"
else
  echo "  settings.json exists — left alone (diff against $REPO/settings.json manually)"
fi

echo "Done."
