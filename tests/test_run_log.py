from datetime import UTC, datetime, timezone

from run_log import open_run_log, run_name

NOW = datetime(2026, 10, 12, 14, 30, 5, tzinfo=UTC)


def test_name_has_time_mode_and_params():
    assert run_name("step", "L25", NOW) == "20261012-143005_step_L25"
    assert run_name("bridge", now=NOW) == "20261012-143005_bridge"


def test_same_second_never_overwrites(tmp_path):
    first = open_run_log("step", ["a"], "L25", tmp_path, NOW)
    first.row(1)
    second = open_run_log("step", ["a"], "L25", tmp_path, NOW)
    second.row(2)
    assert first.path.name == "20261012-143005_step_L25.csv"
    assert second.path.name == "20261012-143005_step_L25-1.csv"
    assert first.path.read_text() == "a\n1\n"
    assert second.path.read_text() == "a\n2\n"


def test_rows_reach_the_file_without_close(tmp_path):
    log = open_run_log("diag", ["t_ms", "peak"], log_dir=tmp_path, now=NOW)
    log.row(1000, 412)
    # Read through a separate handle while the log is still open.
    assert log.path.read_text() == "t_ms,peak\n1000,412\n"


def test_creates_the_log_dir(tmp_path):
    log = open_run_log("diag", ["x"], log_dir=tmp_path / "logs", now=NOW)
    assert log.path.parent == tmp_path / "logs"
