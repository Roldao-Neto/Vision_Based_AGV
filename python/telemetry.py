import time

from arduino.app_utils import Logger
from run_log import open_run_log

logger = Logger("AGV")

STATUS_HEADER = ["rx_monotonic", "t_ms", "late_max_us", "exec_max_us", "hook_max_us", "overruns", "stack_peak", "stack_untouched", "hb_age_ms", "path_id", "emergency"]
EVENTS_HEADER = ["rx_monotonic", "event", "detail"]
HOOK_HEADER = ["rx_monotonic", "t_ms", "hook_us"]


status_log = open_run_log("app", STATUS_HEADER, "status")
events_log = open_run_log("app", EVENTS_HEADER, "events")
hook_log = open_run_log("app", HOOK_HEADER, "hook")


def event(name: str, detail: object = "") -> None:
    events_log.row(time.monotonic(), name, detail)
    logger.info(f"{name}: {detail}")


# Notification handlers


def on_status(*values: int) -> None:
    status_log.row(time.monotonic(), *values)


def on_hook(*values: int) -> None:
    hook_log.row(time.monotonic(), *values)


def on_emergency(t_ms: int, peak: int, untouched: int) -> None:
    event("emergency", f"t_ms={t_ms} stack_peak={peak} stack_untouched={untouched}")
