#pragma once

namespace motion_profile
{
    struct Step
    {
        float speed; // magnitude, >= 0
        float accel; // the acceleration this step commands (+accel, 0 or -accel), for the
                     // wheel feedforward; never a derivative of the speed
    };

    // One tick of the trapezoidal profile on the remaining distance or angle, in magnitudes: speed = min(max_speed, prev + accel·dt, sqrt(2·accel·remaining)).
    // Inside stop_band (remaining < stop_band, including an overshoot, remaining < 0) the
    // speed only ramps down, max(0, prev − accel·dt), so it never drops to zero in one tick.
    // Linear: m, m/s, m/s². Angular: rad, rad/s, rad/s².
    Step next(float prev, float remaining, float max_speed, float accel, float dt, float stop_band);
}
