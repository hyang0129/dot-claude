# Headless agent orchestration — failure modes and how to avoid them

Lessons from orchestrating parallel Claude Code sessions on a remote Linux box (`homen`) via
`ssh` + `tmux`, driving a multi-track sprint. Written 2026-08-31 after losing roughly an hour
to two avoidable self-inflicted bugs. Everything here is about the *harness*, not the agents:
in each case the agents behaved reasonably and the orchestration lied to me.

## 1. A backgrounded command kills a non-interactive agent

**What happened.** Three tracks were launched as `claude --permission-mode bypassPermissions
"<prompt>" | tee log`. Each agent did its work, started `npx playwright test` **in the
background**, then ended its turn saying "I'll report once it finishes." In a non-interactive
session, ending the turn ends the process. The suite died with it, nothing was reported, and
the work sat uncommitted in the working tree. Their last log lines were the tell:

> "Running the full Playwright suite in the background to get one clean end-to-end
> confirmation. I'll report the complete final summary once it finishes."

**Why it is easy to miss.** This is *correct* behaviour in an interactive session, where the
harness re-invokes the agent when the background task completes. The agent has no way to know
which mode it is in unless told.

**Fix.** Say so explicitly in the prompt:

> Never background a command and end your turn. Run every verification in the foreground and
> wait for it, even if it takes several minutes.

**Also fix.** Require an explicit commit as the last step, so an interrupted agent leaves a
recoverable artifact. Recovery is then cheap: relaunch with a "finish and commit" prompt that
tells the agent to read its own `git diff` and continue rather than start over. No work is
lost — but only because the tree persists.

## 2. Health checks that lie

Three signals were used to decide whether agents were running. All three were wrong.

| Signal | Why it lied |
|---|---|
| `pgrep -fc "claude --permission-mode bypassPermissions"` | Matched the **tmux command string** (which contains the pattern) and the **waiter's own `bash -c`** (ditto). Reported 3-5 "running agents" when the real count was 0. |
| `tmux list-panes -F '#{pane_dead}'` | The launcher ended with `exec bash` to keep panes attachable. The pane therefore stays alive **forever** after the agent exits. |
| Log file size | Output goes through `tee`, and a piped (non-tty) Claude buffers — the log is empty until the process exits. Useless as a progress signal, and *actively misleading*: 0 bytes means "running or dead", never "idle". |

**Fix.** Have the launcher write an explicit sentinel, and check for that and nothing else:

```sh
tmux new-session -d -s "$sess" -c "$dir" \
  "claude ... 2>&1 | tee $log; echo FINISH_DONE >> $log; exec bash"
```

Then `grep -q FINISH_DONE "$log"`. For liveness, match the real interpreter process and
exclude wrappers:

```sh
ps -eo pid,rss,args | grep "claude --permission-mode" | grep -v "bash -c\|tmux\|grep"
```

Resident memory is a decent aliveness proxy: a working agent sits in the hundreds of MB.

**General rule.** Any `pgrep -f` whose pattern appears in the checking command's own command
line will match itself. Either use a sentinel file, or use the `[c]laude` bracket trick, or
match on a path only the real process has.

## 3. Nested shell quoting through `ssh`

**What happened.** A launcher script was generated remotely with a heredoc inside an
`ssh homen '...'` single-quoted command. The script body contained single quotes. Those closed
the outer `ssh` quoting early, so `$S` and `$track` were expanded **locally** (undefined →
empty) instead of remotely. The generated line became:

```sh
claude ... "$(cat /prompts/s3/..finish.md)" 2>&1 | tee ; echo FINISH_DONE >> ;
```

`tee` with no operand, `>>` with no target. Every session died instantly. Because the script
also ran `tmux kill-session` first, the previously-running sessions were destroyed and not
replaced — turning a cosmetic bug into three lost sessions.

**Fix.** Never generate a remote script through nested quoting. Write it to a local file, then
`scp` it:

```sh
cat > /tmp/run.sh <<'OUTER'   # quoted delimiter: no local expansion
...
OUTER
scp -q /tmp/run.sh host:path/
```

**Also fix.** Make destructive steps conditional on the constructive step succeeding, and have
the launcher verify itself:

```sh
if tmux has-session -t "$sess" 2>/dev/null; then echo "launched"; else echo "FAILED" >&2; exit 1; fi
```

A launcher that cannot tell you it failed will be assumed to have worked.

## 4. The `pkill` self-match

`pkill -f "vite preview"` run over `ssh` matched the ssh session's **own** `bash -c` command
line (which contained that string) and killed the session — appearing as a network drop
(`exit 255`). Use `pkill -f "[v]ite preview"`, which matches the process but not the literal
pattern in the invoking command line.

## Checklist for the next headless fan-out

- [ ] Prompt forbids backgrounding + ending the turn; requires foreground verification.
- [ ] Prompt requires a commit as the final step (recoverable artifact).
- [ ] Launcher writes a completion sentinel; readiness is judged **only** by the sentinel.
- [ ] Launcher self-verifies (`has-session`) and fails loudly.
- [ ] No `exec bash` in a pane whose liveness you intend to poll — or don't poll it.
- [ ] Remote scripts are `scp`-ed, never heredoc'd through nested quoting.
- [ ] Every `pgrep`/`pkill -f` pattern is self-match-proof.
- [ ] Destructive steps (kill-session) run only after the replacement is known good.
- [ ] Clones/worktrees are created from the commit you actually intend — verify the SHA after
      cloning, especially if you pushed moments earlier (a local `git clone` copies the
      **local** branch, not `origin/main`).
