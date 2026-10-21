"""Day 2: cross-check of the firmware odometry with the Python reference (PC only).

For every calibration run of one app session (straight, umbmark), takes the end report
from the events log (start and end poses in µm/µrad and the odometry constants the firmware
used) and the run's samples file (the absolute counts the firmware's odometry read at every
tick), integrates the counts from the start pose with analysis/odometry.py and compares the end
pose with the firmware's. They must agree within 0.1 mm and 0.1 mrad (the firmware also works in
double; the only differences are the rounding of the report to µm/µrad and of the constants to
pm/nm). Also plots the heading, the lateral offset from the start line and the path (in the
start frame) of each run.

    uv run python analysis/day2_odometry_check.py results/day2/<session>_app_events.csv
"""

import csv
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from odometry import Pose, integrate

TOL_M = 1e-4
TOL_RAD = 1e-4


def parse_detail(detail: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in detail.split() if "=" in item)


def session_runs(events: Path) -> list[tuple[str, dict[str, str], Path]]:
    """(mode, end report fields, samples file) of each calibration run with complete samples."""
    ends: dict[str, tuple[str, dict[str, str]]] = {}
    runs = []
    with open(events, newline="") as f:
        for row in csv.DictReader(f):
            fields = parse_detail(row["detail"])
            if row["event"].endswith("_end") and "x0_um" in fields:
                ends[fields["record_id"]] = (row["event"].removesuffix("_end"), fields)
            elif row["event"] == "run_samples" and fields.get("record_id") in ends:
                mode, end = ends[fields["record_id"]]
                runs.append((mode, end, events.parent / fields["file"]))
    return runs


def load_samples(path: Path) -> dict[str, list[int]]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return {k: [int(r[k]) for r in rows] for k in rows[0]}


def umbmark_phases(end: dict[str, str], s: dict[str, list[int]], poses: list[Pose]) -> list[dict[str, object]]:
    """Per phase of an umbmark run (leg·2 + turning): how each leg and turn ended against the
    targets the firmware aimed at (corners and headings fixed by the start pose)."""
    direction, side = int(end["p1"]), int(end["p2"]) * 1e-3
    pose0 = poses[0]
    corner = (pose0.x, pose0.y)
    rows = []
    for phase in sorted(set(s["phase"])):
        idx = [i for i, ph in enumerate(s["phase"]) if ph == phase]
        leg, turning = divmod(phase, 2)
        heading = pose0.theta + direction * leg * math.pi / 2
        last = poses[idx[-1]]
        row: dict[str, object] = {"phase": phase, "kind": "turn" if turning else "leg",
                                  "duration_s": (s["t_us"][idx[-1]] - s["t_us"][idx[0]]) * 1e-6}
        if turning:
            target = heading + direction * math.pi / 2
            beyond = [direction * (poses[i].theta - target) for i in idx]
            row["end_error_mrad"] = 1000 * direction * (last.theta - target)  # + = turned too far
            row["peak_beyond_mrad"] = 1000 * max(beyond)
        else:
            ux, uy = math.cos(heading), math.sin(heading)
            corner = (corner[0] + side * ux, corner[1] + side * uy)
            row["end_error_mm"] = 1000 * ((last.x - corner[0]) * ux + (last.y - corner[1]) * uy)  # + = past it
            row["max_lateral_mm"] = 1000 * max(abs(-(poses[i].x - corner[0]) * uy + (poses[i].y - corner[1]) * ux)
                                               for i in idx)
            row["max_heading_err_mrad"] = 1000 * max(abs(poses[i].theta - heading) for i in idx)
        rows.append(row)
    return rows


def main() -> None:
    events = Path(sys.argv[1])
    plots = events.parent / "plots"
    plots.mkdir(exist_ok=True)
    tag = events.name.split("_")[0]
    runs = session_runs(events)
    results = []
    print("| record | mode | params | reason | Δx (µm) | Δy (µm) | Δθ (µrad) | agrees |")
    print("|---|---|---|---|---|---|---|---|")
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for mode, end, path in runs:
        s = load_samples(path)
        mpc_l = int(end["m_per_count_l_pm"]) * 1e-12
        mpc_r = int(end["m_per_count_r_pm"]) * 1e-12
        track = int(end["track_nm"]) * 1e-9
        pose0 = Pose(int(end["x0_um"]) * 1e-6, int(end["y0_um"]) * 1e-6, int(end["th0_urad"]) * 1e-6)
        poses = integrate(s["counts_l"], s["counts_r"], mpc_l, mpc_r, track, pose0)
        last = poses[-1]
        dx = last.x - int(end["x_um"]) * 1e-6
        dy = last.y - int(end["y_um"]) * 1e-6
        dth = last.theta - int(end["th_urad"]) * 1e-6
        ok = abs(dx) <= TOL_M and abs(dy) <= TOL_M and abs(dth) <= TOL_RAD
        params = " ".join(end[k] for k in ("p1", "p2", "p3", "p4"))
        results.append({"record_id": end["record_id"], "mode": mode, "params": params, "reason": end["reason"],
                        "dx_um": 1e6 * dx, "dy_um": 1e6 * dy, "dtheta_urad": 1e6 * dth, "agrees": ok})
        print(f"| {end['record_id']} | {mode} | {params} | {end['reason']} | {1e6 * dx:.2f} | {1e6 * dy:.2f} | "
              f"{1e6 * dth:.2f} | {'yes' if ok else 'NO'} |")
        if mode == "umbmark":
            print(f"\n  umbmark #{end['record_id']} by phase (the run's own targets; + = past the corner or turned too far):")
            for row in umbmark_phases(end, s, poses):
                detail = " ".join(f"{k}={v:.1f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items())
                print(f"  {detail}")
            print()
        t = [us * 1e-6 for us in s["t_us"]]
        ux, uy = math.cos(pose0.theta), math.sin(pose0.theta)
        along = [(p.x - pose0.x) * ux + (p.y - pose0.y) * uy for p in poses]
        lateral = [-(p.x - pose0.x) * uy + (p.y - pose0.y) * ux for p in poses]
        label = f"#{end['record_id']} {mode} {params}"
        axes[0].plot(t, [1000 * (p.theta - pose0.theta) for p in poses], label=label)
        axes[1].plot(t, [1000 * v for v in lateral], label=label)
        axes[2].plot([1000 * v for v in along], [1000 * v for v in lateral], label=label)
    axes[0].set_title("heading change from the start (mrad), by the odometry")
    axes[1].set_title("lateral offset from the start line (mm), by the odometry")
    axes[2].set_title("path in the start frame (mm), by the odometry")
    axes[2].set_xlabel("along the start heading (mm)")
    axes[2].set_aspect("equal", adjustable="datalim")
    for ax in axes:
        ax.grid(alpha=0.3)
    for ax in axes[:2]:
        ax.set_xlabel("time (s)")
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(plots / f"day2_odometry_{tag}.png", dpi=110)
    if results:
        with open(plots / f"odometry_check_{tag}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0]))
            w.writeheader()
            w.writerows(results)
    print(f"{sum(r['agrees'] for r in results)} of {len(results)} runs agree; plots and CSV in {plots}")


if __name__ == "__main__":
    main()
