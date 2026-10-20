// Native tests of sketch/src/motion_profile, built with the PC's g++ by tests/test_native.py.
#include <cmath>
#include <cstdio>

#include "motion_profile/motion_profile.h"

static int failures;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            std::printf("%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #cond);                                      \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static const float kDt = 0.02f, kA = 0.5f, kVmax = 0.25f, kBand = 0.015f;

// Drives a perfect point along the profile until it stops; returns where it stopped and checks
// every step against the limits.
static float run_to(float target, float *peak)
{
    float p = 0.0f, v = 0.0f;
    *peak = 0.0f;
    for (int i = 0; i < 2000; i++) {
        const motion_profile::Step s = motion_profile::next(v, target - p, kVmax, kA, kDt, kBand);
        CHECK(s.speed >= 0.0f && s.speed <= kVmax + 1e-6f);
        // The braking curve is sampled at the start of each tick while the robot keeps moving
        // during it, so near the target it brakes up to ~8 % harder than a (0.54 m/s² in the
        // last 2 cm) and stops ~3 mm late
        CHECK(std::fabs(s.speed - v) <= 1.1f * kA * kDt);
        p += 0.5f * (v + s.speed) * kDt;
        v = s.speed;
        *peak = std::fmax(*peak, v);
        if (v == 0.0f && i > 0) {
            break;
        }
    }
    CHECK(v == 0.0f);
    return p;
}

static void test_stops_at_the_target()
{
    float peak;
    const float end = run_to(1.38f, &peak); // the A→B line
    CHECK(std::fabs(end - 1.38f) < 0.005f);
    CHECK(peak == kVmax);
}

static void test_short_move_is_a_triangle()
{
    // 0.1 m is shorter than the 0.125 m that a full ramp up and down needs.
    float peak;
    const float end = run_to(0.1f, &peak);
    CHECK(std::fabs(end - 0.1f) < 0.005f);
    CHECK(peak < kVmax && peak <= std::sqrt(kA * 0.1f) + 0.01f);
}

static void test_overshoot_ramps_down_instead_of_stopping()
{
    // Past the target at 0.2 m/s: the speed must fall by a·dt per tick, not to zero at once.
    const motion_profile::Step s = motion_profile::next(0.2f, -0.01f, kVmax, kA, kDt, kBand);
    CHECK(std::fabs(s.speed - 0.19f) < 1e-6f);
    CHECK(s.accel == -kA);
    const motion_profile::Step z = motion_profile::next(0.005f, 0.0f, kVmax, kA, kDt, kBand);
    CHECK(z.speed == 0.0f);
    CHECK(motion_profile::next(0.0f, 0.0f, kVmax, kA, kDt, kBand).accel == 0.0f);
}

static void test_commanded_acceleration()
{
    CHECK(motion_profile::next(0.0f, 1.0f, kVmax, kA, kDt, kBand).accel == kA);   // speeding up
    CHECK(motion_profile::next(kVmax, 1.0f, kVmax, kA, kDt, kBand).accel == 0.0f); // cruise
    CHECK(motion_profile::next(kVmax, 0.05f, kVmax, kA, kDt, kBand).accel == -kA); // braking curve
}

static void test_angular_use()
{
    // A 360° spin at 90°/s and α = 2a/b: same law in rad.
    const float alpha = 2.0f * kA / 0.217f, w_max = 1.5707963f, band = 0.0523599f;
    float th = 0.0f, w = 0.0f;
    for (int i = 0; i < 1000; i++) {
        const motion_profile::Step s = motion_profile::next(w, 6.2831853f - th, w_max, alpha, kDt, band);
        th += 0.5f * (w + s.speed) * kDt;
        w = s.speed;
        if (w == 0.0f && i > 0) {
            break;
        }
    }
    CHECK(w == 0.0f);
    CHECK(std::fabs(th - 6.2831853f) < 0.02f); // ~1°
}

static void test_turn_with_lagging_wheels()
{
    // The 90° turns of umbmark, closed on the measured heading as in modes.cpp, with the real
    // turn rate one tick behind the command (the wheel PI tracks the profile's ramps through its
    // feedforward, but acts on a speed measured over the previous tick). The braking curve is
    // sampled at the start of each tick, so even a perfect plant ends ~1° past the target; one
    // tick of delay ends ~2° past it, still inside the 3° band, and ω reaches zero there.
    const float alpha = 2.0f * kA / 0.217f, w_max = 1.5707963f, band = 0.0523599f, target = 1.5707963f;
    float th = 0.0f, w_cmd = 0.0f, w_real = 0.0f;
    int i = 0;
    for (; i < 1000; i++) {
        const float w_next = w_cmd; // the command of the previous tick
        th += 0.5f * (w_real + w_next) * kDt;
        w_real = w_next;
        w_cmd = motion_profile::next(w_cmd, target - th, w_max, alpha, kDt, band).speed;
        if (w_cmd == 0.0f && w_real == 0.0f && i > 0) {
            break;
        }
    }
    CHECK(i < 1000);
    CHECK(th > target && th - target < band);
}

int main()
{
    test_stops_at_the_target();
    test_short_move_is_a_triangle();
    test_overshoot_ramps_down_instead_of_stopping();
    test_commanded_acceleration();
    test_angular_use();
    test_turn_with_lagging_wheels();
    if (failures == 0) {
        std::printf("all motion_profile tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
