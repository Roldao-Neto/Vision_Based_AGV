#include <Arduino.h>
#include <math.h>
#include <stdlib.h>
#include "modes.h"
#include "../bridge_stack/bridge_stack.h"
#include "../config/config.h"
#include "../drive/drive.h"
#include "../encoders/encoders.h"
#include "../heading_pi/heading_pi.h"
#include "../motion_profile/motion_profile.h"
#include "../pose/pose.h"
#include "../samples/samples.h"
#include "../wheel_speed/wheel_speed.h"

namespace modes
{
    static int32_t mode = kIdle;
    static int32_t params[kParams]; // of the current mode

    // Encoder state and pose when the current mode started
    static uint32_t start_ms;
    static int32_t count_start[2];
    static uint32_t errors_start[2];
    static odometry::State pose_start;
    static uint32_t time_limit_ms;

    // Recorded runs
    static int32_t record_id;

    // Ramped stop of a moving mode (time, overshoot or command), and the mode that starts after it
    static bool stopping;
    static int32_t stop_reason;
    static bool pending;
    static int32_t pending_code;
    static int32_t pending_params[kParams];

    // Command of the last tick: axle speed (m/s, signed) and turn rate (rad/s)
    static float v_cmd;
    static float w_cmd;

    // Speed profile of the legs
    static float cruise; // m/s
    static float accel;  // m/s²

    // Current leg: drives along leg_heading (forward or backward) to the point leg_end
    static double leg_heading;
    static double leg_end_x, leg_end_y;
    static float leg_dir; // +1 forward, -1 backward
    static heading_pi::State heading_state;

    // Current in-place turn: to the absolute (not wrapped) heading turn_target
    static double turn_target;
    static float turn_dir; // +1 counter-clockwise, -1 clockwise

    // umbmark: phase = leg·2 + turning, legs 0-3, each followed by a 90° turn
    static int32_t phase;
    static float umbmark_dir; // +1 CCW (left turns), -1 CW
    static float umbmark_side; // m

    static bool all_zero(const int32_t p[kParams])
    {
        for (int i = 0; i < kParams; i++) {
            if (p[i] != 0) {
                return false;
            }
        }
        return true;
    }

    static bool valid_straight(const int32_t p[kParams])
    {
        const int32_t v = abs(p[0]), accel_mm = p[1], time_ms = p[2], distance = p[3];
        return v >= kMinMmS && v <= kMaxMmS && accel_mm >= kStraightMinAccelMmS2 &&
               accel_mm <= kStraightMaxAccelMmS2 && time_ms >= 1 && time_ms <= kStraightMaxTimeMs && distance >= 1 &&
               distance <= kStraightMaxDistanceMm;
    }

    static bool valid_umbmark(const int32_t p[kParams])
    {
        const int32_t dir = p[0], side = p[1], v = p[2], time_ms = p[3];
        return (dir == 1 || dir == -1) && side >= kUmbmarkMinSideMm && side <= kUmbmarkMaxSideMm && v >= kMinMmS &&
               v <= kMaxMmS && time_ms >= 1 && time_ms <= kUmbmarkMaxTimeMs;
    }

