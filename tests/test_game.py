"""Rules tests. Run with: python3 -m unittest discover -s tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import (  # noqa: E402
    FOODS_PER_LEVEL,
    MAX_LEVEL,
    MIN_INTERVAL,
    Direction,
    Event,
    SnakeGame,
    State,
)


def game(height=10, width=14, **kwargs):
    """A game with the food parked out of the way unless a test moves it."""
    instance = SnakeGame(height, width, seed=7, **kwargs)
    instance.food = (0, width - 1)
    return instance


def place(instance, cells, direction=Direction.RIGHT):
    """Force the snake to an exact shape; head first."""
    instance.snake.clear()
    instance.snake.extend(cells)
    instance.cells = set(cells)
    instance.direction = direction
    instance._queued.clear()


class TestMovement(unittest.TestCase):
    def test_starts_alive_with_a_body_and_food(self):
        instance = SnakeGame(10, 14, seed=1)
        self.assertEqual(instance.state, State.RUNNING)
        self.assertEqual(len(instance.snake), 3)
        self.assertIsNotNone(instance.food)
        self.assertNotIn(instance.food, instance.cells)

    def test_step_moves_head_and_keeps_length(self):
        instance = game()
        head = instance.head
        self.assertEqual(instance.step(), Event.MOVED)
        self.assertEqual(instance.head, (head[0], head[1] + 1))
        self.assertEqual(len(instance.snake), 3)

    def test_cells_stay_in_sync_with_the_body(self):
        instance = game()
        for _ in range(5):
            instance.step()
        self.assertEqual(instance.cells, set(instance.snake))

    def test_turning_changes_direction(self):
        instance = game()
        instance.turn(Direction.UP)
        row, col = instance.head
        instance.step()
        self.assertEqual(instance.head, (row - 1, col))

    def test_cannot_reverse_onto_own_neck(self):
        instance = game()
        instance.turn(Direction.LEFT)
        self.assertEqual(instance.step(), Event.MOVED)
        self.assertEqual(instance.direction, Direction.RIGHT)

    def test_two_turns_in_one_tick_are_both_kept(self):
        instance = game()
        row, col = instance.head
        instance.turn(Direction.UP)
        instance.turn(Direction.LEFT)
        instance.step()
        self.assertEqual(instance.head, (row - 1, col))
        instance.step()
        self.assertEqual(instance.head, (row - 1, col - 1))

    def test_reversal_is_judged_against_the_queued_turn(self):
        # Up then down would be a reversal once the queued up is applied.
        instance = game()
        instance.turn(Direction.UP)
        instance.turn(Direction.DOWN)
        self.assertEqual(len(instance._queued), 1)


class TestEating(unittest.TestCase):
    def test_eating_grows_the_snake_and_scores(self):
        instance = game()
        row, col = instance.head
        instance.food = (row, col + 1)
        self.assertEqual(instance.step(), Event.ATE)
        self.assertEqual(len(instance.snake), 4)
        self.assertEqual(instance.score, 10)
        self.assertEqual(instance.foods_eaten, 1)

    def test_spawned_food_never_lands_on_the_snake(self):
        instance = game()
        for _ in range(200):
            self.assertTrue(instance._spawn_food())
            self.assertNotIn(instance.food, instance.cells)

    def test_food_still_spawns_on_a_nearly_full_board(self):
        # Exercises the exhaustive branch, where sampling at random would
        # spin for a long time before it happened to hit a free cell.
        instance = game()
        free = {(0, 0), (9, 13), (4, 7)}
        instance.cells = {
            (r, c) for r in range(instance.height) for c in range(instance.width)
        } - free
        for _ in range(50):
            self.assertTrue(instance._spawn_food())
            self.assertIn(instance.food, free)

    def test_a_full_board_has_nowhere_to_put_food(self):
        instance = game()
        instance.cells = {
            (r, c) for r in range(instance.height) for c in range(instance.width)
        }
        self.assertFalse(instance._spawn_food())
        self.assertIsNone(instance.food)

    def test_level_and_speed_climb_with_food(self):
        instance = game()
        self.assertEqual(instance.level, 1)
        instance.foods_eaten = FOODS_PER_LEVEL
        self.assertEqual(instance.level, 2)
        self.assertLess(instance.interval, instance.base_interval)

    def test_speed_is_floored(self):
        instance = game()
        instance.foods_eaten = FOODS_PER_LEVEL * 500
        self.assertEqual(instance.level, MAX_LEVEL)
        self.assertGreaterEqual(instance.interval, MIN_INTERVAL)


class TestDeath(unittest.TestCase):
    def test_wall_kills(self):
        instance = game()
        place(instance, [(5, 13), (5, 12), (5, 11)])
        self.assertEqual(instance.step(), Event.DIED)
        self.assertEqual(instance.state, State.GAME_OVER)

    def test_biting_yourself_kills(self):
        instance = game()
        # A tight coil: turning down then left runs the head into the body.
        place(instance, [(5, 5), (5, 4), (4, 4), (4, 5), (4, 6)])
        instance.turn(Direction.UP)
        self.assertEqual(instance.step(), Event.DIED)

    def test_chasing_the_vacating_tail_is_legal(self):
        instance = game()
        place(instance, [(5, 5), (5, 4), (4, 4), (4, 5)], Direction.UP)
        # Head moves onto (4, 5), the cell the tail leaves this same tick.
        self.assertEqual(instance.step(), Event.MOVED)
        self.assertEqual(instance.head, (4, 5))

    def test_a_dead_game_ignores_further_steps(self):
        instance = game()
        place(instance, [(5, 13), (5, 12), (5, 11)])
        instance.step()
        head = instance.head
        self.assertIsNone(instance.step())
        self.assertEqual(instance.head, head)


class TestWrap(unittest.TestCase):
    def test_edges_teleport(self):
        instance = game(wrap=True)
        place(instance, [(5, 13), (5, 12), (5, 11)])
        self.assertEqual(instance.step(), Event.MOVED)
        self.assertEqual(instance.head, (5, 0))

    def test_top_edge_wraps_to_the_bottom(self):
        instance = game(wrap=True)
        place(instance, [(0, 5), (1, 5), (2, 5)], Direction.UP)
        instance.step()
        self.assertEqual(instance.head, (9, 5))


class TestWinning(unittest.TestCase):
    def test_filling_the_board_wins(self):
        instance = SnakeGame(8, 12, seed=3)
        row, col = instance.head
        instance.food = (row, col + 1)
        # Every cell except the one the head is about to occupy is body.
        instance.cells = {
            (r, c) for r in range(8) for c in range(12)
        } - {instance.food}
        instance.snake.clear()
        instance.snake.extend(sorted(instance.cells))
        instance.snake.appendleft((row, col))
        instance.cells.add((row, col))
        self.assertEqual(instance.step(), Event.WON)
        self.assertEqual(instance.state, State.WON)


class TestPause(unittest.TestCase):
    def test_pause_freezes_the_board(self):
        instance = game()
        instance.toggle_pause()
        head = instance.head
        self.assertIsNone(instance.step())
        self.assertEqual(instance.head, head)
        instance.toggle_pause()
        self.assertEqual(instance.step(), Event.MOVED)


class TestGuards(unittest.TestCase):
    def test_a_board_too_small_is_rejected(self):
        with self.assertRaises(ValueError):
            SnakeGame(2, 2)

    def test_reset_clears_a_finished_game(self):
        instance = game()
        place(instance, [(5, 13), (5, 12), (5, 11)])
        instance.step()
        instance.reset()
        self.assertEqual(instance.state, State.RUNNING)
        self.assertEqual(instance.score, 0)
        self.assertEqual(len(instance.snake), 3)


if __name__ == "__main__":
    unittest.main()
