// Native tests of sketch/src/odometry, built with the PC's g++ by tests/test_native.py.
#include <cmath>
#include <cstdio>

#include "odometry/odometry.h"

static int failures;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            std::printf("%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #cond);                                      \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static bool near(double a, double b, double tol)
{
    return std::fabs(a - b) <= tol;
}

static const double kPi = 3.14159265358979323846;
static const double kMpc = 0.0001607; // m per count, close to the nominal wheel
static const odometry::Config kConfig = {{kMpc, kMpc}, 0.217};

static void test_straight_forward_and_backward()
{
    odometry::State s;
    for (int i = 0; i < 300; i++) {
        odometry::update(s, kConfig, 30, 30);
    }
    CHECK(near(s.x, 9000 * kMpc, 1e-12));
    CHECK(s.y == 0.0);
    CHECK(s.theta == 0.0);
    for (int i = 0; i < 300; i++) {
        odometry::update(s, kConfig, -30, -30);
    }
    CHECK(near(s.x, 0.0, 1e-12));
}

static void test_spin_in_place_keeps_position_and_does_not_wrap()
{
    // Two full turns: each wheel travels 2·π·b, i.e. 2·(2π·b/2) per turn.
    odometry::State s;
    const int per_tick = 10;
    const double counts_per_turn = kPi * 0.217 / kMpc; // per wheel
    const int ticks = (int)std::lround(2.0 * counts_per_turn / per_tick);
    for (int i = 0; i < ticks; i++) {
        odometry::update(s, kConfig, -per_tick, per_tick);
    }
    const double expected = 2.0 * ticks * per_tick * kMpc / 0.217;
    CHECK(near(s.theta, expected, 1e-9));
    CHECK(near(s.theta, 4.0 * kPi, 0.01));
    CHECK(near(s.x, 0.0, 1e-12));
    CHECK(near(s.y, 0.0, 1e-12));
}

static void test_constant_curvature_matches_the_circle()
{
    // dL = 20, dR = 30 counts per tick: radius R = b/2·(dR + dL)/(dR − dL), and after a total
    // turn Θ the exact position is (R·sin Θ, R·(1 − cos Θ)). Midpoint integration only shortens
    // each chord by a factor ~dθ²/24 (~2 µm over this 0.8 m arc).
    odometry::State s;
    const int ticks = 200;
    for (int i = 0; i < ticks; i++) {
        odometry::update(s, kConfig, 20, 30);
    }
    const double b = 0.217;
    const double dtheta = 10 * kMpc / b;
    const double radius = b / 2 * 50.0 / 10.0;
    const double big_theta = ticks * dtheta;
    CHECK(near(s.theta, big_theta, 1e-9));
    CHECK(near(s.x, radius * std::sin(big_theta), 1e-5));
    CHECK(near(s.y, radius * (1.0 - std::cos(big_theta)), 1e-5));
}

static void test_each_wheel_uses_its_own_scale()
{
    // A right wheel 1 % larger turns the same counts into a left turn of 0.01·d/b.
    const odometry::Config c = {{kMpc, kMpc * 1.01}, 0.217};
    odometry::State s;
    odometry::update(s, c, 1000, 1000);
    const double dl = 1000 * kMpc, dr = 1000 * kMpc * 1.01;
    CHECK(near(s.theta, (dr - dl) / 0.217, 1e-12));
    CHECK(near(s.x, (dl + dr) / 2 * std::cos(s.theta / 2), 1e-12));
    CHECK(s.y > 0.0);
}

int main()
{
    test_straight_forward_and_backward();
    test_spin_in_place_keeps_position_and_does_not_wrap();
    test_constant_curvature_matches_the_circle();
    test_each_wheel_uses_its_own_scale();
    if (failures == 0) {
        std::printf("all odometry tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
