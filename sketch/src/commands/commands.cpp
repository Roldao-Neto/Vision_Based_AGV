#include <Arduino.h>
#include <zephyr/kernel.h>
#include "commands.h"
#include "../config/config.h"
#include "../modes/modes.h"
#include "../pose/pose.h"

using namespace config;

namespace commands
{
    enum CommandType : int32_t
    {
        CMD_SET_PATH = 1,   // args: id, number of values
        CMD_STOP = 2,       // no args
        CMD_RESET_POSE = 3, // args: x_mm, y_mm, theta_mrad
        CMD_END_RUN = 4,    // no args
    };

    struct Command
    {
        int32_t type;
        int32_t args[3];
    };

    constexpr int kQueueLength = 8;
    static char cmd_queue_buf[kQueueLength * sizeof(Command)] __aligned(4);
    static struct k_msgq cmd_queue;

    static struct k_mutex staged_path_mutex;
    static int32_t staged_path_id;
    static int32_t staged_path_len;
    static int32_t staged_path_mm[2 * kMaxWaypoints]; // X & Y

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

    bool queue_stop()
    {
        const Command cmd{CMD_STOP, {}};
        
        return k_msgq_put(&cmd_queue, &cmd, K_NO_WAIT) == 0;
    }

    bool queue_end_run()
    {
        const Command cmd{CMD_END_RUN, {}};
        
        return k_msgq_put(&cmd_queue, &cmd, K_NO_WAIT) == 0;
    }

    bool queue_reset_pose(int32_t x_mm, int32_t y_mm, int32_t theta_mrad)
    {
        const Command cmd{CMD_RESET_POSE, {x_mm, y_mm, theta_mrad}};
        
        return k_msgq_put(&cmd_queue, &cmd, K_NO_WAIT) == 0;
    }

    // A newer set_path that overwrote the staged path makes this command stale.
    static void apply_set_path(const Command &cmd)
    {
        k_mutex_lock(&staged_path_mutex, K_FOREVER);
        
        if (staged_path_id == cmd.args[0] && staged_path_len == cmd.args[1])
        {
            modes::start_path(staged_path_id, staged_path_mm, staged_path_len / 2);
        }
        
        k_mutex_unlock(&staged_path_mutex);
    }

    // Only with no run open: it would shift every absolute target, and break the run's odometry
    // check.
    static void apply_reset_pose(const Command &cmd)
    {
        if (modes::still())
        {
            pose::set(cmd.args[0] * 0.001, cmd.args[1] * 0.001, cmd.args[2] * 0.001);
        }
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
                case CMD_STOP:
                    modes::stop();
                    break;
                case CMD_END_RUN:
                    modes::end_run();
                    break;
                case CMD_RESET_POSE:
                    apply_reset_pose(cmd);
                    break;
            }
        }
    }
}
