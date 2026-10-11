import threading
import time

from arduino.app_utils import App, Bridge
from mcu_link import mission
from telemetry import event, events_log, on_emergency, on_hook, on_status, status_log

Bridge.provide("status", on_status)
Bridge.provide("hook", on_hook)
Bridge.provide("emergency", on_emergency)
event("start", f"status={status_log.path.name} events={events_log.path.name}")

threading.Thread(target=mission, name="mission", daemon=True).start()

App.run(user_loop=lambda: time.sleep(1))
