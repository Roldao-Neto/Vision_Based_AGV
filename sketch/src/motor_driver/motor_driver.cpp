#include <Arduino.h>
#include <errno.h>
#include <math.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/pwm.h>
#include "motor_driver.h"
#include "../config/config.h"

using namespace config;

namespace motor_driver
{    
    struct Channel {
        int pwm_pin;
        int in1;
        int in2;
        bool reversed;
        const struct device *pwm_dev;
        uint32_t pwm_channel; // devicetree channel, see the board overlay's zephyr,user pwms
    };
    
    // D6 = TIM3_CH4 (pwm3 channel 4), D9 = TIM4_CH3 (pwm4 channel 3).
    static const Channel kChannels[2] = {
        {kLeftPwm , kLeftIn1 , kLeftIn2 , kLeftMotorReversed , DEVICE_DT_GET(DT_NODELABEL(pwm3)), 4},
        {kRightPwm, kRightIn1, kRightIn2, kRightMotorReversed, DEVICE_DT_GET(DT_NODELABEL(pwm4)), 3},
    };
    
    static uint32_t period_cycles; // timer counts per PWM period, the same on both timers
    static uint32_t frequency_hz;
    static int32_t first_error;
    
    static bool ready;
    static bool locked;
    
    static void note_error(int err)
    {
        if (err < 0 && first_error == 0) {
            first_error = err;
        }
    }
    
    static void set_pulse(const Channel &ch, uint32_t pulse_cycles)
    {
        note_error(pwm_set_cycles(ch.pwm_dev, ch.pwm_channel, period_cycles, pulse_cycles, PWM_POLARITY_NORMAL));
    }
    
    int begin()
    {
        for (const Channel &ch : kChannels)
        {
            pinMode(ch.in1, OUTPUT);
            pinMode(ch.in2, OUTPUT);
            digitalWrite(ch.in1, LOW);
            digitalWrite(ch.in2, LOW);
        }
    
        for (const Channel &ch : kChannels)
        {
            analogWrite(ch.pwm_pin, 0);
            
            if (!device_is_ready(ch.pwm_dev))
            {
                note_error(-ENODEV);
                continue;
            }
            
            uint64_t cycles_per_sec = 0;
            const int err = pwm_get_cycles_per_sec(ch.pwm_dev, ch.pwm_channel, &cycles_per_sec);
            note_error(err);
            if (err < 0) 
            {
                continue;
            }
            
            const uint32_t period = (uint32_t)(cycles_per_sec / kPwmHz);
            
            if (period == 0 || (period_cycles != 0 && period != period_cycles))
            {
                note_error(-EINVAL);
                continue;
            }
            
            period_cycles = period;
            frequency_hz = (uint32_t)(cycles_per_sec / period);
        }
        
        if (first_error != 0)
        {
            frequency_hz = 0;
            return first_error;
        }
    
        for (const Channel &ch : kChannels) 
        {
            set_pulse(ch, period_cycles);
        }
        
        if (first_error != 0) 
        {
            frequency_hz = 0;
            return first_error;
        }
        
        ready = true;
        return 0;
    }
    
    void set_duty(Wheel wheel, float duty)
    {
        if (!ready || locked) {
            return;
        }
        const Channel &ch = kChannels[wheel];
        if (duty == 0.0f) {
            coast(wheel);
            return;
        }
        const float magnitude = min(fabsf(duty), 1.0f);
        const uint32_t pulse = (uint32_t)(magnitude * (float)period_cycles + 0.5f);
        const bool forward = (duty > 0.0f) != ch.reversed;
        const int on_pin = forward ? ch.in1 : ch.in2;
        const int off_pin = forward ? ch.in2 : ch.in1;
    
        // Pulse first, then release the other direction, then select this one: no
        // transition passes through the opposite direction.
        set_pulse(ch, pulse);
        digitalWrite(off_pin, LOW);
        digitalWrite(on_pin, HIGH);
    }
    
    void coast(Wheel wheel)
    {
        if (!ready || locked) {
            return;
        }
        const Channel &ch = kChannels[wheel];
        digitalWrite(ch.in1, LOW);
        digitalWrite(ch.in2, LOW);
        set_pulse(ch, period_cycles);
    }
    
    void brake(Wheel wheel)
    {
        if (!ready || locked) {
            return;
        }
        const Channel &ch = kChannels[wheel];
        digitalWrite(ch.in1, HIGH);
        digitalWrite(ch.in2, HIGH);
        set_pulse(ch, 0);
    }
    
    void lock_brake()
    {
        // IN1 = IN2 = H brakes whatever the PWM does, so this works even if begin() failed.
        locked = true;
        for (const Channel &ch : kChannels) {
            digitalWrite(ch.in1, HIGH);
            digitalWrite(ch.in2, HIGH);
        }
    }

    //get
    uint32_t pwm_hz()
    {
        return frequency_hz;
    }
    
    //get
    int32_t pwm_error()
    {
        return first_error;
    }

}
