#pragma once

#include <stdint.h>

#include "../heading_pi/heading_pi.h"
#include "../odometry/odometry.h"

namespace follower
{
    constexpr int kMaxWaypoints = 32;

    // Reported in the pose notification
    enum Phase : int32_t {
        kIdle = 0,
        kRotate = 1,
        kDrive = 2,
        kArrived = 3, // stopped at the last waypoint
        kLook = 4,    // stopped after ROTATE, so the camera can confirm what the turn revealed
    };

    struct Config
    {
        float cruise;       // m/s
        float accel;        // m/s², speed ramps and every planned stop
        float turn_max;     // rad/s
        float turn_accel;   // rad/s², α = 2a/b, so each wheel also ramps at accel
        float steer_stop;   // m: below this along-track distance steering holds and v only ramps down
        float heading_stop; // rad: below this heading error |ω| only ramps down
        float freeze;       // m: within this distance of the waypoint the aim stops following it
        float realign;      // rad: a larger heading error while driving stops and rotates again
        float look;         // s: stopped after every ROTATE before DRIVE
        heading_pi::Config heading;
    };

    // Axle command of one tick, for drive::set()
    struct Command
    {
        float v;     // m/s
        float a;     // m/s², the profile's acceleration for the feedforward
        float w;     // rad/s
        float alpha; // rad/s²
    };

    struct State
    {
        double xy[2 * kMaxWaypoints]; // m
        int32_t n = 0;
        int32_t wp = 0; // waypoint being executed
        Phase phase = kIdle;
        bool stopping = false; // ramped stop requested: the path ends once stopped
        bool realigning = false; // DRIVE braking to rotate again
        float speed = 0.0f;      // |v| or |ω| commanded last tick
        // DRIVE: direction to the waypoint (frozen within config.freeze) and its heading
        double ux = 1.0, uy = 0.0, aim = 0.0;
        bool frozen = false;
        heading_pi::State heading;
        // ROTATE: absolute (not wrapped) target heading and direction (+1 CCW)
        double turn_target = 0.0;
        float turn_dir = 1.0f;
        float look_left = 0.0f; // LOOK: s still to wait
    };

    // Wraps an angle to [−π, π].
    double wrap(double angle);

    // Starts a path of n waypoints (x, y in mm, 1 ≤ n ≤ kMaxWaypoints) from pose p, with the
    // robot stopped. Waypoints already within config.steer_stop count as reached, so the phase
    // can be kArrived at once.
    void start(State &s, const Config &c, const int32_t *xy_mm, int32_t n, const odometry::State &p);

    // Ramped stop: the path ends (kIdle) once the robot has stopped.
    void stop(State &s);

    // Ends the path at once (emergency, encoder guard, heartbeat); the caller coasts or brakes.
    void abort(State &s);

    // True while the robot follows the path (ROTATE, LOOK or DRIVE).
    bool active(const State &s);

    // One tick from the pose p, stopped = both wheels without a count (drive::stopped()), dt the
    // measured tick (s). Stops at every waypoint, rotates toward the next and looks before
    // driving; after the last one the phase is kArrived. Returns the zero command once the path
    // has ended.
    Command tick(State &s, const Config &c, const odometry::State &p, bool stopped, float dt);
}
