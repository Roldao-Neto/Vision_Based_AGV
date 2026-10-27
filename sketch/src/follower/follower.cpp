#include "follower.h"

#include <math.h>

#include "../motion_profile/motion_profile.h"

namespace follower
{
    static const double kPi = 3.14159265358979;

    double wrap(double angle)
    {
        return remainder(angle, 2.0 * kPi);
    }

    static double distance_to(const State &s, int32_t wp, const odometry::State &p)
    {
        return hypot(s.xy[2 * wp] - p.x, s.xy[2 * wp + 1] - p.y);
    }

    static void begin_rotate(State &s, const odometry::State &p)
    {
        const double bearing = atan2(s.xy[2 * s.wp + 1] - p.y, s.xy[2 * s.wp] - p.x);
        s.turn_target = p.theta + wrap(bearing - p.theta);
        s.turn_dir = s.turn_target >= p.theta ? 1.0f : -1.0f;
        s.phase = kRotate;
        s.realigning = false;
        s.speed = 0.0f;
    }

    static void aim(State &s, const Config &c, const odometry::State &p)
    {
        if (s.frozen) {
            return;
        }
        const double dx = s.xy[2 * s.wp] - p.x, dy = s.xy[2 * s.wp + 1] - p.y;
        const double d = hypot(dx, dy);
        if (d > 0.0) {
            s.ux = dx / d;
            s.uy = dy / d;
            s.aim = atan2(dy, dx);
        }
        s.frozen = d <= (double)c.freeze;
    }

    static void begin_drive(State &s, const Config &c, const odometry::State &p)
    {
        s.phase = kDrive;
        s.speed = 0.0f;
        s.frozen = false;
        s.ux = cos(p.theta);
        s.uy = sin(p.theta);
        s.aim = wrap(p.theta);
        heading_pi::reset(s.heading);
        aim(s, c, p);
    }

    static void begin_waypoint(State &s, const Config &c, const odometry::State &p)
    {
        while (distance_to(s, s.wp, p) < (double)c.steer_stop) {
            if (s.wp + 1 >= s.n) {
                s.phase = kArrived;
                s.speed = 0.0f;
                return;
            }
            s.wp++;
        }
        begin_rotate(s, p);
    }

    void start(State &s, const Config &c, const int32_t *xy_mm, int32_t n, const odometry::State &p)
    {
        s.n = n;
        for (int32_t i = 0; i < 2 * n; i++) {
            s.xy[i] = (double)xy_mm[i] * 0.001;
        }
        s.wp = 0;
        s.stopping = false;
        begin_waypoint(s, c, p);
    }

    bool active(const State &s)
    {
        return s.phase == kRotate || s.phase == kDrive;
    }

    void stop(State &s)
    {
        if (active(s)) {
            s.stopping = true;
        }
    }

    void abort(State &s)
    {
        if (active(s)) {
            s.phase = kIdle;
            s.speed = 0.0f;
        }
    }

    static Command tick_rotate(State &s, const Config &c, const odometry::State &p, bool stopped, float dt)
    {
        const float remaining = s.turn_dir * (float)(s.turn_target - p.theta);
        const motion_profile::Step step = motion_profile::next(
            s.speed,
            s.stopping ? -1.0f : remaining,
            c.turn_max,
            c.turn_accel,
            dt,
            c.heading_stop
        );
        if (step.speed == 0.0f && stopped) {
            if (s.stopping) {
                s.phase = kIdle;
            } else {
                begin_drive(s, c, p);
            }
            return Command{};
        }
        s.speed = step.speed;
        return Command{0.0f, 0.0f, s.turn_dir * step.speed, s.turn_dir * step.accel};
    }

    static Command tick_drive(State &s, const Config &c, const odometry::State &p, bool stopped, float dt)
    {
        aim(s, c, p);

        const float remaining = (float)((s.xy[2 * s.wp] - p.x) * s.ux + (s.xy[2 * s.wp + 1] - p.y) * s.uy);
        const float e = (float)wrap(s.aim - p.theta);

        if (!s.frozen && !s.stopping && fabsf(e) > c.realign) {
            s.realigning = true;
        }

        const bool braking = s.stopping || s.realigning;

        const motion_profile::Step step = motion_profile::next(
            s.speed,
            braking ? -1.0f : remaining,
            c.cruise,
            c.accel,
            dt,
            c.steer_stop
        );

        if (step.speed == 0.0f && stopped) {
            if (s.stopping) {
                s.phase = kIdle;
            } else if (s.realigning) {
                begin_rotate(s, p);
            } else if (s.wp + 1 >= s.n) {
                s.phase = kArrived;
                s.speed = 0.0f;
            } else {
                s.wp++;
                begin_waypoint(s, c, p);
            }
            return Command{};
        }

        float w = 0.0f;

        if (step.speed > 0.0f && remaining >= c.steer_stop) {
            w = heading_pi::update(s.heading, c.heading, e, dt);
        }

        s.speed = step.speed;

        return Command{step.speed, step.accel, w, 0.0f};
    }

    Command tick(State &s, const Config &c, const odometry::State &p, bool stopped, float dt)
    {
        if (s.phase == kRotate) {
            return tick_rotate(s, c, p, stopped, dt);
        }
        if (s.phase == kDrive) {
            return tick_drive(s, c, p, stopped, dt);
        }
        return Command{};
    }
}
