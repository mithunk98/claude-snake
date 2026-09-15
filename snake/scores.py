"""High score persistence.

A missing, unreadable or corrupt score file must never cost you a game, so
every failure here degrades to "no high score" instead of raising.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, Optional


def default_path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "claude-snake", "highscores.json")


class HighScores:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_path()
        self.scores: Dict[str, int] = self._load()

    def _load(self) -> Dict[str, int]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(key): int(value)
            for key, value in data.items()
            if isinstance(value, (int, float))
        }

    def get(self, mode: str) -> int:
        return self.scores.get(mode, 0)

    def set(self, mode: str, score: int) -> int:
        """Record ``score`` if it beats the stored best. Returns the best."""
        if score <= self.get(mode):
            return self.get(mode)
        self.scores[mode] = score
        self._save()
        return score

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            # Write to a sibling temp file and rename, so an interrupted
            # save cannot leave a half-written file behind.
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=os.path.dirname(self.path) or ".",
                prefix=".highscores-",
                delete=False,
            )
            try:
                with handle:
                    json.dump(self.scores, handle, indent=2, sort_keys=True)
                os.replace(handle.name, self.path)
            except BaseException:
                try:
                    os.unlink(handle.name)
                except OSError:
                    pass
                raise
        except OSError:
            pass
