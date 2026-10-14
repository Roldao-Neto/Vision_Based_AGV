// x4 quadrature encoders: every edge of A or B counts, forward positive.
//
// Each wheel has one interrupt handler on CHANGE for both of its pins. It reads A and B
// and steps a state table, so an edge whose level reads unchanged (a bounce) counts
// nothing and a jump of both channels between two interrupts (a missed edge) counts
// as an error instead of a guess. All EXTI lines have the same priority, so the
// handlers of one wheel never preempt each other.

#pragma once

#include <Arduino.h>

#include "../config/config.h"

namespace encoders
{
    using config::Wheel;
    
    // Called once from setup(): pins as INPUT_PULLUP, initial state, interrupts on.
    void begin();
    
    // Cumulative counts since boot, forward positive. Safe from any thread.
    int32_t count(Wheel wheel);
    
    // Transitions where both channels changed between two interrupts (a missed edge).
    uint32_t errors(Wheel wheel);
}
