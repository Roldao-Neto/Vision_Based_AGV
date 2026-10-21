"""Real pose from tape measurements and the run error against the odometry (PC only).

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
at the arena pose. The UMBmark formulas used for the Day 2 calibration are in branch day2.
"""

import math
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
