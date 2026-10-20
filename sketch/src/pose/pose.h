#pragma once

#include <Arduino.h>

#include "../odometry/odometry.h"

namespace pose
{
    // Tick side, right after wheel_speed::update(): integrates the count deltas since the
    // previous tick. The pose starts at (0, 0, 0) at boot.
    void update();
    
    // Axle pose (m, m, rad not wrapped).
    const odometry::State &get();
}
