"""Curses front end for Claude Snake.

Renders with coloured spaces rather than Unicode blocks so the board looks
solid on terminals without a UTF-8 locale, and falls back to plain ASCII
when there are no colours at all.
"""

from __future__ import annotations

import curses
import os
import time
from typing import Optional

from .game import Direction, Event, SnakeGame, State
from .scores import HighScores

#: Chrome around the board: title, two border rows, controls.
CHROME_ROWS = 4
CHROME_COLS = 2
#: Each board cell is two terminal columns so cells look square.
CELL_W = 2
#: Beyond this the board stops growing with the terminal.
MAX_BOARD_H = 26
MAX_BOARD_W = 46

MIN_BOARD_H = 8
MIN_BOARD_W = 12

SPINNER = ("|", "/", "-", "\\")
#: Columns the score line is never squeezed below to make room for status.
MIN_SCORE_COLS = 12
DONE_BLINK_SECONDS = 4
FRAME_NAP_MS = 8
WATCH_POLL = 0.25
#: How often to re-check whether a too-small terminal has grown.
SIZE_RETRY = 0.25

# Colour pair ids.
P_BODY, P_HEAD, P_FOOD, P_FRAME, P_DIM, P_THINK, P_DONE, P_ALERT = range(1, 9)

KEY_TO_DIR = {
    curses.KEY_UP: Direction.UP,
    curses.KEY_DOWN: Direction.DOWN,
    curses.KEY_LEFT: Direction.LEFT,
    curses.KEY_RIGHT: Direction.RIGHT,
    ord("w"): Direction.UP,
    ord("s"): Direction.DOWN,
    ord("a"): Direction.LEFT,
    ord("d"): Direction.RIGHT,
    ord("k"): Direction.UP,
    ord("j"): Direction.DOWN,
    ord("h"): Direction.LEFT,
    ord("l"): Direction.RIGHT,
}


def fit(variants, width: int) -> str:
    """The first spelling that fits in ``width`` columns, else ``""``."""
    for text in variants:
        if len(text) <= width:
            return text
    return ""


class TooSmall(Exception):
    """The terminal cannot hold the smallest playable board."""

    def __init__(self, need_cols: int, need_rows: int, cols: int, rows: int) -> None:
        super().__init__(
            f"need at least {need_cols}x{need_rows}, have {cols}x{rows}"
        )
        self.need_cols = need_cols
        self.need_rows = need_rows

    @property
    def short(self) -> str:
        """A spelling that fits in a terminal this small."""
        return f"need {self.need_cols}x{self.need_rows}"


