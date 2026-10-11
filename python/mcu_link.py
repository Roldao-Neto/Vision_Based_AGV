import threading
import time

from arduino.app_utils import Bridge
from telemetry import event

HB_PERIOD_S = 0.2
PING_RETRY_S = 0.5


def wait_for_mcu() -> None:
    start = time.monotonic()
    attempts = 0
    last_error = None
    while True:
        attempts += 1
        try:
            Bridge.call("ping", timeout=1)
            break
        except (TimeoutError, ValueError, RuntimeError, ConnectionError) as e:
            last_error = e
        time.sleep(PING_RETRY_S)
    event("mcu_ready", f"attempts={attempts} after={time.monotonic() - start:.1f}s last_error={last_error!r}")


def heartbeat() -> None:
    while True:
        Bridge.notify("hb")
        time.sleep(HB_PERIOD_S)


def mission() -> None:
    wait_for_mcu()
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()
