#pragma once

#include <Arduino.h>

#include "../odometry/odometry.h"

namespace pose
{
    // Tick side, right after wheel_speed::update(): integrates the count deltas since the
    // previous tick. The pose starts at (0, 0, 0) at boot.
    void update();
    
    // Tick side (reset_pose): sets the axle pose (m, m, rad). The counts are not touched, so
    // the next update integrates its delta from this pose.
    void set(double x, double y, double theta);
    
    // Axle pose (m, m, rad not wrapped).
    const odometry::State &get();
}
