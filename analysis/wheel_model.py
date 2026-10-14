"""Wheel model identification from the Day 1 `step` and `ramp` recordings (PC only).

Model per wheel and direction, in encoder counts per second (the speed loop's unit):

    tau * dv/dt + v = K * (u - pwm0)     while the wheel moves (|u| > pwm0),

with u the duty in [0, 1] (direction sign removed). A step of duty u from rest gives
the cumulative counts

    x(t) = v_ss * (t - tau * (1 - exp(-t / tau))),   v_ss = K * (u - pwm0),

which is what the fit uses: counts (position) instead of differentiated speeds.
Every function here is pure and works on numpy arrays, so it is tested on synthetic data.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GOLDEN = (np.sqrt(5) - 1) / 2


@dataclass(frozen=True)
class StepRun:
    """A recorded `step`: sample times in s and cumulative counts per wheel."""

    t: np.ndarray
    counts_l: np.ndarray
    counts_r: np.ndarray


@dataclass(frozen=True)
class RampRun:
    """A recorded `ramp`. `duty[i]` is the duty in [-1, 1] applied between samples i-1 and i."""

    t: np.ndarray
    duty: np.ndarray
    counts_l: np.ndarray
    counts_r: np.ndarray


@dataclass(frozen=True)
class FirstOrderFit:
    v_ss: float  # counts/s
    tau: float  # s
    rms: float  # counts, residual of the position fit


def load_step(path: Path) -> StepRun:
    """Read a `*_step_<id>_L<duty>_R<duty>.csv` file (`t_us,counts_l,counts_r`)."""
    a = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return StepRun(a[:, 0] / 1e6, a[:, 1], a[:, 2])


def load_ramp(path: Path) -> RampRun:
    """Read a `*_ramp_<id>_dir<±1>_rate<rate>.csv` file (`t_us,duty,counts_l,counts_r`)."""
    a = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return RampRun(a[:, 0] / 1e6, a[:, 1] / 1000, a[:, 2], a[:, 3])


def session_sample_files(events_csv: Path) -> list[str]:
    """Sample file names of one app session, in recording order, from its events log."""
    files = []
    with open(events_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["event"] in ("step_samples", "ramp_samples", "speed_samples"):
                fields = dict(kv.split("=", 1) for kv in row["detail"].split())
                files.append(fields["file"])
    return files


@dataclass(frozen=True)
class SpeedRun:
    """A recorded closed-loop `speed` run. Row i holds the reference (counts/s) and the
    duties in [-1, 1] applied between samples i-1 and i."""

    t: np.ndarray
    v_ref: np.ndarray
    counts_l: np.ndarray
    counts_r: np.ndarray
    duty_l: np.ndarray
    duty_r: np.ndarray


def load_speed(path: Path) -> SpeedRun:
    """Read a `*_speed_<id>_v<v>_a<a>.csv` file (`t_us,v_ref,counts_l,counts_r,duty_l,duty_r`,
    duties in ten-thousandths)."""
    a = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return SpeedRun(a[:, 0] / 1e6, a[:, 1], a[:, 2], a[:, 3], a[:, 4] / 1e4, a[:, 5] / 1e4)


def first_order_counts(t: np.ndarray, v_ss: float, tau: float) -> np.ndarray:
    """Cumulative counts of a first-order speed response to a step at t = 0."""
    s = np.clip(t, 0.0, None)
    return v_ss * (s - tau * (1 - np.exp(-s / tau)))


def _v_ss_for_tau(t: np.ndarray, x: np.ndarray, tau: float) -> tuple[float, float]:
    """Least-squares v_ss for a fixed tau (the model is linear in v_ss), and the residual SSE."""
    g = first_order_counts(t, 1.0, tau)
    v = float(g @ x / (g @ g))
    r = x - v * g
    return v, float(r @ r)


def fit_first_order(
    t: np.ndarray, x: np.ndarray, tau_min: float = 0.005, tau_max: float = 1.0
) -> FirstOrderFit:
    """Fit v_ss and tau to cumulative counts x(t) of a step from rest (sign removed by the caller).

    v_ss has a closed form for each tau, so only tau is searched: a 1 ms grid, then a
    golden-section refinement around the best grid point.
    """
    grid = np.arange(tau_min, tau_max, 0.001)
    sse = np.array([_v_ss_for_tau(t, x, tau)[1] for tau in grid])
    i = int(np.argmin(sse))
    lo, hi = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    a, b = hi - GOLDEN * (hi - lo), lo + GOLDEN * (hi - lo)
    for _ in range(40):
        if _v_ss_for_tau(t, x, a)[1] < _v_ss_for_tau(t, x, b)[1]:
            hi = b
        else:
            lo = a
        a, b = hi - GOLDEN * (hi - lo), lo + GOLDEN * (hi - lo)
    tau = (lo + hi) / 2
    v_ss, err = _v_ss_for_tau(t, x, tau)
    return FirstOrderFit(v_ss, tau, float(np.sqrt(err / len(x))))


def windowed_speed(t: np.ndarray, x: np.ndarray, half: int) -> tuple[np.ndarray, np.ndarray]:
    """Speed over a centered window of 2*half sample intervals: (window centers, counts/s)."""
    v = (x[2 * half :] - x[: -2 * half]) / (t[2 * half :] - t[: -2 * half])
    return t[half:-half], v


def rise_times(
    t: np.ndarray, x: np.ndarray, fractions: tuple[float, ...], half: int = 10, ss_from: float = 0.7
) -> tuple[float, list[float]]:
    """Model-free check of tau: final speed (mean speed after `ss_from` s) and the first time
    the windowed speed reaches each fraction of it."""
    tc, v = windowed_speed(t, x, half)
    v_end = float(np.mean(v[tc > ss_from]))
    return v_end, [float(tc[np.argmax(v >= p * v_end)]) for p in fractions]


def steady_line(u: np.ndarray, v_ss: np.ndarray) -> tuple[float, float]:
    """Least-squares line v_ss = K * (u - u0) through the steady speeds: (K, u0)."""
    k, b = np.polyfit(u, v_ss, 1)
    return float(k), float(-b / k)


def gain_with_offset(u: np.ndarray, v_ss: np.ndarray, u0: float) -> float:
    """Least-squares K of v_ss = K * (u - u0) with the offset u0 fixed."""
    d = u - u0
    return float(d @ v_ss / (d @ d))


def ramp_start(duty: np.ndarray, counts: np.ndarray, run: int) -> int:
    """Index i of the first interval (between samples i-1 and i) of the first run of `run`
    consecutive intervals that each add at least one count: the start of sustained motion.
    Its duty is `duty[i]`. Counts and duty must have the direction sign removed."""
    moved = np.diff(counts) >= 1
    for i in range(len(moved) - run + 1):
        if moved[i : i + run].all():
            return i + 1
    raise ValueError("no sustained motion in the ramp")


def ramp_line(
    t: np.ndarray, duty: np.ndarray, counts: np.ndarray, tau: float, min_speed: float, half: int = 2
) -> tuple[float, float, int]:
    """Line v = K * (u - u0) through the ramp's moving part: (K, u0, points used).

    The speed is taken over 2*half intervals and paired with the mean duty applied over the
    same intervals. On a ramp of rate r the first-order speed lags the quasi-static one by
    tau * r in duty, so the duty is shifted back by that lag before the fit.
    """
    _, v = windowed_speed(t, counts, half)
    n = 2 * half
    u = np.array([duty[j + 1 : j + n + 1].mean() for j in range(len(v))])
    rate = float(np.polyfit(t[1:], duty[1:], 1)[0])
    m = v >= min_speed
    k, u0 = steady_line(u[m] - tau * rate, v[m])
    return k, u0, int(m.sum())
