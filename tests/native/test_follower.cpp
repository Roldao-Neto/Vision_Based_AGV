// Native tests of sketch/src/follower, built with the PC's g++ by tests/test_native.py.
#include <cmath>
#include <cstdio>

#include "follower/follower.h"

static int failures;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            std::printf("%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #cond);                                      \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static const double kPi = 3.14159265358979;
static const float kDt = 0.02f;

// The firmware's constants (config::kFollower)
static const follower::Config kConfig = {
    0.25f, 0.5f, 1.5707963f, (float)(2.0 * 0.5 / 0.21608), 0.015f, 0.05235988f, 0.10f, 0.5235988f, {2.3f, 1.0f, 0.5f},
};
static const float kMaxStep = 1.15f * 0.5f * kDt; // largest change of v in one tick

// A robot whose axle speed and turn rate follow the command one tick late (the wheel PIs act
// on a speed measured over the previous tick), with exact odometry.
struct Sim
{
    odometry::State pose;
    float v = 0.0f, w = 0.0f;
    int still = 0;
    int ticks = 0;
    float max_v = 0.0f, max_w = 0.0f, max_dv = 0.0f;
    // pose when each waypoint was left (index = waypoint reached)
    odometry::State reached[follower::kMaxWaypoints];
    int n_reached = 0;
    bool went_back_to_rotate = false;

    bool stopped() const { return still >= 2; }

    void step(const follower::Command &c)
    {
        const double heading = pose.theta + 0.5 * (double)w * kDt;
        pose.x += (double)v * kDt * std::cos(heading);
        pose.y += (double)v * kDt * std::sin(heading);
        pose.theta += (double)w * kDt;
        max_dv = std::fmax(max_dv, std::fabs(c.v - v));
        v = c.v;
        w = c.w;
        still = (v == 0.0f && w == 0.0f) ? still + 1 : 0;
        max_v = std::fmax(max_v, std::fabs(v));
        max_w = std::fmax(max_w, std::fabs(w));
        ticks++;
    }
};

// Runs the follower until the path ends (or 60 s); disturb(sim, tick) may shift the pose.
template <typename Disturb>
static follower::State run(Sim &sim, const int32_t *xy_mm, int32_t n, Disturb disturb)
{
    follower::State s;
    follower::start(s, kConfig, xy_mm, n, sim.pose);
    int32_t wp = s.wp;
    while (follower::active(s) && sim.ticks < 3000) {
        disturb(sim, sim.ticks);
        const follower::Phase before = s.phase;
        const follower::Command c = follower::tick(s, kConfig, sim.pose, sim.stopped(), kDt);
        if (before == follower::kDrive && s.phase == follower::kRotate && s.wp == wp) {
            sim.went_back_to_rotate = true;
        }
        if (s.wp != wp || s.phase == follower::kArrived) {
            sim.reached[sim.n_reached++] = sim.pose;
            wp = s.wp;
        }
        sim.step(c);
    }
    return s;
}

static follower::State run(Sim &sim, const int32_t *xy_mm, int32_t n)
{
    return run(sim, xy_mm, n, [](Sim &, int) {});
}

static double dist(const odometry::State &p, double x, double y)
{
    return std::hypot(p.x - x, p.y - y);
}

static void test_wrap()
{
    CHECK(std::fabs(follower::wrap(0.1) - 0.1) < 1e-12);
    CHECK(std::fabs(follower::wrap(2.0 * kPi + 0.1) - 0.1) < 1e-12);
    CHECK(std::fabs(follower::wrap(-2.0 * kPi - 0.1) + 0.1) < 1e-12);
    CHECK(std::fabs(follower::wrap(3.3) - (3.3 - 2.0 * kPi)) < 1e-12);
}

static void test_a_to_b()
{
    // The Day 3 mission: start axle (178, 745), heading 0, one waypoint on the line.
    Sim sim;
    sim.pose = {0.178, 0.745, 0.0};
    const int32_t path[] = {1581, 745};
    const follower::State s = run(sim, path, 1);
    CHECK(s.phase == follower::kArrived);
    CHECK(sim.n_reached == 1);
    // The braking curve is sampled at the start of each tick and the robot answers a tick late,
    // so near the waypoint it brakes up to ~12 % harder than a and stops ~4 mm past it
    CHECK(dist(sim.pose, 1.581, 0.745) < 0.005);
    CHECK(sim.max_v <= kConfig.cruise + 1e-6f);
    CHECK(sim.max_dv <= kMaxStep); // ramps, never a one-tick stop
    CHECK(sim.ticks * kDt < 7.0f);                   // 1.403 m at 0.25 m/s with 0.5 m/s² ramps: ~6.1 s
}

static void test_lateral_offset_is_steered_out()
{
    // 3 cm to the side of the line and 3° off: straight would drive parallel to the line;
    // re-aiming every tick converges on the waypoint.
    Sim sim;
    sim.pose = {0.178, 0.775, 0.05};
    const int32_t path[] = {1581, 745};
    run(sim, path, 1);
    CHECK(dist(sim.pose, 1.581, 0.745) < 0.01);
}

static void test_multi_waypoint_path_stops_at_each()
{
    Sim sim;
    sim.pose = {0.178, 0.745, 0.0};
    const int32_t path[] = {1000, 745, 1000, 1100, 500, 1100, 500, 600};
    const follower::State s = run(sim, path, 4);
    CHECK(s.phase == follower::kArrived);
    CHECK(sim.n_reached == 4);
    for (int i = 0; i < 4 && i < sim.n_reached; i++) {
        CHECK(dist(sim.reached[i], path[2 * i] * 1e-3, path[2 * i + 1] * 1e-3) < 0.01);
    }
    CHECK(sim.max_w <= kConfig.turn_max + 1e-6f);
    CHECK(!sim.went_back_to_rotate);
}

static void test_turns_the_short_way_with_unwrapped_heading()
{
    // θ one full turn up (an earlier rotation is not wrapped); a waypoint 0.1 rad to the right.
    follower::State s;
    const odometry::State p = {0.5, 0.5, 2.0 * kPi + 0.1};
    const int32_t path[] = {1500, 500};
    follower::start(s, kConfig, path, 1, p);
    CHECK(s.phase == follower::kRotate);
    CHECK(s.turn_dir == -1.0f);
    CHECK(std::fabs(s.turn_target - 2.0 * kPi) < 1e-9);
}

static void test_waypoint_already_reached()
{
    follower::State s;
    const odometry::State p = {0.5, 0.5, 0.0};
    const int32_t here[] = {505, 500};
    follower::start(s, kConfig, here, 1, p);
    CHECK(s.phase == follower::kArrived);
    const int32_t skip_first[] = {505, 500, 1000, 500};
    follower::start(s, kConfig, skip_first, 2, p);
    CHECK(s.phase == follower::kRotate && s.wp == 1);
}

static void test_stop_ramps_down_and_drops_the_path()
{
    Sim sim;
    sim.pose = {0.178, 0.745, 0.0};
    const int32_t path[] = {1581, 745, 1581, 1000};
    follower::State s;
    follower::start(s, kConfig, path, 2, sim.pose);
    double x_at_stop = 0.0;
    while (follower::active(s) && sim.ticks < 3000) {
        if (sim.ticks == 100) { // 2 s in, at cruise
            CHECK(s.phase == follower::kDrive && sim.v == kConfig.cruise);
            follower::stop(s);
            x_at_stop = sim.pose.x;
        }
        sim.step(follower::tick(s, kConfig, sim.pose, sim.stopped(), kDt));
    }
    CHECK(s.phase == follower::kIdle);
    CHECK(sim.max_dv <= kMaxStep);
    // v²/2a = 62.5 mm at 0.5 m/s², plus the tick of lag
    CHECK(std::fabs((sim.pose.x - x_at_stop) - 0.0625) < 0.01);
}

static void test_large_heading_error_rotates_again()
{
    // The robot is knocked 45° off while driving: it brakes, rotates toward the waypoint and
    // still gets there.
    Sim sim;
    sim.pose = {0.178, 0.745, 0.0};
    const int32_t path[] = {1581, 745};
    const follower::State s = run(sim, path, 1, [](Sim &m, int tick) {
        if (tick == 100) {
            m.pose.theta += 0.785;
        }
    });
    CHECK(sim.went_back_to_rotate);
    CHECK(s.phase == follower::kArrived);
    CHECK(dist(sim.pose, 1.581, 0.745) < 0.01);
}

int main()
{
    test_wrap();
    test_a_to_b();
    test_lateral_offset_is_steered_out();
    test_multi_waypoint_path_stops_at_each();
    test_turns_the_short_way_with_unwrapped_heading();
    test_waypoint_already_reached();
    test_stop_ramps_down_and_drops_the_path();
    test_large_heading_error_rotates_again();
    if (failures == 0) {
        std::printf("all follower tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
