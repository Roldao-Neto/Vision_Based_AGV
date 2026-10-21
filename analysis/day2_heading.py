"""Day 2: gains of the heading PI used to drive straight (PC only).

The heading plant is θ' = ω behind the two wheel speed loops, which the Day 1 design makes
first-order with Tcl = 0.1 s. A PI on the heading error, ω = Kp·e + Kp/Ti·∫e, then has its
crossover near Kp: Kp ≈ 2.3 s⁻¹ and Ti ≈ 1 s give a crossover near 2.5 rad/s, four times below
the wheel loops, with ~55° of phase margin.

The PI holds the heading the odometry computes, so it only corrects turns the encoders see:
the two wheels not following the same reference. A wheel larger than its m/count says, or a
heading error before the start, are invisible to it; those are what the calibration (UMBmark)
fixes. The simulation therefore uses encoder-visible disturbances.

Wheel model: the wheel PI's feedforward (pwm0 + (v + τ·a_ref)/K) makes each wheel follow the
profile's ramp almost exactly (on Day 1 both wheels ended 1 m runs within 2–6 counts), so the
profile goes straight through, and only the steering correction and the disturbances pass
through the 0.1 s closed wheel loop. Disturbances: a 1 % feedforward error of opposite sign on
each wheel while the profile accelerates or brakes, a 0.3 s drop of 40 mm/s on the left wheel
early in the run (like the left wheel in the first cleanup check, docs/logs/day2-firmware.md,
item 0) and a constant 2 mm/s tracking offset on the right wheel (the integral must remove it).

It drives a 1.38 m straight (the A→B line) at 0.25 m/s with the firmware's profile, computes
the heading from integer encoder counts like the firmware, and prints, per gain pair, the
lateral offset at the end, the largest heading error after the disturbance and the largest
steering ω. Writes results/day2/plots/heading_gains.csv and day2_heading_sim.png.

    uv run python analysis/day2_heading.py
"""

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PLOTS = Path(__file__).resolve().parent.parent / "results" / "day2" / "plots"

DT = 0.02
T_CL = 0.1  # s, closed wheel loops (Day 1 design)
FF_ERROR = 0.01  # feedforward error during the ramps, +1 % left, −1 % right
TRACK = 0.217
M_PER_COUNT = math.pi * 0.0675 / 1319.75
V_MAX, ACCEL, BAND = 0.25, 0.5, 0.015
W_MAX = 0.5  # rad/s, steering limit
DISTANCE = 1.38
DROP = (0.2, 0.5, 0.040)  # s, s, m/s: the left wheel loses 40 mm/s between 0.2 and 0.5 s
OFFSET_R = 0.002  # m/s, constant tracking offset of the right wheel


def profile(prev: float, remaining: float) -> float:
    """The firmware's motion_profile::next, speed only."""
    if remaining < BAND:
        return max(0.0, prev - ACCEL * DT)
    return min(V_MAX, prev + ACCEL * DT, math.sqrt(2 * ACCEL * remaining))


