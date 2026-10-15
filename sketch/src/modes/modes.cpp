#include <Arduino.h>
#include <math.h>
#include <stdlib.h>
#include "modes.h"
#include "../bridge_stack/bridge_stack.h"
#include "../config/config.h"
#include "../encoder_guard/encoder_guard.h"
#include "../encoders/encoders.h"
#include "../motor_driver/motor_driver.h"
#include "../samples/samples.h"
#include "../wheel_pi/wheel_pi.h"
#include "../wheel_speed/wheel_speed.h"

namespace modes
{
    static int32_t mode = kIdle;
    
    // Encoder state when the current mode started
    static uint32_t start_ms;
    static int32_t count_start[2];
    static uint32_t errors_start[2];
    
    // Recorded runs
    static int32_t record_id;
    static int32_t limit_counts;
    
    // speed
    static int32_t speed_mm_s, speed_accel_mm_s2;
    static float speed_target;
    static float speed_accel;
    static uint32_t speed_time_ms;
    static bool speed_stopping;
    static int32_t speed_stop_reason;
    static float speed_ref;
    static float speed_duty[2];
    static wheel_pi::State pi_state[2];
    static encoder_guard::State guard_state[2];
    static const wheel_pi::Config *const pi_config[2] = {&config::kLeftPi, &config::kRightPi};
    static bool pending;
    static int32_t pending_code;
    
    static bool all_zero(const int32_t params[kParams])
    {
        for (int i = 0; i < kParams; i++) {
            if (params[i] != 0) {
                return false;
            }
        }
        return true;
    }
    
    static bool valid_speed(const int32_t params[kParams])
    {
        const int32_t v = params[0], accel = params[1], time_ms = params[2], distance = params[3];
        return v != 0 && v >= -kSpeedMaxMmS && v <= kSpeedMaxMmS &&
               (accel == 0 || (accel >= kSpeedMinAccelMmS2 && accel <= kSpeedMaxAccelMmS2)) && time_ms >= 1 &&
               time_ms <= kSpeedMaxTimeMs && distance >= 1 && distance <= kSpeedMaxDistanceMm;
    }
    
    bool valid(int32_t code, const int32_t params[kParams])
    {
        switch (code)
        {
            case kIdle:
                return all_zero(params);
            case kSpeed:
                return valid_speed(params) && !samples::busy();
            default:
                return false;
            }
    }
    
    static void take_encoder_start()
    {
        start_ms = millis();
        for (int w = 0; w < 2; w++) {
            count_start[w] = encoders::count((config::Wheel)w);
            errors_start[w] = encoders::errors((config::Wheel)w);
        }
    }
    
    static int32_t counts_since_start(int w)
    {
        return encoders::count((config::Wheel)w) - count_start[w];
    }
    
    static uint32_t errors_since_start(int w)
    {
        return encoders::errors((config::Wheel)w) - errors_start[w];
    }
    
    static int32_t distance_to_counts(int32_t mm)
    {
        const float mm_per_count = (float)PI * config::kWheelDiameterM * 1000.0f / config::kCountsPerRev;
        return (int32_t)ceilf((float)mm / mm_per_count);
    }
    
    static bool distance_reached()
    {
        return max(abs(counts_since_start(config::kLeft)), abs(counts_since_start(config::kRight))) >= limit_counts;
    }
    
    static void set_both(float duty_l, float duty_r)
    {
        motor_driver::set_duty(config::kLeft, duty_l);
        motor_driver::set_duty(config::kRight, duty_r);
    }
    
    static void start_speed(const int32_t params[kParams])
    {
        take_encoder_start();
        speed_mm_s = params[0];
        speed_accel_mm_s2 = params[1];
        speed_target = (float)speed_mm_s * 0.001f * config::kCountsPerM;
        speed_accel = (float)speed_accel_mm_s2 * 0.001f * config::kCountsPerM;
        speed_time_ms = (uint32_t)params[2];
        limit_counts = distance_to_counts(params[3]);
        speed_stopping = false;
        speed_ref = 0.0f;
        speed_duty[config::kLeft] = speed_duty[config::kRight] = 0.0f;
        wheel_pi::reset(pi_state[config::kLeft]);
        wheel_pi::reset(pi_state[config::kRight]);
        encoder_guard::reset(guard_state[config::kLeft], encoders::count(config::kLeft));
        encoder_guard::reset(guard_state[config::kRight], encoders::count(config::kRight));
        pending = false;
        record_id++;
        samples::start("speed_samples", record_id, 6, 10);
    }
    
