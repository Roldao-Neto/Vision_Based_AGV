import time

from arduino.app_utils import Logger
from mode_commands import END_REASONS, MODE_NAMES
from run_log import RunLog, open_run_log
from run_samples import RunSamples

logger = Logger("AGV")

STATUS_HEADER = ["rx_monotonic", "t_ms", "late_max_us", "exec_max_us", "hook_max_us", "overruns", "stack_peak", "stack_untouched", "hb_age_ms", "path_id", "emergency", "pwm_hz", "pwm_err", "enc_l", "enc_r", "enc_err_l", "enc_err_r", "mode", "spd_l", "spd_r", "dt_min_us", "dt_max_us", "x_mm", "y_mm", "th_mrad"]
EVENTS_HEADER = ["rx_monotonic", "event", "detail"]
HOOK_HEADER = ["rx_monotonic", "t_ms", "hook_us"]
# Calibration modes (straight, umbmark): one end report and one sample layout for all.
RUN_END_HEADER = ["rx_monotonic", "t_ms", "record_id", "mode", "duration_ms", "reason", "p1", "p2", "p3", "p4", "counts_l", "counts_r", "errors_l", "errors_r", "samples", "x0_um", "y0_um", "th0_urad", "x_um", "y_um", "th_urad", "m_per_count_l_pm", "m_per_count_r_pm", "track_nm"]
RUN_SAMPLE_HEADER = ["t_us", "phase", "v_mm_s", "w_mrad_s", "counts_l", "counts_r", "duty_l", "duty_r"]


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


def on_run_samples(record_id: int, first: int, total: int, flat: list[int]) -> None:
    width = len(RUN_SAMPLE_HEADER)
    s = pending_samples.setdefault(record_id, RunSamples(record_id, width))
    was_lost = s.lost
    s.add(first, total, flat)
    if s.lost and not was_lost:
        event("samples_lost", f"record_id={record_id} first={first} received={len(s.samples)} total={total}")
    if first + len(flat) // width < total:
        return  # more notifications to come
    del pending_samples[record_id]
    if s.complete:
        name_mode, params = run_names.get(record_id, ("run", str(record_id)))
        log = open_run_log(name_mode, RUN_SAMPLE_HEADER, params)
        for sample in s.samples:
            log.row(*sample)
        log.close()
        event("run_samples", f"record_id={record_id} samples={total} file={log.path.name}")


def run_name_params(mode: str, record_id: int, p1: int, p2: int, p3: int, p4: int) -> str:
    """Parameters in the samples file name of a calibration run."""
    if mode == "straight":
        return f"{record_id}_v{p1}_d{p4}"
    if mode == "umbmark":
        return f"{record_id}_{'ccw' if p1 > 0 else 'cw'}_L{p2}"
    return f"{record_id}_{p1}_{p2}_{p3}_{p4}"


def on_run_end(*values: int) -> None:
    """run_end of the calibration modes; values follow RUN_END_HEADER without rx_monotonic.

    mode names the summary log and the samples file."""
    fields: dict[str, object] = dict(zip(RUN_END_HEADER[1:], values, strict=True))
    record_id = values[1]
    mode = MODE_NAMES.get(values[2], f"mode{values[2]}")
    if mode not in end_logs:
        end_logs[mode] = open_run_log(mode, RUN_END_HEADER)
    end_logs[mode].row(time.monotonic(), *values)
    run_names[record_id] = (mode, run_name_params(mode, record_id, *values[5:9]))
    # An older run whose samples never finished was dropped by the MCU.
    for old_id in [i for i in pending_samples if i < record_id]:
        event("samples_lost", f"record_id={old_id} received={len(pending_samples.pop(old_id).samples)}")
    fields["reason"] = END_REASONS.get(values[4], values[4])
    fields.pop("mode")
    event(f"{mode}_end", " ".join(f"{k}={v}" for k, v in fields.items() if k != "t_ms"))


def on_emergency(t_ms: int, peak: int, untouched: int) -> None:
    event("emergency", f"t_ms={t_ms} stack_peak={peak} stack_untouched={untouched}")
