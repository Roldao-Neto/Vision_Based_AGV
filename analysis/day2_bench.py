"""Day 2 bench: straight runs, Es, UMBmark, Ed and Eb (PC only).

Reads the tape values of each bench step, results/day2/bench_<step>.csv (s1, u1, s2, u2; any of
them may be missing), one row per run, all in mm:

    run,session,record_id,start_dx,start_dy,start_dyf,end_dx,end_dy,end_dyf,notes

- session: the app session the run belongs to (the time stamp of its *_app_events.csv);
  record_id: the run's record_id, from its straight_end / umbmark_end event.
- dx, dy: the robot's floor reference point from the tape cross, along the line (+ towards +x)
  and from the line (+ on the robot's left, i.e. +y); dyf: the front centreline point from the
  line (analysis/bench.py, pose_from_tapes). The straight runs start from the cross at A_ref,
  (137, 745) mm, and end at the cross at B_ref, (1540, 745) mm; a UMBmark run starts and ends
  at the cross of its start mark, (459, 250) mm CCW and (459, 1250) mm CW.
- start_* are optional: when blank, the reference point is on the cross with θ0 = 0.

results/day2/bench_setup.csv holds rear_to_front_mm, the horizontal distance between the two
measured points on the robot.

For each run, the odometry start and end poses and the constants it used come from the run's
end report in the events log. Errors are real − odometry, in the run's start frame (Borenstein
and Feng 1996, Eq. 3.1; analysis/bench.py). Prints the tables and the corrected constants, and
writes results/day2/plots/bench_<step>.csv, bench_straight.png and bench_umbmark.png.

    uv run python analysis/day2_bench.py results/day2
"""

import csv
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bench import (
    Pose,
    RunError,
    pose_from_tapes,
    run_error,
    umbmark,
)
from matplotlib.axes import Axes

STEPS = ("s1", "u1", "s2", "u2")
A_REF_MM = (137.0, 745.0)
B_REF_MM = (1540.0, 745.0)
UMBMARK_REF_START_MM = {1: (459.0, 250.0), -1: (459.0, 1250.0)}  # CCW, CW

# Palette slots 1-2 of the dataviz default (validated); marker fill is the second encoding.
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#2b2b29", "#6b6a64", "#e4e3de"


@dataclass(frozen=True)
class Run:
    step: str
    run: str
    mode: str
    params: tuple[int, int, int, int]
    reason: str
    error: RunError
    m_per_count: tuple[float, float]
    track: float
    start_taped: bool
    notes: str


def parse_detail(detail: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in detail.split() if "=" in item)


def end_reports(events: Path) -> dict[str, tuple[str, dict[str, str]]]:
    """record_id -> (mode, end report fields) of every calibration run in one session."""
    reports = {}
    with open(events, newline="") as f:
        for row in csv.DictReader(f):
            fields = parse_detail(row["detail"])
            if row["event"].endswith("_end") and "x0_um" in fields:
                reports[fields["record_id"]] = (row["event"].removesuffix("_end"), fields)
    return reports


def tapes(row: dict[str, str], prefix: str) -> tuple[float, float, float] | None:
    """(dx, dy, dyf) in m, or None when all three are blank."""
    values = [row.get(f"{prefix}_{k}", "").strip() for k in ("dx", "dy", "dyf")]
    if not any(values):
        return None
    if not all(values):
        raise ValueError(f"run {row['run']}: {prefix} measurements are incomplete")
    dx, dy, dyf = (float(v) * 1e-3 for v in values)
    return dx, dy, dyf


def rear_to_front(data: Path) -> float:
    with open(data / "bench_setup.csv", newline="") as f:
        return float(next(csv.DictReader(f))["rear_to_front_mm"]) * 1e-3


def load_step(data: Path, step: str) -> list[Run]:
    path = data / f"bench_{step}.csv"
    if not path.exists():
        return []
    length = rear_to_front(data)
    sessions: dict[str, dict[str, tuple[str, dict[str, str]]]] = {}
    runs = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            session = row["session"].strip()
            if session not in sessions:
                sessions[session] = end_reports(data / f"{session}_app_events.csv")
            mode, end = sessions[session][row["record_id"].strip()]
            params = (int(end["p1"]), int(end["p2"]), int(end["p3"]), int(end["p4"]))
            if mode == "straight":
                start_cross, end_cross = A_REF_MM, B_REF_MM
            else:
                start_cross = end_cross = UMBMARK_REF_START_MM[params[0]]
            start_tapes = tapes(row, "start")
            end_tapes = tapes(row, "end")
            if end_tapes is None:
                raise ValueError(f"{path.name} run {row['run']}: no end measurements")
            real_start = pose_from_tapes((start_cross[0] * 1e-3, start_cross[1] * 1e-3),
                                         *(start_tapes or (0.0, 0.0, 0.0)), length)
            real_end = pose_from_tapes((end_cross[0] * 1e-3, end_cross[1] * 1e-3), *end_tapes, length)
            odo_start = Pose(int(end["x0_um"]) * 1e-6, int(end["y0_um"]) * 1e-6, int(end["th0_urad"]) * 1e-6)
            odo_end = Pose(int(end["x_um"]) * 1e-6, int(end["y_um"]) * 1e-6, int(end["th_urad"]) * 1e-6)
            runs.append(
                Run(
                    step=step,
                    run=row["run"].strip(),
                    mode=mode,
                    params=params,
                    reason=end["reason"],
                    error=run_error(real_start, real_end, odo_start, odo_end),
                    m_per_count=(int(end["m_per_count_l_pm"]) * 1e-12, int(end["m_per_count_r_pm"]) * 1e-12),
                    track=int(end["track_nm"]) * 1e-9,
                    start_taped=start_tapes is not None,
                    notes=row.get("notes", "").strip(),
                )
            )
    return runs


