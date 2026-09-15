# claude-snake

Something to do while Claude Code is thinking.

It opens a game of snake in a tmux pane the moment you send a prompt, and
tells you in the header when Claude is done. Your move until then.

```
 SNAKE  score 170   best 240   lv 5                       | claude is working
+----------------------------------------------------------------------------+
|                                                                            |
|                                                                            |
|                                                                            |
|                                                                            |
|                                                                            |
|                                                                            |
|                                                    **                      |
|                                                                            |
|                                  ooooooOO                                  |
|                                  oo                                        |
|                            oooooooo                                        |
|                            oo                                              |
|                            oooo                                            |
|                                                                            |
|                                                                            |
|                                                                            |
|                                                                            |
|                                                                            |
+----------------------------------------------------------------------------+
 arrows/wasd move   p pause   r restart   q quit
```

Pure Python standard library — no pip install, no dependencies. Python 3.8+
and a terminal is the whole list.

## Play right now

```sh
python3 -m snake            # walls kill
python3 -m snake --wrap     # edges teleport instead
python3 -m snake --speed fast
```

| Key | |
| --- | --- |
| arrows, `wasd`, `hjkl` | turn |
| `p` / space | pause |
| `r` | play again, once you've died |
| `q` | quit |

High scores are kept per mode in `~/.local/share/claude-snake/highscores.json`.

## Play while Claude works

This needs **tmux** — Claude Code owns the terminal it runs in, so the game
needs a pane of its own. Run Claude Code inside tmux and the hooks in
`.claude/settings.json` do the rest:

| When | What happens |
| --- | --- |
| you send a prompt | a snake pane opens beside Claude |
| Claude finishes | the header switches to `* CLAUDE IS DONE *` and beeps |
| you send the next prompt | it goes back to `claude is working` |
| the session ends | the pane closes |

Focus stays in Claude's pane the whole time, so the split never swallows
what you were typing. Switch over with `prefix + →` when you want to play,
and `q` closes the pane whenever you're done with it.

To get this in *every* repo rather than just this one, copy the hook block
from `.claude/settings.json` into `~/.claude/settings.json` and point the
commands at wherever you keep this checkout. Claude Code reviews hooks that
ship with a repository before it runs them, so check `/hooks` if the pane
never shows up.

### Knobs

Set these in the environment Claude Code runs in:

| Variable | Default | |
| --- | --- | --- |
| `CLAUDE_SNAKE_OFF` | `0` | `1` disables it without unwiring the hooks |
| `CLAUDE_SNAKE_SIZE` | `40%` | width of the game pane |
| `CLAUDE_SNAKE_SPLIT` | `-h` | `-h` beside Claude, `-v` below |
| `CLAUDE_SNAKE_AUTOCLOSE` | `0` | `1` closes the pane the instant Claude finishes, mid-game or not |
| `CLAUDE_SNAKE_ARGS` | | passed to the game, e.g. `--wrap --speed fast` |
| `CLAUDE_SNAKE_PYTHON` | `python3` | interpreter to run it with |
| `CLAUDE_SNAKE_DEBUG` | `0` | `1` logs to `$TMPDIR/claude-snake-hook.log` |

By default the pane stays open after Claude finishes — dying to a wall
because your session ended is a bad way to lose a run.

## How it hangs together

```
snake/game.py     the rules, with no idea a terminal exists
snake/tui.py      curses: drawing, input, the Claude status line
snake/scores.py   high scores that survive a corrupt file
.claude/hooks/claude-snake.sh    opens the pane, flags when Claude is done
.claude/settings.json            wires that script to the hooks
```

The hook and the game talk through one empty file. `stop` creates it, the
game notices within 250ms and changes the header, and the next `start`
deletes it again. That's the entire protocol.

Two details worth knowing: the board is drawn as coloured spaces rather
than Unicode blocks, so it stays solid on terminals without a UTF-8 locale
(`--no-color` falls back to `oo`/`OO`/`**`), and every line of chrome has a
ladder of shorter spellings so a narrow split degrades instead of
overflowing.

## Tests

```sh
python3 -m unittest discover -s tests
```

45 of them: the rules, the layout maths, the score file, and three that
boot the real game on a pty and drive it with keystrokes.
