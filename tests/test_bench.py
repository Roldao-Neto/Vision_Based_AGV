import math

import pytest
from bench import Pose, pose_from_corners, pose_from_reference, run_error, umbmark, wrap

HALF_WIDTH = 0.11  # any value: only the midpoint and the direction of the rear edge matter


def corners_of(p: Pose) -> tuple[tuple[float, float], tuple[float, float]]:
    """Rear corners of a robot whose axle is at p (the inverse of pose_from_corners)."""
    c, s = math.cos(p.theta), math.sin(p.theta)
    mx, my = p.x - 0.040 * c, p.y - 0.040 * s
    return (mx - HALF_WIDTH * s, my + HALF_WIDTH * c), (mx + HALF_WIDTH * s, my - HALF_WIDTH * c)


def test_corners_of_a_robot_facing_x():
    p = pose_from_corners((0.097, 0.855), (0.097, 0.635))
    assert math.isclose(p.x, 0.137, abs_tol=1e-12) and math.isclose(p.y, 0.745, abs_tol=1e-12)
    assert p.theta == 0.0


@pytest.mark.parametrize("theta", [0.3, math.pi / 2, 2.5, -math.pi / 2, -0.01])
def test_corners_round_trip(theta: float):
    p = Pose(0.8, 0.6, theta)
    q = pose_from_corners(*corners_of(p))
    assert math.isclose(q.x, p.x, abs_tol=1e-12) and math.isclose(q.y, p.y, abs_tol=1e-12)
    assert math.isclose(wrap(q.theta - p.theta), 0.0, abs_tol=1e-12)


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


def square_run(direction: int, side: float, m_nominal: float, b_nominal: float, ed: float, eb: float) -> tuple[float, float]:
    """(εx, εy) of one UMBmark run of a robot that follows its nominal odometry exactly.

    The odometry sees a perfect square (it closes at the start, θ back to 0); the real wheels
    move ed-unequal distances for the same counts (their mean is nominal: Es already corrected)
    and the real track is eb·b, so each turn is short and each leg an arc (Borenstein's model).
    """
    m_left, m_right = 2 * m_nominal / (ed + 1), 2 * m_nominal / (1 / ed + 1)
    b_real = eb * b_nominal
    x = y = th = 0.0

    def move(counts_l: float, counts_r: float, steps: int) -> None:
        nonlocal x, y, th
        for _ in range(steps):
            dl, dr = counts_l / steps * m_left, counts_r / steps * m_right
            d, dth = (dl + dr) / 2, (dr - dl) / b_real
            x += d * math.cos(th + dth / 2)
            y += d * math.sin(th + dth / 2)
            th += dth

    turn_counts = (math.pi / 2) * (b_nominal / 2) / m_nominal
    for _ in range(4):
        move(side / m_nominal, side / m_nominal, 500)
        move(-direction * turn_counts, direction * turn_counts, 200)
    return x, y


@pytest.mark.parametrize("ed, eb", [(1.0, 1.0), (1.004, 1.0), (1.0, 1.03), (1.004, 1.03), (0.997, 0.98)])
def test_umbmark_recovers_ed_and_eb(ed: float, eb: float):
    m, b, side = 0.0001607, 0.217, 1.0
    cw = [square_run(-1, side, m, b, ed, eb)]
    ccw = [square_run(1, side, m, b, ed, eb)]
    u = umbmark(cw, ccw, side, b)
    # The formulas are small-angle approximations: with both errors at once the x and y
    # estimates part slightly, and the mean lands within 6·10⁻⁵ of Ed and 7·10⁻⁴ of Eb
    # (0.15 mm of b).
    assert math.isclose(u.ed, ed, abs_tol=1e-4)
    assert math.isclose(u.eb, eb, abs_tol=1e-3)
    assert math.isclose(u.c_left + u.c_right, 2.0, abs_tol=1e-12)  # the mean diameter is kept
    assert math.isclose(u.c_right / u.c_left, u.ed, rel_tol=1e-12)
    assert u.e_max_syst == max(math.hypot(*cw[0]), math.hypot(*ccw[0]))


def test_umbmark_errors_have_the_papers_signs():
    # Turning short (Eb > 1, Type A) pulls both ends to −x (Eqs. 4.4a, 4.8a: x4 ≈ −2Lα), so α > 0.
    m, b = 0.0001607, 0.217
    u = umbmark([square_run(-1, 1.0, m, b, 1.0, 1.05)], [square_run(1, 1.0, m, b, 1.0, 1.05)], 1.0, b)
    assert u.cg_cw[0] < 0 and u.cg_ccw[0] < 0 and u.alpha > 0
    # Right wheel larger (Ed > 1, Type B) curves the legs left: β > 0.
    u = umbmark([square_run(-1, 1.0, m, b, 1.01, 1.0)], [square_run(1, 1.0, m, b, 1.01, 1.0)], 1.0, b)
    assert u.beta > 0 and u.ed > 1
