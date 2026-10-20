import math

from odometry import Pose, integrate, step

MPC = 0.0001607
B = 0.217


def test_straight_line():
    counts = list(range(0, 9001, 30))
    end = integrate(counts, counts, MPC, MPC, B, Pose(0.0, 0.0, 0.0))[-1]
    assert math.isclose(end.x, 9000 * MPC, rel_tol=1e-12)
    assert end.y == 0.0 and end.theta == 0.0


def test_spin_in_place_does_not_wrap():
    n = round(2 * math.pi * B / 2 / MPC / 10) * 2  # ticks of ±10 counts for ~two turns
    left = [-10 * i for i in range(n + 1)]
    right = [10 * i for i in range(n + 1)]
    end = integrate(left, right, MPC, MPC, B, Pose(1.0, 2.0, 0.5))[-1]
    assert math.isclose(end.theta, 0.5 + 2 * n * 10 * MPC / B, rel_tol=1e-12)
    assert end.theta > 0.5 + 4 * math.pi - 0.02
    assert math.isclose(end.x, 1.0, abs_tol=1e-12) and math.isclose(end.y, 2.0, abs_tol=1e-12)


def test_constant_curvature_matches_the_circle():
    ticks = 200
    left = [20 * i for i in range(ticks + 1)]
    right = [30 * i for i in range(ticks + 1)]
    end = integrate(left, right, MPC, MPC, B, Pose(0.0, 0.0, 0.0))[-1]
    radius = B / 2 * 50 / 10
    big_theta = ticks * 10 * MPC / B
    assert math.isclose(end.theta, big_theta, rel_tol=1e-12)
    assert math.isclose(end.x, radius * math.sin(big_theta), abs_tol=1e-5)
    assert math.isclose(end.y, radius * (1 - math.cos(big_theta)), abs_tol=1e-5)


def test_each_wheel_uses_its_own_scale():
    p = step(Pose(0.0, 0.0, 0.0), 1000, 1000, MPC, MPC * 1.01, B)
    dl, dr = 1000 * MPC, 1000 * MPC * 1.01
    assert math.isclose(p.theta, (dr - dl) / B, rel_tol=1e-12)
    assert math.isclose(p.x, (dl + dr) / 2 * math.cos(p.theta / 2), rel_tol=1e-12)
