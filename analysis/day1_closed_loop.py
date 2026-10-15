"""Day 1 analysis: the closed-loop speed tests on the arena floor (PC only).

Reads one app session of `speed` recordings from results/day1/ (listed in its events log),
measures the ramp tracking error and the step overshoot and settling time per wheel,
compares them with the simulation of the design model, and writes
results/day1/plots/closed_loop.csv and the plots.

Definitions (docs/logs/day1-analysis.md, section 7):
- interval speed: count delta between two samples over their time difference;
- tracking error of an interval: the profile at the interval's midpoint, i.e. the mean of
  the references computed at its two ticks, minus the interval speed. This is the error
  the firmware's PI acts on;
- smoothed: centered moving average over 5 intervals (100 ms), which takes the
  quantization (one count per interval = 50 counts/s = 8 mm/s) down to ~1.6 mm/s;
- step overshoot and settling time (±5 % and ±10 %) on the smoothed speed, before the stop
  starts. The smoothed speed still ripples ±3–5 mm/s in the hold, about the ±5 % band at
  0.1 m/s, so ±5 % is reported with ±10 % next to it.

    uv run python analysis/day1_closed_loop.py [events_csv]   # other sessions: outputs tagged with their time
"""

import csv
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from day1_identify import AMP_COLORS, INK, MUTED, PLOTS, style
from speed_loop import MM_PER_COUNT, WheelModel, ramp_profile, simulate, step_profile

DATA = Path(__file__).resolve().parent.parent / "results" / "day1"
# Closed-loop floor session of 2026-10-11, 12.6 V (docs/logs/day1-analysis.md, section 7).
SESSION = DATA / "20261011-222209_app_events.csv"
SMOOTH = 5  # intervals, 100 ms
SETTLE_BANDS = (0.05, 0.10)
T_CL, U_MAX = 0.1, 0.5  # as in config.h

WHEELS = (("L", "counts_l", "duty_l"), ("R", "counts_r", "duty_r"))
WHEEL_COLORS = {"L": AMP_COLORS[200], "R": AMP_COLORS[250]}
SIM_COLOR = MUTED


def smooth(x: np.ndarray, n: int = SMOOTH) -> np.ndarray:
    """Centered moving average; the ends average over what is available."""
    k = np.ones(n)
    return np.convolve(x, k, "same") / np.convolve(np.ones_like(x), k, "same")


def models() -> dict[tuple[str, int], WheelModel]:
    with open(PLOTS / "pi_gains.csv", newline="", encoding="utf-8") as f:
        return {(r["wheel"], int(r["dir"])): WheelModel(float(r["k"]), float(r["tau"]), float(r["pwm0"])) for r in csv.DictReader(f)}


def main() -> None:
    from wheel_model import load_speed, session_sample_files

    events = Path(sys.argv[1]) if len(sys.argv) > 1 else SESSION
    # Another session gets its own output names, so the floor tests' outputs stay.
    tag = "" if events.resolve() == SESSION.resolve() else "_" + events.name.split("_")[0]
    model = models()
    rows = []
    figs = {"ramp": [], "step": []}
    for name in session_sample_files(events):
        m = re.search(r"_speed_(\d+)_v(-?\d+)_a(\d+)\.csv$", name)
        if not m:
            continue
        run = load_speed(DATA / name)
        v_mm_s, accel = int(m.group(2)), int(m.group(3))
        if not run.counts_l.any() and not run.counts_r.any():
            print(f"{name}: no counts (motors unpowered), skipped")
            continue
        sign = 1 if v_mm_s > 0 else -1
        kind = "ramp" if accel else "step"
        v_target = v_mm_s / MM_PER_COUNT  # counts/s, signed
        dt = np.diff(run.t)
        t_mid = (run.t[1:] + run.t[:-1]) / 2
        ref_mid = np.append((run.v_ref[1:-1] + run.v_ref[2:]) / 2, 0.0)  # profile at each interval's midpoint
        # The stop starts at the first reference below the previous one (in magnitude).
        mag = np.abs(run.v_ref)
        stop_i = int(np.argmax((mag[1:] < mag[:-1] - 1) & (mag[:-1] > 0))) + 1
        t_stop = run.t[stop_i - 1]
        # Step: it is applied in the start tick, so t0 is the sample before the first reference.
        t0 = run.t[int(np.argmax(mag > 0)) - 1]
        per_wheel = {}
        for wheel, counts_attr, duty_attr in WHEELS:
            counts = getattr(run, counts_attr)
            duty = getattr(run, duty_attr)
            v = np.diff(counts) / dt
            err = (ref_mid - v) * MM_PER_COUNT * sign  # mm/s, positive = slower than the reference
            err_s = smooth(err)
            v_s = smooth(v)
            row = {"file": name, "kind": kind, "v_mm_s": v_mm_s, "accel": accel, "wheel": wheel, "duty_max": float(np.abs(duty).max())}
            before_stop = t_mid < t_stop
            if kind == "ramp":
                t_ramp_end = abs(v_target) / (accel / MM_PER_COUNT)
                up = (t_mid > 0.04) & (t_mid < t_ramp_end)
                hold = (t_mid >= t_ramp_end + 0.2) & before_stop
                row |= {
                    "err_max": float(np.abs(err[before_stop]).max()),
                    "err_rms": float(np.sqrt(np.mean(err[before_stop] ** 2))),
                    "err_s_max_up": float(np.abs(err_s[up]).max()),
                    "err_s_max_hold": float(np.abs(err_s[hold]).max()),
                    "err_mean_up": float(err[up].mean()),
                    "err_mean_hold": float(err[hold].mean()),
                    "err_s_max_stop": float(np.abs(err_s[~before_stop][:-1]).max()),
                }
            else:
                hold = (t_mid > t0) & before_stop
                vs = v_s * sign
                vt = abs(v_target)
                settle = {}
                for band in SETTLE_BANDS:
                    outside = hold & (np.abs(vs - vt) > band * vt)
                    last_out = t_mid[outside].max() if outside.any() else t0
                    settle[f"settle_{round(band * 100)}_s"] = float(last_out + 0.01 - t0)
                row |= settle | {
                    "overshoot": float((vs[hold].max() - vt) / vt),
                    "v_end_mm_s": float(vs[(t_mid > t_stop - 0.3) & before_stop].mean() * MM_PER_COUNT),
                }
            rows.append(row)
            per_wheel[wheel] = (v, v_s, err_s, duty)
        figs[kind].append((name, run, sign, t_mid, t_stop, t0, v_target, accel, per_wheel))

    print_tables(rows)
    with open(PLOTS / f"closed_loop{tag}.csv", "w", newline="", encoding="utf-8") as f:
        keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for kind, runs in figs.items():
        plot(kind, runs, model, tag)
    print(f"\nPlots and CSV in {PLOTS}")


