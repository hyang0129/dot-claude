# warp-playbook spawn-hook — NON-KEYSTROKE, same-window Claude Code spawn.
#
# How it works: a spawner drops ~/.claude/warp-playbook/.pending-spawn
#   line 1   = target cwd (guard)
#   line 2+  = the prompt (claude's first message)
# then opens a new Warp tab (`warp://action/new_tab?path=<cwd>`). The first FRESH
# interactive Warp shell to start claims the sentinel atomically and `exec claude <prompt>`.
#
# Safe by construction:
#   - no-op unless a <15s-old sentinel exists (one stat per shell start)
#   - `-o interactive` guard => never fires in non-interactive (e.g. tool/script) shells
#   - atomic `mv` claim => only ONE shell wins, even if several open at once
#   - cwd guard => a tab only fires if it actually opened in the intended folder
# Disable: remove the `source` line for this file in ~/.zshrc.
if [[ -o interactive && "$TERM_PROGRAM" == "WarpTerminal" ]]; then
  _wpf="$HOME/.claude/warp-playbook/.pending-spawn"
  if [[ -f "$_wpf" ]] && (( $(date +%s) - $(stat -f %m "$_wpf" 2>/dev/null || echo 0) < 15 )); then
    _wpc="${_wpf}.claimed.$$"
    if command mv "$_wpf" "$_wpc" 2>/dev/null; then
      _wpcwd="$(sed -n 1p "$_wpc")"
      _wpprompt="$(sed -n '2,$p' "$_wpc")"
      command rm -f "$_wpc"
      if [[ -z "$_wpcwd" || "${PWD:A}" == "${_wpcwd:A}" ]] && command -v claude >/dev/null 2>&1; then
        exec claude "$_wpprompt"
      fi
    fi
  fi
  unset _wpf _wpc _wpcwd _wpprompt
fi
