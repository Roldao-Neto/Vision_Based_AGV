import math

import pytest
from bench import Pose, pose_from_reference, pose_from_tapes, run_error, wrap

REAR_TO_FRONT = 0.24  # any value: the heading only depends on the rise over it
CROSS = (1.540, 0.745)


def tapes_of(p: Pose) -> tuple[float, float, float]:
    """(dx, dy, dy_front) of a robot whose axle is at p (the inverse of pose_from_tapes)."""
    c, s = math.cos(p.theta), math.sin(p.theta)
    rx, ry = p.x - 0.04075 * c, p.y - 0.04075 * s
    return rx - CROSS[0], ry - CROSS[1], ry + REAR_TO_FRONT * s - CROSS[1]


def test_robot_on_the_cross_facing_x():
    p = pose_from_tapes(CROSS, 0.0, 0.0, 0.0, REAR_TO_FRONT)
    assert math.isclose(p.x, 1.58075, abs_tol=1e-12) and p.y == 0.745 and p.theta == 0.0


def test_front_point_to_the_left_turns_ccw():
    p = pose_from_tapes(CROSS, -0.028, 0.002, 0.003, REAR_TO_FRONT)
    assert math.isclose(p.theta, math.asin(0.001 / REAR_TO_FRONT), abs_tol=1e-15) and p.theta > 0


@pytest.mark.parametrize("theta", [0.0, 0.004, -0.05, 0.3, -1.0])
def test_tapes_round_trip(theta: float):
    p = Pose(1.55, 0.76, theta)
    q = pose_from_tapes(CROSS, *tapes_of(p), REAR_TO_FRONT)
    assert math.isclose(q.x, p.x, abs_tol=1e-12) and math.isclose(q.y, p.y, abs_tol=1e-12)
    assert math.isclose(q.theta, p.theta, abs_tol=1e-12)


def test_impossible_rise_is_refused():
    with pytest.raises(ValueError):
        pose_from_tapes(CROSS, 0.0, 0.0, 0.25, REAR_TO_FRONT)


def test_reference_point_is_40_75_mm_behind_the_axle():
    p = pose_from_reference(0.137, 0.745, 0.0)
    assert math.isclose(p.x, 0.17775, abs_tol=1e-12) and p.y == 0.745


def test_errors_are_real_minus_odometry_in_each_start_frame():
    # The odometry runs in its own frame (boot pose), rotated and shifted from the arena.
    q = math.pi / 2  # the odometry's start heading: its +y is the run's forward
    real = run_error(Pose(0.2, 0.7, 0.0), Pose(1.6, 0.72, 0.01), Pose(1.0, 2.0, q), Pose(1.0, 2.0 + 1.39, q + 0.004))
    assert math.isclose(real.ex, 1.4 - 1.39, abs_tol=1e-12)
    assert math.isclose(real.ey, 0.02, abs_tol=1e-12)
    assert math.isclose(real.etheta, 0.006, abs_tol=1e-12)
    assert math.isclose(real.odometry[0], 1.39, abs_tol=1e-12)
    assert math.isclose(real.odometry[1], 0.0, abs_tol=1e-12)


def test_full_turns_compare_as_wrapped_headings():
    e = run_error(Pose(0, 0, 0), Pose(0, 0, 0.01), Pose(0, 0, 7.0), Pose(0, 0, 7.0 + 2 * math.pi))
    assert math.isclose(e.etheta, 0.01, abs_tol=1e-12)
