"""High scores must never cost you a game, however broken the file is."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.scores import HighScores  # noqa: E402


class TestHighScores(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "scores.json")
        self.addCleanup(self.dir.cleanup)

    def test_missing_file_reads_as_zero(self):
        self.assertEqual(HighScores(self.path).get("walls"), 0)

    def test_a_record_round_trips(self):
        scores = HighScores(self.path)
        self.assertEqual(scores.set("walls", 120), 120)
        self.assertEqual(HighScores(self.path).get("walls"), 120)

    def test_a_worse_score_does_not_overwrite(self):
        scores = HighScores(self.path)
        scores.set("walls", 120)
        self.assertEqual(scores.set("walls", 30), 120)
        self.assertEqual(HighScores(self.path).get("walls"), 120)

    def test_modes_are_scored_separately(self):
        scores = HighScores(self.path)
        scores.set("walls", 120)
        scores.set("wrap", 40)
        self.assertEqual(scores.get("walls"), 120)
        self.assertEqual(scores.get("wrap"), 40)

    def test_corrupt_file_is_ignored_not_raised(self):
        with open(self.path, "w") as handle:
            handle.write("{not json at all")
        scores = HighScores(self.path)
        self.assertEqual(scores.get("walls"), 0)
        self.assertEqual(scores.set("walls", 10), 10)

    def test_a_file_of_the_wrong_shape_is_ignored(self):
        with open(self.path, "w") as handle:
            json.dump(["not", "a", "mapping"], handle)
        self.assertEqual(HighScores(self.path).get("walls"), 0)

    def test_junk_values_are_dropped_but_good_ones_survive(self):
        with open(self.path, "w") as handle:
            json.dump({"walls": 90, "wrap": "lots"}, handle)
        scores = HighScores(self.path)
        self.assertEqual(scores.get("walls"), 90)
        self.assertEqual(scores.get("wrap"), 0)

    def test_an_unwritable_location_is_survivable(self):
        scores = HighScores(os.path.join(self.dir.name, "nope", "scores.json"))
        os.chmod(self.dir.name, 0o500)
        self.addCleanup(os.chmod, self.dir.name, 0o700)
        self.assertEqual(scores.set("walls", 10), 10)  # in memory, no crash

    def test_saving_leaves_no_temp_files_behind(self):
        HighScores(self.path).set("walls", 10)
        self.assertEqual(sorted(os.listdir(self.dir.name)), ["scores.json"])


if __name__ == "__main__":
    unittest.main()
