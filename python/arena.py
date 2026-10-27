"""Arena frame, the fixed start and goal, and the robot center <-> axle conversion (SI units).

Origin at the inner wall corner, x along the 2 m side, theta counter-clockwise. The STM32 and
every waypoint use the axle midpoint, 7 cm behind the robot center; centers appear only at the
edges: the start axle is A - 7 cm in x, and a path planned to the goal center gets its last
waypoint pulled back 7 cm along the last segment.
"""

import math

AXLE_TO_CENTER_M = 0.07

# Robot center at A and B (CLAUDE.md, Arena and goal), heading 0 at A (facing B)
A_CENTER = (0.248, 0.745)
B_CENTER = (1.651, 0.745)
START_HEADING = 0.0

Point = tuple[float, float]


def center_to_axle(x: float, y: float, theta: float) -> Point:
    return (x - AXLE_TO_CENTER_M * math.cos(theta), y - AXLE_TO_CENTER_M * math.sin(theta))


def axle_to_center(x: float, y: float, theta: float) -> Point:
    return (x + AXLE_TO_CENTER_M * math.cos(theta), y + AXLE_TO_CENTER_M * math.sin(theta))


START_AXLE = center_to_axle(*A_CENTER, START_HEADING)  # (0.178, 0.745)


def pull_back_goal(start: Point, waypoints: list[Point]) -> list[Point]:
    """Waypoints planned to the goal center; the last one moves 7 cm back along the last
    segment, so the robot stops facing along it with its center on the goal."""
    prev = waypoints[-2] if len(waypoints) > 1 else start
    gx, gy = waypoints[-1]
    d = math.hypot(gx - prev[0], gy - prev[1])
    if d <= AXLE_TO_CENTER_M:
        raise ValueError(f"last segment ({d:.3f} m) is not longer than the axle offset")
    k = AXLE_TO_CENTER_M / d
    return [*waypoints[:-1], (gx - k * (gx - prev[0]), gy - k * (gy - prev[1]))]


def to_mm(points: list[Point]) -> list[int]:
    """Flat [x1, y1, x2, y2, ...] in integer mm, as native ints (msgpack refuses numpy.int64)."""
    return [round(1000 * v) for p in points for v in p]
