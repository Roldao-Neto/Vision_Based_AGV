#pragma once

namespace heading_pi
{
    struct Config
    {
        float kp;    // rad/s per rad of heading error
        float ti;    // s, integral time
        float w_max; // rad/s, limit of the steering correction, both signs
    };

    struct State
    {
        float integ = 0.0f; // rad/s
    };

    void reset(State &s);

    // Wraps an angle to (−π, π].
    float wrap(float angle);

    // One tick: e = wrapped target − θ (rad), dt the measured tick (s). Returns ω in
    // [−w_max, w_max]. Conditional integration: while ω is clamped, the integral only moves
    // when the error pulls ω back from the limit.
    float update(State &s, const Config &c, float e, float dt);
}
