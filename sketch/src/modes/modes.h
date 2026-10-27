#pragma once

#include <Arduino.h>

namespace modes
{
    enum Mode : int32_t {
        kIdle = 0,
        // 1-3 were the Day 1 identification modes (count, step, ramp), 4 the Day 1 wheel PI
        // test (speed) and 5-6 the Day 2 calibration modes (straight, umbmark), kept out of use
        // so the earlier records keep their meaning
        kPath = 7, // a run: from the first set_path to the goal or a failure, replans included
    };

    enum EndReason : int32_t {
        // 1 (time) and 2 (overshoot guard) were the Day 2 limits
        kEndCommand = 3,   // mode idle
        kEndEmergency = 4, // bridge stack emergency
        kEndEncoder = 5,   // encoder guard: a wheel driven hard without counting
        kEndTarget = 6,    // stopped at the last waypoint
        kEndHeartbeat = 7, // no hb for config::kHeartbeatTimeoutMs
    };

    constexpr int kParams = 4;

    // Handler side, any thread: true if code is a mode and its params are allowed (only idle,
    // all zero; a path starts with set_path).
    bool valid(int32_t code, const int32_t params[kParams]);

    // Any thread: no run open and neither wheel counted in the last tick (reset_pose).
    bool still();

    // Any thread: a set_path would start now: the wheels still and either no run open and the
    // last run's samples sent, or a run paused by stop.
    bool path_allowed();

    // Tick side: follows n waypoints (x, y in mm, already validated) as path id. With no run
    // open it opens one (start pose, recording); in a paused run it is a replan of the same
    // run. Ignored unless path_allowed().
    void start_path(int32_t id, const int32_t *xy_mm, int32_t n);

    // Tick side: ramped stop of the current path, whose rest is dropped; the run stays open
    // (paused) for the next set_path.
    void stop();

    // Tick side (mode idle): ramped stop, then the run ends and its samples go out.
    void end_run();

    // Tick side, once per tick after the commands: runs the current mode.
    void tick();

    int32_t current();

    // For the pose notification: the follower's phase (follower::Phase), the id of the last
    // path started (0 before the first) and the waypoint being executed.
    int32_t phase();
    int32_t path_id();
    int32_t wp_idx();
}
