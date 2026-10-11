// STM32U585 real-time side: motor driver, encoders, wheel PI, odometry, heading PID and point-to-point controller

// So far: the 20 ms control tick, Bridge handlers that only validate and queue, the bridge thread's stack peak with its emergency, and a status report sent with notify.

// Pins
constexpr int kLeftIn1 = D7;
constexpr int kLeftIn2 = D8;
constexpr int kRightIn1 = D10;
constexpr int kRightIn2 = D11;

// ---- Bridge stack peak ----
constexpr uint8_t kStackFill = 0xAA;        // pattern written by the AGV patch in bridge.h
constexpr size_t kStackEmergencyBytes = 512; // fewer untouched bytes than this is an emergency

// ---- Command queue ----
enum CommandType : int32_t {
    CMD_SET_PATH = 1,
};

struct Command {
    int32_t type;
    int32_t arg0;
    int32_t arg1;
};

constexpr int kQueueLength = 8;
static char cmd_queue_buf[kQueueLength * sizeof(Command)] __aligned(4);
static struct k_msgq cmd_queue;

// ---- Paths: 1 to 32 absolute axle waypoints in integer mm ----
constexpr int kMaxWaypoints = 32;
constexpr int32_t kArenaXMm = 2000;
constexpr int32_t kArenaYMm = 1500;

// A handler copies its waypoints here under the mutex; the tick takes them when it
// applies the matching CMD_SET_PATH. A newer set_path replaces an older one that is
// still queued, and the older command is then skipped.
static struct k_mutex staged_path_mutex;
static int32_t staged_path_id;
static int32_t staged_path_len;
static int32_t staged_path_mm[2 * kMaxWaypoints];

static int32_t path_id;
static int32_t path_len;
static int32_t path_mm[2 * kMaxWaypoints];

// ---- State shared with the handlers (atomics only) ----
static k_tid_t main_tid;
static atomic_ptr_t bridge_tid = ATOMIC_PTR_INIT(nullptr);
static atomic_t last_hb_ms = ATOMIC_INIT(0);
static atomic_t emergency = ATOMIC_INIT(0);

// ---- Control tick ----
constexpr uint32_t kTickPeriodUs = 20000;
constexpr uint32_t kReportEveryTicks = 25; // status every 500 ms

static uint32_t next_tick_us;
static uint32_t tick_count;
static uint32_t overrun_count;             // ticks that started more than a period late

// Worst cases over the current report window
static uint32_t win_late_max_us;           // tick start after its slot on the 20 ms grid
static uint32_t win_exec_max_us;           // tick body
static uint32_t win_hook_max_us;           // time outside loop()

// Time outside loop() (the Bridge's __loopHook and any preemption)
constexpr uint32_t kHookReportUs = 3000;
static uint32_t loop_end_us;

// ---- Tick-only state ----
static uint32_t stack_peak;
static uint32_t stack_untouched;
static bool emergency_reported;

// ---- Motors: only the short brake for emergencies until the driver exists ----

static void motors_coast()
{
    // IN1 = IN2 = L: TB6612 output off; PWM stays low through its pull-down.
    for (int pin : {kLeftIn1, kLeftIn2, kRightIn1, kRightIn2}) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
}

static void motors_short_brake()
{
    // IN1 = IN2 = H: short brake, whatever the PWM pin does.
    for (int pin : {kLeftIn1, kLeftIn2, kRightIn1, kRightIn2}) {
        digitalWrite(pin, HIGH);
    }
}

// ---- Bridge handlers: validate, queue, return. No Bridge or Serial calls. ----

static void note_handler_thread()
{
    // Handlers run on the main thread or on the bridge thread, so the first one that
    // runs off the main thread identifies the bridge thread, whose stack the tick scans.
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
    atomic_set(&last_hb_ms, (atomic_val_t)k_uptime_get_32());
}

static bool on_set_path(int32_t id, MsgPack::arr_t<int32_t> xy_mm)
{
    note_handler_thread();
    const size_t n = xy_mm.size();
    if (atomic_get(&emergency) || n < 2 || n > 2 * kMaxWaypoints || n % 2 != 0) {
        return false;
    }
    for (size_t i = 0; i < n; i += 2) {
        if (xy_mm[i] < 0 || xy_mm[i] > kArenaXMm || xy_mm[i + 1] < 0 || xy_mm[i + 1] > kArenaYMm) {
            return false;
        }
    }

    k_mutex_lock(&staged_path_mutex, K_FOREVER);
    staged_path_id = id;
    staged_path_len = (int32_t)n;
    for (size_t i = 0; i < n; i++) {
        staged_path_mm[i] = xy_mm[i];
    }
    k_mutex_unlock(&staged_path_mutex);

    const Command cmd{CMD_SET_PATH, id, (int32_t)n};
    return k_msgq_put(&cmd_queue, &cmd, K_NO_WAIT) == 0;
}

