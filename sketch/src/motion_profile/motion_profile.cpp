#include "motion_profile.h"

#include <math.h>

namespace motion_profile
{
    Step next(float prev, float remaining, float max_speed, float accel, float dt, float stop_band)
    {
        if (remaining < stop_band) {
            const float speed = prev - accel * dt;
            return speed > 0.0f ? Step{speed, -accel} : Step{0.0f, prev > 0.0f ? -accel : 0.0f};
        }
        const float up = prev + accel * dt;
        const float down = sqrtf(2.0f * accel * remaining);
        if (down <= up && down <= max_speed) {
            // On the braking curve; at its first point the curve can sit above prev, which is
            // a hold, not a brake.
            return Step{down, down < prev ? -accel : 0.0f};
        }
        if (max_speed <= up) {
            return Step{max_speed, max_speed > prev ? accel : 0.0f};
        }
        return Step{up, accel};
    }
}
