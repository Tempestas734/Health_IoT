from __future__ import annotations

from collections import deque


class MovingAverageFilter:
    """Keep the last N numeric values and expose their moving average."""

    def __init__(self, window_size: int = 5):
        self.window_size = max(1, int(window_size))
        self._values: deque[float] = deque(maxlen=self.window_size)

    def add(self, value: float | int) -> float:
        numeric_value = float(value)
        self._values.append(numeric_value)
        return self.average()

    def average(self) -> float:
        if not self._values:
            return 0.0
        return sum(self._values) / len(self._values)

    def clear(self) -> None:
        self._values.clear()

    @property
    def last_value(self) -> float | None:
        if not self._values:
            return None
        return self._values[-1]


def is_outlier(new_value: float | int, last_value: float | int | None, threshold: float | int) -> bool:
    if last_value is None:
        return False
    return abs(float(new_value) - float(last_value)) > float(threshold)