def mean_std(values: list[float]) -> str:
    if len(values) < 2:
        return f"{values[0]:.1f}" if values else "-"
    return f"{statistics.mean(values):.1f} ± {statistics.stdev(values):.1f}"


def constants_of(runs: list[Run]) -> tuple[tuple[float, float], float]:
    """The odometry constants of a step's runs, which must all match (one config.h per step)."""
    used = {(r.m_per_count, r.track) for r in runs}
    if len(used) != 1:
        raise ValueError(f"step {runs[0].step}: runs used different odometry constants {used}")
    return used.pop()


def write_runs(plots: Path, step: str, runs: list[Run]) -> None:
    with open(plots / f"bench_{step}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "mode", "p1", "p2", "p3", "p4", "reason", "start_taped", "real_along_mm", "real_left_mm",
                    "real_dtheta_mrad", "odo_along_mm", "odo_left_mm", "odo_dtheta_mrad", "ex_mm", "ey_mm",
                    "etheta_mrad", "notes"])
        for r in runs:
            e = r.error
            w.writerow([r.run, r.mode, *r.params, r.reason, r.start_taped,
                        f"{1e3 * e.real[0]:.1f}", f"{1e3 * e.real[1]:.1f}", f"{1e3 * e.real[2]:.1f}",
                        f"{1e3 * e.odometry[0]:.1f}", f"{1e3 * e.odometry[1]:.1f}", f"{1e3 * e.odometry[2]:.1f}",
                        f"{1e3 * e.ex:.1f}", f"{1e3 * e.ey:.1f}", f"{1e3 * e.etheta:.1f}", r.notes])


def report_straight(step: str, runs: list[Run]) -> None:
    print(f"\n## {step.upper()}: straight\n")
    print("| run | reason | start | real distance (mm) | odometry (mm) | εx along (mm) | εy lateral (mm) | εθ (mrad) |")
    print("|---|---|---|---|---|---|---|---|")
    for r in runs:
        e = r.error
        print(f"| {r.run} | {r.reason} | {'taped' if r.start_taped else 'mark'} | {1e3 * math.hypot(*e.real[:2]):.1f} | "
              f"{1e3 * math.hypot(*e.odometry[:2]):.1f} | {1e3 * e.ex:.1f} | {1e3 * e.ey:.1f} | {1e3 * e.etheta:.1f} |")
    print(f"| mean ± sd | | | | | {mean_std([1e3 * r.error.ex for r in runs])} | "
          f"{mean_std([1e3 * r.error.ey for r in runs])} | {mean_std([1e3 * r.error.etheta for r in runs])} |")
    (m_l, m_r), track = constants_of(runs)
    real = statistics.mean(math.hypot(*r.error.real[:2]) for r in runs)
    odo = statistics.mean(math.hypot(*r.error.odometry[:2]) for r in runs)
    es = real / odo
    print(f"\nEs (mean real / mean odometry distance) = {es:.5f}; constants used: m/count L {1e3 * m_l:.6f} mm, "
          f"R {1e3 * m_r:.6f} mm, b {1e3 * track:.2f} mm")
    print(f"→ m/count × Es: L {1e3 * m_l * es:.6f} mm, R {1e3 * m_r * es:.6f} mm")


