"""Wheel speed loop design and simulation (PC only).

Controller, per wheel, every 20 ms tick, in counts/s:

    u = pwm0·sign(v_ref) + (v_ref + tau·a_ref)/K + Kp·e + I,   e = (v_ref + v_ref_prev)/2 - v_measured

- feedforward: static friction offset, steady-state gain and the profile's commanded
  acceleration a_ref (not a derivative of v_ref);
- PI by pole-zero cancellation: Ti = tau, Kp = tau/(K·Tcl), Ki = Kp/Ti = 1/(K·Tcl), so the
  loop C·G = 1/(Tcl·s) for the model G = K/(tau·s + 1);
- anti-windup by conditional integration: the integrator only moves while u is not clamped,
  or when the error would bring u back inside the limit;
- below `v_min` (|v_ref|) the wheel coasts (u = 0) and the integrator is reset;
- the measured speed is the mean over the last tick, so e compares it with the mean
  reference over the same tick (`mid_tick_ref`). The firmware's `wheel_pi` does the same.

The plant is the identified model tau·dv/dt + v = K·(|u| - pwm0) (zero drive below pwm0,
the wheel cannot be driven backwards by friction), integrated finely between ticks, with
integer encoder counts and the speed measured from the count delta over the tick, as the
firmware's `wheel_speed` does.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

TICK = 0.02  # s
MM_PER_COUNT = 67.5 * np.pi / 1319.75  # nominal wheel, config::kCountsPerRev

Profile = Callable[[float], tuple[float, float]]  # t -> (v_ref, a_ref) in counts/s, counts/s²


@dataclass(frozen=True)
class WheelModel:
    k: float  # counts/s per unit duty
    tau: float  # s
    pwm0: float  # duty


@dataclass(frozen=True)
class PiGains:
    kp: float  # duty per count/s
    ki: float  # duty per count (per count/s per s)


def pi_gains(model: WheelModel, t_cl: float) -> PiGains:
    """Pole-zero cancellation: closed loop (without feedforward) = 1/(t_cl·s + 1)."""
    return PiGains(model.tau / (model.k * t_cl), 1 / (model.k * t_cl))


def ramp_profile(accel_mps2: float, v_max_mps: float, t0: float = 0.0) -> Profile:
    """0 -> v_max at a constant acceleration starting at t0, then hold."""
    a = accel_mps2 * 1000 / MM_PER_COUNT
    v_max = v_max_mps * 1000 / MM_PER_COUNT

    def profile(t: float) -> tuple[float, float]:
        v = a * (t - t0)
        if v <= 0:
            return 0.0, 0.0
        return (v_max, 0.0) if v >= v_max else (v, a)

    return profile


def step_profile(v_mps: float, t0: float) -> Profile:
    v = v_mps * 1000 / MM_PER_COUNT
    return lambda t: (v if t >= t0 else 0.0, 0.0)


@dataclass(frozen=True)
class SimResult:
    t: np.ndarray  # tick times, s
    v_ref: np.ndarray  # counts/s at each tick
    v_true: np.ndarray  # plant speed at each tick, counts/s
    v_meas: np.ndarray  # speed measured over the previous tick, counts/s
    u: np.ndarray  # duty applied from each tick on


def simulate(
    plant: WheelModel,
    ctrl: WheelModel,
    t_cl: float,
    profile: Profile,
    duration: float,
    u_max: float = 0.5,
    v_min_mps: float = 0.005,
    accel_ff: bool = True,
    mid_tick_ref: bool = True,
    h: float = 0.0002,
) -> SimResult:
    """One wheel in closed loop. `ctrl` is the model the controller was designed with,
    `plant` the one that is simulated (they differ to test robustness)."""
    g = pi_gains(ctrl, t_cl)
    v_min = v_min_mps * 1000 / MM_PER_COUNT
    per_tick = round(TICK / h)
    v = pos = integ = u = v_ref_prev = 0.0
    last_count = 0
    rows = []
    for n in range(round(duration / TICK) + 1):
        t = n * TICK
        count = int(np.floor(pos))
        v_meas = (count - last_count) / TICK
        last_count = count
        v_ref, a_ref = profile(t)
        if abs(v_ref) < v_min:
            u = integ = 0.0
        else:
            e = ((v_ref + v_ref_prev) / 2 if mid_tick_ref else v_ref) - v_meas
            ff = ctrl.pwm0 * np.sign(v_ref) + (v_ref + (ctrl.tau * a_ref if accel_ff else 0.0)) / ctrl.k
            u_raw = ff + g.kp * e + integ
            u = float(np.clip(u_raw, -u_max, u_max))
            if u == u_raw or np.sign(e) != np.sign(u_raw):
                integ += g.ki * e * TICK
        v_ref_prev = v_ref
        rows.append((t, v_ref, v, v_meas, u))
        drive = plant.k * max(abs(u) - plant.pwm0, 0.0)
        for _ in range(per_tick):
            v += (drive - v) / plant.tau * h
            v = max(v, 0.0)
            pos += v * h
    a = np.array(rows)
    return SimResult(a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4])


def step_metrics(res: SimResult, t0: float, v_final: float, band: float = 0.02) -> tuple[float, float]:
    """Overshoot (fraction of v_final) and settling time to ±band of v_final, on the true speed."""
    after = res.t >= t0
    overshoot = float((res.v_true[after].max() - v_final) / v_final)
    outside = after & (np.abs(res.v_true - v_final) > band * v_final)
    settle = float(res.t[outside].max() - t0 + TICK) if outside.any() else 0.0
    return overshoot, settle
