"""Pure game rules for Claude Snake.

Deliberately free of curses so the rules can be unit-tested without a
terminal. The front end in ``snake.tui`` owns every byte of rendering.
"""

from __future__ import annotations

import random
from collections import deque
from enum import Enum
from typing import Deque, List, Optional, Set, Tuple

Cell = Tuple[int, int]

#: Board size limits, in cells.
MIN_HEIGHT = 8
MIN_WIDTH = 12

#: Seconds per step at level 1, and the floor no level goes below.
BASE_INTERVAL = 0.140
MIN_INTERVAL = 0.050
#: How much each level shaves off the interval, and how many foods earn one.
LEVEL_STEP = 0.010
FOODS_PER_LEVEL = 4
MAX_LEVEL = 10

SPEED_PRESETS = {"slow": 0.190, "normal": BASE_INTERVAL, "fast": 0.095}


class Direction(Enum):
    UP = (-1, 0)
    DOWN = (1, 0)
    LEFT = (0, -1)
    RIGHT = (0, 1)

    @property
    def opposite(self) -> "Direction":
        dy, dx = self.value
        return Direction((-dy, -dx))


class State(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    GAME_OVER = "game over"
    WON = "won"


class Event(Enum):
    """What a single :meth:`SnakeGame.step` turned out to be."""

    MOVED = "moved"
    ATE = "ate"
    DIED = "died"
    WON = "won"


class SnakeGame:
    """A game of snake on a ``height`` x ``width`` grid of cells.

    Coordinates are ``(row, col)`` with ``(0, 0)`` at the top left. With
    ``wrap`` the edges are portals; without it they are walls.
    """

    def __init__(
        self,
        height: int,
        width: int,
        wrap: bool = False,
        base_interval: float = BASE_INTERVAL,
        seed: Optional[int] = None,
    ) -> None:
        if height < MIN_HEIGHT or width < MIN_WIDTH:
            raise ValueError(f"board must be at least {MIN_WIDTH}x{MIN_HEIGHT} cells")
        self.height = height
        self.width = width
        self.wrap = wrap
        self.base_interval = base_interval
        self.rng = random.Random(seed)
        self.reset()

    # -- lifecycle ---------------------------------------------------------

    def reset(self) -> None:
        row = self.height // 2
        col = self.width // 3
        # Head first, tail last; start pointing right with a little body.
        self.snake: Deque[Cell] = deque([(row, col), (row, col - 1), (row, col - 2)])
        self.cells: Set[Cell] = set(self.snake)
        self.direction = Direction.RIGHT
        self._queued: Deque[Direction] = deque(maxlen=2)
        self.score = 0
        self.foods_eaten = 0
        self.state = State.RUNNING
        self.food: Optional[Cell] = None
        self._spawn_food()

    @property
    def head(self) -> Cell:
        return self.snake[0]

    @property
    def level(self) -> int:
        return min(MAX_LEVEL, 1 + self.foods_eaten // FOODS_PER_LEVEL)

    @property
    def interval(self) -> float:
        """Seconds between steps at the current level."""
        return max(MIN_INTERVAL, self.base_interval - (self.level - 1) * LEVEL_STEP)

    @property
    def alive(self) -> bool:
        return self.state in (State.RUNNING, State.PAUSED)

    # -- input -------------------------------------------------------------

    def turn(self, direction: Direction) -> None:
        """Queue a turn. Reversing onto your own neck is ignored.

        Turns are queued (up to two deep) so a quick flick like "up then
        left" inside a single tick keeps both halves instead of dropping
        one of them.
        """
        last = self._queued[-1] if self._queued else self.direction
        if direction is last or direction is last.opposite:
            return
        self._queued.append(direction)

    def toggle_pause(self) -> None:
        if self.state is State.RUNNING:
            self.state = State.PAUSED
        elif self.state is State.PAUSED:
            self.state = State.RUNNING

    # -- simulation --------------------------------------------------------

    def step(self) -> Optional[Event]:
        """Advance one tick. Returns what happened, or ``None`` if idle."""
        if self.state is not State.RUNNING:
            return None

        if self._queued:
            self.direction = self._queued.popleft()

        dy, dx = self.direction.value
        row, col = self.head
        row, col = row + dy, col + dx

        if self.wrap:
            row %= self.height
            col %= self.width
        elif not (0 <= row < self.height and 0 <= col < self.width):
            self.state = State.GAME_OVER
            return Event.DIED

        new_head = (row, col)
        growing = new_head == self.food
        tail = self.snake[-1]

        # The tail vacates its cell on this same tick, so chasing it is legal.
        blocked = self.cells
        if not growing and new_head == tail and len(self.snake) > 1:
            blocked = blocked - {tail}
        if new_head in blocked:
            self.state = State.GAME_OVER
            return Event.DIED

        if not growing:
            self.snake.pop()
            self.cells.discard(tail)
        self.snake.appendleft(new_head)
        self.cells.add(new_head)

        if not growing:
            return Event.MOVED

        self.foods_eaten += 1
        self.score += 10 + (self.level - 1) * 2
        if not self._spawn_food():
            self.state = State.WON
            return Event.WON
        return Event.ATE

    def _spawn_food(self) -> bool:
        """Place food on a free cell. False when the board is full."""
        free = self.height * self.width - len(self.cells)
        if free <= 0:
            self.food = None
            return False
        # Cheap when the board is mostly empty, exhaustive when it is not.
        if free > self.height * self.width // 4:
            while True:
                spot = (
                    self.rng.randrange(self.height),
                    self.rng.randrange(self.width),
                )
                if spot not in self.cells:
                    self.food = spot
                    return True
        empty: List[Cell] = [
            (r, c)
            for r in range(self.height)
            for c in range(self.width)
            if (r, c) not in self.cells
        ]
        self.food = self.rng.choice(empty)
        return True
