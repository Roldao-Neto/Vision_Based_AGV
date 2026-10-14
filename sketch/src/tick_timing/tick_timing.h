#pragma once

#include <Arduino.h>

namespace tick_timing
{
    // Worst cases over a report window, in µs.
    struct Window {
        uint32_t late_max_us; // tick start after its slot on the grid
        uint32_t exec_max_us; // tick body
        uint32_t hook_max_us; // time outside loop()
        uint32_t dt_min_us;
        uint32_t dt_max_us;
    };
    
    // Called at the end of setup(): first tick one period from now.
    void begin();
    
    // Called at the start of loop(): measures the time outside loop().
    void loop_started(uint32_t now_us);
    
    // True if a tick is due at now_us; the grid then moves to the next slot and the
    // lateness goes into the window.
    bool due(uint32_t now_us);
    
    // Called at the end of a tick that started at start_us.
    void tick_ended(uint32_t start_us);
    
    // Called with each measured dt between speed samples.
    void note_dt(uint32_t dt_us);
    
    // Called at the end of loop().
    void loop_ended(uint32_t now_us);
    
    // Worst cases since the last call; starts a new window.
    Window take_window();
    
    // Ticks that started more than a period late, since boot.
    uint32_t overruns();
}
