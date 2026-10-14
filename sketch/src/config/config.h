// Constants shared by the modules: pins, tick period, path and arena limits.
#pragma once

#include <Arduino.h>
#include "../encoder_guard/encoder_guard.h"
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
    constexpr float kCountsPerM = kCountsPerRev / (3.14159265f * kWheelDiameterM);

    // Control tick
    constexpr uint32_t kTickPeriodUs = 20000;
    constexpr uint32_t kReportEveryTicks = 25; // status every 500 ms

    // Encoder guard (closed loop): |duty| >= 20 % for 10 ticks (200 ms) without a count ends the mode at once, coasting
    constexpr encoder_guard::Config kEncoderGuard = {0.2f, 10};

    constexpr float kSpeedTcl = 0.1f;         // s, closed-loop time constant
    constexpr float kSpeedMaxDuty = 0.5f;     // closed-loop duty limit
    constexpr float kSpeedMinMps = 0.005f;    // below it the w coasts ("a few mm/s")
    constexpr float kStopDecelMps2 = 0.5f;    // every planned stop

    // K in counts/s per unit duty, tau in s, pwm0 = start of sustained motion on the ramp.
    constexpr wheel_pi::Model kLeftFwd = {7160.4f, 0.15362f, 0.074f};
    constexpr wheel_pi::Model kLeftBwd = {6668.3f, 0.14667f, 0.088f};
    constexpr wheel_pi::Model kRightFwd = {7271.4f, 0.10906f, 0.069f};
    constexpr wheel_pi::Model kRightBwd = {7509.1f, 0.14285f, 0.072f};

    constexpr wheel_pi::Config kLeftPi = {kLeftFwd, kLeftBwd, kSpeedTcl, kSpeedMaxDuty, kSpeedMinMps * kCountsPerM};
    constexpr wheel_pi::Config kRightPi = {kRightFwd, kRightBwd, kSpeedTcl, kSpeedMaxDuty, kSpeedMinMps * kCountsPerM};
}
