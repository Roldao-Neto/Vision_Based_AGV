import threading
import time

from arduino.app_utils import App, Bridge
from mcu_link import mission
from telemetry import (
    event,
    events_log,
    on_count,
    on_emergency,
    on_hook,
    on_ramp_end,
    on_ramp_samples,
    on_speed_end,
    on_speed_samples,
    on_status,
    on_step_end,
    on_step_samples,
    status_log,
)

Bridge.provide("status", on_status)
Bridge.provide("hook", on_hook)
Bridge.provide("emergency", on_emergency)
Bridge.provide("count", on_count)
Bridge.provide("step_end", on_step_end)
Bridge.provide("step_samples", on_step_samples)
Bridge.provide("ramp_end", on_ramp_end)
Bridge.provide("ramp_samples", on_ramp_samples)
Bridge.provide("speed_end", on_speed_end)
Bridge.provide("speed_samples", on_speed_samples)
event("start", f"status={status_log.path.name} events={events_log.path.name}")

threading.Thread(target=mission, name="mission", daemon=True).start()

App.run(user_loop=lambda: time.sleep(1))