    bool valid(int32_t code, const int32_t p[kParams])
    {
        switch (code)
        {
            case kIdle:
                return all_zero(p);
            case kStraight:
                return valid_straight(p) && !samples::busy();
            case kUmbmark:
                return valid_umbmark(p) && !samples::busy();
            default:
                return false;
            }
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

    // The first call sets the reason; time, overshoot or a command then only wait for the stop.
    static void begin_stop(int32_t reason)
    {
        if (!stopping) {
            stopping = true;
            stop_reason = reason;
        }
    }

    // A leg of length distance (m) along heading, starting at (x0, y0); dir -1 drives it backward.
    static void start_leg(double x0, double y0, double heading, float distance, float dir)
    {
        leg_heading = heading;
        leg_dir = dir;
        leg_end_x = x0 + (double)(dir * distance) * cos(heading);
        leg_end_y = y0 + (double)(dir * distance) * sin(heading);
        heading_pi::reset(heading_state);
    }

    static void start_turn(double target)
    {
        turn_target = target;
        turn_dir = target >= pose::get().theta ? 1.0f : -1.0f;
    }

    // Heading of umbmark's leg k (also the target of the turn before it).
    static double umbmark_heading(int32_t k)
    {
        return pose_start.theta + (double)umbmark_dir * (double)k * (PI / 2.0);
    }

    static void start_straight()
    {
        cruise = (float)abs(params[0]) * 0.001f;
        accel = (float)params[1] * 0.001f;
        time_limit_ms = (uint32_t)params[2];
        start_leg(pose_start.x, pose_start.y, pose_start.theta, (float)params[3] * 0.001f,
                  params[0] > 0 ? 1.0f : -1.0f);
        phase = 0;
    }

    static void start_umbmark()
    {
        umbmark_dir = (float)params[0];
        umbmark_side = (float)params[1] * 0.001f;
        cruise = (float)params[2] * 0.001f;
        accel = config::kAccelMps2;
        time_limit_ms = (uint32_t)params[3];
        start_leg(pose_start.x, pose_start.y, pose_start.theta, umbmark_side, 1.0f);
        phase = 0;
    }

    // The sample of this tick: the counts read at its start and the command and duties applied
    // since the previous tick.
    static void record()
    {
        const int32_t values[8] = {
            (int32_t)samples::us_since_start(),
            phase,
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
    // the Python reference can redo the run from the samples.
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
            params[0],
            params[1],
            params[2],
            params[3],
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

    // Ends the moving mode (the samples stop first, so they cover the driven part), coasting.
    static void end_current(int32_t reason)
    {
        if (mode != kIdle) {
            samples::stop();
            drive::coast();
            end_run(reason);
        }
        mode = kIdle;
    }

    static void start(int32_t code, const int32_t p[kParams])
    {
        mode = code;
        if (mode == kIdle) {
            return;
        }
        for (int i = 0; i < kParams; i++) {
            params[i] = p[i];
        }
        take_encoder_start();
        stopping = false;
        pending = false;
        v_cmd = 0.0f;
        w_cmd = 0.0f;
        drive::begin();
        record_id++;
        if (mode == kStraight) {
            start_straight();
        } else {
            start_umbmark();
        }
        samples::start("run_samples", record_id, 8, 5);
    }

    // A ramped stop ended: report, then start the mode requested during it, if any.
    static void finish(int32_t reason)
    {
        end_current(reason);
        if (pending) {
            pending = false;
            start(pending_code, pending_params);
        }
    }

    void request(int32_t code, const int32_t p[kParams])
    {
        if (mode != kIdle) {
            begin_stop(kEndCommand);
            pending = true;
            pending_code = code;
            for (int i = 0; i < kParams; i++) {
                pending_params[i] = p[i];
            }
            return;
        }
        start(code, p);
    }

    // One tick of the current leg; true once it has stopped (at its end, or after a ramped stop).
    // The remaining distance is measured along the leg's heading, s = (w − p)·u, and the profile stops at w; near it (and past it) steering holds and v only
    // ramps down. The heading PI holds the leg's heading.
    static bool tick_leg(float dt)
    {
        const odometry::State &p = pose::get();
        const double ux = cos(leg_heading), uy = sin(leg_heading);
        const float remaining = leg_dir * (float)((leg_end_x - p.x) * ux + (leg_end_y - p.y) * uy);
        if (remaining < -config::kLegOvershootM) {
            begin_stop(kEndDistance);
        }
        const motion_profile::Step step =
            stopping ? motion_profile::next(fabsf(v_cmd), -1.0f, cruise, config::kStopDecelMps2, dt,
                                            config::kSteerStopM)
                     : motion_profile::next(fabsf(v_cmd), remaining, cruise, accel, dt, config::kSteerStopM);
        if (step.speed == 0.0f && drive::stopped()) {
            return true;
        }
        float w = 0.0f;
        if (step.speed > 0.0f && remaining >= config::kSteerStopM) {
            const float e = heading_pi::wrap((float)(leg_heading - p.theta));
            w = heading_pi::update(heading_state, config::kHeadingPi, e, dt);
        }
        v_cmd = leg_dir * step.speed;
        w_cmd = w;
        drive::set(v_cmd, leg_dir * step.accel, w, 0.0f, dt);
        return false;
    }

    // One tick of the current in-place turn; true once it has stopped. The same profile on the
    // heading error: below 3° (overshoot included) |ω| only ramps down, and
    // the turn ends when the commanded ω is zero and the wheels have stopped. A ramped stop
    // brakes at α, so each wheel brakes at 0.5 m/s².
    static bool tick_turn(float dt)
    {
        const float remaining = turn_dir * (float)(turn_target - pose::get().theta);
        const motion_profile::Step step =
            motion_profile::next(fabsf(w_cmd), stopping ? -1.0f : remaining, config::kTurnMaxRadS,
                                 config::kTurnAccelRadS2, dt, config::kHeadingStopRad);
        if (step.speed == 0.0f && drive::stopped()) {
            return true;
        }
        v_cmd = 0.0f;
        w_cmd = turn_dir * step.speed;
        drive::set(0.0f, 0.0f, w_cmd, turn_dir * step.accel, dt);
        return false;
    }

    static void tick_straight(float dt)
    {
        if (tick_leg(dt)) {
            finish(stopping ? stop_reason : kEndTarget);
        }
    }

    // UMBmark (Borenstein and Feng 1996, Sec. 3.3 and 5): four legs of the square, stopping at
    // each corner and turning 90° in place, the fourth turn back to the start heading. Every
    // leg and turn aims at absolute targets fixed by the start pose (corners and headings), so
    // the odometry closes the square whatever the stopping errors were.
    static void tick_umbmark(float dt)
    {
        const bool turning = (phase & 1) != 0;
        if (!(turning ? tick_turn(dt) : tick_leg(dt))) {
            return;
        }
        if (stopping) {
            finish(stop_reason);
            return;
        }
        if (phase == 7) {
            finish(kEndTarget);
            return;
        }
        phase++;
        const int32_t leg = phase / 2;
        if ((phase & 1) != 0) {
            start_turn(umbmark_heading(leg + 1));
            tick_turn(dt);
        } else {
            start_leg(leg_end_x, leg_end_y, umbmark_heading(leg), umbmark_side, 1.0f);
            tick_leg(dt);
        }
    }

    void tick()
    {
        if (mode == kIdle) {
            return;
        }
        record();
        if (bridge_stack::emergency()) {
            pending = false; // the motors are locked; stay idle
            end_current(kEndEmergency);
            return;
        }
        if (drive::observe()) {
            pending = false;
            end_current(kEndEncoder);
            return;
        }
        if (millis() - start_ms >= time_limit_ms) {
            begin_stop(kEndTime);
        }
        const float dt = tick_dt();
        if (mode == kStraight) {
            tick_straight(dt);
        } else {
            tick_umbmark(dt);
        }
    }

    int32_t current()
    {
        return mode;
    }
}
