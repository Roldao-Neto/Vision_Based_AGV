#include "encoder_guard.h"

namespace encoder_guard
{
    void reset(State &s, int32_t count)
    {
        s.last_count = count;
        s.stalled_ticks = 0;
    }
    
    bool update(State &s, const Config &c, float duty, int32_t count)
    {
        const bool driven = duty >= c.duty_min || duty <= -c.duty_min;
        if (driven && count == s.last_count) {
            if (s.stalled_ticks < c.ticks) {
                s.stalled_ticks++;
            }
        } else if (s.stalled_ticks < c.ticks) {
            s.stalled_ticks = 0;
        }
        s.last_count = count;
        return s.stalled_ticks >= c.ticks;
    }
}
