import threading
import time

from arduino.app_utils import Bridge
from command_file import take_commands
from mcu_commands import parse
from mission import Mission
from telemetry import event, log_path

HB_PERIOD_S = 0.2
PING_RETRY_S = 0.5
CMD_POLL_S = 0.2
MISSION_STEP_S = 0.05
MISSION_COMMANDS = ("start", "abort", "reset")  # cmd/ texts that go to the mission, like the UI buttons
BRIDGE_ERRORS = (TimeoutError, ValueError, RuntimeError, ConnectionError)


def wait_for_mcu() -> None:
    start = time.monotonic()
    attempts = 0
    last_error = None
    while True:
        attempts += 1
        try:
            Bridge.call("ping", timeout=1)
            break
        except BRIDGE_ERRORS as e:
            last_error = e
        time.sleep(PING_RETRY_S)
    event("mcu_ready", f"attempts={attempts} after={time.monotonic() - start:.1f}s last_error={last_error!r}")


def heartbeat() -> None:
    while True:
        Bridge.notify("hb")
        time.sleep(HB_PERIOD_S)


def run_command(text: str) -> None:
    call = parse(text)
    if call is None:
        event("cmd_rejected", text)
        return
    method, args = call
    try:
        ok = Bridge.call(method, *args, timeout=1)
    except BRIDGE_ERRORS as e:
        event("cmd_error", f"{text}: {e!r}")
        return
    if method == "set_path":
        path_id, xy_mm = args
        log_path(path_id, xy_mm, ok)  # type: ignore[arg-type]
    event("cmd", f"{text} -> {method}{args} ack={ok}")


def bridge_call(method: str, *args: object) -> object:
    return Bridge.call(method, *args, timeout=1)


def mission_thread(mission: Mission) -> None:
    """The only thread that sends commands to the MCU: the mission's, and the cmd/ ones."""
    for text in take_commands():
        event("cmd_discarded", text)
    wait_for_mcu()
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()
    mission.post("reset")  # the robot starts at A, so what the camera sees from there counts
    next_poll = 0.0
    while True:
        try:
            if time.monotonic() >= next_poll:
                next_poll = time.monotonic() + CMD_POLL_S
                for text in take_commands():
                    if text in MISSION_COMMANDS:
                        mission.post(text)
                    else:
                        run_command(text)
            mission.step()
        except Exception as e:  # keep the mission thread alive, but log why  # noqa: BLE001
            event("mission_error", repr(e))
        time.sleep(MISSION_STEP_S)
