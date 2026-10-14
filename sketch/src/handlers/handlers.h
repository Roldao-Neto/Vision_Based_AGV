#pragma once

#include <Arduino.h>
#include <zephyr/kernel.h>

namespace handlers
{ 
    // Called once from setup(), after Bridge.begin(): remembers the main thread (setup()
    // runs on it) and registers ping, hb, set_path and mode with provide_safe.
    void begin();
    
    // The bridge thread, or nullptr until a handler has run off the main thread.
    k_tid_t bridge_thread();
    
    // k_uptime_get_32() of the last hb, or 0 before the first.
    uint32_t last_hb_ms();
}
