"""Day 1 analysis: wheel model (K, tau, pwm0) per wheel and direction (PC only).

Reads one app session of `step` and `ramp` recordings from data/day1/ (the sample files
are listed in that session's events log), prints the tables for the work log, and writes
data/day1/plots/identification_{steps,model}.csv and the plots.

    uv run python analysis/day1_identify.py [events_csv]
"""

import csv
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from wheel_model import (
    fit_first_order,
    gain_with_offset,
    load_ramp,
    load_step,
    ramp_line,
    ramp_start,
    rise_times,
    session_sample_files,
    steady_line,
    windowed_speed,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "day1"
PLOTS = DATA / "plots"
# Floor identification session of 2026-10-11, 12.6 V (docs/logs/day1-firmware.md, section 9).
SESSION = DATA / "20261011-195756_app_events.csv"

MM_PER_COUNT = 67.5 * np.pi / 1319.75  # nominal wheel, config::kCountsPerRev
START_RUN = 5  # sustained motion: 5 consecutive 20 ms intervals with at least one count
START_RUN_CHECK = 10  # sensitivity of the start criterion
RAMP_MIN_SPEED = 200.0  # counts/s, lower end of the ramp line fit (clear of the start)

WHEELS = (("L", "counts_l"), ("R", "counts_r"))
DIRS = ((1, "fwd"), (-1, "bwd"))
# Reference palette (dataviz skill), categorical slots 1-3, one per amplitude.
AMP_COLORS = {200: "#2a78d6", 250: "#eb6834", 300: "#1baf7a"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def style(ax: Axes) -> None:
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK)


def main() -> None:
    events = Path(sys.argv[1]) if len(sys.argv) > 1 else SESSION
    files = session_sample_files(events)
    PLOTS.mkdir(exist_ok=True)

    # --- Steps: first-order fit per wheel ---------------------------------------
    steps = []  # dicts, one per (step, wheel)
    runs = {}
    for name in files:
        m = re.search(r"_step_(\d+)_L(-?\d+)_R(-?\d+)\.csv$", name)
        if not m:
            continue
        run = load_step(DATA / name)
        duty = int(m.group(2))
        sign = 1 if duty > 0 else -1
        runs[(sign, abs(duty))] = run
        for wheel, attr in WHEELS:
            x = getattr(run, attr) * sign
            fit = fit_first_order(run.t, x)
            v_end, (t50, t63, t90) = rise_times(run.t, x, (0.5, 0.632, 0.9))
            steps.append(
                {
                    "file": name, "wheel": wheel, "dir": sign, "duty": abs(duty) / 1000,
                    "v_ss": fit.v_ss, "tau": fit.tau, "rms": fit.rms,
                    "v_end": v_end, "t50": t50, "t63": t63, "t90": t90,
                }
            )  # fmt: skip

    print("## Steps (first-order fit on counts; v in counts/s, times in ms)\n")
    print("| wheel | dir | duty | v_ss | tau | rms (counts) | v 0.7-1 s | t50 | t63 | t90 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in sorted(steps, key=lambda s: (s["wheel"], -s["dir"], s["duty"])):
        print(
            f"| {s['wheel']} | {s['dir']:+d} | {s['duty']:.2f} | {s['v_ss']:.0f} | {s['tau'] * 1e3:.0f} "
            f"| {s['rms']:.1f} | {s['v_end']:.0f} | {s['t50'] * 1e3:.0f} | {s['t63'] * 1e3:.0f} "
            f"| {s['t90'] * 1e3:.0f} |"
        )
    with open(PLOTS / "identification_steps.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(steps[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(steps)

    # --- Ramps: start of sustained motion and the moving-part line ---------------
    ramps = {}
    for name in files:
        m = re.search(r"_ramp_(\d+)_dir([+-]1)_rate(\d+)\.csv$", name)
        if m:
            ramps[int(m.group(2))] = load_ramp(DATA / name)

    model = []
    for wheel, attr in WHEELS:
        for sign, dname in DIRS:
            ss = [s for s in steps if s["wheel"] == wheel and s["dir"] == sign]
            u = np.array([s["duty"] for s in ss])
            v = np.array([s["v_ss"] for s in ss])
            taus = np.array([s["tau"] for s in ss])
            k_line, u0_line = steady_line(u, v)
            ramp = ramps[sign]
            duty = ramp.duty * sign
            counts = getattr(ramp, attr) * sign
            i5 = ramp_start(duty, counts, START_RUN)
            i10 = ramp_start(duty, counts, START_RUN_CHECK)
            k_ramp, u0_ramp, n_ramp = ramp_line(
                ramp.t, duty, counts, float(taus.mean()), RAMP_MIN_SPEED
            )
            pwm0 = float(duty[i5])
            model.append(
                {
                    "wheel": wheel, "dir": sign,
                    "tau_mean": taus.mean(), "tau_min": taus.min(), "tau_max": taus.max(),
                    "k_line": k_line, "u0_line": u0_line,
                    "start5": pwm0, "start10": float(duty[i10]), "t_start5": float(ramp.t[i5]),
                    "k_ramp": k_ramp, "u0_ramp": u0_ramp, "n_ramp": n_ramp,
                    "k_at_start5": gain_with_offset(u, v, pwm0),
                }
            )  # fmt: skip

    print("\n## Per wheel and direction (K in counts/s per unit duty, duties in %)\n")
    print(
        "| wheel | dir | tau mean (min-max) ms | step line K | step line u0 | ramp start N=5 "
        "| N=10 | ramp line K | ramp line u0 | K with u0 = start N=5 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in model:
        print(
            f"| {r['wheel']} | {r['dir']:+d} | {r['tau_mean'] * 1e3:.0f} ({r['tau_min'] * 1e3:.0f}-"
            f"{r['tau_max'] * 1e3:.0f}) | {r['k_line']:.0f} | {r['u0_line'] * 100:.2f} "
            f"| {r['start5'] * 100:.1f} | {r['start10'] * 100:.1f} | {r['k_ramp']:.0f} "
            f"| {r['u0_ramp'] * 100:.2f} | {r['k_at_start5']:.0f} |"
        )
    with open(PLOTS / "identification_model.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(model[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(model)

    plot_step_fits(runs, steps)
    plot_slip_check(steps)
    plot_speed_vs_duty(steps, ramps, model)
    print(f"\nPlots and CSVs in {PLOTS}")


def panels(title: str) -> tuple[Figure, dict]:
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True)
    grid = {}
    for row, (wheel, _) in enumerate(WHEELS):
        for col, (sign, _) in enumerate(DIRS):
            ax = axes[row][col]
            style(ax)
            side = "left" if wheel == "L" else "right"
            way = "forward" if sign > 0 else "backward"
            ax.set_title(f"{side} wheel, {way}", color=INK, fontsize=10)
            grid[(wheel, sign)] = ax
    fig.suptitle(title, color=INK)
    return fig, grid


def plot_step_fits(runs: dict, steps: list[dict]) -> None:
    """Measured speed (20 ms window) and the fitted first-order speed, per amplitude."""
    fig, grid = panels("Steps on the arena floor: measured speed and first-order fit")
    for s in steps:
        run = runs[(s["dir"], round(s["duty"] * 1000))]
        x = getattr(run, "counts_l" if s["wheel"] == "L" else "counts_r") * s["dir"]
        tc, v = windowed_speed(run.t, x, 5)
        ax = grid[(s["wheel"], s["dir"])]
        color = AMP_COLORS[round(s["duty"] * 1000)]
        label = f"{s['duty'] * 100:.0f} %, τ = {s['tau'] * 1e3:.0f} ms"
        ax.plot(tc, v, color=color, linewidth=1.2, label=label)
        vm = s["v_ss"] * (1 - np.exp(-run.t / s["tau"]))
        ax.plot(run.t, vm, color=INK, linewidth=1, linestyle="--")
    for (wheel, sign), ax in grid.items():
        if wheel == "R":
            ax.set_xlabel("time since the step (s)")
        if sign > 0:
            ax.set_ylabel("speed (counts/s)")
    for ax in grid.values():
        ax.plot([], [], color=INK, linewidth=1, linestyle="--", label="first-order fit")
        ax.legend(loc="lower right", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(PLOTS / "day1_step_fits.png", dpi=150)
    plt.close(fig)


def plot_slip_check(steps: list[dict]) -> None:
    """Fitted tau and model-free t63 against the step amplitude (slip consistency check)."""
    fig, grid = panels("Slip check: time constant against step amplitude")
    for (wheel, sign), ax in grid.items():
        ss = sorted((s for s in steps if s["wheel"] == wheel and s["dir"] == sign), key=lambda s: s["duty"])
        d = [s["duty"] * 100 for s in ss]
        ax.plot(d, [s["tau"] * 1e3 for s in ss], color=AMP_COLORS[200], marker="o", markersize=7, linewidth=2, label="fitted τ")
        ax.plot(d, [s["t63"] * 1e3 for s in ss], color=AMP_COLORS[250], marker="s", markersize=7, linewidth=2, label="t63 (model-free)")
        for s in ss:
            ax.annotate(f"{s['tau'] * 1e3:.0f}", (s["duty"] * 100, s["tau"] * 1e3), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8, color=INK)
        ax.set_xticks([20, 25, 30])
        ax.set_ylim(0, 200)
        if wheel == "R":
            ax.set_xlabel("step duty (%)")
        if sign > 0:
            ax.set_ylabel("ms")
    grid[("L", 1)].legend(loc="lower left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(PLOTS / "day1_slip_check.png", dpi=150)
    plt.close(fig)


def plot_speed_vs_duty(steps: list[dict], ramps: dict, model: list[dict]) -> None:
    """Steady speeds of the steps, the slow ramp's speed and the start of sustained motion."""
    fig, grid = panels("Speed against duty: steps (steady state) and slow ramp")
    for r in model:
        ax = grid[(r["wheel"], r["dir"])]
        ramp = ramps[r["dir"]]
        counts = getattr(ramp, "counts_l" if r["wheel"] == "L" else "counts_r") * r["dir"]
        duty = ramp.duty * r["dir"]
        _, v = windowed_speed(ramp.t, counts, 2)
        u = np.array([duty[j + 1 : j + 5].mean() for j in range(len(v))])
        ax.plot(u * 100, v, color=AMP_COLORS[250], linewidth=1.2, label="ramp, 5 %/s (80 ms window)")
        ss = [s for s in steps if s["wheel"] == r["wheel"] and s["dir"] == r["dir"]]
        ax.plot([s["duty"] * 100 for s in ss], [s["v_ss"] for s in ss], "o", color=AMP_COLORS[200], markersize=8, label="step steady speed (fit)")
        uu = np.linspace(0, 0.32, 50)
        ax.plot(uu * 100, np.clip(r["k_line"] * (uu - r["u0_line"]), 0, None), color=AMP_COLORS[200], linewidth=1, linestyle="--", label="line through the steps")
        ax.axvline(r["start5"] * 100, color=MUTED, linewidth=1, linestyle=":")
        ax.annotate(f"start {r['start5'] * 100:.1f} %", (r["start5"] * 100, 1000), xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK)
        if r["wheel"] == "R":
            ax.set_xlabel("duty (%)")
        if r["dir"] > 0:
            ax.set_ylabel("speed (counts/s)")
    grid[("L", 1)].legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(PLOTS / "day1_speed_vs_duty.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
