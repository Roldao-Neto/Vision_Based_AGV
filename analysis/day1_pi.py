"""Day 1 analysis: PI gains per wheel and direction, checked in simulation (PC only).

Reads data/day1/plots/identification_model.csv (written by day1_identify.py), applies the
design decided on 2026-10-11 (docs/logs/day1-analysis.md, section 5) and simulates the two
closed-loop tests of the ROADMAP with the controller's model and with the extreme measured
time constants as the plant.

    uv run python analysis/day1_pi.py
"""

import csv

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from day1_identify import AMP_COLORS, INK, MUTED, PLOTS, style
from speed_loop import (
    MM_PER_COUNT,
    WheelModel,
    pi_gains,
    ramp_profile,
    simulate,
    step_metrics,
    step_profile,
)

T_CL = 0.1  # s, closed-loop time constant (5 ticks)
U_MAX = 0.5  # closed-loop duty cap
RAMP = (0.5, 0.25)  # m/s², m/s: the operating profile
STEP_V, STEP_T0 = 0.1, 0.1  # m/s, s

NAMES = {("L", 1): "left fwd", ("L", -1): "left bwd", ("R", 1): "right fwd", ("R", -1): "right bwd"}
COLORS = {("L", 1): AMP_COLORS[200], ("L", -1): AMP_COLORS[250], ("R", 1): AMP_COLORS[300], ("R", -1): "#eda100"}


def main() -> None:
    with open(PLOTS / "identification_model.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"## PI gains (Tcl = {T_CL} s, duty cap {U_MAX})\n")
    print("| wheel | dir | K | tau (ms) | pwm0 (%) | Kp (duty per count/s) | Ki (duty per count) |")
    print("|---|---|---|---|---|---|---|")
    gains = []
    for r in rows:
        key = (r["wheel"], int(r["dir"]))
        model = WheelModel(float(r["k_at_start5"]), float(r["tau_mean"]), float(r["start5"]))
        g = pi_gains(model, T_CL)
        gains.append((key, model, float(r["tau_min"]), float(r["tau_max"])))
        print(
            f"| {key[0]} | {key[1]:+d} | {model.k:.0f} | {model.tau * 1e3:.0f} | {model.pwm0 * 100:.1f} "
            f"| {g.kp:.3e} | {g.ki:.3e} |"
        )
    with open(PLOTS / "pi_gains.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["wheel", "dir", "k", "tau", "pwm0", "kp", "ki", "t_cl", "u_max"])
        for (wheel, sign), m, _, _ in gains:
            g = pi_gains(m, T_CL)
            w.writerow([wheel, sign, m.k, m.tau, m.pwm0, g.kp, g.ki, T_CL, U_MAX])

    print("\n## Simulated closed-loop tests (true speed; plant tau = design, min, max measured)\n")
    print("| wheel | dir | plant tau (ms) | ramp: max error (mm/s) | ramp: max error after 0.1 s | ramp: max speed (m/s) | ramp: max duty | step: overshoot | step: settling 2 % (ms) | step: max duty |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    v_step = STEP_V * 1000 / MM_PER_COUNT
    nominal = {}
    for key, m, tmin, tmax in gains:
        for tau in (m.tau, tmin, tmax):
            plant = WheelModel(m.k, tau, m.pwm0)
            ramp = simulate(plant, m, T_CL, ramp_profile(*RAMP), 1.5, U_MAX)
            err = (ramp.v_ref - ramp.v_true) * MM_PER_COUNT
            step = simulate(plant, m, T_CL, step_profile(STEP_V, STEP_T0), 1.5, U_MAX)
            ov, ts = step_metrics(step, STEP_T0, v_step)
            if tau == m.tau:
                nominal[key] = (ramp, step)
            print(
                f"| {key[0]} | {key[1]:+d} | {tau * 1e3:.0f} | {np.abs(err).max():.1f} "
                f"| {np.abs(err[ramp.t > 0.1]).max():.1f} | {ramp.v_true.max() * MM_PER_COUNT / 1000:.3f} | {ramp.u.max():.2f} "
                f"| {ov * 100:.0f} % | {ts * 1e3:.0f} | {step.u.max():.2f} |"
            )

    plot(nominal)
    print(f"\nPlot and gains in {PLOTS}")


def plot(nominal: dict) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex="col")
    titles = (
        ("Ramp 0.5 m/s² to 0.25 m/s: speed", "speed (m/s)"),
        ("Step 0 → 0.1 m/s: speed", "speed (m/s)"),
        ("Ramp: tracking error (reference − true)", "error (mm/s)"),
        ("Step: duty", "duty"),
    )
    for ax, (title, ylabel) in zip(axes.flat, titles, strict=True):
        style(ax)
        ax.set_title(title, color=INK, fontsize=10)
        ax.set_ylabel(ylabel)
    for key, (ramp, step) in nominal.items():
        c = COLORS[key]
        axes[0][0].plot(ramp.t, ramp.v_true * MM_PER_COUNT / 1000, color=c, linewidth=1.5, label=NAMES[key])
        axes[1][0].plot(ramp.t, (ramp.v_ref - ramp.v_true) * MM_PER_COUNT, color=c, linewidth=1.5)
        axes[0][1].plot(step.t, step.v_true * MM_PER_COUNT / 1000, color=c, linewidth=1.5)
        axes[1][1].step(step.t, step.u, where="post", color=c, linewidth=1.5)
    ramp, step = next(iter(nominal.values()))
    axes[0][0].plot(ramp.t, ramp.v_ref * MM_PER_COUNT / 1000, color=INK, linestyle="--", linewidth=1, label="reference")
    axes[0][1].step(step.t, step.v_ref * MM_PER_COUNT / 1000, where="post", color=INK, linestyle="--", linewidth=1)
    axes[1][1].axhline(U_MAX, color=MUTED, linestyle=":", linewidth=1)
    axes[0][0].legend(loc="lower right", fontsize=8, frameon=False)
    for ax in axes[1]:
        ax.set_xlabel("time (s)")
    fig.suptitle(f"Simulated speed loop per wheel and direction (Tcl = {T_CL} s, design τ as plant)", color=INK)
    fig.tight_layout()
    fig.savefig(PLOTS / "day1_pi_sim.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
