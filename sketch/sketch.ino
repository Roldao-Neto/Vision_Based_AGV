#include <math.h>
#include "src/bridge_stack/bridge_stack.h"
#include "src/commands/commands.h"
#include "src/config/config.h"
#include "src/encoders/encoders.h"
#include "src/handlers/handlers.h"
#include "src/modes/modes.h"
#include "src/samples/samples.h"
#include "src/motor_driver/motor_driver.h"
#include "src/tick_timing/tick_timing.h"
#include "src/wheel_speed/wheel_speed.h"

using namespace config;

static void tick(uint32_t now_us)
{
    static uint32_t tick_count;
    tick_count++;

    wheel_speed::update();

    if (wheel_speed::dt_us() != 0)
    {
        tick_timing::note_dt(wheel_speed::dt_us());
    }

    commands::drain();
    bridge_stack::scan(handlers::bridge_thread());
    modes::tick();
    samples::tick();

    if (tick_count % kReportEveryTicks == 0) {
        const uint32_t now_ms = millis();
        bridge_stack::report_emergency_once(now_ms);
        const tick_timing::Window w = tick_timing::take_window();
        const uint32_t hb_ms = handlers::last_hb_ms();
        Bridge.notify(
            "status",
            now_ms,
            w.late_max_us,
            w.exec_max_us,
            w.hook_max_us,
            tick_timing::overruns(),
            bridge_stack::peak(),
            bridge_stack::untouched(),
            hb_ms == 0 ? -1 : (int32_t)(now_ms - hb_ms),
            commands::path_id(),
            (int32_t)bridge_stack::emergency(),
            motor_driver::pwm_hz(),
            motor_driver::pwm_error(),
            encoders::count(kLeft),
            encoders::count(kRight),
            encoders::errors(kLeft),
            encoders::errors(kRight),
            modes::current(),
            (int32_t)lroundf(wheel_speed::speed(kLeft)),
            (int32_t)lroundf(wheel_speed::speed(kRight)),
            w.dt_min_us,
            w.dt_max_us
        );
    }
    tick_timing::tick_ended(now_us);
}

void setup()
{
    motor_driver::begin(); // the result goes out in status (pwm_hz, pwm_err)
    encoders::begin();
    commands::begin();

    Bridge.begin();
    
    handlers::begin();

    tick_timing::begin();
}

void loop()
{
    const uint32_t now_us = micros();
    tick_timing::loop_started(now_us);
    if (tick_timing::due(now_us)) {
        tick(now_us);
    }
    tick_timing::loop_ended(micros());
}
