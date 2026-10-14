#pragma once

#include <Arduino.h>

#include "../modes/modes.h"

namespace commands
{
    // Called once from setup(), before any handler is registered.
    void begin();
    
    // Handler side. Copies an already validated waypoint list into the staged path under
    // the mutex and queues the command. False if the queue is full.
    bool queue_set_path(int32_t id, const MsgPack::arr_t<int32_t> &xy_mm);
    
    // Handler side. Queues a mode switch. False if the queue is full.
    bool queue_mode(int32_t code, const int32_t params[modes::kParams]);
    
    // Tick side: applies every queued command.
    void drain();
    
    // Id of the last applied path (0 before the first).
    int32_t path_id();
}
