#pragma once

#include <Arduino.h>
#include <zephyr/kernel.h>      // k_tid_t

namespace bridge_stack
{
    // Tick side. Counts the untouched bytes of tid's stack from its bottom; nullptr (bridge
    // thread not identified yet) does nothing. Fewer than 512 untouched bytes latch the
    // emergency until restart and lock the motors in short brake.
    void scan(k_tid_t tid);

    // bytes used at the last scan
    uint32_t peak();

    // bytes still holding the pattern at the last scan
    uint32_t untouched();

    // Safe from any thread.
    bool emergency();

    // Tick side: sends emergency(t_ms, peak, untouched) once, the first time it is called
    // with the emergency latched.
    void report_emergency_once(uint32_t now_ms);
}