def board_size(rows: int, cols: int) -> tuple:
    """Largest board that fits in a ``rows`` x ``cols`` terminal."""
    height = min(MAX_BOARD_H, rows - CHROME_ROWS)
    width = min(MAX_BOARD_W, (cols - CHROME_COLS) // CELL_W)
    if height < MIN_BOARD_H or width < MIN_BOARD_W:
        raise TooSmall(
            MIN_BOARD_W * CELL_W + CHROME_COLS, MIN_BOARD_H + CHROME_ROWS, cols, rows
        )
    return height, width


class SnakeUI:
    def __init__(self, stdscr, opts) -> None:
        self.stdscr = stdscr
        self.opts = opts
        self.scores = HighScores(opts.highscore_file)
        self.mode = "wrap" if opts.wrap else "walls"
        self.best = self.scores.get(self.mode)
        self.color = False
        self.game: Optional[SnakeGame] = None
        self.claude_done = False
        self.done_at = 0.0
        self.quit = False
        self.frame = 0
        self._next_watch_poll = 0.0
        self._next_size_retry = 0.0

    # -- setup -------------------------------------------------------------

    def setup(self) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        self.color = curses.has_colors() and not self.opts.no_color
        if self.color:
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            curses.init_pair(P_BODY, curses.COLOR_GREEN, curses.COLOR_GREEN)
            curses.init_pair(P_HEAD, curses.COLOR_YELLOW, curses.COLOR_YELLOW)
            curses.init_pair(P_FOOD, curses.COLOR_RED, curses.COLOR_RED)
            curses.init_pair(P_FRAME, curses.COLOR_CYAN, -1)
            curses.init_pair(P_DIM, curses.COLOR_WHITE, -1)
            curses.init_pair(P_THINK, curses.COLOR_YELLOW, -1)
            curses.init_pair(P_DONE, curses.COLOR_GREEN, -1)
            curses.init_pair(P_ALERT, curses.COLOR_MAGENTA, -1)

    def attr(self, pair: int, extra: int = 0) -> int:
        return (curses.color_pair(pair) if self.color else 0) | extra

    def new_game(self) -> bool:
        """Start a game if the terminal can hold a board.

        A pane can open smaller than the smallest board, or be dragged
        below it later, so "too small" is a state to sit in and recover
        from rather than a reason to quit.
        """
        rows, cols = self.stdscr.getmaxyx()
        try:
            height, width = board_size(rows, cols)
        except TooSmall:
            self.game = None
            return False
        self.game = SnakeGame(
            height,
            width,
            wrap=self.opts.wrap,
            base_interval=self.opts.interval,
            seed=self.opts.seed,
        )
        return True

    # -- drawing helpers ---------------------------------------------------

    def put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        """addstr that tolerates the bottom-right corner and tiny windows."""
        rows, cols = self.stdscr.getmaxyx()
        if not (0 <= y < rows) or x < 0 or x >= cols:
            return
        try:
            self.stdscr.addnstr(y, x, text, cols - x, attr)
        except curses.error:
            pass

    def center(self, y: int, text: str, attr: int = 0) -> None:
        _, cols = self.stdscr.getmaxyx()
        self.put(y, max(0, (cols - len(text)) // 2), text, attr)

    # -- main loop ---------------------------------------------------------

    def run(self) -> None:
        self.setup()
        self.new_game()
        next_tick = time.monotonic()
        while not self.quit:
            self.handle_input()
            if self.quit:
                break
            now = time.monotonic()
            if self.game is None:
                # Waiting for the terminal to grow enough to play in. A
                # resize normally wakes us; this is the backstop for
                # terminals that do not report one, so it can be lazy.
                if now >= self._next_size_retry:
                    self._next_size_retry = now + SIZE_RETRY
                    self.new_game()
                next_tick = now
            elif self.game.state is State.RUNNING and now >= next_tick:
                self.on_event(self.game.step())
                # Re-base rather than accumulate, so a stalled terminal
                # cannot bank up a burst of catch-up moves.
                next_tick = now + self.game.interval
            elif self.game.state is not State.RUNNING:
                next_tick = now + self.game.interval
            self.poll_watch_file(now)
            self.draw()
            curses.napms(FRAME_NAP_MS)
            self.frame += 1
        if self.game:
            self.scores.set(self.mode, self.game.score)

    def on_event(self, event: Optional[Event]) -> None:
        if event in (Event.DIED, Event.WON):
            self.best = self.scores.set(self.mode, self.game.score)
            if not self.opts.quiet:
                curses.beep()

    def poll_watch_file(self, now: float) -> None:
        """Track the flag both ways.

        Claude finishing is not the end of the story: the next prompt
        clears the flag again, and the header has to go back to saying so.
        """
        if not self.opts.watch_file or now < self._next_watch_poll:
            return
        self._next_watch_poll = now + WATCH_POLL
        done = os.path.exists(self.opts.watch_file)
        if done == self.claude_done:
            return
        self.claude_done = done
        if not done:
            return
        self.done_at = now
        if not self.opts.quiet:
            curses.beep()
        if self.opts.exit_when_done:
            self.quit = True

    def handle_input(self) -> None:
        game = self.game
        while True:
            key = self.stdscr.getch()
            if key == -1:
                return
            if key == curses.KEY_RESIZE:
                self.on_resize()
                game = self.game
                continue
            if key in (ord("q"), ord("Q")):
                self.quit = True
                return
            if game is None:
                continue
            if key in KEY_TO_DIR:
                game.turn(KEY_TO_DIR[key])
                # An input during the pause menu also resumes play.
                if game.state is State.PAUSED:
                    game.toggle_pause()
                continue
            if key in (ord("p"), ord("P"), ord(" ")):
                if game.alive:
                    game.toggle_pause()
                continue
            if key in (ord("r"), ord("R")) and not game.alive:
                self.new_game()
                continue

    def on_resize(self) -> None:
        """Rebuild the board when the terminal changes size.

        A resize mid-game would move the walls under the player, so the run
        restarts rather than silently teleporting the snake out of bounds.
        """
        try:
            curses.resize_term(0, 0)
        except (curses.error, AttributeError):
            pass
        self.stdscr.clear()
        rows, cols = self.stdscr.getmaxyx()
        try:
            height, width = board_size(rows, cols)
        except TooSmall:
            if self.game:
                self.best = self.scores.set(self.mode, self.game.score)
            self.game = None
            return
        if self.game is None or (height, width) != (self.game.height, self.game.width):
            if self.game:
                self.best = self.scores.set(self.mode, self.game.score)
            self.new_game()

    # -- rendering ---------------------------------------------------------

    def draw(self) -> None:
        self.stdscr.erase()
        rows, cols = self.stdscr.getmaxyx()
        try:
            board_size(rows, cols)
        except TooSmall as exc:
            self.center(
                max(0, rows // 2 - 1),
                fit(["terminal too small", "too small"], cols),
                self.attr(P_ALERT, curses.A_BOLD),
            )
            self.center(rows // 2, exc.short, self.attr(P_DIM))
            self.center(rows // 2 + 1, fit(["resize to play, q quits", "q quits"], cols), self.attr(P_DIM))
            self.stdscr.refresh()
            return
        if self.game is None:
            self.stdscr.refresh()
            return

        game = self.game
        board_w_cols = game.width * CELL_W
        left = max(0, (cols - (board_w_cols + 2)) // 2)
        top = 1

        self.draw_header(left, board_w_cols)
        self.draw_frame(top, left, game.height, board_w_cols)

        origin_y, origin_x = top + 1, left + 1
        if game.food:
            self.draw_cell(origin_y, origin_x, game.food, P_FOOD, "**")
        for index, cell in enumerate(game.snake):
            if index == 0:
                self.draw_cell(origin_y, origin_x, cell, P_HEAD, "OO", curses.A_BOLD)
            else:
                self.draw_cell(origin_y, origin_x, cell, P_BODY, "oo")

        self.draw_footer(rows, left, board_w_cols)
        if game.state is State.PAUSED:
            self.draw_overlay("PAUSED", ["any arrow to resume", "q quit"])
        elif game.state is State.GAME_OVER:
            self.draw_overlay(
                "GAME OVER",
                [f"score {game.score}   best {self.best}", "r play again    q quit"],
            )
        elif game.state is State.WON:
            self.draw_overlay(
                "YOU FILLED THE BOARD",
                [f"score {game.score}   best {self.best}", "r play again    q quit"],
            )
        self.stdscr.refresh()

    def draw_cell(self, oy: int, ox: int, cell, pair: int, mono: str, extra: int = 0) -> None:
        row, col = cell
        text = "  " if self.color else mono
        self.put(oy + row, ox + col * CELL_W, text, self.attr(pair, extra))

    def draw_header(self, left: int, board_w_cols: int) -> None:
        """Title, score and Claude status, shrunk to whatever width there is.

        The game often lives in a narrow split, so every segment has a
        ladder of shorter spellings rather than one that overflows.
        """
        game = self.game
        inner_left = left + 1
        right_edge = left + board_w_cols + 1

        variants, pair = self.status_variants()
        # The status is why the pane is open, but never at the cost of the
        # score: leave room for the shortest score line before fitting it.
        status = fit(variants, board_w_cols - MIN_SCORE_COLS)
        stats_room = board_w_cols - (len(status) + 2 if status else 0)
        stats = fit(
            [
                f"SNAKE  score {game.score}   best {self.best}   lv {game.level}",
                f"SNAKE  {game.score} / {self.best}  lv {game.level}",
                f"score {game.score}  best {self.best}  lv {game.level}",
                f"{game.score} / {self.best}  lv {game.level}",
                f"{game.score} lv{game.level}",
                f"{game.score}/{self.best}",
                f"{game.score}",
            ],
            stats_room,
        )
        if stats.startswith("SNAKE"):
            self.put(0, inner_left, "SNAKE", self.attr(P_FRAME, curses.A_BOLD))
            self.put(0, inner_left + 5, stats[5:], self.attr(P_DIM))
        else:
            self.put(0, inner_left, stats, self.attr(P_DIM))
        if status:
            self.put(
                0, right_edge - len(status), status, self.attr(pair, curses.A_BOLD)
            )

    def status_variants(self):
        """Spellings of the Claude status, longest first."""
        if not self.opts.watch_file:
            return [], P_DIM
        if self.claude_done:
            # Blink the good news for a few seconds, then settle down.
            fresh = time.monotonic() - self.done_at < DONE_BLINK_SECONDS
            if fresh and (self.frame // 30) % 2 == 0:
                return ["* CLAUDE IS DONE *", "* DONE *", "*"], P_DONE
            return ["  claude is done  ", "  done  ", " "], P_DONE
        spin = SPINNER[(self.frame // 12) % len(SPINNER)]
        return [f"{spin} claude is working", f"{spin} working", spin], P_THINK

    def draw_frame(self, top: int, left: int, height: int, board_w_cols: int) -> None:
        attr = self.attr(P_FRAME)
        edge = "." if self.opts.wrap else "-"
        side = ":" if self.opts.wrap else "|"
        self.put(top, left, "+" + edge * board_w_cols + "+", attr)
        for row in range(height):
            self.put(top + 1 + row, left, side, attr)
            self.put(top + 1 + row, left + board_w_cols + 1, side, attr)
        self.put(top + 1 + height, left, "+" + edge * board_w_cols + "+", attr)

    def draw_footer(self, rows: int, left: int, board_w_cols: int) -> None:
        mode = "wrap   " if self.opts.wrap else ""
        hint = fit(
            [
                mode + "arrows/wasd move   p pause   r restart   q quit",
                mode + "arrows/wasd  p pause  r restart  q quit",
                "wasd  p pause  r restart  q quit",
                "wasd   p   r   q",
                "q quit",
            ],
            board_w_cols,
        )
        self.put(rows - 1, left + 1, hint, self.attr(P_DIM, curses.A_DIM))

    def draw_overlay(self, title: str, lines) -> None:
        rows, cols = self.stdscr.getmaxyx()
        width = max(len(title), *(len(line) for line in lines)) + 6
        width = min(width, cols - 2)
        top = max(0, rows // 2 - (len(lines) + 4) // 2)
        left = max(0, (cols - width) // 2)
        attr = self.attr(P_FRAME)
        blank = " " * width
        self.put(top, left, "+" + "-" * (width - 2) + "+", attr)
        for offset in range(len(lines) + 2):
            self.put(top + 1 + offset, left, "|", attr)
            self.put(top + 1 + offset, left + 1, blank[: width - 2])
            self.put(top + 1 + offset, left + width - 1, "|", attr)
        self.put(top + len(lines) + 3, left, "+" + "-" * (width - 2) + "+", attr)
        self.center(top + 1, title, self.attr(P_ALERT, curses.A_BOLD))
        for offset, line in enumerate(lines):
            self.center(top + 3 + offset, line, self.attr(P_DIM))


def run(opts) -> int:
    """Entry point used by ``python -m snake``."""

    def _main(stdscr):
        SnakeUI(stdscr, opts).run()

    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    except TooSmall as exc:
        print(f"claude-snake: {exc}")
        return 1
    return 0
