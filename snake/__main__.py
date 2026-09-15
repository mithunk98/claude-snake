"""Command line entry point: ``python3 -m snake``."""

from __future__ import annotations

import argparse
import sys

from .game import SPEED_PRESETS
from .scores import default_path


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="snake",
        description="A terminal snake game to play while Claude Code works.",
    )
    parser.add_argument(
        "--wrap",
        action="store_true",
        help="edges teleport instead of killing you",
    )
    parser.add_argument(
        "--speed",
        choices=sorted(SPEED_PRESETS),
        default="normal",
        help="starting speed (default: normal)",
    )
    parser.add_argument(
        "--watch-file",
        metavar="PATH",
        help="show 'claude is done' once this file appears",
    )
    parser.add_argument(
        "--exit-when-done",
        action="store_true",
        help="quit as soon as --watch-file appears, even mid-game",
    )
    parser.add_argument(
        "--highscore-file",
        metavar="PATH",
        default=default_path(),
        help="where to keep high scores (default: %(default)s)",
    )
    parser.add_argument("--no-color", action="store_true", help="plain ASCII board")
    parser.add_argument("--quiet", action="store_true", help="never ring the bell")
    parser.add_argument(
        "--seed", type=int, help="fix the food sequence, for reproducible runs"
    )
    opts = parser.parse_args(argv)
    opts.interval = SPEED_PRESETS[opts.speed]
    return opts


def main(argv=None) -> int:
    opts = parse_args(argv)
    # Imported late so --help works on a terminal curses cannot initialise.
    from .tui import run

    return run(opts)


if __name__ == "__main__":
    sys.exit(main())
