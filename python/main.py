import threading
import time

from arduino.app_utils import App, Bridge
from capture import Capture
from flask_video_webui import Server
from mcu_link import bridge_call, mission_thread
from mission import Mission
from opencv_camera_handler import Camera
from telemetry import (
    event,
    events_log,
    log_path,
    on_emergency,
    on_hook,
    on_pose,
    on_run_end,
    on_run_samples,
    on_status,
    pose_listeners,
    run_end_listeners,
    status_log,
)
from webui import preview, register

mission = Mission(bridge_call, event, log_path)
pose_listeners.append(mission.on_pose)
run_end_listeners.append(mission.on_run_end)

Bridge.provide("status", on_status)
Bridge.provide("hook", on_hook)
Bridge.provide("pose", on_pose)
Bridge.provide("emergency", on_emergency)
Bridge.provide("run_end", on_run_end)
Bridge.provide("run_samples", on_run_samples)

event("start", f"status={status_log.path.name} events={events_log.path.name}")

capture = Capture(Camera(), event)
capture.start()

server = Server()
register(server.app, mission, capture)
server.video(lambda: preview(capture))
server.start()

threading.Thread(target=mission_thread, args=(mission,), name="mission", daemon=True).start()

App.run(user_loop=lambda: time.sleep(1))
