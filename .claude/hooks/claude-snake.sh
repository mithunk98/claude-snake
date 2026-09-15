#!/usr/bin/env bash
#
# Claude Code hook: open a game of snake in a tmux pane while Claude works,
# and flag it as finished when Claude stops.
#
#   claude-snake.sh start     opens the pane (UserPromptSubmit)
#   claude-snake.sh stop      tells the game Claude is done (Stop)
#   claude-snake.sh cleanup   closes the pane (SessionEnd)
#
# Environment:
#   CLAUDE_SNAKE_OFF=1        disable without unwiring the hooks
#   CLAUDE_SNAKE_SIZE=40%     width of the game pane
#   CLAUDE_SNAKE_SPLIT=-h     -h side by side, -v below
#   CLAUDE_SNAKE_AUTOCLOSE=1  close the pane the moment Claude finishes
#   CLAUDE_SNAKE_ARGS="--wrap --speed fast"
#   CLAUDE_SNAKE_PYTHON=python3
#   CLAUDE_SNAKE_DEBUG=1      log to $TMPDIR/claude-snake-hook.log

# A hook must never break the session it is attached to, and on
# UserPromptSubmit whatever it prints on stdout is fed to the model. So:
# say nothing, and always exit 0.
trap 'exit 0' EXIT
if [ "${CLAUDE_SNAKE_DEBUG:-0}" = "1" ]; then
    exec >>"${TMPDIR:-/tmp}/claude-snake-hook.log" 2>&1
    printf '\n=== %s %s (pane %s) ===\n' "$(date)" "${1:-}" "${TMUX_PANE:-none}"
    set -x
else
    exec >/dev/null 2>&1
fi

action="${1:-start}"

[ "${CLAUDE_SNAKE_OFF:-0}" = "1" ] && exit 0
# No tmux, no pane to play in. Claude Code owns the one terminal it is in.
[ -n "${TMUX:-}" ] || exit 0
command -v tmux >/dev/null 2>&1 || exit 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd) || exit 0
python_bin="${CLAUDE_SNAKE_PYTHON:-python3}"
command -v "$python_bin" >/dev/null 2>&1 || exit 0

state_dir="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/claude-snake"
mkdir -p "$state_dir" 2>/dev/null || exit 0
chmod 700 "$state_dir" 2>/dev/null

# One game per Claude pane, so two sessions side by side do not fight.
pane_key="${TMUX_PANE:-solo}"
pane_key="${pane_key//[^A-Za-z0-9]/_}"
state_file="$state_dir/$pane_key.pane"
done_flag="$state_dir/$pane_key.done"

pane_alive() {
    [ -n "$1" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx -- "$1"
}

case "$action" in
start)
    # A fresh prompt means Claude is working again.
    rm -f "$done_flag"
    if [ -s "$state_file" ] && pane_alive "$(cat "$state_file")"; then
        exit 0
    fi

    args=(-m snake --watch-file "$done_flag" --quiet)
    [ "${CLAUDE_SNAKE_AUTOCLOSE:-0}" = "1" ] && args+=(--exit-when-done)
    # Word-split on purpose: this is a user-supplied argument string.
    # shellcheck disable=SC2206
    [ -n "${CLAUDE_SNAKE_ARGS:-}" ] && args+=(${CLAUDE_SNAKE_ARGS})

    command=$(printf '%q ' "$python_bin" "${args[@]}")

    size="${CLAUDE_SNAKE_SIZE:-40%}"
    split="${CLAUDE_SNAKE_SPLIT:--h}"
    # -d keeps the cursor in Claude's pane: stealing focus would swallow
    # whatever you type next. tmux 3.4 dropped -p, older tmux lacks -l %.
    pane=$(tmux split-window "$split" -d -l "$size" -t "$TMUX_PANE" \
        -c "$repo_root" -P -F '#{pane_id}' "$command" 2>/dev/null) ||
        pane=$(tmux split-window "$split" -d -p "${size%\%}" -t "$TMUX_PANE" \
            -c "$repo_root" -P -F '#{pane_id}' "$command" 2>/dev/null) || exit 0

    tmux select-pane -t "$pane" -T "snake" 2>/dev/null
    printf '%s\n' "$pane" >"$state_file"
    ;;

stop)
    # Let the game announce it rather than yanking the pane away mid-run;
    # --exit-when-done handles the people who would rather it vanished.
    [ -s "$state_file" ] && pane_alive "$(cat "$state_file")" && : >"$done_flag"
    ;;

cleanup)
    if [ -s "$state_file" ]; then
        pane=$(cat "$state_file")
        pane_alive "$pane" && tmux kill-pane -t "$pane" 2>/dev/null
    fi
    rm -f "$state_file" "$done_flag"
    ;;
esac

exit 0
