#include <Arduino.h>

#include "wheel_speed.h"

#include "../encoders/encoders.h"

namespace wheel_speed
{    
    static bool have_sample;
    static uint32_t last_us;
    static int32_t last_count[2];
    static float speeds[2];
    static uint32_t last_dt_us;
    
    void update()
    {
        const uint32_t now_us = micros();
        int32_t count[2];
        for (int w = 0; w < 2; w++) {
            count[w] = encoders::count((Wheel)w);
        }
    
        if (have_sample) {
            last_dt_us = now_us - last_us;
            const float dt_s = (float)last_dt_us * 1e-6f;
            for (int w = 0; w < 2; w++) {
                speeds[w] = (float)(count[w] - last_count[w]) / dt_s;
            }
        }
        have_sample = true;
        last_us = now_us;
        for (int w = 0; w < 2; w++) {
            last_count[w] = count[w];
        }
    }
    
    float speed(Wheel wheel)
    {
        return speeds[wheel];
    }
    
    uint32_t dt_us()
    {
        return last_dt_us;
    }
    
    int32_t count(Wheel wheel)
    {
        return last_count[wheel];
    }

}
