#include "handlers.h"
#include <Arduino.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include "../commands/commands.h"
#include "../config/config.h"
#include "../modes/modes.h"

using namespace config;

namespace handlers
{
    static k_tid_t main_tid;
    static atomic_ptr_t bridge_tid = ATOMIC_PTR_INIT(nullptr);
    static atomic_t last_hb = ATOMIC_INIT(0);
    
    static void note_handler_thread()
    {
        const k_tid_t current = k_current_get();
        if (current != main_tid) {
            atomic_ptr_cas(&bridge_tid, nullptr, current);
        }
    }
    
    static bool on_ping()
    {
        note_handler_thread();
        return true;
    }
    
    static void on_hb()
    {
        note_handler_thread();
        atomic_set(&last_hb, (atomic_val_t)k_uptime_get_32());
    }
    
    static bool hb_fresh()
    {
        const uint32_t hb_ms = (uint32_t)atomic_get(&last_hb);
        return hb_ms != 0 && k_uptime_get_32() - hb_ms <= kHeartbeatTimeoutMs;
    }
    
    static bool on_set_path(int32_t id, MsgPack::arr_t<int32_t> xy_mm)
    {
        note_handler_thread();
        const size_t n = xy_mm.size();
        if (!modes::path_allowed() || !hb_fresh() || n < 2 || n > 2 * kMaxWaypoints || n % 2 != 0) {
            return false;
        }
        for (size_t i = 0; i < n; i += 2)
        {
            if (xy_mm[i] < 0 || xy_mm[i] > kArenaXMm || xy_mm[i + 1] < 0 || xy_mm[i + 1] > kArenaYMm){
                return false;
            }
        }
        return commands::queue_set_path(id, xy_mm);
    }
    
    static bool on_reset_pose(int32_t x_mm, int32_t y_mm, int32_t theta_mrad)
    {
        note_handler_thread();
        if (!modes::still() || x_mm < 0 || x_mm > kArenaXMm || y_mm < 0 || y_mm > kArenaYMm ||
            theta_mrad < -kMaxThetaMrad || theta_mrad > kMaxThetaMrad) {
            return false;
        }
        return commands::queue_reset_pose(x_mm, y_mm, theta_mrad);
    }
    
    static bool on_stop()
    {
        note_handler_thread();
        return commands::queue_stop();
    }
    
    static bool on_mode(int32_t code, int32_t p1, int32_t p2, int32_t p3, int32_t p4)
    {
        note_handler_thread();
        const int32_t params[modes::kParams] = {p1, p2, p3, p4};
        if (!modes::valid(code, params)) {
            return false;
        }
        return commands::queue_end_run();
    }
    
    void begin()
    {
        main_tid = k_current_get();
        
        Bridge.provide_safe("ping", on_ping);
        Bridge.provide_safe("hb", on_hb);
        Bridge.provide_safe("set_path", on_set_path);
        Bridge.provide_safe("reset_pose", on_reset_pose);
        Bridge.provide_safe("stop", on_stop);
        Bridge.provide_safe("mode", on_mode);
    }
    
    k_tid_t bridge_thread()
    {
        return (k_tid_t)atomic_ptr_get(&bridge_tid);
    }
    
    uint32_t last_hb_ms()
    {
        return (uint32_t)atomic_get(&last_hb);
    }
}
