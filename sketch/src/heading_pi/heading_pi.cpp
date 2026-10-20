#include "heading_pi.h"

#include <math.h>

namespace heading_pi
{
    static float sign(float x)
    {
        return x > 0.0f ? 1.0f : (x < 0.0f ? -1.0f : 0.0f);
    }

    void reset(State &s)
    {
        s.integ = 0.0f;
    }

    float wrap(float angle)
    {
        const float two_pi = 6.28318531f;
        float a = fmodf(angle, two_pi);
        if (a <= -3.14159265f) {
            a += two_pi;
        } else if (a > 3.14159265f) {
            a -= two_pi;
        }
        return a;
    }

    float update(State &s, const Config &c, float e, float dt)
    {
        const float w_raw = c.kp * e + s.integ;
        const float w = w_raw > c.w_max ? c.w_max : (w_raw < -c.w_max ? -c.w_max : w_raw);
        if (w == w_raw || sign(e) != sign(w_raw)) {
            s.integ += c.kp / c.ti * e * dt;
        }
        return w;
    }
}
