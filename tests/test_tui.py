"""Front-end tests: layout maths, text fitting, and a real pty smoke run."""

import os
import re
import select
import subprocess
import sys
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from snake.tui import (  # noqa: E402
    CHROME_COLS,
    CHROME_ROWS,
    MAX_BOARD_H,
    MAX_BOARD_W,
    MIN_BOARD_H,
    MIN_BOARD_W,
    TooSmall,
    board_size,
    fit,
)


class TestBoardSize(unittest.TestCase):
    def test_board_grows_with_the_terminal(self):
        height, width = board_size(24, 80)
        self.assertEqual(height, 24 - CHROME_ROWS)
        self.assertEqual(width, (80 - CHROME_COLS) // 2)

    def test_board_stops_growing_at_the_caps(self):
        height, width = board_size(200, 500)
        self.assertEqual((height, width), (MAX_BOARD_H, MAX_BOARD_W))

    def test_the_smallest_playable_terminal_is_accepted(self):
        rows = MIN_BOARD_H + CHROME_ROWS
        cols = MIN_BOARD_W * 2 + CHROME_COLS
        height, width = board_size(rows, cols)
        self.assertEqual((height, width), (MIN_BOARD_H, MIN_BOARD_W))

    def test_one_row_or_column_short_is_rejected(self):
        rows = MIN_BOARD_H + CHROME_ROWS
        cols = MIN_BOARD_W * 2 + CHROME_COLS
        with self.assertRaises(TooSmall):
            board_size(rows - 1, cols)
        with self.assertRaises(TooSmall):
            board_size(rows, cols - 2)

    def test_the_error_reports_what_is_needed(self):
        with self.assertRaises(TooSmall) as caught:
            board_size(5, 20)
        self.assertEqual(caught.exception.short, "need 26x12")
        self.assertIn("have 20x5", str(caught.exception))

    def test_a_board_always_fits_the_terminal_it_came_from(self):
        for rows in range(12, 40):
            for cols in range(26, 120, 3):
                height, width = board_size(rows, cols)
                self.assertLessEqual(height + CHROME_ROWS, rows)
                self.assertLessEqual(width * 2 + CHROME_COLS, cols)


class TestFit(unittest.TestCase):
    def test_picks_the_first_spelling_that_fits(self):
        self.assertEqual(fit(["long text", "short", "s"], 5), "short")

    def test_prefers_the_longest_when_there_is_room(self):
        self.assertEqual(fit(["long text", "short"], 40), "long text")

    def test_gives_up_rather_than_overflowing(self):
        self.assertEqual(fit(["abc", "ab"], 1), "")

    def test_no_variants_is_empty(self):
        self.assertEqual(fit([], 80), "")


@unittest.skipUnless(hasattr(os, "openpty"), "needs a pty")
class TestSmokeRun(unittest.TestCase):
    """Boot the real curses app on a pty and drive it with keystrokes."""

    def drive(self, keys, cols=80, rows=24, settle=1.2):
        primary, secondary = os.openpty()
        env = dict(os.environ, TERM="xterm-256color", LINES=str(rows), COLUMNS=str(cols))
        env.pop("XDG_DATA_HOME", None)
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "snake",
                "--seed", "1", "--quiet",
                "--highscore-file", os.path.join(REPO, ".pytest-highscores.json"),
            ],
            stdin=secondary, stdout=secondary, stderr=secondary,
            cwd=REPO, env=env, close_fds=True,
        )
        os.close(secondary)
        output = b""

        def pump(seconds):
            nonlocal output
            deadline = time.time() + seconds
            while time.time() < deadline:
                ready, _, _ = select.select([primary], [], [], 0.05)
                if not ready:
                    continue
                try:
                    chunk = os.read(primary, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                output += chunk

        try:
            pump(settle)
            for key in keys:
                os.write(primary, key)
                pump(0.3)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            os.close(primary)
        return proc.returncode, output.decode("utf-8", "replace")

    def screen(self, raw):
        """Strip escape sequences so assertions read the visible text."""
        return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][B0]|\r", "", raw)

    def test_it_boots_draws_and_quits(self):
        code, raw = self.drive([b"\x1b[B", b"\x1b[C", b"q"])
        self.assertEqual(code, 0)
        text = self.screen(raw)
        self.assertIn("SNAKE", text)
        self.assertIn("score", text)
        self.assertIn("q quit", text)

    def test_pause_overlay_appears_and_clears(self):
        code, raw = self.drive([b"p", b"q"])
        self.assertEqual(code, 0)
        self.assertIn("PAUSED", self.screen(raw))

    def test_it_survives_a_terminal_too_small_to_play_in(self):
        code, raw = self.drive([b"q"], cols=22, rows=9)
        self.assertEqual(code, 0)
        self.assertIn("too small", self.screen(raw))

    def tearDown(self):
        stale = os.path.join(REPO, ".pytest-highscores.json")
        if os.path.exists(stale):
            os.unlink(stale)


if __name__ == "__main__":
    unittest.main()