def print_tables(rows: list[dict]) -> None:
    print("## Ramp (mm/s; error = reference - measured, sign removed; s = 100 ms smoothing)\n")
    print("| v | wheel | max err | rms err | max err s, ramp-up | mean err, ramp-up | max err s, hold | mean err, hold | max err s, stop | max duty |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r["kind"] == "ramp":
            print(
                f"| {r['v_mm_s']} | {r['wheel']} | {r['err_max']:.1f} | {r['err_rms']:.1f} | {r['err_s_max_up']:.1f} "
                f"| {r['err_mean_up']:.1f} | {r['err_s_max_hold']:.1f} | {r['err_mean_hold']:.1f} | {r['err_s_max_stop']:.1f} | {r['duty_max']:.3f} |"
            )
    print("\n## Step (smoothed speed)\n")
    print("| v | wheel | overshoot | settling ±5 % (ms) | settling ±10 % (ms) | speed before the stop (mm/s) | max duty |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        if r["kind"] == "step":
            print(
                f"| {r['v_mm_s']} | {r['wheel']} | {r['overshoot'] * 100:.0f} % | {r['settle_5_s'] * 1000:.0f} | {r['settle_10_s'] * 1000:.0f} "
                f"| {r['v_end_mm_s']:.1f} | {r['duty_max']:.3f} |"
            )


def plot(kind: str, runs: list, model: dict, tag: str = "") -> None:
    if not runs:
        return
    fig, axes = plt.subplots(len(runs), 3, figsize=(13, 3.6 * len(runs)), squeeze=False)
    for row, (name, run, sign, t_mid, t_stop, t0, v_target, accel, per_wheel) in enumerate(runs):
        ax_v, ax_e, ax_u = axes[row]
        way = "forward" if sign > 0 else "backward"
        for ax, title in ((ax_v, "speed (100 ms smoothing)"), (ax_e, "tracking error (100 ms smoothing)"), (ax_u, "duty")):
            style(ax)
            ax.set_title(f"{kind} {way}: {title}", color=INK, fontsize=10)
        ax_v.step(run.t, run.v_ref * MM_PER_COUNT / 1000, where="pre", color=INK, linestyle="--", linewidth=1, label="reference")
        for wheel, (v, v_s, err_s, duty) in per_wheel.items():
            c = WHEEL_COLORS[wheel]
            label = "left" if wheel == "L" else "right"
            ax_v.plot(t_mid, v_s * MM_PER_COUNT / 1000, color=c, linewidth=1.5, label=label)
            ax_e.plot(t_mid, err_s, color=c, linewidth=1.5, label=label)
            ax_u.step(run.t, duty, where="pre", color=c, linewidth=1.5, label=label)
            # Simulated design model, until the stop starts.
            m = model[(wheel, sign)]
            prof = ramp_profile(accel / 1000, abs(v_target) * MM_PER_COUNT / 1000) if accel else step_profile(abs(v_target) * MM_PER_COUNT / 1000, 0.0)
            sim = simulate(m, m, T_CL, prof, float(t_stop), U_MAX)
            ax_v.plot(sim.t, sign * sim.v_true * MM_PER_COUNT / 1000, color=c, linewidth=0.8, linestyle=":")
        ax_v.plot([], [], color=SIM_COLOR, linewidth=0.8, linestyle=":", label="simulated (design model)")
        for ax in (ax_v, ax_e, ax_u):
            ax.axvline(t_stop, color=MUTED, linewidth=0.8, linestyle="-.")
            ax.set_xlabel("time (s)")
        ax_v.set_ylabel("m/s")
        ax_e.set_ylabel("mm/s (+ = slower than reference)")
        ax_e.axhline(0, color=MUTED, linewidth=0.8)
        ax_u.axhline(sign * U_MAX, color=MUTED, linewidth=0.8, linestyle=":")
        ax_v.legend(loc="best", fontsize=8, frameon=False)
    fig.suptitle(f"Closed-loop {kind} tests on the arena floor (dash-dot line: ramped stop starts)", color=INK)
    fig.tight_layout()
    fig.savefig(PLOTS / f"day1_closed_loop{tag}_{kind}.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
