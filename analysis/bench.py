"""Day 2 bench (PC only): real pose from tape measurements, run errors and UMBmark.

Real pose (docs/ROADMAP.md, Day 2, Bench): two points on the robot's
centreline are measured from a tape cross on the floor, a line parallel to the arena x axis and
its perpendicular, with the robot facing about +x. The rear point is the floor reference point
(40.75 mm behind the axle, the point A_ref and B_ref are given for): its distance from the
perpendicular along the line (dx) and from the line (dy). The front point, a known distance
ahead of it on the centreline, is measured only from the line (dy_front): the two distances
from the line give the heading.

Errors follow Borenstein and Feng, "Measurement and Correction of Systematic Odometry Errors in
Mobile Robots", IEEE Trans. Robotics and Automation 12(6), 869–880, 1996, doi 10.1109/70.544770
(equation numbers from the authors' preprint, whose header says No 5): ε = absolute − odometry
(Eq. 3.1), both taken as displacements in the frame of
the run's start (x along the start heading, y to its left), since the odometry does not start
at the arena pose. UMBmark: centers of gravity (3.2), r_c.g. (3.3), E_max,syst (3.4), β (4.20),
R (4.21), Ed (4.22), α (4.24), Eb (4.27), correction factors c_L, c_R (4.31, 4.32). Their
square starts facing +x, the CCW run turns left and the CW run right (Fig. 7), as ours.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

REF_TO_AXLE_M = 0.04075  # floor reference point (A_ref, B_ref) to the axle


@dataclass(frozen=True)
class Pose:
    x: float  # m, axle midpoint
    y: float  # m
    theta: float  # rad


def wrap(angle: float) -> float:
    """Wraps to (−π, π]."""
    a = math.fmod(angle, 2 * math.pi)
    if a <= -math.pi:
        a += 2 * math.pi
    elif a > math.pi:
        a -= 2 * math.pi
    return a


def pose_from_tapes(cross: tuple[float, float], dx: float, dy: float, dy_front: float, rear_to_front: float) -> Pose:
    """Axle pose from the reference point and the front point measured from a tape cross (m).

    cross: arena position of the tape cross; dx: reference point from the perpendicular, along
    the line, + towards +x; dy: reference point from the line, + towards +y (the robot's left);
    dy_front: front point from the line, same sign; rear_to_front: horizontal distance between
    the two points.
    """
    rise = dy_front - dy
    if abs(rise) >= rear_to_front:
        raise ValueError(f"front and rear points {rise} m apart across the line, more than {rear_to_front} m between them")
    return pose_from_reference(cross[0] + dx, cross[1] + dy, math.asin(rise / rear_to_front))


def pose_from_reference(x: float, y: float, theta: float) -> Pose:
    """Axle pose of the robot whose floor reference point is at (x, y)."""
    return Pose(x + REF_TO_AXLE_M * math.cos(theta), y + REF_TO_AXLE_M * math.sin(theta), theta)


def displacement(start: Pose, end: Pose) -> tuple[float, float, float]:
    """End relative to start, in the start frame: (along, left, heading change not wrapped)."""
    dx, dy = end.x - start.x, end.y - start.y
    c, s = math.cos(start.theta), math.sin(start.theta)
    return (c * dx + s * dy, -s * dx + c * dy, end.theta - start.theta)


@dataclass(frozen=True)
class RunError:
    real: tuple[float, float, float]  # real displacement in the start frame (m, m, rad wrapped)
    odometry: tuple[float, float, float]  # odometry displacement in its own start frame
    ex: float  # ε along the start heading, real − odometry (m)
    ey: float  # ε to the left
    etheta: float  # rad, wrapped


def run_error(real_start: Pose, real_end: Pose, odo_start: Pose, odo_end: Pose) -> RunError:
    real = displacement(real_start, real_end)
    odo = displacement(odo_start, odo_end)
    return RunError(
        real=(real[0], real[1], wrap(real[2])),
        odometry=odo,
        ex=real[0] - odo[0],
        ey=real[1] - odo[1],
        etheta=wrap(real[2] - odo[2]),
    )


@dataclass(frozen=True)
class Umbmark:
    side: float  # L (m)
    track: float  # b used by the odometry during the runs (m)
    cg_cw: tuple[float, float]  # centers of gravity (m), Eq. 3.2
    cg_ccw: tuple[float, float]
    r_cw: float  # Eq. 3.3
    r_ccw: float
    e_max_syst: float  # Eq. 3.4
    alpha_x: float  # rad, Eq. 4.24a
    alpha_y: float  # rad, Eq. 4.24b
    beta_x: float  # rad, Eq. 4.20a
    beta_y: float  # rad, Eq. 4.20b
    alpha: float  # mean of the x and y estimates (the paper's footnote 2)
    beta: float
    radius: float  # R (m), Eq. 4.21; inf when β = 0
    ed: float  # D_R / D_L, Eq. 4.22
    eb: float  # b_actual / b_nominal, Eq. 4.27
    c_left: float  # Eq. 4.31
    c_right: float  # Eq. 4.32


def centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def umbmark(cw: Sequence[tuple[float, float]], ccw: Sequence[tuple[float, float]], side: float, track: float) -> Umbmark:
    """cw, ccw: (εx, εy) of each run (m); side: L (m); track: b used by the odometry (m)."""
    (xcw, ycw), (xccw, yccw) = centroid(cw), centroid(ccw)
    r_cw, r_ccw = math.hypot(xcw, ycw), math.hypot(xccw, yccw)
    beta_x = (xcw - xccw) / (-4 * side)
    beta_y = (ycw + yccw) / (-4 * side)
    alpha_x = (xcw + xccw) / (-4 * side)
    alpha_y = (ycw - yccw) / (-4 * side)
    alpha, beta = (alpha_x + alpha_y) / 2, (beta_x + beta_y) / 2
    if beta == 0.0:
        radius, ed = math.inf, 1.0
    else:
        radius = (side / 2) / math.sin(beta / 2)
        ed = (radius + track / 2) / (radius - track / 2)
    eb = (math.pi / 2) / (math.pi / 2 - alpha)
    return Umbmark(
        side=side,
        track=track,
        cg_cw=(xcw, ycw),
        cg_ccw=(xccw, yccw),
        r_cw=r_cw,
        r_ccw=r_ccw,
        e_max_syst=max(r_cw, r_ccw),
        alpha_x=alpha_x,
        alpha_y=alpha_y,
        beta_x=beta_x,
        beta_y=beta_y,
        alpha=alpha,
        beta=beta,
        radius=radius,
        ed=ed,
        eb=eb,
        c_left=2 / (ed + 1),
        c_right=2 / (1 / ed + 1),
    )