// ---- Tick-side helpers ----

static void apply_set_path(const Command &cmd)
{
    k_mutex_lock(&staged_path_mutex, K_FOREVER);
    if (staged_path_id == cmd.arg0 && staged_path_len == cmd.arg1) {
        path_id = staged_path_id;
        path_len = staged_path_len;
        for (int32_t i = 0; i < path_len; i++) {
            path_mm[i] = staged_path_mm[i];
        }
    }
    k_mutex_unlock(&staged_path_mutex);
}

static void drain_commands()
{
    Command cmd;
    while (k_msgq_get(&cmd_queue, &cmd, K_NO_WAIT) == 0) {
        switch (cmd.type) {
        case CMD_SET_PATH:
            apply_set_path(cmd);
            break;
        }
    }
}

static void scan_bridge_stack()
{
    const k_tid_t tid = (k_tid_t)atomic_ptr_get(&bridge_tid);
    if (tid == nullptr) {
        return;
    }
    // The stack grows down from the top, so the untouched pattern is at the bottom.
    const uint8_t *bottom = (const uint8_t *)tid->stack_info.start;
    const size_t size = tid->stack_info.size;
    size_t untouched = 0;
    while (untouched < size && bottom[untouched] == kStackFill) {
        untouched++;
    }
    stack_untouched = untouched;
    stack_peak = size - untouched;

    if (untouched < kStackEmergencyBytes && !atomic_get(&emergency)) {
        atomic_set(&emergency, 1);
        motors_short_brake();
    }
}

static void send_status(uint32_t now_ms)
{
    if (atomic_get(&emergency) && !emergency_reported) {
        emergency_reported = true;
        Bridge.notify("emergency", now_ms, stack_peak, stack_untouched);
    }
    const uint32_t hb_ms = (uint32_t)atomic_get(&last_hb_ms);
    Bridge.notify("status", now_ms, win_late_max_us, win_exec_max_us, win_hook_max_us, overrun_count,
                  stack_peak, stack_untouched, hb_ms == 0 ? -1 : (int32_t)(now_ms - hb_ms), path_id,
                  (int32_t)atomic_get(&emergency));
    win_late_max_us = 0;
    win_exec_max_us = 0;
    win_hook_max_us = 0;
}

static void tick(uint32_t now_us, uint32_t late_us)
{
    tick_count++;
    win_late_max_us = max(win_late_max_us, late_us);

    // Commands queued by the handlers apply between ticks, in arrival order.
    drain_commands();
    scan_bridge_stack();

    if (tick_count % kReportEveryTicks == 0) {
        send_status(millis());
    }
    win_exec_max_us = max(win_exec_max_us, micros() - now_us);
}

void setup()
{
    main_tid = k_current_get();
    motors_coast();
    k_msgq_init(&cmd_queue, cmd_queue_buf, sizeof(Command), kQueueLength);
    k_mutex_init(&staged_path_mutex);

    Bridge.begin();
    Bridge.provide_safe("ping", on_ping);
    Bridge.provide_safe("hb", on_hb);
    Bridge.provide_safe("set_path", on_set_path);

    next_tick_us = micros() + kTickPeriodUs;
    loop_end_us = micros();
}

// Time spent outside loop() since it last returned: the Bridge's __loopHook, which
// may run handlers on this thread, plus any preemption. Reported when above
// kHookReportUs. A large incoming message (a 32-waypoint set_path) holds loop() off
// for ~35 ms while it arrives, so set_path is sent only
// while stopped.
static void track_hook_time(uint32_t now_us)
{
    const uint32_t hook_us = now_us - loop_end_us;
    win_hook_max_us = max(win_hook_max_us, hook_us);
    if (hook_us > kHookReportUs) {
        Bridge.notify("hook", millis(), hook_us);
    }
}

static void run_tick_if_due(uint32_t now_us)
{
    const int32_t late_us = (int32_t)(now_us - next_tick_us);
    if (late_us < 0) {
        return;
    }
    if (late_us > (int32_t)kTickPeriodUs) {
        // More than one period behind: resync instead of running catch-up ticks
        // with a near-zero dt, and count it.
        overrun_count++;
        next_tick_us = now_us + kTickPeriodUs;
    } else {
        next_tick_us += kTickPeriodUs;
    }
    tick(now_us, (uint32_t)late_us);
}

void loop()
{
    const uint32_t now_us = micros();
    track_hook_time(now_us);
    run_tick_if_due(now_us);
    loop_end_us = micros();
}
