#pragma once

#include <Arduino.h>

#include "../config/config.h"

namespace drive
{
    using config::Wheel;
    
    // At the start of a closed-loop mode: resets both wheel PIs and encoder guards.
    void begin();
    
    // Every tick of a closed-loop mode, before set(): feeds the encoder guard with the duty
    // applied since the previous tick and the tick's counts, and counts the ticks without a
    // count on either wheel. True once the guard has tripped.
    bool observe();
    
    // One tick: axle speed v (m/s) and acceleration a (m/s²) from the profile, turn rate w
    // (rad/s) and angular acceleration alpha (rad/s²); dt the measured tick (s). Each wheel gets
    // v ∓ w·b/2 (and a ∓ alpha·b/2), converted to counts/s with that wheel's m/count.
    void set(float v, float a, float w, float alpha, float dt);
    
    // Both wheels without a count for config::kStoppedTicks ticks.
    bool stopped();
    
    // Duty applied by the last set() (0 after coast()).
    float duty(Wheel wheel);
    
    // Both wheels coast (ignored while the emergency holds the brake).
    void coast();
}
