"""STM32 clock -> Linux monotonic clock, from the receive times of the pose notifications.

t_ms is the STM32's millis(), never synchronized with Linux. Every message arrives some delay
after it was sent, so receive - t_ms = offset + delay with delay >= 0; the least-delayed
message of a sliding window gives the offset. The two clocks drift ~900 ppm apart (measured on
Day 3, docs/logs/day3-linux.md), so the window's minimum is its oldest message and lags the
true offset by ~0.9 ms per second of window: 2 s keeps that at ~2 ms, and 50 poses in it are
plenty, with a jitter floor of ~0.4 ms.
"""

from collections import deque


class ClockSync:
    def __init__(self, window_s: float = 2.0):
        self.window_s = window_s
        # (receive time, receive - t) with increasing differences: the front is the window's minimum
        self._candidates: deque[tuple[float, float]] = deque()

    def update(self, rx_s: float, t_ms: int) -> tuple[float, float]:
        """One message received at rx_s (Linux monotonic, s) carrying t_ms. Returns the
        offset (s) and this message's delay over it (ms)."""
        diff = rx_s - t_ms * 1e-3
        while self._candidates and self._candidates[-1][1] >= diff:
            self._candidates.pop()
        self._candidates.append((rx_s, diff))
        while self._candidates[0][0] < rx_s - self.window_s:
            self._candidates.popleft()
        offset = self._candidates[0][1]
        return offset, (diff - offset) * 1e3

    @property
    def offset(self) -> float | None:
        return self._candidates[0][1] if self._candidates else None

    def to_linux(self, t_ms: int) -> float:
        """t_ms on the Linux monotonic clock (s); needs at least one update."""
        offset = self.offset
        if offset is None:
            raise RuntimeError("no message received yet")
        return t_ms * 1e-3 + offset
