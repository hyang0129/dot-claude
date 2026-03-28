#!/usr/bin/env bash
set -euo pipefail

# Install dot-claude repo into ~/.claude
# Creates symlinks so edits in either location stay in sync.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/.claude"

mkdir -p "$TARGET/commands" "$TARGET/guides"

link_file() {
  local src="$1" dst="$2"
  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ -e "$dst" ]; then
    echo "  backup: $dst → ${dst}.bak"
    mv "$dst" "${dst}.bak"
  fi
  ln -s "$src" "$dst"
  echo "  linked: $dst → $src"
}

echo "Installing dot-claude from $SCRIPT_DIR"
echo ""

# CLAUDE.md
link_file "$SCRIPT_DIR/CLAUDE.md" "$TARGET/CLAUDE.md"

# settings.json
link_file "$SCRIPT_DIR/settings.json" "$TARGET/settings.json"

# Commands
echo "Commands:"
for f in "$SCRIPT_DIR/commands/"*.md; do
  [ -f "$f" ] || continue
  link_file "$f" "$TARGET/commands/$(basename "$f")"
done

# Guides
echo "Guides:"
for f in "$SCRIPT_DIR/guides/"*.md; do
  [ -f "$f" ] || continue
  link_file "$f" "$TARGET/guides/$(basename "$f")"
done

echo ""
echo "Done. Runtime dirs (sessions, projects, etc.) are untouched."
