#pragma once

#include <Arduino.h>

namespace samples
{
    // Tick side. Starts a recording and drops whatever an earlier one had not sent.
    // name must be a string literal (it is sent after the run ends).
    void start(const char *name, int32_t record_id, uint32_t values_per_sample, uint32_t per_notification);
    
    // Tick side: appends one sample of values_per_sample values (ignored when full).
    void add(const int32_t *values);
    
    // Microseconds since the start of the recording.
    uint32_t us_since_start();
    
    // Tick side: queues the samples for sending.
    void stop();
    
    // Tick side, every tick: sends the next notification every 2 ticks.
    void tick();
    
    // Samples taken by the current or last recording.
    uint32_t count();
    
    // Any thread: true from start() until the last notification has gone out.
    bool busy();
}