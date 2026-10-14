// TB6612 driver: signed duty per wheel at 20 kHz, coast and short brake.

// Main thread only: setup() and the tick.

#pragma once

#include <Arduino.h>
#include "../config/config.h"

namespace motor_driver 
{
    using config::Wheel;
    
    // Called once from setup(): both wheels coast, analogWrite(pin, 0) initializes each PWM timer and switches the pin to it, then the PWM goes to 20 kHz with pwm_set_cycles (a later analogWrite would bring back the devicetree's 500 Hz). Returns 0 or the first negative errno; after an error every command is ignored.
    int begin();
    
    // Signed duty in [-1, 1] (clamped); positive drives the wheel forward, 0 coasts.
    void set_duty(Wheel wheel, float duty);
    
    // Outputs off (high impedance).
    void coast(Wheel wheel);
    
    // Short brake (both outputs low).
    void brake(Wheel wheel);
    
    // Emergencies: short brake on both wheels, then ignore every command until restart.
    void lock_brake();
    
    // PWM frequency in Hz from the timer clock, 0 before begin() or after its error.
    uint32_t pwm_hz();
    
    // First negative return of a PWM call since boot, 0 if none.
    int32_t pwm_error();
}
