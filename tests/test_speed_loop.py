import numpy as np
import pytest
from speed_loop import (
    MM_PER_COUNT,
    WheelModel,
    pi_gains,
    ramp_profile,
    simulate,
    step_metrics,
    step_profile,
)

MODEL = WheelModel(k=7000.0, tau=0.13, pwm0=0.07)


def test_pi_gains_cancel_the_plant_pole():
    g = pi_gains(MODEL, 0.1)
    assert g.kp / g.ki == pytest.approx(MODEL.tau)  # Ti = tau
    assert g.kp * MODEL.k / MODEL.tau == pytest.approx(1 / 0.1)  # C·G = 1/(Tcl·s)


def test_ramp_is_tracked_and_hold_has_no_steady_error():
    res = simulate(MODEL, MODEL, 0.1, ramp_profile(0.5, 0.25), 1.5)
    hold = res.t > 1.0
    v_hold = 0.25 * 1000 / MM_PER_COUNT
    assert np.abs(res.v_true[hold] - v_hold).max() < 0.02 * v_hold
    assert res.u.max() <= 0.5


def test_coasts_and_resets_below_minimum_speed():
    res = simulate(MODEL, MODEL, 0.1, step_profile(0.1, 0.2), 0.4)
    assert (res.u[res.t < 0.2] == 0).all()


def test_conditional_integration_limits_windup():
    # A cap too low for the setpoint: the integrator must not keep growing while clamped,
    # so once the setpoint drops the duty leaves the cap within a couple of ticks.
    v_hi = 0.25 * 1000 / MM_PER_COUNT
    v_lo = 0.05 * 1000 / MM_PER_COUNT
    res = simulate(MODEL, MODEL, 0.1, lambda t: (v_hi if t < 1.0 else v_lo, 0.0), 1.2, u_max=0.2)
    assert res.u[(res.t > 0.5) & (res.t < 1.0)].min() == pytest.approx(0.2)
    assert res.u[res.t >= 1.04].max() < 0.2


def test_step_metrics_on_first_order_response():
    res = simulate(MODEL, MODEL, 0.1, step_profile(0.1, 0.1), 1.5)
    overshoot, settle = step_metrics(res, 0.1, 0.1 * 1000 / MM_PER_COUNT)
    assert 0 <= overshoot < 0.4
    assert 0 < settle < 1.4
