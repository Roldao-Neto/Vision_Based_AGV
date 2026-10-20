#include <Arduino.h>

#include "pose.h"

#include "../config/config.h"
#include "../wheel_speed/wheel_speed.h"

namespace pose
{
    static odometry::State state;
    static bool have_counts;
    static int32_t last_count[2];
    
    void update()
    {
        int32_t count[2];
        for (int w = 0; w < 2; w++) {
            count[w] = wheel_speed::count((config::Wheel)w);
        }
        if (have_counts) {
            odometry::update(
                state,
                config::kOdometry,
                count[config::kLeft] - last_count[config::kLeft],
                count[config::kRight] - last_count[config::kRight]);
        }
        have_counts = true;
        last_count[config::kLeft] = count[config::kLeft];
        last_count[config::kRight] = count[config::kRight];
    }
    
    const odometry::State &get()
    {
        return state;
    }
}
