#pragma once

#include <Arduino.h>

#include "../config/config.h"

namespace wheel_speed
{
    using config::Wheel;
    
    // Called once per tick, before anything uses the speeds. The first call after boot
    // only takes the reference sample.
    void update();
    
    // Counts per second at the last update, forward positive.
    float speed(Wheel wheel);
    
    // Time between the last two samples, µs (0 before the second update).
    uint32_t dt_us();
}
