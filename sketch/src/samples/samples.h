#pragma once

#include <Arduino.h>

namespace samples
{
    // Called once from setup().
    void begin();
    
    // Tick side. Starts a recording and drops whatever an earlier one had not sent.
    // name must be a string literal (it is sent after the run ends).
    void start(const char *name, int32_t record_id, uint32_t values_per_sample, uint32_t per_notification);
    
    // Tick side, after start() with 3 values per sample: takes sample 0 now, then one
    // every 2 ms from the timer interrupt until stop().
    void start_count_timer();
    
    // Tick side: appends one sample of values_per_sample values (ignored when full).
    void add(const int32_t *values);
    
    // Encoder counts relative to the start of the recording.
    int32_t counts_since_start(int wheel);
    
    // Microseconds since the start of the recording.
    uint32_t us_since_start();
    
    // Tick side: stops the timer (if any) and queues the samples for sending.
    void stop();
    
    // Tick side, every tick: sends the next notification every 2 ticks.
    void tick();
    
    // Samples taken by the current or last recording.
    uint32_t count();
    
    // Any thread: true from start() until the last notification has gone out.
    bool busy();
}