"""Small in-process metric registry for deterministic Phase 7 counters."""

from collections import defaultdict


class MetricsRegistry:
    """Collect counters and latest timing values without external services."""

    def __init__(self) -> None:
        """Initialize empty counter and timing maps."""
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._timings: dict[str, int] = {}

    def increment(self, name: str, value: int = 1) -> None:
        """Increment one named counter."""
        self._counters[name] += value

    def observe_ms(self, name: str, value: int) -> None:
        """Record the latest non-negative duration."""
        self._timings[name] = max(0, value)

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Return a copy safe for health and test inspection."""
        return {"counters": dict(self._counters), "timings_ms": dict(self._timings)}
