// Constants shared by the modules: pins, tick period, path and arena limits.
#pragma once

#include <Arduino.h>
#include "../encoder_guard/encoder_guard.h"
#include "../heading_pi/heading_pi.h"
#include "../odometry/odometry.h"
#include "../wheel_pi/wheel_pi.h"

namespace config
{
    enum Wheel { kLeft = 0, kRight = 1 };

    constexpr uint32_t kPwmHz = 20000;

    // TB6612 pins (wiring: docs/diagrama-ligacoes.svg)
    constexpr int kLeftPwm = D6;
    constexpr int kLeftIn1 = D7;
    constexpr int kLeftIn2 = D8;
    constexpr int kRightPwm = D9;
    constexpr int kRightIn1 = D10;
    constexpr int kRightIn2 = D11;

    // Encoders, x4 quadrature (A and B on interrupts)
    constexpr int kLeftEncA = D2;  // PB3
    constexpr int kLeftEncB = D4;  // PA12
    constexpr int kRightEncA = D3; // PB0
    constexpr int kRightEncB = D5; // PA11

    // Right motor reversed: "mirrored" -> Measured to be sure which one was the "default"
    constexpr bool kLeftMotorReversed = false;
    constexpr bool kRightMotorReversed = true;
    constexpr bool kLeftEncReversed = false;
    constexpr bool kRightEncReversed = true;

    // Paths: 1 to 32 absolute axle waypoints in integer mm
    constexpr int kMaxWaypoints = 32;
    constexpr int32_t kArenaXMm = 2000;
    constexpr int32_t kArenaYMm = 1500;

    constexpr float kCountsPerRev = 1319.75f; // mean of 3 count-mode runs of 10 turns samples
    constexpr float kWheelDiameterM = 0.0675f;

    // Odometry: m per count per wheel and track b, nominal until the Day 2 bench calibration
    constexpr double kMetersPerCountNominal = 3.14159265358979 * (double)kWheelDiameterM / (double)kCountsPerRev;
    constexpr double kTrackM = 0.217;
    constexpr odometry::Config kOdometry = {
        {kMetersPerCountNominal, kMetersPerCountNominal},
        kTrackM
    };

    // Control tick
    constexpr uint32_t kTickPeriodUs = 20000;
    constexpr uint32_t kReportEveryTicks = 25; // status every 500 ms

    // Encoder guard (closed loop): |duty| >= 20 % for 10 ticks (200 ms) without a count ends the mode at once, coasting
    constexpr encoder_guard::Config kEncoderGuard = {0.2f, 10};

    constexpr float kSpeedTcl = 0.1f;         // s, closed-loop time constant
    constexpr float kSpeedMaxDuty = 0.5f;     // closed-loop duty limit
    constexpr float kSpeedMinMps = 0.005f;    // below it the w coasts ("a few mm/s")
    constexpr float kStopDecelMps2 = 0.5f;    // every planned stop
    constexpr float kAccelMps2 = 0.5f;        // speed ramps of umbmark

    // K in counts/s per unit duty, tau in s, pwm0 = start of sustained motion on the ramp.
    constexpr wheel_pi::Model kLeftFwd = {7160.4f, 0.15362f, 0.074f};
    constexpr wheel_pi::Model kLeftBwd = {6668.3f, 0.14667f, 0.088f};
    constexpr wheel_pi::Model kRightFwd = {7271.4f, 0.10906f, 0.069f};
    constexpr wheel_pi::Model kRightBwd = {7509.1f, 0.14285f, 0.072f};

    // v_min in counts/s with each wheel's own m/count
    constexpr wheel_pi::Config kLeftPi = {
        kLeftFwd,
        kLeftBwd,
        kSpeedTcl,
        kSpeedMaxDuty,
        (float)((double)kSpeedMinMps / kOdometry.m_per_count[kLeft])
    };

    constexpr wheel_pi::Config kRightPi = {
        kRightFwd,
        kRightBwd,
        kSpeedTcl, 
        kSpeedMaxDuty,
        (float)((double)kSpeedMinMps / kOdometry.m_per_count[kRight])
    };

    // Heading PI for driving straight (Day 2, docs/logs/day2-firmware.md, item 2): Kp 1/s, Ti s,
    // Kd 0, steering limit rad/s
    constexpr heading_pi::Config kHeadingPi = {2.3f, 1.0f, 0.5f};

    // Ends of the moving modes
    constexpr float kSteerStopM = 0.015f;              // below it, steering holds and v only ramps down
    constexpr float kHeadingStopRad = 0.05235988f;     // 3°, the same for the rotations
    constexpr uint32_t kStoppedTicks = 2;              // ticks without a count on either wheel = stopped
    constexpr float kLegOvershootM = 0.1f;             // past a leg's end by this much: ramped stop

    // In-place turns: up to 90°/s at α = 2a/b, so each wheel also accelerates and brakes at a
    constexpr float kTurnMaxRadS = 1.5707963f;
    constexpr float kTurnAccelRadS2 = (float)(2.0 * (double)kStopDecelMps2 / kTrackM);
}
