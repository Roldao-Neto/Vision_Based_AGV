#pragma once

#include <Arduino.h>

namespace commands
{
    // Called once from setup(), before any handler is registered.
    void begin();
    
    // Handler side. Copies an already validated waypoint list into the staged path under
    // the mutex and queues the command, which starts the path when the tick applies it.
    // False if the queue is full.
    bool queue_set_path(int32_t id, const MsgPack::arr_t<int32_t> &xy_mm);
    
    // Handler side. Queues a ramped stop that pauses the run (stop). False if the queue is full.
    bool queue_stop();
    
    // Handler side. Queues a ramped stop that ends the run (mode idle). False if the queue is
    // full.
    bool queue_end_run();
    
    // Handler side. Queues an already validated axle pose (mm, mm, mrad). False if the queue is
    // full.
    bool queue_reset_pose(int32_t x_mm, int32_t y_mm, int32_t theta_mrad);
    
    // Tick side: applies every queued command, in arrival order.
    void drain();
}
