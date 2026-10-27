import pytest
from clock_sync import ClockSync


def test_offset_is_the_least_delayed_message():
    c = ClockSync()
    # STM32 clock 1000 s behind Linux; delays 12, 3 and 20 ms
    assert c.update(1001.012, 1000) == pytest.approx((1000.012, 0.0))
    assert c.update(1001.043, 1040) == pytest.approx((1000.003, 0.0))
    offset, delay = c.update(1001.100, 1080)
    assert offset == pytest.approx(1000.003)
    assert delay == pytest.approx(17.0)
    assert c.to_linux(1080) == pytest.approx(1001.083)  # sent 17 ms before it was received


def test_window_forgets_old_minimum():
    # The STM32 clock runs 100 ppm slow, so receive - t grows ~0.1 ms/s; a session-long minimum
    # would keep the first value, the 30 s window follows the drift.
    c = ClockSync(window_s=30.0)
    rows = []
    offset = delay = 0.0
    for i in range(1201):  # 25 Hz for 48 s, every message delayed 5 ms
        rx = 10.0 + i * 0.04 + 0.005
        t_ms = round(i * 40 * (1 - 1e-4))
        rows.append((rx, rx - t_ms * 1e-3))
        offset, delay = c.update(rx, t_ms)
    last_rx = rows[-1][0]
    window_min = min(d for rx, d in rows if rx >= last_rx - 30.0)
    assert offset == pytest.approx(window_min)
    assert offset > rows[0][1] + 1e-3  # moved on from the first sample
    assert delay == pytest.approx(1e3 * (rows[-1][1] - window_min))


def test_no_offset_before_the_first_message():
    c = ClockSync()
    assert c.offset is None
    with pytest.raises(RuntimeError):
        c.to_linux(0)