def simulate(kp: float, ti: float) -> dict[str, list[float]]:
    x = y = th = 0.0  # pose with the wheels exactly as the encoders measure them
    vl = vr = 0.0  # wheel speeds
    dl = dr = 0.0  # wheel speed minus the profile: steering and disturbances through the loop
    pos_l = pos_r = 0.0  # wheel travel (m)
    th_odo = 0.0
    last_cl = last_cr = 0
    integ = 0.0
    v_ref = 0.0
    out: dict[str, list[float]] = {"t": [], "e": [], "y": [], "w": [], "v": []}
    for k in range(2000):
        # Odometry from integer counts, as in the firmware.
        cl, cr = math.floor(pos_l / M_PER_COUNT), math.floor(pos_r / M_PER_COUNT)
        th_odo += ((cr - last_cr) - (cl - last_cl)) * M_PER_COUNT / TRACK
        last_cl, last_cr = cl, cr
        traveled = 0.5 * (cl + cr) * M_PER_COUNT
        v_prev = v_ref
        v_ref = profile(v_ref, DISTANCE - traveled)
        ramping = v_ref != v_prev
        e = 0.0 - th_odo
        steering = DISTANCE - traveled >= BAND
        w = 0.0
        if steering:
            w_raw = kp * e + integ
            w = max(-W_MAX, min(W_MAX, w_raw))
            if w == w_raw or math.copysign(1, e) != math.copysign(1, w_raw):
                integ += kp / ti * e * DT
        ref_l, ref_r = v_ref - w * TRACK / 2, v_ref + w * TRACK / 2
        # The profile passes through the feedforward (with its ramp error); the steering and the
        # disturbances pass through the closed wheel loop.
        t = k * DT
        drop = DROP[2] if DROP[0] <= t < DROP[1] and v_ref > 0 else 0.0
        offset = OFFSET_R if v_ref > 0 else 0.0
        ff = FF_ERROR * v_ref if ramping else 0.0
        dl += ((ref_l - v_ref) - drop - dl) * DT / T_CL
        dr += ((ref_r - v_ref) + offset - dr) * DT / T_CL
        vl, vr = v_ref + ff + dl, v_ref - ff + dr
        pos_l += vl * DT
        pos_r += vr * DT
        d = 0.5 * (vl + vr) * DT
        dth = (vr - vl) * DT / TRACK
        x += d * math.cos(th + dth / 2)
        y += d * math.sin(th + dth / 2)
        th += dth
        out["t"].append(k * DT)
        out["e"].append(th)
        out["y"].append(y)
        out["w"].append(w)
        out["v"].append(v_ref)
        if k > 10 and v_ref == 0.0 and abs(vl) + abs(vr) < 1e-4:
            break
    return out


def main() -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    pairs = [(kp, ti) for kp in (1.5, 2.3, 3.5) for ti in (0.5, 1.0, 2.0)]
    rows = []
    print("| Kp (1/s) | Ti (s) | lateral at the end (mm) | max |heading| after 1.5 s (mrad) | max |ω| (rad/s) |")
    print("|---|---|---|---|---|")
    for kp, ti in pairs:
        r = simulate(kp, ti)
        after = [abs(e) for t, e in zip(r["t"], r["e"]) if t >= 1.5]
        row = {
            "kp": kp,
            "ti": ti,
            "lateral_end_mm": 1000 * r["y"][-1],
            "heading_max_after_1_5s_mrad": 1000 * max(after),
            "w_max": max(abs(w) for w in r["w"]),
        }
        rows.append(row)
        print(f"| {kp} | {ti} | {row['lateral_end_mm']:.1f} | {row['heading_max_after_1_5s_mrad']:.1f} | {row['w_max']:.3f} |")
    with open(PLOTS / "heading_gains.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for kp, ti in [(0.0, 1.0), (1.5, 1.0), (2.3, 1.0), (3.5, 1.0), (2.3, 0.5), (2.3, 2.0)]:
        r = simulate(kp, ti)
        label = "no heading loop" if kp == 0 else f"Kp {kp}, Ti {ti}"
        axes[0].plot(r["t"], [1000 * e for e in r["e"]], label=label)
        axes[1].plot(r["t"], [1000 * y for y in r["y"]], label=label)
        axes[2].plot(r["t"], r["w"], label=label)
    axes[0].set_title("heading (mrad); target 0")
    axes[1].set_title("lateral offset (mm)")
    axes[2].set_title("steering ω (rad/s)")
    for ax in axes:
        ax.set_xlabel("time (s)")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Heading PI, 1.38 m at 0.25 m/s: ±1 % feedforward error on the ramps, left wheel −40 mm/s "
        "for 0.3 s, right wheel +2 mm/s"
    )
    fig.tight_layout()
    fig.savefig(PLOTS / "day2_heading_sim.png", dpi=110)
    print(f"Plots and CSV in {PLOTS}")


if __name__ == "__main__":
    main()
