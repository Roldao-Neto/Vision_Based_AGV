#include <Arduino.h>

#include "drive.h"

#include "../encoder_guard/encoder_guard.h"
#include "../motor_driver/motor_driver.h"
#include "../wheel_pi/wheel_pi.h"
#include "../wheel_speed/wheel_speed.h"

namespace drive
{
    static wheel_pi::State pi_state[2];
    static encoder_guard::State guard_state[2];
    static const wheel_pi::Config *const pi_config[2] = {&config::kLeftPi, &config::kRightPi};
    static float duties[2];
    static int32_t last_count[2];
    static uint32_t still_ticks;
    
    void begin()
    {
        for (int w = 0; w < 2; w++) {
            const int32_t count = wheel_speed::count((Wheel)w);
            wheel_pi::reset(pi_state[w]);
            encoder_guard::reset(guard_state[w], count);
            duties[w] = 0.0f;
            last_count[w] = count;
        }
        still_ticks = 0;
    }
    
    bool observe()
    {
        bool tripped = false;
        bool moved = false;
        for (int w = 0; w < 2; w++) {
            const int32_t count = wheel_speed::count((Wheel)w);
            tripped |= encoder_guard::update(
                guard_state[w], config::kEncoderGuard, duties[w], count
            );
            moved |= count != last_count[w];
            last_count[w] = count;
        }
        still_ticks = moved ? 0 : still_ticks + 1;
        return tripped;
    }
    
    void set(float v, float a, float w, float alpha, float dt)
    {
        const float half_track = 0.5f * (float)config::kOdometry.track_m;
        const float v_wheel[2] = {v - w * half_track, v + w * half_track};
        const float a_wheel[2] = {a - alpha * half_track, a + alpha * half_track};
        for (int i = 0; i < 2; i++) {
            const float counts_per_m = (float)(1.0 / config::kOdometry.m_per_count[i]);
            duties[i] = wheel_pi::update(
                pi_state[i], *pi_config[i], v_wheel[i] * counts_per_m, a_wheel[i] * counts_per_m, wheel_speed::speed((Wheel)i), dt
            );
        }
        motor_driver::set_duty(config::kLeft, duties[config::kLeft]);
        motor_driver::set_duty(config::kRight, duties[config::kRight]);
    }
    
    bool stopped()
    {
        return still_ticks >= config::kStoppedTicks;
    }
    
    float duty(Wheel wheel)
    {
        return duties[wheel];
    }
    
    void coast()
    {
        duties[config::kLeft] = duties[config::kRight] = 0.0f;
        motor_driver::set_duty(config::kLeft, 0.0f);
        motor_driver::set_duty(config::kRight, 0.0f);
    }
}
