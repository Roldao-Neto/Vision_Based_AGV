import time

from arduino.app_utils import Logger
from mode_commands import END_REASONS
from run_log import RunLog, open_run_log
from run_samples import RunSamples

logger = Logger("AGV")

STATUS_HEADER = ["rx_monotonic", "t_ms", "late_max_us", "exec_max_us", "hook_max_us", "overruns", "stack_peak", "stack_untouched", "hb_age_ms", "path_id", "emergency", "pwm_hz", "pwm_err", "enc_l", "enc_r", "enc_err_l", "enc_err_r", "mode", "spd_l", "spd_r", "dt_min_us", "dt_max_us"]
EVENTS_HEADER = ["rx_monotonic", "event", "detail"]
HOOK_HEADER = ["rx_monotonic", "t_ms", "hook_us"]
END_HEADERS = {
    "speed": ["rx_monotonic", "t_ms", "record_id", "duration_ms", "reason", "v_mm_s", "accel_mm_s2", "counts_l", "counts_r", "errors_l", "errors_r", "samples"],
}
SAMPLE_HEADERS = {"speed": ["t_us", "v_ref", "counts_l", "counts_r", "duty_l", "duty_r"]}


status_log = open_run_log("app", STATUS_HEADER, "status")
events_log = open_run_log("app", EVENTS_HEADER, "events")
hook_log = open_run_log("app", HOOK_HEADER, "hook")
end_logs: dict[str, RunLog] = {}  # mode -> summary log, opened by its first end report
run_names: dict[int, tuple[str, str]] = {}  # record_id -> (mode, samples file name params)
pending_samples: dict[int, RunSamples] = {}


def event(name: str, detail: object = "") -> None:
    events_log.row(time.monotonic(), name, detail)
    logger.info(f"{name}: {detail}")


# Notification handlers


def on_status(*values: int) -> None:
    status_log.row(time.monotonic(), *values)


def on_hook(*values: int) -> None:
    hook_log.row(time.monotonic(), *values)


def _record_end(mode: str, values: list[int], name_params: str) -> None:
    """values follow END_HEADERS[mode] without rx_monotonic."""
    if mode not in end_logs:
        end_logs[mode] = open_run_log(mode, END_HEADERS[mode])
    end_logs[mode].row(time.monotonic(), *values)
    record_id = values[1]
    run_names[record_id] = (mode, name_params)
    # An older run whose samples never finished was dropped by the MCU.
    for old_id in [i for i in pending_samples if i < record_id]:
        event("samples_lost", f"record_id={old_id} received={len(pending_samples.pop(old_id).samples)}")
    fields: dict[str, object] = dict(zip(END_HEADERS[mode][1:], values, strict=True))
    fields["reason"] = END_REASONS.get(values[3], values[3])
    event(f"{mode}_end", " ".join(f"{k}={v}" for k, v in fields.items() if k != "t_ms"))


def _on_samples(mode: str, record_id: int, first: int, total: int, flat: list[int]) -> None:
    width = len(SAMPLE_HEADERS[mode])
    s = pending_samples.setdefault(record_id, RunSamples(record_id, width))
    was_lost = s.lost
    s.add(first, total, flat)
    if s.lost and not was_lost:
        event("samples_lost", f"record_id={record_id} first={first} received={len(s.samples)} total={total}")
    if first + len(flat) // width < total:
        return  # more notifications to come
    del pending_samples[record_id]
    if s.complete:
        name_mode, params = run_names.get(record_id, (mode, str(record_id)))
        log = open_run_log(name_mode, SAMPLE_HEADERS[mode], params)
        for sample in s.samples:
            log.row(*sample)
        log.close()
        event(f"{mode}_samples", f"record_id={record_id} samples={total} file={log.path.name}")


def on_speed_end(t_ms: int, record_id: int, duration_ms: int, reason: int, v_mm_s: int, accel_mm_s2: int, counts_l: int, counts_r: int, errors_l: int, errors_r: int, samples: int) -> None:
    values = [t_ms, record_id, duration_ms, reason, v_mm_s, accel_mm_s2, counts_l, counts_r, errors_l, errors_r, samples]
    _record_end("speed", values, f"{record_id}_v{v_mm_s}_a{accel_mm_s2}")


def on_speed_samples(record_id: int, first: int, total: int, flat: list[int]) -> None:
    _on_samples("speed", record_id, first, total, flat)


def on_emergency(t_ms: int, peak: int, untouched: int) -> None:
    event("emergency", f"t_ms={t_ms} stack_peak={peak} stack_untouched={untouched}")
