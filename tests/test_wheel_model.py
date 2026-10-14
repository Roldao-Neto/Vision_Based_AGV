import numpy as np
import pytest
from wheel_model import (
    first_order_counts,
    fit_first_order,
    gain_with_offset,
    ramp_line,
    ramp_start,
    rise_times,
    steady_line,
)


def test_fit_first_order_recovers_quantized_step():
    t = np.arange(0, 1.0, 0.002)
    x = np.floor(first_order_counts(t, 1500.0, 0.12))  # encoder counts are integers
    fit = fit_first_order(t, x)
    assert fit.v_ss == pytest.approx(1500.0, rel=0.01)
    assert fit.tau == pytest.approx(0.12, rel=0.03)
    assert fit.rms < 1.0


def test_rise_times_match_first_order():
    t = np.arange(0, 1.0, 0.002)
    x = first_order_counts(t, 1000.0, 0.1)
    v_end, (t63,) = rise_times(t, x, (0.632,))
    assert v_end == pytest.approx(1000.0, rel=0.01)
    assert t63 == pytest.approx(0.1, abs=0.01)


def test_steady_line_and_fixed_offset_gain():
    u = np.array([0.2, 0.25, 0.3])
    v = 7000.0 * (u - 0.07)
    k, u0 = steady_line(u, v)
    assert k == pytest.approx(7000.0)
    assert u0 == pytest.approx(0.07)
    assert gain_with_offset(u, v, 0.07) == pytest.approx(7000.0)


def test_ramp_start_skips_isolated_counts():
    counts = np.array([0, 0, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8])
    duty = np.arange(len(counts)) / 1000
    i = ramp_start(duty, counts, run=5)
    assert i == 5  # interval 4 -> 5 starts five moving intervals in a row
    assert duty[i] == pytest.approx(0.005)


def test_ramp_start_without_motion_raises():
    with pytest.raises(ValueError):
        ramp_start(np.zeros(10), np.zeros(10), run=5)


def test_ramp_line_removes_first_order_lag():
    # Simulate tau dv/dt + v = K (u - u0) on a 5 %/s ramp, sampled every 20 ms.
    k_true, u0_true, tau, rate = 7000.0, 0.07, 0.13, 0.05
    h, dt = 0.0005, 0.02
    v = x = 0.0
    ts, us, xs = [], [], []
    for i in range(int(3.2 / h) + 1):
        t = i * h
        u = rate * t
        if i % int(dt / h) == 0:
            ts.append(t)
            us.append(u)
            xs.append(x)
        v += (max(k_true * (u - u0_true), 0.0) - v) / tau * h
        x += v * h
    k, u0, n = ramp_line(np.array(ts), np.array(us), np.array(xs), tau, min_speed=200.0)
    assert n > 10
    assert k == pytest.approx(k_true, rel=0.02)
    assert u0 == pytest.approx(u0_true, abs=0.002)
