#include <Arduino.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include "bridge_stack.h"
#include "../motor_driver/motor_driver.h"

namespace bridge_stack
{
    
    constexpr uint8_t kStackFill = 0xAA;
    constexpr size_t kStackEmergencyBytes = 512;
    
    static atomic_t emergency_flag = ATOMIC_INIT(0);
    
    // Tick-only state
    static uint32_t stack_peak;
    static uint32_t stack_untouched;
    static bool emergency_reported;
    
    void scan(k_tid_t tid)
    {
        if (tid == nullptr) {
            return;
        }
        
        const uint8_t *bottom = (const uint8_t *)tid->stack_info.start;
        const size_t size = tid->stack_info.size;
        size_t n = 0;
        while (n < size && bottom[n] == kStackFill) {
            n++;
        }
        stack_untouched = n;
        stack_peak = size - n;
    
        if (n < kStackEmergencyBytes && !atomic_get(&emergency_flag)) {
            atomic_set(&emergency_flag, 1);
            motor_driver::lock_brake();
        }
    }
    
    uint32_t peak()
    {
        return stack_peak;
    }
    
    uint32_t untouched()
    {
        return stack_untouched;
    }
    
    bool emergency()
    {
        return atomic_get(&emergency_flag) != 0;
    }
    
    void report_emergency_once(uint32_t now_ms)
    {
        if (emergency() && !emergency_reported) {
            emergency_reported = true;
            Bridge.notify("emergency", now_ms, stack_peak, stack_untouched);
        }
    }
}