    // The first call sets the reason; time, distance or a command then only wait for the stop.
    static void begin_speed_stop(int32_t reason)
    {
        if (!speed_stopping) {
            speed_stopping = true;
            speed_stop_reason = reason;
        }
    }
    
    // A recorded run ends by coasting both wheels (ignored while the emergency holds the
    // brake). The samples stop first, so they cover the driven part.
    static void stop_recorded()
    {
        samples::stop();
        set_both(0.0f, 0.0f);
    }
    
    static void end_speed(int32_t reason)
    {
        stop_recorded();
        const uint32_t now_ms = millis();
        Bridge.notify(
            "speed_end",
            now_ms,
            record_id,
            now_ms - start_ms,
            reason, speed_mm_s,
            speed_accel_mm_s2,
            counts_since_start(config::kLeft),
            counts_since_start(config::kRight),
            errors_since_start(config::kLeft),
            errors_since_start(config::kRight),
            samples::count()
        );
    }
    
    static void end_current(int32_t reason)
    {
        if (mode == kSpeed) {
            end_speed(reason);
        }
        mode = kIdle;
    }
    
    static void start(int32_t code, const int32_t params[kParams])
    {
        mode = code;
        if (mode == kSpeed) {
            start_speed(params);
        }
    }
    
    void request(int32_t code, const int32_t params[kParams])
    {
        if (mode == kSpeed) {
            begin_speed_stop(kEndCommand);
            pending = true;
            pending_code = code;
            return;
        }
        end_current(kEndCommand);
        start(code, params);
    }
    
    static void tick_speed()
    {
        const uint32_t elapsed_us = samples::us_since_start();
        
        const int32_t values[6] = {
            (int32_t)elapsed_us,
            (int32_t)lroundf(speed_ref),
            counts_since_start(config::kLeft),
            counts_since_start(config::kRight),
            (int32_t)lroundf(speed_duty[config::kLeft] * 10000.0f),
            (int32_t)lroundf(speed_duty[config::kRight] * 10000.0f)
        };
        
        samples::add(values);
        
        bool encoder_fault = false;
        for (int w = 0; w < 2; w++) {
            encoder_fault |= encoder_guard::update(
                                guard_state[w], 
                                config::kEncoderGuard, 
                                speed_duty[w], 
                                encoders::count((config::Wheel)w)
                            );
        }
        if (encoder_fault) {
            pending = false;
            end_current(kEndEncoder);
            return;
        }
        if (!speed_stopping) {
            if (elapsed_us / 1000 >= speed_time_ms) {
                begin_speed_stop(kEndTime);
            } else if (distance_reached()) {
                begin_speed_stop(kEndDistance);
            }
        }
    
        const uint32_t dt_us = wheel_speed::dt_us();
        const float dt = dt_us != 0 ? (float)dt_us * 1e-6f : (float)config::kTickPeriodUs * 1e-6f;
        float a_ref;
        if (speed_stopping) {
            const float decel = config::kStopDecelMps2 * config::kCountsPerM;
            if (fabsf(speed_ref) <= decel * dt) {
                end_current(speed_stop_reason);
                if (pending) {
                    pending = false;
                    const int32_t none[kParams] = {0, 0, 0, 0};
                    start(pending_code, none);
                }
                return;
            }
            a_ref = speed_ref > 0.0f ? -decel : decel;
            speed_ref += a_ref * dt;
        } else if (speed_accel == 0.0f) {
            speed_ref = speed_target;
            a_ref = 0.0f;
        } else {
            const float v = speed_accel * (float)elapsed_us * 1e-6f;
            const float v_max = fabsf(speed_target);
            a_ref = v < v_max ? copysignf(speed_accel, speed_target) : 0.0f;
            speed_ref = copysignf(fminf(v, v_max), speed_target);
        }
        for (int w = 0; w < 2; w++) {
            speed_duty[w] =
                wheel_pi::update(pi_state[w], *pi_config[w], speed_ref, a_ref, wheel_speed::speed((config::Wheel)w), dt);
        }
        set_both(speed_duty[config::kLeft], speed_duty[config::kRight]);
    }
    
    void tick()
    {
        if (mode != kSpeed) {
            return;
        }
        if (bridge_stack::emergency()) {
            pending = false; // the motors are locked; stay idle
            end_current(kEndEmergency);
            return;
        }
        tick_speed();
    }
    
    int32_t current()
    {
        return mode;
    }
}
