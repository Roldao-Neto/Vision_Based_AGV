#pragma once

#include <Arduino.h>

namespace modes
{
    enum Mode : int32_t {
        kIdle = 0,
        // 1-3 were the Day 1 identification modes (count, step, ramp) and 4 the Day 1 wheel
        // PI test (speed, retired on Day 2), kept out of use so the earlier records keep their
        // meaning
        kStraight = 5,
        kUmbmark = 6,
    };

    enum EndReason : int32_t {
        kEndTime = 1,      // time limit
        kEndDistance = 2,  // overshoot guard: past the leg's end by config::kLegOvershootM
        kEndCommand = 3,   // replaced by another mode command
        kEndEmergency = 4, // bridge stack emergency
        kEndEncoder = 5,   // encoder guard: a wheel driven hard without counting (closed loop)
        kEndTarget = 6,    // reached its distance or angle target and stopped
    };

    constexpr int kParams = 4;

    // Firmware caps, whatever Python sends
    constexpr int32_t kMinMmS = 50;
    constexpr int32_t kMaxMmS = 300;
    constexpr int32_t kStraightMinAccelMmS2 = 100;
    constexpr int32_t kStraightMaxAccelMmS2 = 500;
    constexpr int32_t kStraightMaxTimeMs = 10000;
    constexpr int32_t kStraightMaxDistanceMm = 1600;
    constexpr int32_t kUmbmarkMinSideMm = 100;
    constexpr int32_t kUmbmarkMaxSideMm = 1000;
    constexpr int32_t kUmbmarkMaxTimeMs = 30000;
    
    // Handler side, any thread: true if code is a mode and its params are allowed.
    bool valid(int32_t code, const int32_t params[kParams]);

    // Tick side: ends the current mode, then starts code (already validated).
    void request(int32_t code, const int32_t params[kParams]);

    // Tick side, once per tick after the commands: runs the current mode and checks its
    // limits.
    void tick();

    int32_t current();
}
