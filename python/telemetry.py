import time
from collections.abc import Callable

from arduino.app_utils import Logger
from clock_sync import ClockSync
from mcu_commands import END_REASONS, MODE_NAMES
from mission import Pose
from run_log import RunLog, open_run_log
from run_samples import RunSamples

logger = Logger("AGV")

STATUS_HEADER = ["rx_monotonic", "t_ms", "late_max_us", "exec_max_us", "hook_max_us", "overruns", "stack_peak", "stack_untouched", "hb_age_ms", "path_id", "emergency", "pwm_hz", "pwm_err", "enc_l", "enc_r", "enc_err_l", "enc_err_r", "mode", "spd_l", "spd_r", "dt_min_us", "dt_max_us", "x_mm", "y_mm", "th_mrad"]
EVENTS_HEADER = ["rx_monotonic", "event", "detail"]
HOOK_HEADER = ["rx_monotonic", "t_ms", "hook_us"]
POSE_HEADER = ["rx_monotonic", "t_ms", "x", "y", "theta", "state", "path_id", "wp_idx", "offset_s", "delay_ms", "t_linux"]
PATHS_HEADER = ["rx_monotonic", "path_id", "waypoints", "xy_mm", "ack"]
RUN_END_HEADER = ["rx_monotonic", "t_ms", "record_id", "mode", "duration_ms", "reason", "p1", "p2", "p3", "p4", "counts_l", "counts_r", "errors_l", "errors_r", "samples", "x0_um", "y0_um", "th0_urad", "x_um", "y_um", "th_urad", "m_per_count_l_pm", "m_per_count_r_pm", "track_nm"]
RUN_SAMPLE_HEADER = ["t_us", "phase", "v_mm_s", "w_mrad_s", "counts_l", "counts_r", "duty_l", "duty_r"]


status_log = open_run_log("app", STATUS_HEADER, "status")
events_log = open_run_log("app", EVENTS_HEADER, "events")
hook_log = open_run_log("app", HOOK_HEADER, "hook")
pose_log = open_run_log("app", POSE_HEADER, "pose")
paths_log = open_run_log("app", PATHS_HEADER, "paths")
clock = ClockSync()
pose_listeners: list[Callable[[Pose], None]] = []
run_end_listeners: list[Callable[[int, int], None]] = []  # (path_id, reason)
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


def on_pose(t_ms: int, x: float, y: float, theta: float, state: int, path_id: int, wp_idx: int) -> None:
    rx = time.monotonic()
    offset, delay = clock.update(rx, t_ms)
    t_linux = clock.to_linux(t_ms)
    pose_log.row(rx, t_ms, x, y, theta, state, path_id, wp_idx, f"{offset:.6f}", f"{delay:.2f}", f"{t_linux:.6f}")
    pose = Pose(rx, t_ms, t_linux, x, y, theta, state, path_id, wp_idx)
    for listener in pose_listeners:
        listener(pose)


def log_path(path_id: int, xy_mm: list[int], ack: object) -> None:
    """Every set_path sent (the mission's and the cmd/ ones)."""
    paths_log.row(time.monotonic(), path_id, len(xy_mm) // 2, " ".join(map(str, xy_mm)), repr(ack))


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
    """Parameters in the samples file name of a recorded run."""
    if mode == "path":
        return f"{record_id}_paths{p2}"
    return f"{record_id}_{p1}_{p2}_{p3}_{p4}"


def on_run_end(*values: int) -> None:
    """run_end of a recorded run; values follow RUN_END_HEADER without rx_monotonic.

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
    for listener in run_end_listeners:
        listener(values[5], values[4])  # p1 = last path_id


def on_emergency(t_ms: int, peak: int, untouched: int) -> None:
    event("emergency", f"t_ms={t_ms} stack_peak={peak} stack_untouched={untouched}")
