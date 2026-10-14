#pragma once

#include <Arduino.h>

namespace modes {
    
    enum Mode : int32_t {
        kIdle = 0,
        kCount = 1,
        kStep = 2,
        kRamp = 3,
        kSpeed = 4,
    };
    
    enum EndReason : int32_t {
        kEndTime = 1,      // time limit
        kEndDistance = 2,  // distance limit
        kEndCommand = 3,   // replaced by another mode command
        kEndEmergency = 4, // bridge stack emergency
        kEndEncoder = 5,   // encoder guard: a wheel driven hard without counting (closed loop)
    };
    
    constexpr int kParams = 4;
    
    // Firmware caps, whatever Python sends
    constexpr int32_t kMaxDutyPermille = 300;
    constexpr int32_t kStepMaxTimeMs = 1000;
    constexpr int32_t kStepMaxDistanceMm = 500;
    constexpr int32_t kRampMinRate = 10;  // thousandths per second
    constexpr int32_t kRampMaxRate = 200;
    constexpr int32_t kRampMaxTimeMs = 6000;
    constexpr int32_t kRampMaxDistanceMm = 200;
    constexpr int32_t kSpeedMaxMmS = 300;
    constexpr int32_t kSpeedMinAccelMmS2 = 100;
    constexpr int32_t kSpeedMaxAccelMmS2 = 500;
    constexpr int32_t kSpeedMaxTimeMs = 4500;
    constexpr int32_t kSpeedMaxDistanceMm = 1000;
    
    // Handler side, any thread: true if code is a mode and its params are allowed.
    bool valid(int32_t code, const int32_t params[kParams]);
    
    // Tick side: ends the current mode, then starts code (already validated).
    void request(int32_t code, const int32_t params[kParams]);
    
    // Tick side, once per tick after the commands: runs the current mode and checks its
    // limits.
    void tick();
    
    int32_t current();
}
