#include <Arduino.h>
#include <zephyr/sys/atomic.h>
#include "encoders.h"

using namespace config;

namespace encoders
{
    struct Encoder 
    {
        int a_pin;
        int b_pin;
        int8_t sign;    // +1, or -1 when the wheel's encoder is reversed
        uint8_t state;  // (A << 1) | B at the last interrupt; only the handlers touch it -> 00, 01, 11, 10
        atomic_t count;
        atomic_t errors;
    };
    
    static Encoder encoders[2] = 
    {
        {kLeftEncA, kLeftEncB, (kLeftEncReversed ? (int8_t)-1 : (int8_t)1), 0, ATOMIC_INIT(0), ATOMIC_INIT(0)},
        {kRightEncA, kRightEncB, (kRightEncReversed ? (int8_t)-1 : (int8_t)1), 0, ATOMIC_INIT(0), ATOMIC_INIT(0)},
    };
    
    // Step for each (previous state << 2 | new state), states being (A << 1) | B -> "0bAB"
    // kInvalid marks both channels changed.
    constexpr int8_t kInvalid = 2;
    
    static const int8_t kStep[16] = {
        0, +1, -1, kInvalid,  // from 00
        -1, 0, kInvalid, +1,  // from 01
        +1, kInvalid, 0, -1,  // from 10
        kInvalid, -1, +1, 0,  // from 11
    };
    
    static uint8_t read_state(const Encoder &enc)
    {
        return (uint8_t)((digitalRead(enc.a_pin) == HIGH ? 2 : 0) | (digitalRead(enc.b_pin) == HIGH ? 1 : 0)); //bitwise or -> 0xab
    }
    
    static void update(Encoder &enc)
    {
        const uint8_t state = read_state(enc);
        const int8_t step = kStep[(enc.state << 2) | state];
        enc.state = state;
        if (step == kInvalid) {
            atomic_inc(&enc.errors);
        } else if (step != 0) {
            atomic_add(&enc.count, step * enc.sign);
        }
    }
    
    static void on_left_edge()
    {
        update(encoders[kLeft]);
    }
    
    static void on_right_edge()
    {
        update(encoders[kRight]);
    }
    
    void begin()
    {
        for (Encoder &enc : encoders) {
            pinMode(enc.a_pin, INPUT_PULLUP);
            pinMode(enc.b_pin, INPUT_PULLUP);
            enc.state = read_state(enc);
        }
        const Encoder &left = encoders[kLeft];
        const Encoder &right = encoders[kRight];
        attachInterrupt(digitalPinToInterrupt(left.a_pin), on_left_edge, CHANGE);
        attachInterrupt(digitalPinToInterrupt(left.b_pin), on_left_edge, CHANGE);
        attachInterrupt(digitalPinToInterrupt(right.a_pin), on_right_edge, CHANGE);
        attachInterrupt(digitalPinToInterrupt(right.b_pin), on_right_edge, CHANGE);
    }
    
    int32_t count(Wheel wheel)
    {
        return (int32_t)atomic_get(&encoders[wheel].count);
    }
    
    uint32_t errors(Wheel wheel)
    {
        return (uint32_t)atomic_get(&encoders[wheel].errors);
    }

}
