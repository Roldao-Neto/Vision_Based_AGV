#pragma once

#include <stdint.h>

namespace encoder_guard
{
    struct Config 
    {
        float duty_min;  // magnitude of the duty that must produce counts
        uint32_t ticks;  // consecutive ticks without a count that trip the guard
    };
    
    struct State
    {
        int32_t last_count = 0;
        uint32_t stalled_ticks = 0;
    };
    
    // At the start of a mode, with the wheel's current count.
    void reset(State &s, int32_t count);
    
    // Once per tick: duty applied since the previous tick and the wheel's count now. Returns
    // true once the guard has tripped (and keeps returning true until reset).
    bool update(State &s, const Config &c, float duty, int32_t count);
}
