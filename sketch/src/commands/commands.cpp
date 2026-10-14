#include <Arduino.h>
#include <zephyr/kernel.h>
#include "commands.h"
#include "../config/config.h"
#include "../modes/modes.h"

using namespace config;

namespace commands
{
    enum CommandType : int32_t
    {
        CMD_SET_PATH = 1, // args: id, number of values
        CMD_MODE = 2,     // args: code, p1..p4
    };

    struct Command
    {
        int32_t type;
        int32_t args[1 + modes::kParams];
    };

    constexpr int kQueueLength = 8;
    static char cmd_queue_buf[kQueueLength * sizeof(Command)] __aligned(4);
    static struct k_msgq cmd_queue;

    static struct k_mutex staged_path_mutex;
    static int32_t staged_path_id;
    static int32_t staged_path_len;
    static int32_t staged_path_mm[2 * kMaxWaypoints]; // X & Y

    static int32_t applied_path_id;
    static int32_t path_len;
    static int32_t path_mm[2 * kMaxWaypoints];

    void begin()
    {
        k_msgq_init(&cmd_queue, cmd_queue_buf, sizeof(Command), kQueueLength);
        k_mutex_init(&staged_path_mutex);
    }

    bool queue_set_path(int32_t id, const MsgPack::arr_t<int32_t> &xy_mm)
    {
        const size_t n = xy_mm.size();
        
        k_mutex_lock(&staged_path_mutex, K_FOREVER);
        
        staged_path_id = id;
        staged_path_len = (int32_t)n;

        for (size_t i = 0; i < n; i++)
        {
            staged_path_mm[i] = xy_mm[i];
        }

        k_mutex_unlock(&staged_path_mutex);

        const Command cmd{CMD_SET_PATH, {id, (int32_t)n}};
        
        return k_msgq_put(&cmd_queue, &cmd, K_NO_WAIT) == 0;
    }

    bool queue_mode(int32_t code, const int32_t params[modes::kParams])
    {
        Command cmd{CMD_MODE, {code}};
        
        for (int i = 0; i < modes::kParams; i++)
        {
            cmd.args[1 + i] = params[i];
        }
        
        return k_msgq_put(&cmd_queue, &cmd, K_NO_WAIT) == 0;
    }

    static void apply_set_path(const Command &cmd)
    {
        k_mutex_lock(&staged_path_mutex, K_FOREVER);
        
        if (staged_path_id == cmd.args[0] && staged_path_len == cmd.args[1])
        {
            applied_path_id = staged_path_id;
            path_len = staged_path_len;
            for (int32_t i = 0; i < path_len; i++) 
            {
                path_mm[i] = staged_path_mm[i];
            }
        }
        
        k_mutex_unlock(&staged_path_mutex);
    }

    void drain()
    {
        Command cmd;
        
        while (k_msgq_get(&cmd_queue, &cmd, K_NO_WAIT) == 0) 
        {
            switch (cmd.type) 
            {
                case CMD_SET_PATH:
                    apply_set_path(cmd);
                    break;
                case CMD_MODE:
                    modes::request(cmd.args[0], &cmd.args[1]);
                    break;
            }
        }
    }

    int32_t path_id()
    {
        return applied_path_id;
    }
}
