"""Monotonic operation timing helpers."""

from time import perf_counter


class OperationTimer:
    """Measure one operation in whole milliseconds."""

    def __init__(self) -> None:
        """Start the monotonic timer immediately."""
        self._started = perf_counter()

    def elapsed_ms(self) -> int:
        """Return a stable non-negative elapsed duration."""
        return max(0, round((perf_counter() - self._started) * 1000))
