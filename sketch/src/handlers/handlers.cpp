#include "handlers.h"
#include <Arduino.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include "../bridge_stack/bridge_stack.h"
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
    
    static bool on_set_path(int32_t id, MsgPack::arr_t<int32_t> xy_mm)
    {
        note_handler_thread();
        const size_t n = xy_mm.size();
        if (bridge_stack::emergency() || n < 2 || n > 2 * kMaxWaypoints || n % 2 != 0) {
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
    
    static bool on_mode(int32_t code, int32_t p1, int32_t p2, int32_t p3, int32_t p4)
    {
        note_handler_thread();
        const int32_t params[modes::kParams] = {p1, p2, p3, p4};
        if (!modes::valid(code, params) || (bridge_stack::emergency() && code != modes::kIdle)) {
            return false;
        }
        return commands::queue_mode(code, params);
    }
    
    void begin()
    {
        main_tid = k_current_get();
        
        Bridge.provide_safe("ping", on_ping);
        Bridge.provide_safe("hb", on_hb);
        Bridge.provide_safe("set_path", on_set_path);
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
