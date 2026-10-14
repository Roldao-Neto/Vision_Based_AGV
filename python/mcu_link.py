import threading
import time

from arduino.app_utils import Bridge
from command_file import take_commands
from mode_commands import parse
from telemetry import event

HB_PERIOD_S = 0.2
PING_RETRY_S = 0.5
CMD_POLL_S = 0.2
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
    args = parse(text)
    if args is None:
        event("cmd_rejected", text)
        return
    try:
        ok = Bridge.call("mode", *args, timeout=1)
    except BRIDGE_ERRORS as e:
        event("cmd_error", f"{text}: {e!r}")
        return
    event("cmd", f"{text} -> mode{args} ack={ok}")


def mission() -> None:
    """The only thread that sends commands to the MCU."""
    for text in take_commands():
        event("cmd_discarded", text)
    wait_for_mcu()
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()
    while True:
        try:
            for text in take_commands():
                run_command(text)
        except Exception as e:  # keep the mission thread alive, but log why  # noqa: BLE001
            event("mission_error", repr(e))
        time.sleep(CMD_POLL_S)
