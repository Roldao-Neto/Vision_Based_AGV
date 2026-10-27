#include <Arduino.h>
#include <math.h>
#include <zephyr/kernel.h>
#include "modes.h"
#include "../bridge_stack/bridge_stack.h"
#include "../config/config.h"
#include "../drive/drive.h"
#include "../encoders/encoders.h"
#include "../follower/follower.h"
#include "../handlers/handlers.h"
#include "../motor_driver/motor_driver.h"
#include "../pose/pose.h"
#include "../samples/samples.h"
#include "../wheel_speed/wheel_speed.h"

namespace modes
{
    static int32_t mode = kIdle;

    // Encoder state and pose when the current path started
    static uint32_t start_ms;
    static int32_t count_start[2];
    static uint32_t errors_start[2];
    static odometry::State pose_start;

    // Recorded runs
    static int32_t record_id;

    // The current (or last) path, and the run it belongs to
    static follower::State path;
    static int32_t current_path_id;
    static int32_t paths_in_run;
    static bool ending; // mode idle: the run ends once the robot has stopped

    // Command of the last tick: axle speed (m/s) and turn rate (rad/s)
    static float v_cmd;
    static float w_cmd;

    bool valid(int32_t code, const int32_t p[kParams])
    {
        if (code != kIdle) {
            return false;
        }
        for (int i = 0; i < kParams; i++) {
            if (p[i] != 0) {
                return false;
            }
        }
        return true;
    }

    static bool wheels_still()
    {
        return wheel_speed::speed(config::kLeft) == 0.0f && wheel_speed::speed(config::kRight) == 0.0f;
    }

    bool still()
    {
        return mode == kIdle && wheels_still();
    }

    bool path_allowed()
    {
        if (!wheels_still() || bridge_stack::emergency()) {
            return false;
        }
        return mode == kIdle ? !samples::busy() : !follower::active(path) && !ending;
    }

    static void take_encoder_start()
    {
        start_ms = millis();
        for (int w = 0; w < 2; w++) {
            count_start[w] = wheel_speed::count((config::Wheel)w);
            errors_start[w] = encoders::errors((config::Wheel)w);
        }
        pose_start = pose::get();
    }

    static int32_t counts_since_start(int w)
    {
        return wheel_speed::count((config::Wheel)w) - count_start[w];
    }

    static uint32_t errors_since_start(int w)
    {
        return encoders::errors((config::Wheel)w) - errors_start[w];
    }

    static float tick_dt()
    {
        const uint32_t dt_us = wheel_speed::dt_us();
        return dt_us != 0 ? (float)dt_us * 1e-6f : (float)config::kTickPeriodUs * 1e-6f;
    }

    // The sample of this tick: phase = waypoint·2 + rotating, the counts read at its start and
    // the command and duties applied since the previous tick.
    static void record()
    {
        const int32_t values[8] = {
            (int32_t)samples::us_since_start(),
            path.wp * 2 + (path.phase == follower::kRotate ? 1 : 0),
            (int32_t)lroundf(v_cmd * 1000.0f), // mm/s
            (int32_t)lroundf(w_cmd * 1000.0f), // mrad/s
            wheel_speed::count(config::kLeft), // absolute, the counts the odometry used
            wheel_speed::count(config::kRight),
            (int32_t)lroundf(drive::duty(config::kLeft) * 10000.0f),
            (int32_t)lroundf(drive::duty(config::kRight) * 10000.0f)
        };
        samples::add(values);
    }

    // The end report carries the start and end poses and the constants the odometry used, so
    // the Python reference can redo the run from the samples. p1 = last path id, p2 = paths in
    // the run (1 + replans), p3 = waypoint being executed at the end, p4 = waypoints in the
    // last path.
    static void end_run(int32_t reason)
    {
        const uint32_t now_ms = millis();
        const odometry::State &p = pose::get();
        const odometry::Config &c = config::kOdometry;
        Bridge.notify(
            "run_end",
            now_ms,
            record_id,
            mode,
            now_ms - start_ms,
            reason,
            current_path_id,
            paths_in_run,
            path.wp,
            path.n,
            counts_since_start(config::kLeft),
            counts_since_start(config::kRight),
            errors_since_start(config::kLeft),
            errors_since_start(config::kRight),
            samples::count(),
            (int32_t)llround(pose_start.x * 1e6),     // µm
            (int32_t)llround(pose_start.y * 1e6),
            (int32_t)llround(pose_start.theta * 1e6), // µrad
            (int32_t)llround(p.x * 1e6),
            (int32_t)llround(p.y * 1e6),
            (int32_t)llround(p.theta * 1e6),
            (int32_t)llround(c.m_per_count[config::kLeft] * 1e12), // pm
            (int32_t)llround(c.m_per_count[config::kRight] * 1e12),
            (int32_t)llround(c.track_m * 1e9)                      // nm
        );
    }

    // Ends the run (the samples stop first, so they cover the driven part), coasting.
    static void end_current(int32_t reason)
    {
        if (mode != kIdle) {
            samples::stop();
            drive::coast();
            follower::abort(path);
            end_run(reason);
        }
        mode = kIdle;
    }

    void start_path(int32_t id, const int32_t *xy_mm, int32_t n)
    {
        if (!path_allowed()) {
            return;
        }
        if (mode == kIdle) {
            mode = kPath;
            take_encoder_start();
            paths_in_run = 0;
            ending = false;
            record_id++;
            samples::start("run_samples", record_id, 8, 5);
        }
        paths_in_run++;
        current_path_id = id;
        v_cmd = 0.0f;
        w_cmd = 0.0f;
        drive::begin();
        follower::start(path, config::kFollower, xy_mm, n, pose::get());
    }

    void stop()
    {
        if (mode == kPath) {
            follower::stop(path);
        }
    }

    void end_run()
    {
        if (mode == kPath) {
            ending = true;
            follower::stop(path);
        }
    }

    void tick()
    {
        if (mode == kIdle) {
            return;
        }
        record();
        if (bridge_stack::emergency()) {
            end_current(kEndEmergency); // the motors are locked
            return;
        }
        if (drive::observe()) {
            end_current(kEndEncoder);
            return;
        }
        if (k_uptime_get_32() - handlers::last_hb_ms() > config::kHeartbeatTimeoutMs) {
            end_current(kEndHeartbeat);
            motor_driver::brake(config::kLeft);
            motor_driver::brake(config::kRight);
            return;
        }
        const float dt = tick_dt();
        const follower::Command c = follower::tick(path, config::kFollower, pose::get(), drive::stopped(), dt);
        if (path.phase == follower::kArrived) {
            end_current(kEndTarget);
            return;
        }
        if (!follower::active(path)) {
            if (ending) {
                end_current(kEndCommand);
                return;
            }
            // Paused by stop: still recording, until the next set_path or mode idle
            v_cmd = 0.0f;
            w_cmd = 0.0f;
            drive::coast();
            return;
        }
        v_cmd = c.v;
        w_cmd = c.w;
        drive::set(c.v, c.a, c.w, c.alpha, dt);
    }

    int32_t current()
    {
        return mode;
    }

    int32_t phase()
    {
        return path.phase;
    }

    int32_t path_id()
    {
        return current_path_id;
    }

    int32_t wp_idx()
    {
        return path.wp;
    }
}
