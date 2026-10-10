"""Per-run CSV log files.

Every file gets a unique name (UTC date and time, mode and parameters) and is opened
in exclusive-create mode, so a later run never overwrites it. Rows are line-buffered:
each one reaches the file as soon as it is written, because on `app stop` only the
main thread gets an exception, and files written from other threads are never closed.
"""

import csv
import threading
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path("/app/logs")


class RunLog:
    """A CSV file for one run. `row()` is thread-safe."""

    def __init__(self, path: Path, header: list[str]):
        self.path = path
        self._file = open(path, "x", buffering=1, encoding="utf-8", newline="")  # noqa: SIM115
        self._writer = csv.writer(self._file, lineterminator="\n")
        self._lock = threading.Lock()
        self.row(*header)

    def row(self, *values: object) -> None:
        with self._lock:
            self._writer.writerow(values)

    def close(self) -> None:
        with self._lock:
            self._file.close()


def run_name(mode: str, params: str = "", now: datetime | None = None) -> str:
    """`20261012-143005_step_L25` for mode "step" and params "L25"."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}_{mode}_{params}" if params else f"{stamp}_{mode}"


def open_run_log(
    mode: str,
    header: list[str],
    params: str = "",
    log_dir: Path = LOG_DIR,
    now: datetime | None = None,
) -> RunLog:
    """Create a new CSV log; a name taken in the same second gets a -1, -2... suffix."""
    log_dir.mkdir(parents=True, exist_ok=True)
    base = run_name(mode, params, now)
    suffix = 0
    while True:
        name = f"{base}-{suffix}.csv" if suffix else f"{base}.csv"
        try:
            return RunLog(log_dir / name, header)
        except FileExistsError:
            suffix += 1
