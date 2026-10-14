#pragma once

namespace wheel_pi {

    struct Model
    {
        float k;    // counts/s per unit duty
        float tau;  // s
        float pwm0; // duty, static friction offset
    };

    struct Config
    {
        Model fwd;
        Model bwd;
        float t_cl;  // s, closed-loop time constant
        float u_max; // duty limit, both signs
        float v_min; // counts/s, below it the wheel coasts
    };

    struct State
    {
        float integ = 0.0f;      // duty
        float v_ref_prev = 0.0f; // counts/s, the reference of the previous update
    };

    void reset(State &s);

    // One tick: v_ref (counts/s) and a_ref (counts/s²) from the profile, v_meas the mean
    // speed over the last tick (counts/s), dt the measured tick (s). Returns the duty in
    // [-u_max, u_max].
    float update(State &s, const Config &c, float v_ref, float a_ref, float v_meas, float dt);
}
