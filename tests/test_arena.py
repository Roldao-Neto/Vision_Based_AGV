import math

import pytest
from arena import A_CENTER, B_CENTER, START_AXLE, axle_to_center, center_to_axle, pull_back_goal, to_mm


def test_start_axle_is_seven_cm_behind_a():
    assert START_AXLE == pytest.approx((0.178, 0.745))
    assert axle_to_center(*START_AXLE, 0.0) == pytest.approx(A_CENTER)


def test_center_axle_round_trip_at_any_heading():
    for theta in (0.0, 0.7, -1.9, 2 * math.pi + 0.3):
        axle = center_to_axle(1.0, 0.5, theta)
        assert math.hypot(axle[0] - 1.0, axle[1] - 0.5) == pytest.approx(0.07)
        assert axle_to_center(*axle, theta) == pytest.approx((1.0, 0.5))


def test_goal_pulled_back_along_the_last_segment():
    # A -> B: the axle stops at B - 7 cm, so the center is on B (CLAUDE.md, Reference point)
    assert pull_back_goal(START_AXLE, [B_CENTER]) == [pytest.approx((1.581, 0.745))]
    # Only the last waypoint moves, along the segment from the one before it
    path = pull_back_goal(START_AXLE, [(1.0, 0.745), (1.0, 1.2)])
    assert path[0] == (1.0, 0.745)
    assert path[1] == pytest.approx((1.0, 1.13))


def test_last_segment_must_be_longer_than_the_offset():
    with pytest.raises(ValueError):
        pull_back_goal((1.0, 1.0), [(1.05, 1.0)])


def test_to_mm_gives_native_ints():
    mm = to_mm([(1.5805, 0.745), START_AXLE])
    assert mm == [1580, 745, 178, 745] or mm == [1581, 745, 178, 745]
    assert all(type(v) is int for v in mm)
