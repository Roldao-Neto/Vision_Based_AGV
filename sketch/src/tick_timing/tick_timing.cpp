#include <Arduino.h>
#include "tick_timing.h"
#include "../config/config.h"

using namespace config;

namespace tick_timing
{
    
    constexpr uint32_t kHookReportUs = 3000;
    
    static uint32_t next_tick_us;
    static uint32_t overrun_count;
    static uint32_t loop_end_us;
    static Window window;
    
    void begin()
    {
        next_tick_us = micros() + kTickPeriodUs;
        loop_end_us = micros();
    }
    
    void loop_started(uint32_t now_us)
    {
        const uint32_t hook_us = now_us - loop_end_us;
        window.hook_max_us = max(window.hook_max_us, hook_us);
        if (hook_us > kHookReportUs) {
            Bridge.notify("hook", millis(), hook_us);
        }
    }
    
    bool due(uint32_t now_us)
    {
        const int32_t late = (int32_t)(now_us - next_tick_us);
        if (late < 0) {
            return false;
        }
        if (late > (int32_t)kTickPeriodUs) {
            // More than one period behind: resync instead of running catch-up ticks
            // with a near-zero dt, and count it.
            overrun_count++;
            next_tick_us = now_us + kTickPeriodUs;
        } else {
            next_tick_us += kTickPeriodUs;
        }
        window.late_max_us = max(window.late_max_us, (uint32_t)late);
        return true;
    }
    
    void tick_ended(uint32_t start_us)
    {
        window.exec_max_us = max(window.exec_max_us, micros() - start_us);
    }
    
    void note_dt(uint32_t dt_us)
    {
        if (window.dt_min_us == 0 || dt_us < window.dt_min_us) {
            window.dt_min_us = dt_us;
        }
        window.dt_max_us = max(window.dt_max_us, dt_us);
    }
    
    void loop_ended(uint32_t now_us)
    {
        loop_end_us = now_us;
    }
    
    Window take_window()
    {
        const Window w = window;
        window = Window{};
        return w;
    }
    
    uint32_t overruns()
    {
        return overrun_count;
    }
}