def report_umbmark(step: str, runs: list[Run]) -> None:
    print(f"\n## {step.upper()}: UMBmark\n")
    print("| run | direction | reason | start | εx (mm) | εy (mm) | εθ (mrad) |")
    print("|---|---|---|---|---|---|---|")
    clusters: dict[int, list[tuple[float, float]]] = {1: [], -1: []}
    for r in runs:
        e = r.error
        clusters[r.params[0]].append((e.ex, e.ey))
        print(f"| {r.run} | {'CCW' if r.params[0] > 0 else 'CW'} | {r.reason} | {'taped' if r.start_taped else 'mark'} | "
              f"{1e3 * e.ex:.1f} | {1e3 * e.ey:.1f} | {1e3 * e.etheta:.1f} |")
    if not clusters[1] or not clusters[-1]:
        print("\n(UMBmark needs both CW and CCW runs)")
        return
    sides = {r.params[1] for r in runs}
    if len(sides) != 1:
        raise ValueError(f"step {step}: runs with different sides {sides}")
    (m_l, m_r), track = constants_of(runs)
    u = umbmark(clusters[-1], clusters[1], sides.pop() * 1e-3, track)
    for name, points, cg, r_cg in (("CW", clusters[-1], u.cg_cw, u.r_cw), ("CCW", clusters[1], u.cg_ccw, u.r_ccw)):
        spread = math.sqrt(statistics.mean((p[0] - cg[0]) ** 2 + (p[1] - cg[1]) ** 2 for p in points))
        sem = spread / math.sqrt(len(points))
        print(f"\n{name}: c.g. ({1e3 * cg[0]:.1f}, {1e3 * cg[1]:.1f}) mm, r_c.g. {1e3 * r_cg:.1f} mm, "
              f"rms spread about it {1e3 * spread:.1f} mm, 3·SEM {3e3 * sem:.1f} mm ({len(points)} runs)")
    print(f"\nE_max,syst = {1e3 * u.e_max_syst:.1f} mm")
    print(f"α: x {math.degrees(u.alpha_x):.3f}°, y {math.degrees(u.alpha_y):.3f}°, mean {math.degrees(u.alpha):.3f}°")
    print(f"β: x {math.degrees(u.beta_x):.3f}°, y {math.degrees(u.beta_y):.3f}°, mean {math.degrees(u.beta):.3f}°")
    print(f"R = {u.radius:.1f} m, Ed = {u.ed:.5f}, Eb = {u.eb:.5f}, c_L = {u.c_left:.5f}, c_R = {u.c_right:.5f}")
    print(f"→ m/count L {1e3 * m_l * u.c_left:.6f} mm, R {1e3 * m_r * u.c_right:.6f} mm, "
          f"b {1e3 * track * u.eb:.2f} mm (used: {1e3 * m_l:.6f}, {1e3 * m_r:.6f}, {1e3 * track:.2f})")


def style(ax: Axes) -> None:
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.axvline(0, color=MUTED, linewidth=0.8)


def plot_straight(plots: Path, steps: dict[str, list[Run]]) -> None:
    present = [s for s in ("s1", "s2") if steps.get(s)]
    if not present:
        return
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for step, color, filled in (("s1", BLUE, False), ("s2", ORANGE, True)):
        runs = steps.get(step)
        if not runs:
            continue
        ax.scatter([1e3 * r.error.ex for r in runs], [1e3 * r.error.ey for r in runs], s=60, linewidths=2,
                   facecolors=color if filled else "none", edgecolors=color,
                   label=f"{step.upper()} ({'calibrated' if filled else 'nominal'})")
    style(ax)
    ax.set_xlabel("εx along the line, real − odometry (mm)", color=INK)
    ax.set_ylabel("εy lateral, left + (mm)", color=INK)
    ax.set_title("Straight runs A→B: end error", color=INK, loc="left", pad=28)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, borderaxespad=0.2)
    fig.tight_layout()
    fig.savefig(plots / "bench_straight.png", dpi=130)


def plot_umbmark(plots: Path, steps: dict[str, list[Run]]) -> None:
    present = [s for s in ("u1", "u2") if steps.get(s)]
    if not present:
        return
    fig, ax = plt.subplots(figsize=(6.5, 6))
    for step, filled in (("u1", False), ("u2", True)):
        runs = steps.get(step) or []
        for direction, color, name in ((-1, BLUE, "CW"), (1, ORANGE, "CCW")):
            pts = [(1e3 * r.error.ex, 1e3 * r.error.ey) for r in runs if r.params[0] == direction]
            if not pts:
                continue
            label = f"{step.upper()} {name} ({'after' if filled else 'before'})"
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=60, linewidths=2,
                       facecolors=color if filled else "none", edgecolors=color, label=label)
            cx, cy = statistics.mean(p[0] for p in pts), statistics.mean(p[1] for p in pts)
            ax.scatter([cx], [cy], marker="+", s=500, linewidths=1.5, color=color, zorder=3)
    style(ax)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("εx, real − odometry (mm)", color=INK)
    ax.set_ylabel("εy (mm)", color=INK)
    ax.scatter([], [], marker="+", s=120, linewidths=1.5, color=MUTED, label="center of gravity")
    ax.set_title("UMBmark return errors", color=INK, loc="left", pad=40)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, borderaxespad=0.2)
    fig.tight_layout()
    fig.savefig(plots / "bench_umbmark.png", dpi=130)


def main() -> None:
    data = Path(sys.argv[1])
    plots = data / "plots"
    plots.mkdir(exist_ok=True)
    steps = {step: load_step(data, step) for step in STEPS}
    for step, runs in steps.items():
        if not runs:
            continue
        not_target = [r.run for r in runs if r.reason != "target"]
        if not_target:
            print(f"WARNING {step}: runs {not_target} did not end by target")
        write_runs(plots, step, runs)
        if step.startswith("s"):
            report_straight(step, runs)
        else:
            report_umbmark(step, runs)
    plot_straight(plots, steps)
    plot_umbmark(plots, steps)
    print(f"\nPer-run CSVs and plots in {plots}")


if __name__ == "__main__":
    main()
